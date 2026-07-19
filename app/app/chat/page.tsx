/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, MessageSquare, Share2, File } from "lucide-react";
import { Button, Card, Avatar, Alert } from "@heroui/react";
import { ChatData, ChatMessage, MockChatData } from "./types";

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
          error: "Invalid data format in URL. Showing default conversation.",
        };
      }
    }
  }

  return { data: MockChatData, error: null };
}

export default function App() {
  const [chatData, setChatData] = useState<ChatData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const { data, error: loadError } = loadChatData();
    setChatData(data);
    setError(loadError);
    setReady(true);
  }, []);

  const generateShareUrl = () => {
    if (!chatData) return window.location.href;
    const json = JSON.stringify(chatData);
    const base64 = btoa(unescape(encodeURIComponent(json)));
    const url = new URL(window.location.href);
    url.searchParams.set("data", base64);
    return url.toString();
  };

  const copyToClipboard = () => {
    const url = generateShareUrl();
    navigator.clipboard.writeText(url);
    alert("Share URL copied to clipboard!");
  };

  if (!chatData) {
    return <div className="min-h-screen" data-ready="false" />;
  }

  return (
    <div className="min-h-screen" data-ready={ready ? "true" : "false"}>
      {chatData.title && (
        <header className="border-b px-6 py-4">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white">
                <MessageSquare size={20} />
              </div>
              <div>
                <h1 className="text-lg font-semibold tracking-tight">
                  {chatData.title || "Chat Viewer"}
                </h1>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button onPress={copyToClipboard} variant="primary" size="sm">
                <Share2 size={16} />
                Share
              </Button>
            </div>
          </div>
        </header>
      )}

      <main className="max-w-3xl mx-auto p-6 pb-24">
        {error && (
          <Alert status="danger">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>{error}</Alert.Title>
            </Alert.Content>
          </Alert>
        )}

        <div className="space-y-8">
          {chatData.messages.map((msg, idx) => (
            <MessageRow key={idx} message={msg} />
          ))}
        </div>
      </main>
    </div>
  );
}

function MessageRow({ message }: { message: ChatMessage }) {
  const isLeft = message.role === "assistant";

  return (
    <div
      className={`flex w-full gap-4 ${
        isLeft ? "flex-row" : "flex-row-reverse"
      }`}
    >
      <div className="shrink-0">
        <Avatar size="lg">
          <Avatar.Fallback>
            <User size={20} />
          </Avatar.Fallback>
        </Avatar>
      </div>

      <div
        className={`flex flex-col max-w-[80%] ${
          isLeft ? "items-start" : "items-end"
        }`}
      >
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            {message.role}
          </span>
        </div>

        <Card
          className={`border ${
            isLeft ? "bg-background" : "bg-accent text-background"
          }`}
        >
          {message.content.map((content, index) => (
            <div key={index}>
              {content.type === "text" && (
                <Markdown remarkPlugins={[remarkGfm]}>{content.text}</Markdown>
              )}
              {content.type === "file" && (
                <div className="flex flex-row justify-center items-center gap-2">
                  <File size={36} className="h-full" />
                  <Card.Header>
                    <Card.Title className="pr-8">File</Card.Title>
                    <Card.Description>
                      {content.file?.filename}
                    </Card.Description>
                  </Card.Header>
                </div>
              )}
              {content.type === "image_url" && (
                <img
                  className="max-w-64 rounded-sm"
                  alt="image"
                  src={content.image_url?.url}
                />
              )}
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
