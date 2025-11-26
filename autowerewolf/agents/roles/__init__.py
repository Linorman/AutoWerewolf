"""Role-specific agent implementations."""

from autowerewolf.agents.roles.guard import GuardAgent
from autowerewolf.agents.roles.hunter import HunterAgent
from autowerewolf.agents.roles.seer import SeerAgent, SeerRevealDecision
from autowerewolf.agents.roles.village_idiot import VillageIdiotAgent, VillageIdiotRevealDecision
from autowerewolf.agents.roles.villager import VillagerAgent
from autowerewolf.agents.roles.werewolf import (
    WerewolfAgent,
    WerewolfDiscussionChain,
    SelfExplodeDecision,
)
from autowerewolf.agents.roles.witch import WitchAgent
from autowerewolf.engine.roles import Role

ROLE_AGENT_MAP: dict[Role, type] = {
    Role.VILLAGER: VillagerAgent,
    Role.WEREWOLF: WerewolfAgent,
    Role.SEER: SeerAgent,
    Role.WITCH: WitchAgent,
    Role.HUNTER: HunterAgent,
    Role.GUARD: GuardAgent,
    Role.VILLAGE_IDIOT: VillageIdiotAgent,
}

__all__ = [
    "GuardAgent",
    "HunterAgent",
    "SeerAgent",
    "SeerRevealDecision",
    "VillageIdiotAgent",
    "VillageIdiotRevealDecision",
    "VillagerAgent",
    "WerewolfAgent",
    "WerewolfDiscussionChain",
    "SelfExplodeDecision",
    "WitchAgent",
    "ROLE_AGENT_MAP",
]
