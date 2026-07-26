/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import {
  ExternalLink,
  ImageOff,
  Search,
  Sparkles,
  UserRound,
} from "lucide-react";
import {
  ImageSearchData,
  ImageSearchResult,
  MockImageSearchData,
  parseImageSearchData,
} from "./types";
import { parseUrlData } from "../utils/url-data";
import { useAssetReadiness } from "../utils/use-asset-readiness";
import { Card, Content, Notice, PageHeader, PageShell, QrRail } from "../components/chrome";

declare global {
  interface Window {
    __IMGSEARCH_DATA__?: ImageSearchData;
  }
}

function loadImageSearchData(): { data: ImageSearchData; error: string | null } {
  if (typeof window !== "undefined" && window.__IMGSEARCH_DATA__) {
    const data = parseImageSearchData(window.__IMGSEARCH_DATA__);
    return data
      ? { data, error: null }
      : { data: MockImageSearchData, error: "注入的搜图数据无效，已回退到默认 Mock 数据。" };
  }

  if (typeof window !== "undefined") {
    const dataParam = new URLSearchParams(window.location.search).get("data");
    if (dataParam) {
      const parsed = parseUrlData(dataParam, parseImageSearchData);
      return parsed.data
        ? { data: parsed.data, error: null }
        : { data: MockImageSearchData, error: "URL 参数无效，已回退到默认 Mock 数据。" };
    }
  }

  return { data: MockImageSearchData, error: null };
}

function similarityLabel(similarity: number | null): string {
  return similarity === null || !Number.isFinite(similarity)
    ? "--"
    : `${similarity.toFixed(2)}%`;
}

function similarityTone(similarity: number | null): {
  badge: string;
  bar: string;
} {
  if (similarity !== null && similarity >= 80) {
    return {
      badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
      bar: "bg-emerald-500",
    };
  }
  if (similarity !== null && similarity >= 60) {
    return {
      badge: "bg-amber-50 text-amber-700 ring-amber-600/15",
      bar: "bg-amber-500",
    };
  }
  return {
    badge: "bg-zinc-100 text-zinc-600 ring-black/[0.06]",
    bar: "bg-zinc-400",
  };
}

function displayUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.hostname}${url.pathname}`;
  } catch {
    return value;
  }
}

export default function ImageSearchPage() {
  const [data, setData] = useState<ImageSearchData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const { status, beginAssetTracking, completeAsset } = useAssetReadiness();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const loadedData = loadImageSearchData();
      setData(loadedData.data);
      setLoadError(loadedData.error);
      beginAssetTracking(
        Number(Boolean(loadedData.data.image)) +
          loadedData.data.results.filter((result) => Boolean(result.thumbnail)).length,
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, [beginAssetTracking]);

  if (!data) {
    return <div className="min-h-screen bg-paper" data-ready="false" />;
  }

  return (
    <PageShell ready={status}>
      <PageHeader
        icon={<Search size={18} />}
        accent="bg-teal-600 shadow-teal-600/25"
        title="以图搜图"
        subtitle={
          data.results.length
            ? `发现 ${data.results.length} 个匹配结果`
            : "未发现匹配结果"
        }
      />

      <Content className="space-y-4 py-5 pb-14">
        <Card className="flex items-center gap-4 p-4">
          <div className="flex h-28 w-[5.25rem] shrink-0 items-center justify-center overflow-hidden rounded-xl bg-zinc-900 p-1.5 sm:h-32 sm:w-24">
            {data.image && !imageFailed ? (
              <img
                src={data.image}
                alt="待搜索图片"
                className="h-full w-full rounded-lg object-contain"
                referrerPolicy="no-referrer"
                onLoad={completeAsset}
                onError={() => {
                  setImageFailed(true);
                  completeAsset();
                }}
              />
            ) : (
              <div className="flex flex-col items-center gap-1.5 text-zinc-500">
                <ImageOff size={22} />
                <span className="text-[10px]">原图不可预览</span>
              </div>
            )}
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-600">
              Search target
            </p>
            <h2 className="mt-0.5 text-[15px] font-semibold tracking-tight text-zinc-900">
              搜索目标
            </h2>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              已完成反向匹配，下方结果按相似度排序。
            </p>
          </div>
        </Card>

        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            匹配结果
          </h2>
          <span className="rounded-full bg-teal-50 px-2.5 py-0.5 text-[11px] font-medium text-teal-700 ring-1 ring-inset ring-teal-600/10">
            {data.results.length} 个候选
          </span>
        </div>

        {loadError ? <Notice>{loadError}</Notice> : null}

        {data.results.length ? (
          data.results.map((result, index) => (
            <ResultCard
              key={`${result.url}-${index}`}
              index={index}
              result={result}
              onImageLoad={completeAsset}
            />
          ))
        ) : (
          <Card className="flex flex-col items-center gap-2.5 p-10 text-center">
            <Sparkles size={26} className="text-zinc-300" />
            <p className="text-sm text-zinc-500">没有找到相似图片</p>
          </Card>
        )}

        {data.errors.length ? (
          <Notice>
            <p className="font-medium">部分搜索来源不可用</p>
            <p className="mt-0.5 text-xs text-amber-800">{data.errors.join("；")}</p>
          </Notice>
        ) : null}
      </Content>
    </PageShell>
  );
}

function ResultCard({
  index,
  result,
  onImageLoad,
}: {
  index: number;
  result: ImageSearchResult;
  onImageLoad: () => void;
}) {
  const title = result.title || "未提供标题";
  const [thumbnailFailed, setThumbnailFailed] = useState(!result.thumbnail);
  const tone = similarityTone(result.similarity);

  return (
    <Card>
      <div className="flex gap-3.5 p-3.5 sm:gap-4 sm:p-4">
        <div className="relative aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-lg bg-zinc-100 ring-1 ring-inset ring-black/[0.04] sm:w-[120px]">
          {!thumbnailFailed ? (
            <img
              src={result.thumbnail}
              alt={`${title} 的匹配图片`}
              className="h-full w-full object-cover"
              referrerPolicy="no-referrer"
              onLoad={onImageLoad}
              onError={() => {
                setThumbnailFailed(true);
                onImageLoad();
              }}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-zinc-300">
              <ImageOff size={22} />
            </div>
          )}
          <span className="absolute left-1.5 top-1.5 rounded-md bg-zinc-950/90 px-1.5 py-0.5 text-[10px] font-bold text-white">
            #{index + 1}
          </span>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold leading-4 text-white">
              {result.source || "Unknown"}
            </span>
            <span
              className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold leading-4 ring-1 ring-inset ${tone.badge}`}
            >
              {similarityLabel(result.similarity)}
            </span>
            {result.similarity !== null ? (
              <span className="hidden h-1 w-20 overflow-hidden rounded-full bg-zinc-100 min-[420px]:block">
                <span
                  className={`block h-full rounded-full ${tone.bar}`}
                  style={{ width: `${Math.min(100, Math.max(0, result.similarity))}%` }}
                />
              </span>
            ) : null}
          </div>

          <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug break-words text-zinc-900">
            {title}
          </h3>

          {result.author ? (
            <p className="-mt-1 inline-flex items-center gap-1 text-xs text-zinc-500">
              <UserRound size={12} className="text-zinc-400" />
              <span className="truncate">{result.author}</span>
            </p>
          ) : null}

          {result.url ? (
            <div className="mt-auto flex items-center rounded-lg bg-zinc-50 px-2.5 py-1.5 ring-1 ring-inset ring-black/[0.04]">
              <a
                href={result.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${title}（在新标签页打开）`}
                title={result.url}
                className="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-teal-700 hover:text-teal-900"
              >
                <ExternalLink size={12} className="shrink-0" aria-hidden />
                <span className="truncate">{displayUrl(result.url)}</span>
              </a>
            </div>
          ) : null}
        </div>

        {result.url ? <QrRail url={result.url} /> : null}
      </div>
    </Card>
  );
}
