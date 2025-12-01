import logging
import queue
import threading
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from autowerewolf.agents.prompts import Language, set_language
from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig, OutputCorrectorConfig
from autowerewolf.config.performance import LanguageSetting, PerformanceConfig, PERFORMANCE_PRESETS
from autowerewolf.engine.roles import Role, RoleSet, WinningTeam
from autowerewolf.engine.state import Event, GameConfig, GameState
from autowerewolf.io.persistence import save_game_log
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator, GameResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class StreamlitModelConfig:
    backend: str = "ollama"
    model_name: str = "qwen3:4b-instruct-2507-q4_K_M"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    enable_corrector: bool = True
    corrector_max_retries: int = 2


@dataclass 
class StreamlitGameConfig:
    role_set: str = "A"
    random_seed: Optional[int] = None
    language: str = "en"


@dataclass
class StreamlitCorrectorConfig:
    enabled: bool = True
    max_retries: int = 2
    use_separate_model: bool = False
    corrector_backend: Optional[str] = None
    corrector_model_name: Optional[str] = None
    corrector_api_base: Optional[str] = None
    corrector_api_key: Optional[str] = None
    corrector_ollama_base_url: Optional[str] = None


@dataclass
class EventData:
    event_type: str
    day_number: int
    phase: str
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    public: bool = True
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PlayerData:
    id: str
    name: str
    seat_number: int
    is_alive: bool
    is_sheriff: bool
    role: str
    alignment: str
    is_human: bool = False
    is_teammate: bool = False


class StreamlitGameSession:
    def __init__(
        self,
        game_id: str,
        mode: str,
        model_config: StreamlitModelConfig,
        game_config: StreamlitGameConfig,
        corrector_config: StreamlitCorrectorConfig,
        player_seat: Optional[int] = None,
        player_name: Optional[str] = None,
    ):
        self.game_id = game_id
        self.mode = mode
        self.model_config = model_config
        self.game_config = game_config
        self.corrector_config = corrector_config
        self.player_seat = player_seat
        self.player_name = player_name or "Human Player"
        self.status = "created"
        self.created_at = datetime.now()
        self.orchestrator: Optional[GameOrchestrator] = None
        self.game_state: Optional[GameState] = None
        self.result: Optional[GameResult] = None
        self.events: List[EventData] = []
        self.narrations: List[str] = []
        self._game_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._human_input_handler = None
        self._human_agent = None
        self._action_request_queue: queue.Queue = queue.Queue()
        self._action_response_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self.winning_team: Optional[str] = None
        self.error_message: Optional[str] = None
        
        logger.info(f"[Session:{game_id}] Created new game session")
        logger.info(f"[Session:{game_id}] Mode: {mode}")
        logger.info(f"[Session:{game_id}] Model: {model_config.backend}/{model_config.model_name}")
        logger.info(f"[Session:{game_id}] Role set: {game_config.role_set}, Language: {game_config.language}")
        if mode == "play":
            logger.info(f"[Session:{game_id}] Human player: seat={player_seat}, name={self.player_name}")

    def _create_model_config(self) -> AgentModelConfig:
        logger.debug(f"[Session:{self.game_id}] Creating model configuration...")
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
        logger.info(f"[Session:{self.game_id}] Default model: backend={backend.value}, model={self.model_config.model_name}, temp={self.model_config.temperature}")
        
        corrector_override = None
        if self.corrector_config.use_separate_model:
            corrector_backend = ModelBackend.OLLAMA
            if self.corrector_config.corrector_backend == "api":
                corrector_backend = ModelBackend.API
            
            corrector_override = ModelConfig(
                backend=corrector_backend,
                model_name=self.corrector_config.corrector_model_name or self.model_config.model_name,
                api_base=self.corrector_config.corrector_api_base,
                api_key=self.corrector_config.corrector_api_key,
                ollama_base_url=self.corrector_config.corrector_ollama_base_url,
                temperature=0.3,
                max_tokens=512,
            )
            logger.info(f"[Session:{self.game_id}] Using separate corrector model: {corrector_override.model_name}")
        
        output_corrector = OutputCorrectorConfig(
            enabled=self.corrector_config.enabled,
            max_retries=self.corrector_config.max_retries,
            model_config_override=corrector_override,
        )
        logger.info(f"[Session:{self.game_id}] Output corrector: enabled={output_corrector.enabled}, max_retries={output_corrector.max_retries}")
        
        return AgentModelConfig(default=default_config, output_corrector=output_corrector)

    def _create_game_config(self) -> GameConfig:
        role_set = RoleSet.A if self.game_config.role_set == "A" else RoleSet.B
        logger.info(f"[Session:{self.game_id}] Game config: role_set={role_set.value}, seed={self.game_config.random_seed}")
        return GameConfig(
            num_players=12,
            role_set=role_set,
            random_seed=self.game_config.random_seed,
        )

    def _on_event(self, event: Event, game_state: GameState) -> None:
        with self._lock:
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
            
            event_data = EventData(
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
            self.events.append(event_data)
            
            logger.info(f"[Session:{self.game_id}] Event: Day {event.day_number} {event.phase.value} | {event.event_type.value} | {description}")

    def _on_narration(self, narration: str) -> None:
        with self._lock:
            self.narrations.append(narration)
            logger.debug(f"[Session:{self.game_id}] Narration: {narration[:100]}...")

    def _on_action_request(self, request: Dict[str, Any]) -> None:
        player_info = {}
        if self._human_agent and self.game_state:
            player = self.game_state.get_player(self._human_agent.player_id)
            if player:
                player_info = {
                    "player_id": player.id,
                    "player_name": player.name,
                    "role": player.role.value,
                    "is_alive": player.is_alive,
                    "is_sheriff": player.is_sheriff,
                }
        
        valid_targets_raw = request.get("valid_targets", [])
        valid_targets_with_info = []
        if self.game_state:
            for target_id in valid_targets_raw:
                target_player = self.game_state.get_player(target_id)
                if target_player:
                    valid_targets_with_info.append({
                        "id": target_id,
                        "name": target_player.name,
                        "seat_number": target_player.seat_number,
                        "is_alive": target_player.is_alive,
                    })
        
        action_type = request.get("action_type")
        logger.info(f"[Session:{self.game_id}] Action request: type={action_type}, targets={len(valid_targets_with_info)}, allow_skip={request.get('allow_skip', False)}")
        
        self._action_request_queue.put({
            "action_type": action_type,
            "prompt": request.get("prompt"),
            "valid_targets": valid_targets_raw,
            "valid_targets_info": valid_targets_with_info,
            "allow_skip": request.get("allow_skip", False),
            "extra_context": request.get("extra_context", {}),
            "player_info": player_info,
        })

    def _describe_event(self, event: Event, actor_name: Optional[str], target_name: Optional[str]) -> str:
        event_type = event.event_type.value
        actor = actor_name or "Someone"
        target = target_name or "someone"
        
        descriptions = {
            "death_announcement": f"💀 {target} was found dead",
            "lynch": f"⚖️ {target} was lynched",
            "vote_cast": f"🗳️ {actor} voted for {target}",
            "vote_result": "📊 Vote result announced",
            "sheriff_elected": f"👑 {target} became sheriff",
            "sheriff_election": "🏛️ Sheriff election started",
            "hunter_shot": f"🔫 {actor} (Hunter) shot {target}",
            "badge_pass": f"👑 Badge passed to {target}",
            "badge_tear": "💔 Badge was torn",
            "village_idiot_reveal": f"🃏 {target} revealed as Village Idiot and survives",
            "wolf_self_explode": f"💥 {actor} self-exploded",
            "night_kill": f"🐺 Werewolves targeted {target}",
            "seer_check": f"🔮 Seer checked {target}",
            "witch_save": "💊 Witch used cure",
            "witch_poison": f"☠️ Witch poisoned {target}",
            "guard_protect": f"🛡️ Guard protected {target}",
            "saved": f"✨ {target} was saved",
            "no_death": "☀️ Peaceful night",
            "phase_change": "🌅 Phase changed",
            "game_start": "🎮 Game started",
            "game_end": "🏆 Game ended",
        }
        
        if event_type == "speech":
            content = event.data.get("content", "") if event.data else ""
            is_last_words = event.data.get("is_last_words", False) if event.data else False
            prefix = "🗣️ [Last Words] " if is_last_words else "🗣️ "
            return f"{prefix}{actor}: {content}"
        
        if event_type == "sheriff_campaign_speech":
            content = event.data.get("content", "") if event.data else ""
            return f"🗣️ [Campaign] {actor}: {content}"
        
        return descriptions.get(event_type, f"📝 {event_type}")

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            state = self.game_state
        
        if state is None and self.orchestrator and hasattr(self.orchestrator, '_game_state'):
            state = self.orchestrator._game_state
        
        if state is None:
            logger.debug(f"[Session:{self.game_id}] get_state: No game state available yet")
            return {
                "game_id": self.game_id,
                "status": self.status,
                "day_number": 0,
                "phase": "night",
                "players": [],
                "sheriff_id": None,
                "badge_torn": False,
                "winning_team": self.winning_team,
                "human_player_view": None,
            }
        
        human_player_id = self._human_agent.player_id if self._human_agent else None
        human_player = state.get_player(human_player_id) if human_player_id else None
        human_is_werewolf = human_player and human_player.role == Role.WEREWOLF
        
        werewolf_ids = set()
        if human_is_werewolf:
            werewolf_ids = {w.id for w in state.get_werewolves()}
        
        players_data = []
        for p in state.players:
            is_human_player = human_player_id and p.id == human_player_id
            is_werewolf_teammate = human_is_werewolf and p.id in werewolf_ids
            role_visible = (
                self.mode == "watch" or 
                self.status == "completed" or 
                is_human_player or 
                is_werewolf_teammate
            )
            players_data.append(PlayerData(
                id=p.id,
                name=p.name,
                seat_number=p.seat_number,
                is_alive=p.is_alive,
                is_sheriff=p.is_sheriff,
                role=p.role.value if role_visible else "hidden",
                alignment=p.alignment.value if role_visible else "hidden",
                is_human=bool(is_human_player),
                is_teammate=bool(is_werewolf_teammate and not is_human_player),
            ))
        
        winning = None
        if state.winning_team != WinningTeam.NONE:
            winning = state.winning_team.value
        
        human_player_view = None
        if self.mode == "play" and human_player_id:
            human_player_view = self._get_human_player_view(state, human_player_id)
        
        return {
            "game_id": self.game_id,
            "status": self.status,
            "day_number": state.day_number,
            "phase": state.phase.value,
            "players": players_data,
            "sheriff_id": state.sheriff_id,
            "badge_torn": state.badge_torn,
            "winning_team": winning or self.winning_team,
            "human_player_view": human_player_view,
        }

    def _get_human_player_view(self, state: GameState, player_id: str) -> Optional[Dict[str, Any]]:
        player = state.get_player(player_id)
        if not player:
            return None
        
        private_info: Dict[str, Any] = {}
        if player.role == Role.WEREWOLF:
            wolves = state.get_werewolves()
            private_info["teammates"] = [
                {"id": w.id, "name": w.name, "is_alive": w.is_alive}
                for w in wolves if w.id != player_id
            ]
        elif player.role == Role.SEER:
            check_results = []
            for pid, align in player.seer_checks:
                checked_player = state.get_player(pid)
                check_results.append({
                    "player_id": pid,
                    "player_name": checked_player.name if checked_player else pid,
                    "result": align.value,
                })
            private_info["check_results"] = check_results
        elif player.role == Role.WITCH:
            private_info["has_cure"] = player.witch_has_cure
            private_info["has_poison"] = player.witch_has_poison
            if state.wolf_kill_target_id and state.phase.value == "night":
                target = state.get_player(state.wolf_kill_target_id)
                if target:
                    private_info["attack_target"] = {"id": target.id, "name": target.name}
        elif player.role == Role.GUARD:
            if player.guard_last_protected:
                last_protected_player = state.get_player(player.guard_last_protected)
                private_info["last_protected"] = {
                    "id": player.guard_last_protected,
                    "name": last_protected_player.name if last_protected_player else player.guard_last_protected,
                }
            else:
                private_info["last_protected"] = None
        elif player.role == Role.HUNTER:
            private_info["can_shoot"] = player.hunter_can_shoot
        elif player.role == Role.VILLAGE_IDIOT:
            private_info["revealed"] = player.village_idiot_revealed
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "role": player.role.value,
            "alignment": player.alignment.value,
            "is_alive": player.is_alive,
            "is_sheriff": player.is_sheriff,
            "private_info": private_info,
        }

    def get_events(self) -> List[EventData]:
        with self._lock:
            return list(self.events)

    def get_action_request(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        try:
            return self._action_request_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def submit_action(self, action_type: str, target_id: Optional[str] = None, 
                      content: Optional[str] = None, value: Optional[bool] = None) -> bool:
        logger.info(f"[Session:{self.game_id}] Action submitted: type={action_type}, target={target_id}, value={value}")
        if self._human_input_handler:
            data = {
                "action_type": action_type,
                "target": target_id,
                "text": content or "",
                "value": value,
            }
            self._human_input_handler.set_input(data)
            logger.debug(f"[Session:{self.game_id}] Action data passed to input handler")
            return True
        logger.warning(f"[Session:{self.game_id}] No human input handler available for action submission")
        return False

    def start(self) -> None:
        if self.status != "created":
            logger.error(f"[Session:{self.game_id}] Cannot start game: status is {self.status}")
            raise RuntimeError("Game already started")
        
        logger.info(f"[Session:{self.game_id}] Starting game...")
        self.status = "running"
        self._stop_event.clear()
        self._game_thread = threading.Thread(target=self._run_game, daemon=True)
        self._game_thread.start()
        logger.info(f"[Session:{self.game_id}] Game thread started")

    def stop(self) -> None:
        logger.info(f"[Session:{self.game_id}] Stop requested")
        self._stop_event.set()
        self.status = "stopped"
        if self.orchestrator:
            self.orchestrator.request_stop()
            logger.info(f"[Session:{self.game_id}] Orchestrator stop signal sent")

    def _run_game(self) -> None:
        try:
            from autowerewolf.agents.human import HumanPlayerAgent, WebInputHandler
            
            logger.info(f"[Session:{self.game_id}] Initializing game orchestrator...")
            
            agent_model_config = self._create_model_config()
            game_config = self._create_game_config()
            
            lang = self.game_config.language
            set_language(Language(lang))
            lang_setting = LanguageSetting(lang)
            logger.info(f"[Session:{self.game_id}] Language set to: {lang}")
            
            base_perf = PERFORMANCE_PRESETS["standard"]
            perf_config = PerformanceConfig(
                verbosity=base_perf.verbosity,
                language=lang_setting,
                enable_batching=base_perf.enable_batching,
                batch_size=base_perf.batch_size,
                skip_narration=base_perf.skip_narration,
                compact_logs=base_perf.compact_logs,
                max_speech_length=base_perf.max_speech_length,
                max_reasoning_length=base_perf.max_reasoning_length,
            )
            
            default_logs_dir = Path.cwd() / "logs"
            default_logs_dir.mkdir(parents=True, exist_ok=True)
            
            human_player_agent = None
            if self.mode == "play" and self.player_seat is not None:
                self._human_input_handler = WebInputHandler()
                self._human_input_handler.set_action_request_callback(self._on_action_request)
                self._human_agent = HumanPlayerAgent(
                    player_id="",
                    player_name=self.player_name,
                    role=Role.VILLAGER,
                    input_handler=self._human_input_handler,
                )
                human_player_agent = self._human_agent
                logger.info(f"[Session:{self.game_id}] Human player agent created for seat {self.player_seat}")
            
            logger.info(f"[Session:{self.game_id}] Creating orchestrator...")
            self.orchestrator = GameOrchestrator(
                config=game_config,
                agent_models=agent_model_config,
                enable_console_logging=False,
                enable_file_logging=True,
                output_path=default_logs_dir,
                performance_config=perf_config,
                event_callback=self._on_event,
                narration_callback=self._on_narration,
                human_player_seat=self.player_seat if self.mode == "play" else None,
                human_player_agent=human_player_agent,
            )
            
            logger.info(f"[Session:{self.game_id}] ========== GAME STARTING ==========")
            self.result = self.orchestrator.run_game()
            logger.info(f"[Session:{self.game_id}] ========== GAME FINISHED ==========")
            
            if self._stop_event.is_set() or self.orchestrator.is_stop_requested():
                with self._lock:
                    if self.orchestrator._game_state:
                        self.game_state = self.orchestrator._game_state
                self.status = "stopped"
                logger.info(f"[Session:{self.game_id}] Game stopped by user request")
                return
            
            if self.result:
                with self._lock:
                    self.game_state = self.result.final_state
                self.status = "completed"
                self.winning_team = self.result.winning_team.value if self.result.winning_team else None
                logger.info(f"[Session:{self.game_id}] Game completed! Winner: {self.winning_team}")
                
                alive_count = sum(1 for p in self.result.final_state.players if p.is_alive) if self.result.final_state else 0
                logger.info(f"[Session:{self.game_id}] Final stats: {alive_count} players alive, {len(self.events)} events recorded")
                
                if self.result.game_log:
                    log_path = default_logs_dir / f"logs-{self.orchestrator._game_id}.json"
                    save_game_log(self.result.game_log, log_path)
                    logger.info(f"[Session:{self.game_id}] Game log saved to: {log_path}")
                
        except Exception as e:
            if self._stop_event.is_set():
                self.status = "stopped"
                logger.info(f"[Session:{self.game_id}] Game stopped during exception handling")
            else:
                logger.error(f"[Session:{self.game_id}] Game error: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"[Session:{self.game_id}] Traceback:\n{traceback.format_exc()}")
                self.status = "error"
                self.error_message = str(e)


class StreamlitSessionManager:
    _instance = None
    _lock = threading.Lock()
    _sessions: Dict[str, StreamlitGameSession] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._sessions = {}
        return cls._instance

    def create_session(
        self,
        mode: str,
        model_config: StreamlitModelConfig,
        game_config: StreamlitGameConfig,
        corrector_config: StreamlitCorrectorConfig,
        player_seat: Optional[int] = None,
        player_name: Optional[str] = None,
    ) -> StreamlitGameSession:
        game_id = str(uuid4())[:8]
        logger.info(f"[SessionManager] Creating new session: {game_id}")
        
        session = StreamlitGameSession(
            game_id=game_id,
            mode=mode,
            model_config=model_config,
            game_config=game_config,
            corrector_config=corrector_config,
            player_seat=player_seat,
            player_name=player_name,
        )
        
        self._sessions[game_id] = session
        logger.info(f"[SessionManager] Session {game_id} registered. Total active sessions: {len(self._sessions)}")
        return session

    def get_session(self, game_id: str) -> Optional[StreamlitGameSession]:
        return self._sessions.get(game_id)

    def remove_session(self, game_id: str) -> bool:
        session = self._sessions.pop(game_id, None)
        if session:
            session.stop()
            logger.info(f"[SessionManager] Session {game_id} removed. Remaining sessions: {len(self._sessions)}")
            return True
        logger.warning(f"[SessionManager] Session {game_id} not found for removal")
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "game_id": s.game_id,
                "mode": s.mode,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in self._sessions.values()
        ]

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        now = datetime.now()
        to_remove = []
        
        for game_id, session in self._sessions.items():
            age = (now - session.created_at).total_seconds() / 3600
            if age > max_age_hours and session.status in ("completed", "error", "stopped"):
                to_remove.append(game_id)
        
        for game_id in to_remove:
            self.remove_session(game_id)
        
        if to_remove:
            logger.info(f"[SessionManager] Cleaned up {len(to_remove)} old sessions: {to_remove}")
        
        return len(to_remove)


session_manager = StreamlitSessionManager()
