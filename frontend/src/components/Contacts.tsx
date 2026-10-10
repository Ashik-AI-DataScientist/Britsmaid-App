import React, { useState } from "react";
import { Linking, Pressable, View } from "react-native";
import { Badge, Button, Card, Chip, Icon, IconButton, Input, Sheet, Txt, useToast } from "@/src/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export type Contact = { name: string; role: string; phone: string; alt_phone: string; email: string; notes: string; emergency: boolean };
export const CONTACT_ROLES = ["Co-owner", "Family member", "Emergency contact", "Caretaker", "Property manager", "Local contact", "Security", "Maintenance", "Other"];
const blankContact: Contact = { name: "", role: "Emergency contact", phone: "", alt_phone: "", email: "", notes: "", emergency: true };

/** Editable list of owner-related contacts (used in property form). */
export function ContactsEditor({ value, onChange }: { value: Contact[]; onChange: (c: Contact[]) => void }) {
  const { colors } = useTheme();
  const toast = useToast();
  const [edit, setEdit] = useState<{ idx: number; c: Contact } | null>(null);

  const save = () => {
    if (!edit) return;
    if (!edit.c.name.trim() || !edit.c.phone.trim()) return toast("Name and phone are required", "error");
    const next = [...value];
    if (edit.idx < 0) next.push(edit.c);
    else next[edit.idx] = edit.c;
    onChange(next);
    setEdit(null);
  };

  return (
    <View style={{ gap: spacing.sm }}>
      {value.map((c, i) => (
        <Pressable key={i} testID={`contact-edit-${i}`} onPress={() => setEdit({ idx: i, c })} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary }}>
          <Icon name={c.emergency ? "alert-circle" : "person-circle-outline"} size={22} color={c.emergency ? colors.error : colors.brandPrimary} />
          <View style={{ flex: 1 }}>
            <Txt v="subtitle" style={{ fontSize: 14 }}>{c.name}</Txt>
            <Txt v="caption">{c.role} · {c.phone}</Txt>
          </View>
          <Pressable testID={`contact-remove-${i}`} hitSlop={8} onPress={() => onChange(value.filter((_, j) => j !== i))}>
            <Icon name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </Pressable>
      ))}
      <Button testID="contact-add-button" small variant="secondary" icon="person-add-outline" title="Add contact" onPress={() => setEdit({ idx: -1, c: { ...blankContact } })} />
      <Sheet visible={!!edit} onClose={() => setEdit(null)} title={edit && edit.idx >= 0 ? "Edit contact" : "Add contact"} testID="contact-sheet">
        {edit ? (
          <View style={{ gap: spacing.md }}>
            <Txt v="label">Who are they?</Txt>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {CONTACT_ROLES.map((r) => <Chip key={r} testID={`contact-role-${r}`} label={r} selected={edit.c.role === r} onPress={() => setEdit({ ...edit, c: { ...edit.c, role: r } })} />)}
            </View>
            <Input testID="contact-name-input" label="Name" value={edit.c.name} onChangeText={(t) => setEdit({ ...edit, c: { ...edit.c, name: t } })} />
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}><Input testID="contact-phone-input" label="Phone" keyboardType="phone-pad" value={edit.c.phone} onChangeText={(t) => setEdit({ ...edit, c: { ...edit.c, phone: t } })} /></View>
              <View style={{ flex: 1 }}><Input testID="contact-alt-phone-input" label="Alternate phone" keyboardType="phone-pad" value={edit.c.alt_phone} onChangeText={(t) => setEdit({ ...edit, c: { ...edit.c, alt_phone: t } })} /></View>
            </View>
            <Input testID="contact-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={edit.c.email} onChangeText={(t) => setEdit({ ...edit, c: { ...edit.c, email: t } })} />
            <Input testID="contact-notes-input" label="Notes (relation, availability...)" value={edit.c.notes} onChangeText={(t) => setEdit({ ...edit, c: { ...edit.c, notes: t } })} />
            <Chip testID="contact-emergency-toggle" label={edit.c.emergency ? "✓ Emergency contact" : "Mark as emergency contact"} selected={edit.c.emergency} onPress={() => setEdit({ ...edit, c: { ...edit.c, emergency: !edit.c.emergency } })} />
            <Button testID="contact-save-button" title="Save contact" onPress={save} />
          </View>
        ) : null}
      </Sheet>
    </View>
  );
}

function ContactRow({ name, role, phone, alt, email, notes, emergency, testID }: { name: string; role: string; phone?: string; alt?: string; email?: string; notes?: string; emergency?: boolean; testID: string }) {
  const { colors } = useTheme();
  const digits = (phone ?? "").replace(/[^\d]/g, "");
  return (
    <View testID={testID} style={{ paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: 4 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <Txt v="subtitle" style={{ fontSize: 15 }}>{name}</Txt>
          <View style={{ flexDirection: "row", gap: 6, marginTop: 2 }}>
            <Badge label={role} tone="brand" />
            {emergency ? <Badge label="Emergency" tone="error" /> : null}
          </View>
        </View>
        {phone ? <IconButton testID={`${testID}-call`} name="call" tone="brand" size={18} onPress={() => Linking.openURL(`tel:${phone}`)} /> : null}
        {digits ? <IconButton testID={`${testID}-whatsapp`} name="logo-whatsapp" tone="brand" size={18} onPress={() => Linking.openURL(`https://wa.me/${digits.length === 10 ? `91${digits}` : digits}`)} /> : null}
      </View>
      {phone ? <Txt v="body">{phone}{alt ? ` · ${alt}` : ""}</Txt> : null}
      {email ? <Txt v="caption">{email}</Txt> : null}
      {notes ? <Txt v="caption">{notes}</Txt> : null}
    </View>
  );
}

/** Read-only owner & contacts card grouped by who they are. */
export function ContactsCard({ p }: { p: any }) {
  const contacts: Contact[] = p.contacts ?? [];
  const emergency = contacts.filter((c) => c.emergency);
  const groups: Record<string, Contact[]> = {};
  for (const c of contacts.filter((x) => !x.emergency)) (groups[c.role] ??= []).push(c);
  return (
    <Card testID="property-contacts-card">
      <Txt v="label">Owner</Txt>
      <ContactRow testID="contact-owner" name={p.owner_name || "—"} role="Owner" phone={p.owner_phone} alt={p.owner_alt_phone} email={p.owner_email} notes={p.owner_address} />
      {emergency.length ? <Txt v="label" style={{ marginTop: spacing.md }}>Emergency contacts</Txt> : null}
      {emergency.map((c, i) => <ContactRow key={`e${i}`} testID={`contact-emergency-${i}`} name={c.name} role={c.role} phone={c.phone} alt={c.alt_phone} email={c.email} notes={c.notes} emergency />)}
      {Object.entries(groups).map(([role, list]) => (
        <View key={role}>
          <Txt v="label" style={{ marginTop: spacing.md }}>{role}</Txt>
          {list.map((c, i) => <ContactRow key={i} testID={`contact-${role.replace(/\s/g, "-")}-${i}`} name={c.name} role={c.role} phone={c.phone} alt={c.alt_phone} email={c.email} notes={c.notes} />)}
        </View>
      ))}
      {!contacts.length ? <Txt v="caption" style={{ marginTop: spacing.sm }}>No emergency or other contacts yet — add them via Edit property.</Txt> : null}
    </Card>
  );
}
