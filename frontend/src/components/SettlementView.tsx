import React, { useState } from "react";
import { Pressable, View } from "react-native";
import Animated, { FadeIn, LinearTransition } from "react-native-reanimated";
import { Card, Icon, Row, Txt } from "@/src/ui";
import { fmtShort, inr, monthLabel, monthShort, otaColor } from "@/src/format";
import { fonts, radius, spacing, useTheme } from "@/src/theme";
import { useRouter } from 'expo-router';
import { useAuth } from '@/src/auth';
import { otaBreakdown, reportPresentation } from '@/src/expense-presentation';
import { ExpenseDetails } from '@/src/components/ExpenseDetails';
import { BookingAmounts } from '@/src/components/BookingAmounts';

export function SettlementView({ s, onMonthPress }: { s: any; onMonthPress?: (m: string) => void }) {
  const { colors } = useTheme();
  const router = useRouter();
  const [openBooking, setOpenBooking] = useState<string | null>(null);
  const [seg, setSeg] = useState<string | null>(null);
  const { user } = useAuth();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const presentation = reportPresentation(s);
  const toggle = (key: string) => setExpanded(previous => ({ ...previous, [key]: !previous[key] }));
  const editExpense = (item: any) => item.booking_id ? router.push(`/booking/new?id=${item.booking_id}`) : router.push(`/property/${s.property_id}?expense_id=${item.id}&month=${s.month}`);
  const disclosure = (key: string, label: string, value: string | undefined, children: React.ReactNode) => <View>
      <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ expanded: !!expanded[key] }} testID={`statement-${key}`} onPress={() => toggle(key)} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.md, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Txt style={{ flex: 1 }}>{label}</Txt>{value != null ? <Txt v="mono">{value}</Txt> : null}<Icon name={expanded[key] ? 'chevron-up' : 'chevron-down'} size={18} />
      </Pressable>
      {expanded[key] ? <View testID={`statement-${key}-content`} style={{ gap: spacing.md, paddingVertical: spacing.sm }}>{children}</View> : null}
    </View>;
  const expenseItems = (kind: string) => {
    const group = presentation.groups.find(g => g.key === kind);
    return <>
      {group?.mismatch ? <Txt color={colors.error}>The saved expense total differs from the available details. Saved amounts are retained; ask the admin to review this statement.</Txt> : null}
      {group?.items.map((item: any) => <ExpenseDetails key={item.id} item={item} onEdit={user?.role === 'admin' && !item.summary ? () => editExpense(item) : undefined} />)}
    </>;
  };
  const [openOta, setOpenOta] = useState<string | null>(null);
  const [trendSel, setTrendSel] = useState<string>(s.month);

  const segments = [
    { key: "owner", label: "Owner allocated share", value: s.owner_share, color: colors.brandPrimary, note: `${s.owner_share_percent}% of revenue available to split. Owner expenses after split and TDS are deducted later in the payout calculation.` },
    { key: "bm", label: "Britsmaid allocated share", value: s.britsmaid_share, color: colors.brandSecondary, note: `${s.britsmaid_share_percent}% of revenue available to split. Britsmaid expenses after split are deducted in the Britsmaid breakdown.` },
  ];
  const total = segments.reduce((a, b) => a + b.value, 0) || 1;
  const overview = [
    { key: 'ota', label: 'OTA commissions', value: s.ota_commission, note: 'Charged by booking platforms before the revenue split. Open booking deductions or individual bookings for the breakdown.' },
    { key: 'booking-costs', label: 'Booking taxes', value: presentation.bookingTaxes, note: 'Booking GST and other tax deductions, included once in booking deductions before the revenue split.' },
    { key: 'expenses', label: 'Expenses', value: presentation.totalExpenses, note: 'Full reported expense total for both parties, including before-split, after-split and any reference-only records. See the detailed expense breakdown for how each cost is treated.' },
  ];
  const canChartSplit = s.net_revenue > 0 && segments.every(g => g.value >= 0);
  const trend: any[] = s.trend ?? [];
  const maxT = Math.max(1, ...trend.map((t) => t.gross));
  const selT = trend.find((t) => t.month === trendSel);

  return (
    <View style={{ gap: spacing.md }}>
      <Animated.View entering={FadeIn} testID="settlement-hero" style={{ backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.xl }}>
        <Txt v="label" color={colors.brandTertiary}>Owner final payout · {monthLabel(s.month)}</Txt>
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
        <Row label="Revenue available to split" value={inr(s.net_revenue)} />
        {canChartSplit ? <View style={{ flexDirection: "row", height: 28, borderRadius: radius.sm, overflow: "hidden", marginTop: spacing.md, backgroundColor: colors.surfaceSecondary }}>
          {segments.map((g) => (
            <Pressable key={g.key} testID={`split-segment-${g.key}`} onPress={() => setSeg(seg === g.key ? null : g.key)} style={{ flex: Math.max(g.value, 0) / total, backgroundColor: g.color, opacity: seg && seg !== g.key ? 0.35 : 1 }} />
          ))}
        </View> : <Txt v="caption" style={{ marginTop: spacing.md }}>{segments.some(g => g.value < 0) ? "Costs exceed revenue this month. The amounts and calculation below show the balance." : "No positive revenue available to split this month."}</Txt>}
        <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
          {segments.map((g) => (
            <Pressable key={g.key} testID={`split-legend-${g.key}`} onPress={() => setSeg(seg === g.key ? null : g.key)} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, opacity: seg && seg !== g.key ? 0.5 : 1 }}>
              <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: g.color }} />
              <Txt v="body" style={{ flex: 1 }}>{g.label}</Txt>
              <Txt v="mono">{inr(g.value)}</Txt>
            </Pressable>
          ))}
        </View>
        <View style={{ marginTop: spacing.md }}>
          {overview.filter(g => g.value || (g.key === 'expenses' && presentation.groups.length)).map(g => <Pressable key={g.key} accessibilityRole="button" testID={`split-legend-${g.key}`} onPress={() => setSeg(seg === g.key ? null : g.key)} style={{ flexDirection: 'row', paddingVertical: spacing.sm, gap: spacing.sm }}>
            <Txt style={{ flex: 1 }}>{g.label}</Txt><Txt v="mono">{inr(g.value)}</Txt>
          </Pressable>)}
          {presentation.groups.length ? <Txt v="caption">See the detailed expense breakdown.</Txt> : null}
        </View>
        {seg ? (
          <Animated.View entering={FadeIn} style={{ marginTop: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, padding: spacing.md }}>
            <Txt v="body" color={colors.onBrandTertiary}>{[...segments, ...overview].find((x) => x.key === seg)?.note}</Txt>
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
        <Row label="Gross guest payments" value={inr(s.gross)} />
        {presentation.bookingDeductions ? disclosure('booking-deductions', 'Booking deductions', `-${inr(presentation.bookingDeductions)}`, <>
          {s.ota_commission ? <Row label="OTA commissions" value={inr(s.ota_commission)} /> : null}
          {s.gst_total ? <Row label="Booking GST" value={inr(s.gst_total)} /> : null}
          {s.platform_tax ? <Row label="Other tax deductions" value={inr(s.platform_tax)} /> : null}
          <Txt v="caption">Included once before the revenue split. Individual booking breakdowns are available below.</Txt>
        </>) : null}
        {presentation.groups.some(g => g.key === 'before_split') ? disclosure('before-summary', 'Expenses before revenue split', `-${inr(presentation.before)}`, expenseItems('before_split')) : null}
        <Row strong label="Revenue available to split" value={inr(s.net_revenue)} />
        <Row label={`Owner allocated share (${s.owner_share_percent}%)`} value={inr(s.owner_share)} />
        {presentation.ownerAfter > 0 ? disclosure('owner-after', 'Owner expenses after split', `-${inr(presentation.ownerAfter)}`, <>
          {expenseItems('after_split')}
          <Txt v="caption">Expense entries show the full costs. Only the owner contribution above is deducted from the owner share.</Txt>
        </>) : null}
        {s.owner_before_tds != null ? <Row label="Owner balance before TDS" value={inr(s.owner_before_tds)} /> : null}
        {s.owner_tds_percent || s.owner_tds ? disclosure('tds', `Owner TDS (${s.owner_tds_percent || 2}%)`, `-${inr(s.owner_tds)}`, <Txt v="caption">Calculated on the positive owner balance after applicable expenses. This is the monthly total.</Txt>) : null}
        <Row strong label="Owner final payout" value={inr(s.owner_payout)} testID="breakdown-owner-payout" />
      </Card>

      {presentation.groups.length ? <Card testID="statement-expense-records">
        <Txt v="subtitle">Expenses</Txt>
        <Row label="Total reported expenses" value={inr(presentation.totalExpenses)} />
        {presentation.groups.map(g => <View key={g.key}>
          {disclosure(`expenses-${g.key}`, g.label, inr(g.total), <>
            {g.key === 'after_split' ? <>
              {presentation.ownerAfter > 0 ? <Row label="Owner contribution" value={inr(presentation.ownerAfter)} /> : null}
              {presentation.bmAfter > 0 ? <Row label="Britsmaid contribution" value={inr(presentation.bmAfter)} /> : null}
            </> : null}
            {expenseItems(g.key)}
          </>)}
        </View>)}
      </Card> : null}

      <Card testID="statement-britsmaid-card">
        {disclosure('britsmaid-breakdown', 'Britsmaid breakdown', undefined, <>
          <Row label={`Britsmaid allocated share (${s.britsmaid_share_percent}%)`} value={inr(s.britsmaid_share)} />
          {presentation.bmAfter > 0 ? disclosure('britsmaid-after', 'Britsmaid expenses after split', `-${inr(presentation.bmAfter)}`, expenseItems('after_split')) : null}
          <Row strong label="Britsmaid net earnings" value={inr(s.britsmaid_net)} />
        </>)}
      </Card>

      <Card testID="ota-breakdown-card">
        <Txt v="subtitle" style={{ marginBottom: spacing.sm }}>Revenue by OTA</Txt>
        {s.by_ota.length === 0 ? <Txt v="caption">No bookings this month</Txt> : null}
        {s.by_ota.map((o: any) => {
          const open = openOta === o.ota;
          const breakdown = otaBreakdown(o, s.bookings);
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
                  <Row label="Gross guest payments" value={inr(o.gross)} />
                  <Row label="Taxes & commission" value={`${breakdown.taxesAndCommission ? '-' : ''}${inr(breakdown.taxesAndCommission)}`} />
                  {breakdown.bookingExpenses > 0 ? <Row label="Other booking expenses" value={`-${inr(breakdown.bookingExpenses)}`} /> : null}
                  <Row strong label="Revenue available to split" value={inr(o.net)} />
                  <Txt v="caption">Before property expenses and owner TDS. Any property expenses entered before the split are also deducted in the payout calculation.</Txt>
                </View>
              ) : null}
            </Animated.View>
          );
        })}
      </Card>

      <Card testID="bookings-breakdown-card">
        <Txt v="subtitle" style={{ marginBottom: spacing.sm }}>Bookings ({s.bookings.length})</Txt>
        {s.bookings.map((b: any) => (
          <View key={b.id} style={{ paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.sm }}>
          <Pressable onPress={() => setOpenBooking(openBooking === b.id ? null : b.id)} style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: otaColor(b.ota) }} />
            <View style={{ flex: 1 }}>
              <Txt v="body" style={{ color: colors.onSurface, fontFamily: fonts.textSemi }}>{b.guest_name}</Txt>
              <Txt v="caption">{b.ota} · {fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
            </View>
            <Txt v="mono" style={{ fontSize: 14 }}>{inr(b.amount)}</Txt>
            <Icon name={openBooking === b.id ? 'chevron-up' : 'chevron-down'} size={16} />
          </Pressable>
          {openBooking === b.id ? <>
            <Pressable onPress={() => router.push(`/booking/${b.id}`)}><Txt color={colors.brandPrimary}>Open booking details →</Txt></Pressable>
            <BookingAmounts gross={b.financials?.gst_included === false ? b.amount - b.financials.gst.amount : b.amount} value={b.financials} commission={b.ota_commission || 0} ownerPercent={s.owner_share_percent} readOnly />
          </> : null}
          </View>
        ))}
      </Card>
    </View>
  );
}
