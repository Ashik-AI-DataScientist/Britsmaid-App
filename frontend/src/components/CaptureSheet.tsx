import React, { useEffect, useRef, useState } from "react";
import { Alert, Linking, Platform, ScrollView, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as FileSystem from "expo-file-system/legacy";
import { Button, Sheet, Txt, useToast } from "@/src/ui";
import { getAuthEpoch, request } from "@/src/api";
import { useAuth } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { spacing } from "@/src/theme";
import { acquirePicker, CaptureAsset, CaptureDraft, CaptureQueue, CaptureTarget, DRAFT_KEY, releasePicker } from "@/src/capture-workflow";
export type Media = { id: string; kind: "image" | "video"; content_type: string };
async function uploadAsset(a: CaptureAsset): Promise<Media> {
  if (a.fileSize && a.fileSize > 100 * 1024 * 1024) throw new Error("Choose a file smaller than 100 MB.");
  const isVideo = a.type === "video";
  const type = a.mimeType || (isVideo ? "video/mp4" : "image/jpeg");
  const name = a.fileName || `capture-${Date.now()}.${isVideo ? "mp4" : "jpg"}`;
  const form = new FormData();
  if (a.uploadKey) form.append("request_key", a.uploadKey);
  if (Platform.OS === "web") {
    const blob = await (await fetch(a.uri)).blob();
    form.append("file", blob, name);
  } else form.append("file", { uri: a.uri, name, type } as any);
  return request<Media>("/upload", { method: "POST", form });
}
async function persist(d: CaptureDraft | null, ownerId?: string) {
  const ok = d ? await storage.setItem(`${DRAFT_KEY}:${d.userId}`, JSON.stringify(d)) : await storage.removeItem(`${DRAFT_KEY}:${ownerId}`);
  if (!ok) throw new Error("Could not preserve the pending photo on this device. Keep this screen open and retry.");
}
async function keepAsset(a: ImagePicker.ImagePickerAsset): Promise<CaptureAsset> {
  const uploadKey = `photo_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  if (Platform.OS === "web") return { ...a, uploadKey };
  const dir = `${FileSystem.documentDirectory}capture-drafts/`;
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
  const uri = `${dir}${Date.now()}-${Math.random().toString(36).slice(2)}.${a.type === "video" ? "mp4" : "jpg"}`;
  await FileSystem.copyAsync({ from: a.uri, to: uri });
  return { ...a, uri, uploadKey };
}
async function cleanup(d: CaptureDraft) {
  if (Platform.OS !== "web") for (const a of d.assets) if (a.uri.startsWith(`${FileSystem.documentDirectory}capture-drafts/`)) await FileSystem.deleteAsync(a.uri, { idempotent: true }).catch(() => {});
}
export function CaptureSheet({ visible, onClose, onUploaded, allowVideo, purpose, successMessage, destination, onRestore, testID = "capture-sheet" }: {
  visible: boolean; onClose: () => void; onUploaded: (m: Media[], target: CaptureTarget) => Promise<void>;
  allowVideo?: boolean; purpose: string; successMessage?: string; destination?: CaptureTarget; onRestore?: (target: CaptureTarget) => void; testID?: string;
}) {
  const toast = useToast();
  const { user } = useAuth();
  const actor = useRef(user?.id);
  const lock = useRef({});
  const [busy, setBusy] = useState(false);
  const [perm, setPerm] = useState<"unknown" | "denied" | "blocked">("unknown");
  const [pending, setPending] = useState<CaptureDraft | null>(null);
  const [failure, setFailure] = useState("");
  const [discard, setDiscard] = useState(false);
  const callback = useRef(onUploaded);
  const restore = useRef(onRestore);
  useEffect(() => { actor.current = user?.id; callback.current = onUploaded; restore.current = onRestore; }, [user?.id, onUploaded, onRestore]);
  const taskId = destination?.taskId;
  useEffect(() => {
    let alive = true;
    (async () => {
      const raw = await storage.getItem(`${DRAFT_KEY}:${user?.id}`, "");
      if (!raw || !alive) return;
      let d: CaptureDraft;
      try { d = JSON.parse(raw); } catch { return; }
      if (d.userId !== user?.id || (d.target.taskId ? d.target.taskId !== taskId : d.target.key !== destination?.key)) return;
      if (Platform.OS === "android") {
        const result = await ImagePicker.getPendingResultAsync();
        if (result && !("code" in result) && !result.canceled && result.assets?.length && !d.assets.length && !d.uploaded) {
          d.assets = await Promise.all(result.assets.map(keepAsset)); await persist(d);
        } else if (result && "code" in result) setFailure("The camera could not recover its result. Please take the photo again.");
      }
      if (!alive) return;
      if (!d.assets.length && !d.uploaded) { await persist(null, user?.id); return; }
      setPending(d); restore.current?.(d.target);
      setFailure("A photo is waiting to be saved to its original destination. Check the task, then retry.");
    })().catch(() => { if (alive) setFailure("Could not restore the pending photo. Keep this screen open and try again."); });
    return () => { alive = false; };
  }, [user?.id, taskId, destination?.key]);

  const save = async (d: CaptureDraft, epoch: number) => {
    setPending(d);
    const originals = { ...d, assets: [...d.assets] };
    const queue = new CaptureQueue(d, { persist: async next => { await persist(next, d.userId); setPending(next); }, upload: uploadAsset,
      attach: (m, target) => callback.current(m, target), isCurrent: () => actor.current === d.userId && getAuthEpoch() === epoch });
    await queue.save();
    await cleanup(originals);
    toast(successMessage ?? ("Saved to " + d.target.label)); setPending(null); setFailure(""); onClose();
  };
  const run = async (mode: "photo" | "video" | "library") => {
    if (!user || pending || !acquirePicker(lock.current)) return;
    setBusy(true); setFailure("");
    let d: CaptureDraft | null = null;
    try {
      const old = await storage.getItem(`${DRAFT_KEY}:${user?.id}`, "");
      if (old) {
        const previous: CaptureDraft = JSON.parse(old);
        if (previous.userId !== user.id || previous.assets.length || previous.uploaded) throw new Error("There is an unsaved photo. Return to its original task and save or discard it first.");
      }
      const camera = mode !== "library";
      if (Platform.OS !== "web" && camera) {
        let p = await ImagePicker.getCameraPermissionsAsync();
        if (!p.granted && p.canAskAgain) p = await ImagePicker.requestCameraPermissionsAsync();
        if (!p.granted) { setPerm(p.canAskAgain ? "denied" : "blocked"); return; }
      }
      setPerm("unknown");
      const target = destination ?? { key: purpose, label: purpose };
      d = { userId: user.id, target: { ...target }, assets: [], startedAt: new Date().toISOString() };
      const epoch = getAuthEpoch();
      await persist(d);
      const opts: ImagePicker.ImagePickerOptions = { mediaTypes: mode === "video" ? ["videos"] : mode === "photo" ? ["images"] : allowVideo ? ["images", "videos"] : ["images"], quality: 0.6, videoMaxDuration: 60, allowsMultipleSelection: false };
      const result = camera ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
      if (result.canceled || !result.assets?.length) { await persist(null, user?.id); return; }
      d.assets = await Promise.all(result.assets.map(keepAsset));
      await persist(d); await save(d, epoch);
    } catch (e: any) { if (d?.assets.length || d?.uploaded) setPending(d); setFailure(e.message || "Photo was not saved. Please retry."); }
    finally { setBusy(false); releasePicker(lock.current); }
  };
  // Web must invoke the picker synchronously in the user's gesture, before any storage/permission await.
  const runWeb = (camera: boolean) => {
    if (!user || pending || !acquirePicker(lock.current)) return;
    setBusy(true); setFailure("");
    const d: CaptureDraft = { userId: user.id, target: { ...(destination ?? { key: purpose, label: purpose }) }, assets: [], startedAt: new Date().toISOString() };
    const epoch = getAuthEpoch();
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], allowsMultipleSelection: false, quality: 0.6, cameraType: ImagePicker.CameraType.back };
    const result = camera ? ImagePicker.launchCameraAsync(options) : ImagePicker.launchImageLibraryAsync(options);
    // Browser cancellation is inconsistent: explicit reset releases a stuck picker without permitting late results.
    const owner = lock.current;
    result.then(async r => {
      if (lock.current !== owner) return;
      if (r.canceled || !r.assets?.length) return;
      const old = await storage.getItem(`${DRAFT_KEY}:${user?.id}`, "");
      if (old) { const previous: CaptureDraft = JSON.parse(old); if (previous.userId !== user.id || previous.assets.length || previous.uploaded) throw new Error("Save or discard the previous photo from its original task first."); }
      d.assets = await Promise.all(r.assets.map(keepAsset));
      setPending(d);
      await persist(d); await save(d, epoch);
    }).catch(e => { if (d.assets.length || d.uploaded) setPending(d); setFailure(e.message || "Photo could not be saved."); })
      .finally(() => { releasePicker(owner); if (lock.current === owner) setBusy(false); });
  };
  const close = () => { if (busy) return; if (pending) { setFailure("This photo has not been saved. Retry or explicitly discard it before closing."); return; } onClose(); };
  return <Sheet visible={visible} onClose={close} title="Add photo" testID={testID}><ScrollView contentContainerStyle={{ gap: spacing.sm }}>
    <Txt v="subtitle">{pending?.target.label ?? destination?.label ?? purpose}</Txt>
    <Txt>{purpose}</Txt>
    {Platform.OS === "web" ? <Txt v="caption">Take photo requests your phone camera. Some browsers show a file chooser instead. You can take a photo in your camera app, then choose it from the library. Keep this page open until saved.</Txt> : null}
    {failure ? <View accessibilityRole="alert"><Txt color="#B45309">{failure}</Txt></View> : null}
    {perm !== "unknown" ? <View><Txt>{perm === "blocked" ? "Camera access is off. Enable it in your phone Settings, or choose an existing photo." : "Camera permission was declined. Try again or choose an existing photo."}</Txt>{perm === "blocked" ? <Button title="Open Settings" variant="secondary" onPress={() => Linking.openSettings()} /> : null}</View> : null}
    {pending ? <><Button title={pending.uploaded ? "Retry saving to room" : "Retry upload and save"} loading={busy} onPress={async () => { if (!acquirePicker(lock.current)) return; setBusy(true); try { await save(pending, getAuthEpoch()); } catch(e:any) { setFailure(e.message); } finally { setBusy(false); releasePicker(lock.current); } }} />
      <Button title="Discard unsaved photo" variant="ghost" disabled={busy} onPress={() => setDiscard(true)} />
      {discard ? <><Txt>Discard this pending photo? It will not be attached. An already uploaded file may remain until storage cleanup.</Txt><Button title="Yes, discard photo" variant="danger" disabled={busy} onPress={async () => { try { await cleanup(pending); await persist(null, user?.id); setPending(null); setDiscard(false); setFailure(""); onClose(); } catch { setFailure("Could not discard the draft. Try again."); } }} /><Button title="Keep photo" variant="secondary" onPress={() => setDiscard(false)} /></> : null}</> : <>
      <Button title="Take photo" testID={`${testID}-take-photo`} icon="camera" loading={busy} onPress={() => Platform.OS === "web" ? runWeb(true) : run("photo")} />
      {allowVideo && Platform.OS !== "web" ? <Button title="Record video" disabled={busy} variant="secondary" onPress={() => { Alert.alert("Walkthrough video", "Video may require microphone permission. Only record non-private property areas.", [{ text: "Cancel" }, { text: "Continue", onPress: () => run("video") }]); }} /> : null}
      <Button title="Choose from library" testID={`${testID}-library`} icon="images" disabled={busy} variant="secondary" onPress={() => Platform.OS === "web" ? runWeb(false) : run("library")} />
    </>}
    {Platform.OS === "web" && busy ? <Button title="Camera cancelled? Return to options" variant="ghost" onPress={() => { const previous=lock.current; releasePicker(previous); lock.current={}; setBusy(false); }} /> : null}
    <Button title="Close" variant="ghost" disabled={busy} onPress={close} />
  </ScrollView></Sheet>;
}
