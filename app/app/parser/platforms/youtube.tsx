import { Play } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "YouTube", accent: "#ff0033", accentSoft: "#fff0f2", background: "linear-gradient(145deg, #f6f6f6 0%, #fff 56%, #f3f3f3 100%)", card: "#ffffff", logo: "/parser/youtube.png", Icon: Play };
export function Youtube({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
