import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from autowerewolf.agents.human import HumanPlayerAgent, WebInputHandler
from autowerewolf.agents.memory import create_agent_memory
from autowerewolf.agents.player_base import BasePlayerAgent, create_player_agent
from autowerewolf.config.models import AgentModelConfig
from autowerewolf.config.performance import PerformanceConfig, VerbosityLevel
from autowerewolf.engine.roles import Role, WinningTeam
from autowerewolf.engine.state import GameConfig
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator, GameResult

logger = logging.getLogger(__name__)


class GameStatus(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class PlayerSession:
    player_id: str
    player_name: str
    is_human: bool
    role: Optional[Role] = None
    is_alive: bool = True
    is_connected: bool = False
    input_handler: Optional[WebInputHandler] = None

    def to_dict(self, reveal_role: bool = False) -> dict[str, Any]:
        result = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "is_human": self.is_human,
            "is_alive": self.is_alive,
            "is_connected": self.is_connected,
        }
        if reveal_role and self.role:
            result["role"] = self.role.value
        return result


@dataclass
class GameSession:
    session_id: str
    config: GameConfig
    agent_config: AgentModelConfig
    performance_config: PerformanceConfig
    status: GameStatus = GameStatus.WAITING
    human_player_ids: list[str] = field(default_factory=list)
    players: dict[str, PlayerSession] = field(default_factory=dict)
    orchestrator: Optional[GameOrchestrator] = None
    result: Optional[GameResult] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    events_buffer: list[dict[str, Any]] = field(default_factory=list)
    on_event: Optional[Callable[[dict[str, Any]], None]] = None

    def add_event(self, event: dict[str, Any]) -> None:
        self.events_buffer.append(event)
        if self.on_event:
            self.on_event(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "human_player_ids": self.human_player_ids,
            "players": [p.to_dict() for p in self.players.values()],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "winning_team": self.result.winning_team.value if self.result else None,
        }


class GameManager:
    def __init__(self):
        self.sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        config: GameConfig,
        agent_config: AgentModelConfig,
        performance_config: Optional[PerformanceConfig] = None,
        human_seats: Optional[list[int]] = None,
    ) -> GameSession:
        session_id = str(uuid4())[:8]
        
        session = GameSession(
            session_id=session_id,
            config=config,
            agent_config=agent_config,
            performance_config=performance_config or PerformanceConfig(),
            human_player_ids=[],
        )
        
        async with self._lock:
            self.sessions[session_id] = session
        
        logger.info(f"Created game session: {session_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[GameSession]:
        return self.sessions.get(session_id)

    async def list_sessions(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    async def join_session(
        self,
        session_id: str,
        player_name: str,
        seat_number: Optional[int] = None,
    ) -> Optional[PlayerSession]:
        session = self.sessions.get(session_id)
        if not session or session.status != GameStatus.WAITING:
            return None
        
        player_id = f"human_{len(session.human_player_ids) + 1}"
        input_handler = WebInputHandler()
        
        player_session = PlayerSession(
            player_id=player_id,
            player_name=player_name,
            is_human=True,
            is_connected=True,
            input_handler=input_handler,
        )
        
        session.players[player_id] = player_session
        session.human_player_ids.append(player_id)
        
        session.add_event({
            "type": "player_joined",
            "player_id": player_id,
            "player_name": player_name,
        })
        
        return player_session

    async def start_game(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session or session.status != GameStatus.WAITING:
            return False
        
        try:
            session.status = GameStatus.RUNNING
            session.started_at = datetime.now()
            
            session.add_event({
                "type": "game_started",
                "timestamp": session.started_at.isoformat(),
            })
            
            asyncio.create_task(self._run_game(session))
            return True
        except Exception as e:
            logger.error(f"Failed to start game {session_id}: {e}")
            session.status = GameStatus.ERROR
            return False

    async def _run_game(self, session: GameSession) -> None:
        try:
            orchestrator = GameOrchestrator(
                config=session.config,
                agent_models=session.agent_config,
                performance_config=session.performance_config,
                enable_console_logging=False,
            )
            session.orchestrator = orchestrator
            
            result = orchestrator.run_game()
            
            session.result = result
            session.status = GameStatus.FINISHED
            session.finished_at = datetime.now()
            
            session.add_event({
                "type": "game_finished",
                "winning_team": result.winning_team.value,
                "timestamp": session.finished_at.isoformat(),
            })
            
        except Exception as e:
            logger.error(f"Game error: {e}")
            session.status = GameStatus.ERROR
            session.add_event({
                "type": "game_error",
                "error": str(e),
            })

    async def submit_action(
        self,
        session_id: str,
        player_id: str,
        action_data: dict[str, Any],
    ) -> bool:
        session = self.sessions.get(session_id)
        if not session or session.status != GameStatus.RUNNING:
            return False
        
        player = session.players.get(player_id)
        if not player or not player.is_human or not player.input_handler:
            return False
        
        player.input_handler.set_input(action_data)
        return True

    async def get_game_state(
        self,
        session_id: str,
        player_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        if not session.orchestrator or not session.orchestrator._game_state:
            return {
                "status": session.status.value,
                "waiting_for_players": True,
            }
        
        game_state = session.orchestrator._game_state
        
        result = {
            "status": session.status.value,
            "day_number": game_state.day_number,
            "phase": game_state.phase.value,
            "players": [],
        }
        
        for player in game_state.players:
            player_data = {
                "id": player.id,
                "name": player.name,
                "seat_number": player.seat_number,
                "is_alive": player.is_alive,
                "is_sheriff": player.is_sheriff,
            }
            
            if player_id and player.id == player_id:
                player_data["role"] = player.role.value
            
            result["players"].append(player_data)
        
        return result

    async def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
