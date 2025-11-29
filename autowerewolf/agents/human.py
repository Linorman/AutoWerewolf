import threading
from typing import TYPE_CHECKING, Any, Optional

from autowerewolf.agents.player_base import BasePlayerAgent, GameView
from autowerewolf.agents.schemas import (
    BadgeDecisionOutput,
    GuardNightOutput,
    HunterShootOutput,
    LastWordsOutput,
    NightActionOutput,
    SeerNightOutput,
    SheriffDecisionOutput,
    SpeechOutput,
    VoteOutput,
    WerewolfNightOutput,
    WitchNightOutput,
)
from autowerewolf.config.performance import VerbosityLevel
from autowerewolf.engine.roles import Role

if TYPE_CHECKING:
    from autowerewolf.agents.memory import AgentMemory


class HumanPlayerAgent(BasePlayerAgent):
    def __init__(
        self,
        player_id: str,
        player_name: str,
        role: Role,
        memory: Optional["AgentMemory"] = None,
        verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
        input_handler: Optional[Any] = None,
    ):
        super().__init__(
            player_id=player_id,
            player_name=player_name,
            role=role,
            chat_model=None,  # type: ignore
            memory=memory,
            verbosity=verbosity,
        )
        self.input_handler = input_handler or CLIInputHandler()

    def _display_game_view(self, game_view: GameView) -> None:
        print("\n" + "=" * 60)
        print(f"Your turn: {game_view.player_name} ({game_view.role.value})")
        print(f"Phase: Day {game_view.day_number} - {game_view.phase}")
        print("=" * 60)
        
        print("\nAlive players:")
        for p in game_view.alive_players:
            sheriff = " [Sheriff]" if p.get("is_sheriff") else ""
            status = "ALIVE" if p.get("is_alive", True) else "DEAD"
            print(f"  {p['id']}: {p['name']} (Seat {p.get('seat_number', '?')}){sheriff} - {status}")
        
        if game_view.private_info:
            print("\nYour private information:")
            for key, value in game_view.private_info.items():
                if key == "teammates":
                    print(f"  Fellow werewolves: {[t['name'] for t in value]}")
                elif key == "check_results":
                    print(f"  Seer checks:")
                    for check in value:
                        print(f"    - {check['player_id']}: {check['result']}")
                elif key == "attack_target":
                    print(f"  Tonight's attack target: {value['name']}")
                else:
                    print(f"  {key}: {value}")
        
        if game_view.action_context:
            print("\nAction context:")
            valid_targets = game_view.action_context.get("valid_targets", [])
            if valid_targets:
                print(f"  Valid targets: {valid_targets}")
        
        if game_view.public_history:
            print("\nRecent events:")
            for event in game_view.public_history[-5:]:
                print(f"  - {event.get('description', str(event))}")

    def decide_night_action(self, game_view: GameView) -> NightActionOutput:
        self._display_game_view(game_view)
        valid_targets = game_view.action_context.get("valid_targets", [])
        
        if self.role == Role.WEREWOLF:
            ai_proposals = game_view.action_context.get("ai_proposals", [])
            teammates_info = game_view.action_context.get("teammates_info", [])
            
            prompt = "Choose a player to kill (or 'skip' to abstain):"
            extra_context = {
                "ai_proposals": ai_proposals,
                "teammates_info": teammates_info,
                "is_werewolf_discussion": game_view.action_context.get("is_werewolf_discussion", False),
            }
            
            target = self.input_handler.get_target_selection(
                prompt,
                valid_targets,
                allow_skip=True,
                extra_context=extra_context,
            )
            return WerewolfNightOutput(
                kill_target_id=target or valid_targets[0] if valid_targets else "",
                self_explode=False,
            )
        
        elif self.role == Role.SEER:
            target = self.input_handler.get_target_selection(
                "Choose a player to check:",
                valid_targets,
                allow_skip=False,
            )
            return SeerNightOutput(
                check_target_id=target or valid_targets[0] if valid_targets else "",
            )
        
        elif self.role == Role.WITCH:
            use_cure = False
            use_poison = False
            poison_target = None
            
            attack_target = game_view.private_info.get("attack_target")
            has_cure = game_view.private_info.get("has_cure", False)
            has_poison = game_view.private_info.get("has_poison", False)
            
            if attack_target and has_cure:
                use_cure = self.input_handler.get_yes_no(
                    f"Use cure to save {attack_target['name']}?"
                )
            
            if has_poison and not use_cure:
                use_poison = self.input_handler.get_yes_no("Use poison?")
                if use_poison:
                    poison_target = self.input_handler.get_target_selection(
                        "Choose a player to poison:",
                        valid_targets,
                        allow_skip=False,
                    )
            
            return WitchNightOutput(
                use_cure=use_cure,
                use_poison=use_poison,
                poison_target_id=poison_target,
            )
        
        elif self.role == Role.GUARD:
            target = self.input_handler.get_target_selection(
                "Choose a player to protect:",
                valid_targets,
                allow_skip=False,
            )
            return GuardNightOutput(
                protect_target_id=target or valid_targets[0] if valid_targets else "",
            )
        
        return WerewolfNightOutput(
            kill_target_id=valid_targets[0] if valid_targets else "",
            self_explode=False,
        )

    def decide_day_speech(self, game_view: GameView) -> SpeechOutput:
        self._display_game_view(game_view)
        
        content = self.input_handler.get_text_input(
            "Enter your speech (press Enter twice to finish):",
            multiline=True,
        )
        
        return SpeechOutput(
            content=content,
        )

    def decide_vote(self, game_view: GameView) -> VoteOutput:
        self._display_game_view(game_view)
        valid_targets = game_view.action_context.get("valid_targets", [])
        
        target = self.input_handler.get_target_selection(
            "Vote for a player (or 'skip' to abstain):",
            valid_targets,
            allow_skip=True,
        )
        
        return VoteOutput(
            target_player_id=target or valid_targets[0] if valid_targets else "",
            reasoning="Human player vote",
        )

    def decide_sheriff_run(self, game_view: GameView) -> SheriffDecisionOutput:
        self._display_game_view(game_view)
        
        run_for_sheriff = self.input_handler.get_yes_no(
            "Do you want to run for Sheriff?"
        )
        
        speech = ""
        if run_for_sheriff:
            speech = self.input_handler.get_text_input(
                "Enter your campaign speech:",
                multiline=True,
            )
        
        return SheriffDecisionOutput(
            run_for_sheriff=run_for_sheriff,
        )

    def decide_badge_pass(self, game_view: GameView) -> BadgeDecisionOutput:
        self._display_game_view(game_view)
        valid_targets = game_view.action_context.get("valid_targets", [])
        
        pass_badge = self.input_handler.get_yes_no(
            "Do you want to pass the sheriff badge? (No = tear badge)"
        )
        
        target = None
        if pass_badge:
            target = self.input_handler.get_target_selection(
                "Choose a player to pass the badge to:",
                valid_targets,
                allow_skip=False,
            )
        
        return BadgeDecisionOutput(
            action="pass" if pass_badge else "tear",
            target_player_id=target,
        )

    def decide_last_words(self, game_view: GameView) -> LastWordsOutput:
        self._display_game_view(game_view)
        
        content = self.input_handler.get_text_input(
            "Enter your last words (press Enter twice to finish):",
            multiline=True,
        )
        
        return LastWordsOutput(
            content=content,
        )

    def decide_hunter_shot(self, game_view: GameView) -> HunterShootOutput:
        self._display_game_view(game_view)
        valid_targets = game_view.action_context.get("valid_targets", [])
        
        shoot = self.input_handler.get_yes_no("Do you want to shoot someone?")
        
        target = None
        if shoot:
            target = self.input_handler.get_target_selection(
                "Choose a player to shoot:",
                valid_targets,
                allow_skip=False,
            )
        
        return HunterShootOutput(
            shoot=shoot,
            target_player_id=target,
        )


class CLIInputHandler:
    def get_target_selection(
        self,
        prompt: str,
        valid_targets: list[str],
        allow_skip: bool = False,
    ) -> Optional[str]:
        print(f"\n{prompt}")
        if allow_skip:
            print("  (Enter 'skip' or leave empty to skip)")
        print(f"  Valid targets: {', '.join(valid_targets)}")
        
        while True:
            choice = input("> ").strip()
            
            if allow_skip and (choice.lower() == "skip" or choice == ""):
                return None
            
            if choice in valid_targets:
                return choice
            
            for target in valid_targets:
                if target.lower() == choice.lower():
                    return target
            
            print(f"Invalid choice. Please choose from: {', '.join(valid_targets)}")

    def get_yes_no(self, prompt: str) -> bool:
        print(f"\n{prompt} [y/n]")
        while True:
            choice = input("> ").strip().lower()
            if choice in ("y", "yes", "1", "true"):
                return True
            if choice in ("n", "no", "0", "false"):
                return False
            print("Please enter 'y' or 'n'")

    def get_text_input(
        self,
        prompt: str,
        multiline: bool = False,
    ) -> str:
        print(f"\n{prompt}")
        
        if multiline:
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            return "\n".join(lines)
        else:
            return input("> ").strip()


class WebInputHandler:
    def __init__(self):
        self._pending_input: Optional[Any] = None
        self._input_event = threading.Event()
        self._action_request_callback: Optional[Any] = None
        self._current_request: Optional[dict[str, Any]] = None

    def set_action_request_callback(self, callback: Any) -> None:
        self._action_request_callback = callback

    def set_input(self, data: Any) -> None:
        self._pending_input = data
        self._input_event.set()

    def _request_input(
        self,
        action_type: str,
        prompt: str,
        valid_targets: Optional[list[str]] = None,
        allow_skip: bool = False,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> None:
        self._current_request = {
            "action_type": action_type,
            "prompt": prompt,
            "valid_targets": valid_targets or [],
            "allow_skip": allow_skip,
            "extra_context": extra_context or {},
        }
        if self._action_request_callback:
            self._action_request_callback(self._current_request)

    def _wait_for_input_sync(self, timeout: float = 300.0) -> Any:
        if self._input_event.is_set() and self._pending_input is not None:
            result = self._pending_input
            self._pending_input = None
            self._input_event.clear()
            self._current_request = None
            return result
        self._input_event.clear()
        self._pending_input = None
        
        if self._input_event.wait(timeout=timeout):
            result = self._pending_input
            self._pending_input = None
            self._input_event.clear()
            self._current_request = None
            return result
        
        self._current_request = None
        return None

    def get_target_selection(
        self,
        prompt: str,
        valid_targets: list[str],
        allow_skip: bool = False,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        self._request_input("target_selection", prompt, valid_targets, allow_skip, extra_context)
        data = self._wait_for_input_sync()
        if data is None:
            return None
        target = data.get("target") if isinstance(data, dict) else None
        if allow_skip and target in (None, "", "skip"):
            return None
        if target in valid_targets:
            return target
        return valid_targets[0] if valid_targets else None

    def get_yes_no(self, prompt: str) -> bool:
        self._request_input("yes_no", prompt, allow_skip=False)
        data = self._wait_for_input_sync()
        if data is None or not isinstance(data, dict):
            return False
        return bool(data.get("value", False))

    def get_text_input(self, prompt: str, multiline: bool = False) -> str:
        self._request_input("text_input", prompt, allow_skip=False, extra_context={"multiline": multiline})
        data = self._wait_for_input_sync()
        if data is None or not isinstance(data, dict):
            return ""
        return str(data.get("text", ""))


def create_human_agent(
    player_id: str,
    player_name: str,
    role: Role,
    memory: Optional[Any] = None,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    input_handler: Optional[Any] = None,
) -> HumanPlayerAgent:
    return HumanPlayerAgent(
        player_id=player_id,
        player_name=player_name,
        role=role,
        memory=memory,
        verbosity=verbosity,
        input_handler=input_handler,
    )
