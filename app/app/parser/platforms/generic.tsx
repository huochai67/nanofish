/* eslint-disable @next/next/no-img-element */

import type { CSSProperties } from "react";
import {
  ArrowUpRight,
  AudioLines,
  Bookmark,
  CirclePoundSterling,
  CircleUserRound,
  Eye,
  Link as LinkIcon,
  MessageCircle,
  MessageSquareText,
  Play,
  Share2,
  Star,
  ThumbsUp,
  type LucideIcon,
} from "lucide-react";
import type { ParserMusic, ParserPost, ParserResult, ParserStats, PostMedia } from "../types";

export type PlatformAppearance = {
  label: string;
  accent: string;
  accentSoft: string;
  background: string;
  card: string;
  logo?: string;
  Icon: LucideIcon;
  dark?: boolean;
};

export const genericAppearance: PlatformAppearance = {
  label: "链接解析",
  accent: "#4f46e5",
  accentSoft: "#eef2ff",
  background: "linear-gradient(145deg, #eef2ff 0%, #fafaff 52%, #e9edff 100%)",
  card: "#ffffff",
  Icon: Share2,
};

export function assetCount(result: ParserResult, maxGridImages: number, appearance: PlatformAppearance): number {
  const logo = Number(Boolean(appearance.logo));
  if (result.kind === "music") return logo + Number(Boolean(result.cover));

  const video = result.media.find((media) => media.kind === "video");
  const images = result.media.filter((media) => media.kind === "image" && Boolean(media.src));
  const graphics = !video && images.length === 0
    ? result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src)).length
    : 0;
  return (
    logo +
    Number(Boolean(result.author?.avatar)) +
    (video?.kind === "video" && video.poster ? 1 : Math.min(images.length, maxGridImages)) +
    graphics +
    (result.repost ? assetCount(result.repost, maxGridImages, appearance) : 0)
  );
}

export function GenericCard({
  result,
  appearance,
  maxGridImages,
  onAsset,
  repost = false,
}: {
  result: ParserResult;
  appearance: PlatformAppearance;
  maxGridImages: number;
  onAsset: () => void;
  repost?: boolean;
}) {
  return result.kind === "music" ? (
    <MusicCard result={result} appearance={appearance} onAsset={onAsset} />
  ) : (
    <PostCard
      result={result}
      appearance={appearance}
      maxGridImages={maxGridImages}
      onAsset={onAsset}
      repost={repost}
    />
  );
}

function PostCard({
  result,
  appearance,
  maxGridImages,
  onAsset,
  repost,
}: {
  result: ParserPost;
  appearance: PlatformAppearance;
  maxGridImages: number;
  onAsset: () => void;
  repost: boolean;
}) {
  const dark = Boolean(appearance.dark);
  const text = dark ? "text-slate-100" : "text-slate-900";
  const muted = dark ? "text-slate-400" : "text-slate-500";
  const video = result.media.find((media) => media.kind === "video");
  const images = result.media.filter(
    (media): media is Extract<PostMedia, { kind: "image" }> => media.kind === "image" && Boolean(media.src),
  );
  const Icon = appearance.Icon;
  const style = { backgroundColor: appearance.card } as CSSProperties;

  return (
    <article data-parser-card className={`overflow-hidden rounded-2xl border ${dark ? "border-white/10" : "border-black/[0.06]"} ${repost ? "shadow-none" : "shadow-pop"}`} style={style}>
      <div className={`flex items-center justify-between gap-2 border-b px-4 py-3 sm:px-5 ${dark ? "border-white/10" : "border-black/[0.05]"}`}>
        <div className="flex min-w-0 items-center gap-2">
          {appearance.logo ? <img src={appearance.logo} alt="" className="h-6 max-w-24 object-contain" onLoad={onAsset} onError={onAsset} /> : <><Icon size={17} strokeWidth={2.5} style={{ color: appearance.accent }} /><span className={`text-xs font-bold tracking-wide ${text}`}>{appearance.label}</span></>}
          {result.contentType ? <span className="rounded-md px-1.5 py-0.5 text-[10px] font-semibold" style={{ backgroundColor: appearance.accentSoft, color: dark ? "#e2e8f0" : appearance.accent }}>{result.contentType}</span> : null}
        </div>
        <ArrowUpRight size={15} className={`shrink-0 ${muted}`} />
      </div>

      <div className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
        {result.author ? <div className="flex items-center gap-3">
          {result.author.avatar ? <img src={result.author.avatar} alt="" className="h-10 w-10 rounded-full object-cover ring-1 ring-black/[0.06]" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <span className="flex h-10 w-10 items-center justify-center rounded-full text-white" style={{ backgroundColor: appearance.accent }}><CircleUserRound size={21} /></span>}
          <div className="min-w-0"><p className={`truncate text-sm font-semibold ${text}`}>{result.author.name}</p><p className={`truncate text-xs ${muted}`}>{formatTime(result.timestamp) ?? result.author.description ?? ""}</p></div>
        </div> : null}
        {result.title ? <h1 className={`text-lg font-bold leading-snug sm:text-xl ${text}`}>{result.title}</h1> : null}
        {result.text ? <p className={`whitespace-pre-wrap text-[15px] leading-7 ${text}`}>{result.text}</p> : null}
        {video?.kind === "video" ? <VideoView media={video} onAsset={onAsset} /> : null}
        {!video && images.length ? <MediaGrid images={images} maxItems={maxGridImages} onAsset={onAsset} /> : null}
        {result.graphics.length && !video && !images.length ? <div className={`space-y-3 rounded-xl p-3 ${dark ? "bg-white/5" : "bg-slate-50"}`}>{result.graphics.map((graphic, index) => graphic.kind === "text" ? <p key={index} className={`whitespace-pre-wrap text-sm leading-6 ${text}`}>{graphic.text}</p> : graphic.src ? <img key={index} src={graphic.src} alt={graphic.alt ?? "解析图片"} className="max-h-[560px] w-full rounded-lg object-contain" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : null)}</div> : null}
        {result.extraInfo ? <div className={`rounded-lg border-l-[3px] px-3.5 py-2.5 text-sm leading-6 ${dark ? "bg-white/5 text-slate-300" : "bg-slate-50 text-slate-600"}`} style={{ borderLeftColor: appearance.accent }}>{result.extraInfo}</div> : null}
        {result.repost ? <div className={`rounded-xl p-2 ${dark ? "bg-white/5" : "bg-slate-50"}`}><div className={`mb-2 flex items-center gap-1.5 px-1.5 text-xs ${muted}`}><Share2 size={13} /> 转发内容</div><GenericCard result={result.repost} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} repost /></div> : null}
        {result.stats ? <StatsRow stats={result.stats} dark={dark} /> : null}
        {result.url ? <div className={`flex min-w-0 items-center gap-1.5 text-xs ${muted}`}><LinkIcon size={13} className="shrink-0" style={{ color: appearance.accent }} /><span className="truncate">{result.url}</span></div> : null}
      </div>
    </article>
  );
}

function MusicCard({ result, appearance, onAsset }: { result: ParserMusic; appearance: PlatformAppearance; onAsset: () => void }) {
  const Icon = appearance.Icon;
  return (
    <article data-parser-card className="overflow-hidden rounded-2xl border border-black/[0.06] shadow-pop" style={{ backgroundColor: appearance.card }}>
      <div className="flex items-center gap-2 border-b border-black/[0.05] px-4 py-3 sm:px-5">
        {appearance.logo ? <img src={appearance.logo} alt="" className="h-6 max-w-24 object-contain" onLoad={onAsset} onError={onAsset} /> : <><Icon size={17} strokeWidth={2.5} style={{ color: appearance.accent }} /><span className="text-xs font-bold tracking-wide text-slate-900">{appearance.label}</span></>}
        {result.contentType ? <span className="rounded-md px-1.5 py-0.5 text-[10px] font-semibold" style={{ backgroundColor: appearance.accentSoft, color: appearance.accent }}>{result.contentType}</span> : null}
      </div>
      <div className="flex gap-4 px-4 py-4 sm:px-5 sm:py-5">
        {result.cover ? <img src={result.cover} alt="专辑封面" className="h-20 w-20 shrink-0 rounded-lg object-cover shadow-sm" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg text-white" style={{ backgroundColor: appearance.accent }}><AudioLines size={28} /></span>}
        <div className="min-w-0 flex-1"><h1 className="truncate text-lg font-bold text-slate-900">{result.title}</h1>{result.artist ? <p className="mt-1 truncate text-sm text-slate-600">{result.artist}</p> : null}{result.album ? <p className="mt-1 truncate text-xs text-slate-500">{result.album}</p> : null}{formatDuration(result.duration) ? <p className="mt-2 text-xs text-slate-500">{formatDuration(result.duration)}</p> : null}</div>
      </div>
      {result.extraInfo || result.url || result.stats ? <div className="space-y-3 border-t border-black/[0.05] px-4 py-3 sm:px-5">{result.extraInfo ? <p className="text-sm leading-6 text-slate-600">{result.extraInfo}</p> : null}{result.stats ? <StatsRow stats={result.stats} dark={false} /> : null}{result.url ? <div className="flex min-w-0 items-center gap-1.5 text-xs text-slate-500"><LinkIcon size={13} style={{ color: appearance.accent }} /><span className="truncate">{result.url}</span></div> : null}</div> : null}
    </article>
  );
}

function VideoView({ media, onAsset }: { media: Extract<PostMedia, { kind: "video" }>; onAsset: () => void }) {
  return <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-900">{media.poster ? <img src={media.poster} alt="视频封面" className="h-full w-full object-cover opacity-90" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <div className="h-full w-full bg-gradient-to-br from-slate-700 to-slate-950" />}<span className="absolute inset-0 flex items-center justify-center"><span className="flex h-14 w-14 items-center justify-center rounded-full bg-white/90 pl-0.5 text-slate-900 shadow-xl"><Play size={26} fill="currentColor" /></span></span>{formatDuration(media.duration) ? <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-2 py-1 text-[11px] font-medium text-white">{formatDuration(media.duration)}</span> : null}</div>;
}

function MediaGrid({ images, maxItems, onAsset }: { images: Extract<PostMedia, { kind: "image" }>[]; maxItems: number; onAsset: () => void }) {
  const shown = images.slice(0, maxItems);
  const columns = shown.length === 1 ? "grid-cols-1" : shown.length <= 4 ? "grid-cols-2" : "grid-cols-3";
  return <div className={`grid gap-1.5 ${columns}`}>{shown.map((image, index) => <div key={index} className={`relative overflow-hidden rounded-xl bg-slate-100 ${shown.length === 1 ? "max-h-[560px]" : "aspect-square"}`}><img src={image.src} alt={image.alt ?? "解析图片"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />{index === shown.length - 1 && images.length > maxItems ? <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-xl font-bold text-white">+{images.length - maxItems}</span> : null}</div>)}</div>;
}

function StatsRow({ stats, dark }: { stats: ParserStats; dark: boolean }) {
  const items = [{ Icon: Eye, value: stats.view }, { Icon: MessageSquareText, value: stats.danmaku }, { Icon: ThumbsUp, value: stats.like }, { Icon: MessageCircle, value: stats.comment ?? stats.reply }, { Icon: Star, value: stats.favorite }, { Icon: Bookmark, value: stats.collect }, { Icon: CirclePoundSterling, value: stats.coin }, { Icon: Share2, value: stats.share }].filter((item) => item.value);
  if (!items.length) return null;
  return <div className={`flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t pt-3 text-xs ${dark ? "border-white/10 text-slate-400" : "border-black/[0.05] text-slate-500"}`}>{items.map(({ Icon, value }, index) => <span key={index} className="inline-flex items-center gap-1.5"><Icon size={14} />{formatCount(value)}</span>)}</div>;
}

function formatTime(timestamp?: number | null): string | null {
  if (!timestamp) return null;
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.valueOf()) ? null : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatDuration(duration?: number | null): string | null {
  if (duration === undefined || duration === null || duration < 0) return null;
  const total = Math.round(duration);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function formatCount(value?: number): string {
  if (!value) return "0";
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}亿`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)}万`;
  return String(value);
}
