"""Local validation of embedded C2PA Content Credentials."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

import c2pa
from nonebot import logger

_VERIFY_SETTINGS: dict[str, object] = {
    "verify": {
        "ocsp_fetch": False,
        "remote_manifest_fetch": False,
        "verify_after_reading": True,
        "verify_timestamp_trust": True,
        "verify_trust": True,
    }
}


class C2paStatus(StrEnum):
    TRUSTED = "trusted"
    NOT_FOUND = "not_found"
    NOT_TRUSTED = "not_trusted"
    UNSUPPORTED = "unsupported"
    DOWNLOAD_FAILED = "download_failed"
    TOO_LARGE = "too_large"


@dataclass(frozen=True, slots=True)
class C2paResult:
    status: C2paStatus
    claim_generator: str | None = None

    @property
    def trusted(self) -> bool:
        return self.status is C2paStatus.TRUSTED


def _claim_generator(manifest: dict[object, object] | None) -> str | None:
    if not manifest:
        return None
    generator = manifest.get("claim_generator")
    if isinstance(generator, str) and generator:
        return generator
    infos = manifest.get("claim_generator_info")
    if isinstance(infos, list):
        for info in infos:
            if isinstance(info, dict):
                name = info.get("name")
                if isinstance(name, str) and name:
                    return name
    return None


def inspect_embedded_c2pa(
    image: bytes,
    content_type: str,
    trust_anchors: str | None = None,
) -> C2paResult:
    """Verify an image's embedded manifest against the SDK trust store."""
    try:
        settings = _VERIFY_SETTINGS.copy()
        if trust_anchors:
            settings["trust"] = {"trust_anchors": trust_anchors}
        with c2pa.Context.from_dict(settings) as context:
            reader = c2pa.Reader.try_create(
                content_type,
                BytesIO(image),
                None,
                context,
            )
            if reader is None:
                return C2paResult(C2paStatus.NOT_FOUND)
            with reader:
                manifest = reader.get_active_manifest()
                if reader.get_validation_state() != "Trusted":
                    return C2paResult(
                        C2paStatus.NOT_TRUSTED,
                        _claim_generator(manifest),
                    )
                return C2paResult(C2paStatus.TRUSTED, _claim_generator(manifest))
    except Exception as exc:  # noqa: BLE001
        logger.debug("C2PA manifest unavailable or invalid: %s", exc)
        return C2paResult(C2paStatus.NOT_FOUND)


def trusted_message(result: C2paResult) -> str:
    generator = result.claim_generator or "未知签发方"
    return f"检测到可信 C2PA 内容凭证（签发方：{generator}）"
