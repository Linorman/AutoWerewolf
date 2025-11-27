# AutoWerewolf Development Plan

This plan translates `system_design_en.md` into concrete development phases and tasks for engineers. It assumes a Python + LangChain implementation.

---

## Phase 0 – Project Bootstrap

1. **Repository & Packaging**
   - Initialize Python project structure as described in `system_design_en.md` (`autowerewolf/` package + `docs/`).
   - Add `pyproject.toml` or `requirements.txt` with minimal dependencies:
     - `langchain-core`, `langchain-community`, `langchain-ollama`
     - `pydantic`, `typer` (for CLI), `rich` (optional for pretty logs)
     - `pytest` (for tests)
   - Configure basic tooling:
     - `.gitignore`, formatting (e.g., `black`/`ruff` optional), CI placeholder.

2. **Baseline README & Docs Hook**
   - Update `README.md` with a short project description and link to:
     - `docs/werewolf_rules_en.md`
     - `docs/system_design_en.md`
     - `docs/development_plan_en.md` (this file).

Deliverable: Empty but compilable package with installable dependencies and passing `pytest` (no tests yet).

---

## Phase 1 – Core Domain Model & Rules Engine (Non-LLM)

Goal: Implement and fully test the pure game logic before integrating LLMs.

1. **Domain Models (`engine/state.py`, `engine/roles.py`)**
   - Implement enums and data models:
     - `Role`, `Alignment`, `Phase`, `WinningTeam`.
     - `Player`, `GameConfig`, `RuleVariants`, `GameState`.
     - `Event` base class + concrete event types (`NightKill`, `SeerCheck`, `WitchSave`, `VoteCast`, `SheriffElection`, `HunterShot`, `VillageIdiotReveal`, etc.).
     - `Action` base class + concrete action types.
   - Use `pydantic` models for validation and serialization.

2. **Rules Engine (`engine/rules.py`)**
   - Implement functions for:
     - Role assignment and validation (ensuring correct 12-player compositions for role set A/B).
     - Night resolution:
       - Input: `GameState` + list of night `Action`s.
       - Output: new `GameState` + `Event`s, applying rules in correct order.
     - Day resolution:
       - Speech tracking (events only, no logic).
       - Vote tallying including sheriff 1.5x votes and tie-breaking.
       - Lynch resolution, last words eligibility, and role-triggered effects (Hunter, Village Idiot).
     - Win condition checks (Side-Elimination by default, configurable to City-Elimination).
   - Encode rule variants from `RuleVariants`.

3. **Unit Tests (Rules Only)**
   - Create `tests/test_engine_rules.py` with coverage for:
     - Night kill + witch save + guard interactions, including `same_guard_same_save_kills` behavior.
     - Seer checks and their results storage in state.
     - Sheriff election, badge pass/tear, and vote weights.
     - Hunter shot logic and edge cases (poisoned, killed at night, etc.).
     - Village Idiot lynch + reveal behavior.
     - Win condition evaluation for all relevant end states.

Deliverable: Deterministic rules engine with high unit test coverage, no LLMs involved.

---

## Phase 2 – Model Backend Abstraction (API & Ollama)

Goal: Provide a unified way to obtain LangChain `ChatModel` instances for different backends.

1. **Config Models (`config/models.py`)**
   - Implement `ModelConfig`, `AgentModelConfig`, and defaults.
   - Include validation (e.g., `api_key` required when `backend == "api"`).

2. **Backend Adapter (`agents/backend.py`)**
   - Implement `get_chat_model(config: ModelConfig) -> BaseChatModel`:
     - `backend == "api"`: use `ChatOpenAI`-style model with customizable `api_base`, `model_name`, `api_key`.
     - `backend == "ollama"`: use `ChatOllama` with given `model_name`.
   - Add small integration tests with mocked environment variables or dummy keys to ensure correct instantiation.

3. **Configuration Loading**
   - Define a simple YAML/JSON format for `AgentModelConfig`.
   - Implement loader utilities in `config/models.py` or `io/persistence.py`.

Deliverable: One function call to obtain appropriate LangChain models for any agent role, with config-driven backend selection.

---

## Phase 3 – Base Agent Abstractions (LangChain)

Goal: Define a unified way to build and execute LLM-powered agents for players and moderator.

1. **BasePlayerAgent (`agents/player_base.py`)**
   - Define an abstract class or protocol with methods:
     - `decide_night_action(game_view) -> Action`
     - `decide_day_speech(game_view) -> SpeechAction`
     - `decide_vote(game_view) -> VoteAction`
     - Optional: `decide_sheriff_run(game_view)`, `decide_badge_pass(game_view)`.
   - Implement constructor taking:
     - `BaseChatModel` (from backend adapter).
     - Role metadata and prompt templates.
     - LangChain memory object per agent (see section 5 below).

2. **Prompt and Output Schema Design**
   - Define Pydantic models for structured outputs:
     - `SpeechOutput`, `VoteOutput`, `NightActionOutput` (union of role-specific fields).
   - Implement LangChain parsers or `with_structured_output` usage.

3. **ModeratorChain (`agents/moderator.py`)**
   - Implement a chain that receives `GameState` + `Event`s + `audience` and returns narration.
   - Ensure prompts enforce no leakage of hidden information.

4. **Minimal Integration Test**
   - Implement a dummy `GameState` and use a mock or very small model (can be a fake `LLM` implementation) to ensure chains run end-to-end and return valid structured outputs.

5. **LangChain Memory Implementation (`agents/memory.py`)**
   - Create a new module `agents/memory.py` to centralize memory management.
   - Implement memory types for agents:
     - Use `ConversationBufferMemory` for short-term conversational context (recent speeches, votes).
     - Use `ConversationSummaryMemory` for longer games to compress older history.
     - Implement `GameFactMemory` (custom class) to store structured facts:
       - Player claims (e.g., "Player 3 claimed Seer on Day 1").
       - Seer check results (private to Seer agent).
       - Suspicious behaviors observed.
       - Voting patterns and speech summaries.
   - Integrate memory into chain construction:
     - Modify `_build_night_chain()`, `_build_speech_chain()`, `_build_vote_chain()` to include memory context.
     - Use `RunnableWithMessageHistory` or manual injection of memory into prompts.
   - Implement memory update hooks:
     - `update_memory_after_speech(player_id, speech_content)`.
     - `update_memory_after_vote(player_id, vote_target)`.
     - `update_memory_after_night(player_id, night_events)`.
   - Ensure memory is scoped per agent (no cross-agent memory leakage).

Deliverable: Reusable agent base classes and schemas with integrated LangChain Memory, ready for concrete role-specific behavior.

---

## Phase 4 – Role-Specific Player Agents

Goal: Implement concrete LangChain agents for each role using the base abstractions.

1. **Werewolf Agent (`agents/roles/werewolf.py`)**
   - Night: choose `kill_target_id` (or special actions: self-explode/self-knife if enabled).
   - Day: speeches and votes informed by alignment and private knowledge.
   - **Werewolf Camp Coordination Mechanism** (see section 10 below for details).

2. **Villager Agent (`agents/roles/villager.py`)**
   - No night action.
   - Day: generate suspicion reasoning and votes based on public history.

3. **Seer Agent (`agents/roles/seer.py`)**
   - Night: select check target, store check result in private memory.
   - Day: decide whether to reveal information and how to speak/vote.

4. **Witch Agent (`agents/roles/witch.py`)**
   - Night: consume info about attack target and remaining potions.
   - Choose cure/poison actions under rules constraints.

5. **Hunter Agent (`agents/roles/hunter.py`)**
   - Day: normal speeches and votes.
   - On death: choose a target to shoot, respecting poison restrictions.

6. **Guard Agent (`agents/roles/guard.py`)** (role set A)
   - Night: choose guard target with engine preventing illegal repeats.

7. **Village Idiot Agent (`agents/roles/village_idiot.py`)** (role set B)
   - Day: speeches and votes as normal villager.
   - When lynched: decide reveal behavior if not automatic by rules.

8. **Role-Specific Prompt Tuning**
   - For each role, design:
     - System prompt (role goal, constraints, alignment).
     - Few-shot examples if needed (short, to control output schema).

9. **Tests with Mock LLMs**
   - Use deterministic fake LLM responses to verify each role agent:
     - Accepts a constrained `game_view` input.
     - Produces valid structured outputs.
     - Respects obvious constraints (e.g., no self-vote when disallowed).

10. **Werewolf Camp Internal Coordination Mechanism**
    - Implement werewolf-only communication during night phase:
      - **Option A: Shared Memory Approach**
        - Create `WerewolfCampMemory` class that is shared among all werewolf agents.
        - Store werewolf-only facts: confirmed villager roles, coordination strategies, kill history.
        - Each werewolf can read/write to this shared memory during night actions.
      - **Option B: Multi-Agent Discussion Chain**
        - Implement `WerewolfDiscussionChain` that simulates werewolf night discussion.
        - Input: game state visible to werewolves (all werewolf identities known to each other).
        - Process: Each werewolf agent proposes a target with reasoning (1-2 rounds).
        - Output: Consensus `kill_target_id` agreed upon by the pack.
      - **Implementation Details**:
        - Add `werewolf_coordination_mode: Literal["shared_memory", "discussion_chain", "none"]` to `RuleVariants`.
        - In `GameOrchestrator`, during night phase:
          1. Gather all alive werewolf agents.
          2. If `discussion_chain` mode: run `WerewolfDiscussionChain` to get consensus target.
          3. If `shared_memory` mode: each werewolf decides independently but with shared context.
          4. If `none`: first werewolf's decision is used (simple mode).
        - Ensure coordination happens BEFORE other night actions (Seer, Witch, Guard).
      - **Werewolf Private View**:
        - Werewolves see each other's identities in their `game_view.private_info`.
        - Include `fellow_werewolves: list[str]` in werewolf's private information.

Deliverable: All role agents implemented and testable in isolation with mock or stub LLMs, including werewolf coordination mechanism.

---

## Phase 5 – Game Orchestrator Implementation

Goal: Wire rules engine and agents together into a full game loop.

1. **Orchestrator Core (`orchestrator/game_orchestrator.py`)**
   - Implement `GameOrchestrator` with methods:
     - `__init__(config: GameConfig, agent_models: AgentModelConfig)`.
     - `run_game() -> GameResult`.
   - Responsibilities:
     - Initialize `GameState` and assign roles.
     - Construct all `PlayerAgent` and `ModeratorChain` instances using `get_chat_model`.
     - **Initialize Memory for each agent** (see section 6 below).
     - Manage the main loop:
       - Night: call role-appropriate `decide_night_action()`; pass actions to engine; update state.
       - Day: sheriff election (Day 1), speeches, votes, lynch resolution.
       - After each phase: call ModeratorChain to produce narration and record logs.
       - **Update agent memories** after each phase with relevant events.

2. **Game View Construction**
   - Implement functions to derive per-player `game_view` from `GameState` + `history`, ensuring:
     - Only public information + player's own private info is included.
     - No leakage of hidden roles or night actions.
     - For werewolves: include `fellow_werewolves` in private info.

3. **Error Handling and Fallbacks**
   - In orchestrator, wrap all agent calls with:
     - Timeout handling.
     - JSON/output validation (re-prompt once, then random legal choice on failure).

4. **Basic CLI Integration (`cli/main.py`)**
   - CLI options:
     - `--config` path to game config file.
     - `--backend` (api/ollama override).
     - `--model-name` override.
     - `--seed` for determinism.
   - Commands:
     - `run-game`: run a single game and print summary.
     - Optional: `simulate N` games.

5. **Integration Test (End-to-End, Mocked Models)**
   - Use deterministic fake LLM models returning simple but valid actions.
   - Run full game loop until win condition.
   - Assert no crashes and correct state transitions.

6. **Memory Initialization and Management in Orchestrator**
   - In `_create_agents()`:
     - Create a `ConversationBufferMemory` or `ConversationSummaryMemory` instance for each agent.
     - Create a `GameFactMemory` instance for each agent to store structured facts.
     - For werewolf agents: create or reference shared `WerewolfCampMemory`.
     - Pass memory objects to `create_player_agent()`.
   - Implement memory update cycle:
     - After night phase: update each agent's memory with visible night results.
     - After each speech: update all agents' memories with the speech content.
     - After voting: update all agents' memories with voting results.
   - Add `memory_type: Literal["buffer", "summary"]` to `GameConfig` for configurability.

7. **Werewolf Coordination Integration**
   - During night phase, before collecting individual night actions:
     - If `werewolf_coordination_mode == "discussion_chain"`:
       - Instantiate `WerewolfDiscussionChain` with all alive werewolf agents.
       - Run discussion chain to determine consensus kill target.
       - Use consensus target for all werewolf agents.
     - If `werewolf_coordination_mode == "shared_memory"`:
       - Ensure all werewolves share the same `WerewolfCampMemory`.
       - Each werewolf decides independently but sees shared strategic context.

Deliverable: A runnable game loop that can execute a full Werewolf game with stub or simple models, with proper memory management and werewolf coordination.

---

## Phase 6 – Logging, Persistence, and Observability

Goal: Make games inspectable and debuggable.

1. **Logging Utilities (`io/logging.py`)**
   - Implement structured logging for:
     - Config used for each run.
     - Per-turn `Event`s and important state changes.
     - Prompts and model responses (with PII/secret redaction where needed).
   - Consider using `logging` module with JSON formatter or `rich` for CLI display.

2. **Persistence Layer (`io/persistence.py`)**
   - Define `GameLog` schema.
   - Implement `save_game_log(path, game_log)` and `load_game_log(path)`.
   - Support at least JSON storage; SQLite optional.

3. **Replay/Analysis Hooks**
   - Provide utilities to:
     - Load a game log and print a human-readable summary.
     - Extract key statistics (e.g., win rate of wolves, potion usage, etc.).

Deliverable: All games produce persistent logs and can be replayed/analyzed offline.

---

## Phase 8 – Performance Tuning and Model-Specific Profiles

Goal: Make the system practical for multi-game simulations.

1. **Prompt Optimization**
   - Shorten prompts and outputs while keeping role behavior stable.
   - Add configuration for verbosity levels (e.g., `minimal_logs` vs `full_narration`).

2. **Model Profiles**
   - Define preset `AgentModelConfig`s for:
     - `fast_local`: Ollama small model, low temperature.
     - `cloud_strong`: API model with higher reasoning quality.

3. **Batching Opportunities**
   - Where supported by LangChain models, batch requests (e.g., all day speeches or votes) to reduce latency.

Deliverable: Configurable performance profiles and reduced cost/latency per game.

---

## Phase 9 – Optional Enhancements

These are optional but recommended for a more complete product.

1. **Human Player Support**
   - Allow 1+ human players; treat humans as special agents prompting via CLI or UI.

2. **Simple Web UI**
   - Add a lightweight web server (e.g., FastAPI) to visualize game progress.

3. **Advanced Analytics**
   - Aggregate statistics across many games to evaluate strategies, role balance, and model behavior.

---

## Execution Notes for the Team

- Prioritize **Phase 1–5** to get a fully automated, end-to-end playable system with stub or simple models.
- Keep rules engine pure and fully tested before relying on LLM logic.
- Ensure configuration and backend selection (API vs Ollama) remain data-driven and do not require code changes.
- Use incremental PRs aligned with phases to keep the codebase stable and reviewable.