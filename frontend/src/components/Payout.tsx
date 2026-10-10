import React, { useState } from "react";
import { View } from "react-native";
import { api } from "@/src/api";
import { DateField } from "@/src/components/DateField";
import { payoutReceiptHtml, sharePdf } from "@/src/pdf";
import { Badge, Button, Card, Chip, Icon, Input, Sheet, Txt, useToast } from "@/src/ui";
import { fmtDate, inr, monthLabel, todayISO } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export async function downloadReceipt(p: any) {
  await sharePdf(payoutReceiptHtml(p));
}

/** Shows payout status for a statement month; admins can record the payment. */
export function PayoutStatusCard({ s, canMark, onChange }: { s: any; canMark?: boolean; onChange?: () => void }) {
  const { colors } = useTheme();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ amount: String(Math.max(0, Math.round(s.owner_payout))), paid_on: todayISO(), method: "Bank transfer", reference: "", notes: "" });
  const p = s.payout;

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/payouts", { property_id: s.property_id, month: s.month, amount: Number(f.amount) || 0, paid_on: f.paid_on, method: f.method, reference: f.reference, notes: f.notes });
      setOpen(false);
      toast("Payout recorded · receipt ready");
      onChange?.();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card testID="payout-status-card" style={{ gap: spacing.sm, borderColor: p ? colors.successSoft : colors.warningSoft }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Icon name={p ? "checkmark-circle" : "time-outline"} size={22} color={p ? colors.success : colors.warning} />
        <Txt v="subtitle" style={{ flex: 1 }}>{p ? "Payout paid" : "Payout pending"}</Txt>
        <Badge testID="payout-status-badge" label={p ? "PAID" : "PENDING"} tone={p ? "success" : "warning"} />
      </View>
      {p ? (
        <>
          <Txt v="body">{inr(p.amount)} paid on {fmtDate(p.paid_on)} via {p.method}{p.reference ? ` · Ref ${p.reference}` : ""}</Txt>
          <Txt v="caption">Receipt {p.receipt_number}</Txt>
          <Button testID="payout-receipt-button" small variant="secondary" icon="download-outline" title="Download receipt" onPress={() => downloadReceipt(p).catch((e) => toast(e.message, "error"))} />
        </>
      ) : (
        <>
          <Txt v="caption">{monthLabel(s.month)} payout of {inr(s.owner_payout)} has not been marked as paid yet.</Txt>
          {canMark ? <Button testID="payout-mark-paid-button" small icon="cash-outline" title="Mark as paid" onPress={() => setOpen(true)} /> : null}
        </>
      )}
      <Sheet visible={open} onClose={() => setOpen(false)} title={`Record payout · ${monthLabel(s.month)}`} testID="payout-sheet">
        <View style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}><Input testID="payout-amount-input" label="Amount ₹" keyboardType="numeric" value={f.amount} onChangeText={(t) => setF({ ...f, amount: t })} /></View>
            <DateField testID="payout-date" label="Paid on" value={f.paid_on} onChange={(d) => setF({ ...f, paid_on: d })} />
          </View>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {["Bank transfer", "UPI", "Cash", "Cheque"].map((m) => <Chip key={m} testID={`payout-method-${m}`} label={m} selected={f.method === m} onPress={() => setF({ ...f, method: m })} />)}
          </View>
          <Input testID="payout-reference-input" label="Reference / UTR" value={f.reference} onChangeText={(t) => setF({ ...f, reference: t })} />
          <Input testID="payout-notes-input" label="Notes" value={f.notes} onChangeText={(t) => setF({ ...f, notes: t })} />
          <Button testID="payout-save-button" title="Confirm payout" icon="checkmark-done" onPress={save} loading={busy} />
        </View>
      </Sheet>
    </Card>
  );
}
