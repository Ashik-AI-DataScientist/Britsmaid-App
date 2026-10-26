import React, { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { Button, Card, Chip, ConfirmSheet, ErrorState, Header, Icon, Input, Loading, Segmented, Txt, useToast } from "@/src/ui";
import { OTAS, otaColor } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";
import { Contact, ContactsEditor } from "@/src/components/Contacts";
import { CalendarExport } from "@/src/components/CalendarExport";
import { CaptureSheet } from "@/src/components/CaptureSheet";
import { PropertyCover } from "@/src/components/PropertyCover";

const blank = { name: "", location: "", owner_name: "", owner_email: "", owner_phone: "", owner_alt_phone: "", owner_address: "", contacts: [] as Contact[], owner_share_percent: "70", electricity_mode: "owner" as "owner" | "split_half", base_rate: "", rooms: ["Living Room", "Kitchen", "Bedroom 1", "Bathroom 1"], ical_feeds: [] as { ota: string; url: string; last_synced?: string | null }[], cover_url: "", notes: "" };

export default function EditProperty() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const [f, setF] = useState(blank);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [room, setRoom] = useState("");
  const [feedOta, setFeedOta] = useState("Airbnb");
  const [feedUrl, setFeedUrl] = useState("");
  const [del, setDel] = useState(false);
  const [captureCover, setCaptureCover] = useState(false);
  const [coverId, setCoverId] = useState("");
  const remove = async () => {
    try {
      await api.del(`/properties/${id}`);
      qc.invalidateQueries();
      setDel(false);
      toast("Property deleted");
      router.dismissAll();
      router.replace("/(admin)/properties");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  useEffect(() => {
    if (!id) return;
    let alive = true;
    api.get(`/properties/${id}`).then((p) => {
      if (!alive) return;
      setF({ ...blank, ...p, owner_share_percent: String(p.owner_share_percent), base_rate: String(p.base_rate || "") });
      setCoverId(p.cover_media_id || "");
      setLoading(false);
    }).catch((e) => { if (alive) { setLoadError(e.message); setLoading(false); } });
    return () => { alive = false; };
  }, [id, loadAttempt]);

  const set = (k: keyof typeof blank) => (v: any) => setF((x) => ({ ...x, [k]: v }));

  const save = async () => {
    const pct = Number(f.owner_share_percent);
    if (!f.name.trim()) return toast("Property name is required", "error");
    if (isNaN(pct) || pct < 0 || pct > 100) return toast("Owner share must be 0–100%", "error");
    if (!f.rooms.length) return toast("Add at least one room", "error");
    setSaving(true);
    const body = { ...f, cover_media_id: coverId, owner_share_percent: pct, base_rate: Number(f.base_rate) || 0 };
    try {
      const res = id ? await api.put(`/properties/${id}`, body) : await api.post("/properties", body);
      qc.invalidateQueries();
      toast(id ? "Property updated" : "Property added");
      if (id) router.back();
      else router.replace(`/property/${res.id}`);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading />;
  if (loadError) return <View style={{flex:1}}><Header back title="Property" /><ErrorState message={loadError} onRetry={() => { setLoadError(""); setLoading(true); setLoadAttempt(x=>x+1); }} /></View>;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={id ? "Edit property" : "New property"} />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">Villa</Txt>
          <Input testID="property-name-input" label="Name" value={f.name} onChangeText={set("name")} placeholder="Villa Azure" />
          <Input testID="property-location-input" label="Location" value={f.location} onChangeText={set("location")} placeholder="Candolim, Goa" />
          <Input testID="property-rate-input" label="Base nightly rate ₹" keyboardType="numeric" value={f.base_rate} onChangeText={set("base_rate")} />
          <Txt v="label">Villa cover photo (optional)</Txt>
          {coverId || f.cover_url ? <View style={{ height: 180, overflow: "hidden", borderRadius: 12 }}><PropertyCover property={{ cover_media_id: coverId, cover_url: f.cover_url }} /></View> : <Txt v="caption">Choose a photo of this villa, or take one with your camera.</Txt>}
          <Button testID="property-cover-add" title={coverId || f.cover_url ? "Change cover photo" : "Add cover photo"} icon="camera" disabled={saving} onPress={() => setCaptureCover(true)} />
          {coverId || f.cover_url ? <Button title="Remove cover photo" variant="ghost" disabled={saving} onPress={() => { setCoverId(""); set("cover_url")(""); }} /> : null}
          <Txt v="caption">After choosing your photo, tap {id ? "Save changes" : "Add property"} below to save it.</Txt>
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">Owner & revenue sharing</Txt>
          <Input testID="property-owner-name-input" label="Owner name" value={f.owner_name} onChangeText={set("owner_name")} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}><Input testID="property-owner-phone-input" label="Phone" keyboardType="phone-pad" value={f.owner_phone} onChangeText={set("owner_phone")} /></View>
            <View style={{ flex: 1 }}><Input testID="property-owner-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.owner_email} onChangeText={set("owner_email")} /></View>
          </View>
          <Input testID="property-owner-alt-phone-input" label="Alternate phone" keyboardType="phone-pad" value={f.owner_alt_phone} onChangeText={set("owner_alt_phone")} />
          <Input testID="property-owner-address-input" label="Owner address" value={f.owner_address} onChangeText={set("owner_address")} />
          <Input testID="property-share-input" label="Owner share %" keyboardType="numeric" value={f.owner_share_percent} onChangeText={set("owner_share_percent")} />
          <Txt v="caption">Britsmaid keeps {100 - (Number(f.owner_share_percent) || 0)}% of net revenue (after OTA commissions).</Txt>
          <Txt v="label">Electricity bill</Txt>
          <Segmented testID="property-electricity-mode" value={f.electricity_mode} onChange={set("electricity_mode")} options={[{ value: "owner", label: "Owner pays all" }, { value: "split_half", label: "Britsmaid pays 50%" }]} />
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">Emergency & other contacts</Txt>
          <Txt v="caption">Co-owners, family, caretakers, local emergency contacts — tag who each person is.</Txt>
          <ContactsEditor value={f.contacts} onChange={set("contacts")} />
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">Rooms & common areas</Txt>
          <Txt v="caption">Cleaning staff must photograph each before & after.</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {f.rooms.map((r, i) => (
              <Pressable key={`${r}-${i}`} testID={`room-chip-${i}`} onPress={() => set("rooms")(f.rooms.filter((_, j) => j !== i))} style={{ flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md, height: 36 }}>
                <Txt v="caption" color={colors.onBrandTertiary}>{r}</Txt>
                <Icon name="close" size={14} color={colors.onBrandTertiary} />
              </Pressable>
            ))}
          </View>
          <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
            <View style={{ flex: 1 }}><Input testID="room-name-input" placeholder="e.g. Pool Deck" value={room} onChangeText={setRoom} onSubmitEditing={() => { if (room.trim()) { set("rooms")([...f.rooms, room.trim()]); setRoom(""); } }} /></View>
            <Button testID="room-add-button" small title="Add" onPress={() => { if (room.trim()) { set("rooms")([...f.rooms, room.trim()]); setRoom(""); } }} />
          </View>
        </Card>
        <Card style={{ gap: spacing.md }}>
          <Txt v="label">OTA iCal links</Txt>
          <Txt v="caption">Paste the calendar export link from each OTA extranet to sync bookings automatically.</Txt>
          {f.ical_feeds.map((fd, i) => (
            <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: otaColor(fd.ota) }} />
              <View style={{ flex: 1 }}>
                <Txt v="body" style={{ color: colors.onSurface }}>{fd.ota}</Txt>
                <Txt v="caption" numberOfLines={1}>{fd.url}</Txt>
              </View>
              <Pressable testID={`feed-remove-${i}`} hitSlop={8} onPress={() => set("ical_feeds")(f.ical_feeds.filter((_, j) => j !== i))}>
                <Icon name="trash-outline" size={18} color={colors.error} />
              </Pressable>
            </View>
          ))}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {OTAS.filter((o) => o !== "Direct").map((o) => <Chip key={o} testID={`feed-ota-${o}`} label={o} dot={otaColor(o)} selected={feedOta === o} onPress={() => setFeedOta(o)} />)}
          </View>
          <Input testID="feed-url-input" placeholder="https://www.airbnb.com/calendar/ical/....ics" value={feedUrl} onChangeText={setFeedUrl} autoCapitalize="none" />
          <Button testID="feed-add-button" small variant="secondary" icon="link" title={`Add ${feedOta} link`} onPress={() => {
            if (!/^https?:\/\//.test(feedUrl.trim())) return toast("Enter a valid https iCal link", "error");
            set("ical_feeds")([...f.ical_feeds, { ota: feedOta, url: feedUrl.trim(), last_synced: null }]);
            setFeedUrl("");
          }} />
        </Card>
        {id ? <CalendarExport propertyId={id} /> : null}
        <Input testID="property-notes-input" label="Notes" multiline value={f.notes} onChangeText={set("notes")} />
        <Button testID="property-save-button" title={id ? "Save changes" : "Add property"} onPress={save} loading={saving} />
        {id ? <Button testID="property-delete-from-edit" variant="danger" icon="trash-outline" title="Delete property" onPress={() => setDel(true)} /> : null}
      </KeyboardAwareScrollView>
      <CaptureSheet visible={captureCover} onClose={() => setCaptureCover(false)} singleSelection testID="property-cover-picker" destination={{ key: `property-cover:${id || "new"}`, label: "Villa cover photo" }} purpose="Take a villa photo or choose one from your gallery." successMessage="Cover photo ready. Save the property below to keep it." onUploaded={async (media, target) => {
        if (target.key !== `property-cover:${id || "new"}` || media.length !== 1 || media[0].kind !== "image") throw new Error("Return to the original villa and choose one photo.");
        setCoverId(media[0].id); set("cover_url")("");
      }} />
      <ConfirmSheet visible={del} title="Delete property?" message={`${f.name} will be removed from all lists. Past bookings and reports are kept.`} onConfirm={remove} onClose={() => setDel(false)} />
    </View>
  );
}
