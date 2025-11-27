from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, Field

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import SpeechOutput, VoteOutput
from autowerewolf.engine.roles import Role


class VillageIdiotRevealDecision(BaseModel):
    reveal: bool = Field(description="Whether to reveal as Village Idiot to survive the lynch")


class VillageIdiotAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are the VILLAGE IDIOT. You have a unique survival mechanism.

ABILITIES:
- If you are LYNCHED during the day, you can reveal your identity to SURVIVE
- After revealing, you LOSE your voting rights for the rest of the game
- You gain the ability to INTERRUPT others' speeches after revealing
- You die normally if killed at NIGHT (no protection)

STRATEGY:
- Play like a normal villager during discussions
- Your reveal ability is a safety net against mislynch
- Consider revealing early if:
  * The village clearly has wrong information about you
  * Your survival helps the village
- Consider NOT revealing if:
  * You're confident the village will win soon
  * Losing your vote hurts the village too much
  * The situation is unclear and you might be wrong

AFTER REVEALING:
- You can still speak and analyze
- Use your interrupt ability to cut off suspected werewolves
- Your observations still matter even without a vote
- Help guide discussions even though you can't vote

DAY STRATEGY:
- Don't claim Village Idiot unless necessary
- Werewolves may try to lynch you knowing you'll reveal
- Your reveal confirms you as good to the village"""

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
        self.has_revealed = False
        self.can_vote = True

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def reveal_identity(self) -> None:
        self.has_revealed = True
        self.can_vote = False

    def decide_reveal(self, game_view: GameView) -> VillageIdiotRevealDecision:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

You are being LYNCHED! You can reveal your Village Idiot identity to survive.
If you reveal:
- You survive this lynch
- You lose your voting rights permanently
- You're confirmed as a good player

Consider:
- Is your survival more valuable than your vote?
- Will the village benefit from you staying alive?
- How many days might the game continue?

Decide whether to reveal your identity."""),
        ])
        chain = prompt | self.chat_model.with_structured_output(VillageIdiotRevealDecision)
        context = game_view.to_prompt_context()
        result: VillageIdiotRevealDecision = self._invoke_with_correction(
            chain,
            {"context": context},
            VillageIdiotRevealDecision,
            context,
        )
        return result

    def _build_speech_chain(self) -> RunnableSerializable:
        if self.has_revealed:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
                ("human", """{context}

You have revealed as Village Idiot. You cannot vote but can still:
- Analyze and share observations
- Interrupt others' speeches
- Guide village discussions

Deliver your speech to help the village."""),
            ])
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
                ("human", """{context}

Deliver your day speech. Play like a normal villager:
- Share your observations and suspicions
- Remember you have a safety net against mislynch
- Consider whether revealing your role would help or hurt"""),
            ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Cast your vote (if you still have voting rights).
Vote for suspected werewolves based on your analysis."""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    def decide_vote(self, game_view: GameView) -> Optional[VoteOutput]:
        if not self.can_vote:
            return None
        return super().decide_vote(game_view)
