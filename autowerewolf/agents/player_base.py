from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from autowerewolf.agents.prompts import (
    PromptKey,
    get_base_system_prompt,
    get_prompt,
    get_role_system_prompt,
)
from autowerewolf.agents.schemas import (
    BadgeDecisionOutput,
    LastWordsOutput,
    NightActionOutput,
    SheriffDecisionOutput,
    SpeechOutput,
    VoteOutput,
)
from autowerewolf.config.performance import VerbosityLevel
from autowerewolf.engine.roles import Role

if TYPE_CHECKING:
    from autowerewolf.agents.memory import AgentMemory
    from autowerewolf.agents.output_corrector import OutputCorrector


class GameView:
    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        phase: str,
        day_number: int,
        alive_players: list[dict[str, Any]],
        public_history: list[dict[str, Any]],
        private_info: Optional[dict[str, Any]] = None,
        action_context: Optional[dict[str, Any]] = None,
    ):
        self.player_id = player_id
        self.player_name = player_name
        self.role = role
        self.phase = phase
        self.day_number = day_number
        self.alive_players = alive_players
        self.public_history = public_history
        self.private_info = private_info or {}
        self.action_context = action_context or {}

    def to_prompt_context(self) -> str:
        lines = [
            f"You are Player {self.player_name} (ID: {self.player_id})",
            f"Your role: {self.role.value}",
            f"Current phase: {self.phase} (Day {self.day_number})",
            "",
            "Alive players:",
        ]
        for p in self.alive_players:
            sheriff_mark = " [Sheriff]" if p.get("is_sheriff") else ""
            lines.append(f"  - {p['name']} (ID: {p['id']}, Seat: {p.get('seat_number', '?')}){sheriff_mark}")

        if self.private_info:
            lines.append("")
            lines.append("Your private information:")
            for key, value in self.private_info.items():
                lines.append(f"  - {key}: {value}")

        if self.action_context:
            lines.append("")
            lines.append("Action context:")
            for key, value in self.action_context.items():
                lines.append(f"  - {key}: {value}")

        if self.public_history:
            lines.append("")
            lines.append("Recent public events:")
            for event in self.public_history[-10:]:
                lines.append(f"  - {event.get('description', str(event))}")

        return "\n".join(lines)


class BasePlayerAgent(ABC):
    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        chat_model: BaseChatModel,
        memory: Optional["AgentMemory"] = None,
        verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
        output_corrector: Optional["OutputCorrector"] = None,
    ):
        self.player_id = player_id
        self.player_name = player_name
        self.role = role
        self.chat_model = chat_model
        self.memory = memory
        self.verbosity = verbosity
        self.output_corrector = output_corrector
        self._night_chain: Optional[RunnableSerializable] = None
        self._speech_chain: Optional[RunnableSerializable] = None
        self._vote_chain: Optional[RunnableSerializable] = None
        self._last_words_chain: Optional[RunnableSerializable] = None

    def _get_memory_context(self) -> str:
        if self.memory is None:
            return ""
        return self.memory.to_context_string()

    def update_memory_after_speech(
        self,
        day_number: int,
        player_id: str,
        speech_content: str,
    ) -> None:
        if self.memory:
            self.memory.update_after_speech(day_number, player_id, speech_content)

    def update_memory_after_vote(
        self,
        day_number: int,
        voter_id: str,
        target_id: str,
    ) -> None:
        if self.memory:
            self.memory.update_after_vote(day_number, voter_id, target_id)

    def update_memory_after_night(
        self,
        day_number: int,
        visible_events: list[dict[str, Any]],
    ) -> None:
        if self.memory:
            self.memory.update_after_night(day_number, visible_events)

    @property
    def role_system_prompt(self) -> str:
        return get_role_system_prompt(self.role, self.verbosity)

    @property
    def base_system_prompt(self) -> str:
        return get_base_system_prompt(self.verbosity)

    def _get_night_action_schema(self) -> type:
        from autowerewolf.agents.schemas import (
            GuardNightOutput,
            SeerNightOutput,
            WerewolfNightOutput,
            WitchNightOutput,
        )

        role_schemas = {
            Role.WEREWOLF: WerewolfNightOutput,
            Role.SEER: SeerNightOutput,
            Role.WITCH: WitchNightOutput,
            Role.GUARD: GuardNightOutput,
        }
        return role_schemas.get(self.role, WerewolfNightOutput)

    def _build_night_chain(self) -> RunnableSerializable:
        schema = self._get_night_action_schema()
        human_template = get_prompt(PromptKey.NIGHT_ACTION, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        return prompt | self.chat_model.with_structured_output(schema)

    def _build_speech_chain(self) -> RunnableSerializable:
        human_template = get_prompt(PromptKey.SPEECH, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def _build_vote_chain(self) -> RunnableSerializable:
        human_template = get_prompt(PromptKey.VOTE, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    @property
    def night_chain(self) -> RunnableSerializable:
        if self._night_chain is None:
            self._night_chain = self._build_night_chain()
        return self._night_chain

    @property
    def speech_chain(self) -> RunnableSerializable:
        if self._speech_chain is None:
            self._speech_chain = self._build_speech_chain()
        return self._speech_chain

    @property
    def vote_chain(self) -> RunnableSerializable:
        if self._vote_chain is None:
            self._vote_chain = self._build_vote_chain()
        return self._vote_chain

    def _build_context_with_memory(self, game_view: GameView) -> str:
        context = game_view.to_prompt_context()
        memory_context = self._get_memory_context()
        if memory_context:
            context = f"{context}\n\nYour memory:\n{memory_context}"
        return context

    def _invoke_with_correction(
        self,
        chain: RunnableSerializable,
        input_data: dict[str, Any],
        schema_class: type,
        context: str,
    ) -> Any:
        from pydantic import ValidationError
        
        try:
            return chain.invoke(input_data)
        except ValidationError as e:
            if self.output_corrector and self.output_corrector.enabled:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Output validation failed for {schema_class.__name__}, attempting correction")
                
                raw_content = self._extract_raw_input_from_error(e)
                
                corrected = self.output_corrector.correct_output(
                    original_output=raw_content,
                    schema_class=schema_class,
                    validation_error=e,
                    context=context,
                )
                
                if corrected is not None:
                    return corrected
            
            raise
    
    def _extract_raw_input_from_error(self, error: Any) -> Any:
        errors = error.errors()
        if errors:
            first_error = errors[0]
            if 'input' in first_error:
                return first_error['input']
        
        return str(error)

    def decide_night_action(self, game_view: GameView) -> NightActionOutput:
        context = self._build_context_with_memory(game_view)
        schema = self._get_night_action_schema()
        return self._invoke_with_correction(
            self.night_chain,
            {"context": context},
            schema,
            context,
        )

    def decide_day_speech(self, game_view: GameView) -> SpeechOutput:
        context = self._build_context_with_memory(game_view)
        return self._invoke_with_correction(
            self.speech_chain,
            {"context": context},
            SpeechOutput,
            context,
        )

    def decide_vote(self, game_view: GameView) -> VoteOutput:
        context = self._build_context_with_memory(game_view)
        return self._invoke_with_correction(
            self.vote_chain,
            {"context": context},
            VoteOutput,
            context,
        )

    def decide_sheriff_run(self, game_view: GameView) -> SheriffDecisionOutput:
        human_template = get_prompt(PromptKey.SHERIFF_RUN, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        chain = prompt | self.chat_model.with_structured_output(SheriffDecisionOutput)
        context = self._build_context_with_memory(game_view)
        return self._invoke_with_correction(
            chain,
            {"context": context},
            SheriffDecisionOutput,
            context,
        )

    def decide_badge_pass(self, game_view: GameView) -> BadgeDecisionOutput:
        human_template = get_prompt(PromptKey.BADGE_PASS, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        chain = prompt | self.chat_model.with_structured_output(BadgeDecisionOutput)
        context = self._build_context_with_memory(game_view)
        return self._invoke_with_correction(
            chain,
            {"context": context},
            BadgeDecisionOutput,
            context,
        )

    def _build_last_words_chain(self) -> RunnableSerializable:
        human_template = get_prompt(PromptKey.LAST_WORDS, self.verbosity)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", human_template),
        ])
        return prompt | self.chat_model.with_structured_output(LastWordsOutput)

    @property
    def last_words_chain(self) -> RunnableSerializable:
        if self._last_words_chain is None:
            self._last_words_chain = self._build_last_words_chain()
        return self._last_words_chain

    def decide_last_words(self, game_view: GameView) -> LastWordsOutput:
        context = self._build_context_with_memory(game_view)
        return self._invoke_with_correction(
            self.last_words_chain,
            {"context": context},
            LastWordsOutput,
            context,
        )


def create_player_agent(
    player_id: str,
    player_name: str,
    role: Role,
    chat_model: BaseChatModel,
    memory: Optional[Any] = None,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    output_corrector: Optional["OutputCorrector"] = None,
) -> BasePlayerAgent:
    """Create a player agent for the given role.
    
    This function uses lazy imports to avoid circular import issues.
    
    Args:
        player_id: Unique identifier for the player
        player_name: Display name for the player
        role: The role assigned to this player
        chat_model: The LLM model for agent decisions
        memory: Optional memory manager for the agent
        verbosity: Verbosity level for prompts
        output_corrector: Optional output corrector for fixing malformed outputs
    """
    # Lazy import to avoid circular imports
    from autowerewolf.agents.roles import ROLE_AGENT_MAP, VillagerAgent
    
    agent_cls = ROLE_AGENT_MAP.get(role, VillagerAgent)
    return agent_cls(
        player_id=player_id,
        player_name=player_name,
        role=role,
        chat_model=chat_model,
        memory=memory,
        verbosity=verbosity,
        output_corrector=output_corrector,
    )
