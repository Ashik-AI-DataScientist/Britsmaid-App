import React, { useCallback, useEffect, useRef, useState } from "react";
import { Platform, Pressable, ScrollView, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Button, Card, Chip, Header, Input, Txt, useToast } from "@/src/ui";
import { spacing } from "@/src/theme";
import { request } from "@/src/api";

// Guest capability is kept in memory and sent only in the Authorization header.

export default function GuestCheckIn() {
  const toast = useToast();
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [guestNumber, setGuestNumber] = useState("1");
  const [kind, setKind] = useState("national_id");
  const [expiry, setExpiry] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState("");
  const [uploadError, setUploadError] = useState("");
  const picking = useRef(false);
  const attempt = useRef(0);
  const [waitingForPicker, setWaitingForPicker] = useState(false);
  useEffect(() => () => { attempt.current++; }, []);
  const loadToken = useCallback(async (invitationToken: string) => {
    setBusy(true);
    try {
      const next = await request<any>("/guest/check-in", { authorization: invitationToken.trim() });
      setStatus(next); setError("");
      const available = Array.from({ length: next.guests }, (_, i) => i + 1).find(number =>
        !next.documents.some((d: any) => d.guest_number === number && ["pending", "verified"].includes(d.status)));
      setGuestNumber(available ? String(available) : "");
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const invitationToken = new URLSearchParams(window.location.hash.slice(1)).get("invite") ?? "";
    if (!invitationToken) return;
    window.history.replaceState(null, "", window.location.pathname);
    Promise.resolve().then(() => { setToken(invitationToken); return loadToken(invitationToken); });
  }, [loadToken]);
  const load = () => loadToken(token);
  const upload = async (camera: boolean) => {
    if (picking.current) return;
    if (!consent || !name.trim()) return toast("Enter your name and give consent first", "error");
    if (!guestNumber) return toast("All guests already have an ID awaiting review or approved", "error");
    if ((kind !== "national_id" || expiry) && (!/^\d{4}-\d{2}-\d{2}$/.test(expiry) || expiry < status.check_out)) return toast("Enter an expiry date valid through check-out (YYYY-MM-DD)", "error");
    picking.current = true;
    const currentAttempt = ++attempt.current;
    setBusy(true); setUploadError("");
    try {
      if (Platform.OS !== "web" && camera && !(await ImagePicker.requestCameraPermissionsAsync()).granted) throw new Error("Camera access was declined. Enable it in phone settings, or choose a photo from your gallery.");
      // On web this call must run in the tap gesture, before any asynchronous work.
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 1, allowsMultipleSelection: false, cameraType: ImagePicker.CameraType.back };
      setWaitingForPicker(true);
      const result = await (camera ? ImagePicker.launchCameraAsync(options) : ImagePicker.launchImageLibraryAsync(options));
      if (currentAttempt === attempt.current) setWaitingForPicker(false);
      if (currentAttempt !== attempt.current || result.canceled || !result.assets?.length) return;
      const asset = result.assets[0];
      if (asset.fileSize && asset.fileSize > 8 * 1024 * 1024) throw new Error("Choose a JPEG or PNG photo smaller than 8 MB.");
      const form = new FormData();
      if (Platform.OS === "web") {
        const blob = await (await fetch(asset.uri)).blob();
        if (blob.size > 8 * 1024 * 1024) throw new Error("Choose a JPEG or PNG photo smaller than 8 MB.");
        form.append("file", blob, asset.fileName || "id.jpg");
      }
      else form.append("file", { uri: asset.uri, name: asset.fileName ?? "id.jpg", type: asset.mimeType ?? "image/jpeg" } as any);
      form.append("guest_name", name.trim()); form.append("document_type", kind);
      form.append("guest_number", guestNumber);
      form.append("expires_on", expiry); form.append("consent", "true");
      if (currentAttempt !== attempt.current) return;
      await request("/guest/documents", { method: "POST", form, authorization: token.trim() });
      setName(""); setConsent(false); await load(); toast("ID submitted for admin review");
    } catch (e: any) { if (currentAttempt === attempt.current) { setUploadError(e.message || "The ID photo could not be submitted. Please try again."); toast(e.message, "error"); } }
    finally { if (currentAttempt === attempt.current) { picking.current = false; setWaitingForPicker(false); setBusy(false); } }
  };
  return <View style={{ flex: 1 }}>
    <Header title="Guest check-in" subtitle="Private document submission" />
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
      <Card><Txt>Your ID is reviewed by a Britsmaid admin for this stay. Cleaners, supervisors and property owners cannot open these documents. Contact Britsmaid for document removal or retention details.</Txt></Card>
      {!status ? <Input label="Invitation code" value={token} onChangeText={setToken} autoCapitalize="none" secureTextEntry /> : null}
      <Button title={status ? "Refresh review status" : "Open invitation"} onPress={() => load()} disabled={busy || !token.trim()} />
      {error ? <Card><Txt>{error}</Txt><Button title="Try again" onPress={() => load()} disabled={busy} /></Card> : null}
      {status ? <>
        <Txt>Stay: {status.check_in} to {status.check_out}. Submit one document per guest.</Txt>
        <Txt>Document retention: {status.retention_days} days from upload.</Txt>
        {status.documents.map((d: any, i: number) => <Card key={i}><Txt>Guest {d.guest_number} · {d.guest_name}: {d.status}</Txt>{d.review_reason ? <Txt>{d.review_reason}</Txt> : null}</Card>)}
        {!guestNumber ? <Txt>All guest IDs are submitted. Refresh to see the admin review result. An admin must complete check-in after approving every guest.</Txt> : <>
        <Txt>Select the guest whose ID you are submitting:</Txt>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>{Array.from({ length: status.guests }, (_, i) => i + 1).map(number => {
          const locked = status.documents.some((d: any) => d.guest_number === number && ["pending", "verified"].includes(d.status));
          return <Button key={number} title={`Guest ${number}${locked ? " · submitted" : guestNumber === String(number) ? " · selected" : ""}`} disabled={locked || busy} variant={guestNumber === String(number) ? "primary" : "secondary"} onPress={() => { setGuestNumber(String(number)); setName(""); setConsent(false); }} />;
        })}</View>
        <Input label="Guest full name as shown on ID" value={name} onChangeText={setName} />
        <View style={{ gap: spacing.sm }}>{[["national_id", "National ID (Aadhaar / voter ID)"], ["passport", "Passport"], ["driving_licence", "Driving licence"]].map(([value, label]) => <Chip key={value} label={label} selected={kind === value} onPress={() => setKind(value)} />)}</View>
        <Input label={kind === "national_id" ? "Expiry YYYY-MM-DD (leave blank if none)" : "Expiry YYYY-MM-DD"} value={expiry} onChangeText={setExpiry} />
        <Txt>Use a clear JPEG or PNG up to 8MB. For Aadhaar, use a masked copy. Upload only your own ID.</Txt>
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: consent }} onPress={() => setConsent(!consent)} style={{ padding: spacing.md, borderWidth: 1, borderRadius: 10, flexDirection: "row", gap: spacing.sm }}>
          <Txt>{consent ? "☑" : "☐"}</Txt><View style={{ flex: 1 }}><Txt>I consent to private storage and admin review of my ID for this stay.</Txt></View>
        </Pressable>
        {uploadError ? <Card><View accessibilityRole="alert"><Txt>{uploadError}</Txt><Txt>Your ID has not been submitted. Check the message and try again.</Txt></View></Card> : null}
        <Button title="Take ID photo and submit" icon="camera" onPress={() => upload(true)} loading={busy} disabled={!consent || !name.trim() || busy} />
        <Button title="Choose ID photo from gallery and submit" icon="images" variant="secondary" onPress={() => upload(false)} disabled={!consent || !name.trim() || busy} />
        {Platform.OS === "web" && waitingForPicker ? <Button title="Camera or gallery cancelled? Return to options" variant="ghost" onPress={() => { attempt.current++; picking.current = false; setWaitingForPicker(false); setBusy(false); }} /> : null}
        </>}
      </> : null}
    </ScrollView>
  </View>;
}
