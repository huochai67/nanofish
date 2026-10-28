import asyncio
import base64
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, Self, cast
from unittest.mock import AsyncMock, Mock, call

import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from pydantic import ValidationError
from pytest import MonkeyPatch

from src.plugins import llm
from src.plugins.llm import images
from src.plugins.llm.config import Config, ImageModelConfig

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Bot, MessageEvent


class _RecordingImages:
    def __init__(self, generate_response: object, edit_response: object) -> None:
        self.generate = AsyncMock(return_value=generate_response)
        self.edit = AsyncMock(return_value=edit_response)


class _RecordingClient:
    instances: ClassVar[list["_RecordingClient"]] = []
    generate_response: ClassVar[object] = SimpleNamespace(
        data=[SimpleNamespace(b64_json="generated", url=None)]
    )
    edit_response: ClassVar[object] = SimpleNamespace(
        data=[SimpleNamespace(b64_json="edited", url=None)]
    )

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.images = _RecordingImages(self.generate_response, self.edit_response)
        self.instances.append(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        return None


def _image_profiles() -> dict[str, ImageModelConfig]:
    return {
        "dall-e": ImageModelConfig(
            model="dall-e-3",
            api_key="default-key",
            api_base="https://default.example/v1",
            size="1024x1024",
            response_format="b64_json",
            timeout=120,
        ),
        "flux": ImageModelConfig(
            model="flux-pro",
            api_key="flux-key",
            api_base="https://flux.example/v1",
            size="512x512",
            response_format="b64_json",
            timeout=17,
        ),
    }


def _config() -> Config:
    return Config(
        image_default_model="dall-e",
        image_models=_image_profiles(),
    )


def _event(message: Message | None = None) -> "MessageEvent":
    return cast(
        "MessageEvent",
        SimpleNamespace(
            message_id=42,
            original_message=message or Message(),
        ),
    )


def _bot() -> "Bot":
    return cast("Bot", object())


async def _run_draw(event: "MessageEvent", arg: Message) -> None:
    await llm.handle_draw(_bot(), event, arg)


def _image_segments(count: int) -> Message:
    return Message(
        [
            MessageSegment(type="image", data={"url": f"https://example/{i}.png"})
            for i in range(count)
        ]
    )


def test_image_config_defaults_and_validates_capabilities() -> None:
    profile = _image_profiles()["dall-e"]
    assert profile.capabilities == ["text_to_image", "image_to_image"]

    with pytest.raises(ValidationError, match="capabilities 不能为空"):
        ImageModelConfig(
            model="m",
            api_key="k",
            api_base="https://example/v1",
            capabilities=[],
        )

    with pytest.raises(ValidationError):
        ImageModelConfig.model_validate(
            {
                "model": "m",
                "api_key": "k",
                "api_base": "https://example/v1",
                "capabilities": ["upscale"],
            }
        )


def test_image_config_rejects_empty_mapping_and_missing_default() -> None:
    values = {
        "image_default_model": "dall-e",
        "image_models": _image_profiles(),
    }

    with pytest.raises(ValidationError, match="image_models 不能为空"):
        Config.model_validate({**values, "image_models": {}})

    with pytest.raises(ValidationError, match="image_default_model"):
        Config.model_validate({**values, "image_default_model": "missing"})


@pytest.mark.parametrize("alias", ["", "bad alias", "bad\talias", "@bad"])
def test_image_config_rejects_invalid_aliases(alias: str) -> None:
    profile = _image_profiles()["dall-e"]
    with pytest.raises(ValidationError, match="非法生图模型别名"):
        Config(
            image_default_model=alias,
            image_models={alias: profile},
        )


def test_draw_model_selector_parses_only_the_first_token(
    monkeypatch: MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr(llm, "config", config)

    assert llm._parse_draw_model_selector("a lighthouse") == (None, "a lighthouse")
    assert llm._parse_draw_model_selector("@flux a lighthouse") == (
        "flux",
        "a lighthouse",
    )
    assert llm._parse_draw_model_selector("@") == ("", "")
    assert llm._resolve_draw_profile(None) is config.image_models["dall-e"]
    assert llm._resolve_draw_profile("flux") is config.image_models["flux"]


def test_selector_without_prompt_uses_reply_text(monkeypatch: MonkeyPatch) -> None:
    config = _config()
    get_reply = AsyncMock(return_value={"raw_message": "reply lighthouse"})
    monkeypatch.setattr(llm, "config", config)
    monkeypatch.setattr(llm, "get_reply", get_reply)

    prompt, image_urls, profile = asyncio.run(
        llm._resolve_draw_request(_bot(), _event(), Message("@flux"))
    )

    assert prompt == "reply lighthouse"
    assert image_urls == []
    assert profile is config.image_models["flux"]


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("@", "未知生图模型: @(空)；可用模型: @dall-e @flux"),
        ("@missing test", "未知生图模型: @missing；可用模型: @dall-e @flux"),
    ],
)
def test_unknown_selector_finishes_before_quota(
    monkeypatch: MonkeyPatch,
    selector: str,
    expected: str,
) -> None:
    finish = AsyncMock()
    check_quota = Mock()
    consume_quota = Mock()
    processing = AsyncMock()
    get_reply = AsyncMock()
    monkeypatch.setattr(llm, "config", _config())
    monkeypatch.setattr(llm.draw, "finish", finish)
    monkeypatch.setattr(llm, "check_quota", check_quota)
    monkeypatch.setattr(llm, "consume_quota", consume_quota)
    monkeypatch.setattr(llm, "send_processing_reply", processing)
    monkeypatch.setattr(llm, "get_reply", get_reply)

    asyncio.run(_run_draw(_event(), Message(selector)))

    finish.assert_awaited_once()
    finish_call = finish.await_args
    assert finish_call is not None
    assert expected in str(finish_call.args[0])
    check_quota.assert_not_called()
    consume_quota.assert_not_called()
    processing.assert_not_awaited()
    get_reply.assert_not_awaited()


@pytest.mark.parametrize(
    ("command", "expected_alias"),
    [("a lighthouse", "dall-e"), ("@flux a lighthouse", "flux")],
)
def test_selected_profile_isolates_generation_client(
    monkeypatch: MonkeyPatch,
    command: str,
    expected_alias: str,
) -> None:
    config = _config()
    get_reply = AsyncMock(return_value=None)
    proxy_for_url = Mock(return_value=None)
    _RecordingClient.instances.clear()
    monkeypatch.setattr(llm, "config", config)
    monkeypatch.setattr(llm, "get_reply", get_reply)
    monkeypatch.setattr(images, "AsyncOpenAI", _RecordingClient)
    monkeypatch.setattr(images, "get_http_proxy_for_url", proxy_for_url)

    async def generate() -> list[str]:
        prompt, _, profile = await llm._resolve_draw_request(
            _bot(), _event(), Message(command)
        )
        return await images.image_generate(prompt, profile=profile)

    assert asyncio.run(generate()) == ["generated"]

    profile = config.image_models[expected_alias]
    client = _RecordingClient.instances[0]
    assert client.kwargs["api_key"] == profile.api_key
    assert client.kwargs["base_url"] == profile.api_base
    assert client.kwargs["timeout"] == profile.timeout
    proxy_for_url.assert_called_once_with(profile.api_base)
    client.images.generate.assert_awaited_once_with(
        model=profile.model,
        prompt="a lighthouse",
        n=1,
        size=profile.size,
        response_format=profile.response_format,
    )


def test_image_edit_downloads_reference_and_result_with_profile_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _image_profiles()["flux"]
    _RecordingClient.instances.clear()
    monkeypatch.setattr(
        _RecordingClient,
        "edit_response",
        SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="https://cdn.example/result.png")]
        ),
    )
    download = AsyncMock(
        side_effect=[
            (b"reference", "reference.png", "image/png"),
            (b"result", "result.png", "image/png"),
        ]
    )
    monkeypatch.setattr(images, "AsyncOpenAI", _RecordingClient)
    monkeypatch.setattr(images, "get_http_proxy_for_url", Mock(return_value=None))
    monkeypatch.setattr(images, "_download_image", download)

    result = asyncio.run(
        images.image_edit(
            "make it brighter",
            "https://input.example/reference.png",
            profile=profile,
        )
    )

    assert result == [base64.b64encode(b"result").decode("ascii")]
    assert download.await_args_list == [
        call("https://input.example/reference.png", timeout=profile.timeout),
        call("https://cdn.example/result.png", timeout=profile.timeout),
    ]
    client = _RecordingClient.instances[0]
    client.images.edit.assert_awaited_once_with(
        model=profile.model,
        image=("reference.png", b"reference", "image/png"),
        prompt="make it brighter",
        n=1,
        size=profile.size,
        response_format=profile.response_format,
    )


def test_over_reference_limit_finishes_before_quota(
    monkeypatch: MonkeyPatch,
) -> None:
    finish = AsyncMock()
    check_quota = Mock()
    consume_quota = Mock()
    processing = AsyncMock()
    get_reply = AsyncMock(return_value=None)
    monkeypatch.setattr(llm, "config", _config())
    monkeypatch.setattr(llm.draw, "finish", finish)
    monkeypatch.setattr(llm, "check_quota", check_quota)
    monkeypatch.setattr(llm, "consume_quota", consume_quota)
    monkeypatch.setattr(llm, "send_processing_reply", processing)
    monkeypatch.setattr(llm, "get_reply", get_reply)

    count = images.MAX_REFERENCE_IMAGES + 1
    asyncio.run(_run_draw(_event(_image_segments(count)), Message("a lighthouse")))

    finish.assert_awaited_once()
    finish_call = finish.await_args
    assert finish_call is not None
    assert f"参考图最多支持 {images.MAX_REFERENCE_IMAGES} 张" in str(
        finish_call.args[0]
    )
    check_quota.assert_not_called()
    consume_quota.assert_not_called()
    processing.assert_not_awaited()


def test_image_edit_helper_enforces_reference_limit() -> None:
    count = images.MAX_REFERENCE_IMAGES + 1
    with pytest.raises(
        images.ImageAPIError,
        match=f"参考图最多支持 {images.MAX_REFERENCE_IMAGES} 张",
    ):
        asyncio.run(
            images.image_edit(
                "edit",
                [b"raw"] * count,
                profile=_image_profiles()["dall-e"],
            )
        )


@pytest.mark.parametrize(
    ("capabilities", "image_count", "expected"),
    [
        (["image_to_image"], 0, "当前生图模型不支持文生图"),
        (["text_to_image"], 1, "当前生图模型不支持图生图"),
    ],
)
def test_unsupported_capability_finishes_before_quota(
    monkeypatch: MonkeyPatch,
    capabilities: list[str],
    image_count: int,
    expected: str,
) -> None:
    finish = AsyncMock()
    check_quota = Mock()
    consume_quota = Mock()
    processing = AsyncMock()
    get_reply = AsyncMock(return_value=None)
    profile = _image_profiles()["dall-e"].model_copy(
        update={"capabilities": capabilities}
    )
    config = Config(image_default_model="dall-e", image_models={"dall-e": profile})
    monkeypatch.setattr(llm, "config", config)
    monkeypatch.setattr(llm.draw, "finish", finish)
    monkeypatch.setattr(llm, "check_quota", check_quota)
    monkeypatch.setattr(llm, "consume_quota", consume_quota)
    monkeypatch.setattr(llm, "send_processing_reply", processing)
    monkeypatch.setattr(llm, "get_reply", get_reply)

    event = _event(_image_segments(image_count))
    asyncio.run(_run_draw(event, Message("a lighthouse")))

    finish.assert_awaited_once()
    finish_call = finish.await_args
    assert finish_call is not None
    assert expected in str(finish_call.args[0])
    check_quota.assert_not_called()
    consume_quota.assert_not_called()
    processing.assert_not_awaited()


def test_image_helpers_enforce_profile_capabilities() -> None:
    t2i_only = _image_profiles()["dall-e"].model_copy(
        update={"capabilities": ["text_to_image"]}
    )
    i2i_only = _image_profiles()["dall-e"].model_copy(
        update={"capabilities": ["image_to_image"]}
    )

    with pytest.raises(images.ImageAPIError, match="当前生图模型不支持文生图"):
        asyncio.run(images.image_generate("a lighthouse", profile=i2i_only))

    with pytest.raises(images.ImageAPIError, match="当前生图模型不支持图生图"):
        asyncio.run(images.image_edit("edit", b"raw", profile=t2i_only))
