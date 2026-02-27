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

//[{'role': 'user', 'content': }, {'role': 'user', 'content':}, {'role': 'assistant', 'content': }]

export interface ChatData {
  title?: string;
  messages: ChatMessage[];
}
export const MockChatData: ChatData = {
  title: "Technical Discussion",
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
      ],
    },
    {
      role: "user",
      content: [
        {
          type: "image_url",
          image_url: {
            url: "https://heroui-assets.nyc3.cdn.digitaloceanspaces.com/docs/cherries.jpeg",
          },
        },
      ],
    },
    {
      role: "user",
      content: [{ type: "text", text: "这是什么" }],
    },
    {
      role: "assistant",
      content: [
        {
          type: "text",
          text: "这是一条**测试信息**。\n\n当你发送这条信息时，通常是为了检查：\n1. **通信是否正常**（发送和接收功能是否通畅）。\n2. **系统反应速度**（看看 AI 或对方回复得快不快）。\n3. **格式显示**（确认文字、符号是否能正确显示）。\n\n如果你是想确认我是否在线，**是的，我在这里，随时准备为你提供帮助！** 请问有什么我可以帮你的吗？",
        },
      ],
    },
  ],
};
