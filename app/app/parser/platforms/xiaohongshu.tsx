/* eslint-disable @next/next/no-img-element */

import { FileText, Heart, MessageCircle, Play, Send, Star } from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserPost, ParserResult, PostMedia } from "../types";

export const appearance: PlatformAppearance = { label: "小红书", accent: "#ff2442", accentSoft: "#fff0f2", background: "linear-gradient(145deg, #fff1f3 0%, #fff 50%, #fff5f5 100%)", card: "#ffffff", logo: "/parser/xiaohongshu.png", Icon: FileText };

export function Xiaohongshu({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) {
  return result.kind === "music" ? <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} /> : <XiaohongshuPost result={result} onAsset={onAsset} />;
}

export function countAssets(result: ParserResult, maxGridImages: number) {
  if (result.kind === "music") return assetCount(result, maxGridImages, appearance);
  const video = result.media.find((media) => media.kind === "video");
  const image = result.media.find((media) => media.kind === "image" && Boolean(media.src));
  return 1 + Number(Boolean(video?.kind === "video" ? video.poster : image?.kind === "image" ? image.src : undefined));
}

function XiaohongshuPost({ result, onAsset }: { result: ParserPost; onAsset: () => void }) {
  const video = result.media.find((media): media is Extract<PostMedia, { kind: "video" }> => media.kind === "video");
  const image = result.media.find((media): media is Extract<PostMedia, { kind: "image" }> => media.kind === "image" && Boolean(media.src));
  const media = video?.poster ?? image?.src;

  return (
    <article data-parser-card className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white shadow-pop sm:flex">
      <section className="relative flex aspect-[4/5] items-center justify-center bg-[#202124] sm:aspect-auto sm:min-h-[600px] sm:w-[52%]">
        {media ? <img src={media} alt={result.title ?? "解析媒体"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <div className="h-full w-full bg-gradient-to-br from-[#434343] to-[#111]" />}
        {video ? <span className="absolute inset-0 flex items-center justify-center"><span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/90 pl-1 text-[#222] shadow-xl"><Play size={30} fill="currentColor" /></span></span> : null}
        {video?.duration !== undefined ? <span className="absolute bottom-4 right-4 rounded bg-black/60 px-2 py-1 text-xs text-white">{formatDuration(video.duration)}</span> : null}
      </section>

      <section className="flex flex-1 flex-col px-4 py-4 sm:min-h-[600px] sm:px-5 sm:py-5">
        <header className="flex items-center gap-2.5">
          {result.author?.avatar ? <img src={result.author.avatar} alt="" className="h-10 w-10 rounded-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <img src="/parser/avatar.png" alt="" className="h-10 w-10 rounded-full object-cover" onLoad={onAsset} onError={onAsset} />}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-[#333]">{result.author?.name ?? "小红书用户"}</span>
          <span className="shrink-0 rounded-full bg-[#ff2442] px-4 py-1.5 text-xs font-medium text-white sm:px-5 sm:py-2 sm:text-sm">关注</span>
        </header>
        {result.title ? <h1 className="mt-5 text-lg font-bold leading-7 text-[#222] sm:mt-7">{result.title}</h1> : null}
        {result.text ? <p className="mt-2 whitespace-pre-wrap text-[15px] leading-6 text-[#333]"><XiaohongshuText text={result.text} /></p> : null}
        {result.contentType ? <span className="mt-3 w-fit rounded-md border border-[#efefef] px-2 py-1 text-xs text-[#666]">{result.contentType}</span> : null}
        <p className="mt-3 text-xs text-[#999]">{formatTime(result.timestamp) ?? result.author?.description ?? "刚刚"}</p>
        {result.extraInfo ? <p className="mt-5 border-t border-[#f0f0f0] pt-4 text-sm leading-6 text-[#666]">{result.extraInfo}</p> : null}
        <footer className="mt-auto flex items-center justify-between gap-2 border-t border-[#f0f0f0] pt-3.5 text-[#555]">
          <span className="min-w-0 truncate rounded-full bg-[#f7f7f7] px-3 py-2 text-xs text-[#999]">说点什么...</span>
          <span className="flex shrink-0 items-center gap-1 text-sm"><Heart size={18} />{formatCount(result.stats?.like)}</span>
          <span className="flex shrink-0 items-center gap-1 text-sm"><Star size={18} />{formatCount(result.stats?.collect)}</span>
          <span className="flex shrink-0 items-center gap-1 text-sm"><MessageCircle size={18} />{formatCount(result.stats?.comment)}</span>
          <Send size={18} className="shrink-0" />
        </footer>
      </section>
    </article>
  );
}

function XiaohongshuText({ text }: { text: string }) { return text.replaceAll("[话题]", "").split(/(#[^\s#，。！？、；：]+)/g).map((part, index) => part.startsWith("#") ? <span key={index} className="text-[#3f6699]">{part}</span> : part); }
function formatTime(timestamp?: number | null): string | null { if (!timestamp) return null; const date = new Date(timestamp * 1000); return Number.isNaN(date.valueOf()) ? null : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date); }
function formatDuration(duration?: number): string | null { if (duration === undefined || duration < 0) return null; const total = Math.round(duration); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`; }
function formatCount(value?: number): string { if (!value) return "0"; if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}亿`; if (value >= 10_000) return `${(value / 10_000).toFixed(1)}万`; return String(value); }
