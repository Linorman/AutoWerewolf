from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


def _extract_from_nested(data: dict, field_name: str, aliases: list[str]) -> dict:
    """Extract field value from nested structures like {'action': {'target': 'xxx'}}."""
    if field_name in data:
        return data
    
    for nested_key in ["action", "result", "output", "response", "decision"]:
        if nested_key in data and isinstance(data[nested_key], dict):
            nested = data[nested_key]
            for alias in aliases:
                if alias in nested:
                    data[field_name] = nested[alias]
                    return data
    
    for alias in aliases:
        if alias in data:
            data[field_name] = data.pop(alias)
            return data
    
    return data


class SpeechOutput(BaseModel):
    content: str = Field(description="The speech content to deliver")

    @model_validator(mode="before")
    @classmethod
    def accept_speech_alias(cls, data):
        if isinstance(data, dict) and "speech" in data and "content" not in data:
            data["content"] = data.pop("speech")
        return data


class LastWordsOutput(BaseModel):
    content: str = Field(description="The last words to deliver before dying")
    reveal_role: bool = Field(default=False, description="Whether to reveal your role in last words")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            if "last_words" in data and "content" not in data:
                data["content"] = data.pop("last_words")
            if "speech" in data and "content" not in data:
                data["content"] = data.pop("speech")
        return data


class VoteOutput(BaseModel):
    target_player_id: str = Field(description="The player ID to vote for")
    reasoning: Optional[str] = Field(default=None, description="Brief reasoning for the vote")

    @field_validator("target_player_id", mode="before")
    @classmethod
    def validate_target_not_none(cls, v):
        if v is None:
            raise ValueError("target_player_id cannot be None, you must vote for a player")
        return v

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            # Accept various aliases for target_player_id
            for alias in ["target", "vote_target", "player_id", "target_id", "vote"]:
                if alias in data and "target_player_id" not in data:
                    data["target_player_id"] = data.pop(alias)
                    break
            # Accept alias for reasoning
            if "reason" in data and "reasoning" not in data:
                data["reasoning"] = data.pop("reason")
        return data


class SheriffDecisionOutput(BaseModel):
    run_for_sheriff: bool = Field(description="Whether to run for sheriff")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            for alias in ["run", "participate", "candidate", "running", "decision"]:
                if alias in data and "run_for_sheriff" not in data:
                    data["run_for_sheriff"] = data.pop(alias)
                    break
            if "run_for_sheriff" in data and isinstance(data["run_for_sheriff"], str):
                value = data["run_for_sheriff"].lower().strip()
                negative_indicators = [
                    "not", "no", "false", "decline", "refuse", "don't", "won't",
                    "skip", "pass", "abstain", "negative"
                ]
                data["run_for_sheriff"] = not any(neg in value for neg in negative_indicators)
        return data


class BadgeDecisionOutput(BaseModel):
    action: Literal["pass", "tear"] = Field(description="Whether to pass or tear the badge")
    target_player_id: Optional[str] = Field(
        default=None,
        description="Player ID to pass the badge to (required if action is 'pass')"
    )

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            for alias in ["decision", "badge_action"]:
                if alias in data and "action" not in data:
                    data["action"] = data.pop(alias)
                    break
            for alias in ["target", "pass_to", "target_id"]:
                if alias in data and "target_player_id" not in data:
                    data["target_player_id"] = data.pop(alias)
                    break
        return data


class WerewolfNightOutput(BaseModel):
    kill_target_id: str = Field(description="The player ID to kill")
    self_explode: bool = Field(default=False, description="Whether to self-explode instead")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            data = _extract_from_nested(
                data, "kill_target_id",
                ["target", "kill_target", "target_id", "target_player_id", "kill", "kill_target_id"]
            )
            for alias in ["explode", "self_destruct"]:
                if alias in data and "self_explode" not in data:
                    data["self_explode"] = data.pop(alias)
                    break
        return data


class SeerNightOutput(BaseModel):
    check_target_id: str = Field(description="The player ID to check")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            data = _extract_from_nested(
                data, "check_target_id",
                ["target", "check_target", "target_id", "target_player_id", "check", "check_target_id"]
            )
        return data


class WitchNightOutput(BaseModel):
    use_cure: bool = Field(default=False, description="Whether to use the cure potion")
    use_poison: bool = Field(default=False, description="Whether to use the poison potion")
    poison_target_id: Optional[str] = Field(
        default=None,
        description="Player ID to poison (required if use_poison is True)"
    )

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            for alias in ["cure", "save", "use_save"]:
                if alias in data and "use_cure" not in data:
                    data["use_cure"] = data.pop(alias)
                    break
            for alias in ["poison", "kill"]:
                if alias in data and "use_poison" not in data:
                    data["use_poison"] = data.pop(alias)
                    break
            for alias in ["poison_target", "target", "target_id", "target_player_id"]:
                if alias in data and "poison_target_id" not in data:
                    data["poison_target_id"] = data.pop(alias)
                    break
        return data


class GuardNightOutput(BaseModel):
    protect_target_id: str = Field(description="The player ID to protect")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            data = _extract_from_nested(
                data, "protect_target_id",
                ["target", "protect_target", "target_id", "target_player_id", "protect", "protect_target_id"]
            )
        return data


class HunterShootOutput(BaseModel):
    shoot: bool = Field(description="Whether to use the shoot ability")
    target_player_id: Optional[str] = Field(
        default=None,
        description="Player ID to shoot (required if shoot is True)"
    )

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            for alias in ["use_shoot", "fire", "shooting"]:
                if alias in data and "shoot" not in data:
                    data["shoot"] = data.pop(alias)
                    break
            for alias in ["target", "shoot_target", "target_id"]:
                if alias in data and "target_player_id" not in data:
                    data["target_player_id"] = data.pop(alias)
                    break
        return data


class SheriffSpeechOutput(BaseModel):
    content: str = Field(description="The sheriff campaign speech content")
    claimed_role: Optional[str] = Field(default=None, description="Role claimed during campaign")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            if "speech" in data and "content" not in data:
                data["content"] = data.pop("speech")
            for alias in ["role", "claim"]:
                if alias in data and "claimed_role" not in data:
                    data["claimed_role"] = data.pop(alias)
                    break
        return data


class SheriffVoteOutput(BaseModel):
    target_player_id: str = Field(description="The candidate ID to vote for sheriff")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            for alias in ["target", "vote_target", "candidate", "target_id", "vote"]:
                if alias in data and "target_player_id" not in data:
                    data["target_player_id"] = data.pop(alias)
                    break
        return data


class WerewolfProposalOutput(BaseModel):
    target_player_id: str = Field(description="Proposed kill target")
    reasoning: str = Field(default="", description="Reasoning for the proposal")

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        if isinstance(data, dict):
            data = _extract_from_nested(
                data, "target_player_id",
                ["target", "proposal_target", "target_id", "kill_target", "target_player_id"]
            )
            # Accept aliases for reasoning, including 'thought' which models often use
            for alias in ["reason", "thought", "explanation", "rationale"]:
                if alias in data and "reasoning" not in data:
                    data["reasoning"] = data.pop(alias)
                    break
        return data


NightActionOutput = Union[
    WerewolfNightOutput,
    SeerNightOutput,
    WitchNightOutput,
    GuardNightOutput,
    HunterShootOutput,
]
