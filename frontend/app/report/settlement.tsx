import React, { useState } from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { SettlementView } from "@/src/components/SettlementView";
import { PayoutStatusCard } from "@/src/components/Payout";
import { settlementHtml, sharePdf } from "@/src/pdf";
import { Button, ErrorState, Header, IconButton, Loading, Txt, useToast } from "@/src/ui";
import { monthLabel, shiftMonth, thisMonth } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";


export default function Settlement() {
  const { property_id } = useLocalSearchParams<{ property_id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { colors } = useTheme();
  const [month, setMonth] = useState(thisMonth());
  const [busy, setBusy] = useState(false);
  const q = useQuery({ queryKey: ["settlement", property_id, month], queryFn: () => api.get(`/reports/settlement?property_id=${property_id}&month=${month}`) });

  const share = async () => {
    setBusy(true);
    try {
      await sharePdf(settlementHtml(q.data));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={q.data?.property_name ?? "Owner statement"} subtitle={q.data?.owner_name ? `Statement for ${q.data.owner_name}` : undefined} />
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface }}>
        <IconButton testID="settlement-prev-month" name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
        <Txt v="subtitle" testID="settlement-month">{monthLabel(month)}</Txt>
        <IconButton testID="settlement-next-month" name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
      </View>
      {q.isLoading ? <Loading label="Generating report..." /> : q.isError ? <ErrorState message="Failed to fetch report" onRetry={q.refetch} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 96 }} refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}>
          <SettlementView s={q.data} onMonthPress={setMonth} />
          <View style={{ marginTop: spacing.md }}>
            <PayoutStatusCard key={`${q.data.month}-${q.data.payout?.id ?? "none"}`} s={q.data} canMark onChange={q.refetch} />
          </View>
        </ScrollView>
      )}
      {q.data ? (
        <View style={{ position: "absolute", left: spacing.lg, right: spacing.lg, bottom: insets.bottom + 16, flexDirection: "row", gap: spacing.sm }}>
          <Button testID="settlement-share-pdf" style={{ flex: 1 }} icon="share-outline" title="Share PDF" onPress={share} loading={busy} />
          <Button testID="settlement-create-report" style={{ flex: 1 }} variant="secondary" icon="camera-outline" title="Owner report" onPress={() => router.push(`/report/new?property_id=${property_id}&month=${month}`)} />
        </View>
      ) : null}
    </View>
  );
}
