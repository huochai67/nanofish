import { AudioLines } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "YouTube Music", accent: "#ff1744", accentSoft: "#fff0f2", background: "linear-gradient(145deg, #fff1f3 0%, #fff 52%, #f7f0f3 100%)", card: "#ffffff", Icon: AudioLines };
export function YoutubeMusic({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
