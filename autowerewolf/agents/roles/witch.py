from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import SpeechOutput, VoteOutput, WitchNightOutput
from autowerewolf.engine.roles import Role


class WitchAgent(BasePlayerAgent):
    ROLE_PROMPT = """You are the WITCH. You have powerful one-time-use potions.

ABILITIES:
- CURE POTION (one use): Save the player killed by werewolves tonight
  * You'll be told who was attacked
  * Usually cannot heal yourself (except possibly Night 1, check rules)
- POISON POTION (one use): Kill any player of your choice
  * Powerful but irreversible - be certain of your target

CONSTRAINTS:
- You can only use ONE potion per night
- Each potion can only be used ONCE per game
- Think carefully before using either potion

TERMINOLOGY:
- "Silver water": A player you saved - usually trusted as good
- "Double kill": When you poison someone the same night werewolves kill

NIGHT STRATEGY:
- Cure: Save key roles (confirmed Seer, Sheriff) or prevent early deaths
- Don't waste cure on Night 1 unless certain (the killed player might be werewolf's "self-knife")
- Poison: Use when you're confident someone is a werewolf
- Save poison for late game when information is clearer

DAY STRATEGY:
- Your potions are secret - revealing you have/used them is risky
- "Silver water" claims can help identify good players
- If you're dying, consider using information about who you saved/poisoned"""

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
        self.has_cure = True
        self.has_poison = True

    @property
    def role_system_prompt(self) -> str:
        return self.ROLE_PROMPT

    def use_cure(self) -> None:
        self.has_cure = False

    def use_poison(self) -> None:
        self.has_poison = False

    def get_potion_status(self) -> str:
        cure_status = "AVAILABLE" if self.has_cure else "USED"
        poison_status = "AVAILABLE" if self.has_poison else "USED"
        return f"Cure: {cure_status}, Poison: {poison_status}"

    def _build_night_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Potion status: {potion_status}
Tonight's attack target: {attack_target}

Decide your action:
1. use_cure=true to save the attacked player (if cure available)
2. use_poison=true and poison_target_id to kill someone (if poison available)
3. Do nothing (both false) to save your potions

Remember: Only ONE potion can be used per night."""),
        ])
        return prompt | self.chat_model.with_structured_output(WitchNightOutput)

    def decide_night_action(
        self,
        game_view: GameView,
        attack_target: Optional[str] = None,
    ) -> WitchNightOutput:
        context = game_view.to_prompt_context()
        potion_status = self.get_potion_status()
        attack_info = attack_target if attack_target else "No one was attacked"
        return self._invoke_with_correction(
            self.night_chain,
            {
                "context": context,
                "potion_status": potion_status,
                "attack_target": attack_info,
            },
            WitchNightOutput,
            context,
        )

    def validate_action(self, action: WitchNightOutput) -> WitchNightOutput:
        if action.use_cure and not self.has_cure:
            action.use_cure = False
        if action.use_poison and not self.has_poison:
            action.use_poison = False
            action.poison_target_id = None
        if action.use_cure and action.use_poison:
            action.use_poison = False
            action.poison_target_id = None
        return action

    def _build_speech_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Potion status: {potion_status}

Deliver your day speech. Consider:
- Whether to reveal any potion usage
- How to use "silver water" information strategically
- Whether claiming Witch is safe or dangerous
- Analyze the game situation and share observations"""),
        ])
        return prompt | self.chat_model.with_structured_output(SpeechOutput)

    def decide_day_speech(self, game_view: GameView) -> SpeechOutput:
        context = game_view.to_prompt_context()
        potion_status = self.get_potion_status()
        return self._invoke_with_correction(
            self.speech_chain,
            {"context": context, "potion_status": potion_status},
            SpeechOutput,
            context,
        )

    def _build_vote_chain(self) -> RunnableSerializable:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.base_system_prompt + "\n\n" + self.role_system_prompt),
            ("human", """{context}

Potion status: {potion_status}

Cast your vote. Consider:
- If you have poison, you can always kill a suspect later
- Support verified information from the Seer
- Vote based on speeches and behavior analysis"""),
        ])
        return prompt | self.chat_model.with_structured_output(VoteOutput)

    def decide_vote(self, game_view: GameView) -> VoteOutput:
        context = game_view.to_prompt_context()
        potion_status = self.get_potion_status()
        return self._invoke_with_correction(
            self.vote_chain,
            {"context": context, "potion_status": potion_status},
            VoteOutput,
            context,
        )
