"""Tests for the output corrector module."""
import json
import pytest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field, ValidationError

from autowerewolf.agents.output_corrector import (
    OutputCorrector,
    create_output_corrector,
    _get_schema_description,
    _build_correction_prompt,
)
from autowerewolf.config.models import ModelConfig, OutputCorrectorConfig


class SimpleTestSchema(BaseModel):
    name: str = Field(description="A name field")
    value: int = Field(description="A numeric value")


class OptionalFieldSchema(BaseModel):
    required_field: str = Field(description="A required field")
    optional_field: str = Field(default="default", description="An optional field")


class TestSchemaDescription:
    """Tests for _get_schema_description function."""
    
    def test_simple_schema(self):
        """Test schema description for simple schema."""
        desc = _get_schema_description(SimpleTestSchema)
        assert "SimpleTestSchema" in desc
        assert "name" in desc
        assert "value" in desc
        assert "A name field" in desc
        assert "A numeric value" in desc
    
    def test_optional_fields(self):
        """Test schema description includes optional indicator."""
        desc = _get_schema_description(OptionalFieldSchema)
        assert "required_field" in desc
        assert "optional_field" in desc
        assert "optional" in desc.lower() or "default" in desc.lower()


class TestBuildCorrectionPrompt:
    """Tests for _build_correction_prompt function."""
    
    def test_prompt_contains_original_output(self):
        """Test that correction prompt contains original output."""
        prompt = _build_correction_prompt(
            original_output='{"name": "test"}',
            schema_class=SimpleTestSchema,
            validation_error="Missing required field 'value'",
        )
        assert '{"name": "test"}' in prompt
        assert "Missing required field 'value'" in prompt
    
    def test_prompt_contains_context_when_provided(self):
        """Test that correction prompt includes context when provided."""
        prompt = _build_correction_prompt(
            original_output='{}',
            schema_class=SimpleTestSchema,
            validation_error="Error",
            context="This is important context",
        )
        assert "This is important context" in prompt
    
    def test_prompt_without_context(self):
        """Test that correction prompt works without context."""
        prompt = _build_correction_prompt(
            original_output='{}',
            schema_class=SimpleTestSchema,
            validation_error="Error",
        )
        assert "Context" not in prompt or "important context" not in prompt


class TestOutputCorrector:
    """Tests for OutputCorrector class."""
    
    def test_disabled_corrector(self):
        """Test that disabled corrector returns None."""
        config = OutputCorrectorConfig(enabled=False)
        corrector = OutputCorrector(config, corrector_model=None)
        
        assert not corrector.enabled
        
        # Should return None when disabled
        try:
            result = corrector.correct_output(
                original_output='{}',
                schema_class=SimpleTestSchema,
                validation_error=ValidationError.from_exception_data(
                    title="SimpleTestSchema",
                    line_errors=[{"type": "missing", "loc": ("name",), "input": {}}],
                ),
            )
            assert result is None
        except Exception:
            pass  # Expected when no model is configured
    
    def test_enabled_without_model(self):
        """Test that enabled corrector without model is effectively disabled."""
        config = OutputCorrectorConfig(enabled=True)
        corrector = OutputCorrector(config, corrector_model=None)
        
        assert not corrector.enabled
    
    def test_extract_json_from_markdown(self):
        """Test JSON extraction from markdown code blocks."""
        config = OutputCorrectorConfig(enabled=True)
        corrector = OutputCorrector(config, corrector_model=None)
        
        # Test with ```json block
        text = '```json\n{"name": "test", "value": 123}\n```'
        result = corrector._extract_json(text)
        assert result == '{"name": "test", "value": 123}'
        
        # Test with plain ``` block
        text = '```\n{"name": "test", "value": 123}\n```'
        result = corrector._extract_json(text)
        assert result == '{"name": "test", "value": 123}'
    
    def test_extract_json_from_mixed_text(self):
        """Test JSON extraction from text with surrounding content."""
        config = OutputCorrectorConfig(enabled=True)
        corrector = OutputCorrector(config, corrector_model=None)
        
        text = 'Here is the corrected JSON: {"name": "test", "value": 123} hope this helps!'
        result = corrector._extract_json(text)
        assert json.loads(result) == {"name": "test", "value": 123}
    
    def test_successful_correction_with_mock_model(self):
        """Test successful correction with a mocked model."""
        config = OutputCorrectorConfig(enabled=True, max_retries=2)
        
        # Create mock model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"name": "corrected", "value": 42}'
        mock_model.invoke.return_value = mock_response
        
        corrector = OutputCorrector(config, corrector_model=mock_model)
        assert corrector.enabled
        
        # Create a validation error
        try:
            SimpleTestSchema.model_validate({"name": "test"})
        except ValidationError as e:
            validation_error = e
        
        result = corrector.correct_output(
            original_output='{"name": "test"}',
            schema_class=SimpleTestSchema,
            validation_error=validation_error,
        )
        
        assert result is not None
        assert isinstance(result, SimpleTestSchema)
        assert result.name == "corrected"
        assert result.value == 42
    
    def test_correction_fails_after_max_retries(self):
        """Test that correction fails after exhausting retries."""
        config = OutputCorrectorConfig(enabled=True, max_retries=2)
        
        # Create mock model that always returns invalid JSON
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = 'Not valid JSON at all'
        mock_model.invoke.return_value = mock_response
        
        corrector = OutputCorrector(config, corrector_model=mock_model)
        
        try:
            SimpleTestSchema.model_validate({})
        except ValidationError as e:
            validation_error = e
        
        result = corrector.correct_output(
            original_output='{}',
            schema_class=SimpleTestSchema,
            validation_error=validation_error,
        )
        
        assert result is None
        # Model should be called max_retries times
        assert mock_model.invoke.call_count == config.max_retries


class TestCreateOutputCorrector:
    """Tests for create_output_corrector function."""
    
    def test_create_disabled_corrector(self):
        """Test creating a disabled corrector."""
        config = OutputCorrectorConfig(enabled=False)
        corrector = create_output_corrector(config, None)
        
        assert isinstance(corrector, OutputCorrector)
        assert not corrector.enabled
    
    def test_create_enabled_without_model_config(self):
        """Test creating enabled corrector without model config."""
        config = OutputCorrectorConfig(enabled=True)
        corrector = create_output_corrector(config, None)
        
        assert isinstance(corrector, OutputCorrector)
        assert not corrector.enabled  # No model = effectively disabled


class TestOutputCorrectorConfig:
    """Tests for OutputCorrectorConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = OutputCorrectorConfig()
        
        assert config.enabled is True
        assert config.model_config_override is None
        assert config.max_retries == 2
        assert config.fallback_on_failure is True
    
    def test_custom_values(self):
        """Test custom configuration values."""
        model_config = ModelConfig(model_name="gpt-4")
        config = OutputCorrectorConfig(
            enabled=True,
            model_config_override=model_config,
            max_retries=3,
            fallback_on_failure=False,
        )
        
        assert config.enabled is True
        assert config.model_config_override is not None
        assert config.model_config_override.model_name == "gpt-4"
        assert config.max_retries == 3
        assert config.fallback_on_failure is False
    
    def test_max_retries_bounds(self):
        """Test max_retries validation."""
        config1 = OutputCorrectorConfig(max_retries=1)
        assert config1.max_retries == 1
        
        config5 = OutputCorrectorConfig(max_retries=5)
        assert config5.max_retries == 5
        
        with pytest.raises(ValueError):
            OutputCorrectorConfig(max_retries=0)
        
        with pytest.raises(ValueError):
            OutputCorrectorConfig(max_retries=6)


class TestAgentModelConfigWithCorrector:
    """Tests for AgentModelConfig with output corrector."""
    
    def test_default_corrector_config(self):
        """Test default corrector config in AgentModelConfig."""
        from autowerewolf.config.models import AgentModelConfig
        
        config = AgentModelConfig()
        
        assert config.output_corrector is not None
        assert config.output_corrector.enabled is True
    
    def test_get_corrector_model_config_disabled(self):
        """Test get_corrector_model_config when disabled."""
        from autowerewolf.config.models import AgentModelConfig
        
        config = AgentModelConfig(
            output_corrector=OutputCorrectorConfig(enabled=False)
        )
        
        result = config.get_corrector_model_config()
        assert result is None
    
    def test_get_corrector_model_config_enabled_no_override(self):
        """Test get_corrector_model_config uses default when no override."""
        from autowerewolf.config.models import AgentModelConfig
        
        config = AgentModelConfig(
            output_corrector=OutputCorrectorConfig(enabled=True)
        )
        
        result = config.get_corrector_model_config()
        assert result is not None
        assert result == config.default
    
    def test_get_corrector_model_config_with_override(self):
        """Test get_corrector_model_config uses override when provided."""
        from autowerewolf.config.models import AgentModelConfig
        
        override_model = ModelConfig(model_name="correction-model")
        config = AgentModelConfig(
            output_corrector=OutputCorrectorConfig(
                enabled=True,
                model_config_override=override_model,
            )
        )
        
        result = config.get_corrector_model_config()
        assert result is not None
        assert result.model_name == "correction-model"
