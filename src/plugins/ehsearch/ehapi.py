import asyncio
import re
import threading

import cloudscraper
import httpx
from loguru import logger


class EhMetaData:
    # --- 这里是您的属性定义 ---
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

    # --- 生成的 __init__ 方法 ---
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
        **kwargs,
    ):
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
        return f"[{self.category}]{self.title} \n\tDate: {self.posted} \n\tTags: {self.tags} \n\tUrl: {self.url()} \n\tThumbnail: {self.thumb}"  # noqa: E501


class EhAPI:
    _instance = None
    _lock = threading.Lock()  # 用于确保线程安全的单例创建

    def __new__(cls, *args, **kwargs):
        """
        重写 __new__ 方法来实现单例模式。
        """
        if not cls._instance:
            with cls._lock:
                # 再次检查，防止多线程环境下重复创建实例
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, proxy: str | None = None) -> None:
        # 防止重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.proxy = None
        self.reqproxy = None
        if proxy:
            logger.debug(f"setting up proxy {proxy}")
            self.proxy = proxy
            self.reqproxy = {"http": self.proxy, "https": self.proxy}

        # Optimized configuration for v3 challenges
        self.scraper = cloudscraper.create_scraper(
            interpreter="js2py",  # Recommended for v3 challenges
            delay=5,  # Allow more time for complex challenges
            debug=False,  # Enable debug output to see v3 detection
        )
        self._initialized = True
        logger.info("初始化完成")

    async def search(self, title: str, size: int = 10) -> list[EhMetaData]:
        cookies = {
            "ipb_member_id": "***REMOVED***",
            "ipb_pass_hash": "***REMOVED***",
            "sk": "***REMOVED***",
            "igneous": "***REMOVED***",
        }

        response = await asyncio.to_thread(
            self.scraper.get,
            url=r"https://exhentai.org/",
            params={"f_search": title},
            cookies=cookies,
            proxies=self.reqproxy,
        )

        pattern = (
            r"https://exhentai.org/g/(?P<gallery_id>\d+)/(?P<gallery_token>[0-9a-f]+)/"
        )
        results = []
        for match in re.finditer(pattern, response.text):
            # 通过名称获取捕获组的内容
            gallery_id = match.group("gallery_id")
            gallery_token = match.group("gallery_token")
            results.append([gallery_id, gallery_token])

        items = []
        if len(results) > 0:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                if len(results) > size:
                    results = results[:size]

                response = await client.post(
                    url="https://api.e-hentai.org/api.php",
                    json={
                        "method": "gdata",
                        "gidlist": results,
                        "namespace": 1,
                    },
                )

                j = response.json()
                items = [EhMetaData(**item) for item in j["gmetadata"]]

        return items
