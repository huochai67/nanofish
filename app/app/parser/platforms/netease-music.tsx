import { AudioLines } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "网易云音乐", accent: "#d93026", accentSoft: "#fff0ef", background: "linear-gradient(145deg, #fff0ef 0%, #fff 52%, #fff3f2 100%)", card: "#ffffff", Icon: AudioLines };
export function NeteaseMusic({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
