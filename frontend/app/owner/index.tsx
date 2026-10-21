import { PropertyCover } from "@/src/components/PropertyCover";
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button, Card, Empty, ErrorState, IconButton, Loading, Txt } from "@/src/ui";
import { fmtDate, inr, monthLabel } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export default function OwnerHome() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const { user, logout } = useAuth();
  const q = useQuery({ queryKey: ["owner-dashboard"], queryFn: () => api.get("/owner/dashboard") });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Image source={require("../../assets/images/logo.jpg")} style={{ width: 44, height: 44, borderRadius: 10 }} contentFit="cover" />
        <View style={{ flex: 1 }}>
          <Txt v="caption">Owner portal</Txt>
          <Txt v="title" numberOfLines={1}>{user?.name?.replace(/\s*\(Owner\)/, "")}</Txt>
        </View>
        <IconButton testID="owner-logout-button" name="log-out-outline" onPress={logout} />
      </View>
      {q.isLoading ? <Loading label="Loading your villas..." /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: insets.bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
          <Animated.View entering={FadeInDown} testID="owner-total-card" style={{ backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.xl }}>
            <Txt v="label" color={colors.brandTertiary}>Expected earnings · {monthLabel(q.data.month)}</Txt>
            <Txt v="display" color={colors.onBrandPrimary} style={{ fontSize: 36, marginTop: spacing.xs }} testID="owner-total-payout">{inr(q.data.total_payout)}</Txt>
            <Txt v="caption" color={colors.brandTertiary}>Paid: {inr(q.data.total_paid)} · Balance due: {inr(q.data.total_balance)}</Txt>
          </Animated.View>
          <Txt v="caption">Last updated {new Date(q.dataUpdatedAt).toLocaleTimeString()}</Txt>
          <Button title="Refresh my properties" variant="secondary" loading={q.isRefetching} onPress={() => q.refetch()} />
          {q.data.villas.length === 0 ? <Empty icon="business-outline" title="No villas assigned yet" subtitle="Contact Britsmaid to link your property." /> : null}
          {q.data.villas.map((v: any, i: number) => (
            <Animated.View key={v.id} entering={FadeInDown.delay(80 + i * 60)}>
              <Card testID={`owner-villa-${v.id}`} onPress={() => router.push(`/owner/${v.id}`)} style={{ padding: 0, overflow: "hidden" }}>
                <View style={{ height: 150, backgroundColor: colors.brandTertiary }}>
                  <PropertyCover property={v} />
                  <LinearGradient colors={["transparent", colors.scrim]} style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 100 }} />
                  <View style={{ position: "absolute", left: spacing.lg, bottom: spacing.md }}>
                    <Txt v="title" color={colors.onSurfaceInverse}>{v.name}</Txt>
                    <Txt v="caption" color={colors.onSurfaceInverse}>{v.location}</Txt>
                  </View>
                  <View style={{ position: "absolute", top: spacing.md, right: spacing.md, flexDirection: "row", gap: 6 }}>
                    <Badge label={v.occupied ? "Guest staying" : "Vacant"} tone={v.occupied ? "info" : "neutral"} />
                    <Badge label={v.needs_cleaning ? "Being cleaned" : "Guest-ready"} tone={v.needs_cleaning ? "warning" : "success"} />
                  </View>
                </View>
                <View style={{ flexDirection: "row", padding: spacing.lg, gap: spacing.md }}>
                  {[["Payout", inr(v.month_payout)], ["Nights", String(v.month_nights)], ["Occupancy", `${v.occupancy_percent}%`], ["Upcoming", String(v.upcoming_bookings)]].map(([l, val]) => (
                    <View key={l} style={{ flex: 1 }}>
                      <Txt v="caption">{l}</Txt>
                      <Txt v="mono" style={{ fontSize: 15 }}>{val}</Txt>
                    </View>
                  ))}
                </View>
                <View style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
                  <Txt v="caption">Split {v.owner_share_percent}/{100 - v.owner_share_percent} · Electricity {v.electricity_mode === "split_half" ? "shared 50/50" : "paid by you"} · Last cleaned {v.last_cleaned ? fmtDate(v.last_cleaned) : "—"}</Txt>
                  <View style={{ marginTop: spacing.sm }}><Badge testID={`owner-villa-paid-${v.id}`} label={v.month_paid ? "This month's payout: Paid" : "This month's payout: Pending"} tone={v.month_paid ? "success" : "warning"} /></View>
                </View>
              </Card>
            </Animated.View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
