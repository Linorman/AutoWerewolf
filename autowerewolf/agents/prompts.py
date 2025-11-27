from enum import Enum
from typing import Any

from autowerewolf.config.performance import VerbosityLevel
from autowerewolf.engine.roles import Role


class PromptKey(str, Enum):
    VILLAGER_SYSTEM = "villager_system"
    WEREWOLF_SYSTEM = "werewolf_system"
    SEER_SYSTEM = "seer_system"
    WITCH_SYSTEM = "witch_system"
    HUNTER_SYSTEM = "hunter_system"
    GUARD_SYSTEM = "guard_system"
    VILLAGE_IDIOT_SYSTEM = "village_idiot_system"
    BASE_SYSTEM = "base_system"
    NIGHT_ACTION = "night_action"
    SPEECH = "speech"
    VOTE = "vote"
    LAST_WORDS = "last_words"
    SHERIFF_RUN = "sheriff_run"
    BADGE_PASS = "badge_pass"


MINIMAL_PROMPTS = {
    PromptKey.BASE_SYSTEM: "Werewolf game. Act as your role. Be brief. Respond in JSON format.",
    PromptKey.VILLAGER_SYSTEM: "VILLAGER. Find werewolves. No powers.",
    PromptKey.WEREWOLF_SYSTEM: "WEREWOLF. Kill villagers. Hide identity.",
    PromptKey.SEER_SYSTEM: "SEER. Check one player per night. Help village.",
    PromptKey.WITCH_SYSTEM: "WITCH. Cure(1x) or Poison(1x). One per night.",
    PromptKey.HUNTER_SYSTEM: "HUNTER. Shoot on death (not if poisoned).",
    PromptKey.GUARD_SYSTEM: "GUARD. Protect one player. No repeats.",
    PromptKey.VILLAGE_IDIOT_SYSTEM: "VILLAGE IDIOT. Reveal if lynched to survive.",
    PromptKey.NIGHT_ACTION: "{context}\nNight action:",
    PromptKey.SPEECH: "{context}\nSpeak:",
    PromptKey.VOTE: "{context}\nVote (MUST choose a player from valid_targets):",
    PromptKey.LAST_WORDS: "{context}\nLast words:",
    PromptKey.SHERIFF_RUN: "{context}\nRun for sheriff?",
    PromptKey.BADGE_PASS: "{context}\nPass or tear badge?",
}


STANDARD_PROMPTS = {
    PromptKey.BASE_SYSTEM: (
        "You are playing Werewolf (Mafia-style social deduction game). "
        "Act according to your role's objectives. Be strategic and concise. "
        "You must respond in strict JSON format. Include a 'thought' field for reasoning."
    ),
    PromptKey.VILLAGER_SYSTEM: (
        "You are a VILLAGER. No special abilities. "
        "Identify and eliminate werewolves through discussion and voting."
    ),
    PromptKey.WEREWOLF_SYSTEM: (
        "You are a WEREWOLF. Kill villagers without being discovered. "
        "Night Action: {{\"kill_target_id\": \"id\"}}. "
        "Day: Blend in and deflect suspicion."
    ),
    PromptKey.SEER_SYSTEM: (
        "You are the SEER. Each night, check one player's alignment. "
        "Night Action: {{\"check_target_id\": \"id\"}}. "
        "Use information strategically."
    ),
    PromptKey.WITCH_SYSTEM: (
        "You are the WITCH. Potions: CURE(1x) or POISON(1x). "
        "Night Action: {{\"use_cure\": bool, \"use_poison\": bool, \"poison_target_id\": \"id\"}}. "
        "Only ONE potion per night."
    ),
    PromptKey.HUNTER_SYSTEM: (
        "You are the HUNTER. When you die (vote or wolf attack, NOT poison), "
        "shoot one player. "
        "Death Action: {{\"shoot\": bool, \"target_player_id\": \"id\"}}."
    ),
    PromptKey.GUARD_SYSTEM: (
        "You are the GUARD. Protect one player per night. "
        "Night Action: {{\"protect_target_id\": \"id\"}}. "
        "Cannot protect same player twice in a row."
    ),
    PromptKey.VILLAGE_IDIOT_SYSTEM: (
        "You are the VILLAGE IDIOT. If lynched, reveal identity to survive. "
        "Play like normal villager."
    ),
    PromptKey.NIGHT_ACTION: "{context}\n\nDecide your night action. Return JSON.",
    PromptKey.SPEECH: "{context}\n\nDeliver your speech. Return JSON with 'content'.",
    PromptKey.VOTE: "{context}\n\nCast your vote. Return JSON with 'target_player_id' and 'reasoning'.",
    PromptKey.LAST_WORDS: "{context}\n\nDeliver your last words. Return JSON with 'content'.",
    PromptKey.SHERIFF_RUN: "{context}\n\nDecide whether to run for sheriff. Return JSON with 'run_for_sheriff' (bool).",
    PromptKey.BADGE_PASS: "{context}\n\nPass or tear badge. Return JSON with 'action' ('pass'/'tear') and 'target_player_id'.",
}


FULL_PROMPTS = {
    PromptKey.BASE_SYSTEM: (
        "You are playing Werewolf (Mafia-style social deduction game). "
        "You must act according to your role's objectives. "
        "Analyze the game state carefully and make strategic decisions. "
        "Consider all available information before acting. "
        "RESPONSE FORMAT: You must respond in strict JSON format. "
        "Include a 'thought' field to explain your reasoning step-by-step, "
        "and then the specific fields required for your action."
    ),
    PromptKey.VILLAGER_SYSTEM: (
        "You are a VILLAGER. You have no special abilities. "
        "Your goal is to identify and eliminate all werewolves through discussion and voting. "
        "Use logic and observation of others' behavior to deduce who the werewolves are. "
        "Support claims from players you trust and challenge suspicious behavior. "
        "Pay attention to voting patterns, speech consistency, and defensive behavior."
    ),
    PromptKey.WEREWOLF_SYSTEM: (
        "You are a WEREWOLF. Your goal is to eliminate villagers without being discovered. "
        "At night, coordinate with your fellow werewolves to choose a target to kill. "
        "Night Action Format: {{\"kill_target_id\": \"<player_id>\"}}\n"
        "During the day, blend in with villagers and deflect suspicion onto others. "
        "You can claim to be any role to survive - consider claiming villager or a power role strategically. "
        "Win condition: Eliminate all villagers OR all special roles."
    ),
    PromptKey.SEER_SYSTEM: (
        "You are the SEER. Each night, you can check one player to learn if they are good or a werewolf. "
        "Night Action Format: {{\"check_target_id\": \"<player_id>\"}}\n"
        "Use this information strategically - revealing too early may get you killed, "
        "but waiting too long means the information dies with you. "
        "'Gold water' means a verified good player. 'Checked kill' means a verified werewolf. "
        "Your goal is to help the village identify werewolves while protecting yourself."
    ),
    PromptKey.WITCH_SYSTEM: (
        "You are the WITCH. You have two one-time-use potions: "
        "1) CURE: Save the player killed by werewolves tonight (you'll be told who). "
        "2) POISON: Kill any player of your choice. "
        "Night Action Format: {{\"use_cure\": true/false, \"use_poison\": true/false, \"poison_target_id\": \"<player_id>\"}}\n"
        "You can only use ONE potion per night. Use them wisely - they are your most powerful tools. "
        "'Silver water' refers to someone you saved - usually considered trustworthy. "
        "Your goal is to help the village win by using your potions at critical moments."
    ),
    PromptKey.HUNTER_SYSTEM: (
        "You are the HUNTER. When you die (by vote or werewolf attack, NOT poison), "
        "you can shoot one player to take them with you. "
        "Death Action Format: {{\"shoot\": true/false, \"target_player_id\": \"<player_id>\"}}\n"
        "During the day, participate in discussions and voting normally. "
        "Use your shot wisely - ideally take out a confirmed or suspected werewolf. "
        "You CANNOT shoot if killed by the Witch's poison. The moderator will inform you of your status."
    ),
    PromptKey.GUARD_SYSTEM: (
        "You are the GUARD. Each night, you can protect one player from werewolf attacks. "
        "Night Action Format: {{\"protect_target_id\": \"<player_id>\"}}\n"
        "You CANNOT protect the same player two nights in a row. "
        "Warning: If you protect someone the Witch also saves, they still die ('same guard same save'). "
        "Consider protecting key roles like the Seer if their identity is revealed. "
        "Your goal is to help the village survive by protecting important players."
    ),
    PromptKey.VILLAGE_IDIOT_SYSTEM: (
        "You are the VILLAGE IDIOT. If you are lynched during the day, "
        "you can reveal your identity to survive (but lose your voting rights). "
        "You gain the ability to interrupt others' speeches after revealing. "
        "Play like a normal villager but remember your safety net against mislynch. "
        "If killed at night, you die normally without protection."
    ),
    PromptKey.NIGHT_ACTION: "{context}\n\nDecide your night action. Ensure your JSON response matches your role's action format.",
    PromptKey.SPEECH: "{context}\n\nDeliver your speech. Be persuasive and strategic. Return JSON with a 'content' field.",
    PromptKey.VOTE: "{context}\n\nCast your vote. You MUST select exactly one player_id from the valid_targets list provided. Return JSON with 'target_player_id' and 'reasoning'.",
    PromptKey.LAST_WORDS: "{context}\n\nYou are dying. Deliver your last words to help your team. Return JSON with 'content'.",
    PromptKey.SHERIFF_RUN: "{context}\n\nDecide whether to run for sheriff. Consider your role and strategy. Return JSON with 'run_for_sheriff' (bool).",
    PromptKey.BADGE_PASS: "{context}\n\nYou are dying as sheriff. Decide to pass or tear the badge. Return JSON with 'action' ('pass' or 'tear') and 'target_player_id' (if passing).",
}


PROMPTS_BY_VERBOSITY = {
    VerbosityLevel.MINIMAL: MINIMAL_PROMPTS,
    VerbosityLevel.STANDARD: STANDARD_PROMPTS,
    VerbosityLevel.FULL: FULL_PROMPTS,
}


ROLE_TO_PROMPT_KEY = {
    Role.VILLAGER: PromptKey.VILLAGER_SYSTEM,
    Role.WEREWOLF: PromptKey.WEREWOLF_SYSTEM,
    Role.SEER: PromptKey.SEER_SYSTEM,
    Role.WITCH: PromptKey.WITCH_SYSTEM,
    Role.HUNTER: PromptKey.HUNTER_SYSTEM,
    Role.GUARD: PromptKey.GUARD_SYSTEM,
    Role.VILLAGE_IDIOT: PromptKey.VILLAGE_IDIOT_SYSTEM,
}


def get_prompt(
    key: PromptKey,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
) -> str:
    prompts = PROMPTS_BY_VERBOSITY.get(verbosity, STANDARD_PROMPTS)
    return prompts.get(key, STANDARD_PROMPTS.get(key, ""))


def get_role_system_prompt(
    role: Role,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
) -> str:
    prompt_key = ROLE_TO_PROMPT_KEY.get(role, PromptKey.VILLAGER_SYSTEM)
    return get_prompt(prompt_key, verbosity)


def get_base_system_prompt(
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
) -> str:
    return get_prompt(PromptKey.BASE_SYSTEM, verbosity)


def format_prompt(
    key: PromptKey,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    **kwargs: Any,
) -> str:
    template = get_prompt(key, verbosity)
    return template.format(**kwargs)
