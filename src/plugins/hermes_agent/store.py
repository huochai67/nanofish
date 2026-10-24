"""SQLite mapping between QQ messages and Hermes sessions."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    scope TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    last_active_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_messages (
    bot_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    scope TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (bot_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_session
    ON agent_messages (session_id);
"""


@dataclass(frozen=True, slots=True)
class MessageRecord:
    """One QQ message mapped to a Hermes session."""

    bot_id: str
    message_id: str
    session_id: str
    profile: str
    scope: str
    role: str
    content: str


class AgentStore:
    """Persist QQ message-id to Hermes-session relations.

    Only the final assistant text and the user's command text are stored. Reasoning
    and tool-call payloads never enter this database.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._write_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @property
    def path(self) -> Path:
        return self._path

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_sync)
            self._initialized = True

    def _init_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    async def register_session(
        self,
        *,
        session_id: str,
        profile: str,
        scope: str,
        owner_id: int,
    ) -> None:
        await self._ensure_schema()
        async with self._write_lock:
            await asyncio.to_thread(
                self._register_session_sync,
                session_id,
                profile,
                scope,
                owner_id,
            )

    def _register_session_sync(
        self,
        session_id: str,
        profile: str,
        scope: str,
        owner_id: int,
    ) -> None:
        now = time.time()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    session_id, profile, scope, owner_id, created_at, last_active_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_active_at = excluded.last_active_at
                """,
                (session_id, profile, scope, owner_id, now, now),
            )

    async def record_message(
        self,
        *,
        bot_id: str,
        message_id: str,
        session_id: str,
        profile: str,
        scope: str,
        role: str,
        content: str,
    ) -> None:
        await self._ensure_schema()
        async with self._write_lock:
            await asyncio.to_thread(
                self._record_message_sync,
                bot_id,
                message_id,
                session_id,
                profile,
                scope,
                role,
                content,
            )

    async def record_messages(
        self,
        *,
        bot_id: str,
        session_id: str,
        profile: str,
        scope: str,
        messages: Iterable[tuple[str, str, str]],
    ) -> None:
        """Record ``(message_id, role, content)`` rows in one transaction."""
        rows = tuple(messages)
        if not rows:
            return
        await self._ensure_schema()
        async with self._write_lock:
            await asyncio.to_thread(
                self._record_messages_sync,
                bot_id,
                session_id,
                profile,
                scope,
                rows,
            )

    def _record_message_sync(
        self,
        bot_id: str,
        message_id: str,
        session_id: str,
        profile: str,
        scope: str,
        role: str,
        content: str,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_messages (
                    bot_id, message_id, session_id, profile, scope,
                    role, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, message_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    profile = excluded.profile,
                    scope = excluded.scope,
                    role = excluded.role,
                    content = excluded.content
                """,
                (
                    bot_id,
                    message_id,
                    session_id,
                    profile,
                    scope,
                    role,
                    content,
                    time.time(),
                ),
            )

    def _record_messages_sync(
        self,
        bot_id: str,
        session_id: str,
        profile: str,
        scope: str,
        rows: tuple[tuple[str, str, str], ...],
    ) -> None:
        now = time.time()
        with self._connection() as conn:
            conn.executemany(
                """
                INSERT INTO agent_messages (
                    bot_id, message_id, session_id, profile, scope,
                    role, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, message_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    profile = excluded.profile,
                    scope = excluded.scope,
                    role = excluded.role,
                    content = excluded.content
                """,
                (
                    (
                        bot_id,
                        message_id,
                        session_id,
                        profile,
                        scope,
                        role,
                        content,
                        now,
                    )
                    for message_id, role, content in rows
                ),
            )

    async def lookup_message(
        self,
        *,
        bot_id: str,
        message_id: str,
    ) -> MessageRecord | None:
        await self._ensure_schema()
        return await asyncio.to_thread(
            self._lookup_message_sync,
            bot_id,
            message_id,
        )

    def _lookup_message_sync(
        self,
        bot_id: str,
        message_id: str,
    ) -> MessageRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT bot_id, message_id, session_id, profile, scope, role, content
                FROM agent_messages
                WHERE bot_id = ? AND message_id = ?
                """,
                (bot_id, message_id),
            ).fetchone()
        if row is None:
            return None
        return MessageRecord(
            bot_id=str(row["bot_id"]),
            message_id=str(row["message_id"]),
            session_id=str(row["session_id"]),
            profile=str(row["profile"]),
            scope=str(row["scope"]),
            role=str(row["role"]),
            content=str(row["content"]),
        )


__all__ = ["AgentStore", "MessageRecord"]
