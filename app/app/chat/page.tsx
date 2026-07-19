/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  User,
  MessageSquare,
  Share2,
  FileText,
  AlertCircle,
  Check,
} from "lucide-react";
import {
  ChatData,
  ChatMessage,
  MessageSegment,
  MockChatData,
  Role,
} from "./types";

declare global {
  interface Window {
    __CHAT_DATA__?: ChatData;
  }
}

function loadChatData(): { data: ChatData; error: string | null } {
  if (typeof window !== "undefined" && window.__CHAT_DATA__) {
    return { data: window.__CHAT_DATA__, error: null };
  }

  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const dataParam = params.get("data");
    if (dataParam) {
      try {
        // Matches btoa(unescape(encodeURIComponent(json))) used when sharing
        const binary = atob(decodeURIComponent(dataParam));
        const json = decodeURIComponent(escape(binary));
        return { data: JSON.parse(json) as ChatData, error: null };
      } catch (e) {
        console.error("Failed to parse URL data", e);
        return {
          data: MockChatData,
          error: "URL 参数无效，已回退到默认 Mock 对话。",
        };
      }
    }
  }

  return { data: MockChatData, error: null };
}

export default function ChatPage() {
  const [chatData, setChatData] = useState<ChatData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const { data, error: loadError } = loadChatData();
    setChatData(data);
    setError(loadError);
    setReady(true);
  }, []);

  const copyShareUrl = async () => {
    if (!chatData) return;
    const json = JSON.stringify(chatData);
    const base64 = btoa(unescape(encodeURIComponent(json)));
    const url = new URL(window.location.href);
    url.searchParams.set("data", base64);
    try {
      await navigator.clipboard.writeText(url.toString());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // ignore clipboard failures in restricted contexts
    }
  };

  if (!chatData) {
    return <div className="min-h-screen bg-zinc-50" data-ready="false" />;
  }

  const title = chatData.title?.trim() || "对话";
  const msgCount = chatData.messages.length;

  return (
    <div
      className="min-h-screen bg-zinc-50 text-zinc-900"
      data-ready={ready ? "true" : "false"}
    >
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/20">
              <MessageSquare size={18} />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold tracking-tight">
                {title}
              </h1>
              <p className="text-xs text-zinc-500">{msgCount} 条消息</p>
            </div>
          </div>
          <button
            type="button"
            onClick={copyShareUrl}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-600 transition hover:bg-zinc-50 hover:text-zinc-900"
            title="复制带数据的分享链接"
          >
            {copied ? <Check size={14} className="text-emerald-600" /> : <Share2 size={14} />}
            {copied ? "已复制" : "分享"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-4 px-4 py-6 pb-16">
        {error ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <p>{error}</p>
          </div>
        ) : null}

        {chatData.messages.map((msg, idx) => (
          <MessageRow key={idx} message={msg} index={idx} />
        ))}
      </main>
    </div>
  );
}

const ROLE_META: Record<
  Role,
  { label: string; Icon: typeof Bot; avatar: string; side: "left" | "right" }
> = {
  assistant: {
    label: "助手",
    Icon: Bot,
    avatar: "bg-violet-600 text-white",
    side: "left",
  },
  user: {
    label: "用户",
    Icon: User,
    avatar: "bg-indigo-600 text-white",
    side: "right",
  },
};

function MessageRow({
  message,
  index,
}: {
  message: ChatMessage;
  index: number;
}) {
  const meta = ROLE_META[message.role] ?? ROLE_META.user;
  const isUser = meta.side === "right";
  const { Icon } = meta;

  return (
    <div
      className={`flex w-full gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}
      data-msg-index={index}
      data-role={message.role}
    >
      <div
        className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full shadow-sm ${meta.avatar}`}
        aria-hidden
      >
        <Icon size={16} strokeWidth={2.25} />
      </div>

      <div
        className={`flex min-w-0 max-w-[min(100%,28rem)] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <span className="px-1 text-[11px] font-medium text-zinc-400">
          {meta.label}
        </span>

        <div
          className={`w-full overflow-hidden rounded-2xl px-3.5 py-2.5 shadow-sm ring-1 ${
            isUser
              ? "rounded-tr-md bg-indigo-600 text-white ring-indigo-500/30"
              : "rounded-tl-md bg-white text-zinc-800 ring-zinc-200"
          }`}
        >
          <div className="flex flex-col gap-2.5">
            {message.content.map((segment, i) => (
              <SegmentView key={i} segment={segment} isUser={isUser} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SegmentView({
  segment,
  isUser,
}: {
  segment: MessageSegment;
  isUser: boolean;
}) {
  if (segment.type === "text") {
    return (
      <div className={isUser ? "chat-md chat-md-user" : "chat-md"}>
        <Markdown remarkPlugins={[remarkGfm]}>
          {segment.text || ""}
        </Markdown>
      </div>
    );
  }

  if (segment.type === "image_url") {
    const url = segment.image_url?.url;
    if (!url) return null;
    return (
      <figure className="overflow-hidden rounded-xl">
        <img
          src={url}
          alt=""
          className="max-h-72 w-auto max-w-full object-contain"
        />
      </figure>
    );
  }

  if (segment.type === "file") {
    const name = segment.file?.filename || "未命名文件";
    const ext = name.includes(".") ? name.split(".").pop()?.toUpperCase() : "";
    return (
      <div
        className={`flex items-center gap-3 rounded-xl px-3 py-2.5 ring-1 ${
          isUser
            ? "bg-white/10 ring-white/20"
            : "bg-zinc-50 ring-zinc-200"
        }`}
      >
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
            isUser ? "bg-white/15 text-white" : "bg-indigo-50 text-indigo-600"
          }`}
        >
          <FileText size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p
            className={`truncate text-sm font-medium ${
              isUser ? "text-white" : "text-zinc-800"
            }`}
          >
            {name}
          </p>
          <p
            className={`text-[11px] ${
              isUser ? "text-indigo-100" : "text-zinc-400"
            }`}
          >
            {ext ? `${ext} 文件` : "附件"}
          </p>
        </div>
      </div>
    );
  }

  return null;
}
