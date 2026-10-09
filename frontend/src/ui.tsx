import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { ActivityIndicator, Modal, Pressable, StyleProp, Text, TextInput, TextInputProps, TextStyle, View, ViewStyle, ScrollView } from "react-native";
import Animated, { FadeInDown, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export type IconName = React.ComponentProps<typeof Ionicons>["name"];
export const Icon = Ionicons;

// ---------------------------------------------------------------- Text
type TxtVariant = "display" | "title" | "subtitle" | "body" | "caption" | "label" | "mono";
export function Txt({ v = "body", style, color, children, ...rest }: { v?: TxtVariant; style?: StyleProp<TextStyle>; color?: string; children?: React.ReactNode; numberOfLines?: number; testID?: string }) {
  const { colors } = useTheme();
  const base: Record<TxtVariant, TextStyle> = {
    display: { fontFamily: fonts.display, fontSize: 30, color: colors.onSurface, letterSpacing: -0.5 },
    title: { fontFamily: fonts.display, fontSize: 20, color: colors.onSurface },
    subtitle: { fontFamily: fonts.textSemi, fontSize: 16, color: colors.onSurface },
    body: { fontFamily: fonts.text, fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
    caption: { fontFamily: fonts.text, fontSize: 12, color: colors.muted },
    label: { fontFamily: fonts.textSemi, fontSize: 12, color: colors.muted, letterSpacing: 0.6, textTransform: "uppercase" },
    mono: { fontFamily: fonts.displayMedium, fontSize: 16, color: colors.onSurface },
  };
  return (
    <Text style={[base[v], color ? { color } : null, style]} {...rest}>
      {children}
    </Text>
  );
}

// ---------------------------------------------------------------- Button
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ title, onPress, variant = "primary", icon, loading, disabled, style, testID, small }: {
  title: string; onPress?: () => void; variant?: BtnVariant; icon?: IconName; loading?: boolean; disabled?: boolean; style?: StyleProp<ViewStyle>; testID?: string; small?: boolean;
}) {
  const { colors } = useTheme();
  const bg = { primary: colors.brandPrimary, secondary: colors.brandTertiary, ghost: "transparent", danger: colors.errorSoft }[variant];
  const fg = { primary: colors.onBrandPrimary, secondary: colors.onBrandTertiary, ghost: colors.brandPrimary, danger: colors.error }[variant];
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        { backgroundColor: bg, minHeight: small ? 40 : 50, borderRadius: radius.md, paddingHorizontal: small ? spacing.md : spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, opacity: disabled ? 0.5 : 1, transform: [{ scale: pressed ? 0.97 : 1 }] },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : icon ? <Icon name={icon} size={small ? 16 : 18} color={fg} /> : null}
      <Text style={{ color: fg, fontFamily: fonts.textSemi, fontSize: small ? 13 : 15 }}>{title}</Text>
    </Pressable>
  );
}

export function IconButton({ name, onPress, testID, tone = "default", size = 22 }: { name: IconName; onPress?: () => void; testID?: string; tone?: "default" | "brand" | "inverse"; size?: number }) {
  const { colors } = useTheme();
  const bg = tone === "brand" ? colors.brandTertiary : tone === "inverse" ? colors.scrim : colors.surfaceSecondary;
  const fg = tone === "brand" ? colors.brandPrimary : tone === "inverse" ? colors.onSurfaceInverse : colors.onSurface;
  return (
    <Pressable testID={testID} onPress={onPress} hitSlop={6} style={({ pressed }) => ({ width: 44, height: 44, borderRadius: radius.pill, backgroundColor: bg, alignItems: "center", justifyContent: "center", opacity: pressed ? 0.7 : 1 })}>
      <Icon name={name} size={size} color={fg} />
    </Pressable>
  );
}

// ---------------------------------------------------------------- Card
export function Card({ children, style, onPress, testID }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; testID?: string }) {
  const s = useStyles();
  if (onPress)
    return (
      <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [s.card, { transform: [{ scale: pressed ? 0.985 : 1 }] }, style]}>
        {children}
      </Pressable>
    );
  return (
    <View testID={testID} style={[s.card, style]}>
      {children}
    </View>
  );
}

// ---------------------------------------------------------------- Input
export function Input({ label, style, ...props }: TextInputProps & { label?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [focus, setFocus] = useState(false);
  return (
    <View style={{ gap: spacing.xs }}>
      {label ? <Txt v="label">{label}</Txt> : null}
      <TextInput
        placeholderTextColor={colors.muted}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={[s.input, focus && { borderColor: colors.brandPrimary }, props.multiline && { minHeight: 88, textAlignVertical: "top", paddingTop: spacing.md }, style]}
        {...props}
      />
    </View>
  );
}

// ---------------------------------------------------------------- Chips & badges
export function Chip({ label, selected, onPress, testID, dot }: { label: string; selected?: boolean; onPress?: () => void; testID?: string; dot?: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={{ height: 36, flexShrink: 0, paddingHorizontal: spacing.md, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: selected ? colors.brandPrimary : colors.border, backgroundColor: selected ? colors.brandPrimary : colors.surface }}
    >
      {dot ? <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dot }} /> : null}
      <Text style={{ fontFamily: fonts.textSemi, fontSize: 13, color: selected ? colors.onBrandPrimary : colors.onSurfaceSecondary }}>{label}</Text>
    </Pressable>
  );
}

export function ChipRow({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, height: 56 }} contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" }}>
      {children}
    </ScrollView>
  );
}

export type Tone = "success" | "warning" | "error" | "info" | "brand" | "neutral";
export function Badge({ label, tone = "neutral", testID }: { label: string; tone?: Tone; testID?: string }) {
  const { colors } = useTheme();
  const map: Record<Tone, [string, string]> = {
    success: [colors.successSoft, "#047857"],
    warning: [colors.warningSoft, "#B45309"],
    error: [colors.errorSoft, colors.error],
    info: [colors.brandTertiary, colors.info],
    brand: [colors.brandTertiary, colors.brandPrimary],
    neutral: [colors.surfaceSecondary, colors.onSurfaceTertiary],
  };
  const [bg, fg] = map[tone];
  return (
    <View testID={testID} style={{ backgroundColor: bg, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4, alignSelf: "flex-start" }}>
      <Text style={{ color: fg, fontFamily: fonts.textSemi, fontSize: 11 }}>{label}</Text>
    </View>
  );
}

// ---------------------------------------------------------------- Segmented
export function Segmented<T extends string>({ options, value, onChange, testID }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View testID={testID} style={{ flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: 4 }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable key={o.value} testID={`${testID}-${o.value}`} onPress={() => onChange(o.value)} style={{ flex: 1, height: 38, borderRadius: radius.sm + 2, alignItems: "center", justifyContent: "center", backgroundColor: on ? colors.surface : "transparent", shadowColor: "#000", shadowOpacity: on ? 0.08 : 0, shadowRadius: 4, shadowOffset: { width: 0, height: 1 }, elevation: on ? 1 : 0 }}>
            <Text style={{ fontFamily: fonts.textSemi, fontSize: 13, color: on ? colors.brandPrimary : colors.muted }}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------- Header
export function Header({ title, subtitle, back, right }: { title: string; subtitle?: string; back?: boolean; right?: React.ReactNode }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <View style={{ paddingTop: insets.top + spacing.sm, paddingBottom: spacing.md, paddingHorizontal: spacing.lg, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider, flexDirection: "row", alignItems: "center", gap: spacing.md }}>
      {back ? <IconButton testID="header-back-button" name="chevron-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} /> : null}
      <View style={{ flex: 1 }}>
        <Txt v="title" numberOfLines={1}>{title}</Txt>
        {subtitle ? <Txt v="caption" numberOfLines={1}>{subtitle}</Txt> : null}
      </View>
      {right}
    </View>
  );
}

// ---------------------------------------------------------------- States
export function Loading({ label = "Loading..." }: { label?: string }) {
  const { colors } = useTheme();
  return (
    <View testID="loading-state" style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xxl, gap: spacing.md }}>
      <ActivityIndicator color={colors.brandPrimary} size="large" />
      <Txt v="caption">{label}</Txt>
    </View>
  );
}

export function Empty({ icon, title, subtitle, action }: { icon: IconName; title: string; subtitle?: string; action?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View testID="empty-state" style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.sm }}>
      <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
        <Icon name={icon} size={28} color={colors.brandPrimary} />
      </View>
      <Txt v="subtitle" style={{ textAlign: "center" }}>{title}</Txt>
      {subtitle ? <Txt v="caption" style={{ textAlign: "center" }}>{subtitle}</Txt> : null}
      {action}
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <View testID="error-state" style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.md }}>
      <Icon name="cloud-offline-outline" size={36} color="#EF4444" />
      <Txt v="body" style={{ textAlign: "center" }}>{message || "Something went wrong"}</Txt>
      {onRetry ? <Button small title="Retry" variant="secondary" icon="refresh" onPress={onRetry} testID="retry-button" /> : null}
    </View>
  );
}

export function Row({ label, value, strong, testID }: { label: string; value: string; strong?: boolean; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.md }}>
      <Txt v={strong ? "subtitle" : "body"} style={{ flex: 1 }}>{label}</Txt>
      <Txt testID={testID} v="mono" style={{ fontSize: strong ? 17 : 15, fontFamily: strong ? fonts.display : fonts.displayMedium }}>{value}</Txt>
    </View>
  );
}

// ---------------------------------------------------------------- Sheet
export function Sheet({ visible, onClose, title, children, testID }: { visible: boolean; onClose: () => void; title?: string; children: React.ReactNode; testID?: string }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: colors.backdrop }} onPress={onClose} testID={`${testID}-backdrop`} />
      <View testID={testID} style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: insets.bottom + spacing.lg, maxHeight: "85%" }}>
        <View style={{ width: 40, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md }} />
        {title ? <Txt v="title" style={{ marginBottom: spacing.md }}>{title}</Txt> : null}
        {children}
      </View>
    </Modal>
  );
}

export function ConfirmSheet({ visible, title, message, confirmLabel = "Delete", onConfirm, onClose, loading }: { visible: boolean; title: string; message: string; confirmLabel?: string; onConfirm: () => void; onClose: () => void; loading?: boolean }) {
  return (
    <Sheet visible={visible} onClose={onClose} title={title} testID="confirm-sheet">
      <Txt v="body" style={{ marginBottom: spacing.lg }}>{message}</Txt>
      <View style={{ flexDirection: "row", gap: spacing.md }}>
        <Button title="Cancel" variant="secondary" onPress={onClose} style={{ flex: 1 }} testID="confirm-cancel-button" />
        <Button title={confirmLabel} variant="danger" onPress={onConfirm} loading={loading} style={{ flex: 1 }} testID="confirm-ok-button" />
      </View>
    </Sheet>
  );
}

// ---------------------------------------------------------------- Toast
type ToastT = { msg: string; tone: "success" | "error" | "info" };
const ToastCtx = createContext<(msg: string, tone?: ToastT["tone"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastT | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const show = useCallback((msg: string, tone: ToastT["tone"] = "success") => {
    setToast({ msg, tone });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 3200);
  }, []);
  const icon: IconName = toast?.tone === "error" ? "alert-circle" : toast?.tone === "info" ? "information-circle" : "checkmark-circle";
  const tint = toast?.tone === "error" ? colors.error : toast?.tone === "info" ? colors.info : colors.success;
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast ? (
        <Animated.View entering={FadeInDown} exiting={FadeOutUp} pointerEvents="none" style={{ position: "absolute", top: insets.top + spacing.sm, left: spacing.lg, right: spacing.lg, zIndex: 999, elevation: 10 }}>
          <View testID="toast" style={{ backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Icon name={icon} size={20} color={tint} />
            <Text style={{ color: colors.onSurfaceInverse, fontFamily: fonts.textSemi, fontSize: 14, flex: 1 }}>{toast.msg}</Text>
          </View>
        </Animated.View>
      ) : null}
    </ToastCtx.Provider>
  );
}

const useStyles = makeStyles((c) => ({
  card: { backgroundColor: c.surface, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: c.border, shadowColor: "#000", shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  input: { minHeight: 50, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, paddingHorizontal: spacing.md, fontFamily: fonts.text, fontSize: 15, color: c.onSurface },
}));
