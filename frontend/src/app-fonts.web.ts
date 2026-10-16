import { useEffect, useState } from "react";
import { appFonts } from "./font-assets";

let fontLoad: Promise<void> | undefined;

// Register the bundled fonts explicitly. A generated stylesheet can exist
// without registering its font faces, leaving icon glyphs as empty boxes.
function loadFonts() {
  return fontLoad ??= Promise.all(Object.entries(appFonts).map(async ([family, source]) => {
    const uri = typeof source === "string" ? source : source?.uri ?? source?.default;
    if (typeof uri !== "string") throw new Error(`Missing bundled font: ${family}`);
    const font = new FontFace(family, `url(${JSON.stringify(uri)}) format("truetype")`, { display: "swap" });
    document.fonts.add(await font.load());
  })).then(() => undefined);
}

export function useAppFonts(): [boolean, Error | null] {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    let mounted = true;
    loadFonts().then(() => { if (mounted) setLoaded(true); }, (cause) => {
      if (mounted) setError(cause instanceof Error ? cause : new Error("Font loading failed"));
      fontLoad = undefined;
    });
    return () => { mounted = false; };
  }, []);
  return [loaded, error];
}
