"""Daily quota, cooldown, and global rate-limit tracking."""

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
_RATE_KEY_PREFIX = "_rate_timestamps:"
_RATE_WINDOW_SECONDS = 60.0


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
        stale = [
            key
            for key in self._data
            if key != today and not key.startswith(_RATE_KEY_PREFIX)
        ]
        for k in stale:
            del self._data[k]
        now = time.time()
        for key in self._data:
            if key.startswith(_RATE_KEY_PREFIX):
                self._rate_timestamps(key.removeprefix(_RATE_KEY_PREFIX), now)

    def _rate_timestamps(self, command: str, now: float) -> list[float]:
        key = f"{_RATE_KEY_PREFIX}{command}"
        raw = self._data.get(key)
        timestamps = raw if isinstance(raw, list) else []
        active: list[float] = []
        for timestamp in timestamps:
            try:
                value = float(timestamp)
            except (TypeError, ValueError):
                continue
            if 0 <= now - value < _RATE_WINDOW_SECONDS:
                active.append(value)
        self._data[key] = active
        return active

    def _check_rate(
        self,
        command: str,
        per_minute: int,
        now: float,
    ) -> QuotaResult | None:
        if per_minute <= 0:
            return None
        used = len(self._rate_timestamps(command, now))
        if used >= per_minute:
            return QuotaResult(
                allowed=False,
                message=(
                    f"/{command} 每分钟请求已达上限（{used}/{per_minute}），请稍后再试"
                ),
            )
        return None

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
        per_minute: int,
        unlimited: bool = False,
    ) -> QuotaResult:
        """Check without consuming. A command rate limit applies to every user."""
        now = time.time()
        if unlimited:
            rate_result = self._check_rate(command, per_minute, now)
            return rate_result or QuotaResult(
                allowed=True,
                used=0,
                limit=0,
                remaining=-1,
            )

        entry = self._entry(command, user_id)
        count = int(entry.get("count") or 0)
        last_ts = float(entry.get("last_ts") or 0.0)

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

        rate_result = self._check_rate(command, per_minute, now)
        if rate_result is not None:
            return rate_result

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
        daily_limit: int,
        cooldown: float,
        per_minute: int,
        unlimited: bool = False,
    ) -> QuotaResult:
        """Atomically recheck and reserve quota before a costly operation."""
        result = self.check(
            command=command,
            user_id=user_id,
            daily_limit=daily_limit,
            cooldown=cooldown,
            per_minute=per_minute,
            unlimited=unlimited,
        )
        if not result.allowed:
            return result

        now = time.time()
        if not unlimited:
            entry = self._entry(command, user_id)
            entry["count"] = int(entry.get("count") or 0) + 1
            entry["last_ts"] = now
        if per_minute > 0:
            self._rate_timestamps(command, now).append(now)
        self.save()
        return result

    def usage(self, command: str, user_id: int) -> tuple[int, float]:
        entry = self._entry(command, user_id)
        return int(entry.get("count") or 0), float(entry.get("last_ts") or 0.0)


quota_tracker = QuotaTracker()
