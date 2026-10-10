import React, { useState } from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { SettlementView } from "@/src/components/SettlementView";
import { settlementHtml, sharePdf } from "@/src/pdf";
import { Badge, Button, Card, Empty, ErrorState, Header, Icon, IconButton, Loading, Segmented, Txt, useToast } from "@/src/ui";
import { fmtDate, fmtShort, monthLabel, otaColor, shiftMonth, thisMonth, todayISO } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Tab = "earnings" | "stays" | "updates";

export default function OwnerVilla() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { colors } = useTheme();
  const [tab, setTab] = useState<Tab>("earnings");
  const [month, setMonth] = useState(thisMonth());
  const [busy, setBusy] = useState(false);
  const prop = useQuery({ queryKey: ["property", id], queryFn: () => api.get(`/properties/${id}`) });
  const s = useQuery({ queryKey: ["settlement", id, month], queryFn: () => api.get(`/reports/settlement?property_id=${id}&month=${month}`), enabled: tab === "earnings" });
  const bookings = useQuery({ queryKey: ["bookings", id], queryFn: () => api.get<any[]>(`/bookings?property_id=${id}`), enabled: tab === "stays" });
  const reports = useQuery({ queryKey: ["owner-reports", id], queryFn: () => api.get<any[]>(`/owner-reports?property_id=${id}`), enabled: tab === "updates" });
  const cleans = useQuery({ queryKey: ["cleaning", "completed", id], queryFn: () => api.get<any[]>(`/cleaning?status=completed&property_id=${id}`), enabled: tab === "updates" });

  if (prop.isError) return <View style={{ flex: 1 }}><Header back title="Villa" /><ErrorState message="Villa not available" onRetry={prop.refetch} /></View>;
  const upcoming = (bookings.data ?? []).filter((b) => b.check_out >= todayISO() && b.status !== "cancelled");
  const past = (bookings.data ?? []).filter((b) => b.check_out < todayISO() && b.status === "confirmed").reverse().slice(0, 10);

  const share = async () => {
    setBusy(true);
    try { await sharePdf(settlementHtml(s.data)); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };

  const stay = (b: any) => (
    <Card key={b.id} testID={`owner-stay-${b.id}`} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
      <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: b.status === "blocked" ? colors.muted : otaColor(b.ota) }} />
      <View style={{ flex: 1 }}>
        <Txt v="subtitle" style={{ fontSize: 15 }}>{fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
        <Txt v="caption">{b.status === "blocked" ? "Blocked" : `${b.guest_name} · ${b.ota}`}</Txt>
      </View>
      <Badge label={b.check_in <= todayISO() && b.check_out > todayISO() ? "Staying now" : b.check_out < todayISO() ? "Completed" : "Upcoming"} tone={b.check_out < todayISO() ? "neutral" : "brand"} />
    </Card>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={prop.data?.name ?? "Villa"} subtitle={prop.data?.location} />
      <View style={{ padding: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, gap: spacing.sm }}>
        <Segmented testID="owner-villa-tabs" value={tab} onChange={setTab} options={[{ value: "earnings", label: "Earnings" }, { value: "stays", label: "Stays" }, { value: "updates", label: "Updates" }]} />
        {tab === "earnings" ? (
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <IconButton testID="owner-prev-month" name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
            <Txt v="subtitle" testID="owner-month">{monthLabel(month)}</Txt>
            <IconButton testID="owner-next-month" name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
          </View>
        ) : null}
      </View>
      {tab === "earnings" ? (
        s.isLoading ? <Loading label="Generating report..." /> : s.isError ? <ErrorState message="Failed to fetch report" onRetry={s.refetch} /> : (
          <>
            <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 96 }} refreshControl={<RefreshControl refreshing={s.isRefetching} onRefresh={s.refetch} tintColor={colors.brandPrimary} />}>
              <SettlementView s={s.data} onMonthPress={setMonth} />
            </ScrollView>
            <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16 }}>
              <Button testID="owner-share-pdf" icon="share-outline" title="Download statement PDF" onPress={share} loading={busy} />
            </View>
          </>
        )
      ) : tab === "stays" ? (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={bookings.isRefetching} onRefresh={bookings.refetch} tintColor={colors.brandPrimary} />}>
          {bookings.isLoading ? <Loading /> : null}
          <Txt v="label">Current & upcoming ({upcoming.length})</Txt>
          {upcoming.length === 0 && !bookings.isLoading ? <Card><Txt v="caption">No upcoming stays</Txt></Card> : upcoming.map(stay)}
          <Txt v="label" style={{ marginTop: spacing.md }}>Recent stays</Txt>
          {past.length === 0 && !bookings.isLoading ? <Card><Txt v="caption">No past stays yet</Txt></Card> : past.map(stay)}
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={reports.isRefetching} onRefresh={() => { reports.refetch(); cleans.refetch(); }} tintColor={colors.brandPrimary} />}>
          <Txt v="label">Reports from Britsmaid</Txt>
          {reports.isLoading ? <Loading /> : (reports.data ?? []).length === 0 ? <Empty icon="images-outline" title="No reports yet" subtitle="Status updates with photos & videos will appear here." /> : null}
          {(reports.data ?? []).map((r) => (
            <Card key={r.id} testID={`owner-report-${r.id}`} onPress={() => router.push(`/report/${r.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Icon name="document-text-outline" size={22} color={colors.brandPrimary} />
              <View style={{ flex: 1 }}>
                <Txt v="subtitle" style={{ fontSize: 15 }} numberOfLines={1}>{r.title}</Txt>
                <Txt v="caption">{r.media_ids.length} photos/videos · {fmtDate(r.created_at)}</Txt>
              </View>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Card>
          ))}
          <Txt v="label" style={{ marginTop: spacing.md }}>Cleaning records</Txt>
          {(cleans.data ?? []).length === 0 && !cleans.isLoading ? <Card><Txt v="caption">No completed cleanings yet</Txt></Card> : null}
          {(cleans.data ?? []).slice(0, 10).map((c) => (
            <Card key={c.id} testID={`owner-cleaning-${c.id}`} onPress={() => router.push(`/cleaning/${c.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Icon name="checkmark-done" size={20} color={colors.success} />
              <View style={{ flex: 1 }}>
                <Txt v="subtitle" style={{ fontSize: 15 }}>After checkout {fmtDate(c.date)}</Txt>
                <Txt v="caption">{c.rooms_total} rooms · before & after photos</Txt>
              </View>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Card>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
