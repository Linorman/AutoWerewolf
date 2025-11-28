from enum import Enum
from typing import Any, Dict

from autowerewolf.config.performance import VerbosityLevel
from autowerewolf.engine.roles import Role


class Language(str, Enum):
    """Supported languages for prompts."""
    EN = "en"
    ZH = "zh"


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
    PromptKey.SPEECH: (
        "{context}\n\nDeliver your speech. Only analyze players who already spoke. "
        "Do NOT accuse players who haven't spoken yet. Return JSON with 'content'."
    ),
    PromptKey.VOTE: (
        "{context}\n\nCast your vote from valid_targets list. "
        "Return JSON with 'target_player_id' and 'reasoning'."
    ),
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
    PromptKey.SPEECH: (
        "{context}\n\n"
        "Deliver your speech. Guidelines:\n"
        "1. ONLY analyze players who have ALREADY spoken (listed in 'spoken_players')\n"
        "2. Do NOT accuse or suspect players who haven't spoken yet - they simply haven't had their turn\n"
        "3. If you're speaking first/early, focus on sharing your own observations or role claims\n"
        "4. Base suspicions on actual behavior: speech content, voting patterns, contradictions\n"
        "5. Be strategic: consider what information benefits your team\n"
        "Return JSON with a 'content' field containing your speech."
    ),
    PromptKey.VOTE: (
        "{context}\n\n"
        "Cast your vote. Guidelines:\n"
        "1. You MUST select exactly one player_id from the valid_targets list\n"
        "2. Base your vote on evidence from speeches and observed behavior\n"
        "3. Consider voting patterns, contradictions, and suspicious defenses\n"
        "4. As village: vote for suspected werewolves; As werewolf: deflect to villagers\n"
        "Return JSON with 'target_player_id' (must be from valid_targets) and 'reasoning'."
    ),
    PromptKey.LAST_WORDS: "{context}\n\nYou are dying. Deliver your last words to help your team. Return JSON with 'content'.",
    PromptKey.SHERIFF_RUN: "{context}\n\nDecide whether to run for sheriff. Consider your role and strategy. Return JSON with 'run_for_sheriff' (bool).",
    PromptKey.BADGE_PASS: "{context}\n\nYou are dying as sheriff. Decide to pass or tear the badge. Return JSON with 'action' ('pass' or 'tear') and 'target_player_id' (if passing).",
}


# ============== Chinese Prompts ==============

MINIMAL_PROMPTS_ZH = {
    PromptKey.BASE_SYSTEM: "狼人杀游戏。按你的角色行动。简洁回应。使用JSON格式。",
    PromptKey.VILLAGER_SYSTEM: "村民。找出狼人。无技能。",
    PromptKey.WEREWOLF_SYSTEM: "狼人。杀村民。隐藏身份。",
    PromptKey.SEER_SYSTEM: "预言家。每晚查验一人。帮助村庄。",
    PromptKey.WITCH_SYSTEM: "女巫。解药(1次)或毒药(1次)。每晚只能用一瓶。",
    PromptKey.HUNTER_SYSTEM: "猎人。死亡时可开枪（被毒死除外）。",
    PromptKey.GUARD_SYSTEM: "守卫。每晚守护一人。不能连续守护同一人。",
    PromptKey.VILLAGE_IDIOT_SYSTEM: "白痴。被投票出局时翻牌存活。",
    PromptKey.NIGHT_ACTION: "{context}\n夜间行动：",
    PromptKey.SPEECH: "{context}\n发言：",
    PromptKey.VOTE: "{context}\n投票（必须从valid_targets中选择一名玩家）：",
    PromptKey.LAST_WORDS: "{context}\n遗言：",
    PromptKey.SHERIFF_RUN: "{context}\n是否竞选警长？",
    PromptKey.BADGE_PASS: "{context}\n传递或撕毁警徽？",
}


STANDARD_PROMPTS_ZH = {
    PromptKey.BASE_SYSTEM: (
        "你正在玩狼人杀（类似杀人游戏的社交推理游戏）。"
        "按照你角色的目标行动。策略性地思考并简洁回应。"
        "你必须使用严格的JSON格式回复。包含'thought'字段来解释你的推理。"
    ),
    PromptKey.VILLAGER_SYSTEM: (
        "你是村民。没有特殊能力。"
        "通过讨论和投票来找出并消灭狼人。"
    ),
    PromptKey.WEREWOLF_SYSTEM: (
        "你是狼人。在不被发现的情况下杀死村民。"
        "夜间行动：{{\"kill_target_id\": \"id\"}}。"
        "白天：融入村民并转移怀疑。"
    ),
    PromptKey.SEER_SYSTEM: (
        "你是预言家。每晚可以查验一名玩家的阵营。"
        "夜间行动：{{\"check_target_id\": \"id\"}}。"
        "策略性地使用信息。"
    ),
    PromptKey.WITCH_SYSTEM: (
        "你是女巫。药水：解药(1次)或毒药(1次)。"
        "夜间行动：{{\"use_cure\": bool, \"use_poison\": bool, \"poison_target_id\": \"id\"}}。"
        "每晚只能使用一瓶药水。"
    ),
    PromptKey.HUNTER_SYSTEM: (
        "你是猎人。当你死亡时（投票或狼人袭击，不是被毒死），"
        "可以射杀一名玩家。"
        "死亡行动：{{\"shoot\": bool, \"target_player_id\": \"id\"}}。"
    ),
    PromptKey.GUARD_SYSTEM: (
        "你是守卫。每晚可以守护一名玩家。"
        "夜间行动：{{\"protect_target_id\": \"id\"}}。"
        "不能连续两晚守护同一名玩家。"
    ),
    PromptKey.VILLAGE_IDIOT_SYSTEM: (
        "你是白痴。如果被投票出局，可以翻牌显示身份存活。"
        "像普通村民一样游戏。"
    ),
    PromptKey.NIGHT_ACTION: "{context}\n\n决定你的夜间行动。返回JSON格式。",
    PromptKey.SPEECH: (
        "{context}\n\n进行发言。只能分析已经发言的玩家。"
        "不要指责还未发言的玩家。返回JSON格式，包含'content'字段。"
    ),
    PromptKey.VOTE: (
        "{context}\n\n进行投票，从valid_targets列表选择。"
        "返回JSON格式，包含'target_player_id'和'reasoning'字段。"
    ),
    PromptKey.LAST_WORDS: "{context}\n\n发表遗言。返回JSON格式，包含'content'字段。",
    PromptKey.SHERIFF_RUN: "{context}\n\n决定是否竞选警长。返回JSON格式，包含'run_for_sheriff'(布尔值)。",
    PromptKey.BADGE_PASS: "{context}\n\n传递或撕毁警徽。返回JSON格式，包含'action'('pass'或'tear')和'target_player_id'(如果传递)。",
}


FULL_PROMPTS_ZH = {
    PromptKey.BASE_SYSTEM: (
        "你正在玩狼人杀（类似杀人游戏的社交推理游戏）。"
        "你必须按照你角色的目标行动。"
        "仔细分析游戏状态并做出策略性决定。"
        "在行动前考虑所有可用信息。"
        "回复格式：你必须使用严格的JSON格式回复。"
        "包含'thought'字段来逐步解释你的推理，"
        "然后是你行动所需的特定字段。"
    ),
    PromptKey.VILLAGER_SYSTEM: (
        "你是村民。你没有特殊能力。"
        "你的目标是通过讨论和投票来找出并消灭所有狼人。"
        "运用逻辑和观察他人行为来推断谁是狼人。"
        "支持你信任的玩家的言论，质疑可疑的行为。"
        "注意投票模式、发言一致性和防守性行为。"
    ),
    PromptKey.WEREWOLF_SYSTEM: (
        "你是狼人。你的目标是在不被发现的情况下消灭村民。"
        "夜晚，与你的狼人同伴协调选择一个目标杀害。"
        "夜间行动格式：{{\"kill_target_id\": \"<player_id>\"}}\n"
        "白天，融入村民并将怀疑转移到其他人身上。"
        "你可以伪装成任何角色来生存 - 策略性地考虑伪装成村民或神职角色。"
        "胜利条件：消灭所有村民或所有神职角色。"
    ),
    PromptKey.SEER_SYSTEM: (
        "你是预言家。每晚你可以查验一名玩家来了解他们是好人还是狼人。"
        "夜间行动格式：{{\"check_target_id\": \"<player_id>\"}}\n"
        "策略性地使用这些信息 - 过早暴露可能导致你被杀，"
        "但等待太久意味着信息会随你一起死去。"
        "'金水'指验证过的好人。'查杀'指验证过的狼人。"
        "你的目标是帮助村庄找出狼人，同时保护自己。"
    ),
    PromptKey.WITCH_SYSTEM: (
        "你是女巫。你有两瓶一次性药水："
        "1) 解药：救活今晚被狼人杀死的玩家（你会被告知是谁）。"
        "2) 毒药：杀死你选择的任何玩家。"
        "夜间行动格式：{{\"use_cure\": true/false, \"use_poison\": true/false, \"poison_target_id\": \"<player_id>\"}}\n"
        "每晚只能使用一瓶药水。明智地使用它们 - 它们是你最强大的工具。"
        "'银水'指你救过的人 - 通常被认为是值得信任的。"
        "你的目标是在关键时刻使用药水帮助村庄获胜。"
    ),
    PromptKey.HUNTER_SYSTEM: (
        "你是猎人。当你死亡时（被投票或被狼人袭击，不是被毒死），"
        "你可以射杀一名玩家带走他们。"
        "死亡行动格式：{{\"shoot\": true/false, \"target_player_id\": \"<player_id>\"}}\n"
        "白天正常参与讨论和投票。"
        "明智地使用你的射击 - 最好是带走一个确认或怀疑的狼人。"
        "如果被女巫的毒药杀死，你不能开枪。主持人会告诉你你的状态。"
    ),
    PromptKey.GUARD_SYSTEM: (
        "你是守卫。每晚你可以守护一名玩家免受狼人袭击。"
        "夜间行动格式：{{\"protect_target_id\": \"<player_id>\"}}\n"
        "你不能连续两晚守护同一名玩家。"
        "警告：如果你守护的人女巫也救了，他们仍然会死（'同守同救'）。"
        "考虑守护预言家等关键角色，如果他们的身份已暴露。"
        "你的目标是通过守护重要玩家帮助村庄生存。"
    ),
    PromptKey.VILLAGE_IDIOT_SYSTEM: (
        "你是白痴。如果你在白天被投票出局，"
        "你可以翻牌显示身份存活（但失去投票权）。"
        "翻牌后你获得打断他人发言的能力。"
        "像普通村民一样游戏，但记住你有防止误杀的安全网。"
        "如果晚上被杀，你会正常死亡，没有保护。"
    ),
    PromptKey.NIGHT_ACTION: "{context}\n\n决定你的夜间行动。确保你的JSON回复符合你角色的行动格式。",
    PromptKey.SPEECH: (
        "{context}\n\n"
        "进行发言。发言指南：\n"
        "1. 只能分析已经发言的玩家（在'spoken_players'中列出的玩家）\n"
        "2. 不要指责或怀疑还未发言的玩家——他们只是还没轮到发言\n"
        "3. 如果你是第一个或靠前发言，重点分享你的观察或报身份\n"
        "4. 怀疑要基于实际行为：发言内容、投票模式、矛盾之处\n"
        "5. 策略性发言：考虑什么信息对你的阵营有利\n"
        "返回JSON格式，包含'content'字段。"
    ),
    PromptKey.VOTE: (
        "{context}\n\n"
        "进行投票。投票指南：\n"
        "1. 必须从valid_targets列表中选择一名玩家的player_id\n"
        "2. 根据发言内容和观察到的行为进行投票\n"
        "3. 考虑投票模式、矛盾之处和可疑的辩护\n"
        "4. 好人阵营：投票给怀疑的狼人；狼人阵营：把票引向村民\n"
        "返回JSON格式，包含'target_player_id'（必须来自valid_targets）和'reasoning'字段。"
    ),
    PromptKey.LAST_WORDS: "{context}\n\n你即将死亡。发表遗言帮助你的队伍。返回JSON格式，包含'content'字段。",
    PromptKey.SHERIFF_RUN: "{context}\n\n决定是否竞选警长。考虑你的角色和策略。返回JSON格式，包含'run_for_sheriff'(布尔值)。",
    PromptKey.BADGE_PASS: "{context}\n\n你即将作为警长死亡。决定传递或撕毁警徽。返回JSON格式，包含'action'('pass'或'tear')和'target_player_id'(如果传递)。",
}


# English prompts by verbosity
PROMPTS_BY_VERBOSITY_EN: Dict[VerbosityLevel, Dict[PromptKey, str]] = {
    VerbosityLevel.MINIMAL: MINIMAL_PROMPTS,
    VerbosityLevel.STANDARD: STANDARD_PROMPTS,
    VerbosityLevel.FULL: FULL_PROMPTS,
}

# Chinese prompts by verbosity
PROMPTS_BY_VERBOSITY_ZH: Dict[VerbosityLevel, Dict[PromptKey, str]] = {
    VerbosityLevel.MINIMAL: MINIMAL_PROMPTS_ZH,
    VerbosityLevel.STANDARD: STANDARD_PROMPTS_ZH,
    VerbosityLevel.FULL: FULL_PROMPTS_ZH,
}

# Combined prompts by language
PROMPTS_BY_LANGUAGE: Dict[Language, Dict[VerbosityLevel, Dict[PromptKey, str]]] = {
    Language.EN: PROMPTS_BY_VERBOSITY_EN,
    Language.ZH: PROMPTS_BY_VERBOSITY_ZH,
}

# Default language prompts (for backward compatibility)
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


# Global language setting (default to English)
_current_language: Language = Language.EN


def set_language(language: Language | str) -> None:
    """Set the global language for prompts.
    
    Args:
        language: Language enum value or string ('en', 'zh')
    """
    global _current_language
    if isinstance(language, str):
        language = Language(language.lower())
    _current_language = language


def get_language() -> Language:
    """Get the current global language setting."""
    return _current_language


def get_prompt(
    key: PromptKey,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    language: Language | str | None = None,
) -> str:
    """Get a prompt by key, verbosity level, and language.
    
    Args:
        key: The prompt key
        verbosity: Verbosity level (MINIMAL, STANDARD, FULL)
        language: Language to use. If None, uses global setting.
    
    Returns:
        The prompt string
    """
    if language is None:
        lang = _current_language
    elif isinstance(language, str):
        lang = Language(language.lower())
    else:
        lang = language
    
    prompts_by_verbosity = PROMPTS_BY_LANGUAGE.get(lang, PROMPTS_BY_VERBOSITY_EN)
    prompts = prompts_by_verbosity.get(verbosity, prompts_by_verbosity.get(VerbosityLevel.STANDARD, {}))
    
    # Fallback to English if key not found
    if key not in prompts:
        fallback = PROMPTS_BY_VERBOSITY_EN.get(verbosity, STANDARD_PROMPTS)
        return fallback.get(key, "")
    
    return prompts.get(key, "")


def get_role_system_prompt(
    role: Role,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    language: Language | str | None = None,
) -> str:
    """Get the system prompt for a specific role.
    
    Args:
        role: The player role
        verbosity: Verbosity level
        language: Language to use. If None, uses global setting.
    
    Returns:
        The role system prompt
    """
    prompt_key = ROLE_TO_PROMPT_KEY.get(role, PromptKey.VILLAGER_SYSTEM)
    return get_prompt(prompt_key, verbosity, language)


def get_base_system_prompt(
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    language: Language | str | None = None,
) -> str:
    """Get the base system prompt.
    
    Args:
        verbosity: Verbosity level
        language: Language to use. If None, uses global setting.
    
    Returns:
        The base system prompt
    """
    return get_prompt(PromptKey.BASE_SYSTEM, verbosity, language)


def format_prompt(
    key: PromptKey,
    verbosity: VerbosityLevel = VerbosityLevel.STANDARD,
    language: Language | str | None = None,
    **kwargs: Any,
) -> str:
    """Format a prompt with the given kwargs.
    
    Args:
        key: The prompt key
        verbosity: Verbosity level
        language: Language to use. If None, uses global setting.
        **kwargs: Values to format into the prompt template
    
    Returns:
        The formatted prompt
    """
    template = get_prompt(key, verbosity, language)
    return template.format(**kwargs)


# ============== Role name translations ==============

ROLE_NAMES: Dict[Language, Dict[Role, str]] = {
    Language.EN: {
        Role.VILLAGER: "Villager",
        Role.WEREWOLF: "Werewolf",
        Role.SEER: "Seer",
        Role.WITCH: "Witch",
        Role.HUNTER: "Hunter",
        Role.GUARD: "Guard",
        Role.VILLAGE_IDIOT: "Village Idiot",
    },
    Language.ZH: {
        Role.VILLAGER: "村民",
        Role.WEREWOLF: "狼人",
        Role.SEER: "预言家",
        Role.WITCH: "女巫",
        Role.HUNTER: "猎人",
        Role.GUARD: "守卫",
        Role.VILLAGE_IDIOT: "白痴",
    },
}


def get_role_name(role: Role | str, language: Language | str | None = None) -> str:
    """Get the localized name for a role.
    
    Args:
        role: The role (Role enum or string)
        language: Language to use. If None, uses global setting.
    
    Returns:
        The localized role name
    """
    if language is None:
        lang = _current_language
    elif isinstance(language, str):
        lang = Language(language.lower())
    else:
        lang = language
    
    # Convert string to Role enum if needed
    if isinstance(role, str):
        try:
            role = Role(role.lower())
        except ValueError:
            return role  # Return the string as-is if not a valid role
    
    role_names = ROLE_NAMES.get(lang, ROLE_NAMES[Language.EN])
    return role_names.get(role, role.value)


# ============== Game context translations ==============

CONTEXT_TEMPLATES: Dict[Language, Dict[str, str]] = {
    Language.EN: {
        "player_intro": "You are Player {name} (ID: {player_id})",
        "role_info": "Your role: {role}",
        "phase_info": "Current phase: {phase} (Day {day})",
        "alive_players": "Alive players:",
        "player_entry": "  - {name} (ID: {id}, Seat: {seat}){sheriff}",
        "sheriff_mark": " [Sheriff]",
        "dead_players": "Dead players (CANNOT be targeted for votes or actions):",
        "dead_player_entry": "  - {name} (ID: {id}, Seat: {seat}) [DEAD]",
        "private_info": "Your private information:",
        "action_context": "Action context:",
        "recent_events": "Recent public events:",
        "valid_targets": "Valid targets for your action:",
        "werewolf_teammates": "Your werewolf teammates:",
        "seer_results": "Your check results:",
        "witch_potions": "Your potions - Cure: {cure}, Poison: {poison}",
        "attack_target": "Tonight's attack target: {target}",
        "last_protected": "Last protected: {target}",
        "cannot_protect_same": "You cannot protect the same player twice in a row.",
        "speech_order_info": "Speech order information:",
        "your_speech_position": "  You are speaking at position {position}/{total}",
        "spoken_players": "  Players who have already spoken:",
        "pending_players": "  Players who have not yet spoken:",
        "speech_guidance": "  IMPORTANT: Only analyze and comment on players who have ALREADY spoken. Do NOT accuse or suspect players who have not spoken yet - they simply have not had their turn.",
    },
    Language.ZH: {
        "player_intro": "你是玩家 {name}（ID: {player_id}）",
        "role_info": "你的身份: {role}",
        "phase_info": "当前阶段: {phase}（第 {day} 天）",
        "alive_players": "存活玩家:",
        "player_entry": "  - {name}（ID: {id}, 座位: {seat}）{sheriff}",
        "sheriff_mark": " [警长]",
        "dead_players": "死亡玩家（不能作为投票或行动的目标）:",
        "dead_player_entry": "  - {name}（ID: {id}, 座位: {seat}）[已死亡]",
        "private_info": "你的私密信息:",
        "action_context": "行动上下文:",
        "recent_events": "最近的公开事件:",
        "valid_targets": "你行动的有效目标:",
        "werewolf_teammates": "你的狼队友:",
        "seer_results": "你的查验结果:",
        "witch_potions": "你的药水 - 解药: {cure}, 毒药: {poison}",
        "attack_target": "今晚被袭击的目标: {target}",
        "last_protected": "上次守护的人: {target}",
        "cannot_protect_same": "你不能连续两晚守护同一名玩家。",
        "speech_order_info": "发言顺序信息:",
        "your_speech_position": "  你是第 {position}/{total} 个发言",
        "spoken_players": "  已经发言的玩家:",
        "pending_players": "  还未发言的玩家:",
        "speech_guidance": "  重要：只能分析和评论已经发言的玩家。不要指责或怀疑还未发言的玩家——他们只是还没轮到发言。",
    },
}


def get_context_template(key: str, language: Language | str | None = None) -> str:
    """Get a context template string.
    
    Args:
        key: The template key
        language: Language to use. If None, uses global setting.
    
    Returns:
        The template string
    """
    if language is None:
        lang = _current_language
    elif isinstance(language, str):
        lang = Language(language.lower())
    else:
        lang = language
    
    templates = CONTEXT_TEMPLATES.get(lang, CONTEXT_TEMPLATES[Language.EN])
    return templates.get(key, CONTEXT_TEMPLATES[Language.EN].get(key, key))

