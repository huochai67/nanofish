from loguru import logger

from ..utils.http import HttpRequestError, http_post

# paste.rs 的上传地址
PASTE_RS_URL = "https://paste.rs/"


async def upload_to_paste_rs(text_content: str, proxy: str | None = None) -> str:
    """
    使用 httpx 异步上传文本到 paste.rs。
    参数:
        text_content (str): 你想要上传的文本内容。
    返回:
        str: 成功上传后得到的 Paste URL。
    抛出:
        HttpRequestError: 网络或 HTTP 状态错误。
    """
    logger.info("正在上传文本到 paste.rs...")

    try:
        response = await http_post(
            PASTE_RS_URL,
            proxy=proxy,
            content=text_content.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    except HttpRequestError:
        logger.error("上传 paste.rs 失败")
        raise

    paste_url = response.text
    logger.info("上传成功！")
    return paste_url
