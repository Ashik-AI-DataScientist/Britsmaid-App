import React, { useState } from "react";
import { View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button, Card, ConfirmSheet, Header, Icon, IconButton, Input, Loading, Segmented, Sheet, Txt, useToast } from "@/src/ui";
import { spacing, useTheme } from "@/src/theme";

export default function Staff() {
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { colors } = useTheme();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", email: "", password: "", role: "cleaner" as "cleaner" | "admin" });
  const [busy, setBusy] = useState(false);
  const [rm, setRm] = useState<any>(null);

  const add = async () => {
    if (!f.name || !f.email || f.password.length < 6) return toast("Name, email and a 6+ char password are required", "error");
    setBusy(true);
    try {
      await api.post("/users", f);
      setOpen(false);
      setF({ name: "", email: "", password: "", role: "cleaner" });
      q.refetch();
      toast("Staff member added");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Team" subtitle="Admins & cleaning staff" right={<IconButton testID="staff-add-button" name="person-add-outline" tone="brand" onPress={() => setOpen(true)} />} />
      {q.isLoading ? <Loading /> : (
        <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}>
          {(q.data ?? []).map((u) => (
            <Card key={u.id} testID={`staff-${u.id}`} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Icon name={u.role === "admin" ? "shield-checkmark-outline" : "sparkles-outline"} size={22} color={colors.brandPrimary} />
              <View style={{ flex: 1 }}>
                <Txt v="subtitle" style={{ fontSize: 15 }}>{u.name}</Txt>
                <Txt v="caption">{u.email}</Txt>
              </View>
              <Badge label={u.role === "admin" ? "Admin" : "Cleaner"} tone={u.role === "admin" ? "brand" : "neutral"} />
              {u.id !== user?.id ? <IconButton testID={`staff-remove-${u.id}`} name="trash-outline" size={18} onPress={() => setRm(u)} /> : null}
            </Card>
          ))}
        </KeyboardAwareScrollView>
      )}
      <Sheet visible={open} onClose={() => setOpen(false)} title="Add team member" testID="staff-sheet">
        <View style={{ gap: spacing.md }}>
          <Segmented testID="staff-role" value={f.role} onChange={(r) => setF({ ...f, role: r })} options={[{ value: "cleaner", label: "Cleaning staff" }, { value: "admin", label: "Admin" }]} />
          <Input testID="staff-name-input" label="Name" value={f.name} onChangeText={(t) => setF({ ...f, name: t })} />
          <Input testID="staff-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.email} onChangeText={(t) => setF({ ...f, email: t })} />
          <Input testID="staff-password-input" label="Temporary password" secureTextEntry value={f.password} onChangeText={(t) => setF({ ...f, password: t })} />
          <Button testID="staff-save-button" title="Add member" onPress={add} loading={busy} />
        </View>
      </Sheet>
      <ConfirmSheet visible={!!rm} title="Remove member?" message={`${rm?.name} will no longer be able to sign in.`} confirmLabel="Remove" onClose={() => setRm(null)} onConfirm={async () => { await api.del(`/users/${rm.id}`); setRm(null); q.refetch(); toast("Member removed"); }} />
    </View>
  );
}
