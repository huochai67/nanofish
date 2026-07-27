import {
  asRecord,
  optionalNullableNumber,
  optionalNullableString,
  optionalSafeUrl,
  optionalString,
} from "@/app/utils/data-validation";

export type Platform = { name: string; displayName: string };

export type Author = {
  name: string;
  avatar?: string;
  pendant?: string;
  description?: string;
};

export type PostMedia =
  | { kind: "image"; src?: string; alt?: string }
  | { kind: "video"; poster?: string; duration?: number; isGif?: boolean };

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

interface ParserBase {
  platform: Platform;
  author?: Author | null;
  timestamp?: number | null;
  url?: string | null;
  contentType?: string | null;
  extraInfo?: string | null;
  stats?: ParserStats | null;
}

export interface ParserPost extends ParserBase {
  kind: "post";
  title?: string | null;
  text?: string | null;
  media: PostMedia[];
  graphics: ParserGraphic[];
  repost?: ParserPost | null;
}

export interface ParserMusic extends ParserBase {
  kind: "music";
  title: string;
  artist?: string | null;
  album?: string | null;
  cover?: string | null;
  duration?: number | null;
}

export type ParserResult = ParserPost | ParserMusic;

export interface ParserScreenshotData {
  result: ParserResult;
  maxGridImages?: number;
}

function parsePostMedia(value: unknown): PostMedia | null {
  const media = asRecord(value);
  const kind = media?.kind;
  if (!media || typeof kind !== "string") return null;

  if (kind === "image") {
    const src = optionalSafeUrl(media, "src");
    return src === null ? null : { kind, src, alt: optionalString(media, "alt") };
  }
  if (kind === "video") {
    const duration = media.duration;
    if (duration !== undefined && (typeof duration !== "number" || !Number.isFinite(duration) || duration < 0)) {
      return null;
    }
    if (media.isGif !== undefined && typeof media.isGif !== "boolean") return null;
    const poster = optionalSafeUrl(media, "poster");
    if (poster === null) return null;
    return {
      kind,
      poster,
      duration,
      isGif: media.isGif as boolean | undefined,
    };
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
    const src = optionalSafeUrl(graphic, "src");
    return src === null ? null : { kind, src, alt: optionalString(graphic, "alt") };
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
    if (typeof count !== "number" || !Number.isFinite(count) || count < 0) return null;
    parsed[key] = count;
  }
  return parsed;
}

function parseAuthor(value: unknown): Author | null | undefined {
  if (value === undefined || value === null) return value;
  const author = asRecord(value);
  const name = author ? optionalString(author, "name") : undefined;
  if (!author || name === undefined) return undefined;
  const avatar = optionalSafeUrl(author, "avatar");
  const pendant = optionalSafeUrl(author, "pendant");
  if (avatar === null || pendant === null) return undefined;
  return {
    name,
    avatar,
    pendant,
    description: optionalString(author, "description"),
  };
}

function parseBase(value: Record<string, unknown>): ParserBase | null {
  const platform = asRecord(value.platform);
  const name = platform ? optionalString(platform, "name") : undefined;
  const displayName = platform ? optionalString(platform, "displayName") : undefined;
  if (!platform || name === undefined || displayName === undefined) return null;

  const author = parseAuthor(value.author);
  if (value.author !== undefined && author === undefined) return null;
  const stats = parseStats(value.stats);
  if (value.stats !== undefined && value.stats !== null && stats === null) return null;
  const url = value.url === null ? null : optionalSafeUrl(value, "url");
  if (url === null && value.url !== null) return null;

  return {
    platform: { name, displayName },
    author,
    timestamp: optionalNullableNumber(value, "timestamp"),
    url,
    contentType: optionalNullableString(value, "contentType"),
    extraInfo: optionalNullableString(value, "extraInfo"),
    stats: stats ?? undefined,
  };
}

function parsePost(value: Record<string, unknown>, depth: number): ParserPost | null {
  if (depth > 4 || !Array.isArray(value.media) || value.media.length > 20 || !Array.isArray(value.graphics) || value.graphics.length > 20) {
    return null;
  }
  const base = parseBase(value);
  if (!base) return null;
  const media = value.media.map(parsePostMedia);
  const graphics = value.graphics.map(parseGraphic);
  if (media.some((item) => item === null) || graphics.some((item) => item === null)) return null;

  let repost: ParserPost | null | undefined;
  if (value.repost === null) {
    repost = null;
  } else if (value.repost !== undefined) {
    const rawRepost = asRecord(value.repost);
    if (!rawRepost || rawRepost.kind !== "post") return null;
    repost = parsePost(rawRepost, depth + 1);
    if (!repost) return null;
  }

  return {
    ...base,
    kind: "post",
    title: optionalNullableString(value, "title"),
    text: optionalNullableString(value, "text"),
    media: media as PostMedia[],
    graphics: graphics as ParserGraphic[],
    repost,
  };
}

function parseMusic(value: Record<string, unknown>): ParserMusic | null {
  const base = parseBase(value);
  const title = optionalString(value, "title");
  if (!base || title === undefined) return null;
  const cover = value.cover === null ? null : optionalSafeUrl(value, "cover");
  if (cover === null && value.cover !== null) return null;
  const duration = optionalNullableNumber(value, "duration");
  if (duration !== undefined && duration !== null && duration < 0) return null;

  return {
    ...base,
    kind: "music",
    title,
    artist: optionalNullableString(value, "artist"),
    album: optionalNullableString(value, "album"),
    cover,
    duration,
  };
}

function parseResult(value: unknown, depth = 0): ParserResult | null {
  const result = asRecord(value);
  if (!result) return null;
  if (result.kind === "post") return parsePost(result, depth);
  if (result.kind === "music") return parseMusic(result);
  return null;
}

export function parseParserScreenshotData(value: unknown): ParserScreenshotData | null {
  const data = asRecord(value);
  const result = data ? parseResult(data.result) : null;
  if (!data || !result) return null;

  const maxGridImages = data.maxGridImages;
  if (
    maxGridImages !== undefined &&
    (typeof maxGridImages !== "number" || !Number.isInteger(maxGridImages) || maxGridImages < 1 || maxGridImages > 9)
  ) {
    return null;
  }

  return { result, maxGridImages };
}

export const MockParserData: ParserScreenshotData = {
  maxGridImages: 9,
  result: {
    kind: "post",
    platform: { name: "bilibili", displayName: "哔哩哔哩" },
    author: { name: "Nanofish", description: "一个示例创作者" },
    title: "这是一个平台化媒体解析卡片",
    text: "卡片会根据来源平台切换视觉主题，并保留媒体、正文与转发信息。",
    timestamp: 1_735_689_600,
    url: "https://www.bilibili.com/video/BV1xx411c7mD",
    contentType: "视频",
    media: [{ kind: "video", duration: 125 }],
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
