import React, { useEffect, useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { DateField } from "@/src/components/DateField";
import { Badge, Button, Card, Chip, ChipRow, ConfirmSheet, Header, IconButton, Input, Loading, Txt, useToast } from "@/src/ui";
import { OTAS, addDays, inr, nightsBetween, otaColor, todayISO } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function BookingForm() {
  const params = useLocalSearchParams<{ id?: string; property_id?: string; date?: string }>();
  const id = params.id;
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });
  const start = params.date || todayISO();
  const [f, setF] = useState({ property_id: params.property_id || "", guest_name: "", guest_phone: "", guest_email: "", guests: "2", ota: "Direct", check_in: start, check_out: addDays(start, 1), amount: "", ota_commission: "", status: "confirmed", notes: "", source: "manual" });
  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [del, setDel] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.get(`/bookings/${id}`).then((b) => {
      setF({ ...b, guests: String(b.guests), amount: String(b.amount || ""), ota_commission: String(b.ota_commission || "") });
      setLoading(false);
    });
  }, [id]);
  useEffect(() => {
    if (!f.property_id && props.data?.length) setF((x) => ({ ...x, property_id: props.data![0].id }));
  }, [props.data, f.property_id]);

  const set = (k: string) => (v: any) => setF((x) => ({ ...x, [k]: v }));
  const prop = props.data?.find((p) => p.id === f.property_id);
  const nights = nightsBetween(f.check_in, f.check_out);

  const save = async () => {
    if (!f.property_id || !f.guest_name.trim()) return toast("Choose a villa and enter guest name", "error");
    if (nights < 1) return toast("Check-out must be after check-in", "error");
    setSaving(true);
    const body = { ...f, guests: Number(f.guests) || 1, amount: Number(f.amount) || 0, ota_commission: Number(f.ota_commission) || 0 };
    try {
      if (id) await api.put(`/bookings/${id}`, body);
      else await api.post("/bookings", body);
      qc.invalidateQueries();
      toast(id ? "Booking updated" : "Booking confirmed · cleaning scheduled");
      router.back();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading || props.isLoading) return <Loading />;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={id ? "Booking" : "New booking"} subtitle={f.source === "ical" ? `Imported from ${f.ota} iCal` : undefined}
        right={id ? <View style={{ flexDirection: "row", gap: 8 }}>
          <IconButton testID="booking-invoice-button" name="document-text-outline" tone="brand" onPress={() => router.push(`/invoice/new?booking_id=${id}`)} />
          <IconButton testID="booking-delete-button" name="trash-outline" onPress={() => setDel(true)} />
        </View> : undefined} />
      <View style={{ backgroundColor: colors.surface }}>
        <ChipRow>
          {(props.data ?? []).map((p) => <Chip key={p.id} testID={`booking-property-${p.id}`} label={p.name} selected={f.property_id === p.id} onPress={() => set("property_id")(p.id)} />)}
        </ChipRow>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <Card style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <DateField testID="booking-checkin" label="Check-in" value={f.check_in} onChange={(d) => setF((x) => ({ ...x, check_in: d, check_out: x.check_out <= d ? addDays(d, 1) : x.check_out }))} />
            <DateField testID="booking-checkout" label="Check-out" value={f.check_out} min={addDays(f.check_in, 1)} onChange={set("check_out")} />
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Txt v="mono" testID="booking-nights">{nights} night{nights === 1 ? "" : "s"}</Txt>
            {prop?.base_rate ? <Button small variant="ghost" title={`Use rate ${inr(prop.base_rate * nights)}`} onPress={() => set("amount")(String(prop.base_rate * nights))} testID="booking-use-rate" /> : null}
          </View>
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">Source</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {OTAS.map((o) => <Chip key={o} testID={`booking-ota-${o}`} label={o} dot={otaColor(o)} selected={f.ota === o} onPress={() => set("ota")(o)} />)}
          </View>
          <Txt v="label">Status</Txt>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            {["confirmed", "blocked", "cancelled"].map((s) => <Chip key={s} testID={`booking-status-${s}`} label={s[0].toUpperCase() + s.slice(1)} selected={f.status === s} onPress={() => set("status")(s)} />)}
          </View>
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Input testID="booking-guest-input" label="Guest name" value={f.guest_name} onChangeText={set("guest_name")} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}><Input testID="booking-phone-input" label="Phone" keyboardType="phone-pad" value={f.guest_phone} onChangeText={set("guest_phone")} /></View>
            <View style={{ width: 90 }}><Input testID="booking-guests-input" label="Guests" keyboardType="numeric" value={f.guests} onChangeText={set("guests")} /></View>
          </View>
          <Input testID="booking-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.guest_email} onChangeText={set("guest_email")} />
        </Card>
        <Card style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}><Input testID="booking-amount-input" label="Booking amount ₹" keyboardType="numeric" value={f.amount} onChangeText={set("amount")} /></View>
            <View style={{ flex: 1 }}><Input testID="booking-commission-input" label="OTA commission ₹" keyboardType="numeric" value={f.ota_commission} onChangeText={set("ota_commission")} /></View>
          </View>
          {prop ? (
            <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
              <Badge tone="brand" label={`Owner ${inr(((Number(f.amount) || 0) - (Number(f.ota_commission) || 0)) * prop.owner_share_percent / 100)}`} />
              <Badge tone="info" label={`Britsmaid ${inr(((Number(f.amount) || 0) - (Number(f.ota_commission) || 0)) * (100 - prop.owner_share_percent) / 100)}`} />
            </View>
          ) : null}
          <Input testID="booking-notes-input" label="Notes" multiline value={f.notes} onChangeText={set("notes")} />
        </Card>
        <Button testID="booking-save-button" title={id ? "Save booking" : "Confirm booking"} onPress={save} loading={saving} />
      </KeyboardAwareScrollView>
      <ConfirmSheet visible={del} title="Delete booking?" message="This removes the booking and its pending cleaning task." onClose={() => setDel(false)} onConfirm={async () => { await api.del(`/bookings/${id}`); qc.invalidateQueries(); toast("Booking deleted"); setDel(false); router.back(); }} />
    </View>
  );
}
