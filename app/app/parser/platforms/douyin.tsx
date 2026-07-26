import { Play } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "抖音", accent: "#25f4ee", accentSoft: "#173e46", background: "linear-gradient(145deg, #090a0d 0%, #12151c 55%, #1c1320 100%)", card: "#171a20", logo: "/parser/douyin.png", Icon: Play, dark: true };
export function Douyin({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
