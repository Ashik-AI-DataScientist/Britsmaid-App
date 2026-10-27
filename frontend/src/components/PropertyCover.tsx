import React from "react";
import { Image } from "expo-image";
import { useMediaUrl } from "@/src/use-media-url";
import { Pressable, Text } from "react-native";

// Save only the media ID; signed-in display URLs must never be stored on a property.
export function PropertyCover({ property }: { property: { cover_media_id?: string; cover_url?: string } }) {
  const { uri, error, retry } = useMediaUrl(property.cover_media_id, property.cover_media_id ? undefined : property.cover_url);
  if (error) return <Pressable accessibilityLabel="Retry cover photo" onPress={() => retry()}><Text>Photo unavailable. Tap to retry.</Text></Pressable>;
  return uri ? <Image source={{ uri }} accessibilityLabel="Villa cover photo" style={{ width: "100%", height: "100%" }} contentFit="cover" transition={200} cachePolicy="none" /> : null;
}
