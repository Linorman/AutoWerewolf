from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Optional
from enum import Enum

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class FactType(str, Enum):
    ROLE_CLAIM = "role_claim"
    SEER_CHECK = "seer_check"
    VOTE_CAST = "vote_cast"
    SPEECH_SUMMARY = "speech_summary"
    DEATH = "death"
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"
    TRUSTED_PLAYER = "trusted_player"
    WEREWOLF_TARGET = "werewolf_target"
    PROTECTION = "protection"
    POTION_USED = "potion_used"


@dataclass
class GameFact:
    fact_type: FactType
    day_number: int
    player_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    is_private: bool = False


class GameFactMemory:
    def __init__(self, owner_id: str, max_facts: int = 100):
        self.owner_id = owner_id
        self._facts: list[GameFact] = []
        self._max_facts = max_facts
        self._compressed_summary: str = ""

    def add_fact(self, fact: GameFact) -> None:
        self._facts.append(fact)
        if len(self._facts) > self._max_facts:
            self._compress_old_facts()

    def add_role_claim(
        self,
        day_number: int,
        player_id: str,
        claimed_role: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.ROLE_CLAIM,
            day_number=day_number,
            player_id=player_id,
            content=f"Player {player_id} claimed to be {claimed_role}",
            metadata={"claimed_role": claimed_role},
        ))

    def add_seer_check(
        self,
        day_number: int,
        target_id: str,
        result: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.SEER_CHECK,
            day_number=day_number,
            player_id=target_id,
            content=f"Checked {target_id}: {result}",
            metadata={"result": result},
            is_private=True,
        ))

    def add_vote(
        self,
        day_number: int,
        voter_id: str,
        target_id: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.VOTE_CAST,
            day_number=day_number,
            player_id=voter_id,
            content=f"Player {voter_id} voted for {target_id}",
            metadata={"target_id": target_id},
        ))

    def add_speech_summary(
        self,
        day_number: int,
        player_id: str,
        summary: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.SPEECH_SUMMARY,
            day_number=day_number,
            player_id=player_id,
            content=summary,
        ))

    def add_death(
        self,
        day_number: int,
        player_id: str,
        death_type: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.DEATH,
            day_number=day_number,
            player_id=player_id,
            content=f"Player {player_id} died ({death_type})",
            metadata={"death_type": death_type},
        ))

    def add_suspicious_behavior(
        self,
        day_number: int,
        player_id: str,
        reason: str,
    ) -> None:
        self.add_fact(GameFact(
            fact_type=FactType.SUSPICIOUS_BEHAVIOR,
            day_number=day_number,
            player_id=player_id,
            content=reason,
        ))

    def get_facts(
        self,
        fact_type: Optional[FactType] = None,
        player_id: Optional[str] = None,
        day_number: Optional[int] = None,
        include_private: bool = True,
    ) -> list[GameFact]:
        facts = self._facts
        if fact_type:
            facts = [f for f in facts if f.fact_type == fact_type]
        if player_id:
            facts = [f for f in facts if f.player_id == player_id]
        if day_number:
            facts = [f for f in facts if f.day_number == day_number]
        if not include_private:
            facts = [f for f in facts if not f.is_private]
        return facts

    def get_recent_facts(self, limit: int = 10) -> list[GameFact]:
        return self._facts[-limit:]

    def to_context_string(self, include_private: bool = True) -> str:
        parts = []
        if self._compressed_summary:
            parts.append(f"[Historical Summary]\n{self._compressed_summary}")
        
        facts = self._facts if include_private else [f for f in self._facts if not f.is_private]
        if facts:
            lines = [f"[Day {fact.day_number}] {fact.content}" for fact in facts]
            parts.append("[Recent Events]\n" + "\n".join(lines))
        
        return "\n\n".join(parts) if parts else "No recorded facts."

    def get_voting_patterns(self, player_id: str) -> list[tuple[int, str]]:
        votes = self.get_facts(fact_type=FactType.VOTE_CAST, player_id=player_id)
        return [(v.day_number, v.metadata.get("target_id", "unknown")) for v in votes]

    def _compress_old_facts(self) -> None:
        keep_count = self._max_facts // 2
        old_facts = self._facts[:-keep_count]
        self._facts = self._facts[-keep_count:]
        
        summary_parts = []
        by_day: dict[int, list[str]] = {}
        for fact in old_facts:
            if fact.day_number not in by_day:
                by_day[fact.day_number] = []
            by_day[fact.day_number].append(fact.content)
        
        for day_num in sorted(by_day.keys()):
            day_facts = by_day[day_num]
            if len(day_facts) > 3:
                summary_parts.append(f"Day {day_num}: {len(day_facts)} events recorded")
            else:
                summary_parts.extend([f"[Day {day_num}] {f}" for f in day_facts])
        
        if self._compressed_summary:
            self._compressed_summary = f"{self._compressed_summary}\n{chr(10).join(summary_parts)}"
        else:
            self._compressed_summary = "\n".join(summary_parts)

    def get_compressed_summary(self) -> str:
        return self._compressed_summary

    def clear(self) -> None:
        self._facts = []
        self._compressed_summary = ""


class WerewolfCampMemory:
    def __init__(self):
        self._werewolf_ids: list[str] = []
        self._kill_history: list[tuple[int, str]] = []
        self._discussion_notes: list[dict[str, Any]] = []
        self._strategies: list[str] = []
        self._confirmed_good_players: list[str] = []
        self._suspected_roles: dict[str, str] = {}

    def set_werewolf_ids(self, werewolf_ids: list[str]) -> None:
        self._werewolf_ids = werewolf_ids

    def get_werewolf_ids(self) -> list[str]:
        return self._werewolf_ids.copy()

    def add_kill(self, night_number: int, target_id: str) -> None:
        self._kill_history.append((night_number, target_id))

    def get_kill_history(self) -> list[tuple[int, str]]:
        return self._kill_history.copy()

    def add_discussion_note(
        self,
        night_number: int,
        werewolf_id: str,
        content: str,
    ) -> None:
        self._discussion_notes.append({
            "night_number": night_number,
            "werewolf_id": werewolf_id,
            "content": content,
        })

    def add_strategy(self, strategy: str) -> None:
        self._strategies.append(strategy)

    def mark_confirmed_good(self, player_id: str) -> None:
        if player_id not in self._confirmed_good_players:
            self._confirmed_good_players.append(player_id)

    def set_suspected_role(self, player_id: str, role: str) -> None:
        self._suspected_roles[player_id] = role

    def get_suspected_role(self, player_id: str) -> Optional[str]:
        return self._suspected_roles.get(player_id)

    def to_context_string(self) -> str:
        lines = [
            f"Fellow werewolves: {', '.join(self._werewolf_ids)}",
        ]
        if self._kill_history:
            kills = [f"Night {n}: {t}" for n, t in self._kill_history]
            lines.append(f"Kill history: {'; '.join(kills)}")
        if self._confirmed_good_players:
            lines.append(f"Confirmed good players: {', '.join(self._confirmed_good_players)}")
        if self._suspected_roles:
            roles = [f"{p}: {r}" for p, r in self._suspected_roles.items()]
            lines.append(f"Suspected roles: {'; '.join(roles)}")
        if self._strategies:
            lines.append(f"Strategies: {'; '.join(self._strategies[-3:])}")
        return "\n".join(lines)


class ConversationMemory:
    def __init__(self, max_messages: int = 20):
        self._messages: list[dict[str, str]] = []
        self._max_messages = max_messages

    def add_message(self, role: Literal["human", "ai"], content: str) -> None:
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]

    def get_messages(self) -> list[dict[str, str]]:
        return self._messages.copy()

    def to_context_string(self) -> str:
        if not self._messages:
            return ""
        lines = []
        for msg in self._messages:
            prefix = "You said" if msg["role"] == "ai" else "Context"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._messages = []


class AgentMemory:
    def __init__(
        self,
        owner_id: str,
        memory_type: Literal["buffer", "summary"] = "buffer",
        max_facts: int = 100,
        summary_threshold: int = 50,
    ):
        self.owner_id = owner_id
        self.memory_type = memory_type
        self.facts = GameFactMemory(owner_id, max_facts=max_facts)
        self.conversation = ConversationMemory()
        self._summary: str = ""
        self._summary_threshold = summary_threshold
        self._summarizer: Optional["BaseChatModel"] = None

    def set_summarizer(self, chat_model: "BaseChatModel") -> None:
        self._summarizer = chat_model

    def update_after_speech(
        self,
        day_number: int,
        player_id: str,
        speech_content: str,
    ) -> None:
        summary = speech_content[:200] + "..." if len(speech_content) > 200 else speech_content
        self.facts.add_speech_summary(day_number, player_id, summary)
        self._maybe_compress()

    def update_after_vote(
        self,
        day_number: int,
        voter_id: str,
        target_id: str,
    ) -> None:
        self.facts.add_vote(day_number, voter_id, target_id)

    def update_after_night(
        self,
        day_number: int,
        visible_events: list[dict[str, Any]],
    ) -> None:
        for event in visible_events:
            event_type = event.get("type", "")
            if event_type == "death":
                self.facts.add_death(
                    day_number,
                    event.get("player_id", ""),
                    event.get("death_type", "unknown"),
                )
        self._maybe_compress()

    def _maybe_compress(self) -> None:
        if self.memory_type == "summary" and len(self.facts._facts) > self._summary_threshold:
            self._generate_summary()

    def _generate_summary(self) -> None:
        if not self._summarizer:
            return
        
        current_context = self.facts.to_context_string()
        if len(current_context) < 500:
            return
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content="Summarize the following game events concisely. Focus on key information: deaths, suspicious behaviors, role claims, and voting patterns. Keep it under 300 words."),
                HumanMessage(content=current_context),
            ]
            result = self._summarizer.invoke(messages)
            self._summary = str(result.content)
        except Exception:
            pass

    def update_summary(self, new_summary: str) -> None:
        self._summary = new_summary

    def get_summary(self) -> str:
        return self._summary

    def to_context_string(self) -> str:
        parts = []
        
        compressed = self.facts.get_compressed_summary()
        if compressed:
            parts.append(f"Historical Summary:\n{compressed}")
        
        if self._summary and self.memory_type == "summary":
            parts.append(f"Game Summary:\n{self._summary}")
        
        fact_context = self.facts.to_context_string()
        if fact_context != "No recorded facts.":
            parts.append(f"Known Facts:\n{fact_context}")
        
        conv_context = self.conversation.to_context_string()
        if conv_context:
            parts.append(f"Recent Context:\n{conv_context}")
        
        return "\n\n".join(parts) if parts else ""

    def get_context_length(self) -> int:
        return len(self.to_context_string())


def create_agent_memory(
    owner_id: str,
    memory_type: Literal["buffer", "summary"] = "buffer",
) -> AgentMemory:
    return AgentMemory(owner_id, memory_type)


def create_werewolf_camp_memory() -> WerewolfCampMemory:
    return WerewolfCampMemory()
