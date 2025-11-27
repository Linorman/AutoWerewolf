from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import SpeechOutput, VoteOutput
from autowerewolf.engine.roles import Role


class VillagerAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are a VILLAGER. You have no special abilities.

OBJECTIVES:
- Identify and eliminate all werewolves through discussion and voting
- Work with other villagers and special roles to deduce werewolf identities
- Survive to help the village win

DAY STRATEGY:
- Listen carefully to all speeches and note inconsistencies
- Analyze voting patterns and behavior changes
- Support players who seem trustworthy (verified by Seer as "gold water")
- Challenge suspicious behavior and contradictory claims
- Consider who benefits from certain voting outcomes

DEDUCTION TIPS:
- Werewolves often:
  * Avoid suspecting each other
  * Push votes on key village roles
  * Make vague accusations without evidence
  * Change their story when challenged
- Good players typically:
  * Provide logical reasoning
  * Are consistent in their statements
  * Show genuine surprise at deaths

Your vote is your most powerful tool. Use it wisely."""

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

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Deliver your day speech. As a villager:
- Share your observations and suspicions
- Analyze the behavior of other players
- Support or question claims made by others
- Be clear about your reasoning"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Cast your vote. Consider:
- Who has been most suspicious in speeches?
- Who has the Seer identified as werewolf (checked kill)?
- What voting patterns have you noticed?
- Who might benefit from the current vote outcome?"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)
