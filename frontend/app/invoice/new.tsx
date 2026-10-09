import React, { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { DateField } from "@/src/components/DateField";
import { Button, Card, Chip, ChipRow, Header, Icon, Input, Row, Segmented, Txt, useToast } from "@/src/ui";
import { addDays, inr, nightsBetween, todayISO } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Item = { description: string; qty: string; rate: string };

export default function NewInvoice() {
  const { booking_id } = useLocalSearchParams<{ booking_id?: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });
  const [type, setType] = useState<"guest" | "client">("guest");
  const [pid, setPid] = useState<string | null>(null);
  const [bill, setBill] = useState({ name: "", email: "", phone: "", address: "" });
  const [items, setItems] = useState<Item[]>([{ description: "", qty: "1", rate: "" }]);
  const [tax, setTax] = useState("0");
  const [discount, setDiscount] = useState("");
  const [issue, setIssue] = useState(todayISO());
  const [due, setDue] = useState(addDays(todayISO(), 7));
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!booking_id || !props.data) return;
    api.get(`/bookings/${booking_id}`).then((b) => {
      const n = nightsBetween(b.check_in, b.check_out);
      const p = props.data!.find((x) => x.id === b.property_id);
      setType("guest");
      setPid(b.property_id);
      setBill({ name: b.guest_name, email: b.guest_email, phone: b.guest_phone, address: "" });
      setItems([{ description: `Stay at ${p?.name ?? "villa"} (${b.check_in} → ${b.check_out})`, qty: String(n), rate: String(n ? Math.round((b.amount || (p?.base_rate ?? 0) * n) / n) : 0) }]);
    });
  }, [booking_id, props.data]);

  const pickProperty = (p: any) => {
    setPid(p.id);
    if (type === "client") setBill({ name: p.owner_name, email: p.owner_email, phone: p.owner_phone, address: p.location });
    else if (!items[0].description) setItems([{ description: `Stay at ${p.name}`, qty: "1", rate: String(p.base_rate || "") }]);
  };

  const sub = items.reduce((a, i) => a + (Number(i.qty) || 0) * (Number(i.rate) || 0), 0);
  const taxable = Math.max(sub - (Number(discount) || 0), 0);
  const total = taxable + (taxable * (Number(tax) || 0)) / 100;

  const save = async () => {
    const clean = items.filter((i) => i.description.trim()).map((i) => ({ description: i.description, qty: Number(i.qty) || 1, rate: Number(i.rate) || 0 }));
    if (!bill.name.trim()) return toast("Enter who the invoice is billed to", "error");
    if (!clean.length) return toast("Add at least one line item", "error");
    setSaving(true);
    try {
      const inv = await api.post("/invoices", { type, property_id: pid, booking_id: booking_id ?? null, bill_to_name: bill.name, bill_to_email: bill.email, bill_to_phone: bill.phone, bill_to_address: bill.address, items: clean, tax_percent: Number(tax) || 0, discount: Number(discount) || 0, issue_date: issue, due_date: due, notes });
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast(`Invoice ${inv.number} created`);
      router.replace(`/invoice/${inv.id}`);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const presets = type === "guest" ? ["Extra bed", "Airport transfer", "Breakfast", "Late checkout"] : ["Deep cleaning", "Maintenance visit", "Linen replacement", "Photography", "Management fee"];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="New invoice" />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <View style={{ paddingHorizontal: spacing.lg }}>
          <Segmented testID="invoice-type" value={type} onChange={setType} options={[{ value: "guest", label: "Guest stay" }, { value: "client", label: "Client service" }]} />
        </View>
        <Txt v="label" style={{ paddingHorizontal: spacing.lg }}>Property {type === "client" ? "(fills owner details)" : ""}</Txt>
        <ChipRow>
          {(props.data ?? []).map((p) => <Chip key={p.id} testID={`invoice-property-${p.id}`} label={p.name} selected={pid === p.id} onPress={() => pickProperty(p)} />)}
        </ChipRow>
        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          <Card style={{ gap: spacing.md }}>
            <Txt v="label">Bill to</Txt>
            <Input testID="invoice-billto-name" label={type === "guest" ? "Guest name" : "Client / owner name"} value={bill.name} onChangeText={(t) => setBill({ ...bill, name: t })} />
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}><Input testID="invoice-billto-phone" label="Phone" keyboardType="phone-pad" value={bill.phone} onChangeText={(t) => setBill({ ...bill, phone: t })} /></View>
              <View style={{ flex: 1 }}><Input testID="invoice-billto-email" label="Email" autoCapitalize="none" keyboardType="email-address" value={bill.email} onChangeText={(t) => setBill({ ...bill, email: t })} /></View>
            </View>
            <Input testID="invoice-billto-address" label="Address" value={bill.address} onChangeText={(t) => setBill({ ...bill, address: t })} />
          </Card>
          <Card style={{ gap: spacing.md }}>
            <Txt v="label">Line items</Txt>
            {items.map((it, i) => (
              <View key={i} style={{ gap: spacing.sm, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
                <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
                  <View style={{ flex: 1 }}><Input testID={`invoice-item-desc-${i}`} placeholder="Description" value={it.description} onChangeText={(t) => setItems(items.map((x, j) => (j === i ? { ...x, description: t } : x)))} /></View>
                  {items.length > 1 ? (
                    <Pressable testID={`invoice-item-remove-${i}`} onPress={() => setItems(items.filter((_, j) => j !== i))} style={{ height: 50, justifyContent: "center" }}>
                      <Icon name="trash-outline" size={20} color={colors.error} />
                    </Pressable>
                  ) : null}
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 80 }}><Input testID={`invoice-item-qty-${i}`} label="Qty" keyboardType="numeric" value={it.qty} onChangeText={(t) => setItems(items.map((x, j) => (j === i ? { ...x, qty: t } : x)))} /></View>
                  <View style={{ flex: 1 }}><Input testID={`invoice-item-rate-${i}`} label="Rate ₹" keyboardType="numeric" value={it.rate} onChangeText={(t) => setItems(items.map((x, j) => (j === i ? { ...x, rate: t } : x)))} /></View>
                </View>
              </View>
            ))}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {presets.map((p) => <Chip key={p} testID={`invoice-preset-${p}`} label={`+ ${p}`} onPress={() => setItems([...items.filter((x) => x.description || x.rate), { description: p, qty: "1", rate: "" }])} />)}
            </View>
            <Button testID="invoice-add-item" small variant="secondary" icon="add" title="Add line" onPress={() => setItems([...items, { description: "", qty: "1", rate: "" }])} />
          </Card>
          <Card style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}><Input testID="invoice-tax-input" label="GST %" keyboardType="numeric" value={tax} onChangeText={setTax} /></View>
              <View style={{ flex: 1 }}><Input testID="invoice-discount-input" label="Discount ₹" keyboardType="numeric" value={discount} onChangeText={setDiscount} /></View>
            </View>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <DateField testID="invoice-issue-date" label="Issue date" value={issue} onChange={setIssue} />
              <DateField testID="invoice-due-date" label="Due date" value={due} onChange={setDue} />
            </View>
            <Input testID="invoice-notes-input" label="Notes / payment details" multiline value={notes} onChangeText={setNotes} placeholder="UPI / bank details, terms..." />
          </Card>
          <Card>
            <Row label="Subtotal" value={inr(sub)} />
            {Number(discount) ? <Row label="Discount" value={`-${inr(Number(discount))}`} /> : null}
            {Number(tax) ? <Row label={`GST ${tax}%`} value={inr((taxable * Number(tax)) / 100)} /> : null}
            <Row strong label="Total" value={inr(total)} testID="invoice-total" />
          </Card>
          <Button testID="invoice-save-button" title="Generate invoice" icon="document-text" onPress={save} loading={saving} />
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}
