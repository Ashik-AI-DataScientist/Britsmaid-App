import React from "react";
import { Platform } from "react-native";
import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { usesNativeTabs } from "@/src/navigation";
import { Icon } from "@/src/ui";
import { fonts, useTheme } from "@/src/theme";

export default function AdminTabs() {
  const { colors } = useTheme();
  if (usesNativeTabs) {
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
  const tab = (name: string, title: string, icon: any, iconOn: any) => (
    <Tabs.Screen
      name={name}
      options={{
        title,
        tabBarButtonTestID: `tab-${name}`,
        tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => <Icon name={focused ? iconOn : icon} size={22} color={color} />,
      } as any}
    />
  );
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: fonts.textSemi, fontSize: 11 },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, ...(Platform.OS === "web" ? { height: 64 } : {}) },
        tabBarItemStyle: { alignSelf: "center" },
      }}
    >
      {tab("index", "Home", "home-outline", "home")}
      {tab("calendar", "Calendar", "calendar-outline", "calendar")}
      {tab("properties", "Villas", "business-outline", "business")}
      {tab("finance", "Finance", "wallet-outline", "wallet")}
    </Tabs>
  );
}
