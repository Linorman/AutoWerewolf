import random
from typing import Any, Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from autowerewolf.agents.player_base import GameView
from autowerewolf.agents.schemas import (
    GuardNightOutput,
    SeerNightOutput,
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    WitchNightOutput,
)
from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig
from autowerewolf.engine.roles import Role, RoleSet, WinningTeam
from autowerewolf.engine.state import GameConfig, RuleVariants
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator, GameResult


class MockChatModel(BaseChatModel):
    responses: dict[str, Any] = {}
    call_count: int = 0

    def __init__(self, responses: Optional[dict[str, Any]] = None, **kwargs: Any):
        super().__init__(**kwargs)
        object.__setattr__(self, "responses", responses or {})
        object.__setattr__(self, "call_count", 0)

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        object.__setattr__(self, "call_count", self.call_count + 1)
        content = '{"content": "I am a villager."}'
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def with_structured_output(self, schema: type, **kwargs: Any) -> Any:
        return MockStructuredChain(schema, self.responses)


class MockStructuredChain:
    def __init__(self, schema: type, responses: dict[str, Any]):
        self.schema = schema
        self.responses = responses

    def invoke(self, inputs: dict[str, Any]) -> Any:
        schema_name = self.schema.__name__

        if schema_name == "WerewolfNightOutput":
            target_id = self.responses.get("wolf_target", "p1")
            return WerewolfNightOutput(kill_target_id=target_id, self_explode=False)

        elif schema_name == "SeerNightOutput":
            target_id = self.responses.get("seer_target", "p1")
            return SeerNightOutput(check_target_id=target_id)

        elif schema_name == "WitchNightOutput":
            use_cure = self.responses.get("witch_cure", False)
            use_poison = self.responses.get("witch_poison", False)
            poison_target = self.responses.get("witch_poison_target")
            return WitchNightOutput(
                use_cure=use_cure,
                use_poison=use_poison,
                poison_target_id=poison_target,
            )

        elif schema_name == "GuardNightOutput":
            target_id = self.responses.get("guard_target", "p1")
            return GuardNightOutput(protect_target_id=target_id)

        elif schema_name == "SpeechOutput":
            content = self.responses.get("speech", "I have nothing to say.")
            return SpeechOutput(content=content)

        elif schema_name == "VoteOutput":
            target_id = self.responses.get("vote_target", "p1")
            return VoteOutput(target_player_id=target_id)

        elif schema_name == "SheriffDecisionOutput":
            from autowerewolf.agents.schemas import SheriffDecisionOutput
            run = self.responses.get("run_for_sheriff", False)
            return SheriffDecisionOutput(run_for_sheriff=run)

        elif schema_name == "BadgeDecisionOutput":
            from autowerewolf.agents.schemas import BadgeDecisionOutput
            return BadgeDecisionOutput(action="tear", target_player_id=None)

        elif schema_name == "HunterShootOutput":
            from autowerewolf.agents.schemas import HunterShootOutput
            target = self.responses.get("hunter_target")
            return HunterShootOutput(shoot=bool(target), target_player_id=target)

        elif schema_name == "NarrationOutput":
            from autowerewolf.agents.moderator import NarrationOutput
            return NarrationOutput(narration="The night has fallen.")

        return self.schema()


def create_mock_model_config() -> AgentModelConfig:
    return AgentModelConfig(
        default=ModelConfig(
            backend=ModelBackend.OLLAMA,
            model_name="mock",
            temperature=0.0,
            max_tokens=100,
        )
    )


def create_mock_game_config(seed: int = 42, role_set: RoleSet = RoleSet.A) -> GameConfig:
    return GameConfig(
        role_set=role_set,
        random_seed=seed,
        rule_variants=RuleVariants(),
    )


class TestGameOrchestrator:
    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_initialization(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        assert orchestrator.config == config
        assert orchestrator.agent_models == model_config

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_game_state_initialization(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config(seed=123)
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()

        assert len(game_state.players) == 12
        assert game_state.day_number == 0

        werewolves = game_state.get_werewolves()
        assert len(werewolves) == 4

        villagers = game_state.get_villagers()
        assert len(villagers) == 4

        specials = game_state.get_special_roles()
        assert len(specials) == 4

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_agent_creation(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()
        agents = orchestrator._create_agents(game_state)

        assert len(agents) == 12

        for player in game_state.players:
            assert player.id in agents
            assert agents[player.id].role == player.role

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_game_view_construction(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()
        player = game_state.players[0]

        game_view = orchestrator.build_game_view(game_state, player.id)

        assert game_view.player_id == player.id
        assert game_view.role == player.role
        assert len(game_view.alive_players) == 12

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_werewolf_private_info(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()

        wolf = None
        for p in game_state.players:
            if p.role == Role.WEREWOLF:
                wolf = p
                break

        assert wolf is not None

        game_view = orchestrator.build_game_view(game_state, wolf.id)

        assert "teammates" in game_view.private_info
        teammates = game_view.private_info["teammates"]
        assert len(teammates) == 3

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_seer_private_info(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()

        seer = None
        for p in game_state.players:
            if p.role == Role.SEER:
                seer = p
                break

        assert seer is not None

        game_view = orchestrator.build_game_view(game_state, seer.id)

        assert "check_results" in game_view.private_info

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_witch_private_info(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config()
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()

        witch = None
        for p in game_state.players:
            if p.role == Role.WITCH:
                witch = p
                break

        assert witch is not None

        game_view = orchestrator.build_game_view(game_state, witch.id)

        assert "has_cure" in game_view.private_info
        assert "has_poison" in game_view.private_info
        assert game_view.private_info["has_cure"] is True
        assert game_view.private_info["has_poison"] is True


class TestGameFlow:
    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_full_game_completes(self, mock_get_chat_model: MagicMock) -> None:
        mock_model = MockChatModel(
            responses={
                "speech": "I am innocent.",
                "run_for_sheriff": False,
            }
        )
        mock_get_chat_model.return_value = mock_model

        config = create_mock_game_config(seed=42)
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        result = orchestrator.run_game()

        assert isinstance(result, GameResult)
        assert result.winning_team in [WinningTeam.VILLAGE, WinningTeam.WEREWOLF]
        assert result.final_state is not None
        assert len(result.narration_log) > 0

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_game_result_structure(self, mock_get_chat_model: MagicMock) -> None:
        mock_model = MockChatModel(
            responses={
                "speech": "Test speech.",
                "run_for_sheriff": False,
            }
        )
        mock_get_chat_model.return_value = mock_model

        config = create_mock_game_config(seed=100)
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        result = orchestrator.run_game()

        assert result.final_state.players is not None
        assert len(result.final_state.players) == 12

        alive_count = len(result.final_state.get_alive_players())
        assert alive_count < 12

    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_reproducibility_with_seed(self, mock_get_chat_model: MagicMock) -> None:
        mock_model = MockChatModel(
            responses={
                "speech": "Seeded speech.",
                "run_for_sheriff": False,
            }
        )
        mock_get_chat_model.return_value = mock_model

        seed = 12345
        config1 = create_mock_game_config(seed=seed)
        config2 = create_mock_game_config(seed=seed)
        model_config = create_mock_model_config()

        orchestrator1 = GameOrchestrator(config=config1, agent_models=model_config)
        orchestrator2 = GameOrchestrator(config=config2, agent_models=model_config)

        game_state1 = orchestrator1._initialize_game()
        game_state2 = orchestrator2._initialize_game()

        roles1 = [(p.name, p.role.value) for p in game_state1.players]
        roles2 = [(p.name, p.role.value) for p in game_state2.players]

        assert roles1 == roles2


class TestErrorHandling:
    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_agent_error_recovery(self, mock_get_chat_model: MagicMock) -> None:
        class ErrorProneChain:
            def __init__(self, schema: type):
                self.schema = schema
                self.call_count = 0

            def invoke(self, inputs: dict[str, Any]) -> Any:
                self.call_count += 1
                if self.call_count % 5 == 0:
                    raise RuntimeError("Simulated error")

                schema_name = self.schema.__name__
                if schema_name == "WerewolfNightOutput":
                    return WerewolfNightOutput(kill_target_id="p1", self_explode=False)
                elif schema_name == "SeerNightOutput":
                    return SeerNightOutput(check_target_id="p1")
                elif schema_name == "WitchNightOutput":
                    return WitchNightOutput(use_cure=False, use_poison=False)
                elif schema_name == "GuardNightOutput":
                    return GuardNightOutput(protect_target_id="p1")
                elif schema_name == "SpeechOutput":
                    return SpeechOutput(content="Error recovery test.")
                elif schema_name == "VoteOutput":
                    return VoteOutput(target_player_id="p1")
                elif schema_name == "SheriffDecisionOutput":
                    from autowerewolf.agents.schemas import SheriffDecisionOutput
                    return SheriffDecisionOutput(run_for_sheriff=False)
                elif schema_name == "BadgeDecisionOutput":
                    from autowerewolf.agents.schemas import BadgeDecisionOutput
                    return BadgeDecisionOutput(action="tear")
                elif schema_name == "NarrationOutput":
                    from autowerewolf.agents.moderator import NarrationOutput
                    return NarrationOutput(narration="Error test narration.")
                return self.schema()

        class ErrorProneModel(BaseChatModel):
            error_count: int = 0

            @property
            def _llm_type(self) -> str:
                return "error_prone_mock"

            def _generate(
                self,
                messages: list[BaseMessage],
                stop: Optional[list[str]] = None,
                **kwargs: Any,
            ) -> ChatResult:
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content="{}"))]
                )

            def with_structured_output(self, schema: type, **kwargs: Any) -> Any:
                return ErrorProneChain(schema)

        mock_get_chat_model.return_value = ErrorProneModel()

        config = create_mock_game_config(seed=999)
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        result = orchestrator.run_game()

        assert result.winning_team in [WinningTeam.VILLAGE, WinningTeam.WEREWOLF]


class TestRoleSetB:
    @patch("autowerewolf.orchestrator.game_orchestrator.get_chat_model")
    def test_village_idiot_role_set(self, mock_get_chat_model: MagicMock) -> None:
        mock_get_chat_model.return_value = MockChatModel()

        config = create_mock_game_config(seed=42, role_set=RoleSet.B)
        model_config = create_mock_model_config()

        orchestrator = GameOrchestrator(
            config=config,
            agent_models=model_config,
        )

        game_state = orchestrator._initialize_game()

        village_idiots = game_state.get_players_by_role(Role.VILLAGE_IDIOT)
        assert len(village_idiots) == 1

        guards = game_state.get_players_by_role(Role.GUARD)
        assert len(guards) == 0
