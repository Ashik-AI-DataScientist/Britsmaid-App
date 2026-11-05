import React, { useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { Image } from "expo-image";
import { useVideoPlayer, VideoView } from "expo-video";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useMediaUrl } from "@/src/use-media-url";
import { Icon, IconButton } from "@/src/ui";
import { radius, useTheme } from "@/src/theme";

function VideoPlayer({ uri }: { uri: string }) {
  const player = useVideoPlayer(uri, (p) => { p.loop = false; });
  return <VideoView player={player} style={{ width: "100%", height: "70%" }} nativeControls contentFit="contain" />;
}

export function MediaThumb({ id, kind = "image", size = 84, onRemove, testID, src, expired = false }: { id: string; kind?: string; size?: number | `${number}%`; onRemove?: () => void; testID?: string; src?: string; expired?: boolean }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const { uri, error, retry } = useMediaUrl(expired ? undefined : id, src);
  if (expired) return <View accessibilityLabel="Photo removed under cleaning retention policy" style={{ width: size, aspectRatio: 1, padding: 4, backgroundColor: colors.surfaceTertiary }}><Text style={{ fontSize: 10 }}>Older cleaning photo removed</Text></View>;
  return (
    <>
      <Pressable testID={testID} onPress={async () => { const result = await retry(); if (!result?.isError && (uri || result?.data)) setOpen(true); }} style={{ width: size, aspectRatio: 1, borderRadius: radius.sm + 2, overflow: "hidden", backgroundColor: colors.surfaceTertiary }}>
        {error ? <Text>Photo unavailable. Tap to retry.</Text> : null}
        {kind === "video" ? (
          <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceInverse }}>
            <Icon name="play-circle" size={32} color={colors.onSurfaceInverse} />
          </View>
        ) : (
          <Image source={uri ? { uri } : undefined} style={{ width: "100%", height: "100%" }} contentFit="cover" transition={150} cachePolicy="none" />
        )}
        {onRemove ? (
          <Pressable testID={`${testID}-remove`} onPress={onRemove} hitSlop={8} style={{ position: "absolute", top: 4, right: 4, width: 24, height: 24, borderRadius: 12, backgroundColor: colors.scrim, alignItems: "center", justifyContent: "center" }}>
            <Icon name="close" size={14} color={colors.onSurfaceInverse} />
          </Pressable>
        ) : null}
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <View style={{ flex: 1, backgroundColor: "#000", alignItems: "center", justifyContent: "center" }}>
          {kind === "video" && uri ? <VideoPlayer uri={uri} /> : <Image source={uri ? { uri } : undefined} style={{ width: "100%", height: "80%" }} contentFit="contain" cachePolicy="none" />}
          <View style={{ position: "absolute", top: insets.top + 12, right: 16 }}>
            <IconButton testID="media-viewer-close" name="close" tone="inverse" onPress={() => setOpen(false)} />
          </View>
        </View>
      </Modal>
    </>
  );
}
