import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from autowerewolf.streamlit_web.session import (
    StreamlitModelConfig,
    StreamlitGameConfig,
    StreamlitCorrectorConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DEFAULT_MODEL_CONFIG_PATHS = [
    "autowerewolf_models_config.yaml",
    "autowerewolf_models_config.yml",
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


class StreamlitConfigLoader:
    def __init__(self):
        self._model_config: Optional[StreamlitModelConfig] = None
        self._corrector_config: Optional[StreamlitCorrectorConfig] = None
        self._game_config: Optional[StreamlitGameConfig] = None
        self._config_path: Optional[Path] = None
        self._game_config_path: Optional[Path] = None
    
    def load_from_file(self, config_path: Optional[str] = None) -> bool:
        logger.info("[ConfigLoader] Loading model configuration...")
        if config_path is None:
            config_path = os.environ.get("AUTOWEREWOLF_MODEL_CONFIG")
            if config_path:
                logger.info(f"[ConfigLoader] Using environment variable AUTOWEREWOLF_MODEL_CONFIG: {config_path}")
        
        path = self._find_config_file(config_path, DEFAULT_MODEL_CONFIG_PATHS)
        
        if path is None:
            logger.info("[ConfigLoader] No model config file found, using defaults")
            self._model_config = StreamlitModelConfig()
            self._corrector_config = StreamlitCorrectorConfig()
            logger.info(f"[ConfigLoader] Default model: {self._model_config.backend}/{self._model_config.model_name}")
            return False
        
        try:
            data = self._load_yaml(path)
            self._parse_model_config(data)
            self._config_path = path
            logger.info(f"[ConfigLoader] Successfully loaded model config from: {path}")
            logger.info(f"[ConfigLoader] Model: {self._model_config.backend}/{self._model_config.model_name}")
            logger.info(f"[ConfigLoader] Temperature: {self._model_config.temperature}, MaxTokens: {self._model_config.max_tokens}")
            logger.info(f"[ConfigLoader] Corrector: enabled={self._corrector_config.enabled}, separate_model={self._corrector_config.use_separate_model}")
            return True
        except Exception as e:
            logger.warning(f"[ConfigLoader] Failed to load config from {path}: {e}, using defaults")
            self._model_config = StreamlitModelConfig()
            self._corrector_config = StreamlitCorrectorConfig()
            return False
    
    def load_game_config(self, config_path: Optional[str] = None) -> bool:
        logger.info("[ConfigLoader] Loading game configuration...")
        if config_path is None:
            config_path = os.environ.get("AUTOWEREWOLF_GAME_CONFIG")
            if config_path:
                logger.info(f"[ConfigLoader] Using environment variable AUTOWEREWOLF_GAME_CONFIG: {config_path}")
        
        path = self._find_config_file(config_path, DEFAULT_GAME_CONFIG_PATHS)
        
        if path is None:
            logger.info("[ConfigLoader] No game config file found, using defaults")
            self._game_config = StreamlitGameConfig()
            logger.info(f"[ConfigLoader] Default game config: role_set={self._game_config.role_set}, language={self._game_config.language}")
            return False
        
        try:
            data = self._load_yaml(path)
            self._parse_game_config(data)
            self._game_config_path = path
            logger.info(f"[ConfigLoader] Successfully loaded game config from: {path}")
            logger.info(f"[ConfigLoader] Role set: {self._game_config.role_set}, Language: {self._game_config.language}, Seed: {self._game_config.random_seed}")
            return True
        except Exception as e:
            logger.warning(f"[ConfigLoader] Failed to load game config from {path}: {e}, using defaults")
            self._game_config = StreamlitGameConfig()
            return False
    
    def _find_config_file(
        self, 
        explicit_path: Optional[str], 
        default_paths: list
    ) -> Optional[Path]:
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                logger.debug(f"[ConfigLoader] Found explicit config file: {path}")
                return path
            logger.warning(f"[ConfigLoader] Specified config file not found: {explicit_path}")
            return None
        
        logger.debug(f"[ConfigLoader] Searching for config in default paths: {default_paths}")
        for default_path in default_paths:
            path = Path(default_path)
            if path.exists():
                logger.debug(f"[ConfigLoader] Found config at default path: {path}")
                return path
        
        logger.debug("[ConfigLoader] No config file found in default paths")
        return None
    
    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        logger.debug(f"[ConfigLoader] Reading YAML file: {path}")
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        logger.debug(f"[ConfigLoader] YAML parsed successfully, keys: {list(data.keys())}")
        return data
    
    def _parse_model_config(self, data: Dict[str, Any]) -> None:
        logger.debug("[ConfigLoader] Parsing model configuration...")
        default_config = data.get("default", {})
        
        self._model_config = StreamlitModelConfig(
            backend=default_config.get("backend", "ollama"),
            model_name=default_config.get("model_name", "qwen3:4b-instruct-2507-q4_K_M"),
            api_base=default_config.get("api_base"),
            api_key=default_config.get("api_key"),
            ollama_base_url=default_config.get("ollama_base_url"),
            temperature=default_config.get("temperature", 0.7),
            max_tokens=default_config.get("max_tokens", 1024),
            enable_corrector=data.get("output_corrector", {}).get("enabled", True),
            corrector_max_retries=data.get("output_corrector", {}).get("max_retries", 2),
        )
        
        corrector_data = data.get("output_corrector", {})
        corrector_override = corrector_data.get("model_config_override", {})
        
        use_separate = bool(corrector_override)
        
        self._corrector_config = StreamlitCorrectorConfig(
            enabled=corrector_data.get("enabled", True),
            max_retries=corrector_data.get("max_retries", 2),
            use_separate_model=use_separate,
            corrector_backend=corrector_override.get("backend") if use_separate else None,
            corrector_model_name=corrector_override.get("model_name") if use_separate else None,
            corrector_api_base=corrector_override.get("api_base") if use_separate else None,
            corrector_api_key=corrector_override.get("api_key") if use_separate else None,
            corrector_ollama_base_url=corrector_override.get("ollama_base_url") if use_separate else None,
        )
        logger.debug("[ConfigLoader] Model configuration parsed successfully")
    
    def _parse_game_config(self, data: Dict[str, Any]) -> None:
        logger.debug("[ConfigLoader] Parsing game configuration...")
        self._game_config = StreamlitGameConfig(
            role_set=data.get("role_set", "A"),
            random_seed=data.get("random_seed"),
            language=data.get("language", "en"),
        )
        logger.debug("[ConfigLoader] Game configuration parsed successfully")
    
    @property
    def model_config(self) -> StreamlitModelConfig:
        if self._model_config is None:
            self._model_config = StreamlitModelConfig()
        return self._model_config
    
    @property
    def corrector_config(self) -> StreamlitCorrectorConfig:
        if self._corrector_config is None:
            self._corrector_config = StreamlitCorrectorConfig()
        return self._corrector_config
    
    @property
    def game_config(self) -> StreamlitGameConfig:
        if self._game_config is None:
            self._game_config = StreamlitGameConfig()
        return self._game_config
    
    @property
    def config_path(self) -> Optional[Path]:
        return self._config_path
    
    @property
    def game_config_path(self) -> Optional[Path]:
        return self._game_config_path
    
    def get_defaults_dict(self) -> Dict[str, Any]:
        return {
            "model_config": {
                "backend": self.model_config.backend,
                "model_name": self.model_config.model_name,
                "api_base": self.model_config.api_base,
                "api_key": self.model_config.api_key,
                "ollama_base_url": self.model_config.ollama_base_url,
                "temperature": self.model_config.temperature,
                "max_tokens": self.model_config.max_tokens,
                "enable_corrector": self.model_config.enable_corrector,
                "corrector_max_retries": self.model_config.corrector_max_retries,
            },
            "corrector_config": {
                "enabled": self.corrector_config.enabled,
                "max_retries": self.corrector_config.max_retries,
                "use_separate_model": self.corrector_config.use_separate_model,
                "corrector_backend": self.corrector_config.corrector_backend,
                "corrector_model_name": self.corrector_config.corrector_model_name,
            },
            "game_config": {
                "role_set": self.game_config.role_set,
                "random_seed": self.game_config.random_seed,
                "language": self.game_config.language,
            },
            "config_source": str(self._config_path) if self._config_path else "defaults",
            "game_config_source": str(self._game_config_path) if self._game_config_path else "defaults",
        }


streamlit_config_loader = StreamlitConfigLoader()
