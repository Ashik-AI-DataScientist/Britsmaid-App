import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeIn, LinearTransition } from "react-native-reanimated";
import { api } from "@/src/api";
import { usesNativeTabs } from "@/src/navigation";
import { Badge, Card, Empty, ErrorState, Icon, IconButton, Loading, Segmented, Txt } from "@/src/ui";
import { fmtDate, inr, monthLabel, otaColor, shiftMonth, thisMonth } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

type Tab = "invoices" | "ota" | "owners";

function MonthStepper({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
      <IconButton testID="month-prev" name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
      <Txt v="subtitle" testID="month-label">{monthLabel(month)}</Txt>
      <IconButton testID="month-next" name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
    </View>
  );
}

function Invoices({ bottom }: { bottom: number }) {
  const router = useRouter();
  const { colors } = useTheme();
  const [type, setType] = useState<"all" | "guest" | "client">("all");
  const q = useQuery({ queryKey: ["invoices", type], queryFn: () => api.get<any[]>(`/invoices${type === "all" ? "" : `?type=${type}`}`) });
  return (
    <FlatList
      data={q.data ?? []}
      keyExtractor={(i) => i.id}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: bottom + 96 }}
      refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
      ListHeaderComponent={<Segmented testID="invoice-type-filter" value={type} onChange={setType} options={[{ value: "all", label: "All" }, { value: "guest", label: "Guest stays" }, { value: "client", label: "Client services" }]} />}
      ListEmptyComponent={q.isLoading ? <Loading /> : q.isError ? <ErrorState onRetry={q.refetch} /> : <Empty icon="receipt-outline" title="No invoices yet" subtitle="Create invoices for guests or owner services." />}
      renderItem={({ item: i }) => (
        <Card testID={`invoice-card-${i.id}`} onPress={() => router.push(`/invoice/${i.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
            <Icon name={i.type === "guest" ? "bed-outline" : "briefcase-outline"} size={20} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Txt v="subtitle" style={{ fontSize: 15 }} numberOfLines={1}>{i.bill_to_name}</Txt>
            <Txt v="caption">{i.number} · {fmtDate(i.issue_date)}</Txt>
          </View>
          <View style={{ alignItems: "flex-end", gap: 4 }}>
            <Txt v="mono" style={{ fontSize: 15 }}>{inr(i.total)}</Txt>
            <Badge label={i.status === "paid" ? "Paid" : "Unpaid"} tone={i.status === "paid" ? "success" : "warning"} />
          </View>
        </Card>
      )}
    />
  );
}

function OtaReport({ bottom }: { bottom: number }) {
  const { colors } = useTheme();
  const [month, setMonth] = useState(thisMonth());
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["ota-report", month], queryFn: () => api.get(`/reports/ota?month=${month}`) });
  const max = Math.max(1, ...(q.data?.rows ?? []).map((r: any) => r.gross));
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
      <MonthStepper month={month} setMonth={setMonth} />
      {q.isLoading ? <Loading label="Generating report..." /> : q.isError ? <ErrorState onRetry={q.refetch} /> : (
        <>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            {[["Gross", inr(q.data.total_gross)], ["Commission", inr(q.data.total_commission)], ["Bookings", String(q.data.total_bookings)]].map(([l, v]) => (
              <Card key={l} style={{ flex: 1, padding: spacing.md }}>
                <Txt v="caption">{l}</Txt>
                <Txt v="mono" style={{ fontSize: 16 }}>{v}</Txt>
              </Card>
            ))}
          </View>
          <Card testID="ota-report-card">
            <Txt v="subtitle">Revenue by OTA</Txt>
            <Txt v="caption" style={{ marginBottom: spacing.sm }}>Tap an OTA for villa-wise breakdown</Txt>
            {q.data.rows.length === 0 ? <Empty icon="bar-chart-outline" title="No data available for this period" /> : null}
            {q.data.rows.map((r: any) => {
              const on = open === r.ota;
              return (
                <Animated.View key={r.ota} layout={LinearTransition}>
                  <Pressable testID={`ota-report-row-${r.ota}`} onPress={() => setOpen(on ? null : r.ota)} style={{ paddingVertical: spacing.md, gap: 6, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                      <Txt v="subtitle" style={{ flex: 1, fontSize: 14 }}>{r.ota}</Txt>
                      <Txt v="mono" style={{ fontSize: 15 }}>{inr(r.gross)}</Txt>
                      <Icon name={on ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
                    </View>
                    <View style={{ height: 10, borderRadius: 5, backgroundColor: colors.surfaceSecondary, overflow: "hidden" }}>
                      <View style={{ width: `${(r.gross / max) * 100}%`, height: "100%", backgroundColor: otaColor(r.ota), borderRadius: 5 }} />
                    </View>
                    <Txt v="caption">{r.bookings} bookings · {r.nights} nights · ADR {inr(r.adr)} · commission {inr(r.commission)}</Txt>
                  </Pressable>
                  {on ? (
                    <Animated.View entering={FadeIn} style={{ paddingVertical: spacing.sm, paddingLeft: spacing.md, gap: spacing.xs }}>
                      {r.properties.map((p: any) => (
                        <View key={p.name} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                          <Txt v="body">{p.name}</Txt>
                          <Txt v="mono" style={{ fontSize: 14 }}>{inr(p.gross)}</Txt>
                        </View>
                      ))}
                      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                        <Txt v="body">Net after commission</Txt>
                        <Txt v="mono" style={{ fontSize: 14 }}>{inr(r.net)}</Txt>
                      </View>
                    </Animated.View>
                  ) : null}
                </Animated.View>
              );
            })}
          </Card>
        </>
      )}
    </ScrollView>
  );
}

function Owners({ bottom }: { bottom: number }) {
  const router = useRouter();
  const { colors } = useTheme();
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });
  const reports = useQuery({ queryKey: ["owner-reports"], queryFn: () => api.get<any[]>("/owner-reports") });
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: bottom + 96 }} refreshControl={<RefreshControl refreshing={reports.isRefetching} onRefresh={() => { props.refetch(); reports.refetch(); }} tintColor={colors.brandPrimary} />}>
      <Txt v="label">Owner statements</Txt>
      {(props.data ?? []).map((p) => (
        <Card key={p.id} testID={`owner-statement-${p.id}`} onPress={() => router.push(`/report/settlement?property_id=${p.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <Icon name="pie-chart-outline" size={22} color={colors.brandPrimary} />
          <View style={{ flex: 1 }}>
            <Txt v="subtitle" style={{ fontSize: 15 }}>{p.name}</Txt>
            <Txt v="caption">{p.owner_name} · {p.owner_share_percent}/{100 - p.owner_share_percent} split</Txt>
          </View>
          <Icon name="chevron-forward" size={18} color={colors.muted} />
        </Card>
      ))}
      <Txt v="label" style={{ marginTop: spacing.sm }}>Sent reports</Txt>
      {reports.isLoading ? <Loading /> : (reports.data ?? []).length === 0 ? <Empty icon="images-outline" title="No owner reports yet" subtitle="Create one with photos & videos of the villa." /> : null}
      {(reports.data ?? []).map((r) => (
        <Card key={r.id} testID={`owner-report-${r.id}`} onPress={() => router.push(`/report/${r.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <Txt v="subtitle" style={{ fontSize: 15 }} numberOfLines={1}>{r.title}</Txt>
            <Txt v="caption">{r.media_ids.length} media · {fmtDate(r.created_at)}</Txt>
          </View>
          <Txt v="mono" style={{ fontSize: 14 }}>{inr(r.settlement?.owner_payout)}</Txt>
        </Card>
      ))}
    </ScrollView>
  );
}

export default function Finance() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { colors } = useTheme();
  const [tab, setTab] = useState<Tab>("invoices");
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Txt v="title">Finance & Reports</Txt>
        <Segmented testID="finance-tabs" value={tab} onChange={setTab} options={[{ value: "invoices", label: "Invoices" }, { value: "ota", label: "OTA reports" }, { value: "owners", label: "Owners" }]} />
      </View>
      {tab === "invoices" ? <Invoices bottom={bottomChrome} /> : tab === "ota" ? <OtaReport bottom={bottomChrome} /> : <Owners bottom={bottomChrome} />}
      {tab !== "ota" ? (
        <Pressable testID={tab === "invoices" ? "fab-new-invoice" : "fab-new-owner-report"} onPress={() => router.push(tab === "invoices" ? "/invoice/new" : "/report/new")} style={({ pressed }) => ({ position: "absolute", right: spacing.lg, bottom: bottomChrome + 16, height: 56, paddingHorizontal: spacing.xl, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", gap: spacing.sm, transform: [{ scale: pressed ? 0.96 : 1 }], shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6 })}>
          <Icon name="add" size={22} color={colors.onBrandPrimary} />
          <Txt v="subtitle" color={colors.onBrandPrimary} style={{ fontSize: 15 }}>{tab === "invoices" ? "New invoice" : "Owner report"}</Txt>
        </Pressable>
      ) : null}
    </View>
  );
}
