import React, { useState } from "react";
import { Platform, ScrollView, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, setToken, TOKEN_KEY } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { useAuth } from "@/src/auth";
import { Button, Card, ErrorState, Header, Input, Txt } from "@/src/ui";
import { spacing } from "@/src/theme";

export default function Settings() {
  const { user } = useAuth();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState("");
  const [recovery, setRecovery] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmProperty, setConfirmProperty] = useState("");
  const retention = useQuery({ queryKey: ["photo-retention"], queryFn: () => api.get<{ retention_days: number; properties: {property_id: string; name: string; enabled: boolean; eligible_files: number}[] }>("/system/photo-retention"), enabled: user?.role === "admin" });
  const mfa = useQuery({ queryKey: ["admin-mfa"], queryFn: () => api.get("/auth/mfa"), enabled: user?.role === "admin" });
  const services = useQuery({ queryKey: ["service-readiness"], queryFn: () => api.get("/system/readiness"), enabled: user?.role === "admin" });
  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  if (user?.role !== "admin") return <View><Header back title="Settings" /><Txt>Administrator access required.</Txt></View>;
  return <View style={{ flex: 1 }}><Header back title="Security & storage" />
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: 80, gap: spacing.lg }}>
      {error ? <ErrorState message={error} onRetry={() => setError("")} /> : null}
      {message ? <Card><Txt>{message}</Txt></Card> : null}
      <Card style={{ gap: spacing.md }}><Txt v="subtitle">Services and backups</Txt>
        {services.isError ? <ErrorState message="Could not check services" onRetry={services.refetch} /> : null}
        <Txt>Photo storage: {services.data?.media_provider ?? "Checking…"}</Txt>
        <Txt>Last verified backup: {services.data?.last_backup ?? "Not configured or not yet verified"}</Txt>
        <Txt>External monitoring: {services.data?.external_monitor_configured ? "Configured" : "Not activated"}</Txt>
        <Button title="Back up now" loading={busy} onPress={() => act(async () => { await api.post("/system/backups/run"); setMessage("Backup queued. Allow a few minutes, then refresh the service status."); await services.refetch(); })} />
        <Button title="Refresh service status" onPress={() => services.refetch()} />
      </Card>
      <Card style={{ gap: spacing.md }}><Txt v="subtitle">Cleaning photo retention</Txt>
        <Txt>Each cleaning photo stays for at least 45 days from its own upload time. Automatic deletion starts only when an admin turns it on for that property.</Txt>
        <Txt>Only before-and-after photos in completed cleaning logs can expire. Cleaning history, covers, damage evidence, reports, invoices and other records are kept. A photo hold protects a cleaning log.</Txt>
        <Txt>Deletion is permanent and includes the photo’s backup copy. Some older photos stay protected until their storage review is complete. Cleanup can run later than the expiry date, never earlier.</Txt>
        {retention.isError ? <ErrorState message="Could not preview photo cleanup" onRetry={retention.refetch} /> : null}
        <Input label="Reason for changing a property’s cleanup setting" value={note} onChangeText={setNote} multiline />
        <Button title="Refresh cleanup preview" onPress={() => retention.refetch()} />
        {retention.isPending ? <Txt>Loading property controls…</Txt> : null}
        {retention.data?.properties.map(prop => <View key={prop.property_id} style={{ gap: spacing.sm, paddingVertical: spacing.sm }}>
          <Txt v="subtitle">{prop.name}</Txt>
          <Txt>Automatic deletion: {prop.enabled ? "On" : "Off"}. Eligible cleaning photos: {prop.eligible_files}.</Txt>
          <Button title={prop.enabled ? `Turn off deletion for ${prop.name}` : `Turn on deletion for ${prop.name}`} variant="secondary" loading={busy} onPress={() => {
            if (!prop.enabled) { setConfirmProperty(prop.property_id); return; }
            act(async () => {
              if (!note.trim()) throw new Error("Add a reason before changing this property’s setting.");
              await api.put("/system/photo-retention", { property_id: prop.property_id, enabled: false, note });
              setConfirmProperty(""); setMessage(`Automatic deletion is off for ${prop.name}.`); await retention.refetch();
            });
          }} />
          {confirmProperty === prop.property_id && !prop.enabled ? <>
            <Txt>Allow permanent deletion of this property’s eligible cleaning photos and their recovery copies after 45 days? {prop.eligible_files} photos are eligible now. This cannot restore photos already deleted.</Txt>
            <Button title={`Confirm 45-day deletion for ${prop.name}`} variant="danger" loading={busy} onPress={() => act(async () => {
              if (!note.trim()) throw new Error("Add a reason before enabling permanent photo deletion.");
              await api.put("/system/photo-retention", { property_id: prop.property_id, enabled: true, note });
              setConfirmProperty(""); setMessage(`45-day cleaning-photo deletion is on for ${prop.name}.`); await retention.refetch();
            })} />
            <Button title="Keep deletion off" variant="ghost" onPress={() => setConfirmProperty("")} />
          </> : null}
        </View>)}
        <Button title="Copy existing photos to private cloud storage" loading={busy} onPress={() => act(async () => { await api.post("/system/media/migrate"); setMessage("Photo copy queued. Originals are kept while cloud copies are verified."); })} />
        <Txt>All properties start with deletion off. Use the cleaning admin controls to hold photos for damage, disputes or owner review.</Txt>
      </Card>
      <Card style={{ gap: spacing.md }}><Txt v="subtitle">Your administrator authenticator</Txt>
        <Txt>{mfa.data?.enabled ? `Enabled. ${mfa.data.recovery_codes_remaining} recovery codes remain.` : "Not enabled. Add an authenticator to protect your admin account."}</Txt>
        {!mfa.data?.enabled && !recovery.length ? <>
          <Input label="Current password" secureTextEntry value={password} onChangeText={setPassword} />
          <Button title="Set up authenticator" loading={busy} onPress={() => act(async () => {
            const result = await api.post("/auth/mfa/setup", { password }); setSetup(result.setup_key);
          })} />
          {setup ? <><Txt>Add an account manually in your authenticator. Name: Britsmaid. Type: time-based. Keep this setup key private:</Txt><Txt selectable>{setup}</Txt>
            <Input label="Six-digit authenticator code" value={code} onChangeText={setCode} keyboardType="number-pad" />
            <Button title="Confirm authenticator" loading={busy} onPress={() => act(async () => {
              const result = await api.post("/auth/mfa/confirm", { password, code });
              if (Platform.OS !== "web" && result.access_token) { await storage.secureSet(TOKEN_KEY, result.access_token); setToken(result.access_token); }
              setRecovery(result.recovery_codes); setSetup(""); setPassword(""); setCode(""); await mfa.refetch();
            })} /></> : null}
        </> : null}
        {recovery.length ? <><Txt>Save these recovery codes privately now. Each works once. They will not be shown again.</Txt>
          {recovery.map(item => <Txt key={item} selectable>{item}</Txt>)}
          <Button title="I saved my recovery codes" onPress={() => setRecovery([])} />
        </> : null}
      </Card>
    </ScrollView>
  </View>;
}
