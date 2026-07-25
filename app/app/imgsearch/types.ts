import { asRecord, optionalString } from "@/app/utils/data-validation";

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
  const url = optionalString(result, "url");
  const thumbnail = optionalString(result, "thumbnail");
  const similarity = result.similarity;

  if (
    source === undefined ||
    title === undefined ||
    author === undefined ||
    url === undefined ||
    thumbnail === undefined
  ) {
    return null;
  }
  if (similarity !== null && (typeof similarity !== "number" || !Number.isFinite(similarity))) {
    return null;
  }

  return { source, title, author, url, thumbnail, similarity };
}

export function parseImageSearchData(value: unknown): ImageSearchData | null {
  const data = asRecord(value);
  const image = data ? optionalString(data, "image") : undefined;
  if (!data || image === undefined || !Array.isArray(data.results) || !Array.isArray(data.errors)) {
    return null;
  }

  const results = data.results.map(parseSearchResult);
  const errors = data.errors.filter((error): error is string => typeof error === "string");
  if (results.some((result) => result === null) || errors.length !== data.errors.length) {
    return null;
  }

  return { image, results: results as ImageSearchResult[], errors };
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
