// Exact decimal rational arithmetic, rounded half-up like the Python backend.
type Fraction = { n: bigint; d: bigint };
function fraction(value: number | string | null | undefined): Fraction {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return { n: 0n, d: 1n };
  const parts = String(number).toLowerCase().split('e');
  const negative = parts[0].startsWith('-');
  const mantissa = parts[0].replace(/^[+-]/, '');
  const [whole, decimals = ''] = mantissa.split('.');
  const scale = decimals.length - Number(parts[1] || 0);
  let n = BigInt(whole + decimals) * (negative ? -1n : 1n), d = 1n;
  if (scale > 0) d = 10n ** BigInt(scale); else n *= 10n ** BigInt(-scale);
  return { n, d };
}
function rounded(n: bigint, d: bigint, digits = 2) {
  if (d === 0n) return 0;
  if (d < 0n) { n = -n; d = -d; }
  const sign = n < 0n ? -1n : 1n;
  const scaled = (n < 0n ? -n : n) * 10n ** BigInt(digits);
  let q = scaled / d;
  if ((scaled % d) * 2n >= d) q++;
  return Number(sign * q) / 10 ** digits;
}
export function money(value: number | string) { const a = fraction(value); return rounded(a.n, a.d); }
export function percentAmount(base: number, percent: number) {
  const a = fraction(base), b = fraction(percent);
  return rounded(a.n * b.n, a.d * b.d * 100n);
}
export function amountPercent(amount: number, base: number): number | null {
  if (base <= 0) return null;
  const a = fraction(amount), b = fraction(base);
  return rounded(a.n * b.d * 100n, a.d * b.n, 6);
}
function includedTax(gross: number, percent: number) {
  const a = fraction(gross), b = fraction(percent);
  return rounded(a.n * b.n, a.d * (100n * b.d + b.n));
}
export function financialPayload(f: any) {
  const numeric = (value: any, label: string) => { const n = Number(value || 0); if (!Number.isFinite(n) || n < 0) throw new Error(`Enter a valid non-negative ${label}`); return n; };
  const result = { ...f, misc_amount: numeric(f.misc_amount, 'other booking expense') };
  for (const key of ['gst', 'platform_fee', 'platform_tax']) {
    const percent = f[key].percent == null || f[key].percent === '' ? null : numeric(f[key].percent, 'percentage');
    if (percent != null && percent > 100) throw new Error('Percentages must be between 0 and 100');
    result[key] = { ...f[key], percent, amount: numeric(f[key].amount, 'deduction amount') };
  }
  return result;
}
export const newFinancials = (commission = 0) => ({ version: 1, gst_included: true,
  gst: { percent: null, amount: 0, manual: false, base: 'excluding_gst', entry_mode: null },
  platform_fee: { percent: null, amount: commission, manual: commission > 0, base: 'excluding_gst', entry_mode: null },
  platform_tax: { percent: null, amount: 0, manual: false, base: 'excluding_gst', entry_mode: null },
  misc_amount: 0, misc_title: '', misc_notes: '' });
export function bookingMath(input: number, f: any) {
  const gross = money(input);
  const byAmount = (line: any) => line.entry_mode ? line.entry_mode === 'amount' : line.manual;
  const charge = (line: any, base: number) => byAmount(line) ? money(Number(line.amount) || 0) : percentAmount(base, Number(line.percent) || 0);
  const rate = Number(f.gst.percent) || 0;
  const gst = byAmount(f.gst) ? money(Number(f.gst.amount) || 0) : f.gst_included ? includedTax(gross, rate) : percentAmount(gross, rate);
  const total = f.gst_included ? gross : money(gross + gst);
  const subtotal = money(total - gst);
  const feeBase = f.platform_fee.base === 'gross' ? total : subtotal;
  const taxBase = f.platform_tax.base === 'gross' ? total : subtotal;
  const fee = charge(f.platform_fee, feeBase), tax = charge(f.platform_tax, taxBase);
  return { gross: total, gst, fee, tax, net: money(subtotal - fee - tax - money(Number(f.misc_amount) || 0)),
    rates: { gst: amountPercent(gst, subtotal), platform_fee: amountPercent(fee, feeBase), platform_tax: amountPercent(tax, taxBase) } };
}
export function allocationMath(totalInput: number, a: any) {
  const total = money(totalInput);
  const byAmount = a.entry_mode === 'amount' || (!a.entry_mode && a.manual);
  const side = a.amount_side || 'owner';
  const fixed = money(Number(a[`${side}_amount`]) || 0);
  const owner = byAmount ? side === 'owner' ? fixed : money(total - fixed) : percentAmount(total, Number(a.owner_percent) || 0);
  const bm = money(total - owner);
  const ownerPercent = byAmount ? amountPercent(owner, total) : Number(a.owner_percent) || 0;
  const bmPercent = ownerPercent == null ? null : rounded(fraction(100 - ownerPercent).n, fraction(100 - ownerPercent).d, 6);
  return { ...a, owner_amount: owner, britsmaid_amount: bm, owner_percent: ownerPercent, britsmaid_percent: bmPercent, manual: byAmount };
}
