# AutoWerewolf System Design (LLM Werewolf Game Agents)

## 1. Goals and Scope

AutoWerewolf is a system where multiple LLM-driven agents play the Werewolf game against each other under a neutral moderator. The system must:

- Implement full 12-player Werewolf rules (aligned with `werewolf_rules_en.md`).
- Support multiple model backends: HTTP API models and local Ollama models.
- Use LangChain as the orchestration framework for all agent logic and tools.
- Be robust and extensible as an engineering project (not a one-off script).

The initial scope focuses on self-play (all players are LLM agents) with a human able to observe logs and optionally join as a player later.

---

## 2. High-Level Architecture

### 2.1 Components

- **Game Orchestrator**
  - Owns the lifecycle of a single game instance.
  - Enforces rules and turn order (night/day cycle, voting, deaths, win conditions).
  - Interfaces with the Moderator agent to turn game state into natural-language prompts for players.

- **Moderator Agent (LLM-backed)**
  - Neutral narrator and rule enforcer in natural language.
  - Explains state transitions, announces deaths, manages speaking order textually.
  - Implemented as a LangChain chain/tool that converts internal state → player-facing messages.

- **Player Agents (LLM-backed)**
  - 12 agents: 4 Werewolves, 4 Villagers, 4 special roles (Seer, Witch, Hunter, Guard / Idiot).
  - Each agent has:
    - A hidden **role** and team alignment.
    - **Memory** of past days/nights, speeches, votes, checks, etc.
    - A LangChain chain that consumes structured game events and outputs actions (speech, vote, night action).

- **Game Engine / Rules Layer**
  - Purely deterministic, non-LLM logic implementing:
    - Role assignment and validation.
    - Night action ordering and conflict resolution (Seer → Wolves → Witch → Guard/Hunter, etc.).
    - Sheriff election and badge passing/tearing.
    - Win condition evaluation (Side-Elimination / Tu Bian by default).
  - Exposed through a clear API callable by the Orchestrator.

- **Model Backend Abstraction Layer**
  - Wraps different LLM providers behind a common interface:
    - **HTTP API models** (e.g., OpenAI-compatible APIs, custom inference servers).
    - **Ollama** local models.
  - Provides LangChain-compatible `LLM`/`ChatModel` implementations and configuration.

- **Persistence and Logging**
  - Structured logs for each game:
    - Game config (seed, models used, role distribution).
    - Turn-by-turn events, prompts, responses, and actions.
  - Optional storage backends: local JSON/SQLite initially.

- **CLI / Runner**
  - Entry point to launch games, choose models, seeds, and observe game progress.
  - Future: simple web UI can build on the same Orchestrator API.

### 2.2 Process Overview

1. **Game Setup**
   - Validate configuration (number of players, role set A/B, models, seeds).
   - Initialize Model Backends and LangChain LLM instances.
   - Create Player agents and the Moderator agent.
   - Randomly assign roles and initial sheriff election flag.

2. **Night/Day Cycle**
   - Loop until a win condition is met.
   - **Night**:
     - Orchestrator requests night actions from relevant Player agents via their LangChain chains.
     - Engine resolves actions (kills, saves, protections, checks, shots) according to rules.
   - **Day**:
     - On Day 1, run sheriff election.
     - Announce deaths; collect last words.
     - Manage discussion rounds (speeches) for all alive players.
     - Collect votes, lynch target, resolve last words and potential Hunter shot.

3. **Game End**
   - Engine checks win conditions (Village vs Werewolves).
   - Moderator announces results and optionally summarizes key events.
   - Logs are written and finalized.

---

## 3. Domain Model

### 3.1 Core Entities

- `Player`
  - `id: str`
  - `name: str`
  - `role: Role`
  - `alignment: Alignment` (Werewolf / Good)
  - `is_alive: bool`
  - `is_sheriff: bool`
  - `agent: PlayerAgent` (LangChain-based)

- `Role` (enum)
  - `WEREWOLF`
  - `VILLAGER`
  - `SEER`
  - `WITCH`
  - `HUNTER`
  - `GUARD`
  - `VILLAGE_IDIOT`

- `GameConfig`
  - `num_players: int` (default 12)
  - `role_set: Literal["A", "B"]` (A: Guard, B: Village Idiot)
  - `model_config: ModelConfig` (per-role or global)
  - `random_seed: Optional[int]`
  - `rule_variants: RuleVariants` (e.g. witch_self_heal_first_night, side_elimination=true)

- `GameState`
  - `day_number: int`
  - `phase: Literal["NIGHT", "DAY"]`
  - `players: list[Player]`
  - `sheriff_id: Optional[str]`
  - `badge_torn: bool`
  - `night_events: list[Event]`
  - `day_events: list[Event]`
  - `history: list[Event]`

- `Event`
  - Timestamped structured events (e.g., `NightKill`, `SeerCheck`, `WitchSave`, `VoteCast`, `SheriffElection`, `HunterShot`, `VillageIdiotReveal`).

- `Action`
  - Agent-chosen operations: `SelectKillTarget`, `SelectVoteTarget`, `MakeSpeech`, `UsePotion`, `GuardTarget`, `SheriffDecision`, `SelfExplode`, etc.

### 3.2 Rule Variants and Config

`RuleVariants` encapsulates toggles that might differ by playgroup but should be configurable:

- `witch_can_self_heal_n1: bool`
- `guard_can_self_guard: bool`
- `same_guard_same_save_kills: bool` (true if double-protected still dies)
- `win_mode: Literal["SIDE_ELIMINATION", "CITY_ELIMINATION"]`
- `allow_wolf_self_explode: bool`
- `allow_wolf_self_knife: bool`

The Game Engine reads these flags but Player Agents are told about the configured rules through system prompts.

---

## 4. LangChain-Based Agent Design

### 4.1 Common Patterns

- All agents are implemented as **LangChain chains** with:
  - A **system prompt** describing rules, objectives, and constraints.
  - Input: a structured description of the current game state from that agent's perspective.
  - Output: a constrained JSON (or other schema) representing `Action` or a `Speech`.
- Use **LangChain Structured Output** (e.g. `PydanticOutputParser` or `with_structured_output`) to ensure actions are machine-readable.
- Use **LangChain Memory** to provide short-term conversational context per agent:
  - `ConversationBufferMemory` or `ConversationSummaryMemory` scoped to each player.
  - Additional custom memory that stores structured facts (e.g., "Player 3 claimed Seer on Day 1").

### 4.2 Moderator Chain

- Input:
  - The full `GameState` (or a filtered view) and a list of `Event` objects for the last transition.
- Output:
  - Natural language narration for logs and for players (e.g., "Last night, Player 5 died.").
- Responsibilities:
  - Convert machine state transitions into consistent human-readable descriptions.
  - Optionally, generate short commentary/summary for observers.

Implementation sketch (Python):

- `ModeratorChain` (LangChain Runnable) wraps a `ChatModel` with a system prompt:
  - Explain that it must never leak hidden information.
  - It receives the game history and the audience ("to all players", "to werewolves only", etc.).

### 4.3 Player Agent Chains

Each role has a dedicated chain or a shared base chain with role-specific system prompts:

- **Inputs**:
  - `role`: seer/wolf/etc. (fixed in system prompt).
  - `phase`: `NIGHT` or `DAY`.
  - `visible_events`: only those this player should know (public speeches, own role, own prior actions, seer results, etc.).
  - `action_type`: e.g., `"NIGHT_ACTION"`, `"SPEECH"`, `"VOTE"`.
  - `candidate_targets`: valid player IDs (alive, not self when forbidden, etc.).

- **Outputs**:
  - For speech: `{ "type": "speech", "content": "..." }`.
  - For vote: `{ "type": "vote", "target_player_id": "P03" }`.
  - For night action: role-specific fields such as `seer_target_id`, `wolf_kill_target_id`, `witch_decision`, `guard_target_id`.

- **Special Role Logic** (encoded via prompts + engine verification):
  - **Seer**: chooses one player each night to check.
  - **Witch**: chooses to use cure/poison, respecting once-per-game limit and cannot use both in one night.
  - **Hunter**: chooses a target to shoot when allowed.
  - **Guard**: chooses a protection target; engine blocks illegal repeats.
  - **Village Idiot**: decides whether to reveal when lynched (or this may be automated by rule).

The Game Engine must **validate outputs** and, on invalid responses, either re-prompt or fall back to random valid actions (with logging).

---

## 5. Model Backend Abstraction (API & Ollama)

### 5.1 Requirements

- Support at least two categories of models:
  - **HTTP API models** (e.g. `openai`, `azure`, or custom `/chat/completions` endpoints).
  - **Ollama** local models (e.g. `llama3`, `qwen`, etc.).
- Make backends configurable via a single `ModelConfig` that the orchestrator reads.

### 5.2 ModelConfig

Example structure:

- `ModelConfig`
  - `backend: Literal["api", "ollama"]`
  - `model_name: str`
  - `api_base: Optional[str]` (for HTTP APIs)
  - `api_key: Optional[str]`
  - `temperature: float`
  - `max_tokens: int`
  - `timeout_s: int`

Support per-role overrides:

- `AgentModelConfig`
  - `default: ModelConfig`
  - `moderator: Optional[ModelConfig]`
  - `werewolf: Optional[ModelConfig]`
  - `villager: Optional[ModelConfig]`
  - `seer: Optional[ModelConfig]`
  - `witch: Optional[ModelConfig]`
  - `hunter: Optional[ModelConfig]`
  - `guard: Optional[ModelConfig]`
  - `village_idiot: Optional[ModelConfig]`

### 5.3 LangChain Integration

Implement a small adapter that returns a LangChain `ChatModel` given a `ModelConfig`:

- For `backend == "api"`:
  - Use `ChatOpenAI` or `ChatAnthropic`-style wrappers depending on chosen provider, or a generic `ChatOpenAI` with custom `openai_api_base`.
- For `backend == "ollama"`:
  - Use `ChatOllama` from `langchain-ollama`.

Exposed function:

- `get_chat_model(config: ModelConfig) -> BaseChatModel`

The Orchestrator uses this to construct all agent chains.

---

## 6. Game Orchestrator & Engine

### 6.1 Orchestrator Responsibilities

- Own the main event loop:
  - Initialize game from `GameConfig`.
  - For each phase, call the Game Engine to determine legal actions and next required decisions.
  - Call Player agents (LangChain chains) to obtain decisions.
  - Commit decisions in the engine and produce new `Event`s.
  - Call Moderator to produce human-readable messages.
- Guarantee **no information leaks**:
  - Each agent gets only its permitted view of `GameState`.
  - Moderator messages are filtered for audience.

### 6.2 Engine Responsibilities

- Provide a deterministic API like:
  - `apply_night_actions(game_state, night_actions) -> game_state, events`
  - `apply_day_speeches(game_state, speeches) -> events`
  - `apply_votes(game_state, votes) -> game_state, events`
  - `check_win_condition(game_state) -> Optional[WinningTeam]`

- Handle rule ordering:
  - Night order aligned with `werewolf_rules_en.md`:
    - Werewolves choose kill target.
    - Seer checks a player (or configured order per group).
    - Witch receives info on kill target; decides cure/poison.
    - Guard protects a target.
    - Hunter/Village Idiot passive triggers later on death.

- Implement sheriff logic:
  - On Day 1, run special `SheriffElection` phase.
  - Sheriff has 1.5 votes and speaks first/last per rules.
  - On sheriff death, apply badge pass/tear decision.

---

## 7. LangChain Flows per Phase

### 7.1 Night Phase Flow

For each night:

1. **Collect Werewolf Decision**
   - Visible info: all public history + werewolf camp private chat (if enabled).
   - Chain: `wolf_night_chain` returns `kill_target_id` or `self_explode`/`self_knife` decisions.
2. **Collect Seer Check**
   - `seer_chain` suggests a `target_id` to inspect.
   - Engine resolves alignment and stores in Seer private memory.
3. **Witch Decision**
   - `witch_chain` receives info about who was attacked, remaining potions, and public state.
   - Returns `use_cure: bool`, `use_poison: bool`, and possible `poison_target_id`.
4. **Guard Protection** (if using Set A)
   - `guard_chain` chooses `guard_target_id` with engine enforcing constraints.
5. **Resolve Night**
   - Engine applies rules (attacks, saves, protections, conflicts like `same_guard_same_save_kills`).
   - Generates `NightKill`, `Saved`, and `CheckResult` events.

### 7.2 Day Phase Flow

For each day:

1. **Sheriff Election (Day 1)**
   - Orchestrator asks each agent if they want to run.
   - Candidates give speeches; others vote; Engine computes sheriff.
2. **Announce Deaths and Last Words**
   - Moderator chain narrates results.
   - Orchestrator solicits last words speeches where allowed (night-kill first night, all lynched players).
3. **Discussion Round**
   - Orchestrator iterates over alive players (according to sheriff ordering) and prompts `day_speech_chain` for each.
4. **Voting**
   - All alive players provide a vote target.
   - Engine tallies votes, applying sheriff 1.5x multiplier, resolves ties per config.
5. **Lynch Resolution**
   - Apply death and triggers:
     - Hunter shot if conditions met.
     - Village Idiot reveal and survival if lynched.
   - Add events to history.
6. **Check Win Condition**
   - If a team has won, exit loop; otherwise proceed to next night.

---

## 8. Reliability and Engineering Considerations

### 8.1 Determinism and Reproducibility

- Seed all randomness (role assignment, tie-breaking, fallback random actions) with a known `random_seed`.
- Log prompts and responses to enable replay and debugging.
- Provide an option to run in **deterministic mode** with fixed temperature and seeds.

### 8.2 Error Handling

- Structured output validation:
  - If an agent returns invalid JSON or illegal actions, re-prompt once with explicit error message.
  - If still invalid, choose a random legal action and log the issue.
- Timeouts and retries:
  - Configurable per-model timeout; on timeout, retry N times or fallback to default action.

### 8.3 Performance

- Support running at **fast simulation speed** by:
  - Skipping verbose natural-language narration when not needed; use compact logs.
  - Using small, fast models via Ollama or API.

### 8.4 Extensibility

- Clean separation between:
  - Rule logic (pure Python, unit-testable).
  - Agent chains (LangChain graph; swap models or prompts freely).
  - Backends (API vs Ollama configurable without code changes).

---

## 9. Project Structure (Proposed)

```text
autowerewolf/
  docs/
    werewolf_rules_en.md
    werewolf_rules.md
    system_design_en.md  # this file
  autowerewolf/
    __init__.py
    config/
      __init__.py
      models.py          # ModelConfig, AgentModelConfig, RuleVariants, GameConfig
    engine/
      __init__.py
      roles.py           # enums and role definitions
      state.py           # GameState, Player, Event, Action models
      rules.py           # core resolution logic, win conditions
    agents/
      __init__.py
      backend.py         # get_chat_model, backend selection (api/ollama)
      moderator.py       # ModeratorChain implementation
      player_base.py     # BasePlayerAgent (LangChain chain wrapper)
      roles/
        seer.py
        werewolf.py
        villager.py
        witch.py
        hunter.py
        guard.py
        village_idiot.py
    orchestrator/
      __init__.py
      game_orchestrator.py  # main game loop
    io/
      __init__.py
      logging.py         # JSON + human-readable logging utilities
      persistence.py     # save/load game logs
    cli/
      __init__.py
      main.py            # CLI entry (e.g. `python -m autowerewolf.cli.main`)
  pyproject.toml or requirements.txt
  README.md
```

---

## 10. LangChain

### 10.1 LangChain Version and Core Usage

- Use a recent LangChain release compatible with:
  - `langchain-core`
  - `langchain-community`
  - `langchain-ollama`
- Patterns:
  - Define each agent as a `Runnable` chain created via `chat_model | parser` or `ChatPromptTemplate | chat_model | parser`.
  - Use `RunnableSequence` or `LCEL` composition for more complex flows.

---

## 11. Testing Strategy

- **Unit Tests** (no LLMs):
  - Rules engine (`rules.py`) for all night/day interactions and edge cases.
  - Win condition checks.
  - Sheriff election and badge pass/tear.

- **Integration Tests** (with mocked LLMs):
  - Replace all agents with deterministic stubs that return fixed actions.
  - Simulate full games to ensure orchestrator and engine interactions are correct.

- **Smoke Tests** (with real models):
  - Run short games with small models (Ollama) to verify:
    - No crashes.
    - Actions are valid most of the time.
    - Logs are complete.

---

## 12. Deployment and Configuration

- **Local Development**:
  - Install via `pip` (editable mode) and run CLI.
  - For Ollama backend, require `ollama` installed and a model pulled.

- **Configuration Files**:
  - YAML/JSON config for `GameConfig` and `AgentModelConfig`.
  - Allow overriding via CLI flags (backend, model_name, seed, etc.).

- **Future Extensions**:
  - Web dashboard for observing games in real time.
  - Support human players.
  - Additional role sets and custom rule variants.

---

