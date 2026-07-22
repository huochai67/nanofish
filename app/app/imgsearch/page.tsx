/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useRef, useState } from "react";
import { Card } from "@heroui/react";
import { QRCodeSVG } from "qrcode.react";
import {
  ExternalLink,
  ImageOff,
  Search,
  Sparkles,
  UserRound,
} from "lucide-react";
import { ImageSearchData, ImageSearchResult, MockImageSearchData } from "./types";

declare global {
  interface Window {
    __IMGSEARCH_DATA__?: ImageSearchData;
  }
}

function loadImageSearchData(): ImageSearchData {
  if (typeof window !== "undefined" && window.__IMGSEARCH_DATA__) {
    return window.__IMGSEARCH_DATA__;
  }

  if (typeof window !== "undefined") {
    const dataParam = new URLSearchParams(window.location.search).get("data");
    if (dataParam) {
      try {
        const binary = atob(decodeURIComponent(dataParam));
        return JSON.parse(decodeURIComponent(escape(binary))) as ImageSearchData;
      } catch (error) {
        console.error("Failed to parse image search URL data", error);
      }
    }
  }

  return MockImageSearchData;
}

function similarityLabel(similarity: number | null): string {
  return similarity === null || !Number.isFinite(similarity)
    ? "--"
    : `${similarity.toFixed(2)}%`;
}

function similarityColor(similarity: number | null): string {
  if (similarity === null) return "bg-slate-100 text-slate-600";
  if (similarity >= 80) return "bg-emerald-100 text-emerald-800";
  if (similarity >= 60) return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
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
  const [ready, setReady] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const pendingImageCount = useRef(0);
  const readyTimeout = useRef<number | null>(null);

  const completeImageLoad = () => {
    if (pendingImageCount.current <= 0) return;
    pendingImageCount.current -= 1;
    if (pendingImageCount.current === 0) {
      if (readyTimeout.current !== null) {
        window.clearTimeout(readyTimeout.current);
      }
      setReady(true);
    }
  };

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      const imageSearchData = loadImageSearchData();
      const imageCount =
        Number(Boolean(imageSearchData.image)) +
        imageSearchData.results.filter((result) => Boolean(result.thumbnail)).length;
      pendingImageCount.current = imageCount;
      setData(imageSearchData);

      if (imageCount === 0) {
        setReady(true);
        return;
      }

      // Do not hold the bot response forever when a remote image stalls.
      readyTimeout.current = window.setTimeout(() => {
        pendingImageCount.current = 0;
        setReady(true);
      }, 10_000);
    });
    return () => {
      cancelled = true;
      if (readyTimeout.current !== null) {
        window.clearTimeout(readyTimeout.current);
      }
    };
  }, []);

  if (!data) {
    return <div className="min-h-screen bg-slate-50" data-ready="false" />;
  }

  return (
    <div
      className="min-h-screen bg-slate-50 text-slate-900"
      data-ready={ready ? "true" : "false"}
    >
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-700 text-white shadow-sm shadow-cyan-700/25">
            <Search size={20} />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">以图搜图</h1>
            <p className="text-sm text-slate-500">
              {data.results.length ? `发现 ${data.results.length} 个匹配结果` : "未发现匹配结果"}
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-6 pb-12">
        <div className="grid items-start gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="overflow-hidden rounded-2xl bg-slate-900 text-white shadow-lg shadow-slate-900/10 lg:sticky lg:top-6">
            <div className="border-b border-white/10 px-4 py-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">
                Search target
              </p>
              <h2 className="mt-0.5 text-base font-semibold">搜索目标</h2>
            </div>
            <div className="flex aspect-[3/4] items-center justify-center bg-slate-800 p-3">
              {data.image && !imageFailed ? (
                <img
                  src={data.image}
                  alt="待搜索图片"
                  className="h-full w-full rounded-lg object-contain"
                  onLoad={completeImageLoad}
                  onError={() => {
                    setImageFailed(true);
                    completeImageLoad();
                  }}
                />
              ) : (
                <div className="flex flex-col items-center gap-2 text-slate-400">
                  <ImageOff size={26} />
                  <span className="text-xs">原图不可预览</span>
                </div>
              )}
            </div>
            <div className="px-4 py-3 text-xs leading-5 text-slate-300">
              已完成反向匹配，右侧结果按相似度排序。
            </div>
          </aside>

          <section className="min-w-0 space-y-3">
            <div className="flex items-end justify-between gap-4 border-b border-slate-200 pb-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-700">
                  Matches
                </p>
                <h2 className="mt-0.5 text-xl font-semibold tracking-tight">搜索结果</h2>
              </div>
              <p className="rounded-full bg-cyan-50 px-3 py-1 text-sm font-medium text-cyan-800">
                {data.results.length} 个候选匹配
              </p>
            </div>

            {data.results.length ? (
              data.results.map((result, index) => (
                <ResultCard
                  key={`${result.url}-${index}`}
                  index={index}
                  result={result}
                  onImageLoad={completeImageLoad}
                />
              ))
            ) : (
              <Card className="border border-slate-200 bg-white p-8 text-center shadow-sm">
                <Sparkles className="mx-auto text-slate-300" size={28} />
                <p className="mt-3 text-sm text-slate-500">没有找到相似图片</p>
              </Card>
            )}

            {data.errors.length ? (
              <section className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <p className="font-medium">部分搜索来源不可用</p>
                <p className="mt-1 text-xs text-amber-800">{data.errors.join("；")}</p>
              </section>
            ) : null}
          </section>
        </div>
      </main>
    </div>
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

  return (
    <Card className="border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      <div className="flex gap-3 p-3 sm:gap-4 sm:p-4">
        <div className="relative flex h-32 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 sm:h-36 sm:w-28">
          {!thumbnailFailed ? (
            <img
              src={result.thumbnail}
              alt="匹配图片"
              className="h-full w-full object-cover"
              onLoad={onImageLoad}
              onError={() => {
                setThumbnailFailed(true);
                onImageLoad();
              }}
            />
          ) : (
            <ImageOff className="text-slate-300" size={22} />
          )}
          <span className="absolute left-1.5 top-1.5 rounded-md bg-slate-950/90 px-1.5 py-0.5 text-[10px] font-bold text-white">
            #{index + 1}
          </span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col py-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-500">
              {result.source || "Unknown"}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${similarityColor(result.similarity)}`}>
              {similarityLabel(result.similarity)}
            </span>
          </div>
          <h3 className="mt-2 line-clamp-2 break-words text-base font-semibold leading-snug text-slate-900">
            {title}
          </h3>
          {result.author ? (
            <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-slate-500">
              <UserRound size={14} />
              {result.author}
            </p>
          ) : null}
          {result.url ? (
            <div className="mt-auto flex items-end justify-between gap-3 pt-3">
              <a
                href={result.url}
                target="_blank"
                rel="noreferrer"
                className="group flex min-w-0 items-center gap-1.5 text-sm font-medium text-cyan-700"
                title={result.url}
              >
                <ExternalLink className="shrink-0" size={14} />
                <span className="truncate group-hover:underline">{displayUrl(result.url)}</span>
              </a>
              <div className="flex shrink-0 items-center gap-2 text-right text-[10px] font-medium text-slate-400">
                <span className="hidden sm:inline">扫码打开</span>
                <div className="rounded-md border border-slate-200 bg-white p-1">
                  <QRCodeSVG
                    value={result.url}
                    size={96}
                    level="L"
                    marginSize={2}
                    bgColor="#ffffff"
                    fgColor="#0f172a"
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
