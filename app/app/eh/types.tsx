export interface EhGalleryItem {
  title: string;
  title_jpn?: string;
  category: string;
  thumb?: string;
  uploader: string;
  posted: string;
  filecount: string;
  rating: string;
  /** Raw EH tags, e.g. "female:big breasts" (translated on the frontend) */
  tags: string[];
  url: string;
}

export interface EhResultData {
  query: string;
  results: EhGalleryItem[];
}

export const MockEhData: EhResultData = {
  query: "学園アイドルマスター",
  results: [
    {
      title:
        "[しいたけ工房 (しいたけたいし)] ギャルとハーフのアイドルと△(トライアングル)二股浮気Hする本 (学園アイドルマスター)",
      title_jpn: "",
      category: "Doujinshi",
      thumb: "",
      uploader: "example",
      posted: "1710000000",
      filecount: "24",
      rating: "4.50",
      tags: [
        "language:chinese",
        "parody:gakuen idolmaster",
        "character:fujita kotone",
        "female:big breasts",
        "artist:shiitake taishi",
        "group:shiitake koubou",
      ],
      url: "https://exhentai.org/g/1234567/abcdef01/",
    },
    {
      title: "[Example Circle] Sample Title (Series)",
      title_jpn: "サンプルタイトル",
      category: "Manga",
      thumb: "",
      uploader: "uploader2",
      posted: "1700000000",
      filecount: "12",
      rating: "3.80",
      tags: [
        "language:english",
        "male:glasses",
        "mixed:group",
        "other:full color",
        "reclass:manga",
      ],
      url: "https://exhentai.org/g/7654321/fedcba98/",
    },
  ],
};
