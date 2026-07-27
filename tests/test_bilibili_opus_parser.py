import asyncio
from typing import Any

from msgspec import convert

from src.plugins.media_parser.parsers.bilibili import BilibiliParser
from src.plugins.media_parser.parsers.bilibili.dynamic import DynamicInfo


class _Opus:
    async def get_info(self) -> dict[str, Any]:
        return {
            "item": {
                "id_str": "1229722001022648356",
                "type": 0,
                "modules": [
                    {
                        "module_type": "MODULE_TYPE_AUTHOR",
                        "module_author": {
                            "name": "Narcissuu",
                            "face": "https://example.com/avatar.jpg",
                            "mid": 34281074,
                            "pub_time": "2026年07月27日 20:29",
                            "pub_ts": "1785155365",
                        },
                    },
                    {
                        "module_type": "MODULE_TYPE_STAT",
                        "module_stat": {
                            "forward": {"count": 0},
                            "comment": {"count": 9},
                            "like": {"count": 42},
                            "coin": {"count": 0},
                            "favorite": {"count": 0},
                        },
                    },
                ],
            },
        }


def test_opus_parser_extracts_stats() -> None:
    result = asyncio.run(BilibiliParser()._parse_bilibli_api_opus(_Opus()))

    assert result.extra["stats"] == {
        "share": 0,
        "reply": 9,
        "like": 42,
        "coin": 0,
        "favorite": 0,
    }


def test_dynamic_parser_extracts_stats() -> None:
    dynamic_info = convert(
        {
            "id_str": "1229722001022648356",
            "type": "DYNAMIC_TYPE_DRAW",
            "visible": True,
            "modules": {
                "module_author": {
                    "name": "Narcissuu",
                    "face": "https://example.com/avatar.jpg",
                    "mid": 34281074,
                    "pub_time": "2026年07月27日 20:29",
                    "pub_ts": 1785155365,
                },
                "module_stat": {
                    "forward": {"count": 0},
                    "comment": {"count": 9},
                    "like": {"count": 42},
                },
            },
        },
        DynamicInfo,
    )

    result = asyncio.run(BilibiliParser()._parse_dynamic_info(dynamic_info))

    assert result.extra["stats"] == {"share": 0, "reply": 9, "like": 42}
