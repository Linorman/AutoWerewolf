from typing import TYPE_CHECKING, Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, Field

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import (
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    WerewolfProposalOutput,
)
from autowerewolf.engine.roles import Role

if TYPE_CHECKING:
    from autowerewolf.agents.memory import WerewolfCampMemory


class WerewolfSelfExplodeOutput(WerewolfNightOutput):
    pass


class WerewolfAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are a WEREWOLF. Your team consists of 4 werewolves against 8 good players.

OBJECTIVES:
- Eliminate all villagers OR all special roles to win
- Avoid detection during the day phase
- Coordinate with fellow werewolves at night

NIGHT ACTIONS:
- Choose one player to kill (by consensus with your werewolf team)
- You may "self-knife" (kill a fellow werewolf) to create confusion
- You may "self-explode" during the day to end discussion immediately

DAY STRATEGY:
- Blend in with villagers and deflect suspicion
- You can claim any role (fake seer, fake guard, etc.)
- Support your werewolf teammates subtly
- Vote strategically to eliminate key village roles

TERMINOLOGY:
- "Knife": kill target
- "Self-knife": kill a fellow werewolf to fake innocence
- "Self-explode": sacrifice yourself to skip to night

Your fellow werewolves will be revealed to you through private_info."""

    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        chat_model: BaseChatModel,
        memory: Optional[Any] = None,
        werewolf_teammates: Optional[list[str]] = None,
        **kwargs: Any,
    ):
        super().__init__(player_id, player_name, role, chat_model, memory, **kwargs)
        self.werewolf_teammates = werewolf_teammates or []
        self._self_explode_chain: Optional[RunnableSerializable] = None

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def set_werewolf_teammates(self, teammate_ids: list[str]) -> None:
        self.werewolf_teammates = [tid for tid in teammate_ids if tid != self.player_id]

    def _build_night_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your werewolf teammates: {teammates}

Select a player to kill tonight. You may also choose to self-knife (kill a teammate) if strategically beneficial.
Set self_explode=true ONLY if you want to reveal yourself and end the day immediately (you will die)."""),
        ])
        return prompt | self.chat_model.with_structured_output(WerewolfNightOutput)

    def decide_night_action(self, game_view: GameView) -> WerewolfNightOutput:
        context = game_view.to_prompt_context()
        teammates_info = ", ".join(self.werewolf_teammates) if self.werewolf_teammates else "Unknown"
        return self.night_chain.invoke({"context": context, "teammates": teammates_info})

    def decide_self_explode(self, game_view: GameView) -> bool:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

The situation is critical. Should you self-explode to end today's discussion and skip to night?
This will reveal you as a werewolf and kill you, but saves your team from a bad vote.
Respond with just true or false."""),
        ])

        from pydantic import BaseModel, Field

        class SelfExplodeDecision(BaseModel):
            should_explode: bool = Field(description="Whether to self-explode")

        chain = prompt | self.chat_model.with_structured_output(SelfExplodeDecision)
        context = game_view.to_prompt_context()
        result: SelfExplodeDecision = chain.invoke({"context": context})  # type: ignore
        return result.should_explode

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Deliver your day speech. Remember:
- Act like a villager, deflect suspicion from yourself and teammates
- Consider claiming a role if necessary
- Analyze others' behavior and cast suspicion on good players
- Be convincing and strategic"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Cast your vote. Strategy:
- Target confirmed or suspected special roles (Seer is high priority)
- Follow village consensus to blend in, unless you can swing the vote
- Avoid voting for fellow werewolves unless necessary for cover
- Consider the vote weight if someone is sheriff"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    def propose_kill_target(self, game_view: GameView) -> WerewolfProposalOutput:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Your werewolf teammates: {teammates}

Propose a kill target for tonight. Consider:
- Who is most dangerous to the werewolf team (Seer, active village leaders)?
- Who is less likely to be protected by Guard?
- Strategic value of the target

Provide your proposal with reasoning."""),
        ])
        chain = prompt | self.chat_model.with_structured_output(WerewolfProposalOutput)
        context = game_view.to_prompt_context()
        teammates_info = ", ".join(self.werewolf_teammates) if self.werewolf_teammates else "Unknown"
        result = chain.invoke({
            "context": context,
            "teammates": teammates_info,
        })
        return result  # type: ignore


class SelfExplodeDecision(BaseModel):
    should_explode: bool = Field(description="Whether to self-explode")


class WerewolfDiscussionChain:
    def __init__(
        self,
        werewolf_agents: list[WerewolfAgent],
        chat_model: BaseChatModel,
        camp_memory: Optional["WerewolfCampMemory"] = None,
    ):
        self.werewolf_agents = werewolf_agents
        self.chat_model = chat_model
        self.camp_memory = camp_memory
        self._consensus_chain: Optional[RunnableSerializable] = None

    def get_proposals(self, game_view: GameView) -> list[tuple[str, WerewolfProposalOutput]]:
        proposals = []
        for agent in self.werewolf_agents:
            proposal = agent.propose_kill_target(game_view)
            proposals.append((agent.player_id, proposal))
        return proposals

    def reach_consensus(
        self,
        game_view: GameView,
        proposals: list[tuple[str, WerewolfProposalOutput]],
    ) -> str:
        if not proposals:
            alive_ids = [p["id"] for p in game_view.alive_players if p["id"] not in self._get_werewolf_ids()]
            return alive_ids[0] if alive_ids else ""

        target_votes: dict[str, int] = {}
        for _, proposal in proposals:
            target = proposal.target_player_id
            target_votes[target] = target_votes.get(target, 0) + 1

        consensus_target = max(target_votes.keys(), key=lambda t: target_votes[t])
        return consensus_target

    def _get_werewolf_ids(self) -> list[str]:
        return [agent.player_id for agent in self.werewolf_agents]

    def run(self, game_view: GameView) -> str:
        proposals = self.get_proposals(game_view)

        if self.camp_memory:
            for wolf_id, proposal in proposals:
                self.camp_memory.add_discussion_note(
                    game_view.day_number,
                    wolf_id,
                    f"Proposed {proposal.target_player_id}: {proposal.reasoning}",
                )

        consensus_target = self.reach_consensus(game_view, proposals)

        if self.camp_memory:
            self.camp_memory.add_kill(game_view.day_number, consensus_target)

        return consensus_target
