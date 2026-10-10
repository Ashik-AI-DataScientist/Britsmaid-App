import React, { useState } from "react";
import { ScrollView, Share, View, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as WebBrowser from "expo-web-browser";
import { api, publicReportUrl } from "@/src/api";
import { useAuth } from "@/src/auth";
import { SettlementView } from "@/src/components/SettlementView";
import { MediaThumb } from "@/src/components/MediaThumb";
import { settlementHtml, sharePdf } from "@/src/pdf";
import { Button, Card, ConfirmSheet, ErrorState, Header, IconButton, Loading, Txt, useToast } from "@/src/ui";
import { fmtDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function OwnerReportView() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const q = useQuery({ queryKey: ["owner-report", id], queryFn: () => api.get(`/owner-reports/${id}`) });
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState(false);
  const isAdmin = useAuth().user?.role === "admin";

  if (q.isLoading) return <Loading label="Generating report..." />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Report" /><ErrorState message={(q.error as Error).message} onRetry={q.refetch} /></View>;
  const r = q.data;
  const link = publicReportUrl(r.share_token);

  const shareLink = async () => {
    try {
      if (Platform.OS === "web") {
        await (navigator as any).clipboard?.writeText(link);
        toast("Interactive link copied");
      } else {
        await Share.share({ message: `${r.title} — your Britsmaid owner report: ${link}` });
      }
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const pdf = async () => {
    setBusy(true);
    try {
      await sharePdf(settlementHtml(r.settlement, { title: r.title, notes: r.condition_notes, photos: [] }));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={r.title} subtitle={`Created ${fmtDate(r.created_at)}`} right={isAdmin ? <IconButton testID="report-delete-button" name="trash-outline" onPress={() => setDel(true)} /> : undefined} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + 96 }}>
        <Card style={{ gap: spacing.sm }} testID="report-condition-card">
          <Txt v="label">Property condition</Txt>
          <Txt v="body">{r.condition_notes || "No notes added."}</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs }}>
            {r.media_ids.map((mid: string, i: number) => <MediaThumb key={mid} testID={`report-view-media-${i}`} id={mid} kind="image" src={`${link}/media/${mid}`} size={96} />)}
          </View>
          {r.media_ids.length ? <Txt v="caption">Tap to view full screen</Txt> : null}
        </Card>
        {isAdmin ? <Card style={{ gap: spacing.sm, backgroundColor: colors.brandTertiary, borderColor: colors.brandTertiary }}>
          <Txt v="subtitle" color={colors.onBrandTertiary}>Interactive owner link</Txt>
          <Txt v="caption">The owner can open this link on any phone to explore the split, OTA breakdown, photos and videos.</Txt>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button testID="report-share-link" small style={{ flex: 1 }} icon="link" title="Share link" onPress={shareLink} />
            <Button testID="report-open-link" small style={{ flex: 1 }} variant="ghost" icon="open-outline" title="Preview" onPress={() => WebBrowser.openBrowserAsync(link)} />
          </View>
        </Card> : null}
        <SettlementView s={r.settlement} />
      </ScrollView>
      <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16 }}>
        <Button testID="report-share-pdf" icon="share-outline" title="Share PDF" onPress={pdf} loading={busy} />
      </View>
      <ConfirmSheet visible={del} title="Delete report?" message="The owner's shared link will stop working." onClose={() => setDel(false)} onConfirm={async () => { await api.del(`/owner-reports/${id}`); qc.invalidateQueries({ queryKey: ["owner-reports"] }); setDel(false); router.back(); }} />
    </View>
  );
}
