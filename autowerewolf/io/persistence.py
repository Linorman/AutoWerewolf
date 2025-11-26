import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from autowerewolf.config.models import AgentModelConfig, ModelConfig
from autowerewolf.engine.roles import RoleSet, WinningTeam


class PlayerLog(BaseModel):
    id: str
    name: str
    seat_number: int
    role: str
    alignment: str
    is_alive: bool
    is_sheriff: bool = False


class EventLog(BaseModel):
    event_type: str
    timestamp: datetime
    day_number: int
    phase: str
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    public: bool = True


class GameLog(BaseModel):
    game_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    config: dict[str, Any]
    model_config_info: dict[str, Any] = Field(default_factory=dict)
    role_set: str
    random_seed: Optional[int] = None
    winning_team: str = "none"
    final_day: int = 0
    players: list[PlayerLog] = Field(default_factory=list)
    events: list[EventLog] = Field(default_factory=list)
    narration_log: list[str] = Field(default_factory=list)
    werewolf_discussions: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)

    def add_werewolf_discussion(
        self,
        night_number: int,
        discussions: list[dict[str, Any]],
    ) -> None:
        self.werewolf_discussions[str(night_number)] = discussions

    def add_event(
        self,
        event_type: str,
        day_number: int,
        phase: str,
        actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        public: bool = True,
    ) -> None:
        event = EventLog(
            event_type=event_type,
            timestamp=datetime.now(),
            day_number=day_number,
            phase=phase,
            actor_id=actor_id,
            target_id=target_id,
            data=data or {},
            public=public,
        )
        self.events.append(event)

    def set_result(
        self,
        winning_team: WinningTeam,
        final_day: int,
    ) -> None:
        self.end_time = datetime.now()
        self.winning_team = winning_team.value
        self.final_day = final_day

    def get_public_events(self) -> list[EventLog]:
        return [e for e in self.events if e.public]

    def get_events_by_type(self, event_type: str) -> list[EventLog]:
        return [e for e in self.events if e.event_type == event_type]

    def get_events_for_day(self, day: int) -> list[EventLog]:
        return [e for e in self.events if e.day_number == day]


def create_game_log(
    game_id: str,
    config: dict[str, Any],
    role_set: RoleSet,
    random_seed: Optional[int] = None,
    model_config_info: Optional[dict[str, Any]] = None,
) -> GameLog:
    return GameLog(
        game_id=game_id,
        start_time=datetime.now(),
        config=config,
        model_config_info=model_config_info or {},
        role_set=role_set.value,
        random_seed=random_seed,
    )


def save_game_log(game_log: GameLog, path: Union[str, Path]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = game_log.model_dump(mode="json")
    
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
            content = yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)
        except ImportError:
            raise ImportError("PyYAML is required for YAML files. Install with: pip install pyyaml")
    else:
        content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    
    path.write_text(content, encoding="utf-8")


def load_game_log(path: Union[str, Path]) -> GameLog:
    path = Path(path)
    data = _load_file(path)
    return GameLog(**data)


def load_model_config(path: Union[str, Path]) -> ModelConfig:
    path = Path(path)
    data = _load_file(path)
    return ModelConfig(**data)


def load_agent_model_config(path: Union[str, Path]) -> AgentModelConfig:
    path = Path(path)
    data = _load_file(path)
    return AgentModelConfig(**data)


def save_model_config(config: ModelConfig, path: Union[str, Path]) -> None:
    path = Path(path)
    data = config.model_dump(exclude_none=True)
    _save_file(data, path)


def save_agent_model_config(config: AgentModelConfig, path: Union[str, Path]) -> None:
    path = Path(path)
    data = config.model_dump(exclude_none=True)
    _save_file(data, path)


def _load_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8")

    if suffix in (".yaml", ".yml"):
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
    elif suffix == ".json":
        return json.loads(content)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}. Use .yaml, .yml, or .json")


def _save_file(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            import yaml
            content = yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)
        except ImportError:
            raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
    elif suffix == ".json":
        content = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}. Use .yaml, .yml, or .json")

    path.write_text(content, encoding="utf-8")
