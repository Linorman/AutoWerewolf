from enum import Enum


class Role(str, Enum):
    """Game roles."""

    WEREWOLF = "werewolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    GUARD = "guard"
    VILLAGE_IDIOT = "village_idiot"

    @property
    def is_special(self) -> bool:
        """True for non-basic villager roles."""
        return self in {
            Role.SEER,
            Role.WITCH,
            Role.HUNTER,
            Role.GUARD,
            Role.VILLAGE_IDIOT,
        }

    @property
    def is_werewolf(self) -> bool:
        return self == Role.WEREWOLF

    @property
    def is_villager(self) -> bool:
        return self == Role.VILLAGER


class Alignment(str, Enum):
    """Team alignment."""

    WEREWOLF = "werewolf"
    GOOD = "good"

    @classmethod
    def from_role(cls, role: Role) -> "Alignment":
        return cls.WEREWOLF if role == Role.WEREWOLF else cls.GOOD


class Phase(str, Enum):
    """Game phases."""

    NIGHT = "night"
    DAY = "day"
    SHERIFF_ELECTION = "sheriff_election"
    GAME_OVER = "game_over"


class WinningTeam(str, Enum):
    VILLAGE = "village"
    WEREWOLF = "werewolf"
    NONE = "none"


class WinMode(str, Enum):
    SIDE_ELIMINATION = "side_elimination"
    CITY_ELIMINATION = "city_elimination"


class RoleSet(str, Enum):
    A = "A"
    B = "B"


ROLE_SET_A_SPECIALS: list[Role] = [Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD]
ROLE_SET_B_SPECIALS: list[Role] = [Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGE_IDIOT]

DEFAULT_WEREWOLF_COUNT = 4
DEFAULT_VILLAGER_COUNT = 4
DEFAULT_SPECIAL_COUNT = 4
DEFAULT_PLAYER_COUNT = 12


def get_role_composition(role_set: RoleSet) -> list[Role]:
    """Return the standard 12-player role list for a given set."""
    werewolves = [Role.WEREWOLF] * DEFAULT_WEREWOLF_COUNT
    villagers = [Role.VILLAGER] * DEFAULT_VILLAGER_COUNT
    specials = ROLE_SET_A_SPECIALS.copy() if role_set == RoleSet.A else ROLE_SET_B_SPECIALS.copy()
    return werewolves + villagers + specials
