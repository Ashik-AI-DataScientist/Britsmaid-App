import React, { useState } from "react";
import { Linking, Platform, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Button, Sheet, Txt, useToast } from "@/src/ui";
import { request } from "@/src/api";
import { spacing } from "@/src/theme";

export type Media = { id: string; kind: "image" | "video"; content_type: string };

async function uploadAsset(a: ImagePicker.ImagePickerAsset): Promise<Media> {
  const isVideo = a.type === "video";
  const type = a.mimeType || (isVideo ? "video/mp4" : "image/jpeg");
  const name = a.fileName || `capture-${Date.now()}.${isVideo ? "mp4" : "jpg"}`;
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(a.uri)).blob();
    form.append("file", blob, name);
  } else {
    form.append("file", { uri: a.uri, name, type } as any);
  }
  return request<Media>("/upload", { method: "POST", form });
}

type PermState = "unknown" | "denied" | "blocked";

export function CaptureSheet({ visible, onClose, onUploaded, allowVideo, purpose, testID = "capture-sheet" }: {
  visible: boolean; onClose: () => void; onUploaded: (m: Media[]) => void; allowVideo?: boolean; purpose: string; testID?: string;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [perm, setPerm] = useState<PermState>("unknown");

  const ensure = async (camera: boolean) => {
    const get = camera ? ImagePicker.getCameraPermissionsAsync : ImagePicker.getMediaLibraryPermissionsAsync;
    const ask = camera ? ImagePicker.requestCameraPermissionsAsync : ImagePicker.requestMediaLibraryPermissionsAsync;
    let p = await get();
    if (p.granted) return true;
    if (!p.canAskAgain) { setPerm("blocked"); return false; }
    p = await ask();
    if (p.granted) { setPerm("unknown"); return true; }
    setPerm(p.canAskAgain ? "denied" : "blocked");
    return false;
  };

  const run = async (mode: "photo" | "video" | "library") => {
    try {
      const camera = mode !== "library";
      if (Platform.OS !== "web" && !(await ensure(camera))) return;
      const mediaTypes: ImagePicker.MediaType[] = mode === "photo" ? ["images"] : mode === "video" ? ["videos"] : allowVideo ? ["images", "videos"] : ["images"];
      const opts: ImagePicker.ImagePickerOptions = { mediaTypes, quality: 0.6, videoMaxDuration: 60, allowsMultipleSelection: mode === "library", selectionLimit: 10 };
      const res = camera && Platform.OS !== "web" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
      if (res.canceled || !res.assets?.length) return;
      setBusy(true);
      const uploaded: Media[] = [];
      for (const a of res.assets) uploaded.push(await uploadAsset(a));
      onUploaded(uploaded);
      toast(`${uploaded.length} file${uploaded.length > 1 ? "s" : ""} uploaded`);
      onClose();
    } catch (e: any) {
      toast(e.message || "Upload failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet visible={visible} onClose={onClose} title="Add media" testID={testID}>
      <Txt v="body" style={{ marginBottom: spacing.lg }}>{purpose}</Txt>
      {perm !== "unknown" ? (
        <View testID="permission-notice" style={{ marginBottom: spacing.lg, gap: spacing.sm }}>
          <Txt v="body" color="#B45309">
            {perm === "blocked" ? "Access is turned off. Enable camera / photos for Britsmaid in Settings to continue." : "Permission was declined. Tap again to allow access."}
          </Txt>
          {perm === "blocked" ? <Button small variant="secondary" icon="settings-outline" title="Open Settings" onPress={() => Linking.openSettings()} testID="open-settings-button" /> : null}
        </View>
      ) : null}
      <View style={{ gap: spacing.sm }}>
        <Button testID={`${testID}-take-photo`} icon="camera" title="Take photo" onPress={() => run("photo")} loading={busy} />
        {allowVideo ? <Button testID={`${testID}-record-video`} icon="videocam" variant="secondary" title="Record video" onPress={() => run("video")} disabled={busy} /> : null}
        <Button testID={`${testID}-library`} icon="images" variant="secondary" title="Choose from library" onPress={() => run("library")} disabled={busy} />
      </View>
    </Sheet>
  );
}
