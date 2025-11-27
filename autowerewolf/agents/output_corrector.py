"""
Output Corrector Module

This module provides a separate model-based output correction mechanism
to fix malformed outputs from agent models, ensuring they conform to
the expected Pydantic schema.
"""
import json
import logging
from typing import TYPE_CHECKING, Any, Generic, Optional, Type, TypeVar, cast

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

from autowerewolf.config.models import ModelConfig, OutputCorrectorConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


CORRECTION_SYSTEM_PROMPT = """You are an output format corrector. Your task is to take a malformed JSON output and fix it to match the required schema.

IMPORTANT RULES:
1. Only output valid JSON that matches the schema
2. Do not add any explanation or markdown formatting
3. If a required field is missing, use a reasonable default based on context
4. Keep the original intent of the output as much as possible
5. Return ONLY the corrected JSON, nothing else

Your response must be a single valid JSON object, no markdown code blocks, no explanation."""


def _get_schema_description(schema_class: Type[BaseModel]) -> str:
    """Generate a human-readable schema description from a Pydantic model."""
    schema = schema_class.model_json_schema()
    
    lines = [f"Schema: {schema_class.__name__}"]
    lines.append("Required fields:")
    
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    for field_name, field_info in properties.items():
        is_required = field_name in required
        field_type = field_info.get("type", "any")
        description = field_info.get("description", "No description")
        default = field_info.get("default", "N/A")
        
        if is_required:
            lines.append(f"  - {field_name} ({field_type}): {description}")
        else:
            lines.append(f"  - {field_name} ({field_type}, optional, default={default}): {description}")
    
    return "\n".join(lines)


def _build_correction_prompt(
    original_output: str,
    schema_class: Type[BaseModel],
    validation_error: str,
    context: Optional[str] = None,
) -> str:
    """Build the correction prompt for the corrector model."""
    schema_desc = _get_schema_description(schema_class)
    
    prompt_parts = [
        "Please correct the following malformed output to match the required schema.",
        "",
        f"Expected Schema:",
        schema_desc,
        "",
        f"Validation Error:",
        validation_error,
        "",
        f"Original Output:",
        original_output,
    ]
    
    if context:
        prompt_parts.extend([
            "",
            "Context (use this to infer missing values):",
            context,
        ])
    
    prompt_parts.extend([
        "",
        "Please provide the corrected JSON output only, no explanation:",
    ])
    
    return "\n".join(prompt_parts)


class OutputCorrector:
    """
    A model-based output corrector that uses a separate LLM to fix
    malformed outputs from agent models.
    """
    
    def __init__(
        self,
        config: OutputCorrectorConfig,
        corrector_model: Optional["BaseChatModel"] = None,
    ):
        """
        Initialize the output corrector.
        
        Args:
            config: Configuration for the output corrector
            corrector_model: The LLM model to use for correction.
                            If None, correction is disabled.
        """
        self.config = config
        self.corrector_model = corrector_model
        self._enabled = config.enabled and corrector_model is not None
    
    @property
    def enabled(self) -> bool:
        """Check if the corrector is enabled and has a model."""
        return self._enabled
    
    def correct_output(
        self,
        original_output: Any,
        schema_class: Type[T],
        validation_error: ValidationError,
        context: Optional[str] = None,
    ) -> Optional[T]:
        """
        Attempt to correct a malformed output using the corrector model.
        
        Args:
            original_output: The original malformed output (string or dict)
            schema_class: The Pydantic model class to validate against
            validation_error: The validation error from the original attempt
            context: Optional context to help the corrector infer values
            
        Returns:
            The corrected and validated output, or None if correction failed
        """
        if not self.enabled:
            logger.debug("Output corrector is disabled")
            return None
        
        # Convert original output to string
        if isinstance(original_output, dict):
            original_str = json.dumps(original_output, ensure_ascii=False, indent=2)
        elif isinstance(original_output, BaseModel):
            original_str = original_output.model_dump_json(indent=2)
        else:
            original_str = str(original_output)
        
        error_str = str(validation_error)
        
        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"Correction attempt {attempt + 1}/{self.config.max_retries}")
                
                # Build the correction prompt
                correction_prompt = _build_correction_prompt(
                    original_output=original_str,
                    schema_class=schema_class,
                    validation_error=error_str,
                    context=context,
                )
                
                # Call the corrector model
                from langchain_core.messages import HumanMessage, SystemMessage
                
                messages = [
                    SystemMessage(content=CORRECTION_SYSTEM_PROMPT),
                    HumanMessage(content=correction_prompt),
                ]
                
                assert self.corrector_model is not None
                response = self.corrector_model.invoke(messages)
                corrected_str = str(response.content).strip()
                
                # Try to extract JSON from response (handle markdown code blocks)
                corrected_str = self._extract_json(corrected_str)
                
                # Parse and validate the corrected output
                corrected_data = json.loads(corrected_str)
                result = schema_class.model_validate(corrected_data)
                
                logger.info(f"Output correction successful on attempt {attempt + 1}")
                return result
                
            except json.JSONDecodeError as e:
                logger.warning(f"Correction attempt {attempt + 1} failed: JSON parse error - {e}")
                error_str = f"JSON parse error: {e}"
            except ValidationError as e:
                logger.warning(f"Correction attempt {attempt + 1} failed: Validation error - {e}")
                error_str = str(e)
            except Exception as e:
                logger.warning(f"Correction attempt {attempt + 1} failed: {type(e).__name__} - {e}")
                error_str = str(e)
        
        logger.error(f"Output correction failed after {self.config.max_retries} attempts")
        return None
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text, handling markdown code blocks."""
        text = text.strip()
        
        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's closing ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        # Try to find JSON object boundaries
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]
        
        return text.strip()


def create_output_corrector(
    config: OutputCorrectorConfig,
    model_config: Optional[ModelConfig] = None,
) -> OutputCorrector:
    """
    Create an OutputCorrector instance.
    
    Args:
        config: Configuration for the output corrector
        model_config: Model configuration for the corrector model.
                     If None and config.enabled is True, correction will be disabled.
    
    Returns:
        An OutputCorrector instance
    """
    corrector_model = None
    
    if config.enabled and model_config is not None:
        from autowerewolf.agents.backend import get_chat_model
        corrector_model = get_chat_model(model_config)
    
    return OutputCorrector(config=config, corrector_model=corrector_model)


class CorrectedStructuredOutput(Generic[T]):
    """
    A wrapper that provides structured output with automatic correction.
    
    This class wraps the standard `with_structured_output` functionality
    and adds automatic correction when validation fails.
    """
    
    def __init__(
        self,
        chat_model: "BaseChatModel",
        schema_class: Type[T],
        corrector: Optional[OutputCorrector] = None,
    ):
        """
        Initialize the corrected structured output wrapper.
        
        Args:
            chat_model: The main chat model
            schema_class: The Pydantic schema class for output
            corrector: Optional output corrector for fixing malformed outputs
        """
        self.chat_model = chat_model
        self.schema_class = schema_class
        self.corrector = corrector
        
        # Create the structured output chain
        self._structured_chain = chat_model.with_structured_output(schema_class)
    
    def invoke(self, input_data: Any, context: Optional[str] = None) -> T:
        """
        Invoke the model and return structured output with correction.
        
        Args:
            input_data: The input to the model
            context: Optional context for correction (used if validation fails)
            
        Returns:
            The validated structured output
        """
        try:
            # First, try the standard structured output
            result = self._structured_chain.invoke(input_data)
            return cast(T, result)
        except ValidationError as e:
            logger.warning(f"Structured output validation failed: {e}")
            
            # If we have a corrector, try to fix the output
            if self.corrector and self.corrector.enabled:
                # Get the raw output for correction
                raw_response = self.chat_model.invoke(input_data)
                raw_content = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
                
                corrected = self.corrector.correct_output(
                    original_output=raw_content,
                    schema_class=self.schema_class,
                    validation_error=e,
                    context=context,
                )
                
                if corrected is not None:
                    return cast(T, corrected)
            
            # Re-raise if correction failed or was not available
            raise
