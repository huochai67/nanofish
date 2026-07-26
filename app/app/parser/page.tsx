/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState, type CSSProperties } from "react";
import {
  ArrowUpRight,
  AudioLines,
  Bookmark,
  BadgeCheck,
  CircleUserRound,
  Clapperboard,
  CirclePoundSterling,
  Ellipsis,
  Eye,
  FileText,
  Heart,
  Link as LinkIcon,
  MessageCircle,
  MessageCircleMore,
  MessageSquareText,
  Repeat2,
  Play,
  Send,
  Share2,
  Star,
  ThumbsUp,
  type LucideIcon,
} from "lucide-react";
import {
  MockParserData,
  parseParserScreenshotData,
  type ParserResult,
  type ParserScreenshotData,
  type ParserStats,
} from "./types";
import { parseParserDebugPayload, parserPreviewStorageKey } from "./preview-storage";
import { parseUrlData } from "../utils/url-data";
import { useAssetReadiness } from "../utils/use-asset-readiness";
import { Content, Notice, PageShell } from "../components/chrome";

declare global {
  interface Window {
    __PARSER_DATA__?: ParserScreenshotData;
  }
}

type Theme = {
  label: string;
  accent: string;
  accentSoft: string;
  background: string;
  card: string;
  logo?: string;
  Icon: LucideIcon;
};

const THEMES: Record<string, Theme> = {
  bilibili: {
    label: "Bilibili",
    accent: "#00aeec",
    accentSoft: "#e0f7ff",
    background: "linear-gradient(145deg, #eafaff 0%, #f7fcff 42%, #e9f7ff 100%)",
    card: "#ffffff",
    logo: "/parser/bilibili.png",
    Icon: Clapperboard,
  },
  weibo: {
    label: "微博",
    accent: "#e86b2a",
    accentSoft: "#fff0e6",
    background: "linear-gradient(145deg, #fff7f0 0%, #fffdf9 55%, #fff0e7 100%)",
    card: "#fffefd",
    logo: "/parser/weibo.png",
    Icon: MessageCircleMore,
  },
  xiaohongshu: {
    label: "小红书",
    accent: "#ff2442",
    accentSoft: "#fff0f2",
    background: "linear-gradient(145deg, #fff1f3 0%, #fff 50%, #fff5f5 100%)",
    card: "#ffffff",
    logo: "/parser/xiaohongshu.png",
    Icon: FileText,
  },
  douyin: {
    label: "抖音",
    accent: "#25f4ee",
    accentSoft: "#173e46",
    background: "linear-gradient(145deg, #090a0d 0%, #12151c 55%, #1c1320 100%)",
    card: "#171a20",
    logo: "/parser/douyin.png",
    Icon: Play,
  },
  tiktok: {
    label: "TikTok",
    accent: "#ff3b6b",
    accentSoft: "#3c1c2c",
    background: "linear-gradient(145deg, #090a0d 0%, #12151c 55%, #1a1220 100%)",
    card: "#171a20",
    logo: "/parser/tiktok.png",
    Icon: Play,
  },
  kuaishou: {
    label: "快手",
    accent: "#ff6a00",
    accentSoft: "#fff0e5",
    background: "linear-gradient(145deg, #fff1e8 0%, #fffaf7 50%, #ffe8d6 100%)",
    card: "#ffffff",
    logo: "/parser/kuaishou.png",
    Icon: Clapperboard,
  },
  acfun: {
    label: "AcFun",
    accent: "#fd4c5d",
    accentSoft: "#fff0f2",
    background: "linear-gradient(145deg, #fff0f2 0%, #fff 52%, #fff4f5 100%)",
    card: "#ffffff",
    Icon: Play,
  },
  youtube: {
    label: "YouTube",
    accent: "#ff0033",
    accentSoft: "#fff0f2",
    background: "linear-gradient(145deg, #f6f6f6 0%, #fff 56%, #f3f3f3 100%)",
    card: "#ffffff",
    logo: "/parser/youtube.png",
    Icon: Play,
  },
  youtube_music: {
    label: "YouTube Music",
    accent: "#ff1744",
    accentSoft: "#fff0f2",
    background: "linear-gradient(145deg, #fff1f3 0%, #fff 52%, #f7f0f3 100%)",
    card: "#ffffff",
    Icon: AudioLines,
  },
  spotify: {
    label: "Spotify",
    accent: "#1db954",
    accentSoft: "#e4f8eb",
    background: "linear-gradient(145deg, #e9f8ed 0%, #fff 52%, #eaf7ee 100%)",
    card: "#ffffff",
    Icon: AudioLines,
  },
  netease_music: {
    label: "网易云音乐",
    accent: "#d93026",
    accentSoft: "#fff0ef",
    background: "linear-gradient(145deg, #fff0ef 0%, #fff 52%, #fff3f2 100%)",
    card: "#ffffff",
    Icon: AudioLines,
  },
  qq_music: {
    label: "QQ 音乐",
    accent: "#31c27c",
    accentSoft: "#e4f8ed",
    background: "linear-gradient(145deg, #ebf9f1 0%, #fff 52%, #e7f7ef 100%)",
    card: "#ffffff",
    Icon: AudioLines,
  },
  twitter: {
    label: "X",
    accent: "#111827",
    accentSoft: "#edf1f5",
    background: "linear-gradient(145deg, #eef3f7 0%, #f8fafc 52%, #e9eef3 100%)",
    card: "#ffffff",
    logo: "/parser/twitter.png",
    Icon: MessageCircleMore,
  },
  nga: {
    label: "NGA",
    accent: "#7b5a3f",
    accentSoft: "#f5ead7",
    background: "linear-gradient(145deg, #eee4d3 0%, #f8f3ea 52%, #e9ddc8 100%)",
    card: "#fffdf8",
    Icon: FileText,
  },
};

const DEFAULT_THEME: Theme = {
  label: "链接解析",
  accent: "#4f46e5",
  accentSoft: "#eef2ff",
  background: "linear-gradient(145deg, #eef2ff 0%, #fafaff 52%, #e9edff 100%)",
  card: "#ffffff",
  Icon: Share2,
};

function loadParserData(): { data: ParserScreenshotData; error: string | null } {
  if (typeof window !== "undefined" && window.__PARSER_DATA__) {
    const data = parseParserScreenshotData(window.__PARSER_DATA__);
    return data
      ? { data, error: null }
      : { data: MockParserData, error: "注入的解析数据无效，已回退到默认 Mock 数据。" };
  }

  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const payloadId = params.get("payload");
    if (payloadId) {
      const payload = sessionStorage.getItem(parserPreviewStorageKey(payloadId));
      if (!payload) {
        const error = "上传的 JSON 数据不存在或已过期，已回退到默认 Mock 数据。";
        console.log("[parser preview] Uploaded payload is missing", { payloadId });
        return { data: MockParserData, error };
      }

      try {
        const parsed = parseParserDebugPayload(JSON.parse(payload));
        if (parsed.data) return { data: parsed.data, error: null };
        console.log("[parser preview] Uploaded debug payload was rejected", {
          payloadId,
          error: parsed.error,
        });
        return {
          data: MockParserData,
          error: `上传的调试文件无效：${parsed.error}`,
        };
      } catch (error) {
        console.log("[parser preview] Uploaded payload could not be parsed", error);
        return {
          data: MockParserData,
          error: "上传的 JSON 无法解析，已回退到默认 Mock 数据。",
        };
      }

    }

    const value = params.get("data");
    if (value) {
      const parsed = parseUrlData(value, parseParserScreenshotData);
      return parsed.data
        ? { data: parsed.data, error: null }
        : { data: MockParserData, error: "URL 参数无效，已回退到默认 Mock 数据。" };
    }
  }

  return { data: MockParserData, error: null };
}

function imageCount(result: ParserResult, repost = false, maxGridImages = 9): number {
  const video = result.contents.find((content) => content.kind === "video");
  const images = result.contents.filter(
    (content): content is Extract<ParserResult["contents"][number], { kind: "image" }> =>
      content.kind === "image" && Boolean(content.src),
  );
  const visibleImages = Math.min(images.length, maxGridImages);
  const videoAsset = video?.kind === "video" && video.poster ? 1 : 0;
  const audioAssets = result.contents.filter(
    (content): content is Extract<ParserResult["contents"][number], { kind: "audio" }> => content.kind === "audio",
  ).filter((content) => Boolean(content.cover)).length;

  if (!repost && result.platform.name === "bilibili") {
    return (
      1 +
      Number(Boolean(result.author?.pendant)) +
      (video ? videoAsset : Math.min(images.length, 9))
    );
  }

  if (!repost && result.platform.name === "xiaohongshu") {
    return 1 + Number(Boolean(video?.kind === "video" ? video.poster : images[0]?.src));
  }

  if (!repost && result.platform.name === "twitter") {
    const graphics = !video && images.length === 0
      ? result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src)).length
      : 0;
    return (
      Number(Boolean(result.author?.avatar)) +
      (video ? videoAsset : Math.min(images.length || graphics, maxGridImages)) +
      (result.repost ? imageCount(result.repost, true, maxGridImages) : 0)
    );
  }

  const graphics = !video && images.length === 0
    ? result.graphics.filter((graphic) => graphic.kind === "image" && Boolean(graphic.src)).length
    : 0;
  const platformLogo = Number(Boolean((THEMES[result.platform.name] ?? DEFAULT_THEME).logo));
  return (
    platformLogo +
    Number(Boolean(result.author?.avatar)) +
    (video ? videoAsset : visibleImages) +
    audioAssets +
    graphics +
    (result.repost ? imageCount(result.repost, true, maxGridImages) : 0)
  );
}

function formatTime(timestamp?: number | null): string | null {
  if (!timestamp) return null;
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.valueOf())
    ? null
    : new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
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

function XiaohongshuText({ text }: { text: string }) {
  return text.replaceAll("[话题]", "").split(/(#[^\s#，。！？、；：]+)/g).map((part, index) =>
    part.startsWith("#") ? <span key={index} className="text-[#3f6699]">{part}</span> : part,
  );
}

export default function ParserPage() {
  const [data, setData] = useState<ParserScreenshotData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { status, beginAssetTracking, completeAsset } = useAssetReadiness();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const loadedData = loadParserData();
      setData(loadedData.data);
      setError(loadedData.error);
      beginAssetTracking(
        imageCount(loadedData.data.result, false, loadedData.data.maxGridImages ?? 9),
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, [beginAssetTracking]);

  if (!data) return <div className="min-h-screen bg-paper" data-ready="false" />;

  const theme = THEMES[data.result.platform.name] ?? DEFAULT_THEME;
  return (
    <PageShell
      ready={status}
      style={{ background: theme.background }}
      className="text-slate-900"
    >
      <Content className="space-y-4 py-4 sm:py-6">
        {error ? <Notice>{error}</Notice> : null}
        <ParserCard
          result={data.result}
          theme={theme}
          maxGridImages={data.maxGridImages ?? 9}
          onAsset={completeAsset}
        />
      </Content>
    </PageShell>
  );
}

function ParserCard({
  result,
  theme,
  maxGridImages,
  onAsset,
  repost = false,
}: {
  result: ParserResult;
  theme: Theme;
  maxGridImages: number;
  onAsset: () => void;
  repost?: boolean;
}) {
  if (!repost && result.platform.name === "bilibili") {
    return <BilibiliCard result={result} onAsset={onAsset} />;
  }

  if (!repost && result.platform.name === "xiaohongshu") {
    return <XiaohongshuCard result={result} onAsset={onAsset} />;
  }

  if (!repost && result.platform.name === "twitter") {
    return <TwitterCard result={result} maxGridImages={maxGridImages} onAsset={onAsset} />;
  }

  const dark = result.platform.name === "douyin" || result.platform.name === "tiktok";
  const text = dark ? "text-slate-100" : "text-slate-900";
  const muted = dark ? "text-slate-400" : "text-slate-500";
  const video = result.contents.find((content) => content.kind === "video");
  const images = result.contents.filter(
    (content): content is Extract<typeof content, { kind: "image" }> =>
      content.kind === "image" && Boolean(content.src),
  );
  const audio = result.contents.filter(
    (content): content is Extract<typeof content, { kind: "audio" }> => content.kind === "audio",
  );
  const Icon = theme.Icon;
  const style = { backgroundColor: theme.card } as CSSProperties;

  return (
    <article
      data-parser-card
      className={`overflow-hidden rounded-2xl border ${
        dark ? "border-white/10" : "border-black/[0.06]"
      } ${repost ? "shadow-none" : "shadow-pop"}`}
      style={style}
    >
      <div className={`flex items-center justify-between gap-2 border-b px-4 py-3 sm:px-5 ${dark ? "border-white/10" : "border-black/[0.05]"}`}>
        <div className="flex min-w-0 items-center gap-2">
          {theme.logo ? (
            <img
              src={theme.logo}
              alt=""
              className="h-6 max-w-24 object-contain"
              onLoad={onAsset}
              onError={onAsset}
            />
          ) : (
            <>
              <Icon size={17} strokeWidth={2.5} style={{ color: theme.accent }} />
              <span className={`text-xs font-bold tracking-wide ${text}`}>{theme.label}</span>
            </>
          )}
          {result.contentType ? (
            <span
              className="rounded-md px-1.5 py-0.5 text-[10px] font-semibold"
              style={{
                backgroundColor: theme.accentSoft,
                color: dark ? "#e2e8f0" : theme.accent,
              }}
            >
              {result.contentType}
            </span>
          ) : null}
        </div>
        <ArrowUpRight size={15} className={`shrink-0 ${muted}`} />
      </div>

      <div className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
        {result.author ? (
          <div className="flex items-center gap-3">
            {result.author.avatar ? (
              <img
                src={result.author.avatar}
                alt=""
                className="h-10 w-10 rounded-full object-cover ring-1 ring-black/[0.06]"
                referrerPolicy="no-referrer"
                onLoad={onAsset}
                onError={onAsset}
              />
            ) : (
              <span
                className="flex h-10 w-10 items-center justify-center rounded-full text-white"
                style={{ backgroundColor: theme.accent }}
              >
                <CircleUserRound size={21} />
              </span>
            )}
            <div className="min-w-0">
              <p className={`truncate text-sm font-semibold ${text}`}>{result.author.name}</p>
              <p className={`truncate text-xs ${muted}`}>{formatTime(result.timestamp) ?? result.author.description ?? ""}</p>
            </div>
          </div>
        ) : null}

        {result.title ? <h1 className={`text-lg font-bold leading-snug sm:text-xl ${text}`}>{result.title}</h1> : null}
        {result.text ? <p className={`whitespace-pre-wrap text-[15px] leading-7 ${text}`}>{result.text}</p> : null}

        {video?.kind === "video" ? <VideoView media={video} onAsset={onAsset} /> : null}
        {!video && images.length ? <MediaGrid images={images} maxItems={maxGridImages} onAsset={onAsset} /> : null}

        {result.graphics.length && !video && !images.length ? (
          <div className={`space-y-3 rounded-xl p-3 ${dark ? "bg-white/5" : "bg-slate-50"}`}>
            {result.graphics.map((graphic, index) =>
              graphic.kind === "text" ? (
                <p key={index} className={`whitespace-pre-wrap text-sm leading-6 ${text}`}>{graphic.text}</p>
              ) : graphic.src ? (
                <img
                  key={index}
                  src={graphic.src}
                  alt={graphic.alt ?? "解析图片"}
                  className="max-h-[560px] w-full rounded-lg object-contain"
                  referrerPolicy="no-referrer"
                  onLoad={onAsset}
                  onError={onAsset}
                />
              ) : null,
            )}
          </div>
        ) : null}

        {audio.map((media, index) => (
          <div key={index} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${dark ? "bg-white/10 text-slate-200" : "bg-slate-50 text-slate-600"}`}>
            {media.cover ? (
              <img
                src={media.cover}
                alt="专辑封面"
                className="h-10 w-10 rounded-lg object-cover shadow-sm"
                referrerPolicy="no-referrer"
                onLoad={onAsset}
                onError={onAsset}
              />
            ) : <AudioLines size={17} style={{ color: theme.accent }} />}
            <span>音频内容</span>
            {formatDuration(media.duration) ? <span className="ml-auto text-xs opacity-70">{formatDuration(media.duration)}</span> : null}
          </div>
        ))}

        {result.extraInfo ? (
          <div className={`rounded-lg border-l-[3px] px-3.5 py-2.5 text-sm leading-6 ${dark ? "bg-white/5 text-slate-300" : "bg-slate-50 text-slate-600"}`} style={{ borderLeftColor: theme.accent }}>
            {result.extraInfo}
          </div>
        ) : null}

        {result.repost ? (
          <div className={`rounded-xl p-2 ${dark ? "bg-white/5" : "bg-slate-50"}`}>
            <div className={`mb-2 flex items-center gap-1.5 px-1.5 text-xs ${muted}`}><Share2 size={13} /> 转发内容</div>
            <ParserCard result={result.repost} theme={THEMES[result.repost.platform.name] ?? theme} maxGridImages={maxGridImages} onAsset={onAsset} repost />
          </div>
        ) : null}

        {result.stats ? <StatsRow stats={result.stats} dark={dark} /> : null}

        {result.url ? (
          <div className={`flex min-w-0 items-center gap-1.5 text-xs ${muted}`}>
            <LinkIcon size={13} className="shrink-0" style={{ color: theme.accent }} />
            <span className="truncate">{result.url}</span>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function StatsRow({ stats, dark }: { stats: ParserStats; dark: boolean }) {
  const items = [
    { Icon: Eye, value: stats.view },
    { Icon: MessageSquareText, value: stats.danmaku },
    { Icon: ThumbsUp, value: stats.like },
    { Icon: MessageCircle, value: stats.comment ?? stats.reply },
    { Icon: Star, value: stats.favorite },
    { Icon: Bookmark, value: stats.collect },
    { Icon: CirclePoundSterling, value: stats.coin },
    { Icon: Share2, value: stats.share },
  ].filter((item) => item.value);
  if (!items.length) return null;

  return (
    <div
      className={`flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t pt-3 text-xs ${
        dark ? "border-white/10 text-slate-400" : "border-black/[0.05] text-slate-500"
      }`}
    >
      {items.map(({ Icon, value }, index) => (
        <span key={index} className="inline-flex items-center gap-1.5">
          <Icon size={14} />
          {formatCount(value)}
        </span>
      ))}
    </div>
  );
}

function BilibiliCard({ result, onAsset }: { result: ParserResult; onAsset: () => void }) {
  const video = result.contents.find(
    (content): content is Extract<ParserResult["contents"][number], { kind: "video" }> => content.kind === "video",
  );
  const images = result.contents.filter(
    (content): content is Extract<ParserResult["contents"][number], { kind: "image" }> =>
      content.kind === "image" && Boolean(content.src),
  );
  const body = result.text ?? result.title;

  return (
    <article data-parser-card className="flex gap-3 rounded-2xl border border-black/[0.06] bg-white px-4 py-4 shadow-pop sm:px-5">
      <aside className="shrink-0">
        <div className="relative h-11 w-11">
          {result.author?.avatar ? (
            <img
              src={result.author.avatar}
              alt=""
              className="h-11 w-11 rounded-full object-cover"
              referrerPolicy="no-referrer"
              onLoad={onAsset}
              onError={onAsset}
            />
          ) : (
            <img
              src="/parser/avatar.png"
              alt=""
              className="h-11 w-11 rounded-full object-cover"
              onLoad={onAsset}
              onError={onAsset}
            />
          )}
          {result.author?.pendant ? (
            <img
              src={result.author.pendant}
              alt=""
              className="pointer-events-none absolute -inset-1 h-[52px] w-[52px] max-w-none object-contain"
              referrerPolicy="no-referrer"
              onLoad={onAsset}
              onError={onAsset}
            />
          ) : null}
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-start">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-semibold text-[#fb7299]">{result.author?.name ?? "哔哩哔哩用户"}</p>
            <p className="mt-0.5 text-xs text-[#99a2aa]">
              {formatTime(result.timestamp) ?? result.author?.description ?? "刚刚"}
              {video ? " · 投稿了视频" : ""}
            </p>
          </div>
          <Ellipsis size={20} className="mt-1 shrink-0 text-[#99a2aa]" />
        </header>

        {body ? <p className="mt-2.5 whitespace-pre-wrap text-[15px] leading-6 text-[#18191c]">{body}</p> : null}

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
          <div className="mt-3"><MediaGrid images={images} maxItems={9} onAsset={onAsset} /></div>
        ) : null}

        <footer className="mt-4 grid grid-cols-3 border-t border-[#f1f2f3] pt-3 text-[#7d8590]">
          <span className="flex items-center justify-center gap-1.5 text-sm"><Share2 size={17} />{formatCount(result.stats?.share)}</span>
          <span className="flex items-center justify-center gap-1.5 text-sm"><MessageCircle size={17} />{formatCount(result.stats?.reply)}</span>
          <span className="flex items-center justify-center gap-1.5 text-sm"><ThumbsUp size={17} />{formatCount(result.stats?.like)}</span>
        </footer>
      </div>
    </article>
  );
}

function XiaohongshuCard({ result, onAsset }: { result: ParserResult; onAsset: () => void }) {
  const video = result.contents.find(
    (content): content is Extract<ParserResult["contents"][number], { kind: "video" }> => content.kind === "video",
  );
  const image = result.contents.find(
    (content): content is Extract<ParserResult["contents"][number], { kind: "image" }> =>
      content.kind === "image" && Boolean(content.src),
  );
  const media = video?.poster ?? image?.src;

  return (
    <article data-parser-card className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white shadow-pop sm:flex">
      <section className="relative flex aspect-[4/5] items-center justify-center bg-[#202124] sm:aspect-auto sm:min-h-[600px] sm:w-[52%]">
        {media ? <img src={media} alt={result.title ?? "解析媒体"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <div className="h-full w-full bg-gradient-to-br from-[#434343] to-[#111]" />}
        {video ? (
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/90 pl-1 text-[#222] shadow-xl"><Play size={30} fill="currentColor" /></span>
          </span>
        ) : null}
        {video?.duration !== undefined ? <span className="absolute bottom-4 right-4 rounded bg-black/60 px-2 py-1 text-xs text-white">{formatDuration(video.duration)}</span> : null}
      </section>

      <section className="flex flex-1 flex-col px-4 py-4 sm:min-h-[600px] sm:px-5 sm:py-5">
        <header className="flex items-center gap-2.5">
          {result.author?.avatar ? (
            <img src={result.author.avatar} alt="" className="h-10 w-10 rounded-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
          ) : (
            <img
              src="/parser/avatar.png"
              alt=""
              className="h-10 w-10 rounded-full object-cover"
              onLoad={onAsset}
              onError={onAsset}
            />
          )}
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

function formatTwitterTimestamp(timestamp?: number | null): string | null {
  if (!timestamp) return null;
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.valueOf())) return null;

  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  const calendar = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
  return `${time} · ${calendar}`;
}

function formatTwitterCount(value?: number): string {
  if (!value) return "0";
  const abbreviate = (divisor: number, suffix: string) => {
    const count = (value / divisor).toFixed(1).replace(/\.0$/, "");
    return `${count}${suffix}`;
  };
  if (value >= 1_000_000_000) return abbreviate(1_000_000_000, "B");
  if (value >= 1_000_000) return abbreviate(1_000_000, "M");
  if (value >= 1_000) return abbreviate(1_000, "K");
  return String(value);
}

function TwitterCard({
  result,
  maxGridImages,
  onAsset,
}: {
  result: ParserResult;
  maxGridImages: number;
  onAsset: () => void;
}) {
  const video = result.contents.find(
    (content): content is Extract<ParserResult["contents"][number], { kind: "video" }> => content.kind === "video",
  );
  const contentImages = result.contents.filter(
    (content): content is Extract<ParserResult["contents"][number], { kind: "image" }> =>
      content.kind === "image" && Boolean(content.src),
  );
  const graphicImages = result.graphics.filter(
    (graphic): graphic is Extract<ParserResult["graphics"][number], { kind: "image" }> =>
      graphic.kind === "image" && Boolean(graphic.src),
  );
  const images = (contentImages.length ? contentImages : graphicImages).slice(0, maxGridImages);
  const handle = result.author?.description?.startsWith("@")
    ? result.author.description
    : result.author?.name
      ? `@${result.author.name.replaceAll(/\s+/g, "")}`
      : "@twitter";
  const tweet = result.text ?? result.title;
  const timestamp = formatTwitterTimestamp(result.timestamp);
  const views = result.stats?.view ? formatTwitterCount(result.stats.view) : null;
  const actionItems = [
    { Icon: MessageCircle, value: result.stats?.reply ?? result.stats?.comment },
    { Icon: Repeat2, value: result.stats?.share },
    { Icon: Heart, value: result.stats?.like },
    { Icon: Bookmark, value: result.stats?.collect },
  ];

  return (
    <article data-parser-card className="bg-white px-4 py-3 text-[#0f1419] sm:px-5">
      <div className="flex gap-3">
        {result.author?.avatar ? (
          <img
            src={result.author.avatar}
            alt=""
            className="h-10 w-10 shrink-0 rounded object-cover"
            referrerPolicy="no-referrer"
            onLoad={onAsset}
            onError={onAsset}
          />
        ) : (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-[#0f1419] text-white">
            <CircleUserRound size={22} />
          </span>
        )}

        <div className="min-w-0 flex-1">
          <header className="flex items-start gap-1">
            <div className="min-w-0 flex-1 leading-5">
              <div className="flex min-w-0 items-center gap-1">
                <span className="truncate text-[15px] font-bold">{result.author?.name ?? "X 用户"}</span>
                <BadgeCheck size={17} className="shrink-0 text-[#1d9bf0]" fill="currentColor" stroke="white" strokeWidth={2.5} />
              </div>
              <p className="truncate text-sm text-[#536471]">{handle}</p>
            </div>
            <Ellipsis size={20} className="mt-0.5 shrink-0 text-[#536471]" />
          </header>

          {tweet ? <p className="mt-3 whitespace-pre-wrap text-base leading-6">{tweet}</p> : null}

          {video?.poster ? (
            <div className="relative mt-3 w-fit max-w-full overflow-hidden rounded-2xl border border-[#cfd9de] bg-[#f7f9f9]">
              <img src={video.poster} alt={result.title ?? "视频"} className="block h-auto max-h-[600px] max-w-full w-auto" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
              <span className="absolute inset-0 flex items-center justify-center"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/70 pl-0.5 text-white"><Play size={22} fill="currentColor" /></span></span>
            </div>
          ) : null}

          {images.length ? (
            <div className="mt-3 space-y-2">
              {images.map((image, index) => (
                <div key={index} className="w-fit max-w-full overflow-hidden rounded-2xl border border-[#cfd9de] bg-[#f7f9f9]">
                  <img src={image.src} alt={image.alt ?? "推文图片"} className="block h-auto max-h-[600px] max-w-full w-auto" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
                </div>
              ))}
            </div>
          ) : null}

          {timestamp || views ? (
            <p className="mt-3 text-sm text-[#536471]">
              {timestamp ? <>{timestamp}{views ? " · " : null}</> : null}
              {views ? <><span className="font-bold text-[#0f1419]">{views}</span> Views</> : null}
            </p>
          ) : null}
          <footer className="mt-3 flex items-center justify-between border-t border-[#eff3f4] pt-3 text-[#536471]">
            {actionItems.map(({ Icon, value }, index) => (
              <span key={index} className="inline-flex min-w-0 items-baseline gap-1 text-xs">
                <Icon size={24} strokeWidth={1.8} />
                {value ? <span>{formatTwitterCount(value)}</span> : null}
              </span>
            ))}
            <Share2 size={24} strokeWidth={1.8} />
          </footer>
        </div>
      </div>
    </article>
  );
}

function VideoView({ media, onAsset }: { media: Extract<ParserResult["contents"][number], { kind: "video" }>; onAsset: () => void }) {
  return (
    <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-900">
      {media.poster ? <img src={media.poster} alt="视频封面" className="h-full w-full object-cover opacity-90" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} /> : <div className="h-full w-full bg-gradient-to-br from-slate-700 to-slate-950" />}
      <span className="absolute inset-0 flex items-center justify-center"><span className="flex h-14 w-14 items-center justify-center rounded-full bg-white/90 pl-0.5 text-slate-900 shadow-xl"><Play size={26} fill="currentColor" /></span></span>
      {formatDuration(media.duration) ? <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-2 py-1 text-[11px] font-medium text-white">{formatDuration(media.duration)}</span> : null}
    </div>
  );
}

function MediaGrid({ images, maxItems, onAsset }: { images: Extract<ParserResult["contents"][number], { kind: "image" }>[]; maxItems: number; onAsset: () => void }) {
  const shown = images.slice(0, maxItems);
  const columns = shown.length === 1 ? "grid-cols-1" : shown.length <= 4 ? "grid-cols-2" : "grid-cols-3";
  return (
    <div className={`grid gap-1.5 ${columns}`}>
      {shown.map((image, index) => (
        <div key={index} className={`relative overflow-hidden rounded-xl bg-slate-100 ${shown.length === 1 ? "max-h-[560px]" : "aspect-square"}`}>
          <img src={image.src} alt={image.alt ?? "解析图片"} className="h-full w-full object-cover" referrerPolicy="no-referrer" onLoad={onAsset} onError={onAsset} />
          {index === shown.length - 1 && images.length > maxItems ? <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-xl font-bold text-white">+{images.length - maxItems}</span> : null}
        </div>
      ))}
    </div>
  );
}
