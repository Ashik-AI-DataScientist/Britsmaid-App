"""Admin activity inbox and independently retried web-push delivery."""
import asyncio
import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from activity_details import describe, snapshot, activity_time

logger = logging.getLogger(__name__)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=4096)
    keys: dict[str, str]

    def validate_endpoint(self):
        try:
            url = urlsplit(self.endpoint)
            port = url.port
        except ValueError:
            raise HTTPException(422, 'Invalid push endpoint')
        allowed = ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')
        if url.scheme != 'https' or url.hostname not in allowed or url.username or url.password or port not in (None, 443):
            raise HTTPException(422, 'Unsupported push service')
        try:
            if len(base64.urlsafe_b64decode(self.keys['p256dh'] + '===')) != 65 or len(base64.urlsafe_b64decode(self.keys['auth'] + '===')) != 16:
                raise ValueError()
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.urlsafe_b64decode(self.keys['p256dh'] + '==='))
        except (KeyError, ValueError):
            raise HTTPException(422, 'Invalid push subscription')


class Activity:
    def __init__(self, db):
        self.db = db

    async def record(self, identity, title, url='/notifications', body=''):
        now = datetime.now(timezone.utc).isoformat()
        await self.db.activities.update_one({'_id': identity}, {'$setOnInsert': {
            'title': title, 'url': url, 'created_at': now, **({'body': body} if body else {})}}, upsert=True)

    def register(self, api, admin_user):
        @api.get('/notifications')
        async def inbox(before: str = '', user=Depends(admin_user)):
            query = {'created_at': {'$lt': before}} if before else {}
            rows = await self.db.activities.find(query).sort('created_at', -1).to_list(100)
            read = await self.db.activity_read.find_one({'_id': str(user['_id'])}) or {}
            return [{**row, 'id': row['_id'], 'unread': row['created_at'] > read.get('through', '')} for row in rows]

        @api.post('/notifications/read')
        async def mark_read(user=Depends(admin_user)):
            await self.db.activity_read.update_one({'_id': str(user['_id'])}, {'$set': {
                'through': datetime.now(timezone.utc).isoformat()}}, upsert=True)
            return {'ok': True}

        @api.get('/notifications/push-key')
        async def push_key(user=Depends(admin_user)):
            key = ec.generate_private_key(ec.SECP256R1())
            public = base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
            private = base64.urlsafe_b64encode(key.private_bytes(serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).decode()
            await self.db.settings.update_one({'_id': 'admin-web-push'}, {'$setOnInsert': {
                'public': public, 'private': private}}, upsert=True)
            settings = await self.db.settings.find_one({'_id': 'admin-web-push'})
            return {'public_key': settings['public']}

        @api.post('/notifications/subscribe')
        async def subscribe(body: SubscriptionIn, user=Depends(admin_user)):
            body.validate_endpoint()
            key = hashlib.sha256(body.endpoint.encode()).hexdigest()
            await self.db.push_subscriptions.update_one({'_id': key}, {'$set': {
                'user_id': str(user['_id']), 'subscription': body.model_dump(), 'created_at': datetime.now(timezone.utc).isoformat()}}, upsert=True)
            return {'ok': True}

        @api.post('/notifications/unsubscribe')
        async def unsubscribe(body: SubscriptionIn, user=Depends(admin_user)):
            await self.db.push_subscriptions.delete_one({'_id': hashlib.sha256(body.endpoint.encode()).hexdigest(), 'user_id': str(user['_id'])})
            return {'ok': True}

    async def deliver(self):
        from pywebpush import webpush, WebPushException
        settings = await self.db.settings.find_one({'_id': 'admin-web-push'})
        if not settings:
            return
        async for subscription in self.db.push_subscriptions.find({}):
            user = await self.db.users.find_one({'_id': ObjectId(subscription['user_id']), 'role': 'admin', 'active': True})
            if not user:
                await self.db.push_subscriptions.delete_one({'_id': subscription['_id']})
                continue
            events = await self.db.activities.find({'created_at': {'$gt': subscription.get('last_event_at', subscription['created_at'])}}).sort('created_at', 1).to_list(100)
            for event in events:
                key = subscription['_id'] + ':' + str(event['_id'])
                if await self.db.push_deliveries.find_one({'_id': key}):
                    await self.db.push_subscriptions.update_one({'_id': subscription['_id']}, {'$set': {'last_event_at': event['created_at']}})
                    continue
                when = activity_time(event['created_at'])
                body = ' · '.join(x for x in (event.get('body', ''), 'Activity: ' + when if when else '') if x)
                # Repeat the contextual heading in body for older installed workers.
                payload = json.dumps({'title': event['title'], 'details': body, 'body': event['title'] + ('\n' + body if body else ''),
                    'url': event.get('url', '/notifications'), 'tag': str(event['_id'])})
                try:
                    await run_in_threadpool(webpush, subscription_info=subscription['subscription'], data=payload,
                        vapid_private_key=settings['private'], vapid_claims={'sub': 'https://app.britsmaid.in'}, ttl=3600, timeout=10)
                    await self.db.push_deliveries.update_one({'_id': key}, {'$set': {'at': datetime.now(timezone.utc).isoformat()}}, upsert=True)
                    await self.db.push_subscriptions.update_one({'_id': subscription['_id']}, {'$set': {'last_event_at': event['created_at']}})
                except WebPushException as error:
                    if error.response is not None and error.response.status_code in (404, 410):
                        await self.db.push_subscriptions.delete_one({'_id': subscription['_id']})
                    break

    async def loop(self):
        while True:
            try:
                day = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
                async for task in self.db.cleaning.find({'status': {'$nin': ['completed', 'cancelled']}, 'date': {'$lte': day}}):
                    details = await describe(self.db, 'PUT', '/api/cleaning/' + str(task['_id']), action='Cleaning pending')
                    await self.record(f"cleaning-due:{task['_id']}:{day}", **details)
                async for issue in self.db.system_issues.find({'status': 'open'}):
                    await self.record(f"issue:{issue['_id']}:{issue.get('first_seen', '')}", issue.get('title', 'System needs attention'), '/issues')
                await self.deliver()
            except Exception:
                logger.exception('Admin activity delivery will retry')
            await asyncio.sleep(30)


class ActivityMiddleware:
    def __init__(self, app, activity):
        self.app, self.activity = app, activity

    async def __call__(self, scope, receive, send):
        path, method = scope.get('path', ''), scope.get('method', '')
        if scope['type'] != 'http' or method not in ('POST', 'PUT', 'DELETE') or not path.startswith('/api/') or path.startswith(('/api/auth/', '/api/notifications', '/api/files/')) or path == '/api/upload' or path.endswith('/verify-invite-password'):
            return await self.app(scope, receive, send)
        parts = path.strip('/').split('/')
        before = {}
        try:
            if len(parts) > 2:
                before = await snapshot(self.activity.db, parts[1], parts[2])
        except Exception:
            logger.exception('Could not read activity context')
        status, payload = 0, bytearray()

        async def observe(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            if message['type'] == 'http.response.body' and len(payload) < 262144:
                payload.extend(message.get('body', b'')[:262144 - len(payload)])
            await send(message)

        await self.app(scope, receive, observe)
        if 200 <= status < 300:
            try:
                try:
                    data = json.loads(payload or b'{}')
                except (ValueError, UnicodeDecodeError):
                    # Oversized/non-JSON acknowledgements still represent a
                    # successful activity; never retain their response content.
                    data = {}
                signature = hashlib.sha256((method + path + json.dumps(data, sort_keys=True)).encode()).hexdigest()
                state_id = method + path
                previous = await self.activity.db.activity_state.find_one({'_id': state_id})
                # A bare acknowledgement is not a state snapshot: two real
                # actions can both return {ok: true}. Only dedupe identifiable
                # resource snapshots (for example a retried revenue save).
                identifiable = isinstance(data, dict) and ('id' in data or 'revision' in data)
                if identifiable and previous and previous.get('signature') == signature:
                    return
                identity = secrets.token_hex(16)
                details = await describe(self.activity.db, method, path, data, before)
                await self.activity.record(identity, **details)
                await self.activity.db.activity_state.update_one({'_id': state_id}, {'$set': {'signature': signature}}, upsert=True)
            except DuplicateKeyError:
                pass
            except Exception:
                logger.exception('Could not record completed activity')
