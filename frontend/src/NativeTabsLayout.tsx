import React from "react";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { useTheme } from "@/src/theme";

/**
 * iOS 26+ native tab bar (Liquid Glass). This module imports experimental
 * native-tabs code, so it must ONLY be loaded on supported platforms —
 * app/(admin)/_layout.tsx requires it lazily behind the usesNativeTabs gate.
 */
export default function NativeTabsLayout() {
  const { colors } = useTheme();
  return (
    <NativeTabs tintColor={colors.brandPrimary}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon sf="house.fill" />
        <NativeTabs.Trigger.Label>Home</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="calendar">
        <NativeTabs.Trigger.Icon sf="calendar" />
        <NativeTabs.Trigger.Label>Calendar</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="properties">
        <NativeTabs.Trigger.Icon sf="building.2.fill" />
        <NativeTabs.Trigger.Label>Villas</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="finance">
        <NativeTabs.Trigger.Icon sf="indianrupeesign.circle.fill" />
        <NativeTabs.Trigger.Label>Finance</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
