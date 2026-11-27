import React, { useState } from "react";
import { Linking, Share, View } from "react-native";
import { api } from "@/src/api";
import { Button, Input, Sheet, Txt, useToast } from "@/src/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export type Invitee = { id: string; name: string; email?: string; username?: string; phone?: string; role: string; password?: string | null };

const ROLE_LABEL: Record<string, string> = { owner: "property owner", cleaner: "cleaning staff", supervisor: "cleaning supervisor", admin: "admin" };

export function inviteMessage(u: Invitee, password: string) {
  return `Hi ${u.name.replace(/\s*\(Owner\)/, "")}, welcome to Britsmaid!\n\nYour ${ROLE_LABEL[u.role] ?? ""} login is ready:\nLogin: ${u.email || u.username || u.phone}\nPassword: ${password}\n\nOpen the Britsmaid app and sign in with these details${u.role === "owner" ? " to see your villa earnings, stays, payouts and reports" : ""}.\n\n— Team Britsmaid`;
}

export function InviteSheet({ invitee, onClose }: { invitee: Invitee | null; onClose: () => void }) {
  const toast = useToast();
  const { colors } = useTheme();
  const [password, setPassword] = useState("");
  const [verified, setVerified] = useState(false);
  const [phone, setPhone] = useState(invitee?.phone ?? "");
  const [busy, setBusy] = useState(false);
  const pw = invitee?.password || (verified ? password : "");

  if (!invitee) return null;
  const msg = pw ? inviteMessage(invitee, pw) : "";

  const prepare = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/users/${invitee.id}/verify-invite-password`, { password });
      setVerified(true);
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
            <Txt v="body">Enter the current password you set for this member to include it in the invitation. Sending an invitation does not change their password. If you do not know it, set a new password explicitly in Edit member.</Txt>
            <Input testID="invite-password-input" label="Current member password" secureTextEntry autoCapitalize="none" value={password} onChangeText={setPassword} />
            <Input testID="invite-phone-input" label="WhatsApp number" keyboardType="phone-pad" value={phone} onChangeText={setPhone} placeholder="+91 98xxxxxxxx" />
            <Button testID="invite-prepare-button" icon="paper-plane-outline" title="Verify password & prepare invite" onPress={prepare} loading={busy} disabled={busy || password.length < 12} />
          </>
        ) : (
          <>
            <View testID="invite-message" style={{ backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md }}>
              <Txt v="body" style={{ color: colors.onSurface }}>{msg}</Txt>
            </View>
            {!invitee.password ? null : <Input testID="invite-phone-input" label="WhatsApp number" keyboardType="phone-pad" value={phone} onChangeText={setPhone} placeholder="+91 98xxxxxxxx" />}
            <Button testID="invite-whatsapp-button" icon="logo-whatsapp" title={digits ? "Send on WhatsApp" : "Open WhatsApp"} onPress={wa} />
            {invitee.email ? <Button testID="invite-email-button" variant="secondary" icon="mail-outline" title="Send by email" onPress={mail} /> : null}
            <Button testID="invite-share-button" variant="ghost" icon="share-outline" title="Share another way" onPress={() => Share.share({ message: msg })} />
          </>
        )}
      </View>
    </Sheet>
  );
}
