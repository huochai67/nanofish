"""Daily quota and cooldown tracking."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from nonebot import logger, require

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

if TYPE_CHECKING:
    from pathlib import Path

_QUOTA_FILE = "quotas.json"


def _today_key() -> str:
    return datetime.now(tz=UTC).date().isoformat()


@dataclass(frozen=True, slots=True)
class QuotaResult:
    allowed: bool
    message: str | None = None
    used: int = 0
    limit: int = 0
    remaining: int = 0


class QuotaTracker:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._path: Path | None = None
        self._loaded = False

    def _file(self) -> Path:
        if self._path is None:
            self._path = store.get_plugin_data_file(_QUOTA_FILE)
        return self._path

    def load(self) -> None:
        path = self._file()
        if not path.is_file():
            self._data = {}
            self._loaded = True
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._data = raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[acl] failed to load quotas: {e}")
            self._data = {}
        self._loaded = True
        self._prune()

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        self.ensure_loaded()
        self._file().write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _prune(self) -> None:
        today = _today_key()
        stale = [k for k in self._data if k != today]
        for k in stale:
            del self._data[k]

    def _entry(self, command: str, user_id: int) -> dict[str, Any]:
        self.ensure_loaded()
        today = _today_key()
        day = self._data.setdefault(today, {})
        key = f"{command}:{user_id}"
        entry = day.get(key)
        if not isinstance(entry, dict):
            entry = {"count": 0, "last_ts": 0.0}
            day[key] = entry
        return entry

    def check(
        self,
        *,
        command: str,
        user_id: int,
        daily_limit: int,
        cooldown: float,
        unlimited: bool = False,
    ) -> QuotaResult:
        """Check without consuming. daily_limit/cooldown 0 = unlimited."""
        if unlimited:
            return QuotaResult(allowed=True, used=0, limit=0, remaining=-1)

        entry = self._entry(command, user_id)
        count = int(entry.get("count") or 0)
        last_ts = float(entry.get("last_ts") or 0.0)
        now = time.time()

        if cooldown > 0 and last_ts > 0:
            elapsed = now - last_ts
            if elapsed < cooldown:
                wait = int(cooldown - elapsed) + 1
                remaining = max(daily_limit - count, 0) if daily_limit > 0 else -1
                return QuotaResult(
                    allowed=False,
                    message=f"/{command} 冷却中，请 {wait} 秒后再试",
                    used=count,
                    limit=daily_limit,
                    remaining=remaining,
                )

        if daily_limit > 0 and count >= daily_limit:
            return QuotaResult(
                allowed=False,
                message=(
                    f"今日 /{command} 额度已用完（{count}/{daily_limit}），UTC 零点重置"
                ),
                used=count,
                limit=daily_limit,
                remaining=0,
            )

        remaining = (daily_limit - count) if daily_limit > 0 else -1
        return QuotaResult(
            allowed=True,
            used=count,
            limit=daily_limit,
            remaining=remaining,
        )

    def consume(
        self,
        *,
        command: str,
        user_id: int,
        unlimited: bool = False,
    ) -> None:
        if unlimited:
            return
        entry = self._entry(command, user_id)
        entry["count"] = int(entry.get("count") or 0) + 1
        entry["last_ts"] = time.time()
        self.save()

    def usage(self, command: str, user_id: int) -> tuple[int, float]:
        entry = self._entry(command, user_id)
        return int(entry.get("count") or 0), float(entry.get("last_ts") or 0.0)


quota_tracker = QuotaTracker()
