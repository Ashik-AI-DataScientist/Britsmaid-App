import React, { useState } from "react";
import { View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button, Card, Chip, ConfirmSheet, Header, Icon, IconButton, Input, Loading, Segmented, Sheet, Txt, useToast } from "@/src/ui";
import { spacing, useTheme } from "@/src/theme";
import { InviteSheet, Invitee } from "@/src/components/InviteSheet";

type Role = "cleaner" | "supervisor" | "admin" | "owner";

export default function Staff() {
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { colors } = useTheme();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const [open, setOpen] = useState(false);
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api.get<any[]>("/properties") });
  const blank = { name: "", email: "", password: "", phone: "", role: "cleaner" as Role, property_ids: [] as string[] };
  const [f, setF] = useState(blank);
  const [invite, setInvite] = useState<Invitee | null>(null);
  const [busy, setBusy] = useState(false);
  const [rm, setRm] = useState<any>(null);
  const [edit, setEdit] = useState<{ id: string; name: string; phone: string; role: Role; password: string; property_ids: string[]; self: boolean } | null>(null);
  const pname = (id: string) => props.data?.find((p) => p.id === id)?.name ?? "—";
  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const saveAssign = async () => {
    if (!edit) return;
    if (!edit.name.trim()) return toast("Name is required", "error");
    if (edit.role === "owner" && !edit.property_ids.length) return toast("Assign at least one villa", "error");
    if (edit.password && edit.password.length < 6) return toast("Password must be at least 6 characters", "error");
    try {
      await api.put(`/users/${edit.id}`, {
        name: edit.name.trim(),
        phone: edit.phone,
        ...(edit.self ? {} : { role: edit.role }),
        ...(edit.role !== "admin" ? { property_ids: edit.property_ids } : {}),
        ...(edit.password ? { password: edit.password } : {}),
      });
      setEdit(null);
      q.refetch();
      toast(edit.password ? "Member updated · new password set" : "Member updated");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const add = async () => {
    if (!f.name || !f.email || f.password.length < 6) return toast("Name, email and a 6+ char password are required", "error");
    if (f.role === "owner" && !f.property_ids.length) return toast("Select the villa(s) this owner can see", "error");
    setBusy(true);
    try {
      const created = await api.post("/users", { ...f, property_ids: f.role !== "admin" ? f.property_ids : [] });
      setOpen(false);
      setF(blank);
      setInvite({ ...created, password: f.password });
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
      <Header back title="Team & logins" subtitle="Admins, supervisors, cleaners & owners" right={<IconButton testID="staff-add-button" name="person-add-outline" tone="brand" onPress={() => setOpen(true)} />} />
      {q.isLoading ? <Loading /> : (
        <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}>
          {(q.data ?? []).map((u) => (
            <Card key={u.id} testID={`staff-${u.id}`} onPress={() => setEdit({ id: u.id, name: u.name, phone: u.phone ?? "", role: u.role, password: "", property_ids: u.property_ids ?? [], self: u.id === user?.id })} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Icon name={u.role === "admin" ? "shield-checkmark-outline" : u.role === "owner" ? "home-outline" : "sparkles-outline"} size={22} color={colors.brandPrimary} />
              <View style={{ flex: 1 }}>
                <Txt v="subtitle" style={{ fontSize: 15 }}>{u.name}</Txt>
                <Txt v="caption">{u.email}</Txt>
                {u.role !== "admin" ? <Txt v="caption" color={colors.brandPrimary} testID={`staff-villas-${u.id}`}>Villas: {(u.property_ids ?? []).map(pname).join(", ") || "none"}</Txt> : null}
                <Txt v="caption" color={colors.brandPrimary}>Tap to edit access & password</Txt>
              </View>
              <Badge label={u.role === "admin" ? "Admin" : u.role === "owner" ? "Owner" : u.role === "supervisor" ? "Supervisor" : "Cleaner"} tone={u.role === "admin" ? "brand" : u.role === "owner" ? "info" : "neutral"} />
              {u.id !== user?.id ? <IconButton testID={`staff-invite-${u.id}`} name="paper-plane-outline" size={18} tone="brand" onPress={() => setInvite({ ...u, password: null })} /> : null}
              {u.id !== user?.id ? <IconButton testID={`staff-remove-${u.id}`} name="trash-outline" size={18} onPress={() => setRm(u)} /> : null}
            </Card>
          ))}
        </KeyboardAwareScrollView>
      )}
      <Sheet visible={open} onClose={() => setOpen(false)} title="Add team member" testID="staff-sheet">
        <View style={{ gap: spacing.md }}>
          <Segmented testID="staff-role" value={f.role} onChange={(r) => setF({ ...f, role: r })} options={[{ value: "cleaner", label: "Cleaner" }, { value: "supervisor", label: "Supervisor" }, { value: "owner", label: "Villa owner" }, { value: "admin", label: "Admin" }]} />
          <Txt v="caption">{f.role === "admin" ? "Full access to everything." : f.role === "owner" ? "Sees only the dashboard, earnings, stays & reports of the villas you pick below." : "Assigned villas only: cleaners document their tasks; supervisors review cleaning. Select villas below."}</Txt>
          {f.role !== "admin" ? (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {(props.data ?? []).map((p) => <Chip key={p.id} testID={`staff-villa-${p.id}`} label={p.name} selected={f.property_ids.includes(p.id)} onPress={() => setF({ ...f, property_ids: toggle(f.property_ids, p.id) })} />)}
            </View>
          ) : null}
          <Input testID="staff-name-input" label="Name" value={f.name} onChangeText={(t) => setF({ ...f, name: t })} />
          <Input testID="staff-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.email} onChangeText={(t) => setF({ ...f, email: t })} />
          <Input testID="staff-phone-input" label="WhatsApp number (for invite)" keyboardType="phone-pad" value={f.phone} onChangeText={(t) => setF({ ...f, phone: t })} />
          <Input testID="staff-password-input" label="Temporary password" secureTextEntry value={f.password} onChangeText={(t) => setF({ ...f, password: t })} />
          <Button testID="staff-save-button" title="Add member" onPress={add} loading={busy} />
        </View>
      </Sheet>
      <Sheet visible={!!edit} onClose={() => setEdit(null)} title={`Edit ${edit?.name ?? ""}`} testID="assign-sheet">
        {edit ? (
          <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: spacing.md }}>
            {!edit.self ? (
              <>
                <Txt v="label">Access type</Txt>
                <Segmented testID="edit-role" value={edit.role} onChange={(r) => setEdit({ ...edit, role: r })} options={[{ value: "cleaner", label: "Cleaner" }, { value: "supervisor", label: "Supervisor" }, { value: "owner", label: "Villa owner" }, { value: "admin", label: "Admin" }]} />
              </>
            ) : <Txt v="caption">This is your account — role cannot be changed here.</Txt>}
            {edit.role !== "admin" ? (
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                {(props.data ?? []).map((p) => <Chip key={p.id} testID={`assign-villa-${p.id}`} label={p.name} selected={edit.property_ids.includes(p.id)} onPress={() => setEdit({ ...edit, property_ids: toggle(edit.property_ids, p.id) })} />)}
              </View>
            ) : null}
            <Input testID="edit-name-input" label="Name" value={edit.name} onChangeText={(t) => setEdit({ ...edit, name: t })} />
            <Input testID="edit-phone-input" label="WhatsApp number" keyboardType="phone-pad" value={edit.phone} onChangeText={(t) => setEdit({ ...edit, phone: t })} />
            <Input testID="edit-password-input" label="Set new password (optional)" secureTextEntry value={edit.password} onChangeText={(t) => setEdit({ ...edit, password: t })} placeholder="Leave blank to keep current" />
            <Button testID="assign-save-button" title="Save changes" onPress={saveAssign} />
          </KeyboardAwareScrollView>
        ) : null}
      </Sheet>
      <InviteSheet key={invite ? `${invite.id}-${invite.password ?? ""}` : "none"} invitee={invite} onClose={() => setInvite(null)} />
      <ConfirmSheet visible={!!rm} title="Remove member?" message={`${rm?.name} will no longer be able to sign in.`} confirmLabel="Remove" onClose={() => setRm(null)} onConfirm={async () => { await api.del(`/users/${rm.id}`); setRm(null); q.refetch(); toast("Member removed"); }} />
    </View>
  );
}
