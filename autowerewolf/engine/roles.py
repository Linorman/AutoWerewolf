from enum import Enum


class Role(str, Enum):
    """Enumeration of all possible roles in the Werewolf game.
    
    Standard 12-player setup:
    - 4 Werewolves
    - 4 Villagers  
    - 4 Special roles (Gods):
      - Set A: Seer, Witch, Hunter, Guard
      - Set B: Seer, Witch, Hunter, Village Idiot
    """
    
    WEREWOLF = "werewolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    GUARD = "guard"
    VILLAGE_IDIOT = "village_idiot"
    
    @property
    def is_special(self) -> bool:
        """Check if this role is a special role (God)."""
        return self in {
            Role.SEER,
            Role.WITCH,
            Role.HUNTER,
            Role.GUARD,
            Role.VILLAGE_IDIOT,
        }
    
    @property
    def is_werewolf(self) -> bool:
        """Check if this role is a werewolf."""
        return self == Role.WEREWOLF
    
    @property
    def is_villager(self) -> bool:
        """Check if this role is a plain villager."""
        return self == Role.VILLAGER


class Alignment(str, Enum):
    """Team alignment for win condition evaluation.
    
    - WEREWOLF: The werewolf team (bad guys)
    - GOOD: The village team including villagers and special roles
    """
    
    WEREWOLF = "werewolf"
    GOOD = "good"
    
    @classmethod
    def from_role(cls, role: Role) -> "Alignment":
        """Get the alignment for a given role."""
        if role == Role.WEREWOLF:
            return cls.WEREWOLF
        return cls.GOOD


class Phase(str, Enum):
    """Game phase enumeration.
    
    The game alternates between NIGHT and DAY phases.
    Special phases exist for specific game events.
    """
    
    NIGHT = "night"
    DAY = "day"
    SHERIFF_ELECTION = "sheriff_election"
    GAME_OVER = "game_over"


class WinningTeam(str, Enum):
    """Possible game outcomes.
    
    - VILLAGE: All werewolves eliminated
    - WEREWOLF: Side-elimination victory (all villagers OR all special roles dead)
    - NONE: Game still in progress
    """
    
    VILLAGE = "village"
    WEREWOLF = "werewolf"
    NONE = "none"


class WinMode(str, Enum):
    """Win condition mode configuration.
    
    - SIDE_ELIMINATION (Tu Bian): Werewolves win if ALL villagers OR ALL special roles are dead
    - CITY_ELIMINATION (Tu Cheng): Werewolves win if ALL good players are dead (less common)
    """
    
    SIDE_ELIMINATION = "side_elimination"
    CITY_ELIMINATION = "city_elimination"


class RoleSet(str, Enum):
    """Predefined role sets for 12-player games.
    
    - A: Seer, Witch, Hunter, Guard
    - B: Seer, Witch, Hunter, Village Idiot
    """
    
    A = "A"
    B = "B"


ROLE_SET_A_SPECIALS: list[Role] = [Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD]
ROLE_SET_B_SPECIALS: list[Role] = [Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGE_IDIOT]

DEFAULT_WEREWOLF_COUNT = 4
DEFAULT_VILLAGER_COUNT = 4
DEFAULT_SPECIAL_COUNT = 4
DEFAULT_PLAYER_COUNT = 12


def get_role_composition(role_set: RoleSet) -> list[Role]:
    """Get the full role composition for a 12-player game.
    
    Args:
        role_set: The role set variant (A or B)
        
    Returns:
        List of 12 roles for the game
    """
    werewolves = [Role.WEREWOLF] * DEFAULT_WEREWOLF_COUNT
    villagers = [Role.VILLAGER] * DEFAULT_VILLAGER_COUNT
    
    if role_set == RoleSet.A:
        specials = ROLE_SET_A_SPECIALS.copy()
    else:
        specials = ROLE_SET_B_SPECIALS.copy()
    
    return werewolves + villagers + specials
