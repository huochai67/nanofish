from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from nonebot import get_driver, logger
from nonebot.exception import MatcherException

from .config import pconfig
from .exception import describe_error, is_retryable

T = TypeVar("T")

_MAX_BACKOFF_SECONDS = 30.0


@dataclass(slots=True)
class _Job(Generic[T]):
    factory: Callable[[], Awaitable[T]]
    future: asyncio.Future[T]
    label: str


class ParseTaskQueue:
    """限制解析任务并发数, 并在队列内对临时性错误进行重试。

    - 任务体不发送任何消息, 因此重试不会产生重复提示。
    - dedupe_key 相同的任务共享同一次执行结果。
    """

    def __init__(
        self,
        *,
        concurrency: int = 2,
        max_pending: int = 32,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ):
        self._concurrency = max(1, concurrency)
        self._max_pending = max(0, max_pending)
        self._max_attempts = max(0, max_retries) + 1
        self._retry_delay = max(0.0, retry_delay)
        self._queue: asyncio.Queue[_Job[Any]] | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    def _ensure_started(self) -> asyncio.Queue[_Job[Any]]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_pending)
            self._workers = [
                asyncio.create_task(
                    self._worker(),
                    name=f"media-parser-worker-{index}",
                )
                for index in range(self._concurrency)
            ]
        return self._queue

    async def submit(
        self,
        factory: Callable[[], Awaitable[T]],
        *,
        label: str = "parse",
        dedupe_key: str | None = None,
    ) -> T:
        """排队执行 factory; 相同 dedupe_key 的任务会共享结果"""
        queue = self._ensure_started()

        if dedupe_key is not None:
            existing = self._inflight.get(dedupe_key)
            if existing is not None:
                logger.debug(f"复用进行中的解析任务: {label}")
                return await asyncio.shield(existing)

        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        if dedupe_key is not None:
            self._inflight[dedupe_key] = future
            future.add_done_callback(
                lambda _future: self._discard_inflight(dedupe_key, future)
            )

        try:
            await queue.put(_Job(factory=factory, future=future, label=label))
        except BaseException:
            if dedupe_key is not None:
                self._discard_inflight(dedupe_key, future)
            raise

        # shield: 调用方取消等待时不影响正在执行的共享任务
        return await asyncio.shield(future)

    def _discard_inflight(
        self,
        key: str,
        future: asyncio.Future[Any],
    ) -> None:
        if self._inflight.get(key) is future:
            self._inflight.pop(key, None)

    async def _worker(self) -> None:
        queue = self._queue
        assert queue is not None

        while True:
            job = await queue.get()
            try:
                result = await self._run(job)
            except asyncio.CancelledError:
                if not job.future.done():
                    job.future.cancel()
                raise
            except Exception as error:
                if not job.future.done():
                    job.future.set_exception(error)
            else:
                if not job.future.done():
                    job.future.set_result(result)
            finally:
                queue.task_done()

    async def _run(self, job: _Job[T]) -> T:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await job.factory()
            except asyncio.CancelledError:
                raise
            except MatcherException:
                # Finished/Skipped/Paused 等控制流异常直接上抛
                raise
            except Exception as error:
                if attempt >= self._max_attempts or not is_retryable(error):
                    if attempt > 1:
                        logger.warning(
                            f"解析任务 {job.label} 第 {attempt} 次尝试失败，不再重试: "
                            f"{describe_error(error)}"
                        )
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    f"解析任务 {job.label} 第 {attempt} 次尝试失败，"
                    f"{delay:.1f}s 后重试: {describe_error(error)}"
                )
                await asyncio.sleep(delay)

        raise RuntimeError("解析任务重试循环异常结束")

    def _backoff(self, attempt: int) -> float:
        return min(self._retry_delay * (2 ** (attempt - 1)), _MAX_BACKOFF_SECONDS)

    async def shutdown(self) -> None:
        workers, self._workers = self._workers, []
        queue, self._queue = self._queue, None
        self._inflight.clear()

        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

        if queue is not None:
            while True:
                try:
                    job = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not job.future.done():
                    job.future.cancel()
                queue.task_done()


parser_queue = ParseTaskQueue(
    concurrency=pconfig.max_concurrency,
    max_pending=pconfig.queue_size,
    max_retries=pconfig.max_retries,
    retry_delay=pconfig.retry_delay,
)


@get_driver().on_shutdown
async def _shutdown_parser_queue() -> None:
    await parser_queue.shutdown()
