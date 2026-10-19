"""Versioned cleaner lessons and idempotent assignments. All timestamps are UTC."""
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from typing import Literal
from bson import ObjectId
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError
from urllib.parse import urlsplit


class LessonIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    instructions: str = Field(min_length=1, max_length=20000)
    links: list[str] = Field(default_factory=list, max_length=10)
    onboarding: bool = False
    refresher_days: int | None = Field(default=None, ge=1, le=3650)
    due_days: int = Field(default=7, ge=0, le=365)
    @field_validator('title', 'instructions')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter text')
        return value.strip()
    @field_validator('links')
    @classmethod
    def safe_links(cls, links):
        for link in links:
            u = urlsplit(link)
            if u.scheme != 'https' or not u.hostname or u.username or u.password:
                raise ValueError('Use public HTTPS image or video links without credentials')
        return links


class AssignIn(BaseModel):
    cleaner_ids: list[str] = Field(default_factory=list, max_length=500)
    all_active: bool = False
    due_on: date | None = None
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')


def utcnow():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class Training:
    def __init__(self, db, oid, out):
        self.db, self.oid, self.out = db, oid, out

    async def indexes(self):
        await self.db.training_assignments.create_index('assignment_key', unique=True)
        await self.db.training_assignments.create_index([('cleaner_id', 1), ('due_at', 1)])

    async def assign(self, lesson, cleaner, key, due=None, source='manual', now=None):
        now = now or utcnow()
        # Immutable snapshot is the evidence, even after editing/archiving a lesson.
        snapshot = lesson['published']
        row = {'assignment_key': key, 'lesson_id': str(lesson['_id']), 'cleaner_id': str(cleaner['_id']),
               'cleaner_name': cleaner['name'], 'lesson': snapshot, 'source': source,
               'assigned_at': now.isoformat(), 'due_at': (due or now + timedelta(days=snapshot['due_days'])).isoformat(),
               'completed_at': None}
        try:
            await self.db.training_assignments.update_one({'assignment_key': key}, {'$setOnInsert': row}, upsert=True)
        except DuplicateKeyError:
            pass
        return await self.db.training_assignments.find_one({'assignment_key': key})

    async def onboarding(self, cleaner):
        if cleaner.get('role') != 'cleaner' or not cleaner.get('active'):
            return
        for lesson in await self.db.training_lessons.find({'archived': False, 'published.onboarding': True}).to_list(None):
            await self.assign(lesson, cleaner, f"onboarding:{lesson['_id']}:{cleaner['_id']}", source='onboarding')

    async def schedule(self, now=None):
        now = now or utcnow()
        # Recover interrupted onboarding after account creation without enrolling old staff retroactively.
        for lesson in await self.db.training_lessons.find({'archived': False, 'published.onboarding': True}).to_list(None):
            for cleaner in await self.db.users.find({'active': True, 'role': 'cleaner', 'created_at': {'$gte': lesson['published_at']}}).to_list(None):
                await self.assign(lesson, cleaner, f"onboarding:{lesson['_id']}:{cleaner['_id']}", source='onboarding', now=now)
        for previous in await self.db.training_assignments.find({'completed_at': {'$ne': None}}).to_list(None):
            days = previous['lesson'].get('refresher_days')
            if not days:
                continue
            cleaner = await self.db.users.find_one({'_id': ObjectId(previous['cleaner_id']), 'role': 'cleaner', 'active': True})
            lesson = await self.db.training_lessons.find_one({'_id': ObjectId(previous['lesson_id']), 'archived': False})
            if not cleaner or not lesson or not lesson.get('published'):
                continue
            due = parse_time(previous['completed_at']) + timedelta(days=days)
            # Schedule immediately so the cleaner sees the next refresher due date.
            await self.assign(lesson, cleaner, f"refresher:{previous['_id']}", due=due, source='refresher', now=now)

    def view(self, row, now=None):
        row = self.out(row)
        row.pop('assignment_key', None)
        row['status'] = 'completed' if row.get('completed_at') else 'overdue' if parse_time(row['due_at']) < (now or utcnow()) else 'pending'
        return row

    def register(self, api, admin_user, current_user):
        @api.get('/training/lessons')
        async def lessons(user=Depends(admin_user)):
            return [self.out(x) for x in await self.db.training_lessons.find({}).sort('updated_at', -1).to_list(1000)]

        @api.post('/training/lessons')
        async def create(body: LessonIn, user=Depends(admin_user)):
            now = utcnow().isoformat()
            row = {'draft': body.model_dump(), 'revision': 0, 'archived': False, 'created_at': now, 'updated_at': now}
            row['_id'] = (await self.db.training_lessons.insert_one(row)).inserted_id
            return self.out(row)

        @api.put('/training/lessons/{lid}')
        async def edit(lid: str, body: LessonIn, user=Depends(admin_user)):
            r = await self.db.training_lessons.update_one({'_id': self.oid(lid), 'archived': False}, {'$set': {'draft': body.model_dump(), 'updated_at': utcnow().isoformat()}})
            if not r.matched_count:
                raise HTTPException(404, 'Active lesson not found')
            return self.out(await self.db.training_lessons.find_one({'_id': self.oid(lid)}))

        @api.post('/training/lessons/{lid}/publish')
        async def publish(lid: str, user=Depends(admin_user)):
            row = await self.db.training_lessons.find_one({'_id': self.oid(lid), 'archived': False})
            if not row:
                raise HTTPException(404, 'Active lesson not found')
            if row.get('published') and all(row['published'].get(k) == v for k, v in row['draft'].items()):
                return self.out(row)
            revision = row['revision'] + 1
            snapshot = {**row['draft'], 'revision': revision, 'published_at': utcnow().isoformat(), 'published_by': str(user['_id'])}
            r = await self.db.training_lessons.update_one({'_id': row['_id'], 'revision': row['revision'], 'draft': row['draft'], 'archived': False},
                {'$set': {'revision': revision, 'published': snapshot, 'published_at': snapshot['published_at'], 'updated_at': snapshot['published_at']}, '$push': {'versions': snapshot}})
            if not r.matched_count:
                raise HTTPException(409, 'Lesson changed; refresh before publishing')
            return self.out(await self.db.training_lessons.find_one({'_id': row['_id']}))

        @api.post('/training/lessons/{lid}/archive')
        async def archive(lid: str, user=Depends(admin_user)):
            r = await self.db.training_lessons.update_one({'_id': self.oid(lid)}, {'$set': {'archived': True, 'updated_at': utcnow().isoformat()}})
            if not r.matched_count:
                raise HTTPException(404, 'Lesson not found')
            return {'ok': True}

        @api.post('/training/lessons/{lid}/assign')
        async def assign(lid: str, body: AssignIn, user=Depends(admin_user)):
            lesson = await self.db.training_lessons.find_one({'_id': self.oid(lid), 'archived': False, 'published': {'$exists': True}})
            if not lesson:
                raise HTTPException(409, 'Publish an active lesson before assigning it')
            q = {'active': True, 'role': 'cleaner'}
            if not body.all_active:
                if not body.cleaner_ids:
                    raise HTTPException(422, 'Choose at least one cleaner')
                q['_id'] = {'$in': [self.oid(x) for x in set(body.cleaner_ids)]}
            cleaners = await self.db.users.find(q).to_list(None)
            if not body.all_active and len(cleaners) != len(set(body.cleaner_ids)):
                raise HTTPException(422, 'Choose active cleaners only')
            # Date-only entry means end of day in the business timezone; store UTC explicitly.
            due = datetime.combine(body.due_on + timedelta(days=1), datetime.min.time(), ZoneInfo('Asia/Kolkata')).astimezone(timezone.utc) if body.due_on else None
            return [self.view(await self.assign(lesson, c, f"manual:{lid}:{body.request_id}:{c['_id']}", due=due)) for c in cleaners]

        @api.get('/training/assignments')
        async def assignments(user=Depends(current_user)):
            if user['role'] not in ('admin', 'cleaner'):
                raise HTTPException(403, 'Training is available to admins and cleaners')
            # Scheduler has its own background retry; reads do not create assignments.
            q = {} if user['role'] == 'admin' else {'cleaner_id': str(user['_id'])}
            return [self.view(x) for x in await self.db.training_assignments.find(q).sort('due_at', 1).to_list(2000)]

        @api.post('/training/assignments/{aid}/complete')
        async def complete(aid: str, user=Depends(current_user)):
            if user['role'] != 'cleaner':
                raise HTTPException(403, 'Only the assigned cleaner can acknowledge completion')
            q = {'_id': self.oid(aid), 'cleaner_id': str(user['_id'])}
            row = await self.db.training_assignments.find_one(q)
            if not row:
                raise HTTPException(404, 'Assignment not found')
            await self.db.training_assignments.update_one({**q, 'completed_at': None}, {'$set': {'completed_at': utcnow().isoformat(), 'completed_by': str(user['_id'])}})
            return self.view(await self.db.training_assignments.find_one(q))

        @api.post('/training/schedule')
        async def schedule(user=Depends(admin_user)):
            await self.schedule()
            return {'ok': True}
