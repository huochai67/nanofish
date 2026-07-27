/* eslint-disable @next/next/no-img-element */

import {
  CircleUserRound,
  EllipsisVertical,
  MessageSquareText,
  Play,
  Share2,
  ThumbsUp,
} from "lucide-react";
import { assetCount, GenericCard, type PlatformAppearance } from "./generic";
import type { ParserPost, ParserResult, PostMedia } from "../types";

export const appearance: PlatformAppearance = {
  label: "YouTube",
  accent: "#ff0033",
  accentSoft: "#fff0f2",
  background: "#ffffff",
  card: "#ffffff",
  logo: "/parser/youtube.png",
  Icon: Play,
};

export function Youtube({ result, maxGridImages, onAsset }: { result: ParserResult; maxGridImages: number; onAsset: () => void }) {
  return result.kind === "music" ? (
    <GenericCard result={result} appearance={appearance} maxGridImages={maxGridImages} onAsset={onAsset} />
  ) : (
    <YoutubePost result={result} maxGridImages={maxGridImages} onAsset={onAsset} />
  );
}

export function countAssets(result: ParserResult, maxGridImages: number) {
  if (result.kind === "music") return assetCount(result, maxGridImages, appearance);

  const video = result.media.find((media) => media.kind === "video");
  const mediaImages = result.media.filter((media) => media.kind === "image" && Boolean(media.src));
  const graphicImages = result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src));
  const imageCount = mediaImages.length ? mediaImages.length : graphicImages.length;

  return Number(Boolean(result.author?.avatar)) + (video?.kind === "video" && video.poster ? 1 : Math.min(imageCount, maxGridImages));
}

function YoutubePost({ result, maxGridImages, onAsset }: { result: ParserPost; maxGridImages: number; onAsset: () => void }) {
  const video = result.media.find(
    (media): media is Extract<PostMedia, { kind: "video" }> => media.kind === "video",
  );
  const mediaImages = result.media.filter(
    (media): media is Extract<PostMedia, { kind: "image" }> => media.kind === "image" && Boolean(media.src),
  );
  const graphicImages = result.graphics.filter(
    (graphic): graphic is Extract<ParserPost["graphics"][number], { kind: "image" }> => graphic.kind === "image" && Boolean(graphic.src),
  );
  const images = (mediaImages.length ? mediaImages : graphicImages).slice(0, maxGridImages);
  const postText = result.text ?? result.title;
  const timestamp = formatRelativeTime(result.timestamp) ?? result.author?.description;
  const commentCount = result.stats?.comment ?? result.stats?.reply;

  return (
    <article data-parser-card className="rounded-xl border border-[#d6d6d6] bg-white px-4 py-4 text-[#0f0f0f]">
      <div className="flex gap-4">
        {result.author?.avatar ? (
          <img
            src={result.author.avatar}
            alt=""
            className="h-10 w-10 shrink-0 rounded-full object-cover"
            referrerPolicy="no-referrer"
            onLoad={onAsset}
            onError={onAsset}
          />
        ) : (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#606060] text-white">
            <CircleUserRound size={22} />
          </span>
        )}

        <div className="min-w-0 flex-1">
          <header className="flex min-h-5 items-center gap-2">
            <span className="truncate text-sm font-semibold leading-5">{result.author?.name ?? "YouTube 用户"}</span>
            {timestamp ? <span className="truncate text-xs leading-5 text-[#606060]">{timestamp}</span> : null}
            <EllipsisVertical size={20} strokeWidth={2.4} className="ml-auto shrink-0 text-[#0f0f0f]" />
          </header>

          {postText ? <p className="mt-0.5 whitespace-pre-wrap text-[16px] leading-[1.4]">{postText}</p> : null}

          {video ? <VideoMedia media={video} title={result.title} viewCount={result.stats?.view} timestamp={formatRelativeTime(result.timestamp)} onAsset={onAsset} /> : null}
          {!video && images.length ? <div className="mt-1.5 space-y-2">{images.map((image, index) => <ImageMedia key={index} image={image} onAsset={onAsset} />)}</div> : null}

          <footer className={`${video ? "mt-5" : "mt-3"} flex items-center text-[#0f0f0f]`}>
            <span className="inline-flex w-[53px] items-center gap-1.5 text-xs"><ThumbsUp size={21} strokeWidth={2} />{result.stats?.like ? formatCount(result.stats.like) : null}</span>
            <span className="inline-flex w-[54px] items-center gap-1.5 text-xs"><Share2 size={20} strokeWidth={2} />{result.stats?.share ? formatCount(result.stats.share) : null}</span>
            <span className="inline-flex items-center gap-1.5 text-xs"><MessageSquareText size={20} strokeWidth={2} />{commentCount ? formatCount(commentCount) : null}</span>
          </footer>
        </div>
      </div>
    </article>
  );
}

function ImageMedia({ image, onAsset }: { image: Extract<PostMedia, { kind: "image" }>; onAsset: () => void }) {
  return (
    <div className="w-fit max-w-full overflow-hidden rounded-xl bg-black">
      <img
        src={image.src}
        alt={image.alt ?? "YouTube 社区帖图片"}
        className="block h-auto max-h-[600px] max-w-full w-auto"
        referrerPolicy="no-referrer"
        onLoad={onAsset}
        onError={onAsset}
      />
    </div>
  );
}

function VideoMedia({
  media,
  title,
  viewCount,
  timestamp,
  onAsset,
}: {
  media: Extract<PostMedia, { kind: "video" }>;
  title?: string | null;
  viewCount?: number;
  timestamp: string | null;
  onAsset: () => void;
}) {
  const meta = [viewCount ? `${formatCount(viewCount)} views` : null, timestamp].filter(Boolean).join(" · ");

  return (
    <div className="ml-2 mt-2 flex w-full max-w-[482px] items-start gap-2">
      <div className="relative h-[118px] w-[209px] shrink-0 overflow-hidden rounded-lg bg-[#0f0f0f]">
        {media.poster ? <img src={media.poster} alt={title ?? "YouTube 视频"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : null}
        {formatDuration(media.duration) ? <span className="absolute bottom-1 right-1 rounded-sm bg-black/80 px-1 py-px text-xs font-semibold leading-4 text-white">{formatDuration(media.duration)}</span> : null}
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className="truncate text-[16px] leading-[1.35]">{title ?? "YouTube 视频"}</p>
        {meta ? <p className="mt-0.5 truncate text-xs leading-4 text-[#606060]">{meta}</p> : null}
      </div>
      <EllipsisVertical size={20} strokeWidth={2.4} className="mt-0.5 shrink-0 text-[#0f0f0f]" />
    </div>
  );
}

function formatRelativeTime(timestamp?: number | null): string | null {
  if (!timestamp) return null;
  const seconds = Math.floor(Date.now() / 1000) - timestamp;
  if (seconds < 0) return null;
  if (seconds < 60) return "just now";
  if (seconds < 3_600) return `${Math.floor(seconds / 60)} minutes ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)} hours ago`;
  if (seconds < 604_800) return `${Math.floor(seconds / 86_400)} days ago`;
  if (seconds < 2_592_000) return `${Math.floor(seconds / 604_800)} weeks ago`;
  if (seconds < 31_536_000) return `${Math.floor(seconds / 2_629_800)} months ago`;
  return `${Math.floor(seconds / 31_536_000)} years ago`;
}

function formatCount(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(value);
}

function formatDuration(duration?: number): string | null {
  if (duration === undefined || duration < 0) return null;
  const total = Math.round(duration);
  const seconds = String(total % 60).padStart(2, "0");
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes}:${seconds}`;
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${seconds}`;
}
