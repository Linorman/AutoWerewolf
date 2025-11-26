# AutoWerewolf

LLM-driven Werewolf Game Agents - A system where multiple LLM agents play the Werewolf game against each other.

## Overview

AutoWerewolf implements full 12-player Werewolf rules with LLM-powered agents. The system supports:

- **12-player games** with standard role compositions
- **Two role sets**: 
  - Set A: Seer, Witch, Hunter, Guard
  - Set B: Seer, Witch, Hunter, Village Idiot
- **Multiple model backends**: HTTP API models and local Ollama models
- **LangChain integration** for all agent logic
- **Agent memory system** for strategic reasoning and fact tracking
- **Werewolf coordination** via shared memory or discussion chains
- **Performance profiles** for optimized simulation speed
- **Comprehensive analytics** for multi-game statistics

## Features

### Core Game Engine
- Complete 12-player Werewolf rules implementation
- Night action resolution (Seer, Witch, Guard, Hunter, Werewolves)
- Day phase with speeches, voting, and lynch resolution
- Sheriff election and badge passing/tearing mechanics
- Configurable rule variants (witch self-heal, guard rules, win conditions)

### LLM-Powered Agents
- Role-specific agents: Werewolf, Villager, Seer, Witch, Hunter, Guard, Village Idiot
- LangChain-based chains with structured output parsing
- Per-agent memory system (conversation + game facts)
- Werewolf camp coordination (shared memory or multi-agent discussion)

### Performance & Optimization
- Model profiles: `fast_local`, `balanced`, `cloud_strong`
- Performance presets: `minimal`, `standard`, `fast`, `simulation`
- Batch execution for parallel agent calls
- Configurable verbosity and narration levels

### Logging & Analysis
- Structured game logs (JSON persistence)
- Game replay and analysis tools
- Multi-game statistics and win rate analysis
- Timeline visualization

## Installation

```bash
# Basic installation (rules engine only)
pip install -e .

# With LLM support
pip install -e ".[llm]"

# With CLI support
pip install -e ".[cli]"

# Full installation (development)
pip install -e ".[all]"
```

## Quick Start

### Using the CLI

```bash
# Run a single game with Ollama
autowerewolf run-game --backend ollama --model llama3

# Run a game with a specific role set
autowerewolf run-game --role-set B --seed 42

# Use a performance profile
autowerewolf run-game --profile fast_local

# Run multiple simulations
autowerewolf simulate 10 --backend ollama --model llama3 --fast

# Analyze saved game logs
autowerewolf analyze ./game_logs/

# Replay a specific game
autowerewolf replay ./game_logs/game_0001.json --timeline
```

### Using the Python API

```python
from autowerewolf.engine import (
    create_game_state,
    GameConfig,
    RoleSet,
    resolve_night_actions,
    check_win_condition,
)

# Create a game with role set A
config = GameConfig(role_set=RoleSet.A, random_seed=42)
state = create_game_state(config)

# Game state contains 12 players with assigned roles
for player in state.players:
    print(f"{player.name}: {player.role.value}")
```

### Running Full Games with LLM Agents

```python
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator
from autowerewolf.engine.state import GameConfig
from autowerewolf.engine.roles import RoleSet
from autowerewolf.config.models import AgentModelConfig, ModelConfig, ModelBackend

# Configure the game
game_config = GameConfig(role_set=RoleSet.A, random_seed=42)

# Configure the model
model_config = AgentModelConfig(
    default=ModelConfig(
        backend=ModelBackend.OLLAMA,
        model_name="llama3",
        temperature=0.7,
    )
)

# Create and run the orchestrator
orchestrator = GameOrchestrator(
    config=game_config,
    agent_models=model_config,
)
result = orchestrator.run_game()

print(f"Winner: {result.winning_team.value}")
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `run-game` | Run a single Werewolf game with LLM agents |
| `simulate N` | Run N games and collect statistics |
| `replay <log>` | Replay and analyze a saved game log |
| `analyze <dir>` | Analyze multiple game logs for aggregate statistics |

### Common Options

| Option | Description |
|--------|-------------|
| `--backend` | Model backend: `ollama` or `api` |
| `--model` | Model name (e.g., `llama3`, `gpt-4`) |
| `--role-set` | Role set: `A` (Guard) or `B` (Village Idiot) |
| `--seed` | Random seed for reproducibility |
| `--profile` | Model profile: `fast_local`, `balanced`, `cloud_strong` |
| `--performance` | Performance preset: `minimal`, `standard`, `fast`, `simulation` |
| `--output` | Output file/directory for game logs |

## Documentation

- [Werewolf Rules (English)](docs/werewolf_rules_en.md)
- [System Design](docs/system_design_en.md)
- [Development Plan](docs/development_plan_en.md)

## Project Structure

```
autowerewolf/
├── autowerewolf/
│   ├── config/              # Configuration models
│   │   ├── models.py        # Model and agent configuration
│   │   └── performance.py   # Performance profiles and presets
│   ├── engine/              # Game rules and state
│   │   ├── roles.py         # Role enums and constants
│   │   ├── state.py         # Pydantic models for game state
│   │   └── rules.py         # Core game logic
│   ├── agents/              # LangChain-based agents
│   │   ├── backend.py       # Model backend abstraction
│   │   ├── batch.py         # Batch execution for parallel calls
│   │   ├── memory.py        # Agent memory management
│   │   ├── moderator.py     # Moderator chain for narration
│   │   ├── player_base.py   # Base player agent class
│   │   ├── prompts.py       # Prompt templates
│   │   ├── schemas.py       # Pydantic output schemas
│   │   └── roles/           # Role-specific agents
│   │       ├── werewolf.py
│   │       ├── villager.py
│   │       ├── seer.py
│   │       ├── witch.py
│   │       ├── hunter.py
│   │       ├── guard.py
│   │       └── village_idiot.py
│   ├── orchestrator/        # Game loop management
│   │   └── game_orchestrator.py
│   ├── io/                  # Logging and persistence
│   │   ├── logging.py       # Structured logging
│   │   ├── persistence.py   # Game log save/load
│   │   └── analysis.py      # Statistics and analysis
│   └── cli/                 # Command-line interface
│       └── main.py
├── tests/                   # Unit tests
├── docs/                    # Documentation
└── pyproject.toml           # Project configuration
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=autowerewolf
```

### Code Quality

```bash
# Format code
black autowerewolf tests

# Lint
ruff check autowerewolf tests

# Type check
mypy autowerewolf
```

## Requirements

- Python 3.10+
- For LLM features: LangChain, LangGraph
- For local models: [Ollama](https://ollama.ai/) installed with models pulled

## License

MIT License
