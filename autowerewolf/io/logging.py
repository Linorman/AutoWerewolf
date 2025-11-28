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


class LogCategory(str, Enum):
    GAME = "game"
    PHASE = "phase"
    EVENT = "event"
    ACTION = "action"
    SPEECH = "speech"
    VOTE = "vote"
    DEATH = "death"
    MODEL = "model"
    AGENT = "agent"
    ERROR = "error"


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
        self._logger.propagate = False
        
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)
        
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
            )
            self._logger.addHandler(console_handler)
        
        if enable_file and output_path:
            file_handler = logging.FileHandler(output_path / f"{game_id}.log", encoding="utf-8")
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
            category=LogCategory.GAME.value,
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
            category=LogCategory.PHASE.value,
            message=msg,
            data={"day": day_number, "phase": phase, "alive_players": alive_count},
        )
        if self._should_log(GameLogLevel.STANDARD):
            self._logger.info(f"{msg} ({alive_count} players alive)")

    def log_event(self, event: Event, game_state: GameState) -> None:
        event_data = self._format_event_data(event, game_state)
        event_desc = self._get_event_description(event, game_state)
        
        self._add_entry(
            level="INFO" if event.public else "DEBUG",
            category=LogCategory.EVENT.value,
            message=event_desc,
            data=event_data,
        )
        
        if event.public and self._should_log(GameLogLevel.STANDARD):
            self._logger.info(event_desc)
        elif self._should_log(GameLogLevel.VERBOSE):
            self._logger.debug(event_desc)

    def log_action(
        self,
        actor_id: str,
        action_type: str,
        target_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._add_entry(
            level="DEBUG",
            category=LogCategory.ACTION.value,
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

    def log_speech(
        self,
        player_id: str,
        player_name: str,
        day_number: int,
        content: str,
        speech_type: str = "day_speech",
    ) -> None:
        self._add_entry(
            level="INFO",
            category=LogCategory.SPEECH.value,
            message=f"{player_name}: {content[:100]}..." if len(content) > 100 else f"{player_name}: {content}",
            data={
                "player_id": player_id,
                "player_name": player_name,
                "day_number": day_number,
                "speech_type": speech_type,
                "content": content,
            },
        )
        if self._should_log(GameLogLevel.STANDARD):
            preview = content[:80] + "..." if len(content) > 80 else content
            self._logger.info(f"[Speech] {player_name}: {preview}")

    def log_vote(
        self,
        voter_id: str,
        voter_name: str,
        target_id: Optional[str],
        target_name: Optional[str],
        day_number: int,
    ) -> None:
        if target_name:
            msg = f"{voter_name} voted for {target_name}"
        else:
            msg = f"{voter_name} abstained"
        
        self._add_entry(
            level="INFO",
            category=LogCategory.VOTE.value,
            message=msg,
            data={
                "voter_id": voter_id,
                "voter_name": voter_name,
                "target_id": target_id,
                "target_name": target_name,
                "day_number": day_number,
            },
        )
        if self._should_log(GameLogLevel.STANDARD):
            self._logger.info(f"[Vote] {msg}")

    def log_night_action(
        self,
        actor_id: str,
        actor_name: str,
        role: str,
        action_type: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        msg = f"{role} ({actor_name}) performed {action_type}"
        if target_name:
            msg += f" on {target_name}"
        
        self._add_entry(
            level="DEBUG",
            category=LogCategory.ACTION.value,
            message=msg,
            data={
                "actor_id": actor_id,
                "actor_name": actor_name,
                "role": role,
                "action_type": action_type,
                "target_id": target_id,
                "target_name": target_name,
                "result": result,
            },
        )
        if self._should_log(GameLogLevel.VERBOSE):
            self._logger.debug(f"[Night] {msg}")

    def log_model_request(
        self,
        player_id: str,
        request_type: str,
        model_name: str,
        tokens_used: Optional[int] = None,
        latency_ms: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        if not self._should_log(GameLogLevel.VERBOSE):
            return
        
        self._add_entry(
            level="DEBUG",
            category=LogCategory.MODEL.value,
            message=f"Model request: {request_type}",
            data={
                "player_id": player_id,
                "request_type": request_type,
                "model_name": model_name,
                "tokens_used": tokens_used,
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
            },
        )
        if success:
            self._logger.debug(f"[Model] {request_type} for {player_id} ({model_name})")
        else:
            self._logger.debug(f"[Model] {request_type} failed for {player_id}: {error}")

    def log_agent_prompt(
        self,
        player_id: str,
        role: str,
        prompt_type: str,
        prompt_content: str,
    ) -> None:
        if not self._should_log(GameLogLevel.VERBOSE):
            return
        
        redacted_prompt = self._truncate_text(prompt_content, 500)
        
        self._add_entry(
            level="DEBUG",
            category=LogCategory.AGENT.value,
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
            category=LogCategory.AGENT.value,
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
            category=LogCategory.DEATH.value,
            message=f"{player_name} died ({cause})",
            data={
                "player_id": player_id,
                "player_name": player_name,
                "role": role,
                "cause": cause,
            },
        )
        if self._should_log(GameLogLevel.STANDARD):
            self._logger.info(f"[Death] {player_name} died ({cause})")

    def log_vote_result(
        self,
        votes: dict[str, str],
        vote_counts: dict[str, float],
        lynched_id: Optional[str],
        lynched_name: Optional[str],
    ) -> None:
        self._add_entry(
            level="INFO",
            category=LogCategory.VOTE.value,
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
                self._logger.info(f"[Vote Result] {lynched_name} was lynched")
            else:
                self._logger.info("[Vote Result] No one was lynched")

    def log_game_end(
        self,
        winning_team: str,
        final_day: int,
        survivors: list[dict[str, Any]],
    ) -> None:
        self._add_entry(
            level="INFO",
            category=LogCategory.GAME.value,
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
            category=LogCategory.ERROR.value,
            message=message,
            data={"error_type": error_type, **(details or {})},
        )
        self._logger.error(f"[Error] {error_type}: {message}")

    def _format_event_data(self, event: Event, game_state: GameState) -> dict[str, Any]:
        data = {
            "event_type": event.event_type.value,
            "day_number": event.day_number,
            "phase": event.phase.value,
            "public": event.public,
            "timestamp": event.timestamp.isoformat(),
        }
        
        if event.actor_id:
            actor = game_state.get_player(event.actor_id)
            data["actor_id"] = event.actor_id
            data["actor_name"] = actor.name if actor else "Unknown"
        
        if event.target_id:
            target = game_state.get_player(event.target_id)
            data["target_id"] = event.target_id
            data["target_name"] = target.name if target else "Unknown"
        
        if event.data:
            data["extra"] = event.data
        
        return data

    def _get_event_description(self, event: Event, game_state: GameState) -> str:
        actor = game_state.get_player(event.actor_id) if event.actor_id else None
        target = game_state.get_player(event.target_id) if event.target_id else None
        actor_name = actor.name if actor else "Unknown"
        target_name = target.name if target else "Unknown"
        
        event_type = event.event_type.value
        
        descriptions = {
            "game_start": "Game started",
            "game_end": f"Game ended - {event.data.get('winning_team', 'unknown')} wins",
            "phase_change": f"Phase changed to {event.data.get('new_phase', 'unknown')}",
            "night_kill": f"Werewolves targeted {target_name}",
            "seer_check": f"Seer checked {target_name}",
            "witch_save": f"Witch saved {target_name}",
            "witch_poison": f"Witch poisoned {target_name}",
            "guard_protect": f"Guard protected {target_name}",
            "death_announcement": f"{target_name} was found dead",
            "speech": f"{actor_name} gave a speech",
            "vote_cast": f"{actor_name} voted for {target_name}",
            "vote_result": "Vote concluded",
            "lynch": f"{target_name} was lynched",
            "last_words": f"{actor_name} gave last words",
            "sheriff_election": "Sheriff election started",
            "sheriff_campaign_speech": f"{actor_name} campaigned for sheriff",
            "sheriff_vote": f"{actor_name} voted for sheriff",
            "sheriff_elected": f"{target_name} was elected sheriff",
            "badge_pass": f"Sheriff badge passed to {target_name}",
            "badge_tear": "Sheriff badge was torn",
            "hunter_shot": f"Hunter shot {target_name}",
            "village_idiot_reveal": f"{target_name} was revealed as Village Idiot",
            "wolf_self_explode": f"{actor_name} self-exploded",
            "no_death": "No one died",
            "saved": f"{target_name} was saved",
        }
        
        return f"[Event] {descriptions.get(event_type, f'{event_type}: {actor_name} -> {target_name}')}"

    def _truncate_text(self, text: str, max_length: int = 500) -> str:
        if len(text) > max_length:
            return text[:max_length] + "... [truncated]"
        return text

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
