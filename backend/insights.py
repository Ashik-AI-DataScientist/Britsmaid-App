"""Bounded, property-scoped revenue time series using the existing booking basis."""
from datetime import date, timedelta
from fastapi import Depends, HTTPException
from booking_finance import booking_totals, money
from additional_revenue import period_revenue, revenue_totals
from owner_finance import owner_items


def register_insights(api, db, finance_user, check_pid, owner_pids, oid):
    @api.get('/reports/insights')
    async def insights(start: str, end: str, interval: str = 'month', property_id: str = '', user=Depends(finance_user)):
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if first.isoformat() != start or last.isoformat() != end:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Use valid YYYY-MM-DD dates')
        days = (last - first).days + 1
        if last == date.max or days < 1 or days > 731 or interval not in ('day', 'month') or (interval == 'day' and days > 93):
            raise HTTPException(422, 'Choose up to 93 daily points or two years of monthly points')
        query = {'is_deleted': {'$ne': True}}
        assigned = owner_pids(user)
        if property_id:
            check_pid(user, property_id)
            query['_id'] = oid(property_id)
        elif assigned is not None:
            query['_id'] = {'$in': [oid(pid) for pid in assigned]}
        properties = await db.properties.find(query).to_list(None)
        pids = [str(prop['_id']) for prop in properties]
        if property_id and not pids:
            raise HTTPException(404, 'Property not found')
        until = (last + timedelta(days=1)).isoformat()
        buckets = {}
        day = first
        while day <= last:
            key = day.isoformat() if interval == 'day' else day.isoformat()[:7]
            buckets.setdefault(key, {'period': key, 'gross': 0, 'net': 0, 'bookings': 0})
            day += timedelta(days=1)
        async for booking in db.bookings.find({'property_id': {'$in': pids}, 'status': 'confirmed', 'check_in': {'$gte': start, '$lt': until}}):
            key = booking['check_in'] if interval == 'day' else booking['check_in'][:7]
            totals = booking_totals(booking)
            buckets[key]['gross'] += totals['gross']
            buckets[key]['net'] += totals['net']
            buckets[key]['bookings'] += 1
        additions = await period_revenue(db, {'$in': pids}, start, until)
        if user['role'] == 'owner':
            additions = owner_items(additions)
        for item in additions:
            totals = revenue_totals([item])
            key = item['service_date'] if interval == 'day' else item['service_date'][:7]
            buckets[key]['gross'] += totals['gross']
            buckets[key]['net'] += totals['net']
        for bucket in buckets.values():
            bucket['gross'] = money(bucket['gross'])
            bucket['net'] = money(bucket['net'])
        return {'start': start, 'end': end, 'interval': interval, 'points': list(buckets.values()),
                'basis': 'Booking revenue by check-in date; received add-ons by service date. Net is before property expenses and owner TDS.'}
