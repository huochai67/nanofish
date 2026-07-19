/** Compact EhTagTranslation map: namespace → tag → display name */
export type TagDict = Record<string, Record<string, string>>;

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
  if (ns && dict?.[ns]?.[tag]) {
    return dict[ns][tag];
  }
  // Some entries live under empty/misc namespaces — try bare lookup in all ns
  if (dict) {
    for (const bucket of Object.values(dict)) {
      if (bucket[tag]) return bucket[tag];
    }
  }
  return tag;
}

/** Load dict from public asset (built by scripts/fetch-ehtag.mjs). */
export async function loadTagDict(): Promise<TagDict> {
  try {
    const res = await fetch("/ehtag-dict.json");
    if (!res.ok) {
      console.warn(`ehtag dict unavailable: HTTP ${res.status}`);
      return {};
    }
    return (await res.json()) as TagDict;
  } catch (e) {
    console.warn("ehtag dict load failed", e);
    return {};
  }
}
