import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { useEffect } from "react";
import { LogBox, View } from "react-native";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { useAppFonts } from "@/src/app-fonts";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/auth";
import { ToastProvider, Loading } from "@/src/ui";
import { colors } from "@/src/theme";

LogBox.ignoreLogs(["SafeAreaView has been deprecated"]);

function AuthGate() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    const onLogin = segments[0] === "login";
    const isGuest = segments[0] === "guest-check-in";
    if (!user && !onLogin && !isGuest) router.replace("/login");
    if (user && !onLogin && !isGuest) {
      const area = segments[0] as string;
      if ((user.role === "cleaner" || user.role === "supervisor") && area && area !== "cleaning" && !(user.role === "cleaner" && area === "training")) router.replace("/cleaning");
      if (user.role === "owner" && ["(admin)", "staff", "guests", "booking", "invoice", "issues", "settings", "training"].includes(area)) router.replace("/owner");
    }
  }, [user, loading, segments, router]);
  if (loading) return <Loading label="Signing you in..." />;
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surfaceSecondary } }} />;
}

export default function RootLayout() {
  // Prewarm icon + brand fonts so icons render on first paint (Expo Go Android fix).
  const [loaded, error] = useAppFonts();
  if (!loaded && !error) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;
  return (
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <QueryClientProvider client={queryClient}>
          <KeyboardProvider>
            <ToastProvider>
              <AuthProvider>
                <StatusBar style="dark" />
                <AuthGate />
              </AuthProvider>
            </ToastProvider>
          </KeyboardProvider>
        </QueryClientProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}
