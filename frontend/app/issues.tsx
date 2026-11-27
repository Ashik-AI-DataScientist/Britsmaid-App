import React from "react";
import { useRouter } from "expo-router";
import { ScrollView, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { Badge, Button, Card, ErrorState, Header, Loading, Txt } from "@/src/ui";
import { spacing } from "@/src/theme";

type Issue = { id: string; title: string; route: string; status: string; last_seen: string; recovered_at?: string; count?: number; help: string };
export default function Issues() {
  const router = useRouter();
  const q = useQuery({ queryKey: ["system-issues"], queryFn: () => api.get<Issue[]>("/system/issues"), refetchInterval: 30000 });
  return <View style={{ flex: 1 }}><Header back title="Service notices" subtitle="Admin issue and recovery history" />
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
      <Txt>Notices update while the app is connected. If the service is unavailable, this panel cannot send an alert.</Txt>
      <Button title="Security, storage & backups" onPress={() => router.push("/settings")} />
      <Button title="Refresh notices" loading={q.isRefetching} onPress={() => q.refetch()} />
      {q.isLoading ? <Loading /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : !q.data?.length ? <Card><Txt>No service failures recorded.</Txt></Card> : null}
      {q.data?.slice().sort((a, b) => (a.status === "open" ? 0 : 1) - (b.status === "open" ? 0 : 1)).map(issue => <Card key={issue.id} style={{ gap: spacing.sm }}>
        <Badge label={issue.status === "open" ? "Needs attention" : "Request recovered"} tone={issue.status === "open" ? "warning" : "success"} />
        <Txt v="subtitle">{issue.title}</Txt><Txt>{issue.help}</Txt>
        <Txt v="caption">Reference {issue.id} · {issue.count ?? 1} occurrence(s) · {new Date(issue.last_seen).toLocaleString()}</Txt>
        {issue.recovered_at ? <Txt>Request succeeded again at {new Date(issue.recovered_at).toLocaleString()}</Txt> : null}
      </Card>)}
    </ScrollView>
  </View>;
}
