import { MessageCircleMore } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserResult } from "../types";

export const appearance: PlatformAppearance = { label: "微博", accent: "#e86b2a", accentSoft: "#fff0e6", background: "linear-gradient(145deg, #fff7f0 0%, #fffdf9 55%, #fff0e7 100%)", card: "#fffefd", logo: "/parser/weibo.png", Icon: MessageCircleMore };
export function Weibo({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) { return <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />; }
export function countAssets(result: ParserResult, maxGridImages: number) { return assetCount(result, maxGridImages, appearance); }
