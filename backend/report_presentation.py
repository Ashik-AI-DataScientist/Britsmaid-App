"""Read-only report presentation. Saved financial figures are never recalculated."""
import math
from html import escape
from urllib.parse import quote
from booking_finance import money


def amount(value):
    try:
        number = float(value or 0)
        return money(number) if math.isfinite(number) else 0
    except (TypeError, ValueError):
        return 0


def report_presentation(s):
    items = []
    for original in s.get('deduction_items') or []:
        if not isinstance(original, dict) or amount(original.get('amount')) <= 0:
            continue
        item = dict(original, amount=amount(original['amount']))
        if not item.get('treatment'):
            item['treatment'] = 'before_split' if item.get('type') == 'pre_split' else 'reference' if item.get('type') == 'electricity' and not item.get('allocation') and not item.get('owner_amount') and not item.get('britsmaid_amount') and s.get('electricity_mode') == 'owner' else 'after_split'
        items.append(item)
    if amount(s.get('electricity_total')) > 0 and not any(e.get('type') == 'electricity' for e in items):
        items.append(dict(id='legacy-electricity', summary=True, type='electricity', title='Electricity', amount=amount(s['electricity_total']),
            treatment='after_split' if s.get('owner_electricity') or s.get('britsmaid_electricity') else 'reference',
            owner_amount=s.get('owner_electricity'), britsmaid_amount=s.get('britsmaid_electricity'), notes='Summary retained from this saved report.'))
    def saved(key, fallback):
        return fallback if s.get(key) is None else amount(s[key])
    def total(entries):
        return money(sum(e['amount'] for e in entries))
    owner_after = saved('owner_after_expenses', money(amount(s.get('owner_electricity')) + amount(s.get('other_deductions'))))
    bm_after = saved('britsmaid_after_expenses', money(amount(s.get('britsmaid_electricity')) + amount(s.get('britsmaid_other_expenses'))))
    before_fallback = total([e for e in items if e['treatment'] == 'before_split']) if s.get('pre_split_deductions') is None and s.get('booking_misc') is None else money(amount(s.get('pre_split_deductions')) + amount(s.get('booking_misc')))
    definitions = [
        ('before_split', 'Before revenue split', saved('expense_before_total', before_fallback)),
        ('after_split', 'After revenue split', saved('expense_after_total', max(total([e for e in items if e['treatment'] == 'after_split']), money(owner_after + bm_after)))),
        ('reference', 'Reference only · not deducted', saved('expense_reference_total', total([e for e in items if e['treatment'] == 'reference']))),
    ]
    groups = []
    for key, label, value in definitions:
        entries = [dict(e) for e in items if e['treatment'] == key]
        difference = money(value - total(entries))
        if difference > 0:
            entries.append(dict(id='saved-' + key, summary=True, amount=difference, treatment=key,
                title='Additional expenses recorded in this saved statement', notes='The saved total is retained. Individual source details were not included in this older report.'))
        if value > 0 or entries:
            groups.append(dict(key=key, label=label, total=value, items=entries, mismatch=difference < 0))
    return dict(groups=groups, ownerAfter=owner_after, bmAfter=bm_after, before=definitions[0][2], after=definitions[1][2], reference=definitions[2][2],
        totalExpenses=money(sum(g[2] for g in definitions)), bookingDeductions=money(amount(s.get('ota_commission')) + amount(s.get('gst_total')) + amount(s.get('platform_tax'))),
        bookingTaxes=money(amount(s.get('gst_total')) + amount(s.get('platform_tax'))))


def expense_html(item, currency, token=None):
    content = f'<p>{escape(item.get("notes") or "No additional note recorded")}</p>'
    if item['treatment'] == 'before_split':
        content += '<small>Deducted once before calculating either share.</small>'
    elif item['treatment'] == 'reference':
        content += '<small>Reference only: not deducted from either share.</small>'
    else:
        allocation = item.get('allocation') or {}
        for who, label in [('owner', 'Owner'), ('britsmaid', 'Britsmaid')]:
            value = allocation.get(who + '_amount', item.get(who + '_amount'))
            if value is not None and amount(value) > 0:
                percent = allocation.get(who + '_percent')
                suffix = f' ({escape(str(percent))}%)' if percent is not None else ''
                content += f'<div class="row"><span>{label}{suffix}</span><span>{currency(value)}</span></div>'
        content += '<small>Deducted after the revenue split.</small>'
    for i, mid in enumerate(item.get('media_ids') or []):
        if token:
            href = '/api/public/reports/' + quote(token, safe='') + '/media/' + quote(str(mid), safe='')
            content += f'<p><a href="{escape(href)}" target="_blank" rel="noopener">View attachment {i + 1}</a></p>'
    return f'<details><summary><span>{escape(item.get("title") or "Other expense")}</span><span>{currency(item["amount"])}</span></summary>{content}</details>'


def public_payout_sections(s, currency, token):
    p = report_presentation(s)
    def row(label, value, deduction=False):
        return f'<div class="row"><span>{label}</span><span>{"-" if deduction else ""}{currency(value)}</span></div>'
    def disclosure(label, value, contents, deduction=False):
        return f'<details><summary><span>{label}</span><span>{"-" if deduction else ""}{currency(value)}</span></summary>{contents}</details>'
    group_map = {g['key']: g for g in p['groups']}
    def records(key):
        group = group_map.get(key)
        if not group:
            return ''
        warning = '<p>Saved expense totals differ from the available details. Ask the admin to review this statement.</p>' if group['mismatch'] else ''
        return warning + ''.join(expense_html(item, currency, token) for item in group['items'])
    calculation = row('Gross guest payments', s.get('gross', 0))
    if p['bookingDeductions']:
        lines = ''.join(row(label, s.get(key, 0)) for key, label in [('ota_commission', 'OTA commissions'), ('gst_total', 'Booking GST'), ('platform_tax', 'Other tax deductions')] if s.get(key))
        calculation += disclosure('Booking deductions', p['bookingDeductions'], lines, True)
    if 'before_split' in group_map:
        calculation += disclosure('Expenses before revenue split', p['before'], records('before_split'), True)
    calculation += row('Revenue available to split', s.get('net_revenue', 0)) + row(f'Owner allocated share ({s.get("owner_share_percent", 0):g}%)', s.get('owner_share', 0))
    if p['ownerAfter'] > 0:
        calculation += disclosure('Owner expenses after split', p['ownerAfter'], records('after_split') + '<small>Only the owner contribution above is deducted from the owner share.</small>', True)
    if s.get('owner_before_tds') is not None:
        calculation += row('Owner balance before TDS', s['owner_before_tds'])
    if s.get('owner_tds_percent') or s.get('owner_tds'):
        calculation += row(f'Owner TDS ({s.get("owner_tds_percent") or 2:g}%) · monthly total', s.get('owner_tds', 0), True)
    calculation += '<div class="row"><b>Owner final payout</b><b>' + currency(s.get('owner_payout', 0)) + '</b></div>'
    expenses = ''
    if p['groups']:
        expenses = '<div class="card"><h2>Expenses</h2>' + row('Total reported expenses', p['totalExpenses'])
        for group in p['groups']:
            shares = ''
            if group['key'] == 'after_split':
                shares = ''.join(row(label, p[key]) for key, label in [('ownerAfter', 'Owner contribution'), ('bmAfter', 'Britsmaid contribution')] if p[key] > 0)
            expenses += disclosure(group['label'], group['total'], shares + records(group['key']))
        expenses += '</div>'
    bm = row(f'Britsmaid allocated share ({s.get("britsmaid_share_percent", 0):g}%)', s.get('britsmaid_share', 0))
    if p['bmAfter'] > 0:
        bm += disclosure('Britsmaid expenses after split', p['bmAfter'], records('after_split'), True)
    bm += row('Britsmaid net earnings', s.get('britsmaid_net', 0))
    return p, calculation, expenses, '<div class="card"><details><summary>Britsmaid breakdown</summary>' + bm + '</details></div>'
