import { asRecord, optionalSafeUrl, optionalString } from "@/app/utils/data-validation";

export interface ImageSearchResult {
  source: string;
  similarity: number | null;
  title: string;
  author: string;
  url: string;
  thumbnail: string;
}

export interface ImageSearchData {
  image: string;
  results: ImageSearchResult[];
  errors: string[];
}

function parseSearchResult(value: unknown): ImageSearchResult | null {
  const result = asRecord(value);
  if (!result) return null;

  const source = optionalString(result, "source");
  const title = optionalString(result, "title");
  const author = optionalString(result, "author");
  const url = optionalSafeUrl(result, "url");
  const thumbnail = optionalSafeUrl(result, "thumbnail", true);
  const similarity = result.similarity;

  if (
    source === undefined ||
    title === undefined ||
    author === undefined ||
    url === undefined ||
    url === null ||
    thumbnail === undefined ||
    thumbnail === null
  ) {
    return null;
  }
  if (similarity !== null && (typeof similarity !== "number" || !Number.isFinite(similarity) || similarity < 0 || similarity > 100)) {
    return null;
  }

  return { source, title, author, url, thumbnail, similarity };
}

export function parseImageSearchData(value: unknown): ImageSearchData | null {
  const data = asRecord(value);
  const image = data ? optionalSafeUrl(data, "image", true) : undefined;
  if (
    !data ||
    image === null ||
    !Array.isArray(data.results) ||
    data.results.length > 50 ||
    !Array.isArray(data.errors) ||
    data.errors.length > 20
  ) {
    return null;
  }

  const results = data.results.map(parseSearchResult);
  const errors = data.errors.filter((error): error is string => typeof error === "string");
  if (results.some((result) => result === null) || errors.length !== data.errors.length) {
    return null;
  }

  return { image: image ?? "", results: results as ImageSearchResult[], errors };
}

export const MockImageSearchData: ImageSearchData = {
  image: "",
  results: [
    {
      source: "SauceNAO",
      similarity: 92.48,
      title: "Sample Illustration",
      author: "example artist",
      url: "https://www.pixiv.net/artworks/123456789",
      thumbnail: "",
    },
    {
      source: "Soutubot",
      similarity: 86.12,
      title: "Untitled artwork",
      author: "",
      url: "https://twitter.com/example/status/123456789",
      thumbnail: "",
    },
  ],
  errors: [],
};
