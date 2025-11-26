import pytest
from typing import Any, Optional
from unittest.mock import MagicMock

from langchain_core.runnables import RunnableLambda

from autowerewolf.agents.roles import (
    GuardAgent,
    HunterAgent,
    SeerAgent,
    SeerRevealDecision,
    VillageIdiotAgent,
    VillageIdiotRevealDecision,
    VillagerAgent,
    WerewolfAgent,
    WerewolfDiscussionChain,
    SelfExplodeDecision,
    WitchAgent,
    ROLE_AGENT_MAP,
)
from autowerewolf.agents.roles.guard import GuardAgent as GuardAgentDirect
from autowerewolf.agents.roles.hunter import HunterAgent as HunterAgentDirect
from autowerewolf.agents.roles.seer import SeerAgent as SeerAgentDirect
from autowerewolf.agents.roles.village_idiot import VillageIdiotAgent as VillageIdiotAgentDirect
from autowerewolf.agents.roles.villager import VillagerAgent as VillagerAgentDirect
from autowerewolf.agents.roles.werewolf import WerewolfAgent as WerewolfAgentDirect
from autowerewolf.agents.roles.witch import WitchAgent as WitchAgentDirect
from autowerewolf.agents.player_base import GameView
from autowerewolf.agents.schemas import (
    GuardNightOutput,
    HunterShootOutput,
    SeerNightOutput,
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    WerewolfProposalOutput,
    WitchNightOutput,
)
from autowerewolf.engine.roles import Alignment, Role


class MockChatModel:
    def __init__(self, response: Any):
        self._response = response

    def with_structured_output(self, schema: Any) -> RunnableLambda:
        return RunnableLambda(lambda x: self._response)


def create_game_view(role: Role = Role.VILLAGER) -> GameView:
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
            {"id": "p4", "name": "Player4", "seat_number": 4, "is_sheriff": False},
        ],
        public_history=[{"description": "Game started"}],
    )


class TestWerewolfAgentRole:
    def test_role_prompt_contains_objectives(self):
        mock_model = MockChatModel(WerewolfNightOutput(kill_target_id="p2"))
        agent = WerewolfAgentDirect("p1", "Player1", Role.WEREWOLF, mock_model)
        
        assert "WEREWOLF" in agent.role_system_prompt
        assert "self-knife" in agent.role_system_prompt.lower()
        assert "self-explode" in agent.role_system_prompt.lower()

    def test_set_werewolf_teammates(self):
        mock_model = MockChatModel(WerewolfNightOutput(kill_target_id="p2"))
        agent = WerewolfAgentDirect("p1", "Player1", Role.WEREWOLF, mock_model)
        
        agent.set_werewolf_teammates(["p1", "p2", "p3", "p4"])
        
        assert "p1" not in agent.werewolf_teammates
        assert "p2" in agent.werewolf_teammates
        assert "p3" in agent.werewolf_teammates

    def test_decide_night_action_returns_kill_target(self):
        expected = WerewolfNightOutput(kill_target_id="p3", self_explode=False)
        mock_model = MockChatModel(expected)
        agent = WerewolfAgentDirect("p1", "Player1", Role.WEREWOLF, mock_model)
        
        view = create_game_view(Role.WEREWOLF)
        result = agent.decide_night_action(view)
        
        assert result.kill_target_id == "p3"
        assert result.self_explode is False

    def test_decide_self_explode(self):
        from pydantic import BaseModel, Field
        
        class SelfExplodeDecision(BaseModel):
            should_explode: bool = Field(description="Whether to self-explode")
        
        mock_response = SelfExplodeDecision(should_explode=True)
        mock_model = MockChatModel(mock_response)
        agent = WerewolfAgentDirect("p1", "Player1", Role.WEREWOLF, mock_model)
        
        view = create_game_view(Role.WEREWOLF)
        result = agent.decide_self_explode(view)
        
        assert result is True


class TestVillagerAgentRole:
    def test_role_prompt_contains_objectives(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillagerAgentDirect("p1", "Player1", Role.VILLAGER, mock_model)
        
        assert "VILLAGER" in agent.role_system_prompt
        assert "no special abilities" in agent.role_system_prompt.lower()

    def test_decide_day_speech(self):
        expected = SpeechOutput(content="I suspect Player2")
        mock_model = MockChatModel(expected)
        agent = VillagerAgentDirect("p1", "Player1", Role.VILLAGER, mock_model)
        
        view = create_game_view(Role.VILLAGER)
        result = agent.decide_day_speech(view)
        
        assert result.content == "I suspect Player2"

    def test_decide_vote(self):
        expected = VoteOutput(target_player_id="p2", reasoning="Suspicious behavior")
        mock_model = MockChatModel(expected)
        agent = VillagerAgentDirect("p1", "Player1", Role.VILLAGER, mock_model)
        
        view = create_game_view(Role.VILLAGER)
        result = agent.decide_vote(view)
        
        assert result.target_player_id == "p2"


class TestSeerAgentRole:
    def test_role_prompt_contains_abilities(self):
        mock_model = MockChatModel(SeerNightOutput(check_target_id="p2"))
        agent = SeerAgentDirect("p1", "Player1", Role.SEER, mock_model)
        
        assert "SEER" in agent.role_system_prompt
        assert "gold water" in agent.role_system_prompt.lower()
        assert "check" in agent.role_system_prompt.lower()

    def test_add_check_result(self):
        mock_model = MockChatModel(SeerNightOutput(check_target_id="p2"))
        agent = SeerAgentDirect("p1", "Player1", Role.SEER, mock_model)
        
        agent.add_check_result("p2", Alignment.GOOD)
        agent.add_check_result("p3", Alignment.WEREWOLF)
        
        assert len(agent.check_history) == 2
        assert agent.check_history[0] == ("p2", Alignment.GOOD)
        assert agent.check_history[1] == ("p3", Alignment.WEREWOLF)

    def test_get_check_history_str(self):
        mock_model = MockChatModel(SeerNightOutput(check_target_id="p2"))
        agent = SeerAgentDirect("p1", "Player1", Role.SEER, mock_model)
        
        agent.add_check_result("p2", Alignment.GOOD)
        history_str = agent.get_check_history_str()
        
        assert "p2" in history_str
        assert "GOOD" in history_str

    def test_decide_reveal(self):
        expected = SeerRevealDecision(
            should_reveal=True,
            reveal_target_id="p3",
            reveal_result="werewolf"
        )
        mock_model = MockChatModel(expected)
        agent = SeerAgentDirect("p1", "Player1", Role.SEER, mock_model)
        
        view = create_game_view(Role.SEER)
        result = agent.decide_reveal(view)
        
        assert result.should_reveal is True
        assert result.reveal_target_id == "p3"


class TestWitchAgentRole:
    def test_role_prompt_contains_potions(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        assert "WITCH" in agent.role_system_prompt
        assert "CURE" in agent.role_system_prompt
        assert "POISON" in agent.role_system_prompt

    def test_initial_potion_state(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        assert agent.has_cure is True
        assert agent.has_poison is True

    def test_use_cure(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        agent.use_cure()
        
        assert agent.has_cure is False
        assert agent.has_poison is True

    def test_use_poison(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        agent.use_poison()
        
        assert agent.has_cure is True
        assert agent.has_poison is False

    def test_get_potion_status(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        status = agent.get_potion_status()
        assert "AVAILABLE" in status
        
        agent.use_cure()
        status = agent.get_potion_status()
        assert "USED" in status

    def test_validate_action_no_cure(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        agent.use_cure()
        
        action = WitchNightOutput(use_cure=True, use_poison=False)
        validated = agent.validate_action(action)
        
        assert validated.use_cure is False

    def test_validate_action_both_potions_blocked(self):
        mock_model = MockChatModel(WitchNightOutput())
        agent = WitchAgentDirect("p1", "Player1", Role.WITCH, mock_model)
        
        action = WitchNightOutput(use_cure=True, use_poison=True, poison_target_id="p2")
        validated = agent.validate_action(action)
        
        assert validated.use_cure is True
        assert validated.use_poison is False


class TestHunterAgentRole:
    def test_role_prompt_contains_abilities(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = HunterAgentDirect("p1", "Player1", Role.HUNTER, mock_model)
        
        assert "HUNTER" in agent.role_system_prompt
        assert "shoot" in agent.role_system_prompt.lower()
        assert "poison" in agent.role_system_prompt.lower()

    def test_initial_can_shoot(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = HunterAgentDirect("p1", "Player1", Role.HUNTER, mock_model)
        
        assert agent.can_shoot is True

    def test_set_can_shoot(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = HunterAgentDirect("p1", "Player1", Role.HUNTER, mock_model)
        
        agent.set_can_shoot(False)
        
        assert agent.can_shoot is False

    def test_decide_shoot_cannot_shoot(self):
        mock_model = MockChatModel(HunterShootOutput(shoot=True, target_player_id="p2"))
        agent = HunterAgentDirect("p1", "Player1", Role.HUNTER, mock_model)
        agent.set_can_shoot(False)
        
        view = create_game_view(Role.HUNTER)
        result = agent.decide_shoot(view)
        
        assert result.shoot is False
        assert result.target_player_id is None

    def test_decide_shoot_can_shoot(self):
        expected = HunterShootOutput(shoot=True, target_player_id="p3")
        mock_model = MockChatModel(expected)
        agent = HunterAgentDirect("p1", "Player1", Role.HUNTER, mock_model)
        
        view = create_game_view(Role.HUNTER)
        result = agent.decide_shoot(view)
        
        assert result.shoot is True
        assert result.target_player_id == "p3"


class TestGuardAgentRole:
    def test_role_prompt_contains_abilities(self):
        mock_model = MockChatModel(GuardNightOutput(protect_target_id="p2"))
        agent = GuardAgentDirect("p1", "Player1", Role.GUARD, mock_model)
        
        assert "GUARD" in agent.role_system_prompt
        assert "protect" in agent.role_system_prompt.lower()
        assert "same player two nights" in agent.role_system_prompt.lower()

    def test_set_last_protected(self):
        mock_model = MockChatModel(GuardNightOutput(protect_target_id="p2"))
        agent = GuardAgentDirect("p1", "Player1", Role.GUARD, mock_model)
        
        agent.set_last_protected("p2")
        
        assert agent.last_protected == "p2"

    def test_get_valid_targets(self):
        mock_model = MockChatModel(GuardNightOutput(protect_target_id="p2"))
        agent = GuardAgentDirect("p1", "Player1", Role.GUARD, mock_model)
        agent.set_last_protected("p2")
        
        valid = agent.get_valid_targets(["p1", "p2", "p3", "p4"])
        
        assert "p2" not in valid
        assert "p1" in valid
        assert "p3" in valid

    def test_validate_action_same_target(self):
        mock_model = MockChatModel(GuardNightOutput(protect_target_id="p2"))
        agent = GuardAgentDirect("p1", "Player1", Role.GUARD, mock_model)
        agent.set_last_protected("p2")
        
        action = GuardNightOutput(protect_target_id="p2")
        validated = agent.validate_action(action, ["p1", "p2", "p3"])
        
        assert validated.protect_target_id != "p2"


class TestVillageIdiotAgentRole:
    def test_role_prompt_contains_abilities(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillageIdiotAgentDirect("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)
        
        assert "VILLAGE IDIOT" in agent.role_system_prompt
        assert "lynched" in agent.role_system_prompt.lower()
        assert "reveal" in agent.role_system_prompt.lower()

    def test_initial_state(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillageIdiotAgentDirect("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)
        
        assert agent.has_revealed is False
        assert agent.can_vote is True

    def test_reveal_identity(self):
        mock_model = MockChatModel(SpeechOutput(content="test"))
        agent = VillageIdiotAgentDirect("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)
        
        agent.reveal_identity()
        
        assert agent.has_revealed is True
        assert agent.can_vote is False

    def test_decide_reveal(self):
        expected = VillageIdiotRevealDecision(reveal=True)
        mock_model = MockChatModel(expected)
        agent = VillageIdiotAgentDirect("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)
        
        view = create_game_view(Role.VILLAGE_IDIOT)
        result = agent.decide_reveal(view)
        
        assert result.reveal is True

    def test_decide_vote_after_reveal(self):
        mock_model = MockChatModel(VoteOutput(target_player_id="p2"))
        agent = VillageIdiotAgentDirect("p1", "Player1", Role.VILLAGE_IDIOT, mock_model)
        agent.reveal_identity()
        
        view = create_game_view(Role.VILLAGE_IDIOT)
        result = agent.decide_vote(view)
        
        assert result is None


class TestRoleAgentMap:
    def test_all_roles_mapped(self):
        expected_roles = [
            Role.VILLAGER,
            Role.WEREWOLF,
            Role.SEER,
            Role.WITCH,
            Role.HUNTER,
            Role.GUARD,
            Role.VILLAGE_IDIOT,
        ]
        
        for role in expected_roles:
            assert role in ROLE_AGENT_MAP

    def test_agent_map_types(self):
        assert ROLE_AGENT_MAP[Role.VILLAGER] == VillagerAgent
        assert ROLE_AGENT_MAP[Role.WEREWOLF] == WerewolfAgent
        assert ROLE_AGENT_MAP[Role.SEER] == SeerAgent
        assert ROLE_AGENT_MAP[Role.WITCH] == WitchAgent
        assert ROLE_AGENT_MAP[Role.HUNTER] == HunterAgent
        assert ROLE_AGENT_MAP[Role.GUARD] == GuardAgent
        assert ROLE_AGENT_MAP[Role.VILLAGE_IDIOT] == VillageIdiotAgent


class TestWerewolfDiscussionChain:
    def test_get_proposals(self):
        proposal = WerewolfProposalOutput(
            target_player_id="p5",
            reasoning="P5 seems like the Seer"
        )
        mock_model = MockChatModel(proposal)
        
        wolf1 = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        wolf2 = WerewolfAgentDirect("p2", "Wolf2", Role.WEREWOLF, mock_model)
        
        chain = WerewolfDiscussionChain([wolf1, wolf2], mock_model)
        view = create_game_view(Role.WEREWOLF)
        
        proposals = chain.get_proposals(view)
        
        assert len(proposals) == 2
        assert proposals[0][0] == "p1"
        assert proposals[0][1].target_player_id == "p5"

    def test_reach_consensus(self):
        proposal = WerewolfProposalOutput(
            target_player_id="p5",
            reasoning="Test"
        )
        mock_model = MockChatModel(proposal)
        
        wolf1 = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        wolf2 = WerewolfAgentDirect("p2", "Wolf2", Role.WEREWOLF, mock_model)
        
        chain = WerewolfDiscussionChain([wolf1, wolf2], mock_model)
        view = create_game_view(Role.WEREWOLF)
        
        proposals = [
            ("p1", WerewolfProposalOutput(target_player_id="p5", reasoning="A")),
            ("p2", WerewolfProposalOutput(target_player_id="p5", reasoning="B")),
        ]
        
        consensus = chain.reach_consensus(view, proposals)
        
        assert consensus == "p5"

    def test_reach_consensus_split_vote(self):
        mock_model = MockChatModel(None)
        
        wolf1 = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        wolf2 = WerewolfAgentDirect("p2", "Wolf2", Role.WEREWOLF, mock_model)
        wolf3 = WerewolfAgentDirect("p3", "Wolf3", Role.WEREWOLF, mock_model)
        
        chain = WerewolfDiscussionChain([wolf1, wolf2, wolf3], mock_model)
        view = create_game_view(Role.WEREWOLF)
        
        proposals = [
            ("p1", WerewolfProposalOutput(target_player_id="p5", reasoning="A")),
            ("p2", WerewolfProposalOutput(target_player_id="p5", reasoning="B")),
            ("p3", WerewolfProposalOutput(target_player_id="p6", reasoning="C")),
        ]
        
        consensus = chain.reach_consensus(view, proposals)
        
        assert consensus == "p5"

    def test_run_full_discussion(self):
        proposal = WerewolfProposalOutput(
            target_player_id="p5",
            reasoning="Target the suspected Seer"
        )
        mock_model = MockChatModel(proposal)
        
        wolf1 = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        wolf2 = WerewolfAgentDirect("p2", "Wolf2", Role.WEREWOLF, mock_model)
        
        chain = WerewolfDiscussionChain([wolf1, wolf2], mock_model)
        view = create_game_view(Role.WEREWOLF)
        
        target = chain.run(view)
        
        assert target == "p5"

    def test_run_with_camp_memory(self):
        from autowerewolf.agents.memory import WerewolfCampMemory
        
        proposal = WerewolfProposalOutput(
            target_player_id="p5",
            reasoning="Target"
        )
        mock_model = MockChatModel(proposal)
        
        wolf1 = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        wolf2 = WerewolfAgentDirect("p2", "Wolf2", Role.WEREWOLF, mock_model)
        
        camp_memory = WerewolfCampMemory()
        chain = WerewolfDiscussionChain([wolf1, wolf2], mock_model, camp_memory)
        view = create_game_view(Role.WEREWOLF)
        
        target = chain.run(view)
        
        assert target == "p5"
        kill_history = camp_memory.get_kill_history()
        assert len(kill_history) == 1
        assert kill_history[0][1] == "p5"


class TestWerewolfProposal:
    def test_propose_kill_target(self):
        proposal = WerewolfProposalOutput(
            target_player_id="p5",
            reasoning="P5 is likely the Seer"
        )
        mock_model = MockChatModel(proposal)
        agent = WerewolfAgentDirect("p1", "Wolf1", Role.WEREWOLF, mock_model)
        
        view = create_game_view(Role.WEREWOLF)
        result = agent.propose_kill_target(view)
        
        assert result.target_player_id == "p5"
        assert "Seer" in result.reasoning
