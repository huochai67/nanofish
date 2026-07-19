from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

from .config import Config
from .ehapi import EhAPI
from .ehtag import TagTranslator
from .pasters import upload_to_paste_rs

require("acl")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..utils import HttpRequestError, get_plaintext, get_reply

__plugin_meta__ = PluginMetadata(
    name="ehsearch",
    description="E-Hentai 搜索",
    usage="回复一条消息后发送 /eh",
    config=Config,
)

config = get_plugin_config(Config)
ehapi = EhAPI(
    proxy=config.proxy,
    cookies={
        "ipb_member_id": config.eh_ipb_member_id,
        "ipb_pass_hash": config.eh_ipb_pass_hash,
        "sk": config.eh_sk,
        "igneous": config.eh_igneous,
    },
)
ehtranslator = TagTranslator(db_path=config.eh_db)

ehsearch = on_command("eh", priority=10, block=True, permission=require_command("eh"))


@ehsearch.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    quota = check_quota(event, "eh")
    if not quota.allowed:
        await ehsearch.finish(quota.message or "额度不足")
        return

    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await ehsearch.finish("获取被回复消息失败")
        return

    search = get_plaintext(Message(msg_reply.get("raw_message")))
    if not search.strip():
        await ehsearch.finish("被回复消息中没有可搜索的文本")
        return

    logger.info(f"searching {search}")
    try:
        consume_quota(event, "eh")
        result = await ehapi.search(title=search, size=3)
        logger.debug(result)

        if not result:
            await ehsearch.finish("未找到相关结果")
            return

        lines: list[str] = []
        for i, r in enumerate(result):
            r.tags = ehtranslator.trans_all(r.tags)
            lines.append(f"[{i}][{r.category}]{r.title}")
            lines.append(
                f"\t Uploader: {r.uploader}\t time: {r.posted}\t pages: {r.filecount}"
            )
            lines.append(f"\t thumb: {r.thumb}\t url:{r.url()}")
            lines.append(f"\t tags: {r.tags}\n")

        output = "\n".join(lines)
        url = await upload_to_paste_rs(text_content=output, proxy=config.proxy)
    except FinishedException:
        raise
    except HttpRequestError as e:
        logger.warning(f"ehsearch request error: {e}")
        await ehsearch.finish(f"请求失败: {e.message}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("ehsearch unexpected error")
        await ehsearch.finish(f"处理失败: {type(e).__name__}: {e}")
        return

    await ehsearch.finish(f"找到 {len(result)} 条结果: {url}")
