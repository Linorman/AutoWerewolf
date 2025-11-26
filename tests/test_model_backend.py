import json
import tempfile
from pathlib import Path

import pytest

from autowerewolf.config.models import (
    AgentModelConfig,
    ModelBackend,
    ModelConfig,
)
from autowerewolf.config.performance import (
    MODEL_PROFILES,
    get_model_profile,
)
from autowerewolf.io.persistence import (
    load_model_config,
    load_agent_model_config,
    save_model_config,
    save_agent_model_config,
)


class TestModelConfig:
    def test_default_config(self):
        config = ModelConfig()
        assert config.backend == ModelBackend.OLLAMA
        assert config.model_name == "llama3"
        assert config.temperature == 0.7
        assert config.max_tokens == 1024
        assert config.timeout_s == 60

    def test_ollama_config_no_api_key_required(self):
        config = ModelConfig(backend=ModelBackend.OLLAMA, model_name="mistral")
        assert config.api_key is None

    def test_api_config_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key is required"):
            ModelConfig(backend=ModelBackend.API, model_name="gpt-4")

    def test_api_config_with_api_key(self):
        config = ModelConfig(
            backend=ModelBackend.API,
            model_name="gpt-4",
            api_key="sk-test-key",
            api_base="https://api.openai.com/v1",
        )
        assert config.api_key == "sk-test-key"
        assert config.api_base == "https://api.openai.com/v1"

    def test_temperature_bounds(self):
        config = ModelConfig(temperature=0.0)
        assert config.temperature == 0.0

        config = ModelConfig(temperature=2.0)
        assert config.temperature == 2.0

        with pytest.raises(ValueError):
            ModelConfig(temperature=-0.1)

        with pytest.raises(ValueError):
            ModelConfig(temperature=2.1)


class TestAgentModelConfig:
    def test_default_agent_config(self):
        config = AgentModelConfig()
        assert config.default is not None
        assert config.moderator is None
        assert config.werewolf is None

    def test_get_config_for_role_default(self):
        config = AgentModelConfig()
        result = config.get_config_for_role("villager")
        assert result == config.default

    def test_get_config_for_role_override(self):
        werewolf_config = ModelConfig(
            backend=ModelBackend.OLLAMA,
            model_name="qwen2",
            temperature=0.5,
        )
        config = AgentModelConfig(werewolf=werewolf_config)
        
        result = config.get_config_for_role("werewolf")
        assert result == werewolf_config
        assert result.model_name == "qwen2"

        result = config.get_config_for_role("villager")
        assert result == config.default

    def test_get_config_for_role_case_insensitive(self):
        config = AgentModelConfig()
        result = config.get_config_for_role("WEREWOLF")
        assert result == config.default


class TestModelProfiles:
    def test_fast_local_profile(self):
        fast_local = get_model_profile("fast_local")
        assert fast_local.default.backend == ModelBackend.OLLAMA
        assert fast_local.default.temperature == 0.3
        assert fast_local.default.max_tokens == 256

    def test_model_profiles_available(self):
        assert "fast_local" in MODEL_PROFILES
        assert "balanced_local" in MODEL_PROFILES
        assert "quality_local" in MODEL_PROFILES

    def test_get_model_profile_invalid(self):
        with pytest.raises(ValueError):
            get_model_profile("nonexistent_profile")


class TestPersistence:
    def test_save_and_load_model_config_json(self):
        config = ModelConfig(
            backend=ModelBackend.OLLAMA,
            model_name="llama3",
            temperature=0.5,
        )
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        
        try:
            save_model_config(config, path)
            loaded = load_model_config(path)
            
            assert loaded.backend == config.backend
            assert loaded.model_name == config.model_name
            assert loaded.temperature == config.temperature
        finally:
            path.unlink(missing_ok=True)

    def test_save_and_load_agent_model_config_json(self):
        config = AgentModelConfig(
            default=ModelConfig(model_name="llama3"),
            werewolf=ModelConfig(model_name="mistral"),
        )
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        
        try:
            save_agent_model_config(config, path)
            loaded = load_agent_model_config(path)
            
            assert loaded.default.model_name == "llama3"
            assert loaded.werewolf is not None
            assert loaded.werewolf.model_name == "mistral"
        finally:
            path.unlink(missing_ok=True)

    def test_load_config_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"{}")
            path = Path(f.name)
        
        try:
            with pytest.raises(ValueError, match="Unsupported config file format"):
                load_model_config(path)
        finally:
            path.unlink(missing_ok=True)


class TestBackendAdapter:
    def test_get_chat_model_ollama(self):
        pytest.importorskip("langchain_ollama")
        
        from autowerewolf.agents.backend import get_chat_model
        
        config = ModelConfig(
            backend=ModelBackend.OLLAMA,
            model_name="llama3",
            temperature=0.5,
        )
        
        model = get_chat_model(config)
        assert model is not None

    def test_get_chat_model_api(self):
        openai_module = pytest.importorskip("langchain_openai", reason="langchain-openai not installed")
        
        from autowerewolf.agents.backend import get_chat_model
        
        config = ModelConfig(
            backend=ModelBackend.API,
            model_name="gpt-4",
            api_key="sk-test-key",
            api_base="https://api.openai.com/v1",
        )
        
        model = get_chat_model(config)
        assert model is not None
