import React, { useState } from "react";
import { Pressable, View } from "react-native";
import Animated, { FadeIn, LinearTransition } from "react-native-reanimated";
import { Card, Icon, Row, Txt } from "@/src/ui";
import { fmtShort, inr, monthLabel, monthShort, otaColor } from "@/src/format";
import { fonts, radius, spacing, useTheme } from "@/src/theme";

export function SettlementView({ s, onMonthPress }: { s: any; onMonthPress?: (m: string) => void }) {
  const { colors } = useTheme();
  const [seg, setSeg] = useState<string | null>(null);
  const [openOta, setOpenOta] = useState<string | null>(null);
  const [trendSel, setTrendSel] = useState<string>(s.month);

  const segments = [
    { key: "owner", label: "Owner share", value: s.owner_share, color: colors.brandPrimary, note: `${s.owner_share_percent}% of net revenue goes to the owner.` },
    { key: "bm", label: "Britsmaid share", value: s.britsmaid_share, color: colors.brandSecondary, note: `${s.britsmaid_share_percent}% of net revenue retained for management.` },
    { key: "ota", label: "OTA commission", value: s.ota_commission, color: colors.borderStrong, note: "Charged by booking platforms before the split." },
  ];
  const total = segments.reduce((a, b) => a + b.value, 0) || 1;
  const trend: any[] = s.trend ?? [];
  const maxT = Math.max(1, ...trend.map((t) => t.gross));
  const selT = trend.find((t) => t.month === trendSel);

  return (
    <View style={{ gap: spacing.md }}>
      <Animated.View entering={FadeIn} testID="settlement-hero" style={{ backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.xl }}>
        <Txt v="label" color={colors.brandTertiary}>Owner payout · {monthLabel(s.month)}</Txt>
        <Txt v="display" color={colors.onBrandPrimary} style={{ fontSize: 38, marginTop: spacing.xs }} testID="settlement-owner-payout">{inr(s.owner_payout)}</Txt>
        <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.md }}>
          {[["Nights", String(s.nights)], ["Occupancy", `${s.occupancy_percent}%`], ["Split", `${s.owner_share_percent}/${s.britsmaid_share_percent}`]].map(([l, v]) => (
            <View key={l}>
              <Txt v="caption" color={colors.brandTertiary}>{l}</Txt>
              <Txt v="mono" color={colors.onBrandPrimary}>{v}</Txt>
            </View>
          ))}
        </View>
      </Animated.View>

      <Card testID="split-card">
        <Txt v="subtitle">Revenue split</Txt>
        <Txt v="caption">Tap a segment to see how it is calculated</Txt>
        <View style={{ flexDirection: "row", height: 28, borderRadius: radius.sm, overflow: "hidden", marginTop: spacing.md, backgroundColor: colors.surfaceSecondary }}>
          {segments.map((g) => (
            <Pressable key={g.key} testID={`split-segment-${g.key}`} onPress={() => setSeg(seg === g.key ? null : g.key)} style={{ flex: Math.max(g.value, 0) / total, backgroundColor: g.color, opacity: seg && seg !== g.key ? 0.35 : 1 }} />
          ))}
        </View>
        <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
          {segments.map((g) => (
            <Pressable key={g.key} testID={`split-legend-${g.key}`} onPress={() => setSeg(seg === g.key ? null : g.key)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, opacity: seg && seg !== g.key ? 0.5 : 1 }}>
              <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: g.color }} />
              <Txt v="body" style={{ flex: 1 }}>{g.label}</Txt>
              <Txt v="mono">{inr(g.value)}</Txt>
              <Txt v="caption" style={{ width: 44, textAlign: "right" }}>{Math.round((g.value / total) * 100)}%</Txt>
            </Pressable>
          ))}
        </View>
        {seg ? (
          <Animated.View entering={FadeIn} style={{ marginTop: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, padding: spacing.md }}>
            <Txt v="body" color={colors.onBrandTertiary}>{segments.find((x) => x.key === seg)?.note}</Txt>
          </Animated.View>
        ) : null}
      </Card>

      {trend.length ? (
        <Card testID="trend-card">
          <Txt v="subtitle">6-month trend</Txt>
          <Txt v="caption">Tap a month to compare{onMonthPress ? ", tap again to open it" : ""}</Txt>
          <View style={{ flexDirection: "row", alignItems: "flex-end", height: 130, gap: spacing.sm, marginTop: spacing.md }}>
            {trend.map((t) => {
              const on = t.month === trendSel;
              return (
                <Pressable key={t.month} testID={`trend-bar-${t.month}`} onPress={() => (on && onMonthPress && t.month !== s.month ? onMonthPress(t.month) : setTrendSel(t.month))} style={{ flex: 1, alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
                  <Animated.View layout={LinearTransition} style={{ width: "100%", height: `${Math.max(4, (t.gross / maxT) * 100)}%`, borderRadius: radius.sm, backgroundColor: on ? colors.brandPrimary : colors.brandTertiary, justifyContent: "flex-end", overflow: "hidden" }}>
                    <View style={{ height: `${t.gross ? Math.max(0, (t.owner_payout / t.gross) * 100) : 0}%`, backgroundColor: on ? colors.brandSecondary : colors.borderStrong }} />
                  </Animated.View>
                  <Txt v="caption" style={{ marginTop: 4, fontFamily: on ? fonts.textSemi : fonts.text, color: on ? colors.brandPrimary : colors.muted }}>{monthShort(t.month)}</Txt>
                </Pressable>
              );
            })}
          </View>
          {selT ? (
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.md }}>
              <View><Txt v="caption">Gross</Txt><Txt v="mono">{inr(selT.gross)}</Txt></View>
              <View><Txt v="caption">Owner payout</Txt><Txt v="mono">{inr(selT.owner_payout)}</Txt></View>
              <View><Txt v="caption">Nights</Txt><Txt v="mono">{selT.nights}</Txt></View>
            </View>
          ) : null}
        </Card>
      ) : null}

      <Card testID="breakdown-card">
        <Txt v="subtitle" style={{ marginBottom: spacing.xs }}>How the payout is calculated</Txt>
        <Row label="Gross booking revenue" value={inr(s.gross)} />
        <Row label="OTA commissions" value={`-${inr(s.ota_commission)}`} />
        <Row label="Net revenue" value={inr(s.net_revenue)} />
        <Row label={`Owner share (${s.owner_share_percent}%)`} value={inr(s.owner_share)} />
        <Row label={s.electricity_mode === "split_half" ? `Electricity · owner 50% of ${inr(s.electricity_total)}` : "Electricity · managed by owner"} value={s.electricity_mode === "split_half" ? `-${inr(s.owner_electricity)}` : "—"} />
        {s.other_deductions ? <Row label="Other deductions" value={`-${inr(s.other_deductions)}`} /> : null}
        <Row strong label="Owner payout" value={inr(s.owner_payout)} testID="breakdown-owner-payout" />
        <View style={{ marginTop: spacing.md, flexDirection: "row", justifyContent: "space-between" }}>
          <Txt v="caption">Britsmaid net (after {inr(s.britsmaid_electricity)} electricity)</Txt>
          <Txt v="mono" style={{ fontSize: 14 }}>{inr(s.britsmaid_net)}</Txt>
        </View>
      </Card>

      <Card testID="ota-breakdown-card">
        <Txt v="subtitle" style={{ marginBottom: spacing.sm }}>Revenue by OTA</Txt>
        {s.by_ota.length === 0 ? <Txt v="caption">No bookings this month</Txt> : null}
        {s.by_ota.map((o: any) => {
          const open = openOta === o.ota;
          return (
            <Animated.View key={o.ota} layout={LinearTransition}>
              <Pressable testID={`ota-row-${o.ota}`} onPress={() => setOpenOta(open ? null : o.ota)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
                <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: otaColor(o.ota) }} />
                <Txt v="subtitle" style={{ flex: 1, fontSize: 14 }}>{o.ota}</Txt>
                <Txt v="mono" style={{ fontSize: 15 }}>{inr(o.gross)}</Txt>
                <Icon name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
              </Pressable>
              {open ? (
                <View style={{ paddingLeft: spacing.lg, paddingBottom: spacing.sm }}>
                  <Row label="Bookings" value={String(o.bookings)} />
                  <Row label="Nights" value={String(o.nights)} />
                  <Row label="Commission" value={`-${inr(o.commission)}`} />
                  <Row label="Net" value={inr(o.net)} />
                </View>
              ) : null}
            </Animated.View>
          );
        })}
      </Card>

      <Card testID="bookings-breakdown-card">
        <Txt v="subtitle" style={{ marginBottom: spacing.sm }}>Bookings ({s.bookings.length})</Txt>
        {s.bookings.map((b: any) => (
          <View key={b.id} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.sm }}>
            <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: otaColor(b.ota) }} />
            <View style={{ flex: 1 }}>
              <Txt v="body" style={{ color: colors.onSurface, fontFamily: fonts.textSemi }}>{b.guest_name}</Txt>
              <Txt v="caption">{b.ota} · {fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
            </View>
            <Txt v="mono" style={{ fontSize: 14 }}>{inr(b.amount)}</Txt>
          </View>
        ))}
      </Card>
    </View>
  );
}
