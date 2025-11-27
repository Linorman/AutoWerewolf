import pytest
from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.runnables import RunnableLambda

from autowerewolf.agents.player_base import (
    BasePlayerAgent,
    GameView,
    create_player_agent,
)
from autowerewolf.agents.roles import (
    VillagerAgent,
    WerewolfAgent,
    SeerAgent,
    WitchAgent,
    HunterAgent,
    GuardAgent,
    VillageIdiotAgent,
)
from autowerewolf.agents.moderator import ModeratorChain, NarrationOutput
from autowerewolf.agents.schemas import (
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    SeerNightOutput,
    WitchNightOutput,
    GuardNightOutput,
    SheriffDecisionOutput,
    BadgeDecisionOutput,
)
from autowerewolf.engine.roles import Role


class MockChatModel:
    def __init__(self, response: Any):
        self._response = response

    def with_structured_output(self, schema: Any) -> RunnableLambda:
        return RunnableLambda(lambda x: self._response)


def create_mock_game_view(role: Role = Role.VILLAGER) -> GameView:
    return GameView(
        player_id="p1",
        player_name="Player1",
        role=role,
        phase="day",
        day_number=1,
        alive_players=[
            {"id": "p1", "name": "Player1", "seat_number": 1, "is_sheriff": False},
            {"id": "p2", "name": "Player2", "seat_number": 2, "is_sheriff": True},
            {"id": "p3", "name": "Player3", "seat_number": 3, "is_sheriff": False},
        ],
        public_history=[
            {"description": "Game started"},
            {"description": "Night 1 passed"},
        ],
        private_info={"checked_players": ["p2: good"]},
        action_context={"can_vote": True},
    )


class TestGameView:
    def test_to_prompt_context_contains_player_info(self):
        view = create_mock_game_view()
        context = view.to_prompt_context()

        assert "Player1" in context
        assert "p1" in context
        assert "villager" in context
        assert "day" in context
        assert "Day 1" in context

    def test_to_prompt_context_lists_alive_players(self):
        view = create_mock_game_view()
        context = view.to_prompt_context()

        assert "Player1" in context
        assert "Player2" in context
        assert "Player3" in context
        assert "[Sheriff]" in context

    def test_to_prompt_context_includes_private_info(self):
        view = create_mock_game_view()
        context = view.to_prompt_context()

        assert "checked_players" in context
        assert "p2: good" in context

    def test_to_prompt_context_includes_action_context(self):
        view = create_mock_game_view()
        context = view.to_prompt_context()

        assert "can_vote" in context

    def test_to_prompt_context_includes_history(self):
        view = create_mock_game_view()
        context = view.to_prompt_context()

        assert "Game started" in context
        assert "Night 1 passed" in context


class TestVillagerAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        assert "VILLAGER" in agent.role_system_prompt
        assert "no special abilities" in agent.role_system_prompt

    def test_decide_day_speech(self):
        expected = SpeechOutput(content="I think Player2 is suspicious")
        mock_model = MockChatModel(expected)
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        view = create_mock_game_view()
        result = agent.decide_day_speech(view)

        assert result == expected

    def test_decide_vote(self):
        expected = VoteOutput(target_player_id="p2", reasoning="Suspicious behavior")
        mock_model = MockChatModel(expected)
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        view = create_mock_game_view()
        result = agent.decide_vote(view)

        assert result == expected


class TestWerewolfAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(WerewolfNightOutput(kill_target_id="p2"))
        agent = WerewolfAgent("p1", "Player1", Role.WEREWOLF, mock_model)

        assert "WEREWOLF" in agent.role_system_prompt
        assert "Eliminate all villagers" in agent.role_system_prompt

    def test_decide_night_action(self):
        expected = WerewolfNightOutput(kill_target_id="p3", self_explode=False)
        mock_model = MockChatModel(expected)
        agent = WerewolfAgent("p1", "Player1", Role.WEREWOLF, mock_model)

        view = create_mock_game_view(Role.WEREWOLF)
        result = agent.decide_night_action(view)

        assert result == expected


class TestSeerAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(SeerNightOutput(check_target_id="p2"))
        agent = SeerAgent("p1", "Player1", Role.SEER, mock_model)

        assert "SEER" in agent.role_system_prompt
        assert "check" in agent.role_system_prompt.lower()

    def test_decide_night_action(self):
        expected = SeerNightOutput(check_target_id="p2")
        mock_model = MockChatModel(expected)
        agent = SeerAgent("p1", "Player1", Role.SEER, mock_model)

        view = create_mock_game_view(Role.SEER)
        result = agent.decide_night_action(view)

        assert result == expected


class TestWitchAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgent("p1", "Player1", Role.WITCH, mock_model)

        assert "WITCH" in agent.role_system_prompt
        assert "CURE" in agent.role_system_prompt
        assert "POISON" in agent.role_system_prompt

    def test_decide_night_action_use_cure(self):
        expected = WitchNightOutput(use_cure=True, use_poison=False)
        mock_model = MockChatModel(expected)
        agent = WitchAgent("p1", "Player1", Role.WITCH, mock_model)  # type: ignore

        view = create_mock_game_view(Role.WITCH)
        result = agent.decide_night_action(view)
        witch_result: WitchNightOutput = result  # type: ignore

        assert witch_result.use_cure is True
        assert witch_result.use_poison is False


class TestGuardAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(GuardNightOutput(protect_target_id="p2"))
        agent = GuardAgent("p1", "Player1", Role.GUARD, mock_model)

        assert "GUARD" in agent.role_system_prompt
        assert "protect" in agent.role_system_prompt

    def test_decide_night_action(self):
        expected = GuardNightOutput(protect_target_id="p2")
        mock_model = MockChatModel(expected)
        agent = GuardAgent("p1", "Player1", Role.GUARD, mock_model)

        view = create_mock_game_view(Role.GUARD)
        result = agent.decide_night_action(view)

        assert result == expected


class TestHunterAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = HunterAgent("p1", "Player1", Role.HUNTER, mock_model)

        assert "HUNTER" in agent.role_system_prompt
        assert "shoot" in agent.role_system_prompt


class TestVillageIdiotAgent:
    def test_role_system_prompt(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillageIdiotAgent("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)

        assert "VILLAGE IDIOT" in agent.role_system_prompt
        assert "LYNCHED" in agent.role_system_prompt


class TestCreatePlayerAgent:
    @pytest.mark.parametrize("role,agent_class", [
        (Role.VILLAGER, VillagerAgent),
        (Role.WEREWOLF, WerewolfAgent),
        (Role.SEER, SeerAgent),
        (Role.WITCH, WitchAgent),
        (Role.HUNTER, HunterAgent),
        (Role.GUARD, GuardAgent),
        (Role.VILLAGE_IDIOT, VillageIdiotAgent),
    ])
    def test_creates_correct_agent_type(self, role, agent_class):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = create_player_agent("p1", "Player1", role, mock_model)

        assert isinstance(agent, agent_class)

    def test_sets_player_attributes(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = create_player_agent("p1", "TestPlayer", Role.VILLAGER, mock_model)

        assert agent.player_id == "p1"
        assert agent.player_name == "TestPlayer"
        assert agent.role == Role.VILLAGER


class TestSheriffDecisions:
    def test_decide_sheriff_run(self):
        expected = SheriffDecisionOutput(run_for_sheriff=True)
        mock_model = MockChatModel(expected)
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        view = create_mock_game_view()
        result = agent.decide_sheriff_run(view)

        assert result.run_for_sheriff is True

    def test_decide_badge_pass(self):
        expected = BadgeDecisionOutput(action="pass", target_player_id="p2")
        mock_model = MockChatModel(expected)
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        view = create_mock_game_view()
        result = agent.decide_badge_pass(view)

        assert result.action == "pass"
        assert result.target_player_id == "p2"

    def test_decide_badge_tear(self):
        expected = BadgeDecisionOutput(action="tear", target_player_id=None)
        mock_model = MockChatModel(expected)
        agent = VillagerAgent("p1", "Player1", Role.VILLAGER, mock_model)

        view = create_mock_game_view()
        result = agent.decide_badge_pass(view)

        assert result.action == "tear"


class TestModeratorChain:
    def test_announce_night_start(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        from autowerewolf.engine.state import GameState

        state = GameState(day_number=1)
        result = moderator.announce_night_start(state)

        assert "Night 1" in result
        assert "close their eyes" in result

    def test_announce_day_start_no_deaths(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        from autowerewolf.engine.state import GameState

        state = GameState(day_number=1)
        result = moderator.announce_day_start(state, [])

        assert "Day 1" in result
        assert "No one died" in result

    def test_announce_sheriff_election(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        result = moderator.announce_sheriff_election()

        assert "sheriff" in result.lower()

    def test_announce_voting_start(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        result = moderator.announce_voting_start()

        assert "vote" in result.lower()

    def test_announce_game_end_village_wins(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        from autowerewolf.engine.state import GameState
        from autowerewolf.engine.roles import WinningTeam

        state = GameState(winning_team=WinningTeam.VILLAGE)
        result = moderator.announce_game_end(state)

        assert "village wins" in result.lower()

    def test_announce_game_end_werewolf_wins(self):
        mock_model = MockChatModel(NarrationOutput(narration="test"))
        moderator = ModeratorChain(mock_model)

        from autowerewolf.engine.state import GameState
        from autowerewolf.engine.roles import WinningTeam

        state = GameState(winning_team=WinningTeam.WEREWOLF)
        result = moderator.announce_game_end(state)

        assert "werewolves" in result.lower()
