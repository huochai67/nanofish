import asyncio
import re
import threading
from typing import Any, ClassVar, Self

import cloudscraper
from loguru import logger

from ..utils.http import http_post


class EhMetaData:
    gid: int
    token: str
    title: str
    title_jpn: str
    category: str
    thumb: str
    uploader: str
    posted: str
    filecount: str
    filesize: int
    rating: str
    tags: list[str]

    def __init__(
        self,
        gid: int,
        token: str,
        title: str,
        title_jpn: str,
        category: str,
        thumb: str,
        uploader: str,
        posted: str,
        filecount: str,
        filesize: int,
        rating: str,
        tags: list[str],
        **_kwargs: Any,
    ) -> None:
        self.gid = gid
        self.token = token
        self.title = title
        self.title_jpn = title_jpn
        self.category = category
        self.thumb = thumb
        self.uploader = uploader
        self.posted = posted
        self.filecount = filecount
        self.filesize = filesize
        self.rating = rating
        self.tags = tags

    def url(self) -> str:
        return f"https://exhentai.org/g/{self.gid}/{self.token}/"

    def __repr__(self) -> str:
        return (
            f"[{self.category}]{self.title} \n\tDate: {self.posted} "
            f"\n\tTags: {self.tags} \n\tUrl: {self.url()} \n\tThumbnail: {self.thumb}"
        )


class EhAPI:
    _instance: ClassVar[Self | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Self:
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        proxy: str | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.proxy = proxy
        self.reqproxy = {"http": proxy, "https": proxy} if proxy else None
        self.cookies = cookies or {}

        if proxy:
            logger.debug(f"setting up proxy {proxy}")

        self.scraper = cloudscraper.create_scraper(
            interpreter="js2py",
            delay=5,
            debug=False,
        )
        self._initialized = True
        logger.info("EhAPI 初始化完成")

    async def search(self, title: str, size: int = 10) -> list[EhMetaData]:
        if not self.cookies:
            raise ValueError("EhAPI cookies not configured")

        response = await asyncio.to_thread(
            self.scraper.get,
            url=r"https://exhentai.org/",
            params={"f_search": title},
            cookies=self.cookies,
            proxies=self.reqproxy,
        )

        pattern = (
            r"https://exhentai.org/g/(?P<gallery_id>\d+)/(?P<gallery_token>[0-9a-f]+)/"
        )
        results: list[list[str]] = []
        for match in re.finditer(pattern, response.text):
            gallery_id = match.group("gallery_id")
            gallery_token = match.group("gallery_token")
            results.append([gallery_id, gallery_token])

        if not results:
            return []

        if len(results) > size:
            results = results[:size]

        response = await http_post(
            "https://api.e-hentai.org/api.php",
            proxy=self.proxy,
            json={
                "method": "gdata",
                "gidlist": results,
                "namespace": 1,
            },
        )
        data = response.json()
        return [EhMetaData(**item) for item in data["gmetadata"]]
