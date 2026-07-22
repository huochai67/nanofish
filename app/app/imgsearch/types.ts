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
