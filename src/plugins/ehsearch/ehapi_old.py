
class EhItem:
    def __init__(
        self, typ: str, date: str, thumbnail: str, title: str, url: str, tags: list[str]
    ) -> None:
        self.typ = typ
        self.date = date
        self.thumbnail = thumbnail
        self.title = title
        self.url = url
        self.tags = tags

    def prettify(self) -> str:
        return f"[{self.typ}]{self.title} \n\tDate: {self.date} \n\tTags: {self.tags} \n\tUrl: {self.url} \n\tThumbnail: {self.thumbnail}"


class EhParser:
    def parse_tr(r: str | BeautifulSoup) -> None | EhItem:
        if type(r) == "str":
            r = BeautifulSoup(r)

        glthumb = r.find(attrs={"class": "glthumb"})
        gl3c = r.find(attrs={"class": "gl3c glname"})
        gl1c = r.find(attrs={"class": "gl1c glcat"})

        if glthumb and gl1c and gl3c:
            typ = ""
            date = ""
            thumbnail = ""
            title = ""
            url = ""
            tags = []
            thumbnail = glthumb.img.get("src")
            if not thumbnail.startswith("https"):
                thumbnail = glthumb.img.get("data-src")

            page = glthumb.find(attrs={"class": "ir"})
            if page:
                info = page.parent.parent.div.find_all("div")
                date = info[1].text

            typ = gl1c.div.text

            url = gl3c.a["href"]
            title = gl3c.a.div.text
            htags = gl3c.a.find_all(attrs={"class": "gt"})
            for l in htags:
                tags.append(l.text)

            return EhItem(typ, date, thumbnail, title, url, tags)

        return None

    def parseHtml(html: str) -> list[EhItem]:
        ret = []
        soup = BeautifulSoup(html, features="html.parser")
        results = soup.find_all("tr")
        for r in results:
            result = EhParser.parse_tr(r)
            if result:
                ret.append(result)
        return ret


class EhAPI:
    def __init__(self) -> None:
        # Optimized configuration for v3 challenges
        self.scraper = cloudscraper.create_scraper(
            interpreter="js2py",  # Recommended for v3 challenges
            delay=5,  # Allow more time for complex challenges
            debug=False,  # Enable debug output to see v3 detection
        )
        pass

    def search(self, title: str) -> None:

        cookies = {
            "ipb_member_id": "***REMOVED***",
            "ipb_pass_hash": "***REMOVED***",
            "sk": "***REMOVED***",
            "igneous": "***REMOVED***",
        }
        response = self.scraper.get(
            url=r"https://exhentai.org/",
            cookies=cookies,
        )
        items = EhParser.parseHtml(response.text)
        for i in items:
            print(i.prettify())
        return items
