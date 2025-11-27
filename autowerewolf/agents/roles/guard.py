from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import GuardNightOutput, SpeechOutput, VoteOutput
from autowerewolf.engine.roles import Role


class GuardAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are the GUARD. You protect villagers from werewolf attacks.

ABILITIES:
- Each night, choose ONE player to protect from werewolf attacks
- You CAN protect yourself (unless rules say otherwise)
- The protected player survives if attacked that night

CONSTRAINTS:
- You CANNOT protect the same player two nights in a row
- WARNING: "Same guard same save" rule - if you protect someone AND the Witch saves them, they STILL DIE

NIGHT STRATEGY:
- Consider protecting key roles (revealed Seer, Sheriff, active good players)
- Don't be too predictable - werewolves may guess your target
- If someone claims an important role, they might be lying to draw your protection
- Varying your targets makes it harder for werewolves to plan around you

DAY STRATEGY:
- Your role is valuable - consider not claiming unless necessary
- If you successfully protected someone (they should have died), that info helps
- Coordinate with the Witch if both are revealed to avoid "same guard same save"
- Analyze who werewolves might target next

COMMON MISTAKES TO AVOID:
- Protecting the same player every night (violates rules)
- Always protecting yourself (selfish and predictable)
- Protecting someone the Witch is also saving"""

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
        self.last_protected: Optional[str] = None

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def set_last_protected(self, player_id: Optional[str]) -> None:
        self.last_protected = player_id

    def get_valid_targets(self, alive_player_ids: list[str]) -> list[str]:
        return [pid for pid in alive_player_ids if pid != self.last_protected]

    def _build_night_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Last night you protected: {last_protected}
You CANNOT protect the same player tonight.

Choose a player to protect. Consider:
- Who is most likely to be targeted by werewolves?
- Any revealed special roles that need protection?
- Avoid protecting someone the Witch might also save"""),
        ])
        return prompt | self.chat_model.with_structured_output(GuardNightOutput)

    def decide_night_action(self, game_view: GameView) -> GuardNightOutput:
        context = game_view.to_prompt_context()
        last_protected = self.last_protected if self.last_protected else "No one (first night)"
        return self.night_chain.invoke({
            "context": context,
            "last_protected": last_protected,
        })

    def validate_action(self, action: GuardNightOutput, alive_player_ids: list[str]) -> GuardNightOutput:
        if action.protect_target_id == self.last_protected:
            valid_targets = self.get_valid_targets(alive_player_ids)
            if valid_targets:
                action.protect_target_id = valid_targets[0]
        return action

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Deliver your day speech. Consider:
- Whether to reveal successful protections (if you know about them)
- Whether to claim Guard (risky but may help coordinate with Witch)
- Share your observations and analysis
- Support the village's deduction efforts"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Cast your vote. Consider:
- Vote for suspected werewolves
- Support verified information from the Seer
- Help eliminate threats to the village"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)
