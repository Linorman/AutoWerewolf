from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, Field

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import SeerNightOutput, SpeechOutput, VoteOutput
from autowerewolf.engine.roles import Alignment, Role


class SeerRevealDecision(BaseModel):
    should_reveal: bool = Field(description="Whether to reveal check result this turn")
    reveal_target_id: Optional[str] = Field(default=None, description="Player ID to reveal info about")
    reveal_result: Optional[str] = Field(default=None, description="The result to announce (good/werewolf)")


class SeerAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are the SEER. You are the most important information role for the village.

ABILITIES:
- Each night, you can check ONE player to learn if they are good or a werewolf
- Your information is crucial for the village's victory

TERMINOLOGY:
- "Gold water": A player you verified as GOOD
- "Checked kill": A player you verified as WEREWOLF
- "Silver water": A player saved by Witch (less reliable than your checks)

NIGHT STRATEGY:
- Check players who are active in discussions but hard to read
- Avoid checking obvious targets on Night 1 (too predictable)
- Balance checking suspected werewolves vs. finding trustworthy allies

DAY STRATEGY:
- Revealing early may get you killed, but your info dies with you if you wait too long
- If you found a werewolf, consider revealing to save the village
- If you found good players, they can vouch for you and vice versa
- Fake seers (werewolves) will claim conflicting results - be prepared to counter

SURVIVAL TIPS:
- Consider not claiming seer on Day 1 unless necessary
- If you claim, provide specific check results to prove credibility
- Build a trust network with verified good players"""

    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        chat_model: BaseChatModel,
        memory: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(player_id, player_name, role, chat_model, memory, **kwargs)
        self.check_history: list[tuple[str, Alignment]] = []

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def add_check_result(self, player_id: str, alignment: Alignment) -> None:
        self.check_history.append((player_id, alignment))

    def get_check_history_str(self) -> str:
        if not self.check_history:
            return "No checks performed yet"
        lines = []
        for pid, alignment in self.check_history:
            result = "WEREWOLF" if alignment == Alignment.WEREWOLF else "GOOD"
            lines.append(f"  - {pid}: {result}")
        return "\n".join(lines)

    def _build_night_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your previous check results:
{check_history}

Select a player to check tonight. Consider:
- Who has been most active but unclear in their alignment?
- Who haven't you checked yet?
- Checking a suspected werewolf can confirm suspicions
- Checking a trusted player can establish allies"""),
        ])
        return prompt | self.chat_model.with_structured_output(SeerNightOutput)

    def decide_night_action(self, game_view: GameView) -> SeerNightOutput:
        context = game_view.to_prompt_context()
        check_history = self.get_check_history_str()
        return self.night_chain.invoke({"context": context, "check_history": check_history})

    def decide_reveal(self, game_view: GameView) -> SeerRevealDecision:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your check results:
{check_history}

Decide whether to reveal any information this turn:
- If you have a checked werewolf, revealing may save the village
- If you're under suspicion, revealing your checks may clear your name
- If the village is losing, your information is critical
- Be cautious about revealing verified good players (makes them targets)"""),
        ])
        chain = prompt | self.chat_model.with_structured_output(SeerRevealDecision)
        context = game_view.to_prompt_context()
        check_history = self.get_check_history_str()
        result: SeerRevealDecision = chain.invoke({"context": context, "check_history": check_history})  # type: ignore
        return result

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your check results:
{check_history}

Deliver your day speech. Options:
- Claim Seer and reveal your checks (risky but informative)
- Hint at your role without fully claiming
- Stay low and gather information
- Counter any fake seer claims with your real results"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def decide_day_speech(self, game_view: GameView) -> SpeechOutput:
        context = game_view.to_prompt_context()
        check_history = self.get_check_history_str()
        return self.speech_chain.invoke({"context": context, "check_history": check_history})

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your check results:
{check_history}

Cast your vote. Priority:
1. Vote for players you've confirmed as werewolves
2. Support voting out players identified by other trusted roles
3. Avoid voting for players you've verified as good"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    def decide_vote(self, game_view: GameView) -> VoteOutput:
        context = game_view.to_prompt_context()
        check_history = self.get_check_history_str()
        return self.vote_chain.invoke({"context": context, "check_history": check_history})
