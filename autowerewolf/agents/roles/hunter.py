from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import HunterShootOutput, SpeechOutput, VoteOutput
from autowerewolf.engine.roles import Role


class HunterAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are the HUNTER. You have a powerful revenge ability.

ABILITIES:
- When you die by VOTE or WEREWOLF ATTACK, you can SHOOT one player
- The shot player dies immediately
- You CANNOT shoot if killed by WITCH POISON

CONSTRAINTS:
- The moderator will tell you each night if you can shoot (based on how you might die)
- Your shot is instant and cannot be prevented
- Choose your target wisely - it's your final action

DAY STRATEGY:
- Participate in discussions like a normal villager
- Gather information to identify werewolves
- If you're about to be lynched, consider whether to reveal your role
- Revealing Hunter status may deter votes (they'll think twice about killing you)

SHOOTING STRATEGY:
- Ideally shoot a confirmed or strongly suspected werewolf
- If you're poisoned (can't shoot), revealing that fact may help the village
- Don't shoot randomly - a wrong shot hurts the village
- If the Seer identified a werewolf but died, consider shooting that target

SURVIVAL:
- As a special role, try to survive to use your ability at the right moment
- Being lynched isn't always bad - you can take a werewolf with you"""

    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        chat_model: BaseChatModel,
        memory: Optional[Any] = None,
    ):
        super().__init__(player_id, player_name, role, chat_model, memory)
        self.can_shoot = True

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def set_can_shoot(self, can_shoot: bool) -> None:
        self.can_shoot = can_shoot

    def decide_shoot(self, game_view: GameView) -> HunterShootOutput:
        if not self.can_shoot:
            return HunterShootOutput(shoot=False, target_player_id=None)

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

You are dying and can use your SHOOT ability!
You can take one player with you. Choose wisely:
- Who do you most suspect to be a werewolf?
- Has the Seer identified anyone?
- Who has been acting suspiciously?

Set shoot=true and select your target. This is your final action."""),
        ])
        chain = prompt | self.chat_model.with_structured_output(HunterShootOutput)
        context = game_view.to_prompt_context()
        result: HunterShootOutput = chain.invoke({"context": context})  # type: ignore
        return result

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Can shoot status: {can_shoot}

Deliver your day speech. Options:
- Play like a normal villager without revealing your role
- If under heavy suspicion, consider revealing Hunter to deter votes
- Share your observations and suspicions
- Support the village's information gathering"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def decide_day_speech(self, game_view: GameView) -> SpeechOutput:
        context = game_view.to_prompt_context()
        can_shoot = "Yes" if self.can_shoot else "No (poisoned)"
        return self.speech_chain.invoke({"context": context, "can_shoot": can_shoot})

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Can shoot status: {can_shoot}

Cast your vote. Remember:
- Vote for suspected werewolves
- If you have shoot ability, your death can be useful
- Support the village consensus when appropriate"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    def decide_vote(self, game_view: GameView) -> VoteOutput:
        context = game_view.to_prompt_context()
        can_shoot = "Yes" if self.can_shoot else "No (poisoned)"
        return self.vote_chain.invoke({"context": context, "can_shoot": can_shoot})
