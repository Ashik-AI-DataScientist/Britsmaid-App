import React, { useEffect, useState } from "react";
import { Image, Linking, Modal, Platform, ScrollView, Share, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, authenticatedBlob } from "@/src/api";
import { Badge, Button, Card, ErrorState, Header, Input, Loading, Txt, useToast } from "@/src/ui";
import { fmtDate } from "@/src/format";
import { spacing } from "@/src/theme";

type Action = { action: string; title: string; document_id?: string };
export default function Guests() {
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [options, setOptions] = useState(false);
  const [history, setHistory] = useState(false);
  const [note, setNote] = useState("");
  const [action, setAction] = useState<Action | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [invitation, setInvitation] = useState<{ bookingId: string; url: string } | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [imageReady, setImageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const bookings = useQuery({ queryKey: ["guest-bookings"], queryFn: () => api.get<any[]>("/guest-bookings"), refetchInterval: 15000 });
  const docs = useQuery({ queryKey: ["guest-ids", selected], queryFn: () => api.get<any[]>(`/guest-ids?booking_id=${selected}`), enabled: !!selected, refetchInterval: 15000 });
  const b = bookings.data?.find(item => item.id === selected);
  useEffect(() => () => { if (image && Platform.OS === "web") URL.revokeObjectURL(image); }, [image]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); await Promise.all([bookings.refetch(), ...(selected ? [docs.refetch()] : [])]); }
    catch (e: any) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };
  const chooseAction = (next: Action) => { setAction(next); setNote(""); };
  const invite = async () => {
    const link = await api.post(`/bookings/${selected}/guest-link`);
    const origin = Platform.OS === "web" ? window.location.origin : process.env.EXPO_PUBLIC_GUEST_WEB_URL || "";
    setInvitation({ bookingId: selected!, url: origin ? `${origin}/guest-check-in#invite=${link.token}` : link.token });
  };
  return <View style={{ flex: 1 }}>
    <Header back title={b ? b.guest_name : "Guest check-in"} subtitle={b ? b.property_name : "Choose a stay to get started"} />
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
      {bookings.isLoading ? <Loading /> : bookings.isError ? <ErrorState message="Could not load stays" onRetry={bookings.refetch} /> : null}
      {!b ? <>
        <Txt>Open a stay, review the IDs, then check in. Admins can make an exception with a note.</Txt>
        {bookings.data?.length === 0 ? <Txt>No upcoming stays. Add a booking first.</Txt> : null}
        {(bookings.data ?? []).map(stay => <Card key={stay.id} style={{ gap: spacing.sm }}>
          <Txt v="subtitle">{stay.guest_name}</Txt>
          <Txt>{stay.property_name} · {fmtDate(stay.check_in)} – {fmtDate(stay.check_out)}</Txt>
          <Badge label={stay.guest_checked_in_at ? "Checked in" : `${stay.verified_guests}/${stay.guests} IDs approved`} tone={stay.guest_checked_in_at ? "success" : "warning"} />
          <Button title="Open stay" onPress={() => { setSelected(stay.id); setOptions(false); setAction(null); setImage(null); setHistory(false); }} />
        </Card>)}
      </> : <>
        <Button title="All stays" variant="ghost" onPress={() => { setSelected(null); setImage(null); setAction(null); }} />
        <Card style={{ gap: spacing.sm }}>
          <Txt>{fmtDate(b.check_in)} – {fmtDate(b.check_out)} · {b.guests} guest{b.guests === 1 ? "" : "s"}</Txt>
          <Txt v="subtitle">{b.guest_checked_in_at ? "Checked in" : `${b.verified_guests} of ${b.guests} IDs approved`}</Txt>
          {b.guest_checked_in_at ? <Txt>{new Date(b.guest_checked_in_at).toLocaleString()}</Txt> : <>
            <Button title="Get guest upload link" disabled={busy} onPress={() => run(invite)} />
            {invitation && invitation.bookingId === b.id ? <>
              <Text selectable style={{ overflowWrap: "anywhere" } as any}>{invitation.url}</Text>
              <Button title="Open upload form" onPress={() => Linking.openURL(invitation!.url)} />
              <Button title="Share link" variant="secondary" onPress={() => run(async () => { await Share.share({ message: invitation!.url }); })} />
            </> : <Txt>Guests use the link to send their ID photos.</Txt>}
            <Button title="Check in" disabled={busy} onPress={() => b.can_check_in ? run(async () => { await api.post(`/bookings/${b.id}/check-in`); setInvitation(null); toast("Checked in"); }) : chooseAction({ action: "check_in", title: "Check in with an exception" })} />
            {!b.can_check_in ? <Txt>{b.check_in_reason}. You can check in with an admin note.</Txt> : null}
          </>}
        </Card>
        <Txt v="subtitle">Guest IDs</Txt>
        {docs.isLoading ? <Loading /> : docs.isError ? <ErrorState message="Could not load IDs" onRetry={docs.refetch} /> : null}
        {docs.data?.length === 0 ? <Txt>No IDs yet. Get an upload link above, or check in with an exception.</Txt> : null}
        {(docs.data ?? []).map(d => <Card key={d.id} style={{ gap: spacing.sm }}>
          <Txt v="subtitle">{d.guest_name} · Guest {d.guest_number}</Txt>
          <Badge label={d.status === "verified" ? "Approved" : d.status === "rejected" ? "Needs a new photo" : "Needs review"} tone={d.status === "verified" ? "success" : "warning"} />
          {d.review_reason ? <Txt>{d.review_reason}</Txt> : null}
          <Button title="View ID" disabled={busy} onPress={() => run(async () => {
            setImage(null); setImageReady(false); setImageId(d.id);
            const blob = await authenticatedBlob(`/guest-ids/${d.id}/image`);
            if (Platform.OS === "web") setImage(URL.createObjectURL(blob));
            else { const reader = new FileReader(); reader.onload = () => setImage(String(reader.result)); reader.readAsDataURL(blob); }
          })} />
          {image && imageId === d.id ? <>
            <Image source={{ uri: image }} style={{ width: "100%", height: 320 }} resizeMode="contain" onLoad={() => setImageReady(true)} onError={() => { setImageReady(false); toast("Cannot display image. Try again.", "error"); }} />
            <Txt>{d.document_type.replace(/_/g, " ")} · {d.expires_on === "9999-12-31" ? "No expiry declared" : `Expires ${d.expires_on}`}</Txt>
            <Button title="Close image" variant="ghost" onPress={() => setImage(null)} />
          </> : null}
          {d.status === "pending" && !b.guest_checked_in_at ? <>
            <Button title="Approve ID" disabled={busy} onPress={() => imageId === d.id && image && imageReady ? run(async () => { await api.post(`/guest-ids/${d.id}/review`, { status: "verified" }); setImage(null); }) : chooseAction({ action: "approve_id", document_id: d.id, title: "Approve ID without opening it" })} />
            {imageId === d.id && image && imageReady ? <>
              <Input label="Reason to request a new photo" value={reasons[d.id] ?? ""} onChangeText={value => setReasons(previous => ({ ...previous, [d.id]: value }))} />
              <Button title="Request new photo" variant="secondary" disabled={busy || !reasons[d.id]?.trim()} onPress={() => run(async () => { await api.post(`/guest-ids/${d.id}/review`, { status: "rejected", reason: reasons[d.id] }); setImage(null); })} />
            </> : null}
          </> : null}
          {options ? <>
            {d.status !== "pending" ? <Button title="Undo ID decision" variant="secondary" disabled={busy} onPress={() => chooseAction({ action: "reset_id", document_id: d.id, title: "Return this ID to review" })} /> : null}
            <Button title="Reject ID with a note" variant="ghost" disabled={busy} onPress={() => chooseAction({ action: "reject_id", document_id: d.id, title: "Reject this ID" })} />
          </> : null}
        </Card>)}
        <Button title={options ? "Hide admin options" : "Admin options"} variant="ghost" onPress={() => setOptions(!options)} />
        {options ? <Card style={{ gap: spacing.sm }}>
          {b.guest_checked_in_at ? <Button title="Undo check-in" variant="secondary" disabled={busy} onPress={() => chooseAction({ action: "undo_check_in", title: "Undo this check-in" })} /> : <Button title="Disable upload link" variant="secondary" disabled={busy} onPress={() => run(async () => { await api.del(`/bookings/${b.id}/guest-link`); setInvitation(null); toast("Link disabled"); })} />}
          <Button title={history ? "Hide history" : "View admin history"} variant="ghost" onPress={() => setHistory(!history)} />
          {history ? b.admin_history?.length ? b.admin_history.slice().reverse().map((event: any, i: number) => <View key={i}><Txt>{event.action.replace(/_/g, " ")} · {event.actor_name ?? "Admin"}</Txt><Txt>{event.note}</Txt><Txt v="caption">{new Date(event.at).toLocaleString()}</Txt></View>) : <Txt>No admin exceptions recorded.</Txt> : null}
        </Card> : null}
        {action ? <Modal transparent visible onRequestClose={() => setAction(null)} animationType="fade"><View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: spacing.lg }}><ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center" }}><Card testID="guest-admin-action" style={{ gap: spacing.sm }}>
          <Txt v="subtitle">{action.title}</Txt>
          <Txt>{action.action === "check_in" ? "This skips missing ID approvals or the arrival date. It records an exception; it does not verify guest IDs." : "Your reason and the previous decision will be kept in history."}</Txt>
          <Input testID="guest-admin-note" label="Reason (required)" value={note} onChangeText={setNote} multiline />
          <Button testID="guest-admin-save" title="Save with note" disabled={busy || !note.trim()} onPress={() => run(async () => { await api.post(`/bookings/${b.id}/guest-admin-action`, { action: action.action, document_id: action.document_id, note }); setAction(null); setImage(null); setInvitation(null); toast("Admin action saved"); })} />
          <Button title="Cancel" variant="ghost" onPress={() => setAction(null)} />
        </Card></ScrollView></View></Modal> : null}
      </>}
    </ScrollView>
  </View>;
}
