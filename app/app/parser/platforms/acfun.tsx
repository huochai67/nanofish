import { Play } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "AcFun", accent: "#fd4c5d", accentSoft: "#fff0f2", background: "linear-gradient(145deg, #fff0f2 0%, #fff 52%, #fff4f5 100%)", card: "#ffffff", Icon: Play };
export function Acfun({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
