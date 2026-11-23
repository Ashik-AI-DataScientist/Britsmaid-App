"""Owner-facing views of additional revenue; stored ledgers stay unchanged."""
from copy import deepcopy
from additional_revenue import revenue_totals
from booking_finance import money, percent_amount


def owner_allocation(item):
    if item.get('owner_amount') is not None:
        return money(item['owner_amount'])
    net = money(item['amount'] - item.get('tax', 0) - item.get('fee', 0))
    return percent_amount(net, item.get('owner_percent', 0))


def owner_items(items):
    return [item for item in items if owner_allocation(item) > 0]


def owner_booking(booking):
    result = deepcopy(booking)
    result.pop('admin_history', None)
    result.pop('revenue_history', None)
    if 'additional_revenue' in result:
        result['additional_revenue'] = owner_items(result['additional_revenue'])
    return result


def owner_statement(statement):
    result = deepcopy(statement)
    items = result.get('additional_revenue', [])
    visible = owner_items(items)
    hidden = revenue_totals([item for item in items if owner_allocation(item) <= 0])
    if 'additional_revenue' in result:
        result['additional_revenue'] = visible
        result['additional_totals'] = revenue_totals(visible)
    for field, deduction in [('gross', hidden['gross']), ('net_revenue', hidden['net']),
            ('britsmaid_share', hidden['britsmaid']), ('britsmaid_net', hidden['britsmaid'])]:
        if field in result and deduction:
            result[field] = money(result[field] - deduction)
    if hidden['gross'] and 'by_ota' in result:
        totals = revenue_totals(visible)
        rows = [row for row in result['by_ota'] if row.get('ota') != 'Additional revenue']
        if totals['gross']:
            rows.append(dict(ota='Additional revenue', bookings=0, nights=0, gross=totals['gross'],
                commission=0, deductions=totals['deductions'], net=totals['net']))
        result['by_ota'] = rows
    if 'bookings' in result:
        result['bookings'] = [owner_booking(booking) for booking in result['bookings']]
    if isinstance(result.get('payout'), dict):
        result['payout'] = owner_statement(result['payout'])
    return result


def owner_report(report):
    result = deepcopy(report)
    if isinstance(result.get('settlement'), dict):
        result['settlement'] = owner_statement(result['settlement'])
    return result
