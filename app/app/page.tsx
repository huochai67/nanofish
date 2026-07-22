"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  MessageSquare,
  BookOpen,
  ExternalLink,
  Code2,
  ArrowRight,
  FlaskConical,
  Search,
} from "lucide-react";
import { Card } from "@heroui/react";
import { MockChatData } from "./chat/types";
import { MockEhData } from "./eh/types";
import { MockImageSearchData } from "./imgsearch/types";

type PageEntry = {
  href: string;
  title: string;
  description: string;
  injectKey: string;
  icon: ReactNode;
  accent: string;
  iconBg: string;
  mockSummary: string;
  mockPreview: unknown;
  supportsDataQuery?: boolean;
};

const PAGES: PageEntry[] = [
  {
    href: "/chat",
    title: "Chat Viewer",
    description:
      "多模态对话截图页。支持文本 / 图片 / 文件消息，供 /llm 等结果回传。",
    injectKey: "__CHAT_DATA__",
    icon: <MessageSquare size={22} />,
    accent: "from-indigo-500 to-violet-600",
    iconBg: "bg-indigo-600",
    mockSummary: `${MockChatData.messages.length} 条消息 · title: ${MockChatData.title ?? "(无)"}`,
    mockPreview: MockChatData,
    supportsDataQuery: true,
  },
  {
    href: "/eh",
    title: "EH 搜索结果",
    description:
      "E-Hentai 搜索结果卡片页（封面、标签、二维码），供 /eh 截图回传。",
    injectKey: "__EH_DATA__",
    icon: <BookOpen size={22} />,
    accent: "from-rose-500 to-pink-600",
    iconBg: "bg-rose-600",
    mockSummary: `query: 「${MockEhData.query}」· ${MockEhData.results.length} 条结果`,
    mockPreview: MockEhData,
    supportsDataQuery: true,
  },
  {
    href: "/imgsearch",
    title: "以图搜图结果",
    description:
      "SauceNAO 与 Soutubot 的反向图片搜索结果页，供 /imgsearch 截图回传。",
    injectKey: "__IMGSEARCH_DATA__",
    icon: <Search size={22} />,
    accent: "from-cyan-500 to-teal-600",
    iconBg: "bg-cyan-700",
    mockSummary: `${MockImageSearchData.results.length} 条匹配结果`,
    mockPreview: MockImageSearchData,
    supportsDataQuery: true,
  },
];

function encodeMockQuery(data: unknown): string {
  const json = JSON.stringify(data);
  return btoa(unescape(encodeURIComponent(json)));
}

const primaryBtnClass =
  "inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-zinc-800";
const secondaryBtnClass =
  "inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3.5 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-6 py-5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-900 text-white">
            <FlaskConical size={22} />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              nanofish 前端预览
            </h1>
            <p className="text-sm text-zinc-500">
              进入各截图界面，使用内置 mock 参数本地调试
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 p-6 pb-16">
        <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-800">
              <Code2 size={18} />
            </div>
            <div className="space-y-1 text-sm text-zinc-600">
              <p className="font-medium text-zinc-900">数据注入方式</p>
              <ul className="list-disc space-y-1 pl-4">
                <li>
                  Playwright：打开页面前注入{" "}
                  <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs">
                    window.__CHAT_DATA__
                  </code>{" "}
                  /{" "}
                  <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs">
                    window.__EH_DATA__
                  </code>
                </li>
                <li>
                  各页均支持 URL 参数{" "}
                  <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs">
                    ?data=&lt;base64(json)&gt;
                  </code>
                  （本地预览用）
                </li>
                <li>无注入时各页自动回退到 types 中的 Mock 数据</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="grid gap-4">
          {PAGES.map((page) => (
            <PageCard key={page.href} page={page} />
          ))}
        </section>
      </main>
    </div>
  );
}

function PageCard({ page }: { page: PageEntry }) {
  const mockQueryHref = page.supportsDataQuery
    ? `${page.href}?data=${encodeURIComponent(encodeMockQuery(page.mockPreview))}`
    : page.href;

  return (
    <Card className="overflow-hidden border border-zinc-200 bg-white shadow-sm">
      <div className={`h-1.5 bg-gradient-to-r ${page.accent}`} />
      <div className="space-y-4 p-5">
        <div className="flex items-start gap-4">
          <div
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white ${page.iconBg}`}
          >
            {page.icon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">
                {page.title}
              </h2>
              <code className="rounded-md bg-zinc-100 px-2 py-0.5 font-mono text-[11px] text-zinc-600">
                {page.href}
              </code>
            </div>
            <p className="mt-1 text-sm text-zinc-500">{page.description}</p>
            <p className="mt-2 text-xs text-zinc-400">
              inject:{" "}
              <code className="font-mono text-zinc-500">{page.injectKey}</code>
              {" · "}
              {page.mockSummary}
            </p>
          </div>
        </div>

        <details className="group rounded-xl border border-zinc-100 bg-zinc-50">
          <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-900">
            查看 Mock 参数
          </summary>
          <pre className="max-h-64 overflow-auto border-t border-zinc-100 px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-700">
            {JSON.stringify(page.mockPreview, null, 2)}
          </pre>
        </details>

        <div className="flex flex-wrap gap-2">
          <Link href={page.href} className={primaryBtnClass}>
            进入界面（默认 Mock）
            <ArrowRight size={16} />
          </Link>
          <Link href={mockQueryHref} className={secondaryBtnClass}>
            带 Mock URL 参数打开
            <ExternalLink size={14} />
          </Link>
          <Link
            href={page.href}
            target="_blank"
            rel="noreferrer"
            className={secondaryBtnClass}
          >
            新标签打开
            <ExternalLink size={14} />
          </Link>
        </div>
      </div>
    </Card>
  );
}
