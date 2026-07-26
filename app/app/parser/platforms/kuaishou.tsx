import { Clapperboard } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "快手", accent: "#ff6a00", accentSoft: "#fff0e5", background: "linear-gradient(145deg, #fff1e8 0%, #fffaf7 50%, #ffe8d6 100%)", card: "#ffffff", logo: "/parser/kuaishou.png", Icon: Clapperboard };
export function Kuaishou({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
