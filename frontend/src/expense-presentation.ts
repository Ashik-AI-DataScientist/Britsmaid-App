import { money } from './booking-finance';

const amount = (value: any) => Number.isFinite(Number(value)) ? money(Number(value)) : 0;
const sum = (items: any[]) => money(items.reduce((total, item) => total + amount(item.amount), 0));
const saved = (value: any, fallback: number) => value == null ? amount(fallback) : amount(value);

// Presentation only: never replace the saved statement's allocation, TDS or payout.
export function statementExpenses(s: any): any[] {
  const items = (Array.isArray(s.deduction_items) ? s.deduction_items : [])
    .filter((e: any) => e && e.amount != null && Number.isFinite(Number(e.amount)) && Number(e.amount) > 0)
    .map((e: any) => ({ ...e, amount: amount(e.amount),
      treatment: e.treatment || (e.type === 'pre_split' ? 'before_split' : e.type === 'electricity' && !e.allocation && !e.owner_amount && !e.britsmaid_amount && s.electricity_mode === 'owner' ? 'reference' : 'after_split') }));
  if (amount(s.electricity_total) > 0 && !items.some((e: any) => e.type === 'electricity')) items.push({ id: 'legacy-electricity', summary: true, title: 'Electricity', type: 'electricity', amount: amount(s.electricity_total),
    treatment: s.owner_electricity || s.britsmaid_electricity ? 'after_split' : 'reference', owner_amount: s.owner_electricity, britsmaid_amount: s.britsmaid_electricity, notes: 'Summary retained from this saved report.' });
  return items;
}

export function reportPresentation(s: any) {
  const items = statementExpenses(s);
  const ownerAfter = saved(s.owner_after_expenses, amount(s.owner_electricity) + amount(s.other_deductions));
  const bmAfter = saved(s.britsmaid_after_expenses, amount(s.britsmaid_electricity) + amount(s.britsmaid_other_expenses));
  const definitions = [
    { key: 'before_split', label: 'Before revenue split', total: saved(s.expense_before_total, s.pre_split_deductions == null && s.booking_misc == null ? sum(items.filter((e: any) => e.treatment === 'before_split')) : money(amount(s.pre_split_deductions) + amount(s.booking_misc))) },
    { key: 'after_split', label: 'After revenue split', total: saved(s.expense_after_total, Math.max(sum(items.filter((e: any) => e.treatment === 'after_split')), money(ownerAfter + bmAfter))) },
    { key: 'reference', label: 'Reference only · not deducted', total: saved(s.expense_reference_total, sum(items.filter((e: any) => e.treatment === 'reference'))) },
  ];
  const groups = definitions.map(g => {
    const entries = items.filter((e: any) => e.treatment === g.key);
    const difference = money(g.total - sum(entries));
    if (difference > 0) entries.push({ id: `saved-${g.key}`, summary: true, amount: difference, treatment: g.key,
      title: 'Additional expenses recorded in this saved statement', notes: 'The saved total is retained. Individual source details were not included in this older report.' });
    return { ...g, items: entries, mismatch: difference < 0 };
  }).filter(g => g.total > 0 || g.items.length > 0);
  const bookingDeductions = money(amount(s.ota_commission) + amount(s.gst_total) + amount(s.platform_tax));
  return { groups, ownerAfter, bmAfter, bookingDeductions, bookingTaxes: money(amount(s.gst_total) + amount(s.platform_tax)),
    before: definitions[0].total, after: definitions[1].total, reference: definitions[2].total,
    totalExpenses: money(definitions.reduce((total, g) => total + g.total, 0)) };
}
