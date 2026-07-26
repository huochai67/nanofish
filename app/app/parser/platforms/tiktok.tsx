import { Play } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "TikTok", accent: "#ff3b6b", accentSoft: "#3c1c2c", background: "linear-gradient(145deg, #090a0d 0%, #12151c 55%, #1a1220 100%)", card: "#171a20", logo: "/parser/tiktok.png", Icon: Play, dark: true };
export function Tiktok({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
