// Preserve saved report amounts while presenting legacy expenses alongside new entries.
export function statementExpenses(s: any): any[] {
  const items = (s.deduction_items || []).map((e: any) => ({ ...e,
    treatment: e.treatment || (e.type === 'pre_split' ? 'before_split' : e.type === 'electricity' && !e.allocation && !e.owner_amount && !e.britsmaid_amount && s.electricity_mode === 'owner' ? 'reference' : 'after_split') }));
  if (s.electricity_total && !items.some((e: any) => e.type === 'electricity')) items.push({ id: 'legacy-electricity', summary: true, title: 'Electricity', amount: s.electricity_total,
    treatment: s.owner_electricity || s.britsmaid_electricity ? 'after_split' : 'reference', owner_amount: s.owner_electricity, britsmaid_amount: s.britsmaid_electricity, notes: 'Summary retained from this saved report.' });
  return items;
}
