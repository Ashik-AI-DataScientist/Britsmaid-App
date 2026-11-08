export type CaptureTarget = { key: string; label: string; taskId?: string; roomIndex?: number; roomName?: string; phase?: "before" | "after"; revision?: number };
export type CaptureMedia = { id: string; kind: "image" | "video"; content_type: string };
export type CaptureAsset = { uri: string; file?: Blob; type?: string | null; mimeType?: string; fileName?: string | null; fileSize?: number; uploadKey?: string; width: number; height: number };
export function webCaptureBlob(asset: CaptureAsset): Blob {
  // Expo supplies the selected File directly. Fetching its blob: URL is blocked
  // by the hosted connect-src policy and is unnecessary for a multipart upload.
  if (typeof Blob !== "undefined" && asset.file instanceof Blob) return asset.file;
  // A File cannot survive JSON storage or a page reload. Never fetch an expired
  // object URL or substitute another file for the original capture target.
  throw new Error("This photo is no longer available in this browser. Discard the unsaved photo, then choose it from your library again.");
}
export type CaptureDraft = { userId: string; target: CaptureTarget; assets: CaptureAsset[]; uploaded?: CaptureMedia; startedAt: string };
export const DRAFT_KEY = "bm_capture_v1";
// One lock across all sheets: React state updates alone cannot stop two rapid taps.
let pickerOwner: object | null = null;
export function acquirePicker(owner: object) { if (pickerOwner) return false; pickerOwner = owner; return true; }
export function releasePicker(owner: object) { if (pickerOwner === owner) pickerOwner = null; }
export class CaptureQueue {
  busy = false;
  constructor(public draft: CaptureDraft, private deps: {
    persist: (draft: CaptureDraft | null) => Promise<void>;
    upload: (asset: CaptureAsset) => Promise<CaptureMedia>;
    attach: (media: CaptureMedia[], target: CaptureTarget) => Promise<void>;
    isCurrent: () => boolean;
  }) {}
  async save() {
    if (this.busy) return false;
    this.busy = true;
    try {
      while (this.draft.assets.length || this.draft.uploaded) {
        if (!this.deps.isCurrent()) throw new Error("Your session changed. Sign in to the original account to resume this photo.");
        if (!this.draft.uploaded) {
          this.draft.uploaded = await this.deps.upload(this.draft.assets[0]);
          await this.deps.persist(this.draft);
        }
        if (!this.deps.isCurrent()) throw new Error("Your session changed. Sign in to the original account to resume this photo.");
        await this.deps.attach([this.draft.uploaded], this.draft.target);
        this.draft.uploaded = undefined;
        this.draft.assets.shift();
        await this.deps.persist(this.draft.assets.length ? this.draft : null);
      }
      return true;
    } finally { this.busy = false; }
  }
}

export function captureMediaTypes(mode: "photo" | "video" | "library", allowVideo = false): ("images" | "videos")[] {
  return mode === "video" ? ["videos"] : mode === "library" && allowVideo ? ["images", "videos"] : ["images"];
}
