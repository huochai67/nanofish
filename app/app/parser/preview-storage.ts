import { parseParserScreenshotData, type ParserScreenshotData } from "./types";

const STORAGE_PREFIX = "nanofish:parser-preview:";

export function parserPreviewStorageKey(id: string): string {
  return `${STORAGE_PREFIX}${id}`;
}

type DebugPayloadResult =
  | { data: ParserScreenshotData; error: null }
  | { data: null; error: string };

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function parseParserDebugPayload(value: unknown): DebugPayloadResult {
  const payload = asRecord(value);
  if (!payload) {
    return { data: null, error: "文件根节点必须是对象。" };
  }
  if (payload.path !== "/parser") {
    return { data: null, error: "调试文件的 path 必须是 /parser。" };
  }
  if (payload.global !== "__PARSER_DATA__") {
    return { data: null, error: "调试文件的 global 必须是 __PARSER_DATA__。" };
  }

  const data = parseParserScreenshotData(payload.data);
  return data
    ? { data, error: null }
    : { data: null, error: "调试文件的 data 不符合 Parser 数据结构。" };
}
