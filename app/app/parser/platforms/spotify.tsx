import { AudioLines } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "Spotify", accent: "#1db954", accentSoft: "#e4f8eb", background: "linear-gradient(145deg, #e9f8ed 0%, #fff 52%, #eaf7ee 100%)", card: "#ffffff", Icon: AudioLines };
export function Spotify({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
