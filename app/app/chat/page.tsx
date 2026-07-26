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
  ImageOff,
  Check,
} from "lucide-react";
import {
  ChatData,
  ChatMessage,
  MessageSegment,
  MockChatData,
  parseChatData,
  Role,
} from "./types";
import { parseUrlData, encodeUrlData } from "../utils/url-data";
import { useAssetReadiness } from "../utils/use-asset-readiness";
import { Content, Notice, PageHeader, PageShell } from "../components/chrome";

declare global {
  interface Window {
    __CHAT_DATA__?: ChatData;
  }
}

function loadChatData(): { data: ChatData; error: string | null } {
  if (typeof window !== "undefined" && window.__CHAT_DATA__) {
    const data = parseChatData(window.__CHAT_DATA__);
    return data
      ? { data, error: null }
      : { data: MockChatData, error: "注入的对话数据无效，已回退到默认 Mock 对话。" };
  }

  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const dataParam = params.get("data");
    if (dataParam) {
      const parsed = parseUrlData(dataParam, parseChatData);
      return parsed.data
        ? { data: parsed.data, error: null }
        : { data: MockChatData, error: "URL 参数无效，已回退到默认 Mock 对话。" };
    }
  }

  return { data: MockChatData, error: null };
}

export default function ChatPage() {
  const [chatData, setChatData] = useState<ChatData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { status, beginAssetTracking, completeAsset } = useAssetReadiness();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const { data, error: loadError } = loadChatData();
      setChatData(data);
      setError(loadError);
      beginAssetTracking(
        data.messages.reduce(
          (count, message) =>
            count +
            message.content.filter(
              (segment) => segment.type === "image_url" && Boolean(segment.image_url?.url),
            ).length,
          0,
        ),
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, [beginAssetTracking]);

  const copyShareUrl = async () => {
    if (!chatData) return;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("data", encodeUrlData(chatData));
      await navigator.clipboard.writeText(url.toString());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("对话内容过大或浏览器拒绝访问剪贴板，无法生成分享链接。");
    }
  };

  if (!chatData) {
    return <div className="min-h-screen bg-paper" data-ready="false" />;
  }

  const title = chatData.title?.trim() || "对话";

  return (
    <PageShell ready={status}>
      <PageHeader
        icon={<MessageSquare size={18} />}
        accent="bg-indigo-600 shadow-indigo-600/25"
        title={title}
        subtitle={`${chatData.messages.length} 条消息`}
        action={
          <button
            type="button"
            onClick={copyShareUrl}
            aria-label="复制带数据的分享链接"
            title="复制带数据的分享链接"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-black/[0.08] bg-white px-2.5 text-xs font-medium text-zinc-600 transition hover:bg-zinc-50 hover:text-zinc-900"
          >
            {copied ? <Check size={14} className="text-emerald-600" /> : <Share2 size={14} />}
            {copied ? "已复制" : "分享"}
          </button>
        }
      />

      <Content className="space-y-4 py-5 pb-14">
        {error ? <Notice>{error}</Notice> : null}

        {chatData.messages.map((msg, idx) => (
          <MessageRow key={idx} message={msg} index={idx} onAsset={completeAsset} />
        ))}
      </Content>
    </PageShell>
  );
}

const ROLE_META: Record<
  Role,
  { label: string; Icon: typeof Bot; avatar: string; side: "left" | "right" }
> = {
  assistant: {
    label: "助手",
    Icon: Bot,
    avatar: "border border-black/[0.06] bg-white text-indigo-600 shadow-sm",
    side: "left",
  },
  user: {
    label: "用户",
    Icon: User,
    avatar: "bg-indigo-600 text-white shadow-sm shadow-indigo-600/25",
    side: "right",
  },
};

function MessageRow({
  message,
  index,
  onAsset,
}: {
  message: ChatMessage;
  index: number;
  onAsset: () => void;
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
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full sm:h-9 sm:w-9 ${meta.avatar}`}
        aria-hidden
      >
        <Icon size={15} strokeWidth={2.25} />
      </div>

      <div
        className={`flex min-w-0 max-w-[85%] flex-col gap-1 sm:max-w-[78%] ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <span className="px-1 text-[11px] font-medium text-zinc-400">
          {meta.label}
        </span>

        <div
          className={`w-full overflow-hidden rounded-2xl px-3.5 py-2.5 ${
            isUser
              ? "rounded-tr-md bg-indigo-600 text-white shadow-sm shadow-indigo-600/25"
              : "rounded-tl-md border border-black/[0.05] bg-white text-zinc-800 shadow-sm"
          }`}
        >
          <div className="flex flex-col gap-2.5">
            {message.content.map((segment, i) => (
              <SegmentView key={i} segment={segment} isUser={isUser} onAsset={onAsset} />
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
  onAsset,
}: {
  segment: MessageSegment;
  isUser: boolean;
  onAsset: () => void;
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
    return <ImageSegment url={url} isUser={isUser} onAsset={onAsset} />;
  }

  if (segment.type === "file") {
    const name = segment.file?.filename || "未命名文件";
    const ext = name.includes(".") ? name.split(".").pop()?.toUpperCase() : "";
    return (
      <div
        className={`flex items-center gap-3 rounded-xl px-3 py-2.5 ring-1 ring-inset ${
          isUser
            ? "bg-white/10 ring-white/20"
            : "bg-zinc-50 ring-black/[0.06]"
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

function ImageSegment({
  url,
  isUser,
  onAsset,
}: {
  url: string;
  isUser: boolean;
  onAsset: () => void;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`flex h-24 items-center justify-center gap-2 rounded-xl px-4 text-sm ${
          isUser ? "bg-white/10 text-indigo-100" : "bg-zinc-100 text-zinc-500"
        }`}
      >
        <ImageOff size={17} />
        图片不可预览
      </div>
    );
  }

  return (
    <figure
      className={`w-fit overflow-hidden rounded-xl ring-1 ring-inset ${
        isUser ? "ring-white/20" : "ring-black/[0.06]"
      }`}
    >
      <img
        src={url}
        alt="对话中的图片"
        className="max-h-72 w-auto max-w-full object-contain"
        referrerPolicy="no-referrer"
        onLoad={onAsset}
        onError={() => {
          setFailed(true);
          onAsset();
        }}
      />
    </figure>
  );
}
