"use client";

import { type ChangeEvent, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Braces,
  ChevronRight,
  Clapperboard,
  Database,
  ExternalLink,
  Fish,
  Link2,
  MessageSquare,
  Search,
} from "lucide-react";
import { Card, Content, PageHeader, PageShell } from "./components/chrome";
import { encodeUrlData } from "./utils/url-data";
import { MockChatData } from "./chat/types";
import { MockEhData } from "./eh/types";
import { MockImageSearchData } from "./imgsearch/types";
import { MockParserData } from "./parser/types";
import {
  parseParserDebugPayload,
  parserPreviewStorageKey,
} from "./parser/preview-storage";

type PageEntry = {
  href: string;
  title: string;
  description: string;
  injectKey: string;
  icon: ReactNode;
  /** Solid accent chip classes. */
  accent: string;
  /** Soft tint classes for the route chip. */
  chipSoft: string;
  mockSummary: string;
  mockPreview: unknown;
};

const PAGES: PageEntry[] = [
  {
    href: "/chat",
    title: "Chat Viewer",
    description:
      "多模态对话截图页。支持文本 / 图片 / 文件消息，供 /llm 等结果回传。",
    injectKey: "__CHAT_DATA__",
    icon: <MessageSquare size={20} />,
    accent: "bg-indigo-600 shadow-indigo-600/25",
    chipSoft: "bg-indigo-50 text-indigo-700",
    mockSummary: `${MockChatData.messages.length} 条消息 · title: ${MockChatData.title ?? "(无)"}`,
    mockPreview: MockChatData,
  },
  {
    href: "/eh",
    title: "EH 搜索结果",
    description:
      "E-Hentai 搜索结果卡片页（封面、标签、二维码），供 /eh 截图回传。",
    injectKey: "__EH_DATA__",
    icon: <BookOpen size={20} />,
    accent: "bg-rose-600 shadow-rose-600/25",
    chipSoft: "bg-rose-50 text-rose-700",
    mockSummary: `query: 「${MockEhData.query}」· ${MockEhData.results.length} 条结果`,
    mockPreview: MockEhData,
  },
  {
    href: "/imgsearch",
    title: "以图搜图结果",
    description:
      "SauceNAO 与 Soutubot 的反向图片搜索结果页，供 /imgsearch 截图回传。",
    injectKey: "__IMGSEARCH_DATA__",
    icon: <Search size={20} />,
    accent: "bg-teal-600 shadow-teal-600/25",
    chipSoft: "bg-teal-50 text-teal-700",
    mockSummary: `${MockImageSearchData.results.length} 条匹配结果`,
    mockPreview: MockImageSearchData,
  },
  {
    href: "/parser",
    title: "链接解析卡片",
    description:
      "多平台链接解析截图页，展示来源、作者、正文与媒体内容。",
    injectKey: "__PARSER_DATA__",
    icon: <Clapperboard size={20} />,
    accent: "bg-sky-600 shadow-sky-600/25",
    chipSoft: "bg-sky-50 text-sky-700",
    mockSummary: `${MockParserData.result.platform.displayName} · ${MockParserData.result.contentType ?? "动态"}`,
    mockPreview: MockParserData,
  },
];

const GUIDE: { icon: ReactNode; lead: string; body: ReactNode }[] = [
  {
    icon: <Braces size={13} />,
    lead: "Playwright 注入",
    body: (
      <>
        导航前写入{" "}
        <code className="rounded bg-zinc-100 px-1 py-px font-mono text-[11px] text-zinc-700">
          window.__CHAT_DATA__
        </code>{" "}
        等全局变量，键名见各卡片 inject 标注
      </>
    ),
  },
  {
    icon: <Link2 size={13} />,
    lead: "URL 参数",
    body: (
      <>
        各页接受{" "}
        <code className="rounded bg-zinc-100 px-1 py-px font-mono text-[11px] text-zinc-700">
          ?data=&lt;base64(json)&gt;
        </code>
        ，仅适合本地短数据预览
      </>
    ),
  },
  {
    icon: <Database size={13} />,
    lead: "Mock 回退",
    body: "无注入或数据非法时自动使用内置 Mock 数据，并在页面顶部提示",
  },
];

export default function Home() {
  async function uploadParserPayload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const payload = await file.text();
      const parsed = parseParserDebugPayload(JSON.parse(payload));
      if (!parsed.data) {
        console.log("[parser preview] Debug payload was rejected", {
          file: file.name,
          error: parsed.error,
        });
        event.target.value = "";
        return;
      }
      const id = crypto.randomUUID();
      sessionStorage.setItem(parserPreviewStorageKey(id), payload);
      window.location.assign(`/parser?payload=${encodeURIComponent(id)}`);
    } catch (error) {
      console.log("[parser preview] Failed to upload JSON payload", error);
      event.target.value = "";
    }
  }

  return (
    <PageShell ready="ready">
      <PageHeader
        icon={<Fish size={20} />}
        accent="bg-zinc-900 shadow-zinc-900/25"
        title="nanofish 预览台"
        subtitle="截图界面索引 · 数据注入调试"
        action={
          <span className="hidden rounded-md bg-zinc-100 px-2 py-1 font-mono text-[11px] text-zinc-500 sm:inline-block">
            720 × auto
          </span>
        }
      />

      <Content className="space-y-4 py-5 pb-14">
        <Card className="space-y-2.5 p-4">
          {GUIDE.map((row) => (
            <div key={row.lead} className="flex items-start gap-2.5">
              <span className="mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-zinc-100 text-zinc-500">
                {row.icon}
              </span>
              <p className="text-[13px] leading-6 text-zinc-600">
                <span className="font-medium text-zinc-900">{row.lead}</span>
                <span className="text-zinc-400"> · </span>
                {row.body}
              </p>
            </div>
          ))}
        </Card>

        {PAGES.map((page) => (
          <PageCard
            key={page.href}
            page={page}
            onParserUpload={page.href === "/parser" ? uploadParserPayload : undefined}
          />
        ))}

        <p className="pt-2 text-center text-[11px] text-zinc-400">
          nanofish · screenshot renderer
        </p>
      </Content>
    </PageShell>
  );
}

function PageCard({
  page,
  onParserUpload,
}: {
  page: PageEntry;
  onParserUpload?: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  const mockQueryHref = `${page.href}?data=${encodeURIComponent(
    encodeUrlData(page.mockPreview),
  )}`;

  return (
    <Card className="transition-shadow duration-200 hover:shadow-pop">
      <div className="p-4 sm:p-5">
        <div className="flex items-start gap-3.5">
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${page.accent}`}
          >
            {page.icon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="text-[15px] font-semibold tracking-tight text-zinc-900">
                {page.title}
              </h2>
              <code
                className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${page.chipSoft}`}
              >
                {page.href}
              </code>
            </div>
            <p className="mt-1 text-[13px] leading-5 text-zinc-500">
              {page.description}
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-zinc-400">
              <span>inject</span>
              <code className="rounded bg-zinc-100 px-1 py-px font-mono text-zinc-600">
                {page.injectKey}
              </code>
              <span aria-hidden>·</span>
              <span className="min-w-0">{page.mockSummary}</span>
            </p>
          </div>
        </div>

        <details className="group mt-3.5 overflow-hidden rounded-xl border border-black/[0.06]">
          <summary className="flex cursor-pointer select-none items-center gap-1.5 bg-zinc-50 px-3 py-2 text-xs font-medium text-zinc-600 transition hover:text-zinc-900">
            <ChevronRight
              size={13}
              className="transition-transform group-open:rotate-90"
            />
            查看 Mock 参数
          </summary>
          <pre className="max-h-60 overflow-auto bg-zinc-950 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-zinc-300">
            {JSON.stringify(page.mockPreview, null, 2)}
          </pre>
        </details>

        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            href={page.href}
            className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg bg-zinc-900 px-3.5 text-[13px] font-medium text-white transition hover:bg-zinc-700 sm:flex-none"
          >
            打开界面
            <ArrowRight size={15} />
          </Link>
          <Link
            href={mockQueryHref}
            className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border border-black/[0.08] bg-white px-3.5 text-[13px] font-medium text-zinc-700 transition hover:bg-zinc-50 sm:flex-none"
          >
            带参数打开
            <Link2 size={14} />
          </Link>
          {onParserUpload ? (
            <label className="inline-flex h-9 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-black/[0.08] bg-white px-3.5 text-[13px] font-medium text-zinc-700 transition hover:bg-zinc-50 sm:flex-none">
              上传 JSON
              <input
                className="sr-only"
                type="file"
                accept="application/json,.json"
                onChange={onParserUpload}
              />
            </label>
          ) : null}
          <Link
            href={page.href}
            target="_blank"
            rel="noreferrer"
            aria-label="新标签打开"
            title="新标签打开"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-black/[0.08] bg-white text-zinc-500 transition hover:bg-zinc-50 hover:text-zinc-900"
          >
            <ExternalLink size={15} />
          </Link>
        </div>
      </div>
    </Card>
  );
}
