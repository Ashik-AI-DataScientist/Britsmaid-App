import React, { useState } from "react";
import { View } from "react-native";
import { Image } from "expo-image";
import { Redirect } from "expo-router";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useAuth } from "@/src/auth";
import { Button, Input, Txt } from "@/src/ui";
import { spacing, useTheme } from "@/src/theme";

export default function Login() {
  const { user, login } = useAuth();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Redirect href="/" />;

  const submit = async () => {
    setErr("");
    if (!email || !password) return setErr("Enter your email and password");
    setBusy(true);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ flexGrow: 1, paddingTop: insets.top + spacing.xxl, paddingBottom: insets.bottom + spacing.xl, paddingHorizontal: spacing.xl, justifyContent: "center" }} keyboardShouldPersistTaps="handled">
        <Animated.View entering={FadeInDown.duration(500)} style={{ alignItems: "center" }}>
          <Image source={require("../assets/images/logo.jpg")} style={{ width: 180, height: 180 }} contentFit="contain" />
        </Animated.View>
        <Animated.View entering={FadeInDown.delay(150).duration(500)} style={{ gap: spacing.lg, marginTop: spacing.xl }}>
          <View>
            <Txt v="display">Welcome back</Txt>
            <Txt v="body">Manage villas, bookings, cleaning and owner payouts.</Txt>
          </View>
          <Input testID="login-email-input" label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="you@britsmaid.com" autoComplete="email" />
          <Input testID="login-password-input" label="Password" value={password} onChangeText={setPassword} secureTextEntry placeholder="••••••••" onSubmitEditing={submit} />
          {err ? <Txt testID="login-error" v="body" color={colors.error}>{err}</Txt> : null}
          <Button testID="login-submit-button" title="Sign in" icon="log-in-outline" onPress={submit} loading={busy} />
          <Txt v="caption" style={{ textAlign: "center" }}>Admins manage everything. Cleaning staff see their checkout tasks.</Txt>
        </Animated.View>
      </KeyboardAwareScrollView>
    </View>
  );
}
