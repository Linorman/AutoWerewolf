import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from autowerewolf.agents.human import HumanPlayerAgent, WebInputHandler
from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig
from autowerewolf.config.performance import PERFORMANCE_PRESETS
from autowerewolf.engine.roles import Role, RoleSet, WinningTeam
from autowerewolf.engine.state import Event, GameConfig, GameState
from autowerewolf.io.persistence import save_game_log
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator, GameResult
from autowerewolf.web.schemas import (
    ActionSubmitRequest,
    CreateGameRequest,
    EventResponse,
    GameMode,
    GameStateResponse,
    PlayerViewResponse,
    WebGameConfig,
    WebModelConfig,
)

logger = logging.getLogger(__name__)


class GameSession:
    def __init__(
        self,
        game_id: str,
        mode: GameMode,
        model_config: WebModelConfig,
        game_config: WebGameConfig,
        player_seat: Optional[int] = None,
        player_name: Optional[str] = None,
    ):
        self.game_id = game_id
        self.mode = mode
        self.model_config = model_config
        self.game_config = game_config
        self.player_seat = player_seat
        self.player_name = player_name or "Human Player"
        self.status = "created"
        self.created_at = datetime.now()
        self.orchestrator: Optional[GameOrchestrator] = None
        self.game_state: Optional[GameState] = None
        self.result: Optional[GameResult] = None
        self.events: List[Event] = []
        self.narrations: List[str] = []
        self._game_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._human_input_handler: Optional[WebInputHandler] = None
        self._human_agent: Optional[HumanPlayerAgent] = None
        self._realtime_event_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

    def _create_model_config(self) -> AgentModelConfig:
        backend = ModelBackend.OLLAMA if self.model_config.backend == "ollama" else ModelBackend.API
        default_config = ModelConfig(
            backend=backend,
            model_name=self.model_config.model_name,
            api_base=self.model_config.api_base,
            api_key=self.model_config.api_key,
            ollama_base_url=self.model_config.ollama_base_url,
            temperature=self.model_config.temperature,
            max_tokens=self.model_config.max_tokens,
        )
        return AgentModelConfig(default=default_config)

    def _create_game_config(self) -> GameConfig:
        role_set = RoleSet.A if self.game_config.role_set == "A" else RoleSet.B
        return GameConfig(
            num_players=12,
            role_set=role_set,
            random_seed=self.game_config.random_seed,
        )

    def _on_event(self, event: Event, game_state: GameState) -> None:
        with self._lock:
            self.events.append(event)
            self.game_state = game_state
        
        actor_name = None
        target_name = None
        if event.actor_id:
            actor = game_state.get_player(event.actor_id)
            if actor:
                actor_name = actor.name
        if event.target_id:
            target = game_state.get_player(event.target_id)
            if target:
                target_name = target.name
        
        description = self._describe_event(event, actor_name, target_name)
        
        event_response = EventResponse(
            event_type=event.event_type.value,
            day_number=event.day_number,
            phase=event.phase.value,
            actor_id=event.actor_id,
            actor_name=actor_name,
            target_id=event.target_id,
            target_name=target_name,
            data=event.data or {},
            public=event.public,
            description=description,
        )
        
        state_response = self._build_state_response_from_game_state(game_state)
        
        self._realtime_event_queue.put({
            "type": "event",
            "event": event_response,
            "state": state_response,
        })

    def _on_narration(self, narration: str) -> None:
        with self._lock:
            self.narrations.append(narration)
        
        self._realtime_event_queue.put({
            "type": "narration",
            "content": narration,
        })

    def _build_state_response_from_game_state(self, state: GameState) -> Optional[Dict[str, Any]]:
        if state is None:
            return None
        
        players_data = []
        for p in state.players:
            role_visible = self.mode == GameMode.WATCH or self.status == "completed"
            players_data.append({
                "id": p.id,
                "name": p.name,
                "seat_number": p.seat_number,
                "is_alive": p.is_alive,
                "is_sheriff": p.is_sheriff,
                "role": p.role.value if role_visible else "hidden",
                "alignment": p.alignment.value if role_visible else "hidden",
            })
        
        winning = None
        if state.winning_team != WinningTeam.NONE:
            winning = state.winning_team.value
        
        return {
            "game_id": self.game_id,
            "status": self.status,
            "day_number": state.day_number,
            "phase": state.phase.value,
            "players": players_data,
            "sheriff_id": state.sheriff_id,
            "badge_torn": state.badge_torn,
            "winning_team": winning,
        }

    def get_realtime_event(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        try:
            return self._realtime_event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def start(self) -> None:
        if self.status != "created":
            raise RuntimeError("Game already started")
        
        self.status = "running"
        self._stop_event.clear()
        self._game_thread = threading.Thread(target=self._run_game, daemon=True)
        self._game_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.status = "stopped"
        if self.orchestrator:
            self.orchestrator.request_stop()
            logger.info(f"Game {self.game_id} stop requested")

    def _run_game(self) -> None:
        try:
            agent_model_config = self._create_model_config()
            game_config = self._create_game_config()
            perf_config = PERFORMANCE_PRESETS["standard"]
            
            default_logs_dir = Path.cwd() / "logs"
            default_logs_dir.mkdir(parents=True, exist_ok=True)
            
            self.orchestrator = GameOrchestrator(
                config=game_config,
                agent_models=agent_model_config,
                enable_console_logging=False,
                enable_file_logging=True,
                output_path=default_logs_dir,
                performance_config=perf_config,
                event_callback=self._on_event,
                narration_callback=self._on_narration,
            )
            
            self.result = self.orchestrator.run_game()
            
            # Check if game was stopped externally
            if self._stop_event.is_set() or self.orchestrator.is_stop_requested():
                with self._lock:
                    if self.orchestrator._game_state:
                        self.game_state = self.orchestrator._game_state
                self.status = "stopped"
                logger.info(f"Game {self.game_id} was stopped")
                
                self._realtime_event_queue.put({
                    "type": "game_stopped",
                    "message": "Game was stopped by user",
                })
                return
            
            if self.result:
                with self._lock:
                    self.game_state = self.result.final_state
                self.status = "completed"
                
                if self.result.game_log:
                    log_path = default_logs_dir / f"logs-{self.orchestrator._game_id}.json"
                    save_game_log(self.result.game_log, log_path)
                    logger.info(f"Game log saved to: {log_path}")
                
                self._realtime_event_queue.put({
                    "type": "game_over",
                    "winning_team": self.result.winning_team.value if self.result.winning_team else "unknown",
                })
            
        except Exception as e:
            # Check if this was due to a stop request
            if self._stop_event.is_set():
                self.status = "stopped"
                logger.info(f"Game {self.game_id} was stopped")
                self._realtime_event_queue.put({
                    "type": "game_stopped",
                    "message": "Game was stopped by user",
                })
            else:
                logger.error(f"Game error: {e}")
                self.status = "error"
                self._realtime_event_queue.put({
                    "type": "error",
                    "message": str(e),
                })

    def get_state_response(self) -> Optional[GameStateResponse]:
        with self._lock:
            state = self.game_state
        
        if state is None and self.orchestrator and self.orchestrator._game_state:
            state = self.orchestrator._game_state
        
        if state is None:
            return None
        
        players_data = []
        for p in state.players:
            role_visible = self.mode == GameMode.WATCH or self.status == "completed"
            players_data.append({
                "id": p.id,
                "name": p.name,
                "seat_number": p.seat_number,
                "is_alive": p.is_alive,
                "is_sheriff": p.is_sheriff,
                "role": p.role.value if role_visible else "hidden",
                "alignment": p.alignment.value if role_visible else "hidden",
            })
        
        winning = None
        if state.winning_team != WinningTeam.NONE:
            winning = state.winning_team.value
        
        return GameStateResponse(
            game_id=self.game_id,
            status=self.status,
            day_number=state.day_number,
            phase=state.phase.value,
            players=players_data,
            sheriff_id=state.sheriff_id,
            badge_torn=state.badge_torn,
            winning_team=winning,
        )

    def get_player_view(self, player_id: str) -> Optional[PlayerViewResponse]:
        with self._lock:
            state = self.game_state
        
        if state is None:
            return None
        
        player = state.get_player(player_id)
        if player is None:
            return None
        
        private_info = {}
        if player.role == Role.WEREWOLF:
            wolves = state.get_werewolves()
            private_info["teammates"] = [
                {"id": w.id, "name": w.name, "is_alive": w.is_alive}
                for w in wolves if w.id != player_id
            ]
        elif player.role == Role.SEER:
            private_info["check_results"] = [
                {"player_id": pid, "result": align.value}
                for pid, align in player.seer_checks
            ]
        elif player.role == Role.WITCH:
            private_info["has_cure"] = player.witch_has_cure
            private_info["has_poison"] = player.witch_has_poison
        elif player.role == Role.GUARD:
            private_info["last_protected"] = player.guard_last_protected
        elif player.role == Role.HUNTER:
            private_info["can_shoot"] = player.hunter_can_shoot
        elif player.role == Role.VILLAGE_IDIOT:
            private_info["revealed"] = player.village_idiot_revealed
        
        role_display = player.role.value.replace("_", " ").title()
        
        return PlayerViewResponse(
            player_id=player_id,
            player_name=player.name,
            role=player.role.value,
            role_display=role_display,
            private_info=private_info,
            action_required=False,
            action_type=None,
            valid_targets=[],
            action_context={},
        )

    def get_events(self, start_index: int = 0) -> List[EventResponse]:
        result = []
        with self._lock:
            events_to_process = self.events[start_index:] if self.events else []
            state = self.game_state
        
        for event in events_to_process:
            actor_name = None
            target_name = None
            
            if state:
                if event.actor_id:
                    actor = state.get_player(event.actor_id)
                    if actor:
                        actor_name = actor.name
                if event.target_id:
                    target = state.get_player(event.target_id)
                    if target:
                        target_name = target.name
            
            description = self._describe_event(event, actor_name, target_name)
            
            result.append(EventResponse(
                event_type=event.event_type.value,
                day_number=event.day_number,
                phase=event.phase.value,
                actor_id=event.actor_id,
                actor_name=actor_name,
                target_id=event.target_id,
                target_name=target_name,
                data=event.data,
                public=event.public,
                description=description,
            ))
        
        return result

    def _describe_event(
        self,
        event: Event,
        actor_name: Optional[str],
        target_name: Optional[str],
    ) -> str:
        event_type = event.event_type.value
        actor = actor_name or "Someone"
        target = target_name or "someone"
        
        if event_type == "death_announcement":
            return f"💀 {target} was found dead"
        elif event_type == "lynch":
            return f"⚖️ {target} was lynched"
        elif event_type == "speech":
            content = event.data.get("content", "") if event.data else ""
            is_last_words = event.data.get("is_last_words", False) if event.data else False
            prefix = "🗣️ [Last Words] " if is_last_words else "🗣️ "
            return f"{prefix}{actor}: {content}"
        elif event_type == "vote_cast":
            return f"🗳️ {actor} voted for {target}"
        elif event_type == "vote_result":
            return f"📊 Vote result announced"
        elif event_type == "sheriff_elected":
            return f"👑 {target} became sheriff"
        elif event_type == "sheriff_election":
            return f"🏛️ Sheriff election started"
        elif event_type == "hunter_shot":
            return f"🔫 {actor} (Hunter) shot {target}"
        elif event_type == "badge_pass":
            return f"👑 Badge passed to {target}"
        elif event_type == "badge_tear":
            return "💔 Badge was torn"
        elif event_type == "village_idiot_reveal":
            return f"🃏 {target} revealed as Village Idiot and survives"
        elif event_type == "wolf_self_explode":
            return f"💥 {actor} self-exploded as werewolf"
        elif event_type == "night_kill":
            return f"🐺 Werewolves targeted {target}"
        elif event_type == "seer_check":
            result = event.data.get("result", "") if event.data else ""
            return f"🔮 Seer checked {target}: {result}"
        elif event_type == "witch_save":
            return f"💊 Witch used cure"
        elif event_type == "witch_poison":
            return f"☠️ Witch used poison on {target}"
        elif event_type == "guard_protect":
            return f"🛡️ Guard protected {target}"
        elif event_type == "saved":
            return f"✨ {target} was saved"
        elif event_type == "no_death":
            return "☀️ Peaceful night - no deaths"
        elif event_type == "phase_change":
            return f"🌅 Phase changed"
        elif event_type == "game_start":
            return "🎮 Game started"
        elif event_type == "game_end":
            return "🏆 Game ended"
        
        return f"📝 {event_type}"

    def submit_action(self, action: ActionSubmitRequest) -> Dict[str, Any]:
        if self._human_input_handler:
            data = {
                "action_type": action.action_type,
                "target": action.target_id,
                "text": action.content,
                "value": action.extra_data.get("value"),
            }
            self._human_input_handler.set_input(data)
            return {"success": True, "message": "Action submitted"}
        
        return {"success": False, "message": "No human player in this game"}


class GameSessionManager:
    def __init__(self):
        self._sessions: Dict[str, GameSession] = {}
        self._lock = threading.Lock()

    def create_session(self, request: CreateGameRequest) -> GameSession:
        game_id = str(uuid4())[:8]
        
        session = GameSession(
            game_id=game_id,
            mode=request.mode,
            model_config=request.model_config_data,
            game_config=request.game_config,
            player_seat=request.player_seat,
            player_name=request.player_name,
        )
        
        with self._lock:
            self._sessions[game_id] = session
        
        return session

    def get_session(self, game_id: str) -> Optional[GameSession]:
        with self._lock:
            return self._sessions.get(game_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "game_id": session.game_id,
                    "mode": session.mode.value,
                    "status": session.status,
                    "created_at": session.created_at.isoformat(),
                    "day_number": session.game_state.day_number if session.game_state else 0,
                    "phase": session.game_state.phase.value if session.game_state else "unknown",
                }
                for session in self._sessions.values()
            ]

    def remove_session(self, game_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(game_id, None)
            if session:
                session.stop()
                return True
            return False

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        now = datetime.now()
        to_remove = []
        
        with self._lock:
            for game_id, session in self._sessions.items():
                age = (now - session.created_at).total_seconds() / 3600
                if age > max_age_hours and session.status in ("completed", "error", "stopped"):
                    to_remove.append(game_id)
        
        for game_id in to_remove:
            self.remove_session(game_id)
        
        return len(to_remove)


session_manager = GameSessionManager()
