/** Compact EhTagTranslation map: namespace → tag → display name */
export type TagDict = Record<string, Record<string, string>>;
const TAG_DICT_TIMEOUT_MS = 5_000;
const translationIndexes = new WeakMap<TagDict, Map<string, string>>();

export type ParsedTag = {
  ns: string;
  tag: string;
};

/** Parse EH raw tag "namespace:tag" (or bare string). */
export function parseRawTag(raw: string): ParsedTag {
  const idx = raw.indexOf(":");
  if (idx <= 0) {
    return { ns: "", tag: raw.trim() };
  }
  return {
    ns: raw.slice(0, idx).trim().toLowerCase(),
    tag: raw.slice(idx + 1).trim(),
  };
}

/** Translate a raw tag using dict; fall back to original tag name. */
export function translateTag(raw: string, dict: TagDict | null): string {
  const { ns, tag } = parseRawTag(raw);
  if (!tag) return raw;
  if (!dict) return tag;

  let index = translationIndexes.get(dict);
  if (!index) {
    index = new Map<string, string>();
    for (const [namespace, bucket] of Object.entries(dict)) {
      for (const [rawTag, label] of Object.entries(bucket)) {
        index.set(`${namespace}:${rawTag}`, label);
        if (!index.has(rawTag)) index.set(rawTag, label);
      }
    }
    translationIndexes.set(dict, index);
  }

  return index.get(`${ns}:${tag}`) ?? index.get(tag) ?? tag;
}

function isTagDict(value: unknown): value is TagDict {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Object.values(value).every(
    (bucket) =>
      bucket &&
      typeof bucket === "object" &&
      !Array.isArray(bucket) &&
      Object.values(bucket).every((label) => typeof label === "string"),
  );
}

/** Load dict from public asset (built by scripts/fetch-ehtag.mjs). */
export async function loadTagDict(signal?: AbortSignal): Promise<TagDict> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), TAG_DICT_TIMEOUT_MS);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });

  try {
    const res = await fetch("/ehtag-dict.json", { signal: controller.signal });
    if (!res.ok) {
      console.warn(`ehtag dict unavailable: HTTP ${res.status}`);
      return {};
    }
    const data: unknown = await res.json();
    if (!isTagDict(data)) {
      console.warn("ehtag dict has an invalid shape");
      return {};
    }
    return data;
  } catch (e) {
    if (!controller.signal.aborted) console.warn("ehtag dict load failed", e);
    return {};
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}
