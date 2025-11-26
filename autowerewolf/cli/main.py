import json
import logging
from pathlib import Path
from typing import Optional

import typer

from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig
from autowerewolf.config.performance import (
    MODEL_PROFILES,
    PERFORMANCE_PRESETS,
    PerformanceConfig,
    VerbosityLevel,
    get_model_profile,
    get_performance_preset,
)
from autowerewolf.engine.roles import RoleSet
from autowerewolf.engine.state import GameConfig, RuleVariants
from autowerewolf.io.analysis import (
    MultiGameAnalyzer,
    analyze_game,
    print_game_summary,
    print_game_timeline,
)
from autowerewolf.io.logging import GameLogLevel
from autowerewolf.io.persistence import (
    load_agent_model_config,
    load_game_log,
    save_game_log,
)
from autowerewolf.orchestrator.game_orchestrator import GameOrchestrator, GameResult

app = typer.Typer(
    name="autowerewolf",
    help="AutoWerewolf - LLM-powered Werewolf game simulation",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_game_config(
    role_set: str = "A",
    seed: Optional[int] = None,
) -> GameConfig:
    rs = RoleSet.A if role_set.upper() == "A" else RoleSet.B
    return GameConfig(
        role_set=rs,
        random_seed=seed,
        rule_variants=RuleVariants(),
    )


def create_model_config(
    backend: str,
    model_name: str,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    repeat_penalty: Optional[float] = None,
    model_seed: Optional[int] = None,
) -> AgentModelConfig:
    backend_enum = ModelBackend.OLLAMA if backend.lower() == "ollama" else ModelBackend.API

    default_config = ModelConfig(
        backend=backend_enum,
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        ollama_base_url=ollama_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        seed=model_seed,
    )

    return AgentModelConfig(default=default_config)


def print_game_result(result: GameResult) -> None:
    typer.echo("\n" + "=" * 60)
    typer.echo("GAME RESULT")
    typer.echo("=" * 60)

    typer.echo(f"\nWinner: {result.winning_team.value.upper()}")

    typer.echo("\n--- Final Player Status ---")
    for player in result.final_state.players:
        status = "ALIVE" if player.is_alive else "DEAD"
        sheriff = " [Sheriff]" if player.is_sheriff else ""
        typer.echo(
            f"  {player.name} (Seat {player.seat_number}): "
            f"{player.role.value.upper()} - {status}{sheriff}"
        )

    typer.echo("\n--- Game Narration ---")
    for narration in result.narration_log[-10:]:
        typer.echo(f"  {narration}")

    typer.echo("\n" + "=" * 60)


@app.command()
def run_game(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to game configuration file (YAML/JSON)",
    ),
    model_config_path: Optional[Path] = typer.Option(
        None,
        "--model-config",
        "-m",
        help="Path to model configuration file (YAML/JSON)",
    ),
    backend: str = typer.Option(
        "ollama",
        "--backend",
        "-b",
        help="Model backend: 'ollama' or 'api'",
    ),
    model_name: str = typer.Option(
        "llama3",
        "--model",
        help="Model name to use",
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        help="API base URL (for OpenAI-compatible API backend)",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key (for API backend)",
    ),
    ollama_base_url: Optional[str] = typer.Option(
        None,
        "--ollama-url",
        help="Ollama endpoint URL (default: http://localhost:11434)",
    ),
    temperature: float = typer.Option(
        0.7,
        "--temperature",
        "-t",
        help="Sampling temperature (0.0-2.0)",
    ),
    max_tokens: int = typer.Option(
        1024,
        "--max-tokens",
        help="Maximum tokens in response",
    ),
    top_p: Optional[float] = typer.Option(
        None,
        "--top-p",
        help="Top-p (nucleus) sampling (0.0-1.0)",
    ),
    top_k: Optional[int] = typer.Option(
        None,
        "--top-k",
        help="Top-k sampling",
    ),
    repeat_penalty: Optional[float] = typer.Option(
        None,
        "--repeat-penalty",
        help="Repeat penalty for Ollama",
    ),
    model_seed: Optional[int] = typer.Option(
        None,
        "--model-seed",
        help="Random seed for model generation",
    ),
    role_set: str = typer.Option(
        "A",
        "--role-set",
        "-r",
        help="Role set to use: 'A' (Guard) or 'B' (Village Idiot)",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        "-s",
        help="Random seed for game reproducibility",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for game log (JSON)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    log_level: str = typer.Option(
        "standard",
        "--log-level",
        "-l",
        help="Logging level: 'minimal', 'standard', or 'verbose'",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help=f"Model profile: {', '.join(MODEL_PROFILES.keys())}",
    ),
    performance_preset: str = typer.Option(
        "standard",
        "--performance",
        help=f"Performance preset: {', '.join(PERFORMANCE_PRESETS.keys())}",
    ),
    enable_batching: bool = typer.Option(
        False,
        "--batch",
        help="Enable parallel batching of agent calls",
    ),
) -> None:
    """Run a single Werewolf game with LLM agents."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    typer.echo("AutoWerewolf - Starting game...\n")

    game_config = create_game_config(role_set=role_set, seed=seed)

    if profile:
        try:
            agent_model_config = get_model_profile(profile)
            typer.echo(f"Using model profile: {profile}")
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    elif model_config_path and model_config_path.exists():
        agent_model_config = load_agent_model_config(model_config_path)
    else:
        agent_model_config = create_model_config(
            backend=backend,
            model_name=model_name,
            api_base=api_base,
            api_key=api_key,
            ollama_base_url=ollama_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            model_seed=model_seed,
        )

    try:
        perf_config = get_performance_preset(performance_preset)
        if enable_batching:
            perf_config = PerformanceConfig(
                verbosity=perf_config.verbosity,
                enable_batching=True,
                batch_size=perf_config.batch_size,
                skip_narration=perf_config.skip_narration,
                compact_logs=perf_config.compact_logs,
                max_speech_length=perf_config.max_speech_length,
                max_reasoning_length=perf_config.max_reasoning_length,
            )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    game_log_level = GameLogLevel(log_level.lower())
    output_path = output.parent if output else None

    orchestrator = GameOrchestrator(
        config=game_config,
        agent_models=agent_model_config,
        log_level=game_log_level,
        output_path=output_path,
        enable_console_logging=True,
        enable_file_logging=output is not None,
        performance_config=perf_config,
    )

    typer.echo("Initializing game...")
    typer.echo(f"  Role Set: {game_config.role_set.value}")
    typer.echo(f"  Backend: {agent_model_config.default.backend.value}")
    typer.echo(f"  Model: {agent_model_config.default.model_name}")
    if seed:
        typer.echo(f"  Seed: {seed}")
    typer.echo("")

    try:
        result = orchestrator.run_game()
        print_game_result(result)

        if output and result.game_log:
            save_game_log(result.game_log, output)
            typer.echo(f"\nGame log saved to: {output}")

    except Exception as e:
        typer.echo(f"\nError during game: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def simulate(
    num_games: int = typer.Argument(
        ...,
        help="Number of games to simulate",
    ),
    backend: str = typer.Option(
        "ollama",
        "--backend",
        "-b",
        help="Model backend: 'ollama' or 'api'",
    ),
    model_name: str = typer.Option(
        "llama3",
        "--model",
        help="Model name to use",
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        help="API base URL (for OpenAI-compatible API backend)",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key (for API backend)",
    ),
    ollama_base_url: Optional[str] = typer.Option(
        None,
        "--ollama-url",
        help="Ollama endpoint URL (default: http://localhost:11434)",
    ),
    temperature: float = typer.Option(
        0.7,
        "--temperature",
        "-t",
        help="Sampling temperature (0.0-2.0)",
    ),
    max_tokens: int = typer.Option(
        1024,
        "--max-tokens",
        help="Maximum tokens in response",
    ),
    top_p: Optional[float] = typer.Option(
        None,
        "--top-p",
        help="Top-p (nucleus) sampling (0.0-1.0)",
    ),
    top_k: Optional[int] = typer.Option(
        None,
        "--top-k",
        help="Top-k sampling",
    ),
    repeat_penalty: Optional[float] = typer.Option(
        None,
        "--repeat-penalty",
        help="Repeat penalty for Ollama",
    ),
    model_seed: Optional[int] = typer.Option(
        None,
        "--model-seed",
        help="Random seed for model generation",
    ),
    role_set: str = typer.Option(
        "A",
        "--role-set",
        "-r",
        help="Role set to use: 'A' (Guard) or 'B' (Village Idiot)",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory for game logs",
    ),
    log_level: str = typer.Option(
        "minimal",
        "--log-level",
        "-l",
        help="Logging level: 'minimal', 'standard', or 'verbose'",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help=f"Model profile: {', '.join(MODEL_PROFILES.keys())}",
    ),
    fast_mode: bool = typer.Option(
        True,
        "--fast/--no-fast",
        help="Use simulation performance preset for faster execution",
    ),
) -> None:
    """Run multiple Werewolf games and collect statistics."""
    typer.echo(f"AutoWerewolf - Simulating {num_games} games...\n")

    if profile:
        try:
            agent_model_config = get_model_profile(profile)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        agent_model_config = create_model_config(
            backend=backend,
            model_name=model_name,
            api_base=api_base,
            api_key=api_key,
            ollama_base_url=ollama_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            model_seed=model_seed,
        )

    perf_config = get_performance_preset("simulation" if fast_mode else "standard")
    game_log_level = GameLogLevel(log_level.lower())

    results = {
        "village_wins": 0,
        "werewolf_wins": 0,
        "total_games": 0,
        "errors": 0,
    }

    for i in range(num_games):
        typer.echo(f"Game {i + 1}/{num_games}...", nl=False)

        game_config = create_game_config(role_set=role_set, seed=None)
        orchestrator = GameOrchestrator(
            config=game_config,
            agent_models=agent_model_config,
            log_level=game_log_level,
            output_path=output_dir,
            enable_console_logging=False,
            enable_file_logging=output_dir is not None,
            performance_config=perf_config,
        )

        try:
            result = orchestrator.run_game()
            results["total_games"] += 1

            if result.winning_team.value == "village":
                results["village_wins"] += 1
                typer.echo(" Village wins!")
            else:
                results["werewolf_wins"] += 1
                typer.echo(" Werewolves win!")

            if output_dir and result.game_log:
                output_dir.mkdir(parents=True, exist_ok=True)
                log_path = output_dir / f"game_{i + 1:04d}.json"
                save_game_log(result.game_log, log_path)

        except Exception as e:
            typer.echo(f" Error: {e}")
            results["errors"] += 1

    typer.echo("\n" + "=" * 60)
    typer.echo("SIMULATION RESULTS")
    typer.echo("=" * 60)
    typer.echo(f"Total games: {results['total_games']}")
    typer.echo(f"Village wins: {results['village_wins']}")
    typer.echo(f"Werewolf wins: {results['werewolf_wins']}")
    typer.echo(f"Errors: {results['errors']}")

    if results["total_games"] > 0:
        village_rate = results["village_wins"] / results["total_games"] * 100
        wolf_rate = results["werewolf_wins"] / results["total_games"] * 100
        typer.echo(f"\nVillage win rate: {village_rate:.1f}%")
        typer.echo(f"Werewolf win rate: {wolf_rate:.1f}%")


@app.command()
def replay(
    log_file: Path = typer.Argument(
        ...,
        help="Path to game log file (JSON)",
    ),
    show_timeline: bool = typer.Option(
        False,
        "--timeline",
        "-t",
        help="Show detailed event timeline",
    ),
) -> None:
    """Replay and analyze a saved game log."""
    if not log_file.exists():
        typer.echo(f"Error: File not found: {log_file}", err=True)
        raise typer.Exit(code=1)

    try:
        game_log = load_game_log(log_file)
        print_game_summary(game_log)
        
        if show_timeline:
            typer.echo("")
            print_game_timeline(game_log)

    except Exception as e:
        typer.echo(f"Error loading game log: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def analyze(
    log_dir: Path = typer.Argument(
        ...,
        help="Directory containing game log files",
    ),
) -> None:
    """Analyze multiple game logs and show aggregate statistics."""
    if not log_dir.exists():
        typer.echo(f"Error: Directory not found: {log_dir}", err=True)
        raise typer.Exit(code=1)

    analyzer = MultiGameAnalyzer()
    count = analyzer.load_from_directory(log_dir)

    if count == 0:
        typer.echo("No valid game logs found in the directory.")
        raise typer.Exit(code=1)

    typer.echo(analyzer.format_report())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
