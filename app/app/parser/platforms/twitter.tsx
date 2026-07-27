/* eslint-disable @next/next/no-img-element */

import { BadgeCheck, Bookmark, CircleUserRound, Ellipsis, Heart, MessageCircle, MessageCircleMore, Play, Repeat2, Share2 } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserPost, ParserResult, PostMedia } from "../types";

export const appearance: PlatformAppearance = { label: "X", accent: "#111827", accentSoft: "#edf1f5", background: "#ffffff", card: "#ffffff", logo: "/parser/twitter.png", Icon: MessageCircleMore };

export function Twitter({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) {
  return result.kind === "music" ? <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} /> : <TwitterPost result={result} maxGridImages={maxGridImages} onAsset={onAsset} />;
}

export function countAssets(result: ParserResult, maxGridImages: number) {
  if (result.kind === "music") return assetCount(result, maxGridImages, appearance);
  const video = result.media.find((media) => media.kind === "video");
  const mediaImages = result.media.filter((media) => media.kind === "image" && Boolean(media.src));
  const graphics = !video && mediaImages.length === 0 ? result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src)).length : 0;
  return Number(Boolean(result.author?.avatar)) + (video?.kind === "video" && video.poster ? 1 : Math.min(mediaImages.length || graphics, maxGridImages));
}

function TwitterPost({ result, maxGridImages, onAsset }: { result: ParserPost; maxGridImages: number; onAsset: () => void }) {
  const video = result.media.find((media): media is Extract<PostMedia, { kind: "video" }> => media.kind === "video");
  const contentImages = result.media.filter((media): media is Extract<PostMedia, { kind: "image" }> => media.kind === "image" && Boolean(media.src));
  const graphicImages = result.graphics.filter((graphic): graphic is Extract<ParserPost["graphics"][number], { kind: "image" }> => graphic.kind === "image" && Boolean(graphic.src));
  const images = (contentImages.length ? contentImages : graphicImages).slice(0, maxGridImages);
  const handle = result.author?.description?.startsWith("@") ? result.author.description : result.author?.name ? `@${result.author.name.replaceAll(/\s+/g, "")}` : "@twitter";
  const tweet = result.text ?? result.title;
  const timestamp = formatTwitterTimestamp(result.timestamp);
  const views = result.stats?.view ? formatTwitterCount(result.stats.view) : null;
  const actionItems = [{ Icon: MessageCircle, value: result.stats?.reply ?? result.stats?.comment }, { Icon: Repeat2, value: result.stats?.share }, { Icon: Heart, value: result.stats?.like }, { Icon: Bookmark, value: result.stats?.collect }];

  return (
    <article data-parser-card className="rounded-xl border border-[#cfd9de] bg-white px-4 py-3 text-[#0f1419] shadow-pop sm:px-5">
      <div className="flex gap-3">
        {result.author?.avatar ? <img src={result.author.avatar} alt="" className="h-10 w-10 shrink-0 rounded object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-[#0f1419] text-white"><CircleUserRound size={22} /></span>}
        <div className="min-w-0 flex-1">
          <header className="flex items-start gap-1"><div className="min-w-0 flex-1 leading-5"><div className="flex min-w-0 items-center gap-1"><span className="truncate text-[15px] font-bold">{result.author?.name ?? "X 用户"}</span><BadgeCheck size={17} className="shrink-0 text-[#1d9bf0]" fill="currentColor" stroke="white" strokeWidth={2.5} /></div><p className="truncate text-sm text-[#536471]">{handle}</p></div><Ellipsis size={20} className="mt-0.5 shrink-0 text-[#536471]" /></header>
          {tweet ? <p className="mt-3 whitespace-pre-wrap text-base leading-6">{tweet}</p> : null}
          {video?.poster ? <div className="relative mt-3 w-fit max-w-full overflow-hidden rounded-2xl border border-[#cfd9de] bg-[#f7f9f9]"><img src={video.poster} alt={result.title ?? "视频"} className="block h-auto max-h-[600px] max-w-full w-auto" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /><span className="absolute inset-0 flex items-center justify-center"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/70 pl-0.5 text-white"><Play size={22} fill="currentColor" /></span></span></div> : null}
          {images.length ? <div className="mt-3 space-y-2">{images.map((image, index) => <div key={index} className="w-fit max-w-full overflow-hidden rounded-2xl border border-[#cfd9de] bg-[#f7f9f9]"><img src={image.src} alt={image.alt ?? "推文图片"} className="block h-auto max-h-[600px] max-w-full w-auto" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /></div>)}</div> : null}
          {timestamp || views ? <p className="mt-3 text-sm text-[#536471]">{timestamp ? <>{timestamp}{views ? " · " : null}</> : null}{views ? <><span className="font-bold text-[#0f1419]">{views}</span> Views</> : null}</p> : null}
          <footer className="mt-3 flex items-center justify-between border-t border-[#eff3f4] pt-3 text-[#536471]">{actionItems.map(({ Icon, value }, index) => <span key={index} className="inline-flex min-w-0 items-baseline gap-1 text-xs"><Icon size={24} strokeWidth={1.8} />{value ? <span>{formatTwitterCount(value)}</span> : null}</span>)}<Share2 size={24} strokeWidth={1.8} /></footer>
        </div>
      </div>
    </article>
  );
}

function formatTwitterTimestamp(timestamp?: number | null): string | null { if (!timestamp) return null; const date = new Date(timestamp * 1000); if (Number.isNaN(date.valueOf())) return null; const time = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(date); const calendar = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date); return `${time} · ${calendar}`; }
function formatTwitterCount(value?: number): string { if (!value) return "0"; const abbreviate = (divisor: number, suffix: string) => `${(value / divisor).toFixed(1).replace(/\.0$/, "")}${suffix}`; if (value >= 1_000_000_000) return abbreviate(1_000_000_000, "B"); if (value >= 1_000_000) return abbreviate(1_000_000, "M"); if (value >= 1_000) return abbreviate(1_000, "K"); return String(value); }
