import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { invoiceHtml, sharePdf } from "@/src/pdf";
import { Badge, Button, Card, ConfirmSheet, ErrorState, Header, IconButton, Loading, Row, Txt, useToast } from "@/src/ui";
import { fmtDate, inr } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function InvoiceView() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const q = useQuery({ queryKey: ["invoice", id], queryFn: () => api.get(`/invoices/${id}`) });
  const [sharing, setSharing] = useState(false);
  const [del, setDel] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Invoice" /><ErrorState message={(q.error as Error).message} onRetry={q.refetch} /></View>;
  const inv = q.data;

  const share = async () => {
    setSharing(true);
    try {
      await sharePdf(invoiceHtml(inv));
    } catch (e: any) {
      toast(e.message || "Could not create PDF", "error");
    } finally {
      setSharing(false);
    }
  };
  const toggle = async () => {
    await api.put(`/invoices/${id}/status`, { status: inv.status === "paid" ? "unpaid" : "paid" });
    q.refetch();
    qc.invalidateQueries({ queryKey: ["invoices"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    toast(inv.status === "paid" ? "Marked unpaid" : "Marked as paid");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={inv.number} subtitle={inv.type === "guest" ? "Guest stay invoice" : "Client service invoice"} right={<IconButton testID="invoice-delete-button" name="trash-outline" onPress={() => setDel(true)} />} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + 100 }}>
        <Card testID="invoice-preview" style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <View>
              <Txt v="display" style={{ color: colors.brandPrimary, fontSize: 26 }}>INVOICE</Txt>
              <Txt v="caption">{inv.number}</Txt>
            </View>
            <Image source={require("../../assets/images/logo.jpg")} style={{ width: 64, height: 64 }} contentFit="contain" />
          </View>
          <Badge testID="invoice-status-badge" label={inv.status === "paid" ? "PAID" : "UNPAID"} tone={inv.status === "paid" ? "success" : "warning"} />
          <View style={{ flexDirection: "row", gap: spacing.lg }}>
            <View style={{ flex: 1 }}>
              <Txt v="label">Bill to</Txt>
              <Txt v="subtitle" style={{ fontSize: 15 }}>{inv.bill_to_name}</Txt>
              {[inv.bill_to_address, inv.bill_to_phone, inv.bill_to_email].filter(Boolean).map((x: string) => <Txt key={x} v="caption">{x}</Txt>)}
            </View>
            <View>
              <Txt v="label">Issued</Txt>
              <Txt v="body">{fmtDate(inv.issue_date)}</Txt>
              {inv.due_date ? <><Txt v="label" style={{ marginTop: 6 }}>Due</Txt><Txt v="body">{fmtDate(inv.due_date)}</Txt></> : null}
            </View>
          </View>
          {inv.property_name ? <Txt v="caption">Property: {inv.property_name}</Txt> : null}
          <View>
            {inv.items.map((i: any, k: number) => (
              <Row key={k} label={`${i.description}  ×${i.qty}`} value={inr(i.qty * i.rate)} />
            ))}
            <Row label="Subtotal" value={inr(inv.subtotal)} />
            {inv.discount ? <Row label="Discount" value={`-${inr(inv.discount)}`} /> : null}
            {inv.tax_percent ? <Row label={`GST ${inv.tax_percent}%`} value={inr(inv.tax_amount)} /> : null}
            <Row strong label="Total" value={inr(inv.total)} testID="invoice-view-total" />
          </View>
          {inv.notes ? <Txt v="body">{inv.notes}</Txt> : null}
        </Card>
        <Button testID="invoice-toggle-paid" variant="secondary" icon={inv.status === "paid" ? "refresh" : "checkmark-done"} title={inv.status === "paid" ? "Mark as unpaid" : "Mark as paid"} onPress={toggle} />
      </ScrollView>
      <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16 }}>
        <Button testID="invoice-share-pdf" icon="share-outline" title="Share PDF" onPress={share} loading={sharing} />
      </View>
      <ConfirmSheet visible={del} title="Delete invoice?" message={`${inv.number} will be permanently deleted.`} onClose={() => setDel(false)} onConfirm={async () => { await api.del(`/invoices/${id}`); qc.invalidateQueries({ queryKey: ["invoices"] }); setDel(false); toast("Invoice deleted"); router.back(); }} />
    </View>
  );
}
