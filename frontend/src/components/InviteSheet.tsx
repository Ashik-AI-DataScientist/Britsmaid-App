import React, { useState } from "react";
import { Linking, Share, View } from "react-native";
import { api } from "@/src/api";
import { Button, Input, Sheet, Txt, useToast } from "@/src/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export type Invitee = { id: string; name: string; email: string; phone?: string; role: string; password?: string | null };

const ROLE_LABEL: Record<string, string> = { owner: "villa owner", cleaner: "cleaning staff", admin: "admin" };

export function inviteMessage(u: Invitee, password: string) {
  return `Hi ${u.name.replace(/\s*\(Owner\)/, "")}, welcome to Britsmaid!\n\nYour ${ROLE_LABEL[u.role] ?? ""} login is ready:\nEmail: ${u.email}\nPassword: ${password}\n\nOpen the Britsmaid app and sign in with these details${u.role === "owner" ? " to see your villa earnings, stays, payouts and reports" : ""}. If this is your Google email you can also tap "Continue with Google".\n\n— Team Britsmaid`;
}

export function InviteSheet({ invitee, onClose }: { invitee: Invitee | null; onClose: () => void }) {
  const toast = useToast();
  const { colors } = useTheme();
  const [password, setPassword] = useState<string | null>(null);
  const [phone, setPhone] = useState(invitee?.phone ?? "");
  const [busy, setBusy] = useState(false);
  const pw = invitee?.password ?? password;

  if (!invitee) return null;
  const msg = pw ? inviteMessage(invitee, pw) : "";

  const reset = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/users/${invitee.id}/reset-password`);
      setPassword(r.temp_password);
      if (phone !== (invitee.phone ?? "")) await api.put(`/users/${invitee.id}`, { phone });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const open = async (url: string) => {
    try {
      await Linking.openURL(url);
    } catch {
      toast("Could not open the app on this device", "error");
    }
  };
  const digits = phone.replace(/[^\d]/g, "");
  const wa = () => open(`https://wa.me/${digits.length === 10 ? `91${digits}` : digits}?text=${encodeURIComponent(msg)}`);
  const mail = () => open(`mailto:${invitee.email}?subject=${encodeURIComponent("Your Britsmaid login")}&body=${encodeURIComponent(msg)}`);

  return (
    <Sheet visible={!!invitee} onClose={onClose} title={`Invite ${invitee.name}`} testID="invite-sheet">
      <View style={{ gap: spacing.md }}>
        {!pw ? (
          <>
            <Txt v="body">A new temporary password will be created for {invitee.email}. Their old password will stop working.</Txt>
            <Input testID="invite-phone-input" label="WhatsApp number" keyboardType="phone-pad" value={phone} onChangeText={setPhone} placeholder="+91 98xxxxxxxx" />
            <Button testID="invite-generate-button" icon="key-outline" title="Create password & prepare invite" onPress={reset} loading={busy} />
          </>
        ) : (
          <>
            <View testID="invite-message" style={{ backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md }}>
              <Txt v="body" style={{ color: colors.onSurface }}>{msg}</Txt>
            </View>
            {!invitee.password ? null : <Input testID="invite-phone-input" label="WhatsApp number" keyboardType="phone-pad" value={phone} onChangeText={setPhone} placeholder="+91 98xxxxxxxx" />}
            <Button testID="invite-whatsapp-button" icon="logo-whatsapp" title={digits ? "Send on WhatsApp" : "Open WhatsApp"} onPress={wa} />
            <Button testID="invite-email-button" variant="secondary" icon="mail-outline" title="Send by email" onPress={mail} />
            <Button testID="invite-share-button" variant="ghost" icon="share-outline" title="Share another way" onPress={() => Share.share({ message: msg })} />
          </>
        )}
      </View>
    </Sheet>
  );
}
