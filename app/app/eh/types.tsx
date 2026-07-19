export interface EhGalleryItem {
  title: string;
  title_jpn?: string;
  category: string;
  thumb?: string;
  uploader: string;
  posted: string;
  filecount: string;
  rating: string;
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
        "language: 汉语",
        "parody: 学园偶像大师",
        "character: 藤田琴音",
        "female: 巨乳",
        "artist: しいたけたいし",
        "group: しいたけ工房",
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
        "language: 英语",
        "male: 眼镜",
        "mixed: 群交",
        "other: 全彩",
        "reclass: 漫画",
      ],
      url: "https://exhentai.org/g/7654321/fedcba98/",
    },
  ],
};
