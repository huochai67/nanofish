/**
 * Download EhTagTranslation release JSON and write a compact lookup map
 * to public/ehtag-dict.json for the /eh screenshot page.
 *
 * Usage:
 *   node scripts/fetch-ehtag.mjs          # skip if output exists
 *   node scripts/fetch-ehtag.mjs --force  # always re-download
 */
import { gunzipSync } from "node:zlib";
import { mkdir, writeFile, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const OUT = path.join(ROOT, "public", "ehtag-dict.json");
const SOURCE_URL =
  "https://github.com/EhTagTranslation/Database/releases/latest/download/db.text.json.gz";

const force = process.argv.includes("--force");

async function exists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

if (!force && (await exists(OUT))) {
  console.log(`ehtag dict exists, skip: ${OUT}`);
  process.exit(0);
}

console.log(`downloading ${SOURCE_URL}`);
const res = await fetch(SOURCE_URL, {
  headers: { "User-Agent": "nanofish-app/fetch-ehtag" },
  redirect: "follow",
});
if (!res.ok) {
  console.error(`download failed: HTTP ${res.status}`);
  process.exit(1);
}

const gz = Buffer.from(await res.arrayBuffer());
const raw = gunzipSync(gz).toString("utf8");
const payload = JSON.parse(raw);

if (!payload?.data || !Array.isArray(payload.data)) {
  console.error("invalid EhTagTranslation JSON: missing data[]");
  process.exit(1);
}

/** @type {Record<string, Record<string, string>>} */
const dict = {};
let count = 0;
for (const item of payload.data) {
  const ns = item?.namespace;
  if (!ns || !item.data || typeof item.data !== "object") continue;
  const bucket = {};
  for (const [tag, meta] of Object.entries(item.data)) {
    const name = meta?.name;
    if (typeof name === "string" && name.length > 0) {
      bucket[tag] = name;
      count += 1;
    }
  }
  if (Object.keys(bucket).length > 0) {
    dict[ns] = bucket;
  }
}

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify(dict));
console.log(
  `wrote ${OUT} (namespaces=${Object.keys(dict).length}, tags=${count})`,
);
