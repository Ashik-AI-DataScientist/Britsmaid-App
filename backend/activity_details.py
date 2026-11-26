"""Small, allowlisted activity summaries; never retain request bodies or credentials."""
from datetime import date, datetime, timedelta, timezone
from bson import ObjectId

FIELDS = {k: 1 for k in ('name', 'role', 'property_id', 'property_ids', 'booking_id',
    'check_in', 'check_out', 'date', 'month', 'paid_on', 'status', 'title', 'number',
    'issue_date', 'guest_number', 'guest_checked_in_at', 'assigned_to', 'cleaner_name',
    'draft.title', 'published.title', 'lesson.title')}
COLLECTIONS = {'bookings': 'bookings', 'cleaning': 'cleaning', 'properties': 'properties',
    'users': 'users', 'expenses': 'expenses', 'payouts': 'payouts', 'invoices': 'invoices',
    'owner-reports': 'owner_reports', 'guest-ids': 'guest_ids', 'guest': 'guest_ids',
    'training-lessons': 'training_lessons', 'training-assignments': 'training_assignments'}


def clean(value, limit=180):
    return ' '.join(str(value or '').split())[:limit]


def day(value):
    try:
        return date.fromisoformat(value).strftime('%d %b %Y').lstrip('0')
    except (ValueError, TypeError):
        return ''


def activity_time(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%d %b, %H:%M IST').lstrip('0')
    except (ValueError, TypeError):
        return ''


async def snapshot(db, resource, identifier):
    collection = COLLECTIONS.get(resource)
    if collection and ObjectId.is_valid(identifier):
        return await db[collection].find_one({'_id': ObjectId(identifier)}, FIELDS) or {}
    return {}


async def describe(db, method, path, data=None, before=None, action=None):
    """Use persisted resource relationships, including a pre-delete safe snapshot."""
    parts = path.strip('/').split('/')
    resource = parts[1] if len(parts) > 1 else ''
    data = data if isinstance(data, dict) else {}
    before = before or {}
    identifier = parts[2] if len(parts) > 2 else data.get('id', '')
    if resource == 'guest':
        identifier = data.get('id', '')
    lookup = resource
    if resource == 'training' and len(parts) > 2 and parts[2] in ('lessons', 'assignments'):
        lookup, identifier = 'training-' + parts[2], parts[3] if len(parts) > 3 else data.get('id', '')
    doc = await snapshot(db, lookup, identifier) or before
    # Prefer the saved response's allowlisted fields over a later concurrent edit.
    doc = {**doc, **{key: value for key, value in data.items() if key in FIELDS}}
    verb = {'POST': 'recorded', 'PUT': 'updated', 'DELETE': 'removed'}.get(method, 'updated')
    title, body, url = '', [], '/notifications'
    booking = doc if resource == 'bookings' else {}
    bid = doc.get('booking_id')
    if not booking and bid:
        booking = await snapshot(db, 'bookings', bid)
    pid = doc.get('property_id') or booking.get('property_id')
    prop = doc if resource == 'properties' else await snapshot(db, 'properties', pid)
    property_name = clean(prop.get('name'))
    if ObjectId.is_valid(identifier):
        route = {'bookings': 'booking', 'cleaning': 'cleaning', 'properties': 'property', 'invoices': 'invoice', 'owner-reports': 'report'}.get(resource)
        if route:
            url = f'/{route}/{identifier}'
    if resource == 'bookings':
        title = 'Booking ' + verb
        if path.endswith('/revenue'):
            title = 'Additional revenue saved'
        elif path.endswith('/guest-link'):
            title = 'Guest upload link revoked' if method == 'DELETE' else 'Guest upload link created'
        elif path.endswith('/check-in') or doc.get('guest_checked_in_at') != before.get('guest_checked_in_at'):
            title = 'Guests checked in' if doc.get('guest_checked_in_at') else 'Guest check-in undone'
        elif path.endswith('/guest-admin-action'):
            title = 'Guest ID review updated'
        elif path.endswith('/cancel') or (doc.get('status') == 'cancelled' and before.get('status') != 'cancelled'):
            title = 'Booking cancelled'
        elif doc.get('status') == 'blocked':
            title = 'Calendar block ' + verb
    elif resource == 'cleaning':
        title = 'Cleaning ' + verb
        status = doc.get('status')
        if status and status != before.get('status') and method != 'DELETE':
            title = {'completed': 'Cleaning completed', 'awaiting_review': 'Cleaning ready for review',
                'in_progress': 'Cleaning in progress', 'cancelled': 'Cleaning cancelled', 'pending': 'Cleaning scheduled'}.get(status, title)
        elif '/checklist' in path:
            title = 'Cleaning checklist updated'
        elif '/media' in path:
            title = 'Cleaning photo removed' if method == 'DELETE' else 'Cleaning photo added'
        elif doc.get('assigned_to') != before.get('assigned_to') and before:
            title = 'Cleaning assignment updated'
        if day(doc.get('date')):
            body.append('Cleaning date: ' + day(doc['date']))
    elif resource == 'users':
        title = 'Team member ' + ('removed' if method == 'DELETE' else 'added' if method == 'POST' else 'updated')
        if path.endswith('/reset-password'):
            title = 'Team member password changed'
        name = clean(doc.get('name'))
        if name:
            title += ' · ' + name
        if doc.get('role'):
            body.append('Role: ' + clean(doc['role']))
        names = []
        for assigned in (doc.get('property_ids') or [])[:5]:
            p = await snapshot(db, 'properties', assigned)
            if p.get('name'):
                names.append(clean(p['name']))
        if names:
            body.append('Properties: ' + '; '.join(names))
        url = '/staff'
    elif resource in ('guest', 'guest-ids'):
        title = 'Guest ID ' + ('submitted' if resource == 'guest' else 'removed' if method == 'DELETE' else
            {'verified': 'approved', 'rejected': 'rejected', 'pending': 'review updated'}.get(doc.get('status'), 'updated'))
        if doc.get('guest_number'):
            body.append('Guest ' + clean(doc['guest_number'], 4))
        if bid:
            url = '/guests?booking_id=' + str(bid)
    elif resource in ('expenses', 'payouts', 'owner-reports', 'invoices', 'properties'):
        title = {'expenses': 'Expense', 'payouts': 'Owner payout', 'owner-reports': 'Owner report', 'invoices': 'Invoice', 'properties': 'Property'}[resource] + ' ' + verb
        if resource == 'invoices' and path.endswith('/status'):
            title = 'Invoice marked ' + clean(doc.get('status', 'updated'))
        if doc.get('month'):
            try:
                body.append('Period: ' + date.fromisoformat(doc['month'] + '-01').strftime('%B %Y'))
            except (ValueError, TypeError):
                pass
        if resource == 'expenses' and doc.get('title'):
            body.append('Expense: ' + clean(doc['title']))
        if resource == 'invoices' and doc.get('number'):
            body.append(clean(doc['number']))
        if resource in ('expenses', 'payouts') and pid:
            url = '/property/' + str(pid)
        if path.endswith('/ical-sync'):
            title = 'Calendar sync completed'
        elif path.endswith('/ical-export'):
            title = 'Availability link revoked' if method == 'DELETE' else 'Availability link created'
    elif resource == 'training':
        title = 'Training completed' if path.endswith('/complete') else 'Training ' + verb
        for suffix, label in (('/publish', 'Training lesson published'), ('/archive', 'Training lesson archived'), ('/assign', 'Training assigned'), ('/schedule', 'Training schedule updated')):
            if path.endswith(suffix):
                title = label
        lesson_name = (doc.get('lesson') or doc.get('draft') or doc.get('published') or {}).get('title')
        if lesson_name:
            body.append('Lesson: ' + clean(lesson_name))
        if doc.get('cleaner_name'):
            body.append('Team member: ' + clean(doc['cleaner_name']))
        url = '/training'
    elif resource == 'system':
        title = {'/api/system/backups/run': 'Backup completed', '/api/system/photo-retention': 'Photo retention settings updated',
            '/api/system/photo-retention/run': 'Photo retention cleanup completed'}.get(path, 'System settings updated')
    if not title:
        title = {'POST': 'Recorded', 'PUT': 'Updated', 'DELETE': 'Removed'}.get(method, 'Updated') + ' ' + clean(resource.replace('-', ' '))
    if action:
        title = action
    if property_name:
        title += ' · ' + property_name
    if booking and day(booking.get('check_in')) and day(booking.get('check_out')):
        body.append('Stay: ' + day(booking['check_in']) + ' – ' + day(booking['check_out']))
    return {'title': clean(title, 240), 'body': clean(' · '.join(body), 600), 'url': url}
