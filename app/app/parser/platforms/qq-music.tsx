import { AudioLines } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "QQ 音乐", accent: "#31c27c", accentSoft: "#e4f8ed", background: "linear-gradient(145deg, #ebf9f1 0%, #fff 52%, #e7f7ef 100%)", card: "#ffffff", Icon: AudioLines };
export function QQMusic({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
