import React from "react";
import { Pressable, Text, View } from "react-native";
import { fonts, radius, useTheme } from "@/src/theme";
import { CLEANING_COMPLETE_COLOR } from "@/src/cleaning-status";
import { todayISO } from "@/src/format";

export type DayMark = { bars?: string[]; clean?: "pending" | "completed" | "in_progress" };

const W = ["S", "M", "T", "W", "T", "F", "S"];

export function MonthGrid({ month, selected, onSelect, marks, min, testID = "month-grid" }: {
  month: string; selected?: string; onSelect: (d: string) => void; marks?: Record<string, DayMark>; min?: string; testID?: string;
}) {
  const { colors } = useTheme();
  const [y, m] = month.split("-").map(Number);
  const first = new Date(y, m - 1, 1).getDay();
  const days = new Date(y, m, 0).getDate();
  const cells: (string | null)[] = [...Array(first).fill(null)];
  for (let d = 1; d <= days; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);
  while (cells.length % 7) cells.push(null);
  const today = todayISO();

  return (
    <View testID={testID}>
      <View style={{ flexDirection: "row" }}>
        {W.map((w, i) => (
          <Text key={i} style={{ flex: 1, textAlign: "center", fontFamily: fonts.textSemi, fontSize: 11, color: colors.muted, paddingVertical: 6 }}>{w}</Text>
        ))}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {cells.map((d, i) => {
          if (!d) return <View key={i} style={{ width: `${100 / 7}%`, height: 52 }} />;
          const on = d === selected;
          const disabled = !!min && d < min;
          const mk = marks?.[d];
          const isToday = d === today;
          return (
            <Pressable accessibilityLabel={d + (mk?.clean === "completed" ? ", cleaning complete" : mk?.clean ? ", cleaning due" : "")} key={i} testID={`${testID}-day-${d}`} disabled={disabled} onPress={() => onSelect(d)} style={{ width: `${100 / 7}%`, height: 52, alignItems: "center", paddingTop: 4, opacity: disabled ? 0.3 : 1 }}>
              <View style={{ width: 34, height: 34, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: on ? colors.brandPrimary : isToday ? colors.brandTertiary : "transparent" }}>
                <Text style={{ fontFamily: fonts.displayMedium, fontSize: 14, color: on ? colors.onBrandPrimary : colors.onSurface }}>{Number(d.slice(8))}</Text>
              </View>
              <View style={{ flexDirection: "row", gap: 2, marginTop: 3, height: 6, alignItems: "center" }}>
                {(mk?.bars ?? []).slice(0, 3).map((c, j) => (
                  <View key={j} style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: c }} />
                ))}
                {mk?.clean ? <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: mk.clean === "completed" ? CLEANING_COMPLETE_COLOR : colors.warning }} /> : null}
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
