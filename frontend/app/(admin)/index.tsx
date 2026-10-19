import React from "react";
import { RefreshControl, ScrollView, View, Pressable } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { usesNativeTabs } from "@/src/navigation";
import { Badge, Card, ErrorState, Icon, IconButton, IconName, Loading, Txt } from "@/src/ui";
import { fmtShort, inr, monthLabel, otaColor } from "@/src/format";
import { fonts, radius, spacing, useTheme } from "@/src/theme";

export default function Dashboard() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { colors } = useTheme();
  const { user, logout } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get("/dashboard") });
  const d = q.data;
  const notices = useQuery({ queryKey: ["system-issues"], queryFn: () => api.get<any[]>("/system/issues"), refetchInterval: 30000 });

  const metric = (label: string, value: string, icon: IconName, testID: string, onPress?: () => void) => (
    <Card testID={testID} onPress={onPress} style={{ flex: 1, padding: spacing.md, gap: spacing.sm }}>
      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
        <Icon name={icon} size={18} color={colors.brandPrimary} />
      </View>
      <Txt v="mono" style={{ fontSize: 20, fontFamily: fonts.display }}>{value}</Txt>
      <Txt v="caption">{label}</Txt>
    </Card>
  );

  const action = (label: string, icon: IconName, to: string, testID: string) => (
    <Pressable testID={testID} onPress={() => router.push(to as any)} style={({ pressed }) => ({ flex: 1, alignItems: "center", gap: spacing.xs, opacity: pressed ? 0.6 : 1 })}>
      <View style={{ width: 52, height: 52, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}>
        <Icon name={icon} size={22} color={colors.onBrandPrimary} />
      </View>
      <Txt v="caption" style={{ textAlign: "center", color: colors.onSurfaceSecondary }}>{label}</Txt>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <Image source={require("../../assets/images/logo.jpg")} style={{ width: 44, height: 44, borderRadius: 10 }} contentFit="cover" />
        <View style={{ flex: 1 }}>
          <Txt v="caption">Hello, {user?.name?.split(" ")[0]}</Txt>
          <Txt v="title">Britsmaid</Txt>
        </View>
        </View>
        <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
          <IconButton testID="dashboard-guests-button" name="id-card-outline" label="Guest IDs" onPress={() => router.push("/guests")} />
          <IconButton testID="dashboard-staff-button" name="people-outline" label="Team" onPress={() => router.push("/staff")} />
          <IconButton name="notifications-outline" label={`Notices${notices.data?.some((issue: any) => issue.status === "open") ? " !" : ""}`} onPress={() => router.push("/issues")} />
          <IconButton testID="dashboard-logout-button" name="log-out-outline" label="Sign out" onPress={logout} />
        </View>
      </View>
      {q.isLoading ? <Loading label="Syncing properties..." /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: bottomChrome + spacing.xl }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
          <Animated.View entering={FadeInDown.duration(400)}>
            <Txt v="label">{monthLabel(d.month)}</Txt>
            <View style={{ flexDirection: "row", gap: spacing.md, marginTop: spacing.sm }}>
              {metric("Gross revenue", inr(d.month_gross), "trending-up", "metric-revenue", () => router.push("/(admin)/finance"))}
              {metric("Bookings", String(d.month_bookings), "bed-outline", "metric-bookings", () => router.push("/(admin)/calendar"))}
            </View>
            <View style={{ flexDirection: "row", gap: spacing.md, marginTop: spacing.md }}>
              {metric("Occupied today", `${d.occupied_today}/${d.properties}`, "home-outline", "metric-occupied", () => router.push("/(admin)/properties"))}
              {metric(`Unpaid (${d.unpaid_invoices})`, inr(d.unpaid_total), "receipt-outline", "metric-unpaid", () => router.push("/(admin)/finance"))}
            </View>
          </Animated.View>

          <Animated.View entering={FadeInDown.delay(100).duration(400)}>
            <Card style={{ flexDirection: "row", paddingVertical: spacing.lg }}>
              {action("New booking", "add-circle-outline", "/booking/new", "quick-new-booking")}
              {action("Invoice", "document-text-outline", "/invoice/new", "quick-new-invoice")}
              {action("Owner report", "stats-chart-outline", "/report/new", "quick-owner-report")}
              {action("Cleaning", "sparkles-outline", "/cleaning", "quick-cleaning")}
            </Card>
          </Animated.View>

          <Card onPress={() => router.push("/training")}><Txt v="subtitle">Cleaner training</Txt><Txt v="caption">Lessons, onboarding, refreshers and completion history</Txt></Card>
          <Animated.View entering={FadeInDown.delay(150).duration(400)}>
            <Card testID="dashboard-team-card" onPress={() => router.push("/staff")} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Icon name="people" size={22} color={colors.brandPrimary} />
              <View style={{ flex: 1 }}>
                <Txt v="subtitle" style={{ fontSize: 15 }}>Team & logins</Txt>
                <Txt v="caption">Add people, set passwords & choose their access</Txt>
              </View>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Card>
          </Animated.View>

          <Animated.View entering={FadeInDown.delay(200).duration(400)} style={{ gap: spacing.sm }}>
            <Txt v="label">Cleaning to verify</Txt>
            {d.pending_cleaning.length === 0 ? (
              <Card><Txt v="body">All villas are guest-ready.</Txt></Card>
            ) : d.pending_cleaning.map((c: any) => (
              <Card key={c.id} testID={`pending-clean-${c.id}`} onPress={() => router.push(`/cleaning/${c.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <Icon name="sparkles" size={20} color={colors.warning} />
                <View style={{ flex: 1 }}>
                  <Txt v="subtitle" style={{ fontSize: 15 }}>{c.property_name}</Txt>
                  <Txt v="caption">Checkout {fmtShort(c.date)}</Txt>
                </View>
                <Badge label={c.status === "in_progress" ? "In progress" : "Pending"} tone="warning" />
              </Card>
            ))}
          </Animated.View>

          {[["Arrivals today", d.arrivals, "arrivals"], ["Departures today", d.departures, "departures"]].map(([title, list, key]: any) => (
            <View key={key} style={{ gap: spacing.sm }}>
              <Txt v="label">{title}</Txt>
              {list.length === 0 ? <Card><Txt v="caption">None</Txt></Card> : list.map((b: any) => (
                <Card key={b.id} testID={`${key}-${b.id}`} onPress={() => router.push(`/booking/new?id=${b.id}`)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                  <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: otaColor(b.ota) }} />
                  <View style={{ flex: 1 }}>
                    <Txt v="subtitle" style={{ fontSize: 15 }}>{b.guest_name}</Txt>
                    <Txt v="caption">{b.property_name} · {b.ota}</Txt>
                  </View>
                  <Txt v="mono" style={{ fontSize: 13 }}>{fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
                </Card>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
