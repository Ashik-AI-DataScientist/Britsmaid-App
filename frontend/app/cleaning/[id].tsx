import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { CaptureTarget } from "@/src/capture-workflow";
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
  const canReview = isAdmin || user?.role === "supervisor";
  const q = useQuery({ queryKey: ["cleaning-session", id], queryFn: () => api.get(`/cleaning/${id}`) });
  const staff = useQuery({ queryKey: ["cleaning-team"], queryFn: () => api.get<any[]>("/cleaning-team"), enabled: canReview });
  const [target, setTarget] = useState<{ idx: number; phase: "before" | "after" } | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [adminOptions, setAdminOptions] = useState(false);
  const [adminAction, setAdminAction] = useState<"reopen" | "complete" | "reassign">("reopen");
  const [adminNote, setAdminNote] = useState("");
  const [adminAssignee, setAdminAssignee] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [activeRoom, setActiveRoom] = useState(0);

  if (q.isLoading) return <Loading label="Loading task details..." />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Cleaning" /><ErrorState message="Could not load task details" onRetry={q.refetch} /></View>;
  const c = q.data;
  const done = c.status === "cancelled" || c.status === "completed" || c.status === "awaiting_review" || user?.role === "owner";
  const refresh = (data: any) => {
    qc.setQueryData(["cleaning-session", id], data);
    qc.invalidateQueries({ queryKey: ["cleaning"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const addMedia = async (ids: string[], destination: CaptureTarget) => {
    if (destination.taskId !== id || destination.roomIndex === undefined || !destination.phase) throw new Error("Return to the original task to save this photo.");
    let data = c;
    for (const mid of ids) data = await api.post(`/cleaning/${destination.taskId}/rooms/${destination.roomIndex}/media`, {
      phase: destination.phase, media_id: mid, room_name: destination.roomName, expected_revision: destination.revision
    });
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
      toast("Cleaning submitted for supervisor review");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const saveNotes = async () => {
    if (submitting || notes === null) return;
    setSubmitting(true);
    try {
      refresh(await api.put(`/cleaning/${id}`, { notes }));
      setNotes(null);
      toast("Notes saved to this task");
    } catch (e: any) { toast(e.message, "error"); }
    finally { setSubmitting(false); }
  };

  const review = async (approved: boolean) => {
    setSubmitting(true);
    try { refresh(await api.post(`/cleaning/${id}/review`, { approved, notes: notes ?? "" })); setNotes(null); }
    catch (e: any) { toast(e.message, "error"); }
    finally { setSubmitting(false); }
  };
  const saveAdminAction = async () => {
    setSubmitting(true);
    try {
      refresh(await api.post(`/cleaning/${id}/admin-action`, { action: adminAction, note: adminNote, assigned_to: adminAssignee }));
      setAdminNote(""); setAdminOptions(false); setNotes(null); setAdminAssignee(null);
      toast(adminAction === "complete" ? "Marked complete with admin note" : "Cleaning reopened and ready to assign");
    } catch (e: any) { toast(e.message, "error"); }
    finally { setSubmitting(false); }
  };
  const toggleCheck = async (idx: number, room: any, item: string) => {
    const checked: string[] = room.checked ?? [];
    try { refresh(await api.put(`/cleaning/${id}/rooms/${idx}/checklist`, { checked: checked.includes(item) ? checked.filter(x => x !== item) : [...checked, item] })); }
    catch (e: any) { toast(e.message, "error"); }
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
            <Pressable testID={`room-${idx}-${phase}-add`} accessibilityLabel={`Add ${phase} photo of ${room.name}`} onPress={() => setTarget({ idx, phase })} style={({ pressed }) => ({ width: 82, minHeight: 76, paddingVertical: 8, gap: 4, borderRadius: radius.sm + 2, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", backgroundColor: pressed ? colors.brandTertiary : colors.surfaceSecondary })}>
              <Icon name="camera-outline" size={22} color={colors.brandPrimary} /><Txt v="caption">Add photo</Txt>
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={c.property_name} subtitle={`Checkout cleaning · ${fmtDate(c.date)}`} right={<Badge testID="cleaning-status-badge" label={c.status === "completed" ? "Ready" : c.status === "awaiting_review" ? "Needs review" : c.status === "in_progress" ? "In progress" : "Pending"} tone={done ? "success" : "warning"} />} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + (done ? spacing.xl : 100) }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
        <Card style={{ gap: spacing.sm }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Txt v="subtitle" testID="cleaning-progress">{c.rooms_done}/{c.rooms_total} rooms documented</Txt>
            <Txt v="caption">{c.assigned_name ?? "Unassigned"}</Txt>
          </View>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceSecondary, overflow: "hidden" }}>
            <View style={{ width: `${c.rooms_total ? (c.rooms_done / c.rooms_total) * 100 : 0}%`, height: "100%", backgroundColor: done ? colors.success : colors.brandPrimary }} />
          </View>
          <Txt v="caption">{c.status === "awaiting_review" ? "Submitted for supervisor review" : done ? (c.completed_at ? `Completed ${fmtDate(c.completed_at)}` : "Read-only cleaning record") : "Photograph each room before you start, then again after cleaning & setting up."}</Txt>
        </Card>

        {isAdmin ? <Card style={{ gap: spacing.sm }}>
          <Button title={adminOptions ? "Close admin options" : "Admin: reopen, reassign or complete"} variant="secondary" onPress={() => { setAdminOptions(!adminOptions); setAdminAssignee(c.assigned_to ?? null); setAdminAction(c.status === "completed" ? "reopen" : "complete"); }} />
          {adminOptions ? <>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {([ ["reopen", "Reopen cleaning"], ["reassign", "Send to another cleaner"], ["complete", "Mark complete"] ] as const).map(([value, label]) => <Chip key={value} label={label} selected={adminAction === value} onPress={() => setAdminAction(value)} />)}
            </View>
            <Txt>{adminAction === "complete" ? "Complete this task even if photos, checklists or supervisor review are missing." : "Send this task back to To do. Previous photos and checklists stay in history; the cleaner starts a fresh round."}</Txt>
            {adminAction !== "complete" ? <>
              <Txt v="label">Cleaner</Txt>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                {(staff.data ?? []).filter(u => (u.property_ids ?? []).includes(c.property_id)).map(u => <Chip key={u.id} label={u.name} selected={adminAssignee === u.id} onPress={() => setAdminAssignee(u.id)} />)}
              </View>
              {!adminAssignee ? <Txt>No cleaner selected. Reopen keeps this task unassigned.</Txt> : null}
            </> : null}
            <Input testID="cleaning-admin-note" label="Reason (required)" value={adminNote} onChangeText={setAdminNote} multiline />
            <Button testID="cleaning-admin-save" title="Save with note" disabled={submitting || !adminNote.trim() || (adminAction === "reassign" && !adminAssignee)} onPress={saveAdminAction} />
          </> : null}
          <Button title={showHistory ? "Hide admin history" : "View admin history"} variant="ghost" onPress={() => setShowHistory(!showHistory)} />
          {showHistory ? c.admin_history?.length ? c.admin_history.slice().reverse().map((event: any, i: number) => <View key={i} style={{ gap: spacing.xs }}>
            <Txt>{event.action} · {event.actor_name ?? "Admin"} · {new Date(event.at).toLocaleString()}</Txt>
            <Txt>{event.note}</Txt>
            <Txt v="caption">Previous status: {event.before?.status}</Txt>
            {(event.before?.rooms ?? []).map((room: any, idx: number) => <View key={idx}><Txt v="caption">{room.name} · {(room.checked ?? []).length} checklist items recorded</Txt><View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>{[...(room.before ?? []), ...(room.after ?? [])].map((mid: string, k: number) => <MediaThumb key={`${mid}-${k}`} id={mid} size={64} />)}</View></View>)}
          </View>) : <Txt>No admin actions yet.</Txt> : null}
        </Card> : null}

        {canReview && !done ? (
          <Card style={{ gap: spacing.sm }}>
            <Txt v="label">Assign cleaner</Txt>
            {staff.isLoading ? <Loading label="Loading cleaners..." /> : staff.isError ? <ErrorState message="Could not load cleaners" onRetry={staff.refetch} /> : !(staff.data ?? []).some((u: any) => (u.property_ids ?? []).includes(c.property_id)) ? <Txt>No cleaner has access to this property yet. Ask the admin to assign one.</Txt> : null}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {(staff.data ?? []).filter((u) => (u.property_ids ?? []).includes(c.property_id)).map((u) => <Chip key={u.id} testID={`assign-${u.id}`} label={u.name} selected={c.assigned_to === u.id} onPress={() => assign(u.id).catch(e => toast(e.message, "error"))} />)}
            </View>
          </Card>
        ) : null}

        {c.review_notes ? <Card><Txt v="label">Supervisor feedback</Txt><Txt>{c.review_notes}</Txt></Card> : null}
        {canReview && c.status === "awaiting_review" ? (
          <Card style={{ gap: spacing.sm }}>
            <Input label="Review notes (required for rework)" value={notes ?? ""} onChangeText={setNotes} multiline />
            <Button title="Approve: ready for guest" onPress={() => review(true)} loading={submitting} />
            <Button title="Send back to cleaner" onPress={() => review(false)} disabled={submitting || !notes?.trim()} />
          </Card>
        ) : null}
        {!canReview && !done && c.rooms.length ? <Card style={{ gap: spacing.sm }}><Txt v="subtitle">Room {activeRoom + 1} of {c.rooms.length}</Txt><Txt>1. Add a before photo · 2. Add an after photo · 3. Tick the checks</Txt><View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>{c.rooms.map((room: any, idx: number) => <Chip key={idx} label={room.name} selected={activeRoom === idx} onPress={() => setActiveRoom(idx)} />)}</View></Card> : null}
        {c.rooms.map((room: any, idx: number) => {
          if (!canReview && !done && idx !== activeRoom) return null;
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
                <Txt v="label">Room checklist</Txt>
                {(c.checklist_items ?? []).map((item: string) => (
                  <Chip key={item} label={item} selected={(room.checked ?? []).includes(item)}
                    onPress={() => { if (!done) toggleCheck(idx, room, item); }} />
                ))}
              </Card>
            </Animated.View>
          );
        })}
        {!canReview && !done && activeRoom < c.rooms.length - 1 ? <Button title="Next room" variant="secondary" onPress={() => setActiveRoom(activeRoom + 1)} /> : null}
        {!done ? <Card><Txt v="label">Still needed before you send</Txt>{c.rooms.filter((r: any) => !r.before.length || !r.after.length || (r.checked ?? []).length !== (c.checklist_items ?? []).length).map((r: any) => <Txt key={r.name}>{r.name}: {[!r.before.length ? "before photo" : "", !r.after.length ? "after photo" : "", (r.checked ?? []).length !== (c.checklist_items ?? []).length ? "finish checks" : ""].filter(Boolean).join(", ")}</Txt>)}{c.rooms.every((r: any) => r.before.length && r.after.length && (r.checked ?? []).length === (c.checklist_items ?? []).length) ? <Txt>Everything is saved. You can send this for review.</Txt> : null}</Card> : null}

        {!done ? (
          <Card style={{ gap: spacing.sm }}>
            <Input testID="cleaning-notes-input" label="Notes (damages, missing items, maintenance)" multiline editable={!submitting} value={notes ?? c.notes ?? ""} onChangeText={setNotes} />
            <Txt v="caption">Save notes before leaving this task. Photos and checklist changes save separately.</Txt>
            <Button testID="cleaning-save-notes" title="Save notes" variant="secondary" loading={submitting} disabled={notes === null || notes === (c.notes ?? "")} onPress={saveNotes} />
          </Card>
        ) : c.notes ? (
          <Card><Txt v="label">Notes</Txt><Txt v="body">{c.notes}</Txt></Card>
        ) : null}
      </ScrollView>
      {!done ? (
        <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16 }}>
          <Button testID="cleaning-complete-button" icon="checkmark-done" title={c.rooms_done === c.rooms_total ? "Submit for supervisor review" : `Document ${c.rooms_total - c.rooms_done} more room${c.rooms_total - c.rooms_done === 1 ? "" : "s"}`} disabled={!c.rooms_total || c.rooms_done !== c.rooms_total || c.rooms.some((r: any) => (r.checked ?? []).length !== (c.checklist_items ?? []).length)} onPress={complete} loading={submitting} />
        </View>
      ) : null}
      <CaptureSheet visible={!!target} onClose={() => setTarget(null)} destination={{ key: `${id}:${target?.idx}:${target?.phase}`, label: target ? `${c.property_name} / ${c.rooms[target.idx]?.name} / ${target.phase} cleaning` : c.property_name, taskId: id, roomIndex: target?.idx, roomName: target ? c.rooms[target.idx]?.name : undefined, phase: target?.phase, revision: c.revision ?? 0 }} onRestore={(d) => { if (d.taskId === id && d.roomIndex !== undefined && d.phase) setTarget({ idx: d.roomIndex, phase: d.phase }); }} purpose={target ? `Take a ${target.phase} photo of ${c.rooms[target.idx]?.name} so the condition is on record.` : ""} onUploaded={(m, d) => addMedia(m.map((x) => x.id), d)} />
    </View>
  );
}
