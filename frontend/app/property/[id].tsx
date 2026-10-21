import { PropertyCover } from "@/src/components/PropertyCover";
import React, { useState } from "react";
import { RefreshControl, ScrollView, View, Pressable } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { Badge, Button, Card, ConfirmSheet, ErrorState, HomeButton, Icon, IconButton, Input, Loading, Row, Segmented, Sheet, Txt, useToast } from "@/src/ui";
import { ContactsCard } from "@/src/components/Contacts";
import { fmtDate, fmtShort, inr, monthLabel, otaColor, thisMonth, todayISO } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export default function PropertyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const p = useQuery({ queryKey: ["property", id], queryFn: () => api.get(`/properties/${id}`) });
  const exp = useQuery({ queryKey: ["expenses", id], queryFn: () => api.get<any[]>(`/expenses?property_id=${id}`) });
  const bookings = useQuery({ queryKey: ["bookings", id], queryFn: () => api.get<any[]>(`/bookings?property_id=${id}`) });
  const [syncing, setSyncing] = useState(false);
  const [billOpen, setBillOpen] = useState(false);
  const [bill, setBill] = useState({ month: thisMonth(), amount: "", type: "electricity" as "electricity" | "other", notes: "" });
  const [del, setDel] = useState(false);

  if (p.isLoading) return <View style={{ flex: 1, backgroundColor: colors.surface }}><Loading /></View>;
  if (p.isError) return <View style={{ flex: 1, paddingTop: insets.top }}><ErrorState message={(p.error as Error).message} onRetry={p.refetch} /></View>;
  const v = p.data;
  const upcoming = (bookings.data ?? []).filter((b) => b.check_out >= todayISO() && b.status !== "cancelled").slice(0, 5);

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await api.post(`/properties/${id}/ical-sync`);
      const errs = r.results.filter((x: any) => !x.ok);
      const added = r.results.reduce((a: number, x: any) => a + (x.added ?? 0), 0);
      toast(errs.length ? `${errs[0].ota}: ${errs[0].error}` : `Synced · ${added} new booking${added === 1 ? "" : "s"}`, errs.length ? "error" : "success");
      qc.invalidateQueries();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSyncing(false);
    }
  };

  const saveBill = async () => {
    if (!/^\d{4}-\d{2}$/.test(bill.month) || !Number(bill.amount)) return toast("Enter month (YYYY-MM) and amount", "error");
    try {
      await api.post("/expenses", { property_id: id, month: bill.month, type: bill.type, amount: Number(bill.amount), notes: bill.notes });
      setBillOpen(false);
      setBill({ ...bill, amount: "", notes: "" });
      exp.refetch();
      toast("Bill recorded");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const remove = async () => {
    await api.del(`/properties/${id}`);
    qc.invalidateQueries({ queryKey: ["properties"] });
    toast("Property removed");
    router.back();
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={p.isRefetching} onRefresh={() => { p.refetch(); exp.refetch(); bookings.refetch(); }} tintColor={colors.brandPrimary} />}>
        <View style={{ height: 240, backgroundColor: colors.brandTertiary }}>
          <PropertyCover property={v} />
          <LinearGradient colors={["transparent", colors.scrim]} style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 140 }} />
          <View style={{ position: "absolute", top: insets.top + spacing.sm, left: spacing.lg, right: spacing.lg, flexDirection: "row", justifyContent: "space-between" }}>
            <IconButton testID="property-back-button" name="chevron-back" tone="inverse" onPress={() => router.back()} />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <HomeButton tone="inverse" />
              <IconButton testID="property-edit-button" name="create-outline" tone="inverse" onPress={() => router.push(`/property/edit?id=${id}`)} />
              <IconButton testID="property-delete-button" name="trash-outline" tone="inverse" onPress={() => setDel(true)} />
            </View>
          </View>
          <View style={{ position: "absolute", left: spacing.lg, bottom: spacing.lg, right: spacing.lg }}>
            <Txt v="display" color={colors.onSurfaceInverse} testID="property-name">{v.name}</Txt>
            <Txt v="body" color={colors.onSurfaceInverse}>{v.location}</Txt>
            <View style={{ flexDirection: "row", gap: 6, marginTop: spacing.sm }}>
              <Badge label={v.occupied ? `Occupied · ${v.current_guest}` : "Vacant"} tone={v.occupied ? "info" : "neutral"} />
              <Badge label={v.needs_cleaning ? "Needs cleaning" : "Guest-ready"} tone={v.needs_cleaning ? "warning" : "success"} />
            </View>
          </View>
        </View>

        <View style={{ padding: spacing.lg, gap: spacing.md }}>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button testID="property-new-booking" small icon="add" title="Booking" onPress={() => router.push(`/booking/new?property_id=${id}`)} style={{ flex: 1 }} />
            <Button testID="property-statement" small variant="secondary" icon="pie-chart-outline" title="Statement" onPress={() => router.push(`/report/settlement?property_id=${id}`)} style={{ flex: 1 }} />
            <Button testID="property-report" small variant="secondary" icon="camera-outline" title="Report" onPress={() => router.push(`/report/new?property_id=${id}`)} style={{ flex: 1 }} />
          </View>
          {v.needs_cleaning && v.pending_cleaning_id ? (
            <Card testID="property-pending-cleaning" onPress={() => router.push(`/cleaning/${v.pending_cleaning_id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.warningSoft, borderColor: colors.warningSoft }}>
              <Icon name="sparkles" size={20} color={colors.warning} />
              <Txt v="body" style={{ flex: 1 }}>Checkout cleaning pending — view before/after</Txt>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Card>
          ) : null}

          <ContactsCard p={v} />

          <Card>
            <Txt v="label" style={{ marginBottom: spacing.xs }}>Revenue share</Txt>
            <Row label="Owner share" value={`${v.owner_share_percent}%`} />
            <Row label="Britsmaid share" value={`${100 - v.owner_share_percent}%`} />
            <Row label="Electricity" value={v.electricity_mode === "split_half" ? "Britsmaid pays 50%" : "Owner managed"} />
            <Row label="Base nightly rate" value={inr(v.base_rate)} />
          </Card>

          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
              <Txt v="label" style={{ flex: 1 }}>OTA iCal sync</Txt>
              <Button testID="property-ical-sync" small variant="secondary" icon="sync" title="Sync now" loading={syncing} onPress={sync} />
            </View>
            {(v.ical_feeds ?? []).length === 0 ? (
              <Pressable testID="property-add-ical" onPress={() => router.push(`/property/edit?id=${id}`)}>
                <Txt v="body" color={colors.brandPrimary}>Add Airbnb / Booking.com / Agoda iCal links →</Txt>
              </Pressable>
            ) : v.ical_feeds.map((f: any, i: number) => (
              <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 }}>
                <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: otaColor(f.ota) }} />
                <Txt v="body" style={{ flex: 1 }}>{f.ota}</Txt>
                <Txt v="caption">{f.last_synced ? `Synced ${fmtShort(f.last_synced.slice(0, 10))}` : "Never synced"}</Txt>
              </View>
            ))}
          </Card>

          <Card>
            <Txt v="label" style={{ marginBottom: spacing.sm }}>Upcoming stays</Txt>
            {upcoming.length === 0 ? <Txt v="caption">No upcoming bookings</Txt> : upcoming.map((b) => (
              <Pressable key={b.id} testID={`property-booking-${b.id}`} onPress={() => router.push(`/booking/new?id=${b.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm }}>
                <View style={{ width: 4, height: 32, borderRadius: 2, backgroundColor: otaColor(b.ota) }} />
                <View style={{ flex: 1 }}>
                  <Txt v="body" style={{ color: colors.onSurface }}>{b.guest_name}</Txt>
                  <Txt v="caption">{b.ota} · {fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
                </View>
                {b.amount ? <Txt v="mono" style={{ fontSize: 13 }}>{inr(b.amount)}</Txt> : null}
              </Pressable>
            ))}
          </Card>

          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
              <Txt v="label" style={{ flex: 1 }}>Bills & deductions</Txt>
              <Button testID="property-add-bill" small variant="secondary" icon="flash-outline" title="Add bill" onPress={() => setBillOpen(true)} />
            </View>
            {(exp.data ?? []).length === 0 ? <Txt v="caption">No bills recorded</Txt> : exp.data!.map((e) => (
              <View key={e.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 }}>
                <Icon name={e.type === "electricity" ? "flash" : "construct-outline"} size={16} color={colors.warning} />
                <Txt v="body" style={{ flex: 1 }}>{monthLabel(e.month)} · {e.type === "electricity" ? "Electricity" : e.notes || "Other"}</Txt>
                <Txt v="mono" style={{ fontSize: 14 }}>{inr(e.amount)}</Txt>
                <Pressable testID={`delete-bill-${e.id}`} hitSlop={8} onPress={async () => { await api.del(`/expenses/${e.id}`); exp.refetch(); }}>
                  <Icon name="close-circle" size={18} color={colors.muted} />
                </Pressable>
              </View>
            ))}
            <Txt v="caption" style={{ marginTop: spacing.sm }}>{v.electricity_mode === "split_half" ? "Electricity is split 50/50 between owner & Britsmaid in statements." : "Electricity is paid by the owner directly (shown for reference)."}</Txt>
          </Card>

          <Card>
            <Txt v="label" style={{ marginBottom: spacing.sm }}>Rooms & common areas ({v.rooms.length})</Txt>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {v.rooms.map((r: string) => (
                <View key={r} style={{ backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 6 }}>
                  <Txt v="caption" color={colors.onBrandTertiary}>{r}</Txt>
                </View>
              ))}
            </View>
          </Card>
          <Button testID="property-cleaning-history" variant="ghost" icon="sparkles-outline" title="Cleaning history" onPress={() => router.push(`/cleaning?property_id=${id}`)} />
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button testID="property-edit-bottom" style={{ flex: 1 }} variant="secondary" icon="create-outline" title="Edit property" onPress={() => router.push(`/property/edit?id=${id}`)} />
            <Button testID="property-delete-bottom" style={{ flex: 1 }} variant="danger" icon="trash-outline" title="Delete" onPress={() => setDel(true)} />
          </View>
          <Txt v="caption" style={{ textAlign: "center" }}>Added {fmtDate(v.created_at)}</Txt>
        </View>
      </ScrollView>

      <Sheet visible={billOpen} onClose={() => setBillOpen(false)} title="Record a bill" testID="bill-sheet">
        <View style={{ gap: spacing.md }}>
          <Segmented testID="bill-type" value={bill.type} onChange={(t) => setBill({ ...bill, type: t })} options={[{ value: "electricity", label: "Electricity" }, { value: "other", label: "Other deduction" }]} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}><Input testID="bill-month-input" label="Month (YYYY-MM)" value={bill.month} onChangeText={(t) => setBill({ ...bill, month: t })} /></View>
            <View style={{ flex: 1 }}><Input testID="bill-amount-input" label="Amount ₹" keyboardType="numeric" value={bill.amount} onChangeText={(t) => setBill({ ...bill, amount: t })} /></View>
          </View>
          <Input testID="bill-notes-input" label="Notes" value={bill.notes} onChangeText={(t) => setBill({ ...bill, notes: t })} />
          <Button testID="bill-save-button" title="Save bill" onPress={saveBill} />
        </View>
      </Sheet>
      <ConfirmSheet visible={del} title="Remove property?" message={`${v.name} will be hidden from all lists. Bookings and reports are kept.`} onConfirm={remove} onClose={() => setDel(false)} />
    </View>
  );
}
