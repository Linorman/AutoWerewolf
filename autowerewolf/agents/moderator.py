from typing import Any, Literal, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, Field

from autowerewolf.engine.state import Event, GameState


class NarrationOutput(BaseModel):
    narration: str = Field(description="The narration text to deliver to players")


class ModeratorChain:
    SYSTEM_PROMPT = """You are the neutral moderator of a Werewolf game. Your responsibilities:
1. Narrate game events clearly and dramatically
2. NEVER reveal hidden information (roles, night actions, etc.) to inappropriate audiences
3. Announce deaths without revealing how they died (unless rules specify otherwise)
4. Maintain fairness and impartiality

When narrating:
- Be concise but atmospheric
- Use present tense for current events
- Do not editorialize or give hints about player roles
- Keep announcements clear and unambiguous"""

    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model
        self._narration_chain: Optional[RunnableSerializable] = None

    @property
    def narration_chain(self) -> RunnableSerializable:
        if self._narration_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.SYSTEM_PROMPT),
                ("human", "{context}\n\nGenerate appropriate narration for the audience: {audience}"),
            ])
            self._narration_chain = prompt | self.chat_model.with_structured_output(NarrationOutput)
        return self._narration_chain

    def narrate(
        self,
        game_state: GameState,
        events: list[Event],
        audience: Literal["all", "werewolves", "seer", "witch", "guard"] = "all",
    ) -> str:
        context = self._build_context(game_state, events, audience)
        result = self.narration_chain.invoke({"context": context, "audience": audience})
        return result.narration  # type: ignore

    def _build_context(
        self,
        game_state: GameState,
        events: list[Event],
        audience: str,
    ) -> str:
        lines = [
            f"Day {game_state.day_number}, Phase: {game_state.phase.value}",
            f"Alive players: {len(game_state.get_alive_players())}/{len(game_state.players)}",
            "",
            "Events to narrate:",
        ]

        for event in events:
            if audience == "all" and not event.public:
                continue

            event_desc = self._describe_event(event, game_state, audience)
            if event_desc:
                lines.append(f"  - {event_desc}")

        return "\n".join(lines)

    def _describe_event(
        self,
        event: Event,
        game_state: GameState,
        audience: str,
    ) -> Optional[str]:
        event_type = event.event_type.value

        actor = game_state.get_player(event.actor_id) if event.actor_id else None
        target = game_state.get_player(event.target_id) if event.target_id else None

        actor_name = actor.name if actor else "Unknown"
        target_name = target.name if target else "Unknown"

        if event_type == "death_announcement":
            return f"Player {target_name} was found dead"
        elif event_type == "lynch":
            return f"Player {target_name} was lynched by vote"
        elif event_type == "speech":
            content = event.data.get("content", "")
            return f"Player {actor_name} spoke: '{content[:100]}...'" if len(content) > 100 else f"Player {actor_name} spoke: '{content}'"
        elif event_type == "vote_result":
            lynched = event.data.get("lynched_player_name", "no one")
            return f"Vote concluded. {lynched} will be lynched."
        elif event_type == "sheriff_elected":
            return f"Player {target_name} was elected sheriff"
        elif event_type == "hunter_shot":
            return f"The Hunter {actor_name} fired, taking {target_name} with them"
        elif event_type == "village_idiot_reveal":
            return f"Player {target_name} revealed themselves as the Village Idiot and survives"
        elif event_type == "badge_pass":
            return f"The sheriff badge was passed to {target_name}"
        elif event_type == "badge_tear":
            return "The sheriff badge was torn and destroyed"
        elif event_type == "phase_change":
            new_phase = event.data.get("new_phase", "unknown")
            return f"The game transitions to {new_phase} phase"
        elif event_type == "game_start":
            return "The game begins. Night falls over the village..."
        elif event_type == "game_end":
            winner = event.data.get("winner", "unknown")
            return f"The game has ended. {winner} wins!"
        elif event_type == "no_death":
            return "The night passed peacefully. No one died."
        elif event_type == "wolf_self_explode":
            return f"Player {actor_name} suddenly revealed themselves as a werewolf!"
        else:
            if audience != "all":
                return self._describe_private_event(event, game_state, audience, actor_name, target_name)
        return None

    def _describe_private_event(
        self,
        event: Event,
        game_state: GameState,
        audience: str,
        actor_name: str,
        target_name: str,
    ) -> Optional[str]:
        event_type = event.event_type.value

        if audience == "werewolves" and event_type == "night_kill":
            return f"The pack targets {target_name} for elimination"
        elif audience == "seer" and event_type == "seer_check":
            result = event.data.get("result", "unknown")
            return f"Your vision reveals {target_name} is {result}"
        elif audience == "witch" and event_type == "witch_save":
            return f"You used your cure potion to save {target_name}"
        elif audience == "witch" and event_type == "witch_poison":
            return f"You used your poison on {target_name}"
        elif audience == "guard" and event_type == "guard_protect":
            return f"You stand guard over {target_name} tonight"

        return None

    def announce_night_start(self, game_state: GameState) -> str:
        return f"Night {game_state.day_number} falls. All players close their eyes."

    def announce_day_start(self, game_state: GameState, deaths: list[str]) -> str:
        if not deaths:
            return f"Day {game_state.day_number} breaks. The village awakens. No one died last night."

        dead_players = []
        for pid in deaths:
            player = game_state.get_player(pid)
            if player:
                dead_players.append(player.name)

        if len(dead_players) == 1:
            return f"Day {game_state.day_number} breaks. Tragically, {dead_players[0]} did not survive the night."
        else:
            return f"Day {game_state.day_number} breaks. Tragically, {', '.join(dead_players)} did not survive the night."

    def announce_sheriff_election(self) -> str:
        return "Before we proceed, it's time to elect a sheriff. Those who wish to run, please step forward."

    def announce_voting_start(self) -> str:
        return "Discussion time is over. It's time to vote. Choose who you believe is a werewolf."

    def announce_game_end(self, game_state: GameState) -> str:
        winner = game_state.winning_team.value
        if winner == "village":
            return "All werewolves have been eliminated! The village wins!"
        elif winner == "werewolf":
            return "The werewolves have achieved victory! Darkness consumes the village."
        else:
            return "The game has ended."
