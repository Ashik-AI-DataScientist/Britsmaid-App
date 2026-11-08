import { useEffect, useState } from "react";
import { Linking, View } from "react-native";
import { Button, Card, Txt } from "@/src/ui";
import { spacing } from "@/src/theme";

export function InstallHelp() {
  const [standalone, setStandalone] = useState(false);
  useEffect(() => {
    const display = window.matchMedia("(display-mode: standalone)");
    const update = () => setStandalone(display.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true);
    update();
    display.addEventListener("change", update);
    return () => display.removeEventListener("change", update);
  }, []);
  if (standalone) return null;
  return <Card style={{ gap: spacing.sm }} testID="web-install-help">
    <Txt v="subtitle">Britsmaid on your home screen</Txt>
    <Txt>Keep your property workspace one tap away, with the Britsmaid icon.</Txt>
    <View><Button title="Add to Home Screen" icon="phone-portrait-outline" variant="secondary" onPress={() => Linking.openURL("/install.html")} /></View>
    <Txt v="caption">Android and iPhone instructions. Internet is required.</Txt>
  </Card>;
}
