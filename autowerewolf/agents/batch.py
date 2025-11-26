import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, TypeVar

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import SpeechOutput, VoteOutput
from autowerewolf.config.performance import PerformanceConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class BatchRequest(Generic[T]):
    agent: BasePlayerAgent
    game_view: GameView
    callback: Optional[Callable[[T], None]] = None


@dataclass
class BatchResult(Generic[T]):
    player_id: str
    result: Optional[T] = None
    error: Optional[Exception] = None
    duration_ms: float = 0.0


class RateLimiter:
    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self._last_request_time = 0.0
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    def wait(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.time()

    async def async_wait(self) -> None:
        if self._lock:
            async with self._lock:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)
                self._last_request_time = time.time()
        else:
            self.wait()


class BatchExecutor:
    def __init__(
        self,
        performance_config: PerformanceConfig,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.config = performance_config
        self.rate_limiter = rate_limiter
        self._executor = ThreadPoolExecutor(max_workers=self.config.batch_size)

    def _execute_single(
        self,
        agent: BasePlayerAgent,
        game_view: GameView,
        method_name: str,
    ) -> tuple[str, Any, Optional[Exception], float]:
        start = time.time()
        try:
            if self.rate_limiter:
                self.rate_limiter.wait()
            method = getattr(agent, method_name)
            result = method(game_view)
            return agent.player_id, result, None, (time.time() - start) * 1000
        except Exception as e:
            logger.warning(f"Batch execution failed for {agent.player_id}: {e}")
            return agent.player_id, None, e, (time.time() - start) * 1000

    def execute_speeches_batch(
        self,
        requests: list[tuple[BasePlayerAgent, GameView]],
    ) -> list[BatchResult[SpeechOutput]]:
        if not self.config.enable_batching or len(requests) <= 1:
            return self._execute_sequential(requests, "decide_day_speech")

        results = []
        for i in range(0, len(requests), self.config.batch_size):
            batch = requests[i:i + self.config.batch_size]
            batch_results = self._execute_parallel(batch, "decide_day_speech")
            results.extend(batch_results)
        return results

    def execute_votes_batch(
        self,
        requests: list[tuple[BasePlayerAgent, GameView]],
    ) -> list[BatchResult[VoteOutput]]:
        if not self.config.enable_batching or len(requests) <= 1:
            return self._execute_sequential(requests, "decide_vote")

        results = []
        for i in range(0, len(requests), self.config.batch_size):
            batch = requests[i:i + self.config.batch_size]
            batch_results = self._execute_parallel(batch, "decide_vote")
            results.extend(batch_results)
        return results

    def _execute_sequential(
        self,
        requests: list[tuple[BasePlayerAgent, GameView]],
        method_name: str,
    ) -> list[BatchResult]:
        results = []
        for agent, game_view in requests:
            player_id, result, error, duration = self._execute_single(
                agent, game_view, method_name
            )
            results.append(BatchResult(
                player_id=player_id,
                result=result,
                error=error,
                duration_ms=duration,
            ))
        return results

    def _execute_parallel(
        self,
        requests: list[tuple[BasePlayerAgent, GameView]],
        method_name: str,
    ) -> list[BatchResult]:
        futures = []
        for agent, game_view in requests:
            future = self._executor.submit(
                self._execute_single, agent, game_view, method_name
            )
            futures.append(future)

        results = []
        for future in futures:
            player_id, result, error, duration = future.result()
            results.append(BatchResult(
                player_id=player_id,
                result=result,
                error=error,
                duration_ms=duration,
            ))
        return results

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


def create_batch_executor(
    performance_config: PerformanceConfig,
    rate_limit_rpm: Optional[int] = None,
) -> BatchExecutor:
    rate_limiter = RateLimiter(rate_limit_rpm) if rate_limit_rpm else None
    return BatchExecutor(performance_config, rate_limiter)
