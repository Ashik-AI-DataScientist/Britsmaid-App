import React, { useState } from "react";
import { Platform, Share, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, BACKEND_URL } from "@/src/api";
import { OTAS } from "@/src/format";
import { Button, Card, Chip, ConfirmSheet, Input, Txt, useToast } from "@/src/ui";
import { spacing } from "@/src/theme";

export function CalendarExport({ propertyId }: { propertyId: string }) {
  const toast = useToast();
  const [destination, setDestination] = useState("Airbnb");
  const [busy, setBusy] = useState(false);
  const [revoke, setRevoke] = useState(false);
  const [error, setError] = useState("");
  const q = useQuery({ queryKey: ["calendar-export", propertyId], queryFn: () => api.get(`/properties/${propertyId}/ical-export`) });
  const url = q.data?.token ? `${BACKEND_URL}/api/ical/${q.data.token}.ics?exclude_ota=${encodeURIComponent(destination)}` : "";
  const change = async (disable = false) => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (disable) await api.del(`/properties/${propertyId}/ical-export`);
      else await api.post(`/properties/${propertyId}/ical-export`);
      await q.refetch(); setRevoke(false);
    } catch (e: any) { setError(e.message || "Calendar link could not be updated. Try again."); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    try {
      if (Platform.OS === "web" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url); toast("Calendar link copied");
      } else await Share.share({ message: url });
    } catch { setError("Copy is unavailable. Select and copy the calendar link above."); }
  };
  return <Card style={{ gap: spacing.sm }} testID="calendar-export-card">
    <Txt v="label">Send this villa’s availability to an OTA</Txt>
    <Txt>Choose the destination, then paste its link into that OTA’s Import calendar setting. Booked and blocked nights are shared; guest names and amounts are excluded.</Txt>
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
      {OTAS.filter(x => x !== "Direct").map(ota => <Chip key={ota} label={ota} selected={destination === ota} onPress={() => setDestination(ota)} />)}
    </View>
    <Txt v="caption">This link excludes bookings imported from {destination} to reduce calendar loops. OTA refresh times vary; iCal is not instant. Only give the link to services you want to read this villa’s availability.</Txt>
    {q.isError || error ? <View accessibilityRole="alert"><Txt>{error || (q.error as Error).message}</Txt><Button title="Retry link status" variant="secondary" onPress={() => q.refetch()} /></View> : null}
    {url ? <>
      <Input label={`${destination} import link`} testID="calendar-export-url" value={url} editable={false} selectTextOnFocus />
      <Button title="Copy calendar link" icon="copy-outline" onPress={copy} />
      <Button title="Disable calendar link" variant="ghost" disabled={busy} onPress={() => setRevoke(true)} />
    </> : <Button title="Create iCal link" icon="calendar-outline" loading={busy || q.isLoading} disabled={q.isError} onPress={() => change()} />}
    <ConfirmSheet visible={revoke} title="Disable this calendar link?" message="OTAs using this link will stop receiving updates. Creating another link later will require updating each OTA." confirmLabel="Disable link" loading={busy} onClose={() => setRevoke(false)} onConfirm={() => change(true)} />
  </Card>;
}
