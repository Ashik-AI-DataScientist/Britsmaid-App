import React from "react";
import { View } from "react-native";
import { Button, Chip, Input, Row, Txt } from "@/src/ui";
import { bookingMath, money, newFinancials } from "@/src/booking-finance";
import { inr } from "@/src/format";
import { spacing } from "@/src/theme";

export function BookingAmounts({ gross, value, onChange, ownerPercent = 70, readOnly = false, commission = 0 }: {
  gross: number; value: any; onChange?: (v: any) => void; ownerPercent?: number; readOnly?: boolean; commission?: number;
}) {
  if (!value) return <View style={{ gap: spacing.sm }}><Txt>Saved with the original amount / commission calculation.</Txt>
    {!readOnly ? <Button title="Add detailed amounts (optional)" onPress={() => onChange?.(newFinancials(commission))} /> : null}</View>;
  const f = value;
  const t = bookingMath(gross, f);
  const owner = money(t.net * ownerPercent / 100);
  return <View style={{ gap: spacing.md }}>
    <Txt v="subtitle">Booking amount breakdown</Txt>
    <Txt v="caption">Optional. Add these amounts now or return later. Adjusted amounts are kept when the gross payment changes.</Txt>
    {!readOnly ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      <Chip label="Payment includes GST" selected={f.gst_included} onPress={() => onChange?.({ ...f, gst_included: true })} />
      <Chip label="Amount excludes GST" selected={!f.gst_included} onPress={() => onChange?.({ ...f, gst_included: false })} />
    </View> : <Txt v="caption">{f.gst_included ? "GST included in guest payment" : "Entered amount excludes GST"}</Txt>}
    {([['gst', 'GST', t.gst], ['platform_fee', 'Platform fee', t.fee], ['platform_tax', 'Platform tax deduction', t.tax]] as const).map(([key, label, amount]) => <View key={key} style={{ gap: 6 }}>
      {!readOnly ? <Txt v="label">{label}</Txt> : null}
      {readOnly ? <Row label={`${label}${f[key].percent != null ? ` (${f[key].percent}%)` : ''}${f[key].manual ? ' · adjusted' : ''}`} value={inr(amount)} /> : <View style={{ flexDirection: "row", gap: 12 }}>
        <View style={{ flex: 1 }}><Input testID={`financial-${key}-percent`} label="Percentage %" keyboardType="decimal-pad" value={f[key].percent == null ? "" : String(f[key].percent)} onChangeText={v => onChange?.({ ...f, [key]: { ...f[key], percent: v === "" ? null : v, manual: false } })} /></View>
        <View style={{ flex: 1 }}><Input testID={`financial-${key}-amount`} label="Amount ₹" keyboardType="decimal-pad" value={f[key].manual ? String(f[key].amount) : String(amount)} onChangeText={v => onChange?.({ ...f, [key]: { ...f[key], amount: v, manual: true } })} /></View>
      </View>}
      <Txt v="caption">{f[key].manual ? "Adjusted manually. Check this amount if the booking changes." : "Calculated automatically"}</Txt>
      {key !== 'gst' ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {readOnly ? <Txt v="caption">Percentage base: {f[key].base === 'gross' ? 'guest total' : 'amount excluding GST'}</Txt> : <>
          <Chip label="% of amount excluding GST" selected={f[key].base !== 'gross'} onPress={() => onChange?.({ ...f, [key]: { ...f[key], base: 'excluding_gst' } })} />
          <Chip label="% of guest total" selected={f[key].base === 'gross'} onPress={() => onChange?.({ ...f, [key]: { ...f[key], base: 'gross' } })} />
        </>}
      </View> : null}
    </View>)}
    {readOnly ? <><Row label={f.misc_title || "Other booking expense"} value={inr(f.misc_amount)} />{f.misc_notes ? <Txt>{f.misc_notes}</Txt> : null}</> : <>
      <Input label="Other booking expense ₹" keyboardType="decimal-pad" value={String(f.misc_amount || '')} onChangeText={v => onChange?.({ ...f, misc_amount: v })} />
      <Input label="Expense title / description" value={f.misc_title} onChangeText={v => onChange?.({ ...f, misc_title: v })} />
      <Input label="Expense note" value={f.misc_notes} onChangeText={v => onChange?.({ ...f, misc_notes: v })} />
    </>}
    <Row label="Gross guest payment" value={inr(t.gross)} />
    <Row strong label="Net booking revenue" value={inr(t.net)} />
    <Row label={`Owner allocation (${ownerPercent}%)`} value={inr(owner)} />
    <Row label={`Britsmaid allocation (${100 - ownerPercent}%)`} value={inr(money(t.net - owner))} />
    <Txt v="caption">Monthly expenses are deducted from the allocated shares once. Owner TDS is 2% of the remaining positive owner balance; the final payout and total TDS appear in the monthly statement.</Txt>
  </View>;
}
