from enum import Enum
from typing import Dict, Optional


class Language(str, Enum):
    EN = "en"
    ZH = "zh"


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "app_title": {
        "en": "AutoWerewolf",
        "zh": "自动狼人杀",
    },
    "watch_mode": {
        "en": "Watch Mode",
        "zh": "观看模式",
    },
    "play_mode": {
        "en": "Play Mode",
        "zh": "游戏模式",
    },
    "watch_desc": {
        "en": "Watch AI agents play",
        "zh": "观看AI对局",
    },
    "play_desc": {
        "en": "Join the game as a player",
        "zh": "作为玩家参与游戏",
    },
    "start_game": {
        "en": "Start Game",
        "zh": "开始游戏",
    },
    "stop_game": {
        "en": "Stop Game",
        "zh": "停止游戏",
    },
    "game_config": {
        "en": "Game Configuration",
        "zh": "游戏配置",
    },
    "model_config": {
        "en": "Model Settings",
        "zh": "模型设置",
    },
    "backend": {
        "en": "Backend",
        "zh": "后端",
    },
    "model_name": {
        "en": "Model Name",
        "zh": "模型名称",
    },
    "temperature": {
        "en": "Temperature",
        "zh": "温度",
    },
    "max_tokens": {
        "en": "Max Tokens",
        "zh": "最大Token数",
    },
    "game_rules": {
        "en": "Game Rules",
        "zh": "游戏规则",
    },
    "role_set": {
        "en": "Role Set",
        "zh": "角色集",
    },
    "role_set_a": {
        "en": "Set A (Guard)",
        "zh": "角色集A (守卫)",
    },
    "role_set_b": {
        "en": "Set B (Village Idiot)",
        "zh": "角色集B (白痴)",
    },
    "random_seed": {
        "en": "Random Seed (optional)",
        "zh": "随机种子（可选）",
    },
    "game_language": {
        "en": "Game Language",
        "zh": "游戏语言",
    },
    "game_language_hint": {
        "en": "Language used for AI agent prompts",
        "zh": "用于AI代理提示词的语言",
    },
    "player_settings": {
        "en": "Player Settings",
        "zh": "玩家设置",
    },
    "your_seat": {
        "en": "Your Seat",
        "zh": "你的座位",
    },
    "your_name": {
        "en": "Your Name",
        "zh": "你的名字",
    },
    "day": {
        "en": "Day",
        "zh": "天数",
    },
    "night": {
        "en": "Night",
        "zh": "夜晚",
    },
    "phase": {
        "en": "Phase",
        "zh": "阶段",
    },
    "alive": {
        "en": "Alive",
        "zh": "存活",
    },
    "dead": {
        "en": "Dead",
        "zh": "死亡",
    },
    "sheriff": {
        "en": "Sheriff",
        "zh": "警长",
    },
    "players": {
        "en": "Players",
        "zh": "玩家",
    },
    "events": {
        "en": "Events",
        "zh": "事件",
    },
    "game_over": {
        "en": "Game Over",
        "zh": "游戏结束",
    },
    "village_wins": {
        "en": "🎉 Village Wins!",
        "zh": "🎉 好人阵营胜利！",
    },
    "werewolf_wins": {
        "en": "🐺 Werewolves Win!",
        "zh": "🐺 狼人阵营胜利！",
    },
    "waiting": {
        "en": "Waiting...",
        "zh": "等待中...",
    },
    "your_turn": {
        "en": "Your Turn",
        "zh": "轮到你了",
    },
    "submit": {
        "en": "Submit",
        "zh": "提交",
    },
    "skip": {
        "en": "Skip",
        "zh": "跳过",
    },
    "vote": {
        "en": "Vote",
        "zh": "投票",
    },
    "speech": {
        "en": "Speech",
        "zh": "发言",
    },
    "werewolf": {
        "en": "Werewolf",
        "zh": "狼人",
    },
    "villager": {
        "en": "Villager",
        "zh": "村民",
    },
    "seer": {
        "en": "Seer",
        "zh": "预言家",
    },
    "witch": {
        "en": "Witch",
        "zh": "女巫",
    },
    "hunter": {
        "en": "Hunter",
        "zh": "猎人",
    },
    "guard": {
        "en": "Guard",
        "zh": "守卫",
    },
    "village_idiot": {
        "en": "Village Idiot",
        "zh": "白痴",
    },
    "hidden": {
        "en": "???",
        "zh": "???",
    },
    "action_kill": {
        "en": "Kill Target",
        "zh": "击杀目标",
    },
    "action_check": {
        "en": "Check Target",
        "zh": "查验目标",
    },
    "action_save": {
        "en": "Save Target",
        "zh": "救治目标",
    },
    "action_poison": {
        "en": "Poison Target",
        "zh": "毒杀目标",
    },
    "action_protect": {
        "en": "Protect Target",
        "zh": "保护目标",
    },
    "action_shoot": {
        "en": "Shoot Target",
        "zh": "射击目标",
    },
    "use_cure": {
        "en": "Use Cure",
        "zh": "使用解药",
    },
    "use_poison": {
        "en": "Use Poison",
        "zh": "使用毒药",
    },
    "run_for_sheriff": {
        "en": "Run for Sheriff",
        "zh": "竞选警长",
    },
    "pass_badge": {
        "en": "Pass Badge",
        "zh": "传递警徽",
    },
    "tear_badge": {
        "en": "Tear Badge",
        "zh": "撕毁警徽",
    },
    "last_words": {
        "en": "Last Words",
        "zh": "遗言",
    },
    "connecting": {
        "en": "Connecting...",
        "zh": "连接中...",
    },
    "connected": {
        "en": "Connected",
        "zh": "已连接",
    },
    "disconnected": {
        "en": "Disconnected",
        "zh": "已断开",
    },
    "error": {
        "en": "Error",
        "zh": "错误",
    },
    "api_base": {
        "en": "API Base URL",
        "zh": "API基础URL",
    },
    "api_key": {
        "en": "API Key",
        "zh": "API密钥",
    },
    "ollama_url": {
        "en": "Ollama URL",
        "zh": "Ollama地址",
    },
    "game_speed": {
        "en": "Game Speed",
        "zh": "游戏速度",
    },
    "speed_slow": {
        "en": "Slow",
        "zh": "慢速",
    },
    "speed_normal": {
        "en": "Normal",
        "zh": "正常",
    },
    "speed_fast": {
        "en": "Fast",
        "zh": "快速",
    },
    "language": {
        "en": "Language",
        "zh": "语言",
    },
    "english": {
        "en": "English",
        "zh": "英语",
    },
    "chinese": {
        "en": "Chinese",
        "zh": "中文",
    },
    "game_log": {
        "en": "Game Progress",
        "zh": "游戏进程",
    },
    "no_game_running": {
        "en": "No game running",
        "zh": "没有正在进行的游戏",
    },
    "select_target": {
        "en": "Select Target",
        "zh": "选择目标",
    },
    "enter_speech": {
        "en": "Enter your speech...",
        "zh": "输入你的发言...",
    },
    "confirm": {
        "en": "Confirm",
        "zh": "确认",
    },
    "cancel": {
        "en": "Cancel",
        "zh": "取消",
    },
    "seat": {
        "en": "Seat",
        "zh": "座位",
    },
    "role": {
        "en": "Role",
        "zh": "角色",
    },
    "status": {
        "en": "Status",
        "zh": "状态",
    },
    "game_not_started": {
        "en": "Game Not Started",
        "zh": "游戏未开始",
    },
    "game_in_progress": {
        "en": "Game In Progress",
        "zh": "游戏进行中",
    },
    "waiting_for_action": {
        "en": "Waiting for action...",
        "zh": "等待操作...",
    },
    "night_action": {
        "en": "Night Action",
        "zh": "夜间行动",
    },
    "day_discussion": {
        "en": "Day Discussion",
        "zh": "白天讨论",
    },
    "voting_phase": {
        "en": "Voting Phase",
        "zh": "投票阶段",
    },
    "sheriff_election": {
        "en": "Sheriff Election",
        "zh": "警长竞选",
    },
    "death_announcement": {
        "en": "was found dead",
        "zh": "被发现死亡",
    },
    "lynch_announcement": {
        "en": "was lynched",
        "zh": "被处决",
    },
    "hunter_shot_announcement": {
        "en": "shot",
        "zh": "射杀了",
    },
    "sheriff_elected": {
        "en": "became sheriff",
        "zh": "成为警长",
    },
    "badge_passed": {
        "en": "Badge passed to",
        "zh": "警徽传递给",
    },
    "badge_torn": {
        "en": "Badge was torn",
        "zh": "警徽被撕毁",
    },
    "voted_for": {
        "en": "voted for",
        "zh": "投票给",
    },
    "good": {
        "en": "Good",
        "zh": "好人",
    },
    "evil": {
        "en": "Werewolf",
        "zh": "狼人",
    },
    "check_result_good": {
        "en": "is Good",
        "zh": "是好人",
    },
    "check_result_evil": {
        "en": "is Werewolf",
        "zh": "是狼人",
    },
    "wolf_teammate": {
        "en": "Werewolf Teammate",
        "zh": "狼队友",
    },
    "has_cure": {
        "en": "Has Cure",
        "zh": "有解药",
    },
    "has_poison": {
        "en": "Has Poison",
        "zh": "有毒药",
    },
    "attack_target": {
        "en": "Attack Target",
        "zh": "被袭击的目标",
    },
    "can_shoot": {
        "en": "Can Shoot",
        "zh": "可以开枪",
    },
    "last_protected": {
        "en": "Last Protected",
        "zh": "上次守护的人",
    },
    "yes": {
        "en": "Yes",
        "zh": "是",
    },
    "no": {
        "en": "No",
        "zh": "否",
    },
    "created": {
        "en": "Created",
        "zh": "已创建",
    },
    "running": {
        "en": "Running",
        "zh": "进行中",
    },
    "completed": {
        "en": "Completed",
        "zh": "已完成",
    },
    "stopped": {
        "en": "Stopped",
        "zh": "已停止",
    },
    "events_appear": {
        "en": "Events will appear here",
        "zh": "事件将在此显示",
    },
    "all": {
        "en": "All",
        "zh": "全部",
    },
    "narration": {
        "en": "Narration",
        "zh": "旁白",
    },
    "click_to_start": {
        "en": "Click 'Start Game' to begin",
        "zh": "点击「开始游戏」开始",
    },
    "night_phase": {
        "en": "Night",
        "zh": "夜晚",
    },
    "day_phase": {
        "en": "Day",
        "zh": "白天",
    },
    "event_death": {
        "en": "💀 {name} was found dead",
        "zh": "💀 {name} 被发现死亡",
    },
    "event_lynch": {
        "en": "⚖️ {name} was lynched",
        "zh": "⚖️ {name} 被处决",
    },
    "event_speech": {
        "en": "🗣️ {name}: {content}",
        "zh": "🗣️ {name}：{content}",
    },
    "event_last_words": {
        "en": "🗣️ [Last Words] {name}: {content}",
        "zh": "🗣️ [遗言] {name}：{content}",
    },
    "event_vote": {
        "en": "🗳️ {voter} voted for {target}",
        "zh": "🗳️ {voter} 投票给 {target}",
    },
    "event_sheriff": {
        "en": "👑 {name} became sheriff",
        "zh": "👑 {name} 成为警长",
    },
    "event_hunter_shot": {
        "en": "🔫 {hunter} shot {target}",
        "zh": "🔫 {hunter} 射杀了 {target}",
    },
    "event_badge_pass": {
        "en": "👑 Badge passed to {name}",
        "zh": "👑 警徽传递给 {name}",
    },
    "event_badge_tear": {
        "en": "💔 Badge was torn",
        "zh": "💔 警徽被撕毁",
    },
    "event_idiot_reveal": {
        "en": "🃏 {name} revealed as Village Idiot",
        "zh": "🃏 {name} 显示为白痴身份",
    },
    "event_wolf_explode": {
        "en": "💥 {name} self-exploded",
        "zh": "💥 {name} 自爆了",
    },
    "event_peaceful_night": {
        "en": "☀️ Peaceful night",
        "zh": "☀️ 平安夜",
    },
    "werewolf_discussion": {
        "en": "🐺 Werewolves are discussing...",
        "zh": "🐺 狼人正在讨论...",
    },
    "seer_checking": {
        "en": "🔮 Seer is checking...",
        "zh": "🔮 预言家正在查验...",
    },
    "witch_deciding": {
        "en": "🧙 Witch is deciding...",
        "zh": "🧙 女巫正在决定...",
    },
    "guard_protecting": {
        "en": "🛡️ Guard is protecting...",
        "zh": "🛡️ 守卫正在守护...",
    },
    "loading": {
        "en": "Loading...",
        "zh": "加载中...",
    },
    "game_starting": {
        "en": "Game starting...",
        "zh": "游戏开始中...",
    },
    "all_players": {
        "en": "All Players",
        "zh": "所有玩家",
    },
    "alive_players": {
        "en": "Alive Players",
        "zh": "存活玩家",
    },
    "dead_players": {
        "en": "Dead Players",
        "zh": "死亡玩家",
    },
    "show_role": {
        "en": "Show Role",
        "zh": "显示身份",
    },
    "hide_role": {
        "en": "Hide Role",
        "zh": "隐藏身份",
    },
    "game_summary": {
        "en": "Game Summary",
        "zh": "游戏总结",
    },
    "total_days": {
        "en": "Total Days",
        "zh": "总天数",
    },
    "winner": {
        "en": "Winner",
        "zh": "获胜方",
    },
    "survivors": {
        "en": "Survivors",
        "zh": "存活者",
    },
    "refresh": {
        "en": "Refresh",
        "zh": "刷新",
    },
    "auto_scroll": {
        "en": "Auto Scroll",
        "zh": "自动滚动",
    },
    "clear_log": {
        "en": "Clear Log",
        "zh": "清空日志",
    },
    "good_team_victory": {
        "en": "The village has successfully eliminated all werewolves!",
        "zh": "村民成功消灭了所有狼人！",
    },
    "evil_team_victory": {
        "en": "The werewolves have taken over the village!",
        "zh": "狼人占领了村庄！",
    },
    "output_corrector": {
        "en": "Output Corrector",
        "zh": "输出校正器",
    },
    "enable_corrector": {
        "en": "Enable Corrector",
        "zh": "启用校正器",
    },
    "corrector_retries": {
        "en": "Max Retries",
        "zh": "最大重试次数",
    },
    "corrector_desc": {
        "en": "Automatically fix malformed model outputs",
        "zh": "自动修复格式错误的模型输出",
    },
    "advanced_settings": {
        "en": "Advanced Settings",
        "zh": "高级设置",
    },
    "use_separate_model": {
        "en": "Use Separate Model",
        "zh": "使用独立模型",
    },
    "corrector_backend": {
        "en": "Corrector Backend",
        "zh": "校正器后端",
    },
    "corrector_model": {
        "en": "Corrector Model",
        "zh": "校正器模型",
    },
    "corrector_ollama_url": {
        "en": "Corrector Ollama URL",
        "zh": "校正器 Ollama 地址",
    },
    "corrector_api_base": {
        "en": "Corrector API Base",
        "zh": "校正器 API 地址",
    },
    "corrector_api_key": {
        "en": "Corrector API Key",
        "zh": "校正器 API 密钥",
    },
}


class I18n:
    def __init__(self, language: Language = Language.EN):
        self.language = language

    def get(self, key: str, default: Optional[str] = None) -> str:
        trans = TRANSLATIONS.get(key)
        if trans is None:
            return default or key
        return trans.get(self.language.value, trans.get("en", default or key))

    def set_language(self, language: Language) -> None:
        self.language = language

    def get_all_translations(self) -> Dict[str, str]:
        result = {}
        for key in TRANSLATIONS:
            result[key] = self.get(key)
        return result


i18n = I18n()


def get_translation(key: str, language: str = "en") -> str:
    trans = TRANSLATIONS.get(key)
    if trans is None:
        return key
    return trans.get(language, trans.get("en", key))


def get_all_translations(language: str = "en") -> Dict[str, str]:
    result = {}
    for key in TRANSLATIONS:
        trans = TRANSLATIONS.get(key)
        if trans:
            result[key] = trans.get(language, trans.get("en", key))
        else:
            result[key] = key
    return result
