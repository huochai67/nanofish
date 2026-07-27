/* eslint-disable @next/next/no-img-element */

import {
  CirclePoundSterling,
  EllipsisVertical,
  MessageCircle,
  MessageSquareText,
  Play,
  Share2,
  Star,
  ThumbsUp,
  Clapperboard,
} from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserPost, ParserResult, PostMedia } from "../types";

export const appearance: PlatformAppearance = {
  label: "Bilibili",
  accent: "#00aeec",
  accentSoft: "#e0f7ff",
  background: "linear-gradient(145deg, #eafaff 0%, #f7fcff 42%, #e9f7ff 100%)",
  card: "#ffffff",
  logo: "/parser/bilibili.png",
  Icon: Clapperboard,
};

export function Bilibili({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) {
  return result.kind === "music" ? (
    <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />
  ) : (
    <BilibiliPost result={result} onAsset={onAsset} />
  );
}

export function countAssets(result: ParserResult, maxGridImages: number) {
  if (result.kind === "music") return assetCount(result, maxGridImages, appearance);
  const video = result.media.find((media) => media.kind === "video");
  const mediaImages = result.media.filter((media) => media.kind === "image" && Boolean(media.src));
  const graphicImages = result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src));
  const imageCount = mediaImages.length ? mediaImages.length : graphicImages.length;
  return 1 + Number(Boolean(result.author?.pendant)) + (video?.kind === "video" && video.poster ? 1 : Math.min(imageCount, 9));
}

function BilibiliPost({ result, onAsset }: { result: ParserPost; onAsset: () => void }) {
  const video = result.media.find(
    (media): media is Extract<PostMedia, { kind: "video" }> => media.kind === "video",
  );
  const mediaImages = result.media.filter(
    (media): media is Extract<PostMedia, { kind: "image" }> => media.kind === "image" && Boolean(media.src),
  );
  const graphicImages = result.graphics.filter(
    (graphic): graphic is Extract<ParserPost["graphics"][number], { kind: "image" }> => graphic.kind === "image" && Boolean(graphic.src),
  );
  const graphicText = result.graphics.filter(
    (graphic): graphic is Extract<ParserPost["graphics"][number], { kind: "text" }> => graphic.kind === "text",
  );
  const images = (mediaImages.length ? mediaImages : graphicImages).map((image) => ({ src: image.src!, alt: image.alt }));
  const body = result.text;
  const title = result.title && result.title !== body ? result.title : null;

  return (
    <article data-parser-card className="overflow-hidden rounded-xl border border-black/[0.06] bg-white text-[#18191c] shadow-pop">
      <div className="flex gap-[17px] px-4 pt-4 sm:px-[18px]">
        <aside className="shrink-0">
          <div className="relative h-[52px] w-[52px]">
          {result.author?.avatar ? (
            <img
              src={result.author.avatar}
              alt=""
              className="h-[52px] w-[52px] rounded-full object-cover"
              referrerPolicy="no-referrer"
              onLoad={onAsset}
              onError={onAsset}
            />
          ) : (
            <img
              src="/parser/avatar.png"
              alt=""
              className="h-[52px] w-[52px] rounded-full object-cover"
              onLoad={onAsset}
              onError={onAsset}
            />
          )}
          {result.author?.pendant ? (
            <img
              src={result.author.pendant}
              alt=""
              className="pointer-events-none absolute -inset-1 h-[60px] w-[60px] max-w-none object-contain"
              referrerPolicy="no-referrer"
              onLoad={onAsset}
              onError={onAsset}
            />
          ) : null}
          </div>
        </aside>
        <div className="min-w-0 flex-1 pb-0.5">
          <header className="flex items-start">
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-semibold leading-6 text-[#fb7299]">{result.author?.name ?? "哔哩哔哩用户"}</p>
              <p className="mt-1 text-[13px] leading-4 text-[#9499a0]">
                {formatBilibiliTime(result.timestamp) ?? result.author?.description ?? "刚刚"}
                {video ? " · 投稿了视频" : ""}
              </p>
            </div>
            <EllipsisVertical size={20} className="mt-1 shrink-0 text-[#9499a0]" />
          </header>

          {!video && title ? <p className="mt-3 text-[15px] font-semibold leading-5">{title}</p> : null}
          {body ? <p className={`${title && !video ? "mt-3" : "mt-2"} whitespace-pre-wrap text-[15px] leading-5 text-[#18191c]`}><BilibiliText text={body} /></p> : null}
          {graphicText.map((graphic, index) => <p key={index} className="mt-2 whitespace-pre-wrap text-[15px] leading-6 text-[#18191c]">{graphic.text}</p>)}

          {video ? (
            <div className="mt-3 flex overflow-hidden rounded-xl border border-[#e3e5e7] bg-[#f6f7f8]">
              <div className="relative h-32 w-[38%] shrink-0 bg-[#2b2d31]">
                {video.poster ? (
                  <img src={video.poster} alt={result.title ?? "视频封面"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
                ) : null}
                <span className="absolute bottom-2 right-2 rounded bg-black/65 px-1.5 py-0.5 text-xs text-white">{formatDuration(video.duration) ?? "视频"}</span>
              </div>
              <div className="flex min-w-0 flex-1 flex-col justify-between p-3">
                <p className="line-clamp-2 text-sm leading-5 text-[#18191c]">{result.title ?? body}</p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#9499a0]">
                  <span className="flex items-center gap-1"><Play size={13} />{formatCount(result.stats?.view)}</span>
                  <span className="flex items-center gap-1"><MessageSquareText size={13} />{formatCount(result.stats?.danmaku)}</span>
                  <span className="flex items-center gap-1"><CirclePoundSterling size={13} />{formatCount(result.stats?.coin)}</span>
                  <span className="flex items-center gap-1"><Star size={13} />{formatCount(result.stats?.favorite)}</span>
                </div>
              </div>
            </div>
          ) : images.length ? (
            <div className="mt-6"><MediaGrid images={images} maxItems={9} onAsset={onAsset} /></div>
          ) : null}
        </div>
      </div>

      <footer className="mt-4 flex items-center justify-between px-4 pb-4 pl-[88px] pr-6 text-[#7d8590] sm:pr-[94px]">
        <span className="flex items-center gap-1.5 text-sm"><Share2 size={17} />{formatCount(result.stats?.share)}</span>
        <span className="flex items-center gap-1.5 text-sm"><MessageCircle size={17} />{formatCount(result.stats?.reply)}</span>
        <span className="flex items-center gap-1.5 text-sm"><ThumbsUp size={17} />{formatCount(result.stats?.like)}</span>
      </footer>
    </article>
  );
}

type ImageAsset = { src: string; alt?: string };

function MediaGrid({ images, maxItems, onAsset }: { images: ImageAsset[]; maxItems: number; onAsset: () => void }) {
  const shown = images.slice(0, maxItems);
  const singleImage = shown.length === 1;
  const columns = singleImage ? "w-[132px] grid-cols-1" : shown.length <= 4 ? "w-[400px] grid-cols-2" : "w-[400px] grid-cols-3";
  return (
    <div className={`grid max-w-full gap-1 ${columns}`}>
      {shown.map((image, index) => (
        <div key={index} className={`relative overflow-hidden rounded-md bg-slate-100 ${singleImage ? "w-full" : "aspect-square"}`}>
          <img src={image.src} alt={image.alt ?? "解析图片"} className={singleImage ? "block h-auto w-full" : "h-full w-full object-cover"} referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
          {index === shown.length - 1 && images.length > maxItems ? <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-xl font-bold text-white">+{images.length - maxItems}</span> : null}
        </div>
      ))}
    </div>
  );
}

function formatBilibiliTime(timestamp?: number | null): string | null {
  if (!timestamp) return null;
  const seconds = Math.floor(Date.now() / 1000) - timestamp;
  if (seconds >= 0 && seconds < 60) return "刚刚";
  if (seconds >= 0 && seconds < 3_600) return `${Math.floor(seconds / 60)}分钟前`;
  if (seconds >= 0 && seconds < 86_400) return `${Math.floor(seconds / 3_600)}小时前`;
  if (seconds >= 0 && seconds < 604_800) return `${Math.floor(seconds / 86_400)}天前`;
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.valueOf()) ? null : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(date);
}

function formatDuration(duration?: number): string | null {
  if (duration === undefined || duration < 0) return null;
  const total = Math.round(duration);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function formatCount(value?: number): string {
  if (!value) return "0";
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}亿`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)}万`;
  return String(value);
}

function BilibiliText({ text }: { text: string }) {
  return text.split(/(#[^\s#，。！？、；：]+)/g).map((part, index) => (
    part.startsWith("#") ? <span key={index} className="text-[#00aeec]">{part}</span> : part
  ));
}
