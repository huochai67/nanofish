import httpx
from loguru import logger

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
        httpx.HTTPStatusError: 如果服务器返回一个错误状态码 (例如 4xx 或 5xx)。
        httpx.RequestError: 如果发生网络连接问题。
    """
    logger.info("正在上传文本到 paste.rs...")

    # 使用 async with 创建一个异步客户端，确保会话被正确关闭
    async with httpx.AsyncClient(proxy=proxy) as client:
        try:
            # 发送 POST 请求。
            # - `content` 参数直接将字符串作为请求体。
            # - `headers` 指定了内容类型，这是良好实践，尽管 paste.rs 也能处理没有它的情况。
            response = await client.post(
                PASTE_RS_URL,
                content=text_content.encode("utf-8"),  # 最佳实践：将字符串编码为字节
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )

            # 检查响应状态码。如果不是 2xx，此行会抛出 HTTPStatusError 异常。
            # paste.rs 成功时返回 201 Created。
            response.raise_for_status()

            # 服务器返回的响应体就是新的 Paste URL
            paste_url = response.text
            logger.info("上传成功！")
            return paste_url
        except httpx.HTTPStatusError as e:
            logger.error(
                f"上传失败，服务器返回错误: {e.response.status_code} {e.response.reason_phrase}"
            )
            # 可以选择在这里进一步处理错误，例如打印响应体
            # print(f"服务器响应内容: {e.response.text}")
            raise  # 重新抛出异常，让调用者知道发生了错误
        except httpx.RequestError as e:
            logger.error(f"网络连接错误: {e}")
            raise  # 重新抛出异常
