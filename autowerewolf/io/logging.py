import json
import logging
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel

from autowerewolf.engine.state import Event, GameConfig, GameState


class GameLogLevel(str, Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    VERBOSE = "verbose"


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    category: str
    message: str
    data: dict[str, Any] = {}


class GameLogger:
    def __init__(
        self,
        game_id: str,
        log_level: GameLogLevel = GameLogLevel.STANDARD,
        output_path: Optional[Path] = None,
        enable_console: bool = True,
        enable_file: bool = False,
    ):
        self.game_id = game_id
        self.log_level = log_level
        self.output_path = output_path
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.entries: list[LogEntry] = []
        
        self._logger = logging.getLogger(f"autowerewolf.game.{game_id}")
        self._logger.setLevel(logging.DEBUG)
        
        if not self._logger.handlers:
            if enable_console:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
                )
                self._logger.addHandler(console_handler)
            
            if enable_file and output_path:
                file_handler = logging.FileHandler(output_path / f"{game_id}.log")
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
                )
                self._logger.addHandler(file_handler)

    def _should_log(self, required_level: GameLogLevel) -> bool:
        levels = [GameLogLevel.MINIMAL, GameLogLevel.STANDARD, GameLogLevel.VERBOSE]
        return levels.index(self.log_level) >= levels.index(required_level)

    def _add_entry(
        self,
        level: str,
        category: str,
        message: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            category=category,
            message=message,
            data=data or {},
        )
        self.entries.append(entry)

    def log_game_start(self, config: GameConfig, players: list[dict[str, Any]]) -> None:
        self._add_entry(
            level="INFO",
            category="game",
            message="Game started",
            data={"config": config.model_dump(), "players": players},
        )
        self._logger.info(f"Game {self.game_id} started with {len(players)} players")

    def log_phase_change(
        self, day_number: int, phase: str, alive_count: int
    ) -> None:
        msg = f"Day {day_number} - {phase.upper()} phase"
        self._add_entry(
            level="INFO",
            category="phase",
            message=msg,
            data={"day": day_number, "phase": phase, "alive_players": alive_count},
        )
        if self._should_log(GameLogLevel.STANDARD):
            self._logger.info(f"{msg} ({alive_count} players alive)")

    def log_event(self, event: Event, game_state: GameState) -> None:
        event_data = self._redact_event(event, game_state)
        
        self._add_entry(
            level="DEBUG",
            category="event",
            message=f"Event: {event.event_type.value}",
            data=event_data,
        )
        
        if self._should_log(GameLogLevel.VERBOSE):
            self._logger.debug(f"Event: {event.event_type.value}")

    def log_action(
        self,
        actor_id: str,
        action_type: str,
        target_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._add_entry(
            level="DEBUG",
            category="action",
            message=f"Action: {action_type}",
            data={
                "actor_id": actor_id,
                "action_type": action_type,
                "target_id": target_id,
                **(details or {}),
            },
        )
        if self._should_log(GameLogLevel.VERBOSE):
            self._logger.debug(f"Action: {action_type} by {actor_id}")

    def log_agent_prompt(
        self,
        player_id: str,
        role: str,
        prompt_type: str,
        prompt_content: str,
    ) -> None:
        if not self._should_log(GameLogLevel.VERBOSE):
            return
        
        redacted_prompt = self._redact_prompt(prompt_content)
        
        self._add_entry(
            level="DEBUG",
            category="agent_prompt",
            message=f"Agent prompt: {prompt_type}",
            data={
                "player_id": player_id,
                "role": role,
                "prompt_type": prompt_type,
                "prompt": redacted_prompt,
            },
        )

    def log_agent_response(
        self,
        player_id: str,
        role: str,
        response_type: str,
        response_content: Union[str, dict[str, Any]],
    ) -> None:
        if not self._should_log(GameLogLevel.VERBOSE):
            return
        
        self._add_entry(
            level="DEBUG",
            category="agent_response",
            message=f"Agent response: {response_type}",
            data={
                "player_id": player_id,
                "role": role,
                "response_type": response_type,
                "response": response_content,
            },
        )

    def log_death(
        self,
        player_id: str,
        player_name: str,
        role: str,
        cause: str,
    ) -> None:
        self._add_entry(
            level="INFO",
            category="death",
            message=f"{player_name} died ({cause})",
            data={
                "player_id": player_id,
                "player_name": player_name,
                "role": role,
                "cause": cause,
            },
        )
        if self._should_log(GameLogLevel.STANDARD):
            self._logger.info(f"{player_name} died ({cause})")

    def log_vote_result(
        self,
        votes: dict[str, str],
        vote_counts: dict[str, float],
        lynched_id: Optional[str],
        lynched_name: Optional[str],
    ) -> None:
        self._add_entry(
            level="INFO",
            category="vote",
            message="Vote completed",
            data={
                "votes": votes,
                "vote_counts": vote_counts,
                "lynched_id": lynched_id,
                "lynched_name": lynched_name,
            },
        )
        if self._should_log(GameLogLevel.STANDARD):
            if lynched_name:
                self._logger.info(f"Vote result: {lynched_name} was lynched")
            else:
                self._logger.info("Vote result: No one was lynched")

    def log_game_end(
        self,
        winning_team: str,
        final_day: int,
        survivors: list[dict[str, Any]],
    ) -> None:
        self._add_entry(
            level="INFO",
            category="game",
            message=f"Game ended - {winning_team} wins",
            data={
                "winning_team": winning_team,
                "final_day": final_day,
                "survivors": survivors,
            },
        )
        self._logger.info(f"Game ended on Day {final_day}: {winning_team.upper()} wins!")

    def log_error(
        self,
        message: str,
        error_type: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._add_entry(
            level="ERROR",
            category="error",
            message=message,
            data={"error_type": error_type, **(details or {})},
        )
        self._logger.error(f"{error_type}: {message}")

    def _redact_event(self, event: Event, game_state: GameState) -> dict[str, Any]:
        data = {
            "event_type": event.event_type.value,
            "day_number": event.day_number,
            "phase": event.phase.value,
            "public": event.public,
        }
        
        if event.actor_id:
            actor = game_state.get_player(event.actor_id)
            data["actor"] = actor.name if actor else event.actor_id
        
        if event.target_id:
            target = game_state.get_player(event.target_id)
            data["target"] = target.name if target else event.target_id
        
        safe_data = {}
        for k, v in event.data.items():
            if k not in ("seer_result", "role"):
                safe_data[k] = v
        data["data"] = safe_data
        
        return data

    def _redact_prompt(self, prompt: str) -> str:
        if len(prompt) > 500:
            return prompt[:500] + "... [truncated]"
        return prompt

    def get_entries(self, category: Optional[str] = None) -> list[LogEntry]:
        if category:
            return [e for e in self.entries if e.category == category]
        return self.entries.copy()

    def export_json(self) -> str:
        return json.dumps(
            [e.model_dump(mode="json") for e in self.entries],
            indent=2,
            ensure_ascii=False,
            default=str,
        )


def create_game_logger(
    game_id: Optional[str] = None,
    log_level: GameLogLevel = GameLogLevel.STANDARD,
    output_path: Optional[Union[str, Path]] = None,
    enable_console: bool = True,
    enable_file: bool = False,
) -> GameLogger:
    if game_id is None:
        game_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    path = Path(output_path) if output_path else None
    
    return GameLogger(
        game_id=game_id,
        log_level=log_level,
        output_path=path,
        enable_console=enable_console,
        enable_file=enable_file,
    )
