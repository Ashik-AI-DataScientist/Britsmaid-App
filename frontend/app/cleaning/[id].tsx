import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { CaptureSheet } from "@/src/components/CaptureSheet";
import { MediaThumb } from "@/src/components/MediaThumb";
import { Badge, Button, Card, Chip, ErrorState, Header, Icon, Input, Loading, Txt, useToast } from "@/src/ui";
import { fmtDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export default function CleaningSession() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const q = useQuery({ queryKey: ["cleaning-session", id], queryFn: () => api.get(`/cleaning/${id}`) });
  const staff = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users"), enabled: isAdmin });
  const [target, setTarget] = useState<{ idx: number; phase: "before" | "after" } | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (q.isLoading) return <Loading label="Loading task details..." />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Cleaning" /><ErrorState message="Could not load task details" onRetry={q.refetch} /></View>;
  const c = q.data;
  const done = c.status === "completed";
  const refresh = (data: any) => {
    qc.setQueryData(["cleaning-session", id], data);
    qc.invalidateQueries({ queryKey: ["cleaning"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const addMedia = async (ids: string[]) => {
    if (!target) return;
    let data = c;
    for (const mid of ids) data = await api.post(`/cleaning/${id}/rooms/${target.idx}/media`, { phase: target.phase, media_id: mid });
    refresh(data);
  };
  const removeMedia = async (idx: number, phase: string, mid: string) => refresh(await api.del(`/cleaning/${id}/rooms/${idx}/media/${phase}/${mid}`));
  const assign = async (uid: string) => {
    refresh(await api.put(`/cleaning/${id}`, { assigned_to: uid }));
    toast("Cleaner assigned");
  };
  const complete = async () => {
    setSubmitting(true);
    try {
      refresh(await api.put(`/cleaning/${id}`, { status: "completed", ...(notes !== null ? { notes } : {}) }));
      toast("Villa marked ready for the next guest");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const phaseBox = (room: any, idx: number, phase: "before" | "after") => {
    const list: string[] = room[phase];
    return (
      <View style={{ flex: 1, gap: spacing.xs }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: phase === "before" ? colors.warning : colors.success }} />
          <Txt v="label">{phase}</Txt>
          <Txt v="caption">({list.length})</Txt>
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {list.map((mid, k) => <MediaThumb key={mid} testID={`room-${idx}-${phase}-media-${k}`} id={mid} size={64} onRemove={done ? undefined : () => removeMedia(idx, phase, mid)} />)}
          {!done ? (
            <Pressable testID={`room-${idx}-${phase}-add`} onPress={() => setTarget({ idx, phase })} style={({ pressed }) => ({ width: 64, height: 64, borderRadius: radius.sm + 2, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", backgroundColor: pressed ? colors.brandTertiary : colors.surfaceSecondary })}>
              <Icon name="camera-outline" size={22} color={colors.brandPrimary} />
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={c.property_name} subtitle={`Checkout cleaning · ${fmtDate(c.date)}`} right={<Badge testID="cleaning-status-badge" label={done ? "Ready" : c.status === "in_progress" ? "In progress" : "Pending"} tone={done ? "success" : "warning"} />} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + (done ? spacing.xl : 100) }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
        <Card style={{ gap: spacing.sm }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Txt v="subtitle" testID="cleaning-progress">{c.rooms_done}/{c.rooms_total} rooms documented</Txt>
            <Txt v="caption">{c.assigned_name ?? "Unassigned"}</Txt>
          </View>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceSecondary, overflow: "hidden" }}>
            <View style={{ width: `${c.rooms_total ? (c.rooms_done / c.rooms_total) * 100 : 0}%`, height: "100%", backgroundColor: done ? colors.success : colors.brandPrimary }} />
          </View>
          <Txt v="caption">{done ? `Completed ${fmtDate(c.completed_at)}` : "Photograph each room before you start, then again after cleaning & setting up."}</Txt>
        </Card>

        {isAdmin && !done ? (
          <Card style={{ gap: spacing.sm }}>
            <Txt v="label">Assign cleaner</Txt>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {(staff.data ?? []).filter((u) => u.role === "cleaner").map((u) => <Chip key={u.id} testID={`assign-${u.id}`} label={u.name} selected={c.assigned_to === u.id} onPress={() => assign(u.id)} />)}
            </View>
          </Card>
        ) : null}

        {c.rooms.map((room: any, idx: number) => {
          const ok = room.before.length && room.after.length;
          return (
            <Animated.View key={idx} entering={FadeInDown.delay(idx * 40)}>
              <Card testID={`room-card-${idx}`} style={{ gap: spacing.md }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Icon name={ok ? "checkmark-circle" : "ellipse-outline"} size={20} color={ok ? colors.success : colors.borderStrong} />
                  <Txt v="subtitle" style={{ flex: 1 }}>{room.name}</Txt>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.md }}>
                  {phaseBox(room, idx, "before")}
                  <View style={{ width: 1, backgroundColor: colors.divider }} />
                  {phaseBox(room, idx, "after")}
                </View>
              </Card>
            </Animated.View>
          );
        })}

        {!done ? (
          <Input testID="cleaning-notes-input" label="Notes (damages, missing items, maintenance)" multiline value={notes ?? c.notes ?? ""} onChangeText={setNotes} />
        ) : c.notes ? (
          <Card><Txt v="label">Notes</Txt><Txt v="body">{c.notes}</Txt></Card>
        ) : null}
      </ScrollView>
      {!done ? (
        <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16 }}>
          <Button testID="cleaning-complete-button" icon="checkmark-done" title={c.rooms_done === c.rooms_total ? "Mark ready for next guest" : `Document ${c.rooms_total - c.rooms_done} more room${c.rooms_total - c.rooms_done === 1 ? "" : "s"}`} disabled={c.rooms_done !== c.rooms_total} onPress={complete} loading={submitting} />
        </View>
      ) : null}
      <CaptureSheet visible={!!target} onClose={() => setTarget(null)} purpose={target ? `Take a ${target.phase} photo of ${c.rooms[target.idx]?.name} so the condition is on record.` : ""} onUploaded={(m) => addMedia(m.map((x) => x.id)).catch((e) => toast(e.message, "error"))} />
    </View>
  );
}
