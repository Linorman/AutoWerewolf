"""
Web configuration loader.

This module handles loading default model configurations from YAML files
for the web interface.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from autowerewolf.web.schemas import WebModelConfig, WebOutputCorrectorConfig, WebGameConfig

logger = logging.getLogger(__name__)

# Default config file paths to search
DEFAULT_MODEL_CONFIG_PATHS = [
    "autowerewolf_models.yaml",
    "autowerewolf_models.yml",
    "config/models.yaml",
    "config/models.yml",
]

DEFAULT_GAME_CONFIG_PATHS = [
    "autowerewolf_config.yaml",
    "autowerewolf_config.yml",
    "config/game.yaml",
    "config/game.yml",
]


class WebConfigLoader:
    """Loads and manages web default configurations from files."""
    
    def __init__(self):
        self._model_config: Optional[WebModelConfig] = None
        self._output_corrector_config: Optional[WebOutputCorrectorConfig] = None
        self._game_config: Optional[WebGameConfig] = None
        self._config_path: Optional[Path] = None
        self._game_config_path: Optional[Path] = None
    
    def load_from_file(self, config_path: Optional[str] = None) -> bool:
        """
        Load model configuration from a YAML file.
        
        Args:
            config_path: Path to config file. If None, searches default paths.
            
        Returns:
            True if configuration was loaded, False if using defaults.
        """
        path = self._find_config_file(config_path, DEFAULT_MODEL_CONFIG_PATHS)
        
        if path is None:
            logger.info("No model config file found, using defaults")
            self._model_config = WebModelConfig()
            self._output_corrector_config = WebOutputCorrectorConfig()
            return False
        
        try:
            data = self._load_yaml(path)
            self._parse_model_config(data)
            self._config_path = path
            logger.info(f"Loaded model config from: {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}, using defaults")
            self._model_config = WebModelConfig()
            self._output_corrector_config = WebOutputCorrectorConfig()
            return False
    
    def load_game_config(self, config_path: Optional[str] = None) -> bool:
        """
        Load game configuration from a YAML file.
        
        Args:
            config_path: Path to config file. If None, searches default paths.
            
        Returns:
            True if configuration was loaded, False if using defaults.
        """
        path = self._find_config_file(config_path, DEFAULT_GAME_CONFIG_PATHS)
        
        if path is None:
            logger.info("No game config file found, using defaults")
            self._game_config = WebGameConfig()
            return False
        
        try:
            data = self._load_yaml(path)
            self._parse_game_config(data)
            self._game_config_path = path
            logger.info(f"Loaded game config from: {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load game config from {path}: {e}, using defaults")
            self._game_config = WebGameConfig()
            return False
    
    def _find_config_file(
        self, 
        explicit_path: Optional[str], 
        default_paths: list[str]
    ) -> Optional[Path]:
        """Find config file from explicit path or search default locations."""
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return path
            logger.warning(f"Specified config file not found: {explicit_path}")
            return None
        
        # Search default paths
        for default_path in default_paths:
            path = Path(default_path)
            if path.exists():
                return path
        
        return None
    
    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML file and return as dict."""
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}
    
    def _parse_model_config(self, data: Dict[str, Any]) -> None:
        """Parse model configuration from YAML data."""
        default_config = data.get("default", {})
        
        # Build WebModelConfig
        self._model_config = WebModelConfig(
            backend=default_config.get("backend", "ollama"),
            model_name=default_config.get("model_name", "llama3"),
            api_base=default_config.get("api_base"),
            api_key=default_config.get("api_key"),
            ollama_base_url=default_config.get("ollama_base_url"),
            temperature=default_config.get("temperature", 0.7),
            max_tokens=default_config.get("max_tokens", 1024),
            enable_corrector=data.get("output_corrector", {}).get("enabled", True),
            corrector_max_retries=data.get("output_corrector", {}).get("max_retries", 2),
        )
        
        # Build WebOutputCorrectorConfig
        corrector_data = data.get("output_corrector", {})
        corrector_override = corrector_data.get("model_config_override", {})
        
        use_separate = bool(corrector_override)
        
        self._output_corrector_config = WebOutputCorrectorConfig(
            enabled=corrector_data.get("enabled", True),
            max_retries=corrector_data.get("max_retries", 2),
            use_separate_model=use_separate,
            corrector_backend=corrector_override.get("backend") if use_separate else None,
            corrector_model_name=corrector_override.get("model_name") if use_separate else None,
            corrector_api_base=corrector_override.get("api_base") if use_separate else None,
            corrector_api_key=corrector_override.get("api_key") if use_separate else None,
            corrector_ollama_base_url=corrector_override.get("ollama_base_url") if use_separate else None,
        )
    
    def _parse_game_config(self, data: Dict[str, Any]) -> None:
        """Parse game configuration from YAML data."""
        self._game_config = WebGameConfig(
            role_set=data.get("role_set", "A"),
            random_seed=data.get("random_seed"),
        )
    
    @property
    def model_config(self) -> WebModelConfig:
        """Get loaded model configuration or defaults."""
        if self._model_config is None:
            self._model_config = WebModelConfig()
        return self._model_config
    
    @property
    def output_corrector_config(self) -> WebOutputCorrectorConfig:
        """Get loaded output corrector configuration or defaults."""
        if self._output_corrector_config is None:
            self._output_corrector_config = WebOutputCorrectorConfig()
        return self._output_corrector_config
    
    @property
    def game_config(self) -> WebGameConfig:
        """Get loaded game configuration or defaults."""
        if self._game_config is None:
            self._game_config = WebGameConfig()
        return self._game_config
    
    @property
    def config_path(self) -> Optional[Path]:
        """Get path of loaded model config file, or None if using defaults."""
        return self._config_path
    
    def get_defaults_dict(self) -> Dict[str, Any]:
        """Get all default configurations as a dictionary for API response."""
        return {
            "model_config": self.model_config.model_dump(),
            "output_corrector_config": self.output_corrector_config.model_dump(),
            "game_config": self.game_config.model_dump(),
            "config_source": str(self._config_path) if self._config_path else "defaults",
            "game_config_source": str(self._game_config_path) if self._game_config_path else "defaults",
        }


# Global instance for the web application
web_config_loader = WebConfigLoader()
