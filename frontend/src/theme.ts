// Design tokens for Britsmaid. Light theme only (per design guidelines).
// Keys match the "color" block of /app/design_guidelines.json.

import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FFFFFF",
  onSurface: "#111827",
  surfaceSecondary: "#F3F4F6",
  onSurfaceSecondary: "#374151",
  surfaceTertiary: "#E5E7EB",
  onSurfaceTertiary: "#4B5563",
  surfaceInverse: "#1F2937",
  onSurfaceInverse: "#F9FAFB",
  muted: "#6B7280",

  brand: "#1B3A6B",
  onBrand: "#FFFFFF",
  brandPrimary: "#1B3A6B",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#375B96",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#E8EDF4",
  onBrandTertiary: "#1B3A6B",

  success: "#10B981",
  onSuccess: "#FFFFFF",
  successSoft: "#D1FAE5",
  warning: "#F59E0B",
  onWarning: "#FFFFFF",
  warningSoft: "#FEF3C7",
  error: "#EF4444",
  onError: "#FFFFFF",
  errorSoft: "#FEE2E2",
  info: "#3B82F6",
  onInfo: "#FFFFFF",

  border: "#E5E7EB",
  borderStrong: "#D1D5DB",
  divider: "#F3F4F6",
  scrim: "rgba(17,24,39,0.72)",
  backdrop: "rgba(17,24,39,0.45)",
};

export type ThemeColors = typeof light;

export const fonts = {
  display: "SpaceGrotesk-Bold",
  displayMedium: "SpaceGrotesk-Medium",
  text: "Geist-Regular",
  textSemi: "Geist-SemiBold",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };
export const colors = light;

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}
setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system === "dark" && themes.dark ? "dark" : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
