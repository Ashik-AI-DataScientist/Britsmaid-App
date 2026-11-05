export const money = (v: number) => Math.round((v + Number.EPSILON) * 100) / 100;
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
  gst: { percent: null, amount: 0, manual: false, base: "excluding_gst" },
  platform_fee: { percent: null, amount: commission, manual: commission > 0, base: "excluding_gst" },
  platform_tax: { percent: null, amount: 0, manual: false, base: "excluding_gst" },
  misc_amount: 0, misc_title: "", misc_notes: "" });
export function bookingMath(gross: number, f: any) {
  const charge = (line: any, base: number) => line.manual ? Number(line.amount) || 0 : money(base * (Number(line.percent) || 0) / 100);
  const rate = Number(f.gst.percent) || 0;
  const gst = f.gst.manual ? Number(f.gst.amount) || 0 : money(gross * rate / (f.gst_included ? 100 + rate : 100));
  const total = f.gst_included ? gross : money(gross + gst);
  const subtotal = money(total - gst);
  const fee = charge(f.platform_fee, f.platform_fee.base === "gross" ? total : subtotal);
  const tax = charge(f.platform_tax, f.platform_tax.base === "gross" ? total : subtotal);
  return { gross: total, gst, fee, tax, net: money(subtotal - fee - tax - (Number(f.misc_amount) || 0)) };
}
