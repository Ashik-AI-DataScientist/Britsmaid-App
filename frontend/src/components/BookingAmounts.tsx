import React from "react";
import { View } from "react-native";
import { Button, Chip, Input, Row, Txt } from "@/src/ui";
import { bookingMath, money, newFinancials, percentAmount } from "@/src/booking-finance";
import { inr } from "@/src/format";
import { spacing } from "@/src/theme";

export function BookingAmounts({ gross, value, onChange, ownerPercent = 70, readOnly = false, commission = 0 }: {
  gross: number; value: any; onChange?: (v: any) => void; ownerPercent?: number; readOnly?: boolean; commission?: number;
}) {
  if (!value) return <View style={{ gap: spacing.sm }}><Txt>Saved with the original amount / commission calculation.</Txt>
    {!readOnly ? <Button title="Add detailed amounts (optional)" onPress={() => onChange?.(newFinancials(commission))} /> : null}</View>;
  const f = value;
  const t = bookingMath(gross, f);
  const owner = percentAmount(t.net, ownerPercent);
  return <View style={{ gap: spacing.md }}>
    <Txt v="subtitle">Booking amount breakdown</Txt>
    <Txt v="caption">{readOnly ? 'Saved booking breakdown. Monthly property expenses and TDS are shown separately below or in the monthly statement.' : 'Optional. Enter either a percentage or an amount: the other field calculates automatically. The last field you edit controls the calculation.'}</Txt>
    {!readOnly ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      <Chip label="Payment includes GST" selected={f.gst_included} onPress={() => onChange?.({ ...f, gst_included: true })} />
      <Chip label="Amount excludes GST" selected={!f.gst_included} onPress={() => onChange?.({ ...f, gst_included: false })} />
    </View> : <Txt v="caption">{f.gst_included ? "GST included in guest payment" : "Entered amount excludes GST"}</Txt>}
    {([['gst', 'GST', t.gst], ['platform_fee', 'Platform fee', t.fee], ['platform_tax', 'Platform tax deduction', t.tax]] as const).map(([key, label, amount]) => { const rate = f[key].entry_mode === 'amount' ? t.rates[key] : f[key].percent; return <View key={key} style={{ gap: 6 }}>
      {!readOnly ? <Txt v="label">{label}</Txt> : null}
      {readOnly ? <Row label={`${label}${rate != null ? ` (${rate}%)` : ''}${f[key].manual && !f[key].entry_mode ? ' · adjusted' : ''}`} value={inr(amount)} /> : <View style={{ flexDirection: "row", gap: spacing.md }}>
        <View style={{ flex: 1 }}><Input testID={`financial-${key}-percent`} label="Percentage %" keyboardType="decimal-pad" value={rate == null ? "" : String(rate)} onChangeText={v => onChange?.({ ...f, [key]: { ...f[key], percent: v === "" ? null : v, manual: false, entry_mode: 'percent' } })} /></View>
        <View style={{ flex: 1 }}><Input testID={`financial-${key}-amount`} label="Amount ₹" keyboardType="decimal-pad" value={f[key].manual || f[key].entry_mode === 'amount' ? String(f[key].amount) : String(amount)} onChangeText={v => onChange?.({ ...f, [key]: { ...f[key], amount: v, manual: true, entry_mode: 'amount' } })} /></View>
      </View>}
      <Txt v="caption">{f[key].entry_mode === 'amount' ? rate == null ? 'Enter a positive calculation base to calculate the percentage.' : 'Amount entered directly; percentage calculated from the stated base (up to 6 decimals). Amount stays fixed if the base changes.' : f[key].manual ? `Historical manual adjustment${t.rates[key] != null ? `; effective rate ${t.rates[key]}%` : ''}.` : 'Amount calculated from the entered percentage.'}</Txt>
      {key !== 'gst' ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {readOnly ? <Txt v="caption">Percentage base: {f[key].base === 'gross' ? 'guest total' : 'amount excluding GST'}</Txt> : <>
          <Chip label="% of amount excluding GST" selected={f[key].base !== 'gross'} onPress={() => onChange?.({ ...f, [key]: { ...f[key], base: 'excluding_gst' } })} />
          <Chip label="% of guest total" selected={f[key].base === 'gross'} onPress={() => onChange?.({ ...f, [key]: { ...f[key], base: 'gross' } })} />
        </>}
      </View> : null}
    </View>; })}
    {readOnly ? <><Row label={f.misc_title || "Other booking expense"} value={inr(f.misc_amount)} />{f.misc_notes ? <Txt>{f.misc_notes}</Txt> : null}</> : <>
      <Input label="Other booking expense ₹" keyboardType="decimal-pad" value={String(f.misc_amount || '')} onChangeText={v => onChange?.({ ...f, misc_amount: v })} />
      <Input label="Expense title / description" value={f.misc_title} onChangeText={v => onChange?.({ ...f, misc_title: v })} />
      <Input label="Expense note" value={f.misc_notes} onChangeText={v => onChange?.({ ...f, misc_notes: v })} />
    </>}
    <Row label="Gross guest payment" value={inr(t.gross)} />
    <Row strong label="Net booking revenue" value={inr(t.net)} />
    <Row label={`Owner allocation (${ownerPercent}%)`} value={inr(owner)} />
    <Row label={`Britsmaid allocation (${100 - ownerPercent}%)`} value={inr(money(t.net - owner))} />
    <Txt v="caption">Before-split expenses reduce the common revenue pool; after-split expenses reduce only the allocated shares. Each is deducted once. Owner TDS is 2% of the remaining positive owner balance; the final payout and total TDS appear in the monthly statement.</Txt>
  </View>;
}
