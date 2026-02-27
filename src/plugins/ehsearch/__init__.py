from nonebot import get_plugin_config, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config
from .ehapi import EhAPI
from .ehtag import TagTranslator
from .pasters import upload_to_paste_rs

__plugin_meta__ = PluginMetadata(
    name="ehsearch",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
ehapi = EhAPI(proxy=config.proxy)
ehtranslator = TagTranslator(db_path=config.eh_db)

ehsearch = on_command("eh", priority=10, block=True, permission=SUPERUSER)


def get_replyid(msg: Message) -> None | int:
    for segment in msg:
        if segment.type == "reply":
            return segment.data.get("id")
    return None


def get_first_image(msg: Message) -> None | str:
    for segment in msg:
        if segment.type == "image":
            return segment.data.get("url")
    return None


def get_plaintext(msg: Message) -> str:
    ret = ""
    for segment in msg:
        if segment.type == "text":
            ret += str(segment.data.get("text"))
    return ret


async def get_reply(bot: Bot, msg: Message) -> None | dict:
    message_id = get_replyid(msg)
    if message_id:
        return await bot.get_msg(message_id=message_id)
    return None


@ehsearch.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await ehsearch.finish("failed get reply")
        return

    # TODO: image comparison
    # imageurl = get_first_image(msg=Message(msg_reply.get("raw_message")))
    # logger.debug(f"get image {imageurl}")

    search = get_plaintext(Message(msg_reply.get("raw_message")))
    logger.info(f"searching {search}")
    result = await EhAPI().search(title=search, size=3)
    logger.debug(result)

    if len(result) != 0:
        output = ""
        for i, r in enumerate(result):
            r.tags = TagTranslator().trans_all(r.tags)
            output += f"[{i}][{r.category}]{r.title}\n"
            output += (
                f"\t Uploader: {r.uploader}\t time: {r.posted}\t pages: {r.filecount}\n"
            )
            output += f"\t thumb: {r.thumb}\t url:{r.url()}\n"
            output += f"\t tags: {r.tags}\n\n"

        url = await upload_to_paste_rs(text_content=output, proxy=config.proxy)
        await ehsearch.finish(f"got {len(result)} results :{url}")

    await ehsearch.finish("No availble content.")
