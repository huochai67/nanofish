import { FileText } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "NGA", accent: "#7b5a3f", accentSoft: "#f5ead7", background: "linear-gradient(145deg, #eee4d3 0%, #f8f3ea 52%, #e9ddc8 100%)", card: "#fffdf8", Icon: FileText };
export function Nga({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
