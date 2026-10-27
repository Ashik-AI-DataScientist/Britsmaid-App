import React, { useMemo, useState } from "react";
import { RefreshControl, ScrollView, View, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { usesNativeTabs } from "@/src/navigation";
import { CLEANING_COMPLETE_COLOR, CLEANING_COMPLETE_SOFT, CLEANING_COMPLETE_MARKER, cleaningDayStatus } from "@/src/cleaning-status";
import { MonthGrid, DayMark } from "@/src/components/MonthGrid";
import { Badge, Card, Chip, ChipRow, ErrorState, Icon, IconButton, Loading, Txt, useToast } from "@/src/ui";
import { OTAS, fmtDate, fmtShort, inr, monthLabel, otaColor, shiftMonth, thisMonth, todayISO, addDays } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export default function CalendarScreen() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const toast = useToast();
  const { colors } = useTheme();
  const [month, setMonth] = useState(thisMonth());
  const [day, setDay] = useState(todayISO());
  const [pid, setPid] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties"), refetchInterval: 30000 });
  const cal = useQuery({ queryKey: ["calendar", month, pid], queryFn: () => api.get(`/calendar?month=${month}${pid ? `&property_id=${pid}` : ""}`), refetchInterval: 30000 });
  const pmap = useMemo(() => Object.fromEntries((props.data ?? []).map((p) => [p.id, p])), [props.data]);
  const syncStatus = useQuery({ queryKey: ["sync-status"], queryFn: () => api.get("/sync/status"), refetchInterval: 60000 });

  const marks = useMemo(() => {
    const m: Record<string, DayMark> = {};
    for (const b of cal.data?.bookings ?? []) {
      for (let d = b.check_in; d < b.check_out; d = addDays(d, 1)) {
        if (!d.startsWith(month)) continue;
        (m[d] ??= { bars: [] }).bars!.push(b.status === "blocked" ? colors.muted : otaColor(b.ota));
      }
    }
    const cleanings = cal.data?.cleanings ?? [];
    for (const day of new Set<string>(cleanings.map((c: any) => c.date))) {
      (m[day] ??= {}).clean = cleaningDayStatus(cleanings.filter((c: any) => c.date === day));
    }
    return m;
  }, [cal.data, month, colors.muted]);

  const dayBookings = (cal.data?.bookings ?? []).filter((b: any) => b.check_in <= day && b.check_out > day);
  const dayOut = (cal.data?.bookings ?? []).filter((b: any) => b.check_out === day);
  const dayClean = (cal.data?.cleanings ?? []).filter((c: any) => c.date === day && c.status !== "cancelled");
  const freeVillas = (props.data ?? []).filter((p) => (!pid || p.id === pid) && !dayBookings.some((b: any) => b.property_id === p.id));

  const syncAll = async () => {
    setSyncing(true);
    try {
      const r = await api.post("/sync/run");
      toast(r.properties ? `OTA sync complete · ${r.added} new booking${r.added === 1 ? "" : "s"}${r.errors ? ` · ${r.errors} feed error(s)` : ""}` : "Add iCal links to a villa first", r.properties ? (r.errors ? "error" : "success") : "info");
      cal.refetch();
      syncStatus.refetch();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSyncing(false);
    }
  };
  const mins = syncStatus.data?.last_run ? Math.max(0, Math.round((syncStatus.dataUpdatedAt - new Date(syncStatus.data.last_run).getTime()) / 60000)) : null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <Txt v="title">Calendar</Txt>
            <Txt v="caption" testID="calendar-sync-status">OTA imports every 10 minutes while the service is running{mins !== null ? ` · last ${mins < 1 ? "just now" : mins < 60 ? `${mins} min ago` : `${Math.round(mins / 60)} h ago`}` : ""}</Txt>
          </View>
          <IconButton testID="calendar-sync-button" name={syncing ? "hourglass-outline" : "sync"} tone="brand" onPress={syncAll} />
          <IconButton testID="calendar-add-booking-button" name="add" tone="brand" onPress={() => router.push(`/booking/new?date=${day}${pid ? `&property_id=${pid}` : ""}`)} />
        </View>
        <ChipRow>
          <Chip testID="calendar-filter-all" label="All villas" selected={!pid} onPress={() => setPid(null)} />
          {(props.data ?? []).map((p) => (
            <Chip key={p.id} testID={`calendar-filter-${p.id}`} label={p.name} selected={pid === p.id} onPress={() => setPid(p.id)} />
          ))}
        </ChipRow>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: bottomChrome + spacing.xl }} refreshControl={<RefreshControl refreshing={cal.isRefetching} onRefresh={cal.refetch} tintColor={colors.brandPrimary} />}>
        <Card style={{ padding: spacing.md }}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.xs }}>
            <IconButton testID="calendar-prev-month" name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
            <Pressable testID="calendar-today-button" onPress={() => { setMonth(thisMonth()); setDay(todayISO()); }}>
              <Txt v="subtitle">{monthLabel(month)}</Txt>
            </Pressable>
            <IconButton testID="calendar-next-month" name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
          </View>
          {cal.isLoading ? <Loading /> : cal.isError ? <ErrorState message="Failed to load calendar" onRetry={cal.refetch} /> : (
            <MonthGrid month={month} selected={day} onSelect={setDay} marks={marks} />
          )}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm, paddingHorizontal: spacing.xs }}>
            {OTAS.map((o) => (
              <View key={o} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: otaColor(o) }} />
                <Txt v="caption">{o}</Txt>
              </View>
            ))}
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.warning }} />
              <Txt v="caption">Cleaning due</Txt>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <View style={{ width: 8, height: 8, ...CLEANING_COMPLETE_MARKER }} />
              <Txt v="caption">Cleaning complete</Txt>
            </View>
          </View>
        </Card>

        <Txt v="label" testID="calendar-selected-day">{fmtDate(day)}</Txt>
        {dayBookings.map((b: any) => (
          <Card key={b.id} testID={`calendar-booking-${b.id}`} onPress={() => router.push(`/booking/new?id=${b.id}`)} style={{ flexDirection: "row", gap: spacing.md, alignItems: "center" }}>
            <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: b.status === "blocked" ? colors.muted : otaColor(b.ota) }} />
            <View style={{ flex: 1, gap: 2 }}>
              <Txt v="subtitle" style={{ fontSize: 15 }}>{b.guest_name}</Txt>
              <Txt v="caption">{pmap[b.property_id]?.name} · {fmtShort(b.check_in)} → {fmtShort(b.check_out)}</Txt>
            </View>
            <View style={{ alignItems: "flex-end", gap: 4 }}>
              <Badge label={b.status === "blocked" ? "Blocked" : b.ota} tone={b.status === "blocked" ? "neutral" : "brand"} />
              {b.amount ? <Txt v="mono" style={{ fontSize: 13 }}>{inr(b.amount)}</Txt> : b.source === "ical" ? <Txt v="caption">iCal</Txt> : null}
            </View>
          </Card>
        ))}
        {dayOut.map((b: any) => (
          <Card key={`out-${b.id}`} style={{ flexDirection: "row", gap: spacing.md, alignItems: "center", backgroundColor: colors.surfaceSecondary }}>
            <Icon name="exit-outline" size={18} color={colors.muted} />
            <Txt v="body" style={{ flex: 1 }}>{b.guest_name} checks out · {pmap[b.property_id]?.name}</Txt>
          </Card>
        ))}
        {dayClean.map((c: any) => (
          <Card key={c.id} testID={`calendar-cleaning-${c.id}`} onPress={() => router.push(`/cleaning/${c.id}`)} style={{ flexDirection: "row", gap: spacing.md, alignItems: "center" }}>
            <View style={{ width: 36, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", borderWidth: c.status === "completed" ? 1 : 0, borderColor: CLEANING_COMPLETE_COLOR, backgroundColor: c.status === "completed" ? CLEANING_COMPLETE_SOFT : colors.warningSoft }}>
              <Icon name={c.status === "completed" ? "checkmark-done" : "sparkles"} size={18} color={c.status === "completed" ? CLEANING_COMPLETE_COLOR : colors.warning} />
            </View>
            <Txt v="body" style={{ flex: 1 }}>Cleaning · {pmap[c.property_id]?.name}</Txt>
            {c.status === "completed" ? <View style={{ backgroundColor: CLEANING_COMPLETE_SOFT, borderWidth: 1, borderColor: CLEANING_COMPLETE_COLOR, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 4 }}><Txt v="caption" color={CLEANING_COMPLETE_COLOR}>Cleaning complete</Txt></View> : <Badge label={c.status === "in_progress" ? "In progress" : c.status === "awaiting_review" ? "Awaiting review" : "Pending"} tone="warning" />}
          </Card>
        ))}
        <Card>
          <Txt v="label" style={{ marginBottom: spacing.sm }}>Available on this day ({freeVillas.length})</Txt>
          {freeVillas.length === 0 ? <Txt v="caption">Fully booked</Txt> : freeVillas.map((p) => (
            <Pressable key={p.id} testID={`calendar-free-${p.id}`} onPress={() => router.push(`/booking/new?date=${day}&property_id=${p.id}`)} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, gap: spacing.sm }}>
              <Icon name="checkmark-circle" size={18} color={colors.success} />
              <Txt v="body" style={{ flex: 1 }}>{p.name}</Txt>
              <Txt v="caption" color={colors.brandPrimary}>Book</Txt>
            </Pressable>
          ))}
        </Card>
      </ScrollView>
    </View>
  );
}
