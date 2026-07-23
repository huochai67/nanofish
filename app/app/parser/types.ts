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
