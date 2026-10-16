import React, { useState } from "react";
import { RefreshControl, SectionList, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Card, Empty, ErrorState, Header, Icon, IconButton, Loading, Segmented, Txt } from "@/src/ui";
import { fmtDate, todayISO } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export default function CleaningList() {
  const { property_id } = useLocalSearchParams<{ property_id?: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const { user, logout } = useAuth();
  const isCleaner = user?.role === "cleaner" || user?.role === "supervisor";
  const canReview = user?.role === "admin" || user?.role === "supervisor";
  const [tab, setTab] = useState<"open" | "completed" | "awaiting_review" | "unassigned">(canReview ? "awaiting_review" : "open");
  const q = useQuery({ queryKey: ["cleaning", tab, property_id], queryFn: () => api.get<any[]>(`/cleaning?status=${tab}${property_id ? `&property_id=${property_id}` : ""}`) });

  const groups: Record<string, any[]> = {};
  for (const c of q.data ?? []) (groups[c.property_name] ??= []).push(c);
  const sections = Object.entries(groups).map(([title, data]) => ({ title, data }));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back={!isCleaner} title={isCleaner ? `Hi, ${user?.name?.split(" ")[0]}` : "Cleaning sessions"} subtitle={isCleaner ? "Your checkout cleaning tasks" : "Before & after documentation"}
        right={isCleaner ? <IconButton testID="cleaner-logout-button" name="log-out-outline" onPress={logout} /> : undefined} />
      <View style={{ padding: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface }}>
        <Segmented testID="cleaning-tabs" value={tab} onChange={setTab} options={canReview ? [{ value: "awaiting_review", label: "Review" }, { value: "unassigned", label: "Unassigned" }, { value: "open", label: "To do" }, { value: "completed", label: "Done" }] : [{ value: "open", label: "To do" }, { value: "completed", label: "Completed" }]} />
      </View>
      {q.isLoading ? <Loading label="Loading task details..." /> : q.isError ? <ErrorState message="Could not load tasks" onRetry={q.refetch} /> : (
        <SectionList
          sections={sections}
          keyExtractor={(c) => c.id}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={<Empty icon="checkmark-done-circle-outline" title={tab === "awaiting_review" ? "No cleaning waiting for review" : tab === "unassigned" ? "All tasks have a cleaner" : tab === "open" ? "No tasks to do" : "No completed sessions yet"} />}
          renderSectionHeader={({ section }) => <Txt v="label" style={{ marginTop: spacing.sm, marginBottom: spacing.xs }}>{section.title}</Txt>}
          renderItem={({ item: c }) => {
            const pct = c.rooms_total ? c.rooms_done / c.rooms_total : 0;
            const overdue = c.status !== "completed" && c.date < todayISO();
            return (
              <Card testID={`cleaning-card-${c.id}`} onPress={() => router.push(`/cleaning/${c.id}`)} style={{ gap: spacing.sm, marginBottom: spacing.sm }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                  <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: c.status === "completed" ? colors.successSoft : colors.warningSoft, alignItems: "center", justifyContent: "center" }}>
                    <Icon name={c.status === "completed" ? "checkmark-done" : "sparkles"} size={20} color={c.status === "completed" ? colors.success : colors.warning} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Txt v="subtitle" style={{ fontSize: 15 }}>Checkout {fmtDate(c.date)}</Txt>
                    <Txt v="caption">{c.assigned_name ? `Assigned to ${c.assigned_name}` : "Unassigned"}</Txt>
                  </View>
                  <Badge label={c.status === "completed" ? "Ready" : c.status === "awaiting_review" ? "Needs review" : overdue ? "Overdue" : c.status === "in_progress" ? "In progress" : "Pending"} tone={c.status === "completed" ? "success" : overdue ? "error" : "warning"} />
                </View>
                <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.surfaceSecondary, overflow: "hidden" }}>
                  <View style={{ width: `${pct * 100}%`, height: "100%", backgroundColor: c.status === "completed" ? colors.success : colors.brandPrimary }} />
                </View>
                <Txt v="caption">{c.rooms_done}/{c.rooms_total} rooms documented (before & after)</Txt>
              </Card>
            );
          }}
        />
      )}
    </View>
  );
}
