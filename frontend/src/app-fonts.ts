import { useFonts } from "expo-font";
import { appFonts } from "./font-assets";

export function useAppFonts() {
  return useFonts(appFonts);
}
