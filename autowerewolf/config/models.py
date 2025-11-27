from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ModelBackend(str, Enum):
    API = "api"
    OLLAMA = "ollama"


class ModelConfig(BaseModel):
    backend: ModelBackend = Field(
        default=ModelBackend.OLLAMA,
        description="Model backend type (api or ollama)"
    )
    model_name: str = Field(
        default="llama3",
        description="Model name to use"
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Base URL for API backend (OpenAI-compatible)"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for API backend"
    )
    ollama_base_url: Optional[str] = Field(
        default=None,
        description="Base URL for Ollama endpoint (default: http://localhost:11434)"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )
    max_tokens: int = Field(
        default=1024,
        gt=0,
        description="Maximum tokens in response"
    )
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus) sampling"
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=0,
        description="Top-k sampling"
    )
    repeat_penalty: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Repeat penalty for Ollama"
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility"
    )
    stop_sequences: Optional[list[str]] = Field(
        default=None,
        description="Stop sequences for generation"
    )
    timeout_s: int = Field(
        default=60,
        gt=0,
        description="Request timeout in seconds"
    )
    batch_size: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Batch size for parallel requests"
    )
    rate_limit_rpm: Optional[int] = Field(
        default=None,
        description="Rate limit in requests per minute"
    )
    extra_params: Optional[dict] = Field(
        default=None,
        description="Extra parameters to pass to the model"
    )

    @model_validator(mode="after")
    def validate_api_config(self) -> "ModelConfig":
        if self.backend == ModelBackend.API and not self.api_key:
            raise ValueError("api_key is required when backend is 'api'")
        return self


class OutputCorrectorConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether to enable output correction"
    )
    model_config_override: Optional[ModelConfig] = Field(
        default=None,
        description="Model configuration for the corrector. If None, uses the same model as the agent."
    )
    max_retries: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum number of correction attempts"
    )
    fallback_on_failure: bool = Field(
        default=True,
        description="Whether to use fallback values if correction fails"
    )


class AgentModelConfig(BaseModel):
    default: ModelConfig = Field(
        default_factory=ModelConfig,
        description="Default model configuration for all agents"
    )
    moderator: Optional[ModelConfig] = Field(
        default=None,
        description="Override for moderator agent"
    )
    werewolf: Optional[ModelConfig] = Field(
        default=None,
        description="Override for werewolf agents"
    )
    villager: Optional[ModelConfig] = Field(
        default=None,
        description="Override for villager agents"
    )
    seer: Optional[ModelConfig] = Field(
        default=None,
        description="Override for seer agent"
    )
    witch: Optional[ModelConfig] = Field(
        default=None,
        description="Override for witch agent"
    )
    hunter: Optional[ModelConfig] = Field(
        default=None,
        description="Override for hunter agent"
    )
    guard: Optional[ModelConfig] = Field(
        default=None,
        description="Override for guard agent"
    )
    village_idiot: Optional[ModelConfig] = Field(
        default=None,
        description="Override for village idiot agent"
    )
    output_corrector: OutputCorrectorConfig = Field(
        default_factory=OutputCorrectorConfig,
        description="Configuration for output correction model"
    )

    def get_config_for_role(self, role: str) -> ModelConfig:
        role_config = getattr(self, role.lower(), None)
        if role_config is not None:
            return role_config
        return self.default
    
    def get_corrector_model_config(self) -> Optional[ModelConfig]:
        """Get the model config for output corrector."""
        if not self.output_corrector.enabled:
            return None
        return self.output_corrector.model_config_override or self.default
