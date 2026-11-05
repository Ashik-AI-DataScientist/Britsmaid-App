"""Versioned optional booking breakdown. Legacy bookings retain their original meaning."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal, Optional
from pydantic import BaseModel, Field
from fastapi import HTTPException


def money(value):
    try:
        number = Decimal(str(value or 0))
        if not number.is_finite():
            raise InvalidOperation()
        return float(number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise HTTPException(422, 'Enter a valid amount within the supported currency range') from None


def percent_amount(value, percent):
    return money(Decimal(str(value)) * Decimal(str(percent)) / 100)


def amount_percent(amount, base):
    if base <= 0:
        return None
    return float((Decimal(str(amount)) * 100 / Decimal(str(base))).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP))


class Charge(BaseModel):
    percent: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)
    amount: float = Field(0, ge=0, allow_inf_nan=False)
    manual: bool = False
    base: Literal['gross', 'excluding_gst'] = 'excluding_gst'
    entry_mode: Optional[Literal['percent', 'amount']] = None


class BookingFinance(BaseModel):
    version: Literal[1] = 1
    gst_included: bool = True
    gst: Charge = Field(default_factory=Charge)
    platform_fee: Charge = Field(default_factory=Charge)
    platform_tax: Charge = Field(default_factory=Charge)
    misc_amount: float = Field(0, ge=0, allow_inf_nan=False)
    misc_title: str = Field('', max_length=150)
    misc_notes: str = Field('', max_length=2000)


def calculate(gross, detail):
    gross = money(gross)
    f = BookingFinance.model_validate(detail).model_dump()
    for key in ('gst', 'platform_fee', 'platform_tax'):
        if f[key]['entry_mode']:
            f[key]['manual'] = f[key]['entry_mode'] == 'amount'
    gst = f['gst']
    if not gst['manual']:
        rate = gst['percent'] or 0
        gst['amount'] = money(Decimal(str(gross)) * Decimal(str(rate)) / Decimal(str(100 + rate if f['gst_included'] else 100)))
    gst['amount'] = money(gst['amount'])
    # Exclusive mode means the entered amount is before GST; guest total is derived.
    guest_total = gross if f['gst_included'] else money(gross + gst['amount'])
    subtotal = money(guest_total - gst['amount'])
    gst['effective_percent'] = amount_percent(gst['amount'], subtotal)
    if gst['entry_mode'] == 'amount':
        if gst['amount'] and (subtotal <= 0 or gst['effective_percent'] > 100):
            raise HTTPException(422, 'GST amount must have a positive taxable base and an effective rate no greater than 100%')
        gst['percent'] = gst['effective_percent']
    for key in ('platform_fee', 'platform_tax'):
        line = f[key]
        if not line['manual']:
            line['amount'] = money(Decimal(str(guest_total if line['base'] == 'gross' else subtotal)) * Decimal(str(line['percent'] or 0)) / 100)
        line['amount'] = money(line['amount'])
        base = guest_total if line['base'] == 'gross' else subtotal
        line['effective_percent'] = amount_percent(line['amount'], base)
        if line['entry_mode'] == 'amount':
            line['percent'] = line['effective_percent']
    if f['misc_amount'] and not f['misc_title'].strip():
        raise HTTPException(422, 'Add a title for the other booking expense')
    f['misc_amount'] = money(f['misc_amount'])
    net = money(subtotal - f['platform_fee']['amount'] - f['platform_tax']['amount'] - f['misc_amount'])
    if net < 0:
        raise HTTPException(422, 'Booking deductions cannot exceed the guest payment')
    f.update(guest_total=guest_total, net_revenue=net)
    return f


def booking_totals(booking):
    f = booking.get('financials')
    if not f:
        return dict(gross=money(booking.get('amount')), gst=0, commission=money(booking.get('ota_commission')),
                    platform_tax=0, misc=0, net=money(booking.get('amount', 0) - booking.get('ota_commission', 0)))
    f = calculate(booking.get('amount'), f)
    return dict(gross=f['guest_total'], gst=f['gst']['amount'], commission=f['platform_fee']['amount'],
                platform_tax=f['platform_tax']['amount'], misc=f['misc_amount'], net=f['net_revenue'])


def expense_shares(expense, prop):
    if expense.get('treatment') in ('before_split', 'reference'):
        return 0, 0
    if expense.get('allocation'):
        return expense['allocation']['owner_amount'], expense['allocation']['britsmaid_amount']
    if expense['type'] == 'other':
        return money(expense['amount']), 0
    if expense['type'] == 'electricity' and prop.get('electricity_mode') == 'split_half':
        owner = money(Decimal(str(expense['amount'])) / 2)
        return owner, money(expense['amount'] - owner)
    return 0, 0


class ExpenseAllocation(BaseModel):
    owner_percent: float = Field(100, ge=0, le=100, allow_inf_nan=False)
    britsmaid_percent: float = Field(0, ge=0, le=100, allow_inf_nan=False)
    owner_amount: float = Field(0, ge=0, allow_inf_nan=False)
    britsmaid_amount: float = Field(0, ge=0, allow_inf_nan=False)
    manual: bool = False
    entry_mode: Optional[Literal['percent', 'amount']] = None
    amount_side: Literal['owner', 'britsmaid'] = 'owner'


def allocate(total, allocation):
    a = ExpenseAllocation.model_validate(allocation).model_dump()
    total = money(total)
    if a['entry_mode']:
        a['manual'] = a['entry_mode'] == 'amount'
    if a['entry_mode'] != 'amount' and abs(a['owner_percent'] + a['britsmaid_percent'] - 100) > .00001:
        raise HTTPException(422, 'Owner and Britsmaid percentages must add up to 100%')
    if not a['manual']:
        a['owner_amount'] = money(Decimal(str(total)) * Decimal(str(a['owner_percent'])) / 100)
        a['britsmaid_amount'] = money(total - a['owner_amount'])
    else:
        a['owner_amount'], a['britsmaid_amount'] = money(a['owner_amount']), money(a['britsmaid_amount'])
        if money(a['owner_amount'] + a['britsmaid_amount']) != total:
            raise HTTPException(422, 'Owner and Britsmaid amounts must equal the total expense')
        if a['entry_mode'] == 'amount':
            a['owner_percent'] = amount_percent(a['owner_amount'], total) or 0
            a['britsmaid_percent'] = float(Decimal('100') - Decimal(str(a['owner_percent'])))
    return a


def expense_view(expense, prop):
    """Resolve old property rules for display without rewriting historical records."""
    e = dict(expense)
    e.pop('change_history', None)
    e['media_ids'] = e.get('media_ids') or []
    e['notes'] = e.get('notes') or ''
    e['title'] = e.get('title') or ('Electricity' if e.get('type') == 'electricity' else 'Other expense')
    treatment = e.get('treatment')
    if not treatment:
        treatment = 'before_split' if e['type'] == 'pre_split' else 'reference' if e['type'] == 'electricity' and not e.get('allocation') and prop.get('electricity_mode') != 'split_half' else 'after_split'
    e['treatment'] = treatment
    owner, bm = expense_shares(expense, prop)
    e.update(owner_amount=owner, britsmaid_amount=bm, revision=e.get('revision', 0), legacy_rule=not bool(expense.get('treatment')))
    if treatment == 'after_split' and not e.get('allocation'):
        e['allocation'] = {'owner_amount': owner, 'britsmaid_amount': bm,
            'owner_percent': amount_percent(owner, e['amount']) or 0,
            'britsmaid_percent': amount_percent(bm, e['amount']) or 0, 'manual': False}
    return e


def booking_expense_item(booking):
    f = booking.get('financials') or {}
    if not f.get('misc_amount'):
        return None
    return {'id': 'booking:' + str(booking['_id']), 'booking_id': str(booking['_id']), 'source': 'booking',
            'property_id': booking['property_id'], 'month': booking['check_in'][:7], 'type': 'pre_split', 'treatment': 'before_split',
            'title': f.get('misc_title') or 'Other booking expense', 'notes': f.get('misc_notes', ''),
            'amount': money(f['misc_amount']), 'allocation': None, 'media_ids': [], 'revision': booking.get('revision', 0)}
