/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import { BookOpen, ImageOff, Star, User, FileText } from "lucide-react";
import { Card } from "@heroui/react";
import { QRCodeSVG } from "qrcode.react";
import { EhGalleryItem, EhResultData, MockEhData } from "./types";

declare global {
  interface Window {
    __EH_DATA__?: EhResultData;
  }
}

function loadEhData(): EhResultData {
  if (typeof window !== "undefined" && window.__EH_DATA__) {
    return window.__EH_DATA__;
  }

  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const dataParam = params.get("data");
    if (dataParam) {
      try {
        const decoded = atob(decodeURIComponent(dataParam));
        // utf-8 safe: reverse of btoa(unescape(encodeURIComponent(json)))
        const json = decodeURIComponent(escape(decoded));
        return JSON.parse(json) as EhResultData;
      } catch (e) {
        console.error("Failed to parse URL data", e);
      }
    }
  }

  return MockEhData;
}

function formatPosted(posted: string): string {
  const n = Number(posted);
  if (!Number.isFinite(n) || n <= 0) return posted || "-";
  // EH API uses unix seconds
  const ms = n < 1e12 ? n * 1000 : n;
  try {
    return new Date(ms).toISOString().slice(0, 10);
  } catch {
    return posted;
  }
}

/** EH tag namespace → chip colors (aligned with site convention-ish) */
const TAG_NS_STYLES: Record<string, string> = {
  language: "bg-sky-100 text-sky-800 ring-sky-200",
  parody: "bg-lime-100 text-lime-900 ring-lime-200",
  character: "bg-amber-100 text-amber-900 ring-amber-200",
  group: "bg-teal-100 text-teal-900 ring-teal-200",
  artist: "bg-violet-100 text-violet-900 ring-violet-200",
  cosplayer: "bg-fuchsia-100 text-fuchsia-900 ring-fuchsia-200",
  male: "bg-blue-100 text-blue-900 ring-blue-200",
  female: "bg-rose-100 text-rose-900 ring-rose-200",
  mixed: "bg-indigo-100 text-indigo-900 ring-indigo-200",
  other: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  reclass: "bg-orange-100 text-orange-900 ring-orange-200",
  location: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  temp: "bg-stone-100 text-stone-700 ring-stone-200",
};

const DEFAULT_TAG_STYLE = "bg-zinc-100 text-zinc-700 ring-zinc-200";

function parseTag(raw: string): { ns: string; label: string } {
  // backend: "namespace: 译文" or bare tag
  const idx = raw.indexOf(":");
  if (idx <= 0) {
    return { ns: "", label: raw };
  }
  return {
    ns: raw.slice(0, idx).trim().toLowerCase(),
    label: raw.slice(idx + 1).trim() || raw,
  };
}

function TagChip({ tag }: { tag: string }) {
  const { ns, label } = parseTag(tag);
  const style = (ns && TAG_NS_STYLES[ns]) || DEFAULT_TAG_STYLE;
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ring-1 ring-inset ${style}`}
      title={ns ? `${ns}: ${label}` : label}
    >
      {ns ? (
        <span className="shrink-0 opacity-60 font-medium uppercase tracking-wide text-[9px]">
          {ns.slice(0, 3)}
        </span>
      ) : null}
      <span className="truncate">{label}</span>
    </span>
  );
}

/** Max tags shown before fold (screenshots stay compact by default). */
const TAG_FOLD_LIMIT = 12;

function TagList({ tags }: { tags: string[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!tags.length) return null;

  const needsFold = tags.length > TAG_FOLD_LIMIT;
  const visible =
    expanded || !needsFold ? tags : tags.slice(0, TAG_FOLD_LIMIT);
  const hiddenCount = tags.length - visible.length;

  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {visible.map((tag) => (
        <TagChip key={tag} tag={tag} />
      ))}
      {needsFold && !expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="rounded-full bg-zinc-900 px-2.5 py-0.5 text-[11px] font-medium text-white ring-1 ring-inset ring-zinc-800"
          title={`展开剩余 ${hiddenCount} 个标签`}
        >
          +{hiddenCount}
        </button>
      ) : null}
      {needsFold && expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="rounded-full bg-zinc-200 px-2.5 py-0.5 text-[11px] font-medium text-zinc-700 ring-1 ring-inset ring-zinc-300"
        >
          收起
        </button>
      ) : null}
    </div>
  );
}

export default function EhResultsPage() {
  const [data, setData] = useState<EhResultData | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setData(loadEhData());
    setReady(true);
  }, []);

  if (!data) {
    return <div className="min-h-screen bg-zinc-50" data-ready="false" />;
  }

  return (
    <div
      className="min-h-screen bg-zinc-50 text-zinc-900"
      data-ready={ready ? "true" : "false"}
    >
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-600 text-white">
            <BookOpen size={20} />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight">
              EH 搜索结果
            </h1>
            <p className="truncate text-sm text-zinc-500">
              「{data.query}」· {data.results.length} 条
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-4 p-6 pb-16">
        {data.results.length === 0 ? (
          <p className="text-center text-zinc-500">无结果</p>
        ) : (
          data.results.map((item, idx) => (
            <ResultCard key={`${item.url}-${idx}`} index={idx} item={item} />
          ))
        )}
      </main>
    </div>
  );
}

function ResultCard({ index, item }: { index: number; item: EhGalleryItem }) {
  const [imgFailed, setImgFailed] = useState(!item.thumb);

  return (
    <Card className="overflow-hidden border border-zinc-200 bg-white shadow-sm">
      <div className="flex gap-4 p-4">
        <div className="flex w-28 shrink-0 flex-col items-center gap-2">
          <div className="h-36 w-28 overflow-hidden rounded-lg bg-zinc-100">
            {!imgFailed && item.thumb ? (
              <img
                src={item.thumb}
                alt=""
                className="h-full w-full object-cover"
                onError={() => setImgFailed(true)}
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-zinc-400">
                <ImageOff size={22} />
                <span className="text-[10px]">no thumb</span>
              </div>
            )}
          </div>
          {item.url ? (
            <div className="flex w-full flex-col items-center gap-1">
              <div className="rounded-md border border-zinc-200 bg-white p-1">
                <QRCodeSVG
                  value={item.url}
                  size={104}
                  level="M"
                  marginSize={1}
                  bgColor="#ffffff"
                  fgColor="#18181b"
                />
              </div>
              <span className="text-[10px] text-zinc-400">扫码打开</span>
            </div>
          ) : null}
        </div>

        <div className="flex min-w-0 flex-1 flex-col space-y-2">
          <div className="flex flex-wrap items-start gap-2">
            <span className="rounded-md bg-zinc-900 px-2 py-0.5 text-[11px] font-medium text-white">
              #{index}
            </span>
            <span className="rounded-md bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-800">
              {item.category || "Unknown"}
            </span>
          </div>

          <h2 className="text-base font-semibold leading-snug break-words">
            {item.title}
          </h2>
          {item.title_jpn ? (
            <p className="text-sm text-zinc-500 break-words">{item.title_jpn}</p>
          ) : null}

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600">
            <span className="inline-flex items-center gap-1">
              <User size={12} />
              {item.uploader || "-"}
            </span>
            <span className="inline-flex items-center gap-1">
              <FileText size={12} />
              {item.filecount || "?"} 页
            </span>
            <span className="inline-flex items-center gap-1">
              <Star size={12} />
              {item.rating || "-"}
            </span>
            <span>{formatPosted(item.posted)}</span>
          </div>

          {item.tags?.length > 0 ? <TagList tags={item.tags} /> : null}

          {item.url ? (
            <div className="mt-auto rounded-md border border-zinc-100 bg-zinc-50 px-2.5 py-1.5">
              <p className="font-mono text-[11px] break-all text-zinc-500">
                {item.url}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
