import pytest

from autowerewolf.agents.memory import (
    AgentMemory,
    ConversationMemory,
    FactType,
    GameFact,
    GameFactMemory,
    WerewolfCampMemory,
    create_agent_memory,
    create_werewolf_camp_memory,
)
from autowerewolf.engine.roles import Alignment


class TestGameFact:
    def test_create_fact(self):
        fact = GameFact(
            fact_type=FactType.ROLE_CLAIM,
            day_number=1,
            player_id="p1",
            content="Player p1 claimed to be Seer",
        )
        assert fact.fact_type == FactType.ROLE_CLAIM
        assert fact.day_number == 1
        assert fact.player_id == "p1"
        assert fact.is_private is False

    def test_create_private_fact(self):
        fact = GameFact(
            fact_type=FactType.SEER_CHECK,
            day_number=1,
            player_id="p2",
            content="Checked p2: WEREWOLF",
            is_private=True,
        )
        assert fact.is_private is True


class TestGameFactMemory:
    def test_add_fact(self):
        memory = GameFactMemory("p1")
        fact = GameFact(
            fact_type=FactType.SPEECH_SUMMARY,
            day_number=1,
            player_id="p2",
            content="P2 gave a suspicious speech",
        )
        memory.add_fact(fact)
        assert len(memory.get_facts()) == 1

    def test_add_role_claim(self):
        memory = GameFactMemory("p1")
        memory.add_role_claim(1, "p2", "Seer")
        
        facts = memory.get_facts(fact_type=FactType.ROLE_CLAIM)
        assert len(facts) == 1
        assert "Seer" in facts[0].content

    def test_add_seer_check(self):
        memory = GameFactMemory("p1")
        memory.add_seer_check(1, "p2", "WEREWOLF")
        
        facts = memory.get_facts(fact_type=FactType.SEER_CHECK)
        assert len(facts) == 1
        assert facts[0].is_private is True

    def test_add_vote(self):
        memory = GameFactMemory("p1")
        memory.add_vote(1, "p2", "p3")
        
        facts = memory.get_facts(fact_type=FactType.VOTE_CAST)
        assert len(facts) == 1
        assert facts[0].metadata["target_id"] == "p3"

    def test_filter_by_day(self):
        memory = GameFactMemory("p1")
        memory.add_speech_summary(1, "p2", "Day 1 speech")
        memory.add_speech_summary(2, "p2", "Day 2 speech")
        
        facts = memory.get_facts(day_number=1)
        assert len(facts) == 1

    def test_filter_by_player(self):
        memory = GameFactMemory("p1")
        memory.add_speech_summary(1, "p2", "P2 speech")
        memory.add_speech_summary(1, "p3", "P3 speech")
        
        facts = memory.get_facts(player_id="p2")
        assert len(facts) == 1

    def test_exclude_private_facts(self):
        memory = GameFactMemory("p1")
        memory.add_speech_summary(1, "p2", "Public fact")
        memory.add_seer_check(1, "p3", "WEREWOLF")
        
        facts = memory.get_facts(include_private=False)
        assert len(facts) == 1

    def test_get_recent_facts(self):
        memory = GameFactMemory("p1")
        for i in range(15):
            memory.add_speech_summary(1, f"p{i}", f"Speech {i}")
        
        recent = memory.get_recent_facts(limit=5)
        assert len(recent) == 5

    def test_to_context_string(self):
        memory = GameFactMemory("p1")
        memory.add_role_claim(1, "p2", "Seer")
        
        context = memory.to_context_string()
        assert "Day 1" in context
        assert "Seer" in context

    def test_get_voting_patterns(self):
        memory = GameFactMemory("p1")
        memory.add_vote(1, "p2", "p3")
        memory.add_vote(2, "p2", "p4")
        
        patterns = memory.get_voting_patterns("p2")
        assert len(patterns) == 2
        assert (1, "p3") in patterns

    def test_clear(self):
        memory = GameFactMemory("p1")
        memory.add_role_claim(1, "p2", "Seer")
        memory.clear()
        
        assert len(memory.get_facts()) == 0


class TestWerewolfCampMemory:
    def test_set_werewolf_ids(self):
        memory = WerewolfCampMemory()
        memory.set_werewolf_ids(["p1", "p2", "p3", "p4"])
        
        assert memory.get_werewolf_ids() == ["p1", "p2", "p3", "p4"]

    def test_add_kill(self):
        memory = WerewolfCampMemory()
        memory.add_kill(1, "p5")
        memory.add_kill(2, "p6")
        
        history = memory.get_kill_history()
        assert len(history) == 2
        assert (1, "p5") in history

    def test_add_discussion_note(self):
        memory = WerewolfCampMemory()
        memory.add_discussion_note(1, "p1", "I suggest killing p5")
        
        context = memory.to_context_string()
        assert "kill" not in context.lower() or "p5" not in context

    def test_mark_confirmed_good(self):
        memory = WerewolfCampMemory()
        memory.mark_confirmed_good("p5")
        memory.mark_confirmed_good("p5")
        
        context = memory.to_context_string()
        assert "p5" in context

    def test_suspected_roles(self):
        memory = WerewolfCampMemory()
        memory.set_suspected_role("p5", "Seer")
        
        assert memory.get_suspected_role("p5") == "Seer"
        assert memory.get_suspected_role("p6") is None

    def test_to_context_string(self):
        memory = WerewolfCampMemory()
        memory.set_werewolf_ids(["p1", "p2"])
        memory.add_kill(1, "p5")
        memory.mark_confirmed_good("p6")
        memory.set_suspected_role("p7", "Witch")
        
        context = memory.to_context_string()
        assert "p1" in context
        assert "p2" in context
        assert "Night 1: p5" in context
        assert "p6" in context
        assert "p7" in context


class TestConversationMemory:
    def test_add_message(self):
        memory = ConversationMemory()
        memory.add_message("human", "What happened last night?")
        memory.add_message("ai", "Player 5 was killed.")
        
        messages = memory.get_messages()
        assert len(messages) == 2

    def test_max_messages(self):
        memory = ConversationMemory(max_messages=3)
        for i in range(5):
            memory.add_message("human", f"Message {i}")
        
        messages = memory.get_messages()
        assert len(messages) == 3

    def test_to_context_string(self):
        memory = ConversationMemory()
        memory.add_message("human", "Context message")
        memory.add_message("ai", "AI response")
        
        context = memory.to_context_string()
        assert "Context message" in context
        assert "AI response" in context

    def test_clear(self):
        memory = ConversationMemory()
        memory.add_message("human", "Test")
        memory.clear()
        
        assert len(memory.get_messages()) == 0


class TestAgentMemory:
    def test_create_agent_memory(self):
        memory = create_agent_memory("p1", "buffer")
        assert memory.owner_id == "p1"
        assert memory.memory_type == "buffer"

    def test_update_after_speech(self):
        memory = AgentMemory("p1")
        memory.update_after_speech(1, "p2", "Test speech content")
        
        facts = memory.facts.get_facts(fact_type=FactType.SPEECH_SUMMARY)
        assert len(facts) == 1

    def test_update_after_vote(self):
        memory = AgentMemory("p1")
        memory.update_after_vote(1, "p2", "p3")
        
        facts = memory.facts.get_facts(fact_type=FactType.VOTE_CAST)
        assert len(facts) == 1

    def test_update_after_night(self):
        memory = AgentMemory("p1")
        events = [
            {"type": "death", "player_id": "p5", "death_type": "werewolf_kill"}
        ]
        memory.update_after_night(1, events)
        
        facts = memory.facts.get_facts(fact_type=FactType.DEATH)
        assert len(facts) == 1

    def test_to_context_string(self):
        memory = AgentMemory("p1")
        memory.update_after_speech(1, "p2", "Test speech")
        memory.conversation.add_message("human", "Test context")
        
        context = memory.to_context_string()
        assert "Test speech" in context
        assert "Test context" in context

    def test_summary_mode(self):
        memory = AgentMemory("p1", "summary")
        memory.update_summary("Day 1: Nothing major happened")
        
        context = memory.to_context_string()
        assert "Day 1" in context


class TestCreateFunctions:
    def test_create_agent_memory(self):
        memory = create_agent_memory("p1")
        assert isinstance(memory, AgentMemory)

    def test_create_werewolf_camp_memory(self):
        memory = create_werewolf_camp_memory()
        assert isinstance(memory, WerewolfCampMemory)
