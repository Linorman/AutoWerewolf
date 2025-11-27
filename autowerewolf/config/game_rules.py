"""Game rules configuration system with YAML file support.

This module provides a configuration system for game rules that:
1. Uses default values if no configuration file is provided
2. Loads from a YAML configuration file if specified
3. Supports environment variable overrides

Configuration priority (highest to lowest):
1. Environment variables (prefixed with AUTOWEREWOLF_)
2. Configuration file (YAML)
3. Default values
"""

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import Field

from autowerewolf.engine.roles import RoleSet, WinMode
from autowerewolf.engine.state import GameConfig, RuleVariants


DEFAULT_CONFIG_FILENAME = "autowerewolf_config.yaml"
DEFAULT_CONFIG_PATHS = [
    Path.cwd() / DEFAULT_CONFIG_FILENAME,
    Path.home() / ".config" / "autowerewolf" / DEFAULT_CONFIG_FILENAME,
]


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load YAML file if available, otherwise return empty dict."""
    if not path.exists():
        return {}
    
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except ImportError:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    except Exception:
        return {}


def _find_config_file(config_path: Optional[Path] = None) -> Optional[Path]:
    """Find the configuration file.
    
    Args:
        config_path: Explicit path to configuration file
        
    Returns:
        Path to configuration file if found, None otherwise
    """
    if config_path:
        if config_path.exists():
            return config_path
        return None
    
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    
    return None


def load_rule_variants(config_path: Optional[Path] = None) -> RuleVariants:
    """Load rule variants from configuration file or use defaults.
    
    Args:
        config_path: Optional explicit path to configuration file
        
    Returns:
        RuleVariants instance with loaded or default values
    """
    found_path = _find_config_file(config_path)
    
    if not found_path:
        return RuleVariants()
    
    config_data = _load_yaml_file(found_path)
    rule_data = config_data.get("rule_variants", {})
    
    if not rule_data:
        return RuleVariants()
    
    if "win_mode" in rule_data and isinstance(rule_data["win_mode"], str):
        rule_data["win_mode"] = WinMode(rule_data["win_mode"])
    
    return RuleVariants(**rule_data)


def load_game_config(config_path: Optional[Path] = None) -> GameConfig:
    """Load game configuration from file or use defaults.
    
    Args:
        config_path: Optional explicit path to configuration file
        
    Returns:
        GameConfig instance with loaded or default values
    """
    found_path = _find_config_file(config_path)
    
    if not found_path:
        return GameConfig()
    
    config_data = _load_yaml_file(found_path)
    
    game_data: dict[str, Any] = {}
    
    if "num_players" in config_data:
        game_data["num_players"] = config_data["num_players"]
    
    if "role_set" in config_data:
        role_set_value = config_data["role_set"]
        if isinstance(role_set_value, str):
            game_data["role_set"] = RoleSet(role_set_value.upper())
        else:
            game_data["role_set"] = role_set_value
    
    if "random_seed" in config_data:
        game_data["random_seed"] = config_data["random_seed"]
    
    game_data["rule_variants"] = load_rule_variants(found_path)
    
    return GameConfig(**game_data)


def save_default_config(path: Path) -> None:
    """Save default configuration to a YAML file.
    
    Args:
        path: Path to save the configuration file
    """
    default_config = GameConfig()
    
    config_dict = {
        "num_players": default_config.num_players,
        "role_set": default_config.role_set.value,
        "random_seed": default_config.random_seed,
        "rule_variants": {
            "witch_can_self_heal_n1": default_config.rule_variants.witch_can_self_heal_n1,
            "witch_can_self_heal": default_config.rule_variants.witch_can_self_heal,
            "witch_can_use_both_potions": default_config.rule_variants.witch_can_use_both_potions,
            "guard_can_self_guard": default_config.rule_variants.guard_can_self_guard,
            "same_guard_same_save_kills": default_config.rule_variants.same_guard_same_save_kills,
            "win_mode": default_config.rule_variants.win_mode.value,
            "allow_wolf_self_explode": default_config.rule_variants.allow_wolf_self_explode,
            "allow_wolf_self_knife": default_config.rule_variants.allow_wolf_self_knife,
            "sheriff_vote_weight": default_config.rule_variants.sheriff_vote_weight,
            "hunter_can_shoot_if_poisoned": default_config.rule_variants.hunter_can_shoot_if_poisoned,
            "hunter_can_shoot_if_night_killed": default_config.rule_variants.hunter_can_shoot_if_night_killed,
            "first_night_death_has_last_words": default_config.rule_variants.first_night_death_has_last_words,
        },
    }
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except ImportError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)


def get_config_template() -> str:
    """Get a YAML configuration template with comments.
    
    Returns:
        YAML template string with documentation comments
    """
    return """# AutoWerewolf Game Configuration
# ================================
# This file configures the game rules and variants.
# All values shown are defaults - only specify values you want to change.

# Number of players (currently only 12 is supported)
num_players: 12

# Role set to use: "A" or "B"
# Set A: Seer, Witch, Hunter, Guard (balanced)
# Set B: Seer, Witch, Hunter, Village Idiot (more chaotic)
role_set: "A"

# Random seed for reproducible games (null for random)
random_seed: null

# Rule variants - customize game mechanics
rule_variants:
  # ===================
  # Witch Rules
  # ===================
  
  # Whether the Witch can use cure potion on herself on Night 1
  witch_can_self_heal_n1: true
  
  # Whether the Witch can use cure potion on herself after Night 1
  witch_can_self_heal: false
  
  # Whether the Witch can use both potions (cure and poison) in the same night
  witch_can_use_both_potions: false

  # ===================
  # Guard Rules
  # ===================
  
  # Whether the Guard can protect themselves
  guard_can_self_guard: true
  
  # If Guard protects AND Witch saves the same target, target dies
  # (double protection paradox)
  same_guard_same_save_kills: true

  # ===================
  # Win Condition
  # ===================
  
  # Win mode determines how werewolves win:
  # - "side_elimination": Werewolves win if ALL villagers OR ALL special roles are eliminated
  # - "city_elimination": Werewolves win if ALL good players are eliminated
  win_mode: "side_elimination"

  # ===================
  # Werewolf Rules
  # ===================
  
  # Allow werewolves to self-explode during the day (reveal identity and die)
  allow_wolf_self_explode: true
  
  # Allow werewolves to kill their own teammates at night
  allow_wolf_self_knife: true

  # ===================
  # Sheriff Rules
  # ===================
  
  # Vote weight multiplier for the sheriff (1.5 = sheriff's vote counts 1.5 times)
  sheriff_vote_weight: 1.5

  # ===================
  # Hunter Rules
  # ===================
  
  # Whether the Hunter can shoot if killed by Witch's poison
  # false = Hunter dies silently when poisoned (cannot use skill)
  # true = Hunter can still shoot even when poisoned
  hunter_can_shoot_if_poisoned: false
  
  # Whether the Hunter can shoot if killed by werewolves at night
  # true = Hunter can shoot upon death announcement
  hunter_can_shoot_if_night_killed: true

  # ===================
  # Last Words Rules
  # ===================
  
  # Whether players killed on the first night get to speak last words
  first_night_death_has_last_words: true
"""
