import React from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { api } from "@/src/api";
import { usesNativeTabs } from "@/src/navigation";
import { Badge, Button, Card, Empty, ErrorState, IconButton, Loading, Txt } from "@/src/ui";
import { spacing, radius, useTheme } from "@/src/theme";

export default function Properties() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { colors } = useTheme();
  const q = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingBottom: spacing.md, paddingHorizontal: spacing.lg, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flex: 1 }}>
          <Txt v="title">Villas</Txt>
          <Txt v="caption">{q.data?.length ?? 0} properties under management</Txt>
        </View>
        <IconButton testID="add-property-button" name="add" tone="brand" onPress={() => router.push("/property/edit")} />
      </View>
      {q.isLoading ? <Loading /> : q.isError ? <ErrorState message="Failed to load properties" onRetry={q.refetch} /> : (
        <FlatList
          data={q.data}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: bottomChrome + spacing.xl }}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={<Empty icon="business-outline" title="No properties added yet." action={<Button small title="Add Property" onPress={() => router.push("/property/edit")} testID="empty-add-property" />} />}
          renderItem={({ item: p, index }) => (
            <Animated.View entering={FadeInDown.delay(index * 60)}>
              <Card testID={`property-card-${p.id}`} onPress={() => router.push(`/property/${p.id}`)} style={{ padding: 0, overflow: "hidden" }}>
                <View style={{ height: 150, backgroundColor: colors.brandTertiary }}>
                  {p.cover_url ? <Image source={{ uri: p.cover_url }} style={{ width: "100%", height: "100%" }} contentFit="cover" transition={200} /> : null}
                  <LinearGradient colors={["transparent", colors.scrim]} style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 100 }} />
                  <View style={{ position: "absolute", left: spacing.lg, bottom: spacing.md, right: spacing.lg }}>
                    <Txt v="title" color={colors.onSurfaceInverse}>{p.name}</Txt>
                    <Txt v="caption" color={colors.onSurfaceInverse}>{p.location}</Txt>
                  </View>
                  <View style={{ position: "absolute", top: spacing.md, right: spacing.md, flexDirection: "row", gap: 6 }}>
                    <Badge label={p.occupied ? "Occupied" : "Vacant"} tone={p.occupied ? "info" : "neutral"} />
                    <Badge label={p.needs_cleaning ? "Needs cleaning" : "Guest-ready"} tone={p.needs_cleaning ? "warning" : "success"} />
                  </View>
                </View>
                <View style={{ flexDirection: "row", padding: spacing.lg, gap: spacing.lg }}>
                  <View style={{ flex: 1 }}>
                    <Txt v="caption">Owner</Txt>
                    <Txt v="subtitle" style={{ fontSize: 14 }} numberOfLines={1}>{p.owner_name || "—"}</Txt>
                  </View>
                  <View>
                    <Txt v="caption">Owner / BM</Txt>
                    <Txt v="mono">{p.owner_share_percent}/{100 - p.owner_share_percent}</Txt>
                  </View>
                  <View>
                    <Txt v="caption">Electricity</Txt>
                    <View style={{ marginTop: 2, borderRadius: radius.pill }}>
                      <Badge label={p.electricity_mode === "split_half" ? "50/50" : "Owner"} tone="brand" />
                    </View>
                  </View>
                </View>
              </Card>
            </Animated.View>
          )}
        />
      )}
    </View>
  );
}
