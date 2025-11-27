from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .roles import Alignment, Phase, Role, RoleSet, WinMode, WinningTeam


class Player(BaseModel):
    """Represents a player in the game.
    
    Attributes:
        id: Unique identifier for the player
        name: Display name for the player
        role: The player's assigned role
        alignment: The player's team alignment (derived from role)
        is_alive: Whether the player is still alive
        is_sheriff: Whether the player holds the sheriff badge
        seat_number: The player's seat position (1-12)
    """
    
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    role: Role
    alignment: Alignment = Field(default=Alignment.GOOD)
    is_alive: bool = Field(default=True)
    is_sheriff: bool = Field(default=False)
    seat_number: int = Field(ge=1, le=12)
    
    # Private state for specific roles
    witch_has_cure: bool = Field(default=True)
    witch_has_poison: bool = Field(default=True)
    guard_last_protected: Optional[str] = Field(default=None)  # Player ID protected last night
    seer_checks: list[tuple[str, Alignment]] = Field(default_factory=list)  # (player_id, result)
    
    # Village Idiot specific
    village_idiot_revealed: bool = Field(default=False)
    
    # Hunter specific - whether hunter can shoot (not if poisoned)
    hunter_can_shoot: bool = Field(default=True)
    
    @model_validator(mode="after")
    def set_alignment_from_role(self) -> "Player":
        """Automatically set alignment based on role."""
        self.alignment = Alignment.from_role(self.role)
        return self


class RuleVariants(BaseModel):
    """Configurable rule variants for the game.
    
    Different play groups may use different rule variations.
    These settings control how certain edge cases are resolved.
    """
    
    # Witch rules
    witch_can_self_heal_n1: bool = Field(
        default=True,
        description="Whether the Witch can heal herself on Night 1"
    )
    witch_can_self_heal: bool = Field(
        default=False,
        description="Whether the Witch can heal herself (after N1)"
    )
    witch_can_use_both_potions: bool = Field(
        default=False,
        description="Whether the Witch can use both potions in one night"
    )
    
    # Guard rules
    guard_can_self_guard: bool = Field(
        default=True,
        description="Whether the Guard can protect themselves"
    )
    same_guard_same_save_kills: bool = Field(
        default=True,
        description="If Guard protects and Witch saves same target, target still dies"
    )
    
    # Win condition
    win_mode: WinMode = Field(
        default=WinMode.SIDE_ELIMINATION,
        description="Win condition mode (side_elimination or city_elimination)"
    )
    
    # Werewolf special actions
    allow_wolf_self_explode: bool = Field(
        default=True,
        description="Allow werewolves to self-explode during the day"
    )
    allow_wolf_self_knife: bool = Field(
        default=True,
        description="Allow werewolves to kill their own teammates at night"
    )
    
    # Sheriff rules
    sheriff_vote_weight: float = Field(
        default=1.5,
        description="Vote weight multiplier for the sheriff"
    )
    
    # Hunter rules
    hunter_can_shoot_if_poisoned: bool = Field(
        default=False,
        description="Whether the Hunter can shoot if killed by Witch poison"
    )
    hunter_can_shoot_if_night_killed: bool = Field(
        default=True,
        description="Whether the Hunter can shoot if killed at night"
    )
    
    # Last words rules
    first_night_death_has_last_words: bool = Field(
        default=True,
        description="Whether the first night death gets last words"
    )


class GameConfig(BaseModel):
    """Configuration for a game instance.
    
    Attributes:
        num_players: Number of players (default 12)
        role_set: Which special role set to use (A or B)
        rule_variants: Rule customizations
        random_seed: Optional seed for reproducibility
    """
    
    num_players: int = Field(default=12, ge=12, le=12)
    role_set: RoleSet = Field(default=RoleSet.A)
    rule_variants: RuleVariants = Field(default_factory=RuleVariants)
    random_seed: Optional[int] = Field(default=None)
    
    @field_validator("num_players")
    @classmethod
    def validate_player_count(cls, v: int) -> int:
        """Validate that we have exactly 12 players (standard game)."""
        if v != 12:
            raise ValueError("Currently only 12-player games are supported")
        return v


class EventType(str, Enum):
    """Types of events that can occur in the game."""
    
    # Game lifecycle
    GAME_START = "game_start"
    GAME_END = "game_end"
    PHASE_CHANGE = "phase_change"
    
    # Night events
    NIGHT_KILL = "night_kill"
    SEER_CHECK = "seer_check"
    WITCH_SAVE = "witch_save"
    WITCH_POISON = "witch_poison"
    GUARD_PROTECT = "guard_protect"
    
    # Day events
    DEATH_ANNOUNCEMENT = "death_announcement"
    SPEECH = "speech"
    VOTE_CAST = "vote_cast"
    VOTE_RESULT = "vote_result"
    LYNCH = "lynch"
    LAST_WORDS = "last_words"
    
    # Sheriff events
    SHERIFF_ELECTION = "sheriff_election"
    SHERIFF_CAMPAIGN_SPEECH = "sheriff_campaign_speech"
    SHERIFF_VOTE = "sheriff_vote"
    SHERIFF_ELECTED = "sheriff_elected"
    BADGE_PASS = "badge_pass"
    BADGE_TEAR = "badge_tear"
    
    # Special role events
    HUNTER_SHOT = "hunter_shot"
    VILLAGE_IDIOT_REVEAL = "village_idiot_reveal"
    WOLF_SELF_EXPLODE = "wolf_self_explode"
    
    # Resolution events
    NO_DEATH = "no_death"
    SAVED = "saved"


class Event(BaseModel):
    """Base class for all game events.
    
    Events are immutable records of things that happened in the game.
    They form the game history and are used for logging and replay.
    """
    
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)
    day_number: int = Field(ge=0)
    phase: Phase
    
    # Event-specific data
    actor_id: Optional[str] = Field(default=None, description="ID of the player who caused this event")
    target_id: Optional[str] = Field(default=None, description="ID of the affected player")
    data: dict[str, Any] = Field(default_factory=dict, description="Additional event data")
    
    # Visibility control
    public: bool = Field(default=True, description="Whether this event is visible to all players")
    visible_to: Optional[list[str]] = Field(
        default=None, 
        description="If not public, list of player IDs who can see this event"
    )
    
    model_config = ConfigDict(frozen=True)



class NightKillEvent(Event):
    """A werewolf night kill event."""
    
    event_type: Literal[EventType.NIGHT_KILL] = EventType.NIGHT_KILL
    public: bool = False


class SeerCheckEvent(Event):
    """A Seer check event."""
    
    event_type: Literal[EventType.SEER_CHECK] = EventType.SEER_CHECK
    public: bool = False
    
    @property
    def check_result(self) -> Optional[Alignment]:
        """Get the result of the check."""
        return self.data.get("result")


class WitchSaveEvent(Event):
    """A Witch save (cure) event."""
    
    event_type: Literal[EventType.WITCH_SAVE] = EventType.WITCH_SAVE
    public: bool = False


class WitchPoisonEvent(Event):
    """A Witch poison event."""
    
    event_type: Literal[EventType.WITCH_POISON] = EventType.WITCH_POISON
    public: bool = False


class GuardProtectEvent(Event):
    """A Guard protection event."""
    
    event_type: Literal[EventType.GUARD_PROTECT] = EventType.GUARD_PROTECT
    public: bool = False


class HunterShotEvent(Event):
    """A Hunter shooting event."""
    
    event_type: Literal[EventType.HUNTER_SHOT] = EventType.HUNTER_SHOT
    public: bool = True


class VillageIdiotRevealEvent(Event):
    """A Village Idiot reveal event."""
    
    event_type: Literal[EventType.VILLAGE_IDIOT_REVEAL] = EventType.VILLAGE_IDIOT_REVEAL
    public: bool = True


class SheriffElectedEvent(Event):
    """Sheriff election result event."""
    
    event_type: Literal[EventType.SHERIFF_ELECTED] = EventType.SHERIFF_ELECTED
    public: bool = True


class BadgePassEvent(Event):
    """Sheriff badge passing event."""
    
    event_type: Literal[EventType.BADGE_PASS] = EventType.BADGE_PASS
    public: bool = True


class BadgeTearEvent(Event):
    """Sheriff badge tearing event."""
    
    event_type: Literal[EventType.BADGE_TEAR] = EventType.BADGE_TEAR
    public: bool = True


class VoteCastEvent(Event):
    """A vote cast by a player."""
    
    event_type: Literal[EventType.VOTE_CAST] = EventType.VOTE_CAST
    public: bool = True


class VoteResultEvent(Event):
    """Result of a voting round."""
    
    event_type: Literal[EventType.VOTE_RESULT] = EventType.VOTE_RESULT
    public: bool = True


class LynchEvent(Event):
    """A player being lynched."""
    
    event_type: Literal[EventType.LYNCH] = EventType.LYNCH
    public: bool = True


class SpeechEvent(Event):
    """A player making a speech during the day."""
    
    event_type: Literal[EventType.SPEECH] = EventType.SPEECH
    public: bool = True


class DeathAnnouncementEvent(Event):
    """Announcement of deaths at the start of the day."""
    
    event_type: Literal[EventType.DEATH_ANNOUNCEMENT] = EventType.DEATH_ANNOUNCEMENT
    public: bool = True


class WolfSelfExplodeEvent(Event):
    """A werewolf self-exploding during the day."""
    
    event_type: Literal[EventType.WOLF_SELF_EXPLODE] = EventType.WOLF_SELF_EXPLODE
    public: bool = True


class ActionType(str, Enum):
    """Types of actions players can take."""
    
    # Night actions
    WOLF_KILL = "wolf_kill"
    SEER_CHECK = "seer_check"
    WITCH_CURE = "witch_cure"
    WITCH_POISON = "witch_poison"
    GUARD_PROTECT = "guard_protect"
    
    # Day actions
    SPEECH = "speech"
    VOTE = "vote"
    
    # Sheriff actions
    RUN_FOR_SHERIFF = "run_for_sheriff"
    SHERIFF_VOTE = "sheriff_vote"
    PASS_BADGE = "pass_badge"
    TEAR_BADGE = "tear_badge"
    
    # Special actions
    HUNTER_SHOOT = "hunter_shoot"
    WOLF_SELF_EXPLODE = "wolf_self_explode"


class Action(BaseModel):
    """Base class for all player actions.
    
    Actions are decisions made by players (or their agents).
    They are validated and processed by the rules engine.
    """
    
    action_type: ActionType
    actor_id: str = Field(description="ID of the player taking the action")
    target_id: Optional[str] = Field(default=None, description="ID of the target player")
    data: dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(frozen=True)


class WolfKillAction(Action):
    """Werewolf night kill action."""
    
    action_type: Literal[ActionType.WOLF_KILL] = ActionType.WOLF_KILL


class SeerCheckAction(Action):
    """Seer check action."""
    
    action_type: Literal[ActionType.SEER_CHECK] = ActionType.SEER_CHECK


class WitchCureAction(Action):
    """Witch cure (save) action."""
    
    action_type: Literal[ActionType.WITCH_CURE] = ActionType.WITCH_CURE


class WitchPoisonAction(Action):
    """Witch poison action."""
    
    action_type: Literal[ActionType.WITCH_POISON] = ActionType.WITCH_POISON


class GuardProtectAction(Action):
    """Guard protection action."""
    
    action_type: Literal[ActionType.GUARD_PROTECT] = ActionType.GUARD_PROTECT


class SpeechAction(Action):
    """Day speech action."""
    
    action_type: Literal[ActionType.SPEECH] = ActionType.SPEECH
    
    @property
    def content(self) -> str:
        """Get the speech content."""
        return self.data.get("content", "")


class VoteAction(Action):
    """Day vote action."""
    
    action_type: Literal[ActionType.VOTE] = ActionType.VOTE


class HunterShootAction(Action):
    """Hunter shoot action."""
    
    action_type: Literal[ActionType.HUNTER_SHOOT] = ActionType.HUNTER_SHOOT


class WolfSelfExplodeAction(Action):
    """Werewolf self-explode action."""
    
    action_type: Literal[ActionType.WOLF_SELF_EXPLODE] = ActionType.WOLF_SELF_EXPLODE


class RunForSheriffAction(Action):
    """Run for sheriff action."""
    
    action_type: Literal[ActionType.RUN_FOR_SHERIFF] = ActionType.RUN_FOR_SHERIFF


class SheriffVoteAction(Action):
    """Vote in sheriff election."""
    
    action_type: Literal[ActionType.SHERIFF_VOTE] = ActionType.SHERIFF_VOTE


class PassBadgeAction(Action):
    """Pass sheriff badge action."""
    
    action_type: Literal[ActionType.PASS_BADGE] = ActionType.PASS_BADGE


class TearBadgeAction(Action):
    """Tear sheriff badge action."""
    
    action_type: Literal[ActionType.TEAR_BADGE] = ActionType.TEAR_BADGE



class NightResolution(BaseModel):
    """Results of night phase resolution."""
    
    killed_player_ids: list[str] = Field(default_factory=list)
    saved_player_ids: list[str] = Field(default_factory=list)
    protected_player_id: Optional[str] = None
    poisoned_player_id: Optional[str] = None
    seer_check_result: Optional[tuple[str, Alignment]] = None
    events: list[Event] = Field(default_factory=list)


class VoteResult(BaseModel):
    """Results of a voting round."""
    
    votes: dict[str, str] = Field(default_factory=dict)  # voter_id -> target_id
    vote_counts: dict[str, float] = Field(default_factory=dict)  # target_id -> vote count
    lynched_player_id: Optional[str] = None
    is_tie: bool = False
    events: list[Event] = Field(default_factory=list)


class GameState(BaseModel):
    """Complete state of a Werewolf game.
    
    This model contains all information needed to:
    - Continue a game from any point
    - Generate views for specific players
    - Evaluate win conditions
    """
    
    # Game configuration
    config: GameConfig = Field(default_factory=GameConfig)
    
    # Current phase info
    day_number: int = Field(default=0, ge=0)
    phase: Phase = Field(default=Phase.NIGHT)
    
    # Players
    players: list[Player] = Field(default_factory=list)
    
    # Sheriff status
    sheriff_id: Optional[str] = Field(default=None)
    badge_torn: bool = Field(default=False)
    sheriff_election_complete: bool = Field(default=False)
    
    # Night tracking
    current_night_actions: dict[str, Action] = Field(default_factory=dict)
    wolf_kill_target_id: Optional[str] = Field(default=None)
    
    # History
    history: list[Event] = Field(default_factory=list)
    
    # Game result
    winning_team: WinningTeam = Field(default=WinningTeam.NONE)
    
    def get_player(self, player_id: str) -> Optional[Player]:
        """Get a player by ID."""
        for player in self.players:
            if player.id == player_id:
                return player
        return None
    
    def get_player_by_seat(self, seat_number: int) -> Optional[Player]:
        """Get a player by seat number."""
        for player in self.players:
            if player.seat_number == seat_number:
                return player
        return None
    
    def get_alive_players(self) -> list[Player]:
        """Get all alive players."""
        return [p for p in self.players if p.is_alive]
    
    def get_alive_player_ids(self) -> list[str]:
        """Get IDs of all alive players."""
        return [p.id for p in self.players if p.is_alive]
    
    def get_players_by_role(self, role: Role) -> list[Player]:
        """Get all players with a specific role."""
        return [p for p in self.players if p.role == role]
    
    def get_alive_players_by_role(self, role: Role) -> list[Player]:
        """Get all alive players with a specific role."""
        return [p for p in self.players if p.role == role and p.is_alive]
    
    def get_players_by_alignment(self, alignment: Alignment) -> list[Player]:
        """Get all players with a specific alignment."""
        return [p for p in self.players if p.alignment == alignment]
    
    def get_alive_players_by_alignment(self, alignment: Alignment) -> list[Player]:
        """Get all alive players with a specific alignment."""
        return [p for p in self.players if p.alignment == alignment and p.is_alive]
    
    def get_werewolves(self) -> list[Player]:
        """Get all werewolf players."""
        return self.get_players_by_role(Role.WEREWOLF)
    
    def get_alive_werewolves(self) -> list[Player]:
        """Get all alive werewolf players."""
        return self.get_alive_players_by_role(Role.WEREWOLF)
    
    def get_villagers(self) -> list[Player]:
        """Get all plain villager players."""
        return self.get_players_by_role(Role.VILLAGER)
    
    def get_alive_villagers(self) -> list[Player]:
        """Get all alive plain villager players."""
        return self.get_alive_players_by_role(Role.VILLAGER)
    
    def get_special_roles(self) -> list[Player]:
        """Get all special role players (Gods)."""
        return [p for p in self.players if p.role.is_special]
    
    def get_alive_special_roles(self) -> list[Player]:
        """Get all alive special role players."""
        return [p for p in self.players if p.role.is_special and p.is_alive]
    
    def get_sheriff(self) -> Optional[Player]:
        """Get the current sheriff."""
        if self.sheriff_id:
            return self.get_player(self.sheriff_id)
        return None
    
    def is_game_over(self) -> bool:
        """Check if the game has ended."""
        return self.winning_team != WinningTeam.NONE
    
    def add_event(self, event: Event) -> None:
        """Add an event to the history."""
        self.history.append(event)
    
    def get_public_events(self) -> list[Event]:
        """Get all public events."""
        return [e for e in self.history if e.public]
    
    def get_events_for_player(self, player_id: str) -> list[Event]:
        """Get all events visible to a specific player."""
        return [
            e for e in self.history
            if e.public or (e.visible_to and player_id in e.visible_to)
        ]
