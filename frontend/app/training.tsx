import React, { useState } from "react";
import { Linking, RefreshControl, ScrollView, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button, Card, Chip, Empty, ErrorState, Header, Input, Loading, Txt, useToast } from "@/src/ui";
import { spacing, useTheme } from "@/src/theme";
const blank = { title: "", instructions: "", links: "", onboarding: false, refresher_days: "", due_days: "7" };
export default function TrainingScreen() {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const allowed = admin || user?.role === "cleaner";
  const { colors } = useTheme();
  const qc = useQueryClient(), toast = useToast();
  const assignments = useQuery({ queryKey: ["training-assignments", user?.id], queryFn: () => api.get<any[]>("/training/assignments"), enabled: allowed });
  const lessons = useQuery({ queryKey: ["training-lessons"], queryFn: () => api.get<any[]>("/training/lessons"), enabled: admin });
  const team = useQuery({ queryKey: ["training-team"], queryFn: () => api.get<any[]>("/users"), enabled: admin });
  const [edit, setEdit] = useState<string | null>(null), [form, setForm] = useState(blank);
  const [assign, setAssign] = useState<string | null>(null), [cleaners, setCleaners] = useState<string[]>([]), [all, setAll] = useState(false), [due, setDue] = useState("");
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const gate = React.useRef(false);
  const [tab, setTab] = useState("To do");
  const [confirmArchive, setConfirmArchive] = useState<string | null>(null);
  const mutate = async (action: () => Promise<unknown>, success: string, done?: () => void) => {
    if (gate.current) return;
    gate.current=true; setBusy(true); setError("");
    try { await action(); await qc.invalidateQueries({ queryKey: ["training-assignments"] }); await qc.invalidateQueries({ queryKey: ["training-lessons"] }); done?.(); toast(success); }
    catch(e:any) { setError(e.message); } finally { gate.current=false; setBusy(false); }
  };
  if (!allowed) return <View><Header back title="Training" /><ErrorState message="Training is available to cleaners and administrators." /></View>;
  const dateLabel = (value: string) => new Date(value).toLocaleString();
  const rows = (assignments.data ?? []).filter(x => tab === "History" ? x.status === "completed" : x.status !== "completed");
  return <View style={{ flex:1, backgroundColor:colors.surfaceSecondary }}><Header back title={admin ? "Cleaner training" : "My training"} subtitle="Read, practise, then acknowledge completion" />
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding:spacing.lg, paddingBottom:60, gap:spacing.md }} refreshControl={<RefreshControl refreshing={assignments.isRefetching} onRefresh={() => { assignments.refetch(); if(admin) { lessons.refetch(); team.refetch(); } }} />}>
      <Txt>Training reminders do not block urgent cleaning work. Dates below use your device timezone.</Txt>
      {error ? <Card><Txt color={colors.error}>{error}</Txt><Txt>Check the result and retry. Your form stays open.</Txt></Card> : null}
      {admin ? <>
        <Button title="Create lesson" disabled={busy} onPress={() => { if (edit) { setError("Save or cancel the open lesson first."); return; } setEdit("new"); setForm(blank); }} />
        {lessons.isLoading ? <Loading /> : lessons.isError ? <ErrorState message="Could not load lessons" onRetry={lessons.refetch} /> : null}
        {edit ? <Card style={{ gap:spacing.sm }}><Txt v="subtitle">{edit === "new" ? "New lesson draft" : "Edit draft"}</Txt>
          <Input label="Lesson title" value={form.title} onChangeText={v => setForm({...form,title:v})} />
          <Input label="Instructions" multiline value={form.instructions} onChangeText={v => setForm({...form,instructions:v})} />
          <Input label="Image or video HTTPS links (one per line)" multiline value={form.links} onChangeText={v => setForm({...form,links:v})} />
          <Chip label="Assign to new cleaners during onboarding" selected={form.onboarding} onPress={() => setForm({...form,onboarding:!form.onboarding})} />
          <Input label="Days allowed to finish" keyboardType="number-pad" value={form.due_days} onChangeText={v => setForm({...form,due_days:v})} />
          <Input label="Refresher interval in days (empty = none)" keyboardType="number-pad" value={form.refresher_days} onChangeText={v => setForm({...form,refresher_days:v})} />
          <Button title="Save draft" loading={busy} onPress={() => mutate(() => (edit === "new" ? api.post : api.put)(edit === "new" ? "/training/lessons" : `/training/lessons/${edit}`, { ...form, links:form.links.split("\n").map(x=>x.trim()).filter(Boolean), due_days: Number(form.due_days), refresher_days: form.refresher_days ? Number(form.refresher_days) : null }), "Draft saved; publish when approved", () => setEdit(null))} />
          <Button title="Discard form changes" variant="ghost" disabled={busy} onPress={() => setEdit(null)} />
        </Card> : null}
        {(lessons.data ?? []).map(l => <Card key={l.id} style={{ gap:spacing.sm }}><Txt v="subtitle">{l.draft.title}</Txt><Badge label={l.archived ? "Archived" : l.published ? `Published v${l.revision}` : "Draft"} />{l.published && Object.keys(l.draft).some(k => JSON.stringify(l.draft[k]) !== JSON.stringify(l.published[k])) ? <Txt>Draft changes are waiting. Publish to create a new lesson version; existing assignments keep their original instructions.</Txt> : null}<Txt v="caption">{l.published?.onboarding ? "Onboarding · " : ""}{l.published?.refresher_days ? `Refresh every ${l.published.refresher_days} days` : "No automatic refresher"}</Txt>
          {!l.archived ? <><Button title="Edit lesson" disabled={busy || !!edit} variant="secondary" onPress={() => { setEdit(l.id); setForm({...l.draft, links:l.draft.links.join("\n"), refresher_days:String(l.draft.refresher_days ?? ""), due_days:String(l.draft.due_days)}); }} />
          <Button title="Publish current draft" disabled={busy} onPress={() => mutate(()=>api.post(`/training/lessons/${l.id}/publish`),"Lesson published; existing assignments keep their original version")} />
          {l.published ? <Button title="Assign or reassign lesson" disabled={busy} variant="secondary" onPress={() => { setAssign(l.id); setCleaners([]); setAll(false); setDue(""); setRequestId(`assign_${Date.now()}_${Math.random().toString(36).slice(2)}`); }} /> : null}
          <Button title="Archive lesson" disabled={busy} variant="ghost" onPress={()=>setConfirmArchive(l.id)} />
          {confirmArchive === l.id ? <><Txt>Stop new assignments and refreshers? Existing records remain available.</Txt><Button title="Confirm archive" disabled={busy} variant="danger" onPress={()=>mutate(()=>api.post(`/training/lessons/${l.id}/archive`),"Archived",()=>setConfirmArchive(null))} /><Button title="Keep lesson" variant="ghost" onPress={()=>setConfirmArchive(null)} /></> : null}</> : null}
          {assign === l.id ? <View style={{gap:spacing.sm}}><Txt v="label">Who should learn this?</Txt>
            <Chip label="All active cleaners" selected={all} onPress={()=>setAll(!all)} />
            {team.isError ? <ErrorState message="Could not load cleaners" onRetry={team.refetch} /> : team.isLoading ? <Loading /> : !all ? (team.data ?? []).filter(c=>c.active && c.role === "cleaner").map(c=><Chip key={c.id} label={c.name} selected={cleaners.includes(c.id)} onPress={()=>setCleaners(cleaners.includes(c.id)?cleaners.filter(id=>id!==c.id):[...cleaners,c.id])} />) : null}
            <Input label="Due date YYYY-MM-DD (end of day, India time; optional)" value={due} onChangeText={setDue} />
            <Button title="Save assignments" loading={busy} onPress={()=>mutate(()=>api.post(`/training/lessons/${l.id}/assign`, { all_active:all, cleaner_ids:cleaners, due_on:due || null, request_id:requestId }),"Training assigned",()=>setAssign(null))} /><Button title="Cancel assignment" variant="ghost" disabled={busy} onPress={()=>setAssign(null)} />
          </View> : null}
        </Card>)}
        <Button title="Update refresher schedule" variant="secondary" loading={busy} onPress={()=>mutate(()=>api.post("/training/schedule"),"Refresher schedule updated")} />
      </> : null}
      <View style={{flexDirection:"row",gap:spacing.sm}}>{["To do","History"].map(t=><Chip key={t} label={t} selected={tab===t} onPress={()=>setTab(t)} />)}</View>
      {assignments.isLoading ? <Loading /> : assignments.isError ? <ErrorState message="Could not load training" onRetry={assignments.refetch} /> : !rows.length ? <Empty icon="book-outline" title={tab === "History" ? "No completed lessons yet" : "No training to do"} /> : rows.map(a=><Card key={a.id} style={{gap:spacing.sm}}>
        <Txt v="subtitle">{a.lesson.title}</Txt>{admin ? <Txt>{a.cleaner_name}</Txt> : null}<Badge label={a.status} tone={a.status === "overdue" ? "warning" : a.status === "completed" ? "success" : "neutral"} />
        <Txt v="caption">Version {a.lesson.revision} · {a.source} · Due {dateLabel(a.due_at)}</Txt>
        <Txt>{a.lesson.instructions}</Txt>
        {a.lesson.links.map((link:string,i:number)=><Button key={link} variant="secondary" title={`Open supporting image / video ${i+1}`} onPress={()=>Linking.openURL(link).catch(()=>setError("Could not open this training link."))} />)}
        {a.completed_at ? <Txt>Completed {dateLabel(a.completed_at)}</Txt> : !admin ? <Button title="I have read and completed this lesson" loading={busy} onPress={()=>mutate(()=>api.post(`/training/assignments/${a.id}/complete`),"Training completion saved")} /> : null}
      </Card>)}
    </ScrollView></View>;
}
