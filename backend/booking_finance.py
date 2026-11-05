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


class Charge(BaseModel):
    percent: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)
    amount: float = Field(0, ge=0, allow_inf_nan=False)
    manual: bool = False
    base: Literal['gross', 'excluding_gst'] = 'excluding_gst'


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
    gst = f['gst']
    if not gst['manual']:
        rate = gst['percent'] or 0
        gst['amount'] = money(Decimal(str(gross)) * Decimal(str(rate)) / Decimal(str(100 + rate if f['gst_included'] else 100)))
    gst['amount'] = money(gst['amount'])
    # Exclusive mode means the entered amount is before GST; guest total is derived.
    guest_total = gross if f['gst_included'] else money(gross + gst['amount'])
    subtotal = money(guest_total - gst['amount'])
    for key in ('platform_fee', 'platform_tax'):
        line = f[key]
        if not line['manual']:
            line['amount'] = money(Decimal(str(guest_total if line['base'] == 'gross' else subtotal)) * Decimal(str(line['percent'] or 0)) / 100)
        line['amount'] = money(line['amount'])
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


def allocate(total, allocation):
    a = ExpenseAllocation.model_validate(allocation).model_dump()
    total = money(total)
    if abs(a['owner_percent'] + a['britsmaid_percent'] - 100) > .00001:
        raise HTTPException(422, 'Owner and Britsmaid percentages must add up to 100%')
    if not a['manual']:
        a['owner_amount'] = money(Decimal(str(total)) * Decimal(str(a['owner_percent'])) / 100)
        a['britsmaid_amount'] = money(total - a['owner_amount'])
    else:
        a['owner_amount'], a['britsmaid_amount'] = money(a['owner_amount']), money(a['britsmaid_amount'])
        if money(a['owner_amount'] + a['britsmaid_amount']) != total:
            raise HTTPException(422, 'Owner and Britsmaid amounts must equal the total expense')
    return a
