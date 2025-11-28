from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig


class VerbosityLevel(str, Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


class LanguageSetting(str, Enum):
    """Language setting for prompts and game content."""
    EN = "en"
    ZH = "zh"


class PerformanceConfig(BaseModel):
    verbosity: VerbosityLevel = Field(
        default=VerbosityLevel.STANDARD,
        description="Prompt and output verbosity level"
    )
    language: LanguageSetting = Field(
        default=LanguageSetting.EN,
        description="Language for prompts and game content (en=English, zh=Chinese)"
    )
    enable_batching: bool = Field(
        default=False,
        description="Enable batching of parallel agent calls"
    )
    batch_size: int = Field(
        default=4,
        ge=1,
        le=12,
        description="Maximum batch size for parallel requests"
    )
    skip_narration: bool = Field(
        default=False,
        description="Skip natural language narration for faster simulation"
    )
    compact_logs: bool = Field(
        default=False,
        description="Use compact log format"
    )
    max_speech_length: int = Field(
        default=2000,
        ge=50,
        le=5000,
        description="Maximum speech length in characters"
    )
    max_reasoning_length: int = Field(
        default=200,
        ge=0,
        le=2000,
        description="Maximum reasoning length in characters"
    )
    memory_type: Literal["buffer", "summary"] = Field(
        default="buffer",
        description="Memory type: buffer keeps recent history, summary compresses with LLM"
    )
    max_memory_facts: int = Field(
        default=100,
        ge=20,
        le=500,
        description="Maximum number of facts to keep before compression"
    )


FAST_LOCAL_MODEL = ModelConfig(
    backend=ModelBackend.OLLAMA,
    model_name="llama3.2:3b",
    temperature=0.3,
    max_tokens=256,
    timeout_s=30,
)

FAST_LOCAL_PROFILE = AgentModelConfig(
    default=FAST_LOCAL_MODEL,
)

BALANCED_LOCAL_MODEL = ModelConfig(
    backend=ModelBackend.OLLAMA,
    model_name="llama3.1:8b",
    temperature=0.5,
    max_tokens=512,
    timeout_s=60,
)

BALANCED_LOCAL_PROFILE = AgentModelConfig(
    default=BALANCED_LOCAL_MODEL,
)

QUALITY_LOCAL_MODEL = ModelConfig(
    backend=ModelBackend.OLLAMA,
    model_name="llama3.1:70b",
    temperature=0.7,
    max_tokens=1024,
    timeout_s=180,
)

QUALITY_LOCAL_PROFILE = AgentModelConfig(
    default=QUALITY_LOCAL_MODEL,
)


def create_cloud_profile(
    api_key: str,
    api_base: Optional[str] = None,
    model_name: str = "gpt-4o-mini",
) -> AgentModelConfig:
    return AgentModelConfig(
        default=ModelConfig(
            backend=ModelBackend.API,
            model_name=model_name,
            api_base=api_base or "https://api.openai.com/v1",
            api_key=api_key,
            temperature=0.7,
            max_tokens=1024,
            timeout_s=60,
        )
    )


def create_cloud_strong_profile(
    api_key: str,
    api_base: Optional[str] = None,
    model_name: str = "gpt-4o",
) -> AgentModelConfig:
    return AgentModelConfig(
        default=ModelConfig(
            backend=ModelBackend.API,
            model_name=model_name,
            api_base=api_base or "https://api.openai.com/v1",
            api_key=api_key,
            temperature=0.7,
            max_tokens=2048,
            timeout_s=120,
        )
    )


MODEL_PROFILES = {
    "fast_local": FAST_LOCAL_PROFILE,
    "balanced_local": BALANCED_LOCAL_PROFILE,
    "quality_local": QUALITY_LOCAL_PROFILE,
}


PERFORMANCE_PRESETS = {
    "simulation": PerformanceConfig(
        verbosity=VerbosityLevel.MINIMAL,
        enable_batching=True,
        batch_size=6,
        skip_narration=True,
        compact_logs=True,
        max_speech_length=1000,
        max_reasoning_length=200,
    ),
    "standard": PerformanceConfig(
        verbosity=VerbosityLevel.STANDARD,
        enable_batching=False,
        batch_size=4,
        skip_narration=False,
        compact_logs=False,
        max_speech_length=2000,
        max_reasoning_length=500,
    ),
    "verbose": PerformanceConfig(
        verbosity=VerbosityLevel.FULL,
        enable_batching=False,
        batch_size=4,
        skip_narration=False,
        compact_logs=False,
        max_speech_length=5000,
        max_reasoning_length=1000,
    ),
}


def get_model_profile(profile_name: str) -> AgentModelConfig:
    if profile_name not in MODEL_PROFILES:
        raise ValueError(
            f"Unknown model profile: {profile_name}. "
            f"Available profiles: {list(MODEL_PROFILES.keys())}"
        )
    return MODEL_PROFILES[profile_name]


def get_performance_preset(preset_name: str) -> PerformanceConfig:
    if preset_name not in PERFORMANCE_PRESETS:
        raise ValueError(
            f"Unknown performance preset: {preset_name}. "
            f"Available presets: {list(PERFORMANCE_PRESETS.keys())}"
        )
    return PERFORMANCE_PRESETS[preset_name]
