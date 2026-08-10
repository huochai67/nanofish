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
        model="chat-model",
        openai_api_key="chat-key",
        openai_api_base="https://chat.example/v1",
        image_default_model="dall-e",
        image_models=_image_profiles(),
    )


def _grok_profile() -> ImageModelConfig:
    return ImageModelConfig(
        model="grok-imagine-image-quality",
        api_key="grok-key",
        api_base="https://api.x.ai/v1",
        backend="grok",
        aspect_ratio="1:1",
        resolution="1k",
        response_format="b64_json",
        timeout=42,
    )


def _gemini_profile() -> ImageModelConfig:
    return ImageModelConfig(
        model="gemini-3.1-flash-image",
        api_key="gemini-key",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        backend="gemini",
        aspect_ratio="1:1",
        resolution="1K",
        timeout=42,
    )


def _config_with(alias: str, profile: ImageModelConfig) -> Config:
    return Config(
        model="chat-model",
        openai_api_key="chat-key",
        openai_api_base="https://chat.example/v1",
        image_default_model=alias,
        image_models={alias: profile},
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


def _json_response(payload: object) -> SimpleNamespace:
    return SimpleNamespace(json=lambda: payload)


def _invalid_json_response() -> Mock:
    return Mock(json=Mock(side_effect=ValueError("bad json")))


GROK_MAX_REFERENCE_IMAGES = 3
GEMINI_MAX_REFERENCE_IMAGES = 14


def _image_segments(count: int) -> Message:
    return Message(
        [
            MessageSegment(type="image", data={"url": f"https://example/{i}.png"})
            for i in range(count)
        ]
    )


def test_image_config_defaults_backend_to_openai() -> None:
    assert _image_profiles()["dall-e"].backend == "openai"


def test_image_config_rejects_unknown_backend() -> None:
    with pytest.raises(ValidationError, match="'openai', 'grok' or 'gemini'"):
        ImageModelConfig.model_validate(
            {
                "model": "m",
                "api_key": "k",
                "api_base": "https://example/v1",
                "backend": "anthropic",
            }
        )


@pytest.mark.parametrize("field", ["aspect_ratio", "resolution"])
def test_openai_profile_rejects_aspect_ratio_and_resolution(field: str) -> None:
    profile = _image_profiles()["dall-e"].model_copy(update={field: "1:1"})
    with pytest.raises(ValidationError, match="openai 后端不支持"):
        _config_with("dall-e", profile)


def test_grok_profile_rejects_size() -> None:
    profile = _grok_profile().model_copy(update={"size": "1024x1024"})
    with pytest.raises(ValidationError, match="grok 后端不支持 size"):
        _config_with("grok", profile)


def test_grok_profile_rejects_invalid_response_format() -> None:
    profile = _grok_profile().model_copy(update={"response_format": "json"})
    with pytest.raises(ValidationError, match="grok 后端 response_format"):
        _config_with("grok", profile)


def test_grok_profile_allows_url_response_format() -> None:
    profile = _grok_profile().model_copy(update={"response_format": "url"})
    assert _config_with("grok", profile).image_models["grok"].response_format == "url"


@pytest.mark.parametrize("backend", ["grok", "gemini"])
def test_non_openai_profiles_reject_size(backend: str) -> None:
    profile = (
        _grok_profile() if backend == "grok" else _gemini_profile()
    ).model_copy(update={"size": "1024x1024"})
    with pytest.raises(ValidationError, match=rf"{backend} 后端不支持 size"):
        _config_with(backend, profile)


def test_gemini_profile_rejects_url_response_format() -> None:
    profile = _gemini_profile().model_copy(update={"response_format": "url"})
    with pytest.raises(ValidationError, match="gemini 后端 response_format"):
        _config_with("gemini", profile)


def test_max_reference_images_per_backend() -> None:
    assert images.max_reference_images(_image_profiles()["dall-e"]) == (
        images.MAX_REFERENCE_IMAGES
    )
    assert images.max_reference_images(_grok_profile()) == GROK_MAX_REFERENCE_IMAGES
    assert (
        images.max_reference_images(_gemini_profile()) == GEMINI_MAX_REFERENCE_IMAGES
    )


def test_image_config_rejects_empty_mapping_and_missing_default() -> None:
    values = {
        "model": "chat-model",
        "openai_api_key": "chat-key",
        "openai_api_base": "https://chat.example/v1",
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
            model="chat-model",
            openai_api_key="chat-key",
            openai_api_base="https://chat.example/v1",
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


def test_grok_generation_posts_json_to_images_generations(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _grok_profile()
    http_post = AsyncMock(
        return_value=_json_response({"data": [{"b64_json": "grok-generated"}]})
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(
        images.image_generate("a lighthouse", profile=profile)
    )

    assert result == ["grok-generated"]
    call_ = http_post.await_args
    assert call_ is not None
    assert call_.args[0] == "https://api.x.ai/v1/images/generations"
    assert call_.kwargs["headers"] == {"Authorization": "Bearer grok-key"}
    assert call_.kwargs["timeout"] == profile.timeout
    assert call_.kwargs["json"] == {
        "model": profile.model,
        "prompt": "a lighthouse",
        "n": 1,
        "response_format": "b64_json",
        "aspect_ratio": "1:1",
        "resolution": "1k",
    }


def test_grok_generation_omits_empty_output_options(monkeypatch: MonkeyPatch) -> None:
    profile = _grok_profile().model_copy(
        update={
            "response_format": None,
            "aspect_ratio": None,
            "resolution": None,
        }
    )
    http_post = AsyncMock(
        return_value=_json_response({"data": [{"url": "https://cdn.example/r.png"}]})
    )
    download = AsyncMock(return_value=(b"result", "result.png", "image/png"))
    monkeypatch.setattr(images, "http_post", http_post)
    monkeypatch.setattr(images, "_download_image", download)

    result = asyncio.run(images.image_generate("a lighthouse", profile=profile))

    assert result == [base64.b64encode(b"result").decode("ascii")]
    call_ = http_post.await_args
    assert call_ is not None
    assert call_.kwargs["json"] == {
        "model": profile.model,
        "prompt": "a lighthouse",
        "n": 1,
    }
    download.assert_awaited_once_with(
        "https://cdn.example/r.png", timeout=profile.timeout
    )


def test_grok_edit_single_image_uses_root_image_field(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _grok_profile()
    http_post = AsyncMock(
        return_value=_json_response({"data": [{"b64_json": "edited"}]})
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(
        images.image_edit("make it bright", b"raw", profile=profile)
    )

    assert result == ["edited"]
    call_ = http_post.await_args
    assert call_ is not None
    assert call_.args[0] == "https://api.x.ai/v1/images/edits"
    assert call_.kwargs["json"]["image"] == {
        "url": "data:image/png;base64,cmF3"
    }
    assert "images" not in call_.kwargs["json"]


def test_grok_edit_two_images_uses_ordered_images_field(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _grok_profile()
    http_post = AsyncMock(
        return_value=_json_response({"data": [{"b64_json": "edited"}]})
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(
        images.image_edit("make it bright", [b"raw1", b"raw2"], profile=profile)
    )

    assert result == ["edited"]
    call_ = http_post.await_args
    assert call_ is not None
    expected = [
        {"url": f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"}
        for data in (b"raw1", b"raw2")
    ]
    assert call_.kwargs["json"]["images"] == expected
    assert "image" not in call_.kwargs["json"]


@pytest.mark.parametrize(
    "response",
    [
        _invalid_json_response(),
        _json_response([1, 2]),
        _json_response({"data": []}),
    ],
)
def test_grok_generation_rejects_unparseable_responses(
    monkeypatch: MonkeyPatch,
    response: object,
) -> None:
    http_post = AsyncMock(return_value=response)
    monkeypatch.setattr(images, "http_post", http_post)

    with pytest.raises(images.ImageAPIError, match="生图 API 返回无法解析的图片数据"):
        asyncio.run(images.image_generate("a lighthouse", profile=_grok_profile()))


def test_gemini_generation_posts_interactions_with_stateless_store(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _gemini_profile()
    http_post = AsyncMock(
        return_value=_json_response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "text", "text": "done"},
                            {"type": "image", "data": "img-one"},
                            {"type": "image", "data": ""},
                        ],
                    },
                    {
                        "type": "user_tool_use",
                        "content": [{"type": "image", "data": "img-ignored"}],
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(
        images.image_generate("a lighthouse", profile=profile)
    )

    assert result == ["img-one"]
    call_ = http_post.await_args
    assert call_ is not None
    assert (
        call_.args[0]
        == "https://generativelanguage.googleapis.com/v1beta/interactions"
    )
    assert call_.kwargs["headers"] == {"x-goog-api-key": "gemini-key"}
    assert call_.kwargs["timeout"] == profile.timeout
    assert call_.kwargs["json"] == {
        "model": profile.model,
        "input": [{"type": "text", "text": "a lighthouse"}],
        "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"},
        "store": False,
    }


def test_gemini_generation_minimal_response_format(monkeypatch: MonkeyPatch) -> None:
    profile = _gemini_profile().model_copy(
        update={"aspect_ratio": None, "resolution": None}
    )
    http_post = AsyncMock(
        return_value=_json_response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "image", "data": "img"}],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(images.image_generate("a lighthouse", profile=profile))

    assert result == ["img"]
    call_ = http_post.await_args
    assert call_ is not None
    assert call_.kwargs["json"]["response_format"] == {"type": "image"}


def test_gemini_edit_puts_text_first_then_images_in_order(
    monkeypatch: MonkeyPatch,
) -> None:
    profile = _gemini_profile()
    http_post = AsyncMock(
        return_value=_json_response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "image", "data": "img-1"},
                            {"type": "image", "data": "img-2"},
                        ],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(images, "http_post", http_post)

    result = asyncio.run(
        images.image_edit("make it bright", [b"raw1", b"raw2"], profile=profile)
    )

    assert result == ["img-1", "img-2"]
    call_ = http_post.await_args
    assert call_ is not None
    assert call_.kwargs["json"]["store"] is False
    assert call_.kwargs["json"]["input"] == [
        {"type": "text", "text": "make it bright"},
        {
            "type": "image",
            "mime_type": "image/png",
            "data": base64.b64encode(b"raw1").decode("ascii"),
        },
        {
            "type": "image",
            "mime_type": "image/png",
            "data": base64.b64encode(b"raw2").decode("ascii"),
        },
    ]


def test_gemini_request_raises_when_no_image_output(
    monkeypatch: MonkeyPatch,
) -> None:
    http_post = AsyncMock(
        return_value=_json_response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "ok"}],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(images, "http_post", http_post)

    with pytest.raises(images.ImageAPIError, match="生图 API 未返回图片"):
        asyncio.run(images.image_generate("a lighthouse", profile=_gemini_profile()))


@pytest.mark.parametrize(
    ("backend", "profile", "count", "expected"),
    [
        ("grok", _grok_profile(), 4, "当前生图后端最多支持 3 张参考图"),
        ("gemini", _gemini_profile(), 15, "当前生图后端最多支持 14 张参考图"),
    ],
)
def test_over_vendor_limit_finishes_before_quota(
    monkeypatch: MonkeyPatch,
    backend: str,
    profile: ImageModelConfig,
    count: int,
    expected: str,
) -> None:
    finish = AsyncMock()
    check_quota = Mock()
    consume_quota = Mock()
    processing = AsyncMock()
    get_reply = AsyncMock(return_value=None)
    monkeypatch.setattr(llm, "config", _config_with(backend, profile))
    monkeypatch.setattr(llm.draw, "finish", finish)
    monkeypatch.setattr(llm, "check_quota", check_quota)
    monkeypatch.setattr(llm, "consume_quota", consume_quota)
    monkeypatch.setattr(llm, "send_processing_reply", processing)
    monkeypatch.setattr(llm, "get_reply", get_reply)

    asyncio.run(_run_draw(_event(_image_segments(count)), Message("a lighthouse")))

    finish.assert_awaited_once()
    finish_call = finish.await_args
    assert finish_call is not None
    assert expected in str(finish_call.args[0])
    check_quota.assert_not_called()
    consume_quota.assert_not_called()
    processing.assert_not_awaited()


@pytest.mark.parametrize(
    ("profile", "count", "expected"),
    [
        (_grok_profile(), 4, "当前生图后端最多支持 3 张参考图"),
        (_gemini_profile(), 15, "当前生图后端最多支持 14 张参考图"),
    ],
)
def test_image_edit_helper_enforces_vendor_limit(
    profile: ImageModelConfig,
    count: int,
    expected: str,
) -> None:
    with pytest.raises(images.ImageAPIError, match=expected):
        asyncio.run(
            images.image_edit(
                "edit",
                [b"raw"] * count,
                profile=profile,
            )
        )
