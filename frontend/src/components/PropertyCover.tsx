import React from "react";
import { Image } from "expo-image";
import { fileUrl } from "@/src/api";

// Save only the media ID; signed-in display URLs must never be stored on a property.
export function PropertyCover({ property }: { property: { cover_media_id?: string; cover_url?: string } }) {
  const uri = property.cover_media_id ? fileUrl(property.cover_media_id) : property.cover_url;
  return uri ? <Image source={{ uri }} accessibilityLabel="Villa cover photo" style={{ width: "100%", height: "100%" }} contentFit="cover" transition={200} cachePolicy="none" /> : null;
}
