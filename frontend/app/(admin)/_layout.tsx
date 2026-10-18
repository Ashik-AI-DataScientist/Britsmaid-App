import React from "react";
import { Platform } from "react-native";
import { Tabs } from "expo-router";
import { usesNativeTabs } from "@/src/navigation";
import { Icon } from "@/src/ui";
import { fonts, useTheme } from "@/src/theme";

// IMPORTANT: expo-router/unstable-native-tabs pulls experimental
// react-native-screens code that breaks Expo Go on Android, so it must be
// required lazily — only on iOS 26+ where NativeTabs is actually rendered.
let NativeTabsLayout: React.ComponentType | null = null;
if (usesNativeTabs) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy import avoids loading unsupported native tabs on Android
  NativeTabsLayout = require("@/src/NativeTabsLayout").default;
}

export default function AdminTabs() {
  const { colors } = useTheme();
  if (usesNativeTabs && NativeTabsLayout) {
    const Layout = NativeTabsLayout;
    return <Layout />;
  }
  const tab = (name: string, title: string, icon: any, iconOn: any) => (
    <Tabs.Screen
      name={name}
      options={{
        title,
        tabBarButtonTestID: `tab-${name}`,
        tabBarIcon: ({ color, focused }: { color: any; focused: boolean }) => <Icon name={focused ? iconOn : icon} size={22} color={color} />,
      }}
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
