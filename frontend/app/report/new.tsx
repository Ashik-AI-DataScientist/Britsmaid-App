import React, { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { CaptureSheet, Media } from "@/src/components/CaptureSheet";
import { MediaThumb } from "@/src/components/MediaThumb";
import { Button, Card, Chip, ChipRow, ErrorState, Header, IconButton, Input, Txt, useToast } from "@/src/ui";
import { monthLabel, shiftMonth, thisMonth } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function NewOwnerReport() {
  const params = useLocalSearchParams<{ property_id?: string; month?: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });
  const [pid, setPid] = useState(params.property_id ?? "");
  const [month, setMonth] = useState(params.month ?? thisMonth());
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [media, setMedia] = useState<Media[]>([]);
  const [capture, setCapture] = useState(false);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!pid) return toast("Choose a property", "error");
    setSaving(true);
    try {
      const r = await api.post("/owner-reports", { property_id: pid, month, title, condition_notes: notes, media_ids: media.map((m) => m.id) });
      qc.invalidateQueries({ queryKey: ["owner-reports"] });
      toast("Owner report created");
      router.replace(`/report/${r.id}`);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (props.isError) return <View style={{flex:1}}><Header back title="Owner report" /><ErrorState message={(props.error as Error).message} onRetry={props.refetch} /></View>;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Owner report" subtitle="Status update with photos, videos & payout" />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <Txt v="label" style={{ paddingHorizontal: spacing.lg }}>Property</Txt>
        <ChipRow>
          {(props.data ?? []).map((p) => <Chip key={p.id} testID={`report-property-${p.id}`} label={p.name} selected={pid === p.id} onPress={() => setPid(p.id)} />)}
        </ChipRow>
        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          <Card style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm }}>
            <IconButton testID="report-prev-month" name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
            <Txt v="subtitle" testID="report-month">{monthLabel(month)}</Txt>
            <IconButton testID="report-next-month" name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
          </Card>
          <Card style={{ gap: spacing.md }}>
            <Input testID="report-title-input" label="Title (optional)" value={title} onChangeText={setTitle} placeholder="Monthly update" />
            <Input testID="report-notes-input" label="Current condition of the house" multiline value={notes} onChangeText={setNotes} placeholder="Garden maintained, AC serviced, minor wall touch-up needed..." />
          </Card>
          <Card style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Txt v="label" style={{ flex: 1 }}>Photos & videos ({media.length})</Txt>
              <Button testID="report-add-media" small icon="camera" title="Add" onPress={() => setCapture(true)} />
            </View>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {media.map((m, i) => <MediaThumb key={m.id} testID={`report-media-${i}`} id={m.id} kind={m.kind} onRemove={() => setMedia(media.filter((x) => x.id !== m.id))} />)}
            </View>
            {media.length === 0 ? <Txt v="caption">Capture the current state of the villa to keep the owner updated.</Txt> : null}
          </Card>
          <Txt v="caption">The payout split and OTA breakdown for {monthLabel(month)} will be attached automatically.</Txt>
          <Button testID="report-submit-button" title="Create report" icon="send" onPress={submit} loading={saving} />
        </View>
      </KeyboardAwareScrollView>
      <CaptureSheet visible={capture} onClose={() => setCapture(false)} allowVideo successMessage="Added to report draft. Create report to save it." destination={{ key: `report:${pid}:${month}`, label: `Owner report / ${month}` }} purpose="Capture photos or a walkthrough video so the owner can see the current status of their house." onUploaded={async (m, d) => { if(d.key !== `report:${pid}:${month}`) throw new Error("Return to the original property and month to add this attachment."); setMedia((x) => [...x, ...m]); }} />
    </View>
  );
}
