"""Booking-linked add-ons with explicit allocation and retry-safe item identities."""
from datetime import date
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from booking_finance import money, percent_amount


class RevenueIn(BaseModel):
    id: str = Field(min_length=10, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(min_length=1, max_length=180)
    amount: float = Field(gt=0, le=100000000, allow_inf_nan=False)
    tax: float = Field(default=0, ge=0, allow_inf_nan=False)
    fee: float = Field(default=0, ge=0, allow_inf_nan=False)
    owner_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    owner_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    service_date: str
    status: Literal['received', 'pending', 'refunded'] = 'received'
    notes: str = Field(default='', max_length=3000)
    revision: int = Field(default=0, ge=0)

    @field_validator('service_date')
    @classmethod
    def valid_day(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Use YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def valid_amounts(self):
        if not self.title.strip() or money(self.amount) <= 0 or money(self.tax + self.fee) > money(self.amount):
            raise ValueError('Enter a title and deductions no greater than the positive revenue')
        if self.owner_amount is not None and money(self.owner_amount) > money(self.amount - self.tax - self.fee):
            raise ValueError('Owner allocation exceeds the net additional revenue')
        return self


def revenue_totals(items):
    active = [item for item in items if item.get('status') == 'received']
    gross = money(sum(item['amount'] for item in active))
    deductions = money(sum(item.get('tax', 0) + item.get('fee', 0) for item in active))
    net = money(gross - deductions)
    owner = money(sum(money(item['owner_amount']) if item.get('owner_amount') is not None else percent_amount(
        money(item['amount'] - item.get('tax', 0) - item.get('fee', 0)), item['owner_percent']) for item in active))
    return {'gross': gross, 'deductions': deductions, 'net': net, 'owner': owner, 'britsmaid': money(net - owner)}


async def period_revenue(db, property_filter, start, end):
    rows = []
    async for booking in db.bookings.find({'property_id': property_filter, 'additional_revenue': {'$exists': True}}):
        rows.extend({**item, 'booking_id': str(booking['_id']), 'property_id': booking['property_id'], 'guest_name': booking['guest_name']}
                    for item in booking.get('additional_revenue', []) if start <= item['service_date'] < end)
    return rows


def register_revenue(api, db, admin_user, oid, now_iso, get_booking):
    @api.post('/bookings/{bid}/revenue')
    async def save_revenue(bid: str, body: RevenueIn, user=Depends(admin_user)):
        booking = await db.bookings.find_one({'_id': oid(bid)})
        if not booking:
            raise HTTPException(404, 'Booking not found')
        items = booking.get('additional_revenue', [])
        old = next((item for item in items if item['id'] == body.id), None)
        item = body.model_dump(exclude={'revision'})
        for key in ('amount', 'tax', 'fee'):
            item[key] = money(item[key])
        item['title'] = item['title'].strip()
        if old and all(old.get(key) == value for key, value in item.items()):
            return await get_booking(bid, user)
        if body.revision != (booking.get('revision') or 0):
            raise HTTPException(409, 'Booking changed. Refresh before saving additional revenue.')
        if not old and booking['status'] != 'confirmed':
            raise HTTPException(422, 'Additional revenue requires a confirmed booking')
        if old and not body.notes.strip():
            raise HTTPException(422, 'Explain the revenue correction or refund in Notes')
        if len(items) >= 100 and not old:
            raise HTTPException(422, 'Maximum 100 additional revenue entries per booking')
        item['updated_at'] = now_iso()
        item['updated_by'] = str(user['_id'])
        updated = [item if row['id'] == item['id'] else row for row in items] if old else [*items, item]
        history = {'at': now_iso(), 'actor_id': str(user['_id']), 'before': old, 'after': item}
        result = await db.bookings.update_one({'_id': booking['_id'], 'revision': booking.get('revision')}, {
            '$set': {'additional_revenue': updated}, '$inc': {'revision': 1}, '$push': {'revenue_history': history}})
        if not result.matched_count:
            raise HTTPException(409, 'Booking changed. Refresh before saving additional revenue.')
        return await get_booking(bid, user)
