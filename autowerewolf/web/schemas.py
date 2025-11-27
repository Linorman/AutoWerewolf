from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class GameMode(str, Enum):
    WATCH = "watch"
    PLAY = "play"


class WebModelConfig(BaseModel):
    backend: Literal["ollama", "api"] = "ollama"
    model_name: str = "qwen3:4b-instruct-2507-q4_K_M"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)


class WebGameConfig(BaseModel):
    role_set: Literal["A", "B"] = "A"
    random_seed: Optional[int] = None


class CreateGameRequest(BaseModel):
    mode: GameMode = GameMode.WATCH
    model_config_data: WebModelConfig = Field(default_factory=WebModelConfig)
    game_config: WebGameConfig = Field(default_factory=WebGameConfig)
    player_seat: Optional[int] = Field(default=None, ge=1, le=12)
    player_name: Optional[str] = None


class GameStateResponse(BaseModel):
    game_id: str
    status: str
    day_number: int
    phase: str
    players: List[Dict[str, Any]]
    sheriff_id: Optional[str] = None
    badge_torn: bool = False
    winning_team: Optional[str] = None


class PlayerViewResponse(BaseModel):
    player_id: str
    player_name: str
    role: str
    role_display: str
    private_info: Dict[str, Any]
    action_required: bool = False
    action_type: Optional[str] = None
    valid_targets: List[str] = Field(default_factory=list)
    action_context: Dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    event_type: str
    day_number: int
    phase: str
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    public: bool = True
    description: str = ""


class ActionSubmitRequest(BaseModel):
    action_type: str
    target_id: Optional[str] = None
    content: Optional[str] = None
    extra_data: Dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    success: bool
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class WSMessageType(str, Enum):
    GAME_STATE = "game_state"
    PLAYER_VIEW = "player_view"
    EVENT = "event"
    ACTION_REQUEST = "action_request"
    ACTION_RESPONSE = "action_response"
    GAME_OVER = "game_over"
    GAME_STOPPED = "game_stopped"
    ERROR = "error"
    CONNECTED = "connected"
    LOG = "log"
    NARRATION = "narration"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class GameListResponse(BaseModel):
    games: List[Dict[str, Any]]


class LanguageRequest(BaseModel):
    language: Literal["en", "zh"] = "en"


class TranslationsResponse(BaseModel):
    language: str
    translations: Dict[str, str]
