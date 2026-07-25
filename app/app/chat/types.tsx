import { asRecord, optionalString } from "@/app/utils/data-validation";

export type Role = "assistant" | "user";

export type MessageSegmentType = "file" | "text" | "image_url";

export interface MessageSegment {
  type: MessageSegmentType;
  text?: string;
  file?: {
    filename: string;
    file_data: string;
  };
  image_url?: {
    url: string;
  };
}

export interface ChatMessage {
  role: Role;
  content: MessageSegment[];
}

export interface ChatData {
  title?: string;
  messages: ChatMessage[];
}

function parseSegment(value: unknown): MessageSegment | null {
  const segment = asRecord(value);
  const type = segment?.type;
  if (!segment || typeof type !== "string") return null;

  if (type === "text") {
    return { type, text: optionalString(segment, "text") };
  }

  if (type === "image_url") {
    const imageUrl = asRecord(segment.image_url);
    const url = imageUrl ? optionalString(imageUrl, "url") : undefined;
    return url === undefined ? null : { type, image_url: { url } };
  }

  if (type === "file") {
    const file = asRecord(segment.file);
    const filename = file ? optionalString(file, "filename") : undefined;
    const fileData = file ? optionalString(file, "file_data") : undefined;
    return filename === undefined || fileData === undefined
      ? null
      : { type, file: { filename, file_data: fileData } };
  }

  return null;
}

export function parseChatData(value: unknown): ChatData | null {
  const data = asRecord(value);
  if (!data || !Array.isArray(data.messages)) return null;

  const messages: ChatMessage[] = [];
  for (const value of data.messages) {
    const message = asRecord(value);
    if (!message || !Array.isArray(message.content)) return null;
    const role = message.role;
    if (role !== "assistant" && role !== "user") return null;

    const content = message.content.map(parseSegment);
    if (content.some((segment) => segment === null)) return null;
    messages.push({ role, content: content as MessageSegment[] });
  }

  return { title: optionalString(data, "title"), messages };
}

export const MockChatData: ChatData = {
  title: "多模态测试对话",
  messages: [
    {
      role: "user",
      content: [
        {
          type: "file",
          file: {
            filename: "test.txt",
            file_data:
              "data:text/plain;base64,6L+Z5piv5LiA5p2h5rWL6K+V5L+h5oGv",
          },
        },
        {
          type: "image_url",
          image_url: {
            url: "https://heroui-assets.nyc3.cdn.digitaloceanspaces.com/docs/cherries.jpeg",
          },
        },
        { type: "text", text: "这是什么？" },
      ],
    },
    {
      role: "assistant",
      content: [
        {
          type: "text",
          text: "这是一条**测试信息**。\n\n当你发送这条信息时，通常是为了检查：\n1. **通信是否正常**（发送和接收功能是否通畅）\n2. **系统反应速度**（看看 AI 或对方回复得快不快）\n3. **格式显示**（确认文字、符号是否能正确显示）\n\n如果你是想确认我是否在线——**是的，我在这里。** 请问有什么可以帮你的？",
        },
      ],
    },
  ],
};
