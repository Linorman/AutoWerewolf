import logging
import random
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, NotRequired, Optional, TypedDict, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, StateGraph

from autowerewolf.agents.backend import get_chat_model
from autowerewolf.agents.batch import BatchExecutor, create_batch_executor
from autowerewolf.agents.human import HumanPlayerAgent
from autowerewolf.agents.memory import WerewolfCampMemory, create_agent_memory
from autowerewolf.agents.moderator import ModeratorChain
from autowerewolf.agents.output_corrector import OutputCorrector, create_output_corrector
from autowerewolf.agents.player_base import (
    BasePlayerAgent,
    GameView,
    create_player_agent,
)
from autowerewolf.agents.roles.werewolf import WerewolfAgent, WerewolfDiscussionChain
from autowerewolf.agents.schemas import (
    BadgeDecisionOutput,
    GuardNightOutput,
    HunterShootOutput,
    LastWordsOutput,
    SeerNightOutput,
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    WitchNightOutput,
)
from autowerewolf.config.models import AgentModelConfig
from autowerewolf.config.performance import (
    PERFORMANCE_PRESETS,
    PerformanceConfig,
)
from autowerewolf.engine.roles import Phase, Role, WinningTeam
from autowerewolf.engine.rules import (
    advance_to_day,
    advance_to_night,
    create_game_state,
    get_valid_guard_targets,
    get_valid_hunter_targets,
    get_valid_vote_targets,
    get_valid_wolf_targets,
    resolve_badge_action,
    resolve_hunter_shot,
    resolve_lynch,
    resolve_night_actions,
    resolve_sheriff_election,
    resolve_vote,
    update_win_condition,
)
from autowerewolf.engine.state import (
    Action,
    DeathAnnouncementEvent,
    Event,
    GameConfig,
    GameState,
    GuardProtectAction,
    HunterShootAction,
    PassBadgeAction,
    SeerCheckAction,
    SpeechEvent,
    TearBadgeAction,
    WitchCureAction,
    WitchPoisonAction,
    WolfKillAction,
)
from autowerewolf.io.logging import GameLogLevel, GameLogger, create_game_logger
from autowerewolf.io.persistence import (
    GameLog,
    PlayerLog,
    create_game_log,
    save_game_log,
)

logger = logging.getLogger(__name__)

MAX_GAME_DAYS = 20


@dataclass
class GameResult:
    winning_team: WinningTeam
    final_state: GameState
    events: list[Event] = field(default_factory=list)
    narration_log: list[str] = field(default_factory=list)
    game_log: Optional[GameLog] = None


class GraphState(TypedDict):
    """TypedDict for StateGraph state."""
    game_state: GameState
    agents: dict[str, BasePlayerAgent]
    moderator: ModeratorChain
    events_buffer: NotRequired[list[Event]]
    narration_log: NotRequired[list[str]]
    night_deaths: NotRequired[list[str]]
    pending_hunter_shot: NotRequired[Optional[str]]
    pending_badge_decision: NotRequired[Optional[str]]


@dataclass
class OrchestratorState:
    """State container for orchestrator during game execution."""
    game_state: GameState
    agents: dict[str, BasePlayerAgent]
    moderator: ModeratorChain
    events_buffer: list[Event] = field(default_factory=list)
    narration_log: list[str] = field(default_factory=list)
    night_deaths: list[str] = field(default_factory=list)
    pending_hunter_shot: Optional[str] = None
    pending_badge_decision: Optional[str] = None

    def to_dict(self) -> "GraphState":
        """Convert to GraphState dict for StateGraph."""
        return {
            "game_state": self.game_state,
            "agents": self.agents,
            "moderator": self.moderator,
            "events_buffer": self.events_buffer,
            "narration_log": self.narration_log,
            "night_deaths": self.night_deaths,
            "pending_hunter_shot": self.pending_hunter_shot,
            "pending_badge_decision": self.pending_badge_decision,
        }

    @classmethod
    def from_dict(cls, d: "GraphState") -> "OrchestratorState":
        """Create OrchestratorState from GraphState dict."""
        return cls(
            game_state=d["game_state"],
            agents=d["agents"],
            moderator=d["moderator"],
            events_buffer=d.get("events_buffer", []),
            narration_log=d.get("narration_log", []),
            night_deaths=d.get("night_deaths", []),
            pending_hunter_shot=d.get("pending_hunter_shot"),
            pending_badge_decision=d.get("pending_badge_decision"),
        )


class GameOrchestrator:
    def __init__(
        self,
        config: GameConfig,
        agent_models: AgentModelConfig,
        player_names: Optional[list[str]] = None,
        log_level: GameLogLevel = GameLogLevel.STANDARD,
        output_path: Optional[Path] = None,
        enable_console_logging: bool = True,
        enable_file_logging: bool = False,
        performance_config: Optional[PerformanceConfig] = None,
        event_callback: Optional[Callable[[Event, "GameState"], None]] = None,
        narration_callback: Optional[Callable[[str], None]] = None,
        human_player_seat: Optional[int] = None,
        human_player_agent: Optional[BasePlayerAgent] = None,
    ):
        self.config = config
        self.agent_models = agent_models
        self.player_names = player_names
        self.performance_config = performance_config or PERFORMANCE_PRESETS["standard"]
        self._game_state: Optional[GameState] = None
        self._agents: dict[str, BasePlayerAgent] = {}
        self._moderator: Optional[ModeratorChain] = None
        self._graph: Optional[StateGraph] = None
        self._batch_executor: Optional[BatchExecutor] = None
        self._werewolf_camp_memory: Optional[WerewolfCampMemory] = None
        self._event_callback = event_callback
        self._narration_callback = narration_callback
        self._stop_requested = False
        self._human_player_seat = human_player_seat
        self._human_player_agent = human_player_agent
        
        self._game_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
        self._log_level = log_level
        self._output_path = output_path
        self._enable_console_logging = enable_console_logging
        self._enable_file_logging = enable_file_logging
        self._game_logger: Optional[GameLogger] = None
        self._game_log: Optional[GameLog] = None

    def request_stop(self) -> None:
        self._stop_requested = True
        logger.info("Game stop requested")

    def is_stop_requested(self) -> bool:
        return self._stop_requested

    def _truncate_content(self, content: str) -> str:
        """Truncate content to max speech length if needed."""
        max_len = self.performance_config.max_speech_length
        if len(content) > max_len:
            return content[:max_len] + "..."
        return content

    def _emit_event(self, event: Event, game_state: GameState) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, game_state)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def _emit_narration(self, narration: str) -> None:
        if self._narration_callback:
            try:
                self._narration_callback(narration)
            except Exception as e:
                logger.warning(f"Narration callback error: {e}")

    def _add_event_to_buffer(self, state: OrchestratorState, event: Event) -> None:
        state.events_buffer.append(event)
        self._emit_event(event, state.game_state)

    def _add_events_to_buffer(self, state: OrchestratorState, events: list[Event]) -> None:
        for event in events:
            state.events_buffer.append(event)
            self._emit_event(event, state.game_state)

    def _add_narration(self, state: OrchestratorState, narration: str) -> None:
        state.narration_log.append(narration)
        self._emit_narration(narration)

    def _record_werewolf_discussion(
        self,
        night_number: int,
        discussions: list[dict[str, Any]],
    ) -> None:
        if self._game_log and discussions:
            self._game_log.add_werewolf_discussion(night_number, discussions)

    def _initialize_game(self) -> GameState:
        return create_game_state(self.config, self.player_names)

    def _get_model_for_role(self, role: Role) -> BaseChatModel:
        role_name = role.value
        config = self.agent_models.get_config_for_role(role_name)
        return get_chat_model(config)

    def _create_agents(self, game_state: GameState) -> dict[str, BasePlayerAgent]:
        agents = {}
        verbosity = self.performance_config.verbosity
        language = self.performance_config.language.value  # Get language from performance config
        memory_type = self.performance_config.memory_type
        max_facts = self.performance_config.max_memory_facts
        
        werewolf_camp_memory = WerewolfCampMemory()
        werewolf_ids = [p.id for p in game_state.players if p.role == Role.WEREWOLF]
        werewolf_camp_memory.set_werewolf_ids(werewolf_ids)
        self._werewolf_camp_memory = werewolf_camp_memory
        
        # Create output corrector if configured
        output_corrector: OutputCorrector | None = None
        corrector_config = self.agent_models.output_corrector
        if corrector_config.enabled:
            corrector_model_config = self.agent_models.get_corrector_model_config()
            output_corrector = create_output_corrector(corrector_config, corrector_model_config)
            logger.info(f"Output corrector enabled with max_retries={corrector_config.max_retries}")
        
        # Find human player id if human_player_seat is specified
        human_player_id: Optional[str] = None
        if self._human_player_seat is not None:
            for player in game_state.players:
                if player.seat_number == self._human_player_seat:
                    human_player_id = player.id
                    break
        
        for player in game_state.players:
            # Use human agent if this is the human player's seat
            if human_player_id and player.id == human_player_id and self._human_player_agent:
                # Update human agent with actual role assignment
                self._human_player_agent.player_id = player.id
                self._human_player_agent.player_name = player.name
                self._human_player_agent.role = player.role
                
                # Create memory for human player
                memory = create_agent_memory(player.id, memory_type)
                memory.facts._max_facts = max_facts
                self._human_player_agent.memory = memory
                
                agents[player.id] = self._human_player_agent
                logger.info(f"Human player assigned to seat {self._human_player_seat} (player {player.id}, role: {player.role.value})")
                continue
            
            chat_model = self._get_model_for_role(player.role)
            memory = create_agent_memory(player.id, memory_type)
            memory.facts._max_facts = max_facts
            
            if memory_type == "summary":
                memory.set_summarizer(chat_model)
            
            agent = create_player_agent(
                player_id=player.id,
                player_name=player.name,
                role=player.role,
                chat_model=chat_model,
                memory=memory,
                verbosity=verbosity,
                output_corrector=output_corrector,
                language=language,
            )
            agents[player.id] = agent
        return agents

    def _create_batch_executor(self) -> BatchExecutor:
        rate_limit = self.agent_models.default.rate_limit_rpm
        return create_batch_executor(self.performance_config, rate_limit)

    def _create_moderator(self) -> ModeratorChain:
        config = self.agent_models.get_config_for_role("moderator")
        chat_model = get_chat_model(config)
        return ModeratorChain(chat_model)

    def _update_all_agents_memory_after_speech(
        self,
        state: OrchestratorState,
        speaker_id: str,
        content: str,
    ) -> None:
        day_number = state.game_state.day_number
        for agent in state.agents.values():
            agent.update_memory_after_speech(day_number, speaker_id, content)

    def _update_all_agents_memory_after_vote(
        self,
        state: OrchestratorState,
        votes: dict[str, str],
    ) -> None:
        day_number = state.game_state.day_number
        for voter_id, target_id in votes.items():
            for agent in state.agents.values():
                agent.update_memory_after_vote(day_number, voter_id, target_id)

    def _update_all_agents_memory_after_night(
        self,
        state: OrchestratorState,
        events: list[Event],
    ) -> None:
        day_number = state.game_state.day_number
        visible_events = [
            {"type": "death", "player_id": e.target_id, "death_type": e.event_type.value}
            for e in events
            if e.event_type.value == "death_announcement" and e.target_id
        ]
        for agent in state.agents.values():
            agent.update_memory_after_night(day_number, visible_events)

    def build_game_view(
        self,
        game_state: GameState,
        player_id: str,
        action_context: Optional[dict[str, Any]] = None,
    ) -> GameView:
        player = game_state.get_player(player_id)
        if not player:
            raise ValueError(f"Player {player_id} not found")

        alive_players = [
            {
                "id": p.id,
                "name": p.name,
                "seat_number": p.seat_number,
                "is_sheriff": p.is_sheriff,
                "is_alive": p.is_alive,
            }
            for p in game_state.players
        ]

        public_events = game_state.get_public_events()
        public_history = [
            {"description": self._describe_event_for_view(e, game_state)}
            for e in public_events[-20:]
        ]

        private_info = self._get_private_info(game_state, player)

        return GameView(
            player_id=player_id,
            player_name=player.name,
            role=player.role,
            phase=game_state.phase.value,
            day_number=game_state.day_number,
            alive_players=alive_players,
            public_history=public_history,
            private_info=private_info,
            action_context=action_context or {},
        )

    def _describe_event_for_view(self, event: Event, game_state: GameState) -> str:
        target = game_state.get_player(event.target_id) if event.target_id else None
        actor = game_state.get_player(event.actor_id) if event.actor_id else None

        event_type = event.event_type.value
        target_name = target.name if target else "Unknown"
        actor_name = actor.name if actor else "Unknown"

        descriptions = {
            "death_announcement": f"{target_name} was found dead",
            "lynch": f"{target_name} was lynched",
            "speech": f"{actor_name}: {event.data.get('content', '')[:100]}",
            "vote_cast": f"{actor_name} voted for {target_name}",
            "sheriff_elected": f"{target_name} became sheriff",
            "hunter_shot": f"{actor_name} shot {target_name}",
            "village_idiot_reveal": f"{target_name} revealed as Village Idiot",
            "badge_pass": f"Badge passed to {target_name}",
            "badge_tear": "Badge was torn",
            "wolf_self_explode": f"{actor_name} self-exploded as werewolf",
        }
        return descriptions.get(event_type, event_type)

    def _get_private_info(
        self, game_state: GameState, player: Any
    ) -> dict[str, Any]:
        private_info: dict[str, Any] = {}
        role = player.role

        match role:
            case Role.WEREWOLF:
                wolves = game_state.get_werewolves()
                private_info["teammates"] = [
                    {"id": w.id, "name": w.name, "is_alive": w.is_alive}
                    for w in wolves if w.id != player.id
                ]
            case Role.SEER:
                private_info["check_results"] = [
                    {"player_id": pid, "result": alignment.value}
                    for pid, alignment in player.seer_checks
                ]
            case Role.WITCH:
                private_info["has_cure"] = player.witch_has_cure
                private_info["has_poison"] = player.witch_has_poison
                if game_state.wolf_kill_target_id:
                    target = game_state.get_player(game_state.wolf_kill_target_id)
                    if target:
                        private_info["attack_target"] = {"id": target.id, "name": target.name}
            case Role.GUARD:
                private_info["last_protected"] = player.guard_last_protected
            case Role.HUNTER:
                private_info["can_shoot"] = player.hunter_can_shoot
            case Role.VILLAGE_IDIOT:
                private_info["revealed"] = player.village_idiot_revealed

        return private_info

    def _collect_werewolf_action(
        self,
        state: OrchestratorState,
    ) -> tuple[Optional[WolfKillAction], list[dict[str, Any]]]:
        wolves = state.game_state.get_alive_werewolves()
        if not wolves:
            return None, []

        valid_targets = get_valid_wolf_targets(
            state.game_state,
            include_self_knife=state.game_state.config.rule_variants.allow_wolf_self_knife,
        )

        werewolf_agents: list[WerewolfAgent] = []
        human_wolf_agent: Optional[BasePlayerAgent] = None
        human_wolf_id: Optional[str] = None
        
        for wolf in wolves:
            agent = state.agents.get(wolf.id)
            if agent:
                if isinstance(agent, HumanPlayerAgent):
                    human_wolf_agent = agent
                    human_wolf_id = wolf.id
                elif isinstance(agent, WerewolfAgent):
                    werewolf_agents.append(agent)

        discussions: list[dict[str, Any]] = []
        target_votes: dict[str, int] = {}
        
        if human_wolf_agent and human_wolf_id:
            try:
                game_view = self.build_game_view(
                    state.game_state,
                    human_wolf_id,
                    {
                        "valid_targets": valid_targets,
                        "teammates": [w.id for w in wolves if w.id != human_wolf_id],
                    },
                )
                result = human_wolf_agent.decide_night_action(game_view)
                
                if isinstance(result, WerewolfNightOutput):
                    human_wolf_player = state.game_state.get_player(human_wolf_id)
                    discussions.append({
                        "werewolf_id": human_wolf_id,
                        "werewolf_name": human_wolf_player.name if human_wolf_player else human_wolf_id,
                        "proposed_target": result.kill_target_id,
                        "reasoning": "Human player choice",
                    })
                    if result.kill_target_id in valid_targets:
                        target_votes[result.kill_target_id] = target_votes.get(result.kill_target_id, 0) + 1
            except Exception as e:
                logger.warning(f"Human werewolf action failed: {e}")
        
        if werewolf_agents:
            try:
                lead_wolf = wolves[0]
                chat_model = werewolf_agents[0].chat_model
                discussion_chain = WerewolfDiscussionChain(
                    werewolf_agents=werewolf_agents,
                    chat_model=chat_model,
                    camp_memory=self._werewolf_camp_memory,
                )

                game_view = self.build_game_view(
                    state.game_state,
                    lead_wolf.id,
                    {
                        "valid_targets": valid_targets,
                        "teammates": [w.id for w in wolves if w.id != lead_wolf.id],
                    },
                )

                proposals = discussion_chain.get_proposals(game_view)
                for wolf_id, proposal in proposals:
                    wolf_player = state.game_state.get_player(wolf_id)
                    discussions.append({
                        "werewolf_id": wolf_id,
                        "werewolf_name": wolf_player.name if wolf_player else wolf_id,
                        "proposed_target": proposal.target_player_id,
                        "reasoning": proposal.reasoning,
                    })
                    if proposal.target_player_id in valid_targets:
                        target_votes[proposal.target_player_id] = target_votes.get(proposal.target_player_id, 0) + 1

                if self._werewolf_camp_memory:
                    for wolf_id, proposal in proposals:
                        self._werewolf_camp_memory.add_discussion_note(
                            state.game_state.day_number,
                            wolf_id,
                            f"Proposed {proposal.target_player_id}: {proposal.reasoning}",
                        )

            except Exception as e:
                logger.warning(f"Werewolf discussion failed: {e}")

        # Determine consensus target by voting
        if target_votes:
            consensus_target = max(target_votes.keys(), key=lambda t: target_votes[t])
            
            if self._werewolf_camp_memory:
                self._werewolf_camp_memory.add_kill(state.game_state.day_number, consensus_target)

            if consensus_target in valid_targets:
                lead_wolf_id = wolves[0].id
                return WolfKillAction(
                    actor_id=lead_wolf_id,
                    target_id=consensus_target,
                ), discussions

        # Fallback to random target
        if valid_targets:
            target = random.choice(valid_targets)
            return WolfKillAction(actor_id=wolves[0].id, target_id=target), discussions
        return None, discussions

    def _collect_seer_action(
        self,
        state: OrchestratorState,
    ) -> Optional[SeerCheckAction]:
        seers = state.game_state.get_alive_players_by_role(Role.SEER)
        if not seers:
            return None

        seer = seers[0]
        valid_targets = [
            p.id for p in state.game_state.get_alive_players() if p.id != seer.id
        ]

        agent = state.agents.get(seer.id)
        if not agent:
            return None

        try:
            game_view = self.build_game_view(
                state.game_state, seer.id, {"valid_targets": valid_targets}
            )
            result = agent.decide_night_action(game_view)

            if isinstance(result, SeerNightOutput):
                if result.check_target_id in valid_targets:
                    return SeerCheckAction(
                        actor_id=seer.id,
                        target_id=result.check_target_id,
                    )
        except Exception as e:
            logger.warning(f"Seer action failed: {e}")

        if valid_targets:
            target = random.choice(valid_targets)
            return SeerCheckAction(actor_id=seer.id, target_id=target)
        return None

    def _collect_witch_action(
        self,
        state: OrchestratorState,
    ) -> tuple[Optional[WitchCureAction], Optional[WitchPoisonAction]]:
        witches = state.game_state.get_alive_players_by_role(Role.WITCH)
        if not witches:
            return None, None

        witch = witches[0]
        agent = state.agents.get(witch.id)
        if not agent:
            return None, None

        valid_targets = [
            p.id for p in state.game_state.get_alive_players() if p.id != witch.id
        ]

        action_context = {
            "has_cure": witch.witch_has_cure,
            "has_poison": witch.witch_has_poison,
            "attack_target": state.game_state.wolf_kill_target_id,
            "valid_targets": valid_targets,
        }

        try:
            game_view = self.build_game_view(
                state.game_state, witch.id, action_context
            )
            result = agent.decide_night_action(game_view)

            cure_action = None
            poison_action = None

            if isinstance(result, WitchNightOutput):
                if result.use_cure and witch.witch_has_cure:
                    cure_action = WitchCureAction(
                        actor_id=witch.id,
                        target_id=state.game_state.wolf_kill_target_id,
                    )
                if result.use_poison and witch.witch_has_poison and result.poison_target_id:
                    if result.poison_target_id in valid_targets:
                        poison_action = WitchPoisonAction(
                            actor_id=witch.id,
                            target_id=result.poison_target_id,
                        )

            return cure_action, poison_action
        except Exception as e:
            logger.warning(f"Witch action failed: {e}")
            return None, None

    def _collect_guard_action(
        self,
        state: OrchestratorState,
    ) -> Optional[GuardProtectAction]:
        guards = state.game_state.get_alive_players_by_role(Role.GUARD)
        if not guards:
            return None

        guard = guards[0]
        valid_targets = get_valid_guard_targets(state.game_state, guard.id)

        agent = state.agents.get(guard.id)
        if not agent:
            return None

        try:
            game_view = self.build_game_view(
                state.game_state, guard.id, {"valid_targets": valid_targets}
            )
            result = agent.decide_night_action(game_view)

            if isinstance(result, GuardNightOutput):
                if result.protect_target_id in valid_targets:
                    return GuardProtectAction(
                        actor_id=guard.id,
                        target_id=result.protect_target_id,
                    )
        except Exception as e:
            logger.warning(f"Guard action failed: {e}")

        if valid_targets:
            target = random.choice(valid_targets)
            return GuardProtectAction(actor_id=guard.id, target_id=target)
        return None

    def _run_night_phase(self, state: OrchestratorState) -> OrchestratorState:
        alive_count = len(state.game_state.get_alive_players())
        if self._game_logger:
            self._game_logger.log_phase_change(
                state.game_state.day_number, "night", alive_count
            )
        
        narration = state.moderator.announce_night_start(state.game_state)
        self._add_narration(state, narration)

        actions: list[Action] = []

        # Helper to append non-None actions
        def add_action(action: Optional[Action]) -> None:
            if action:
                actions.append(action)
                if self._game_logger:
                    actor = state.game_state.get_player(action.actor_id)
                    target = state.game_state.get_player(action.target_id) if action.target_id else None
                    self._game_logger.log_night_action(
                        action.actor_id,
                        actor.name if actor else action.actor_id,
                        actor.role.value if actor else "unknown",
                        action.action_type.value,
                        action.target_id,
                        target.name if target else None,
                    )

        add_action(self._collect_guard_action(state))

        wolf_action, wolf_discussions = self._collect_werewolf_action(state)
        if wolf_action:
            actions.append(wolf_action)
            new_state = deepcopy(state.game_state)
            new_state.wolf_kill_target_id = wolf_action.target_id
            state.game_state = new_state
            
            if self._game_logger:
                wolves = state.game_state.get_alive_werewolves()
                wolf_names = ", ".join(w.name for w in wolves)
                target = state.game_state.get_player(wolf_action.target_id) if wolf_action.target_id else None
                self._game_logger.log_night_action(
                    wolf_action.actor_id,
                    wolf_names,
                    "werewolf",
                    wolf_action.action_type.value,
                    wolf_action.target_id,
                    target.name if target else None,
                )

        if wolf_discussions:
            self._record_werewolf_discussion(state.game_state.day_number, wolf_discussions)

        cure_action, poison_action = self._collect_witch_action(state)
        add_action(cure_action)
        add_action(poison_action)
        add_action(self._collect_seer_action(state))

        alive_before = set(p.id for p in state.game_state.get_alive_players())

        new_game_state, events = resolve_night_actions(state.game_state, actions)
        state.game_state = new_game_state
        self._add_events_to_buffer(state, events)

        alive_after = set(p.id for p in state.game_state.get_alive_players())
        state.night_deaths = list(alive_before - alive_after)

        return state

    def _run_sheriff_election(self, state: OrchestratorState) -> OrchestratorState:
        if state.game_state.sheriff_election_complete:
            return state

        narration = state.moderator.announce_sheriff_election()
        self._add_narration(state, narration)

        candidates = []
        for player in state.game_state.get_alive_players():
            agent = state.agents.get(player.id)
            if not agent:
                continue

            try:
                game_view = self.build_game_view(state.game_state, player.id)
                result = agent.decide_sheriff_run(game_view)
                if result.run_for_sheriff:
                    candidates.append(player.id)
            except Exception as e:
                logger.warning(f"Sheriff decision failed for {player.id}: {e}")

        if not candidates:
            state.game_state.sheriff_election_complete = True
            return state

        votes: dict[str, str] = {}
        for player in state.game_state.get_alive_players():
            if player.id in candidates:
                continue

            agent = state.agents.get(player.id)
            if not agent:
                continue

            try:
                game_view = self.build_game_view(
                    state.game_state,
                    player.id,
                    {"candidates": candidates},
                )
                result = agent.decide_vote(game_view)
                if result.target_player_id in candidates:
                    votes[player.id] = result.target_player_id
            except Exception as e:
                logger.warning(f"Sheriff vote failed for {player.id}: {e}")

        new_game_state, events = resolve_sheriff_election(
            state.game_state, candidates, votes
        )
        state.game_state = new_game_state
        self._add_events_to_buffer(state, events)

        return state

    def _run_day_speeches(self, state: OrchestratorState) -> OrchestratorState:
        alive_players = state.game_state.get_alive_players()

        sheriff = state.game_state.get_sheriff()
        if sheriff and sheriff.is_alive:
            ordered = [sheriff] + [p for p in alive_players if p.id != sheriff.id]
        else:
            ordered = alive_players

        if self.performance_config.enable_batching and self._batch_executor:
            requests = []
            for player in ordered:
                agent = state.agents.get(player.id)
                if agent:
                    game_view = self.build_game_view(state.game_state, player.id)
                    requests.append((agent, game_view))

            results = self._batch_executor.execute_speeches_batch(requests)
            for batch_result in results:
                if batch_result.result and isinstance(batch_result.result, SpeechOutput):
                    content = self._truncate_content(batch_result.result.content)
                    player = state.game_state.get_player(batch_result.player_id)
                    player_name = player.name if player else batch_result.player_id
                    
                    event = SpeechEvent(
                        day_number=state.game_state.day_number,
                        phase=Phase.DAY,
                        actor_id=batch_result.player_id,
                        data={"content": content},
                    )
                    state.game_state.add_event(event)
                    self._add_event_to_buffer(state, event)
                    self._update_all_agents_memory_after_speech(state, batch_result.player_id, content)
                    
                    if self._game_logger:
                        self._game_logger.log_speech(
                            batch_result.player_id,
                            player_name,
                            state.game_state.day_number,
                            content,
                        )
        else:
            for player in ordered:
                agent = state.agents.get(player.id)
                if not agent:
                    continue

                try:
                    game_view = self.build_game_view(state.game_state, player.id)
                    result = agent.decide_day_speech(game_view)

                    if isinstance(result, SpeechOutput):
                        content = self._truncate_content(result.content)
                        event = SpeechEvent(
                            day_number=state.game_state.day_number,
                            phase=Phase.DAY,
                            actor_id=player.id,
                            data={"content": content},
                        )
                        state.game_state.add_event(event)
                        self._add_event_to_buffer(state, event)
                        self._update_all_agents_memory_after_speech(state, player.id, content)
                        
                        if self._game_logger:
                            self._game_logger.log_speech(
                                player.id,
                                player.name,
                                state.game_state.day_number,
                                content,
                            )
                except Exception as e:
                    logger.warning(f"Speech failed for {player.id}: {e}")

        return state

    def _run_day_vote(self, state: OrchestratorState) -> OrchestratorState:
        if not self.performance_config.skip_narration:
            narration = state.moderator.announce_voting_start()
            self._add_narration(state, narration)

        votes: dict[str, str] = {}

        if self.performance_config.enable_batching and self._batch_executor:
            requests = []
            player_targets: dict[str, list[str]] = {}
            for player in state.game_state.get_alive_players():
                agent = state.agents.get(player.id)
                if agent:
                    valid_targets = get_valid_vote_targets(state.game_state, player.id)
                    player_targets[player.id] = valid_targets
                    game_view = self.build_game_view(
                        state.game_state,
                        player.id,
                        {"valid_targets": valid_targets},
                    )
                    requests.append((agent, game_view))

            results = self._batch_executor.execute_votes_batch(requests)
            for batch_result in results:
                valid_targets = player_targets.get(batch_result.player_id, [])
                if batch_result.result and isinstance(batch_result.result, VoteOutput):
                    if batch_result.result.target_player_id in valid_targets:
                        votes[batch_result.player_id] = batch_result.result.target_player_id
                    elif valid_targets:
                        votes[batch_result.player_id] = random.choice(valid_targets)
                elif valid_targets:
                    votes[batch_result.player_id] = random.choice(valid_targets)
        else:
            for player in state.game_state.get_alive_players():
                agent = state.agents.get(player.id)
                if not agent:
                    continue

                valid_targets = get_valid_vote_targets(state.game_state, player.id)

                try:
                    game_view = self.build_game_view(
                        state.game_state,
                        player.id,
                        {"valid_targets": valid_targets},
                    )
                    result = agent.decide_vote(game_view)

                    if isinstance(result, VoteOutput):
                        if result.target_player_id in valid_targets:
                            votes[player.id] = result.target_player_id
                        elif valid_targets:
                            votes[player.id] = random.choice(valid_targets)
                except Exception as e:
                    logger.warning(f"Vote failed for {player.id}: {e}")
                    if valid_targets:
                        votes[player.id] = random.choice(valid_targets)

        new_game_state, vote_result = resolve_vote(state.game_state, votes)
        state.game_state = new_game_state
        self._add_events_to_buffer(state, vote_result.events)

        self._update_all_agents_memory_after_vote(state, votes)

        if self._game_logger:
            for voter_id, target_id in votes.items():
                voter = state.game_state.get_player(voter_id)
                target = state.game_state.get_player(target_id)
                self._game_logger.log_vote(
                    voter_id,
                    voter.name if voter else voter_id,
                    target_id,
                    target.name if target else target_id,
                    state.game_state.day_number,
                )
            
            lynched_name = None
            if vote_result.lynched_player_id:
                lynched = state.game_state.get_player(vote_result.lynched_player_id)
                lynched_name = lynched.name if lynched else None
            
            self._game_logger.log_vote_result(
                votes,
                vote_result.vote_counts,
                vote_result.lynched_player_id,
                lynched_name,
            )

        if vote_result.lynched_player_id:
            state = self._handle_lynch(state, vote_result.lynched_player_id)

        return state

    def _handle_lynch(
        self, state: OrchestratorState, lynched_player_id: str
    ) -> OrchestratorState:
        lynched = state.game_state.get_player(lynched_player_id)
        was_sheriff = lynched.is_sheriff if lynched else False

        new_game_state, events = resolve_lynch(state.game_state, lynched_player_id)
        state.game_state = new_game_state
        self._add_events_to_buffer(state, events)

        lynched = state.game_state.get_player(lynched_player_id)

        if lynched and lynched.role == Role.VILLAGE_IDIOT and lynched.village_idiot_revealed:
            return state

        if lynched and not lynched.is_alive:
            if self._game_logger:
                self._game_logger.log_death(
                    lynched.id,
                    lynched.name,
                    lynched.role.value,
                    "lynched",
                )
            
            state = self._handle_last_words(state, lynched.id)

            if lynched.role == Role.HUNTER and lynched.hunter_can_shoot:
                state = self._handle_hunter_shot(state, lynched.id)

            if was_sheriff:
                state = self._handle_badge_decision(state, lynched.id)

        return state

    def _handle_last_words(
        self, state: OrchestratorState, player_id: str
    ) -> OrchestratorState:
        """Handle a dying player's last words.
        
        According to rules:
        - First night deaths get last words (only on Day 1)
        - Lynched players always get last words
        - Players killed by Hunter do NOT get last words
        """
        player = state.game_state.get_player(player_id)
        if not player:
            return state

        agent = state.agents.get(player_id)
        if not agent:
            return state

        try:
            game_view = self.build_game_view(
                state.game_state,
                player_id,
                {"giving_last_words": True, "is_dying": True},
            )
            
            if isinstance(agent, HumanPlayerAgent):
                result = agent.decide_last_words(game_view)
                content = result.content if isinstance(result, LastWordsOutput) else str(result)
            else:
                result = agent.decide_day_speech(game_view)
                content = result.content if isinstance(result, SpeechOutput) else str(result)

            if content:
                content = self._truncate_content(content)
                event = SpeechEvent(
                    day_number=state.game_state.day_number,
                    phase=Phase.DAY,
                    actor_id=player_id,
                    data={"content": content, "is_last_words": True},
                )
                state.game_state.add_event(event)
                self._add_event_to_buffer(state, event)
        except Exception as e:
            logger.warning(f"Last words failed for {player_id}: {e}")

        return state

    def _handle_hunter_shot(
        self, state: OrchestratorState, hunter_id: str
    ) -> OrchestratorState:
        hunter = state.game_state.get_player(hunter_id)
        if not hunter or not hunter.hunter_can_shoot:
            return state

        agent = state.agents.get(hunter_id)
        if not agent:
            return state

        valid_targets = get_valid_hunter_targets(state.game_state, hunter_id)

        try:
            game_view = self.build_game_view(
                state.game_state,
                hunter_id,
                {"valid_targets": valid_targets, "dying": True},
            )

            result = None
            try:
                if isinstance(agent, HumanPlayerAgent):
                    raw_result = agent.decide_hunter_shot(game_view)
                else:
                    raw_result = agent.decide_night_action(game_view)
                if isinstance(raw_result, HunterShootOutput):
                    result = raw_result
            except Exception:
                pass

            target_id = None
            if isinstance(result, HunterShootOutput) and result.shoot:
                target_id = result.target_player_id

            if target_id and target_id in valid_targets:
                action = HunterShootAction(actor_id=hunter_id, target_id=target_id)
                new_game_state, events = resolve_hunter_shot(state.game_state, action)
                state.game_state = new_game_state
                self._add_events_to_buffer(state, events)
                
                target = state.game_state.get_player(target_id)
                if target and self._game_logger:
                    self._game_logger.log_death(
                        target_id,
                        target.name,
                        target.role.value,
                        "hunter_shot",
                    )

        except Exception as e:
            logger.warning(f"Hunter shot failed: {e}")

        return state

    def _handle_badge_decision(
        self, state: OrchestratorState, sheriff_id: str
    ) -> OrchestratorState:
        agent = state.agents.get(sheriff_id)
        if not agent:
            return state

        alive_players = [
            p.id for p in state.game_state.get_alive_players() if p.id != sheriff_id
        ]

        try:
            game_view = self.build_game_view(
                state.game_state,
                sheriff_id,
                {"valid_targets": alive_players, "dying_as_sheriff": True},
            )
            result = agent.decide_badge_pass(game_view)

            if isinstance(result, BadgeDecisionOutput):
                if result.action == "pass" and result.target_player_id in alive_players:
                    action = PassBadgeAction(
                        actor_id=sheriff_id,
                        target_id=result.target_player_id,
                    )
                else:
                    action = TearBadgeAction(actor_id=sheriff_id)

                new_game_state, events = resolve_badge_action(state.game_state, action)
                state.game_state = new_game_state
                self._add_events_to_buffer(state, events)

        except Exception as e:
            logger.warning(f"Badge decision failed: {e}")

        return state

    def _run_day_phase(self, state: OrchestratorState) -> OrchestratorState:
        state.game_state = advance_to_day(state.game_state)

        if state.game_state.day_number >= MAX_GAME_DAYS:
            state.game_state.winning_team = WinningTeam.WEREWOLF
            state.game_state.phase = Phase.GAME_OVER
            return state

        alive_count = len(state.game_state.get_alive_players())
        if self._game_logger:
            self._game_logger.log_phase_change(
                state.game_state.day_number, "day", alive_count
            )

        if state.game_state.day_number == 1:
            state = self._run_sheriff_election(state)

        deaths = state.night_deaths
        narration = state.moderator.announce_day_start(state.game_state, deaths)
        self._add_narration(state, narration)

        death_events = []
        for death_id in deaths:
            event = DeathAnnouncementEvent(
                day_number=state.game_state.day_number,
                phase=Phase.DAY,
                target_id=death_id,
            )
            state.game_state.add_event(event)
            self._add_event_to_buffer(state, event)
            death_events.append(event)
            
            player = state.game_state.get_player(death_id)
            if player and self._game_logger:
                self._game_logger.log_death(
                    death_id,
                    player.name,
                    player.role.value,
                    "night_kill",
                )

            if state.game_state.day_number == 1 and state.game_state.config.rule_variants.first_night_death_has_last_words:
                state = self._handle_last_words(state, death_id)

            if player and player.role == Role.HUNTER and player.hunter_can_shoot:
                state = self._handle_hunter_shot(state, death_id)

        if death_events:
            self._update_all_agents_memory_after_night(state, death_events)

        state.game_state = update_win_condition(state.game_state)
        if state.game_state.is_game_over():
            return state

        state = self._run_day_speeches(state)
        state = self._run_day_vote(state)

        state.game_state = update_win_condition(state.game_state)

        return state

    def _check_game_end(self, state: OrchestratorState) -> bool:
        return state.game_state.is_game_over()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(GraphState)

        def night_node(state: GraphState) -> GraphState:
            orch_state = OrchestratorState.from_dict(state)
            orch_state = self._run_night_phase(orch_state)
            self._game_state = orch_state.game_state
            return cast(GraphState, orch_state.to_dict())

        def day_node(state: GraphState) -> GraphState:
            orch_state = OrchestratorState.from_dict(state)
            orch_state = self._run_day_phase(orch_state)
            self._game_state = orch_state.game_state
            return cast(GraphState, orch_state.to_dict())

        def transition_to_night_node(state: GraphState) -> GraphState:
            orch_state = OrchestratorState.from_dict(state)
            orch_state.game_state = advance_to_night(orch_state.game_state)
            orch_state.night_deaths = []
            self._game_state = orch_state.game_state
            return cast(GraphState, orch_state.to_dict())

        def check_win_node(state: GraphState) -> GraphState:
            orch_state = OrchestratorState.from_dict(state)
            orch_state.game_state = update_win_condition(orch_state.game_state)
            self._game_state = orch_state.game_state
            return cast(GraphState, orch_state.to_dict())

        graph.add_node("night", night_node)
        graph.add_node("day", day_node)
        graph.add_node("transition_to_night", transition_to_night_node)
        graph.add_node("check_win", check_win_node)

        def route_after_night(state: GraphState) -> str:
            if self._stop_requested:
                return END
            return "day"

        def route_after_day(state: GraphState) -> str:
            if self._stop_requested:
                return END
            if OrchestratorState.from_dict(state).game_state.is_game_over():
                return END
            return "transition_to_night"

        def route_after_transition(state: GraphState) -> str:
            if self._stop_requested:
                return END
            return "check_win"

        def route_after_check_win(state: GraphState) -> str:
            if self._stop_requested:
                return END
            if OrchestratorState.from_dict(state).game_state.is_game_over():
                return END
            return "night"

        graph.add_conditional_edges("night", route_after_night)
        graph.add_conditional_edges("day", route_after_day)
        graph.add_conditional_edges("transition_to_night", route_after_transition)
        graph.add_conditional_edges("check_win", route_after_check_win)

        graph.set_entry_point("night")

        return graph

    def _init_logging(self, game_state: GameState) -> None:
        self._game_logger = create_game_logger(
            game_id=self._game_id,
            log_level=self._log_level,
            output_path=self._output_path,
            enable_console=self._enable_console_logging,
            enable_file=self._enable_file_logging,
        )
        
        self._game_log = create_game_log(
            game_id=self._game_id,
            config=self.config.model_dump(),
            role_set=self.config.role_set,
            random_seed=self.config.random_seed,
            model_config_info={
                "backend": self.agent_models.default.backend.value,
                "model_name": self.agent_models.default.model_name,
            },
        )
        
        for player in game_state.players:
            self._game_log.players.append(
                PlayerLog(
                    id=player.id,
                    name=player.name,
                    seat_number=player.seat_number,
                    role=player.role.value,
                    alignment=player.alignment.value,
                    is_alive=player.is_alive,
                    is_sheriff=player.is_sheriff,
                )
            )
        
        players_info = [
            {"id": p.id, "name": p.name, "seat": p.seat_number, "role": p.role.value}
            for p in game_state.players
        ]
        self._game_logger.log_game_start(self.config, players_info)

    def _log_event(self, event: Event, game_state: GameState) -> None:
        if not self._game_logger or not self._game_log:
            return
        
        self._game_logger.log_event(event, game_state)
        self._game_log.add_event(
            event_type=event.event_type.value,
            day_number=event.day_number,
            phase=event.phase.value,
            actor_id=event.actor_id,
            target_id=event.target_id,
            data=event.data,
            public=event.public,
        )

    def _finalize_game_log(self, final_state: GameState, narration_log: list[str]) -> None:
        if not self._game_log:
            return
        
        self._game_log.set_result(
            winning_team=final_state.winning_team,
            final_day=final_state.day_number,
        )
        self._game_log.narration_log = narration_log
        
        for player in final_state.players:
            for p_log in self._game_log.players:
                if p_log.id == player.id:
                    p_log.is_alive = player.is_alive
                    p_log.is_sheriff = player.is_sheriff
                    break
        
        if self._game_logger:
            survivors = [
                {"name": p.name, "role": p.role.value}
                for p in final_state.players if p.is_alive
            ]
            self._game_logger.log_game_end(
                winning_team=final_state.winning_team.value,
                final_day=final_state.day_number,
                survivors=survivors,
            )

    def save_game_log(self, path: Path) -> None:
        if self._game_log:
            save_game_log(self._game_log, path)

    def run_game(self) -> GameResult:
        self._game_state = self._initialize_game()
        self._agents = self._create_agents(self._game_state)
        self._moderator = self._create_moderator()
        
        if self.performance_config.enable_batching:
            self._batch_executor = self._create_batch_executor()
        
        self._init_logging(self._game_state)

        initial_state = OrchestratorState(
            game_state=self._game_state,
            agents=self._agents,
            moderator=self._moderator,
        )

        graph = self._build_graph()
        compiled_graph = graph.compile()

        final_state_dict = None
        run_config = {"recursion_limit": MAX_GAME_DAYS * 5}
        for state_dict in compiled_graph.stream(initial_state.to_dict(), config=run_config):  # type: ignore[arg-type]
            final_state_dict = state_dict

        if final_state_dict:
            last_key = list(final_state_dict.keys())[-1]
            final_data = final_state_dict[last_key]
            final_state = OrchestratorState.from_dict(final_data)
            
            for event in final_data.get("events_buffer", []):
                self._log_event(event, final_state.game_state)
        else:
            final_state = initial_state

        if not self.performance_config.skip_narration:
            narration = self._moderator.announce_game_end(final_state.game_state)
            self._add_narration(final_state, narration)
        
        self._finalize_game_log(final_state.game_state, final_state.narration_log)

        if self._batch_executor:
            self._batch_executor.shutdown()

        return GameResult(
            winning_team=final_state.game_state.winning_team,
            final_state=final_state.game_state,
            events=final_state.events_buffer,
            narration_log=final_state.narration_log,
            game_log=self._game_log,
        )
