"use client";

import { useEffect, useState, type ComponentType } from "react";
import { Acfun, appearance as acfunAppearance, countAssets as countAcfunAssets } from "./platforms/acfun";
import { Bilibili, appearance as bilibiliAppearance, countAssets as countBilibiliAssets } from "./platforms/bilibili";
import { Douyin, appearance as douyinAppearance, countAssets as countDouyinAssets } from "./platforms/douyin";
import { GenericCard, assetCount, genericAppearance, type PlatformAppearance } from "./platforms/generic";
import { Kuaishou, appearance as kuaishouAppearance, countAssets as countKuaishouAssets } from "./platforms/kuaishou";
import { Nga, appearance as ngaAppearance, countAssets as countNgaAssets } from "./platforms/nga";
import { NeteaseMusic, appearance as neteaseMusicAppearance, countAssets as countNeteaseMusicAssets } from "./platforms/netease-music";
import { QQMusic, appearance as qqMusicAppearance, countAssets as countQQMusicAssets } from "./platforms/qq-music";
import { Spotify, appearance as spotifyAppearance, countAssets as countSpotifyAssets } from "./platforms/spotify";
import { Tiktok, appearance as tiktokAppearance, countAssets as countTiktokAssets } from "./platforms/tiktok";
import { Twitter, appearance as twitterAppearance, countAssets as countTwitterAssets } from "./platforms/twitter";
import { Weibo, appearance as weiboAppearance, countAssets as countWeiboAssets } from "./platforms/weibo";
import { Xiaohongshu, appearance as xiaohongshuAppearance, countAssets as countXiaohongshuAssets } from "./platforms/xiaohongshu";
import { Youtube, appearance as youtubeAppearance, countAssets as countYoutubeAssets } from "./platforms/youtube";
import { YoutubeMusic, appearance as youtubeMusicAppearance, countAssets as countYoutubeMusicAssets } from "./platforms/youtube-music";
import {
  MockParserData,
  parseParserScreenshotData,
  type ParserResult,
  type ParserScreenshotData,
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

type CardProps = {
  result: ParserResult;
  maxGridImages: number;
  onAsset: () => void;
};

type PlatformRenderer = {
  appearance: PlatformAppearance;
  Card: ComponentType<CardProps>;
  countAssets: (result: ParserResult, maxGridImages: number) => number;
};

const GENERIC_RENDERER: PlatformRenderer = {
  appearance: genericAppearance,
  Card: ({ result, maxGridImages, onAsset }) => <GenericCard result={result} appearance={genericAppearance} maxGridImages={maxGridImages} onAsset={onAsset} />,
  countAssets: (result, maxGridImages) => assetCount(result, maxGridImages, genericAppearance),
};

const PLATFORM_RENDERERS: Record<string, PlatformRenderer> = {
  acfun: { appearance: acfunAppearance, Card: Acfun, countAssets: countAcfunAssets },
  bilibili: { appearance: bilibiliAppearance, Card: Bilibili, countAssets: countBilibiliAssets },
  douyin: { appearance: douyinAppearance, Card: Douyin, countAssets: countDouyinAssets },
  kuaishou: { appearance: kuaishouAppearance, Card: Kuaishou, countAssets: countKuaishouAssets },
  nga: { appearance: ngaAppearance, Card: Nga, countAssets: countNgaAssets },
  netease_music: { appearance: neteaseMusicAppearance, Card: NeteaseMusic, countAssets: countNeteaseMusicAssets },
  qq_music: { appearance: qqMusicAppearance, Card: QQMusic, countAssets: countQQMusicAssets },
  spotify: { appearance: spotifyAppearance, Card: Spotify, countAssets: countSpotifyAssets },
  tiktok: { appearance: tiktokAppearance, Card: Tiktok, countAssets: countTiktokAssets },
  twitter: { appearance: twitterAppearance, Card: Twitter, countAssets: countTwitterAssets },
  weibo: { appearance: weiboAppearance, Card: Weibo, countAssets: countWeiboAssets },
  xiaohongshu: { appearance: xiaohongshuAppearance, Card: Xiaohongshu, countAssets: countXiaohongshuAssets },
  youtube: { appearance: youtubeAppearance, Card: Youtube, countAssets: countYoutubeAssets },
  youtube_music: { appearance: youtubeMusicAppearance, Card: YoutubeMusic, countAssets: countYoutubeMusicAssets },
};

function rendererFor(result: ParserResult): PlatformRenderer {
  return PLATFORM_RENDERERS[result.platform.name] ?? GENERIC_RENDERER;
}

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
        console.log("[parser preview] Uploaded debug payload was rejected", { payloadId, error: parsed.error });
        return { data: MockParserData, error: `上传的调试文件无效：${parsed.error}` };
      } catch (error) {
        console.log("[parser preview] Uploaded payload could not be parsed", error);
        return { data: MockParserData, error: "上传的 JSON 无法解析，已回退到默认 Mock 数据。" };
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

export default function ParserPage() {
  const [data, setData] = useState<ParserScreenshotData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { status, beginAssetTracking, completeAsset } = useAssetReadiness();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const loadedData = loadParserData();
      const maxGridImages = loadedData.data.maxGridImages ?? 9;
      setData(loadedData.data);
      setError(loadedData.error);
      beginAssetTracking(rendererFor(loadedData.data.result).countAssets(loadedData.data.result, maxGridImages));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [beginAssetTracking]);

  if (!data) return <div className="min-h-screen bg-paper" data-ready="false" />;

  const renderer = rendererFor(data.result);
  const Card = renderer.Card;
  return (
    <PageShell ready={status} style={{ background: renderer.appearance.background }} className="text-slate-900">
      <Content flush className="py-0">
        <div data-parser-frame className="space-y-4 p-4 sm:p-5" style={{ background: renderer.appearance.background }}>
          {error ? <Notice>{error}</Notice> : null}
          <Card result={data.result} maxGridImages={data.maxGridImages ?? 9} onAsset={completeAsset} />
        </div>
      </Content>
    </PageShell>
  );
}
