import React, { useEffect, useState } from "react";
import { Image, Platform, ScrollView, Share, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, authenticatedBlob } from "@/src/api";
import { Button, Card, ConfirmSheet, ErrorState, Header, Input, Loading, Txt, useToast } from "@/src/ui";
import { spacing } from "@/src/theme";

export default function Guests() {
  const toast = useToast();
  const q = useQuery({ queryKey: ["guest-ids"], queryFn: () => api.get<any[]>("/guest-ids") });
  const bookings = useQuery({ queryKey: ["guest-bookings"], queryFn: () => api.get<any[]>("/bookings") });
  const [reason, setReason] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const audit = useQuery({ queryKey: ["guest-id-audit"], queryFn: () => api.get<any[]>("/guest-id-audit"), enabled: showAudit });
  useEffect(() => () => { if (image && Platform.OS === "web") URL.revokeObjectURL(image); }, [image]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try { await action(); await q.refetch(); }
    catch (e: any) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };
  const invite = async (id: string) => {
    const link = await api.post(`/bookings/${id}/guest-link`);
    const origin = process.env.EXPO_PUBLIC_GUEST_WEB_URL || (Platform.OS === "web" ? window.location.origin : "");
    await Share.share({ message: origin ? `Submit your ID for admin review: ${origin}/guest-check-in#invite=${link.token}\nExpires: ${link.expires_at}` : `Open Britsmaid guest check-in and enter this invitation code: ${link.token}\nExpires: ${link.expires_at}` });
  };
  return <View style={{ flex: 1 }}>
    <Header back title="Guest IDs & check-in" subtitle="Admin review · documents stay private" />
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
      <Card><Txt>Review the original document, guest name, validity and match to the person arriving before approving. This is manual review; automated authenticity verification is not enabled.</Txt></Card>
      <Txt v="subtitle">Booking invitations</Txt>
      {bookings.isError ? <ErrorState message="Could not load bookings" onRetry={bookings.refetch} /> : null}
      {(bookings.data ?? []).filter(b => b.status === "confirmed" && !b.guest_checked_in_at).map(b => <Card key={b.id} style={{ gap: spacing.sm }}>
        <Txt>{b.guest_name} · {b.check_in} to {b.check_out} · {b.guests} guests</Txt>
        <Button title="Create / replace guest invitation" onPress={() => run(() => invite(b.id))} disabled={busy} />
        <Button title="Revoke invitation" onPress={() => run(async () => { await api.del(`/bookings/${b.id}/guest-link`); toast("Invitation revoked"); })} disabled={busy} />
        <Button title="Check in verified guests" onPress={() => run(async () => { await api.post(`/bookings/${b.id}/check-in`); await bookings.refetch(); toast("Guests checked in"); })} disabled={busy} />
      </Card>)}
      <Txt v="subtitle">Documents</Txt>
      <Input label="Rejection reason" value={reason} onChangeText={setReason} multiline />
      {q.isLoading ? <Loading /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : null}
      {(q.data ?? []).map(d => <Card key={d.id} style={{ gap: spacing.sm }}>
        <Txt>Guest {d.guest_number} · {d.guest_name} · {d.document_type} · {d.status}</Txt>
        <Txt>ID expiry: {d.expires_on === "9999-12-31" ? "No expiry declared" : d.expires_on}</Txt>
        <Txt>Booking: {d.booking_id} · Retained until: {d.delete_after.slice(0, 10)}</Txt>
        <Button title="Open private ID image" disabled={busy} onPress={() => run(async () => {
          const blob = await authenticatedBlob(`/guest-ids/${d.id}/image`);
          setImageId(d.id);
          if (Platform.OS === "web") setImage(URL.createObjectURL(blob));
          else {
            const reader = new FileReader();
            reader.onload = () => setImage(String(reader.result)); reader.readAsDataURL(blob);
          }
        })} />
        {image && imageId === d.id ? <><Image source={{ uri: image }} style={{ width: "100%", height: 400 }} resizeMode="contain" /><Button title="Close ID" onPress={() => setImage(null)} /></> : null}
        {d.status === "pending" ? <>
          <Button title="Approve after reviewing ID and guest" disabled={busy || imageId !== d.id || !image} onPress={() => run(async () => { await api.post(`/guest-ids/${d.id}/review`, { status: "verified" }); setImage(null); })} />
          <Button title="Reject with reason" disabled={busy || !reason.trim()} onPress={() => run(async () => { await api.post(`/guest-ids/${d.id}/review`, { status: "rejected", reason }); })} />
        </> : null}
        <Button title="Delete this ID permanently" disabled={busy} onPress={() => setRemoveId(d.id)} />
      </Card>)}
      <Button title="Purge IDs past retention date" disabled={busy} onPress={() => run(async () => { const result = await api.post("/guest-ids/purge-expired"); toast(`${result.deleted} expired IDs deleted`); })} />
      <Button title={showAudit ? "Hide document access log" : "Show document access log"} onPress={() => { setShowAudit(!showAudit); audit.refetch(); }} />
      {showAudit ? (audit.data ?? []).map(event => <Card key={event.id}><Txt>{event.action} · {event.at}</Txt><Txt>Actor: {event.actor_id} · Booking: {event.booking_id}</Txt></Card>) : null}
    </ScrollView>
    <ConfirmSheet visible={!!removeId} title="Delete guest ID?" message="The stored ID image will be permanently removed. Its access audit trail will remain." confirmLabel="Delete ID" onClose={() => setRemoveId(null)} onConfirm={() => run(async () => { if (removeId) await api.del(`/guest-ids/${removeId}`); setImage(null); setRemoveId(null); })} />
  </View>;
}

