import {
  asRecord,
  optionalNullableNumber,
  optionalNullableString,
  optionalString,
} from "@/app/utils/data-validation";

export type ParserMedia =
  | { kind: "image"; src?: string; alt?: string }
  | { kind: "video"; poster?: string; duration?: number; isGif?: boolean }
  | { kind: "audio"; duration?: number };

export type ParserGraphic =
  | { kind: "text"; text: string }
  | { kind: "image"; src?: string; alt?: string };

export interface ParserStats {
  view?: number;
  danmaku?: number;
  reply?: number;
  favorite?: number;
  coin?: number;
  share?: number;
  like?: number;
  collect?: number;
  comment?: number;
}

export interface ParserResult {
  platform: { name: string; displayName: string };
  author?: { name: string; avatar?: string; pendant?: string; description?: string } | null;
  title?: string | null;
  text?: string | null;
  timestamp?: number | null;
  url?: string | null;
  contentType?: string | null;
  contents: ParserMedia[];
  graphics: ParserGraphic[];
  extraInfo?: string | null;
  stats?: ParserStats | null;
  repost?: ParserResult | null;
}

export interface ParserScreenshotData {
  result: ParserResult;
  maxGridImages?: number;
}

function parseMedia(value: unknown): ParserMedia | null {
  const media = asRecord(value);
  const kind = media?.kind;
  if (!media || typeof kind !== "string") return null;

  if (kind === "image") {
    return { kind, src: optionalString(media, "src"), alt: optionalString(media, "alt") };
  }
  if (kind === "video") {
    const duration = media.duration;
    if (duration !== undefined && (typeof duration !== "number" || !Number.isFinite(duration))) {
      return null;
    }
    if (media.isGif !== undefined && typeof media.isGif !== "boolean") return null;
    return {
      kind,
      poster: optionalString(media, "poster"),
      duration,
      isGif: media.isGif as boolean | undefined,
    };
  }
  if (kind === "audio") {
    const duration = media.duration;
    return duration === undefined || (typeof duration === "number" && Number.isFinite(duration))
      ? { kind, duration }
      : null;
  }

  return null;
}

function parseGraphic(value: unknown): ParserGraphic | null {
  const graphic = asRecord(value);
  const kind = graphic?.kind;
  if (!graphic || typeof kind !== "string") return null;
  if (kind === "text") {
    const text = optionalString(graphic, "text");
    return text === undefined ? null : { kind, text };
  }
  if (kind === "image") {
    return { kind, src: optionalString(graphic, "src"), alt: optionalString(graphic, "alt") };
  }
  return null;
}

function parseStats(value: unknown): ParserStats | null {
  if (value === undefined || value === null) return value === null ? null : {};
  const stats = asRecord(value);
  if (!stats) return null;

  const parsed: Record<string, number> = {};
  for (const key of ["view", "danmaku", "reply", "favorite", "coin", "share", "like", "collect", "comment"]) {
    const count = stats[key];
    if (count === undefined) continue;
    if (typeof count !== "number" || !Number.isFinite(count)) return null;
    parsed[key] = count;
  }
  return parsed;
}

function parseResult(value: unknown, depth = 0): ParserResult | null {
  if (depth > 4) return null;
  const result = asRecord(value);
  const platform = result && asRecord(result.platform);
  const platformName = platform ? optionalString(platform, "name") : undefined;
  const displayName = platform ? optionalString(platform, "displayName") : undefined;
  if (!result || !platform || platformName === undefined || displayName === undefined) return null;
  if (!Array.isArray(result.contents) || !Array.isArray(result.graphics)) return null;

  const contents = result.contents.map(parseMedia);
  const graphics = result.graphics.map(parseGraphic);
  if (contents.some((content) => content === null) || graphics.some((graphic) => graphic === null)) {
    return null;
  }

  let author: ParserResult["author"];
  if (result.author === null) {
    author = null;
  } else if (result.author !== undefined) {
    const rawAuthor = asRecord(result.author);
    const name = rawAuthor ? optionalString(rawAuthor, "name") : undefined;
    if (!rawAuthor || name === undefined) return null;
    author = {
      name,
      avatar: optionalString(rawAuthor, "avatar"),
      pendant: optionalString(rawAuthor, "pendant"),
      description: optionalString(rawAuthor, "description"),
    };
  }

  const stats = parseStats(result.stats);
  if (result.stats !== undefined && stats === null) return null;

  let repost: ParserResult | null | undefined;
  if (result.repost === null) {
    repost = null;
  } else if (result.repost !== undefined) {
    repost = parseResult(result.repost, depth + 1);
    if (!repost) return null;
  }

  return {
    platform: { name: platformName, displayName },
    author,
    title: optionalNullableString(result, "title"),
    text: optionalNullableString(result, "text"),
    timestamp: optionalNullableNumber(result, "timestamp"),
    url: optionalNullableString(result, "url"),
    contentType: optionalNullableString(result, "contentType"),
    contents: contents as ParserMedia[],
    graphics: graphics as ParserGraphic[],
    extraInfo: optionalNullableString(result, "extraInfo"),
    stats: stats ?? undefined,
    repost,
  };
}

export function parseParserScreenshotData(value: unknown): ParserScreenshotData | null {
  const data = asRecord(value);
  const result = data ? parseResult(data.result) : null;
  if (!data || !result) return null;

  const maxGridImages = data.maxGridImages;
  if (
    maxGridImages !== undefined &&
    (typeof maxGridImages !== "number" || !Number.isInteger(maxGridImages) || maxGridImages < 1)
  ) {
    return null;
  }

  return { result, maxGridImages };
}

export const MockParserData: ParserScreenshotData = {
  maxGridImages: 9,
  result: {
    platform: { name: "bilibili", displayName: "哔哩哔哩" },
    author: { name: "Nanofish", description: "一个示例创作者" },
    title: "这是一个平台化媒体解析卡片",
    text: "卡片会根据来源平台切换视觉主题，并保留媒体、正文与转发信息。",
    timestamp: 1_735_689_600,
    url: "https://www.bilibili.com/video/BV1xx411c7mD",
    contentType: "视频",
    contents: [{ kind: "video", duration: 125 }],
    graphics: [],
    stats: {
      view: 125_600,
      danmaku: 348,
      reply: 91,
      favorite: 4_206,
      coin: 1_102,
      share: 56,
      like: 12_800,
    },
    extraInfo: "媒体解析由 Nanofish 完成",
  },
};
