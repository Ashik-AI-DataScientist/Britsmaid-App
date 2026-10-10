import React, { useEffect, useState } from "react";
import { Platform, ScrollView, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Button, Card, Chip, Header, Input, Txt, useToast } from "@/src/ui";
import { spacing } from "@/src/theme";

// Guest capability is kept in memory and sent only in the Authorization header.
const base = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;
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
  useEffect(() => {
    if (Platform.OS === "web") {
      const t = new URLSearchParams(window.location.hash.slice(1)).get("invite") ?? "";
      setToken(t);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  const call = async (path: string, form?: FormData) => {
    const r = await fetch(base + path, { method: form ? "POST" : "GET", headers: { Authorization: `Bearer ${token}` }, body: form });
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please check your details");
    return data;
  };
  const load = async () => {
    try { setStatus(await call("/guest/check-in")); setError(""); }
    catch (e: any) { setError(e.message); }
  };
  const upload = async () => {
    if (!consent || !name.trim()) return toast("Enter your name and give consent first", "error");
    setBusy(true);
    try {
      if (Platform.OS !== "web" && !(await ImagePicker.requestMediaLibraryPermissionsAsync()).granted) throw new Error("Photo permission is required");
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 1, allowsMultipleSelection: false });
      if (result.canceled) return;
      const asset = result.assets[0];
      const form = new FormData();
      if (Platform.OS === "web") form.append("file", await (await fetch(asset.uri)).blob(), "id.jpg");
      else form.append("file", { uri: asset.uri, name: asset.fileName ?? "id.jpg", type: asset.mimeType ?? "image/jpeg" } as any);
      form.append("guest_name", name.trim()); form.append("document_type", kind);
      form.append("guest_number", guestNumber);
      form.append("expires_on", expiry); form.append("consent", "true");
      await call("/guest/documents", form);
      setName(""); setConsent(false); await load(); toast("ID submitted for admin review");
    } catch (e: any) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };
  return <View style={{ flex: 1 }}>
    <Header title="Guest check-in" subtitle="Private document submission" />
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
      <Card><Txt>Your ID is reviewed by a Britsmaid admin for this stay. Cleaners, supervisors and property owners cannot open these documents. Contact Britsmaid for document removal or retention details.</Txt></Card>
      {!status ? <Input label="Invitation code" value={token} onChangeText={setToken} autoCapitalize="none" secureTextEntry /> : null}
      <Button title={status ? "Refresh review status" : "Open invitation"} onPress={load} />
      {error ? <Txt>{error}</Txt> : null}
      {status ? <>
        <Txt>Stay: {status.check_in} to {status.check_out}. Submit one document per guest.</Txt>
        <Txt>Document retention: {status.retention_days} days from upload.</Txt>
        {status.documents.map((d: any, i: number) => <Card key={i}><Txt>Guest {d.guest_number} · {d.guest_name}: {d.status}</Txt>{d.review_reason ? <Txt>{d.review_reason}</Txt> : null}</Card>)}
        <Input label="Guest full name as shown on ID" value={name} onChangeText={setName} />
        <Input label={`Guest number (1 to ${status.guests})`} value={guestNumber} onChangeText={setGuestNumber} keyboardType="number-pad" />
        <View style={{ gap: spacing.sm }}>{[["national_id", "National ID (Aadhaar / voter ID)"], ["passport", "Passport"], ["driving_licence", "Driving licence"]].map(([value, label]) => <Chip key={value} label={label} selected={kind === value} onPress={() => setKind(value)} />)}</View>
        <Input label={kind === "national_id" ? "Expiry YYYY-MM-DD (leave blank if none)" : "Expiry YYYY-MM-DD"} value={expiry} onChangeText={setExpiry} />
        <Txt>Use a clear JPEG or PNG up to 8MB. For Aadhaar, use a masked copy. Upload only your own ID.</Txt>
        <Chip label="I consent to private storage and admin review of my ID for this stay" selected={consent} onPress={() => setConsent(!consent)} />
        <Button title="Choose ID photo and submit" onPress={upload} loading={busy} disabled={!consent || !name.trim()} />
      </> : null}
    </ScrollView>
  </View>;
}
