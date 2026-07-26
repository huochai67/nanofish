/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useId, useState } from "react";
import {
  BookOpen,
  CalendarDays,
  ExternalLink,
  FileText,
  FolderOpen,
  ImageOff,
  Star,
  User,
} from "lucide-react";
import {
  loadTagDict,
  parseRawTag,
  translateTag,
  type TagDict,
} from "./ehtag";
import { EhGalleryItem, EhResultData, MockEhData, parseEhResultData } from "./types";
import { parseUrlData } from "../utils/url-data";
import { useAssetReadiness } from "../utils/use-asset-readiness";
import { Card, Content, Notice, PageHeader, PageShell, QrRail } from "../components/chrome";

declare global {
  interface Window {
    __EH_DATA__?: EhResultData;
  }
}

function loadEhData(): { data: EhResultData; error: string | null } {
  if (typeof window !== "undefined" && window.__EH_DATA__) {
    const data = parseEhResultData(window.__EH_DATA__);
    return data
      ? { data, error: null }
      : { data: MockEhData, error: "注入的搜索数据无效，已回退到默认 Mock 数据。" };
  }

  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const dataParam = params.get("data");
    if (dataParam) {
      const parsed = parseUrlData(dataParam, parseEhResultData);
      return parsed.data
        ? { data: parsed.data, error: null }
        : { data: MockEhData, error: "URL 参数无效，已回退到默认 Mock 数据。" };
    }
  }

  return { data: MockEhData, error: null };
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
  language: "bg-sky-50 text-sky-700 ring-sky-600/15",
  parody: "bg-lime-50 text-lime-800 ring-lime-600/15",
  character: "bg-amber-50 text-amber-800 ring-amber-600/15",
  group: "bg-teal-50 text-teal-800 ring-teal-600/15",
  artist: "bg-violet-50 text-violet-800 ring-violet-600/15",
  cosplayer: "bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-600/15",
  male: "bg-blue-50 text-blue-800 ring-blue-600/15",
  female: "bg-rose-50 text-rose-800 ring-rose-600/15",
  mixed: "bg-indigo-50 text-indigo-800 ring-indigo-600/15",
  other: "bg-zinc-100 text-zinc-600 ring-black/[0.06]",
  reclass: "bg-orange-50 text-orange-800 ring-orange-600/15",
  location: "bg-emerald-50 text-emerald-800 ring-emerald-600/15",
  temp: "bg-stone-100 text-stone-600 ring-black/[0.06]",
};

const DEFAULT_TAG_STYLE = "bg-zinc-100 text-zinc-600 ring-black/[0.06]";

function TagChip({ raw, dict }: { raw: string; dict: TagDict }) {
  const { ns } = parseRawTag(raw);
  const label = translateTag(raw, dict);
  const style = (ns && TAG_NS_STYLES[ns]) || DEFAULT_TAG_STYLE;
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] leading-4 ring-1 ring-inset ${style}`}
      title={ns ? `${ns}: ${label}` : label}
    >
      {ns ? (
        <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wide opacity-55">
          {ns.slice(0, 3)}
        </span>
      ) : null}
      <span className="truncate">{label}</span>
    </span>
  );
}

/** Max tags shown before fold (screenshots stay compact by default). */
const TAG_FOLD_LIMIT = 12;

function TagList({ tags, dict }: { tags: string[]; dict: TagDict }) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();

  if (!tags.length) return null;

  const needsFold = tags.length > TAG_FOLD_LIMIT;
  const visible =
    expanded || !needsFold ? tags : tags.slice(0, TAG_FOLD_LIMIT);
  const hiddenCount = tags.length - visible.length;

  return (
    <div id={contentId} className="flex flex-wrap gap-1.5">
      {visible.map((tag) => (
        <TagChip key={tag} raw={tag} dict={dict} />
      ))}
      {needsFold && !expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          aria-expanded="false"
          aria-controls={contentId}
          className="rounded-md bg-zinc-900 px-2 py-0.5 text-[11px] font-medium leading-4 text-white"
          title={`展开剩余 ${hiddenCount} 个标签`}
        >
          +{hiddenCount}
        </button>
      ) : null}
      {needsFold && expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          aria-expanded="true"
          aria-controls={contentId}
          className="rounded-md bg-zinc-100 px-2 py-0.5 text-[11px] font-medium leading-4 text-zinc-600 ring-1 ring-inset ring-black/[0.06]"
        >
          收起
        </button>
      ) : null}
    </div>
  );
}

export default function EhResultsPage() {
  const [data, setData] = useState<EhResultData | null>(null);
  const [dict, setDict] = useState<TagDict>({});
  const [error, setError] = useState<string | null>(null);
  const { status, beginAssetTracking, completeAsset } = useAssetReadiness();

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      const loadedData = loadEhData();
      if (cancelled) return;
      setData(loadedData.data);
      setError(loadedData.error);
      beginAssetTracking(
        loadedData.data.results.filter((item) => Boolean(item.thumb)).length,
      );
    });
    void loadTagDict(controller.signal).then((tagDict) => {
      if (!cancelled) setDict(tagDict);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [beginAssetTracking]);

  if (!data) {
    return <div className="min-h-screen bg-paper" data-ready="false" />;
  }

  return (
    <PageShell ready={status}>
      <PageHeader
        icon={<BookOpen size={18} />}
        accent="bg-rose-600 shadow-rose-600/25"
        title="EH 搜索结果"
        subtitle={`「${data.query}」· ${data.results.length} 条结果`}
      />

      <Content className="space-y-4 py-5 pb-14">
        {error ? <Notice>{error}</Notice> : null}

        {data.results.length === 0 ? (
          <Card className="flex flex-col items-center gap-2.5 p-10 text-center">
            <FolderOpen size={26} className="text-zinc-300" />
            <p className="text-sm text-zinc-500">没有找到匹配的画廊</p>
          </Card>
        ) : (
          data.results.map((item, idx) => (
            <ResultCard
              key={`${item.url}-${idx}`}
              index={idx}
              item={item}
              dict={dict}
              onAsset={completeAsset}
            />
          ))
        )}
      </Content>
    </PageShell>
  );
}

function ResultCard({
  index,
  item,
  dict,
  onAsset,
}: {
  index: number;
  item: EhGalleryItem;
  dict: TagDict;
  onAsset: () => void;
}) {
  const [imgFailed, setImgFailed] = useState(!item.thumb);

  return (
    <Card>
      <div className="flex gap-3.5 p-3.5 sm:gap-4 sm:p-4">
        <div className="aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-lg bg-zinc-100 ring-1 ring-inset ring-black/[0.04] sm:w-[128px]">
          {!imgFailed && item.thumb ? (
            <img
              src={item.thumb}
              alt={`${item.title} 的封面`}
              className="h-full w-full object-cover"
              referrerPolicy="no-referrer"
              onLoad={onAsset}
              onError={() => {
                setImgFailed(true);
                onAsset();
              }}
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-zinc-300">
              <ImageOff size={22} />
              <span className="text-[10px] text-zinc-400">no thumb</span>
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold leading-4 text-white">
              #{index + 1}
            </span>
            <span className="rounded-md bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold leading-4 text-rose-700 ring-1 ring-inset ring-rose-600/15">
              {item.category || "Unknown"}
            </span>
          </div>

          <h2 className="text-[15px] font-semibold leading-snug break-words text-zinc-900">
            {item.title}
          </h2>
          {item.title_jpn ? (
            <p className="-mt-1 text-xs leading-5 break-words text-zinc-500">
              {item.title_jpn}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-xs text-zinc-500">
            <span className="inline-flex items-center gap-1">
              <User size={12} className="text-zinc-400" />
              {item.uploader || "-"}
            </span>
            <span className="inline-flex items-center gap-1">
              <FileText size={12} className="text-zinc-400" />
              {item.filecount || "?"} 页
            </span>
            <span className="inline-flex items-center gap-1">
              <Star size={12} className="fill-amber-400 text-amber-400" />
              {item.rating || "-"}
            </span>
            <span className="inline-flex items-center gap-1">
              <CalendarDays size={12} className="text-zinc-400" />
              {formatPosted(item.posted)}
            </span>
          </div>

          {item.tags?.length > 0 ? (
            <TagList tags={item.tags} dict={dict} />
          ) : null}

          {item.url ? (
            <div className="mt-auto flex items-center rounded-lg bg-zinc-50 px-2.5 py-1.5 ring-1 ring-inset ring-black/[0.04]">
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${item.title}（在新标签页打开）`}
                className="inline-flex min-w-0 items-center gap-1.5 font-mono text-[11px] text-zinc-500 hover:text-zinc-900"
              >
                <span className="truncate">{item.url}</span>
                <ExternalLink size={11} className="shrink-0" aria-hidden />
              </a>
            </div>
          ) : null}
        </div>

        {item.url ? <QrRail url={item.url} /> : null}
      </div>
    </Card>
  );
}
