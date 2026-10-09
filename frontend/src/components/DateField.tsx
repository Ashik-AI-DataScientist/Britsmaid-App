import React, { useState } from "react";
import { Pressable, View } from "react-native";
import { Icon, IconButton, Sheet, Txt } from "@/src/ui";
import { MonthGrid } from "@/src/components/MonthGrid";
import { fmtDate, monthLabel, shiftMonth, thisMonth } from "@/src/format";
import { fonts, radius, spacing, useTheme } from "@/src/theme";

export function DateField({ label, value, onChange, min, testID }: { label: string; value: string; onChange: (d: string) => void; min?: string; testID: string }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState((value || "").slice(0, 7) || thisMonth());
  return (
    <View style={{ gap: spacing.xs, flex: 1 }}>
      <Txt v="label">{label}</Txt>
      <Pressable testID={testID} onPress={() => { setMonth((value || "").slice(0, 7) || thisMonth()); setOpen(true); }} style={{ minHeight: 50, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Icon name="calendar-outline" size={18} color={colors.brandPrimary} />
        <Txt v="body" style={{ fontFamily: fonts.displayMedium, color: value ? colors.onSurface : colors.muted }}>{value ? fmtDate(value) : "Select"}</Txt>
      </Pressable>
      <Sheet visible={open} onClose={() => setOpen(false)} title={label} testID={`${testID}-sheet`}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
          <IconButton testID={`${testID}-prev-month`} name="chevron-back" onPress={() => setMonth(shiftMonth(month, -1))} />
          <Txt v="subtitle">{monthLabel(month)}</Txt>
          <IconButton testID={`${testID}-next-month`} name="chevron-forward" onPress={() => setMonth(shiftMonth(month, 1))} />
        </View>
        <MonthGrid testID={`${testID}-grid`} month={month} selected={value} min={min} onSelect={(d) => { onChange(d); setOpen(false); }} />
      </Sheet>
    </View>
  );
}
