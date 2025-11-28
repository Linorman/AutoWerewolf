import json
import logging
from pathlib import Path
from typing import Optional

import typer

from autowerewolf.agents.prompts import Language, set_language
from autowerewolf.config.game_rules import (
    get_config_template,
    load_game_config,
    save_default_config,
)
from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig, OutputCorrectorConfig
from autowerewolf.config.performance import (
    LanguageSetting,
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
    AdvancedGameAnalyzer,
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
    config_path: Optional[Path] = None,
) -> GameConfig:
    """Create game configuration from file or defaults.
    
    Args:
        role_set: Role set override ("A" or "B")
        seed: Random seed override
        config_path: Path to configuration file
        
    Returns:
        GameConfig instance
    """
    if config_path and config_path.exists():
        game_config = load_game_config(config_path)
    else:
        game_config = load_game_config()
    
    if role_set:
        rs = RoleSet.A if role_set.upper() == "A" else RoleSet.B
        game_config = GameConfig(
            num_players=game_config.num_players,
            role_set=rs,
            rule_variants=game_config.rule_variants,
            random_seed=seed if seed is not None else game_config.random_seed,
        )
    elif seed is not None:
        game_config = GameConfig(
            num_players=game_config.num_players,
            role_set=game_config.role_set,
            rule_variants=game_config.rule_variants,
            random_seed=seed,
        )
    
    return game_config


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
    enable_corrector: bool = True,
    corrector_max_retries: int = 2,
    corrector_backend: Optional[str] = None,
    corrector_model: Optional[str] = None,
    corrector_api_base: Optional[str] = None,
    corrector_api_key: Optional[str] = None,
    corrector_ollama_url: Optional[str] = None,
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

    corrector_override = None
    if corrector_backend or corrector_model:
        cb = corrector_backend or backend
        corrector_backend_enum = ModelBackend.OLLAMA if cb.lower() == "ollama" else ModelBackend.API
        corrector_override = ModelConfig(
            backend=corrector_backend_enum,
            model_name=corrector_model or model_name,
            api_base=corrector_api_base or api_base,
            api_key=corrector_api_key or api_key,
            ollama_base_url=corrector_ollama_url or ollama_base_url,
            temperature=0.3,
            max_tokens=512,
        )

    output_corrector = OutputCorrectorConfig(
        enabled=enable_corrector,
        max_retries=corrector_max_retries,
        model_config_override=corrector_override,
    )

    return AgentModelConfig(default=default_config, output_corrector=output_corrector)


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
        help="Path to game rules configuration file (YAML/JSON)",
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
    language: str = typer.Option(
        "en",
        "--language",
        "--lang",
        help="Language for prompts and game content: 'en' (English) or 'zh' (Chinese)",
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
    enable_corrector: bool = typer.Option(
        True,
        "--corrector/--no-corrector",
        help="Enable output corrector to fix malformed model outputs",
    ),
    corrector_retries: int = typer.Option(
        2,
        "--corrector-retries",
        help="Maximum correction attempts (1-5)",
        min=1,
        max=5,
    ),
    corrector_backend: Optional[str] = typer.Option(
        None,
        "--corrector-backend",
        help="Corrector model backend (if different from main model)",
    ),
    corrector_model: Optional[str] = typer.Option(
        None,
        "--corrector-model",
        help="Corrector model name (if different from main model)",
    ),
    corrector_api_base: Optional[str] = typer.Option(
        None,
        "--corrector-api-base",
        help="Corrector API base URL",
    ),
    corrector_api_key: Optional[str] = typer.Option(
        None,
        "--corrector-api-key",
        help="Corrector API key",
    ),
    corrector_ollama_url: Optional[str] = typer.Option(
        None,
        "--corrector-ollama-url",
        help="Corrector Ollama endpoint URL",
    ),
) -> None:
    """Run a single Werewolf game with LLM agents."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set global language for prompts
    lang_setting = LanguageSetting(language.lower())
    set_language(Language(language.lower()))
    
    typer.echo("AutoWerewolf - Starting game...\n")

    game_config = create_game_config(role_set=role_set, seed=seed, config_path=config)

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
            enable_corrector=enable_corrector,
            corrector_max_retries=corrector_retries,
            corrector_backend=corrector_backend,
            corrector_model=corrector_model,
            corrector_api_base=corrector_api_base,
            corrector_api_key=corrector_api_key,
            corrector_ollama_url=corrector_ollama_url,
        )

    try:
        perf_config = get_performance_preset(performance_preset)
        perf_config = PerformanceConfig(
            verbosity=perf_config.verbosity,
            language=lang_setting,
            enable_batching=enable_batching or perf_config.enable_batching,
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
    
    default_logs_dir = Path.cwd() / "logs"
    output_path = output.parent if output else default_logs_dir

    orchestrator = GameOrchestrator(
        config=game_config,
        agent_models=agent_model_config,
        log_level=game_log_level,
        output_path=output_path,
        enable_console_logging=True,
        enable_file_logging=True,  # Always enable file logging
        performance_config=perf_config,
    )

    lang_display = "Chinese" if lang_setting == LanguageSetting.ZH else "English"
    typer.echo("Initializing game...")
    typer.echo(f"  Role Set: {game_config.role_set.value}")
    typer.echo(f"  Language: {lang_display}")
    typer.echo(f"  Backend: {agent_model_config.default.backend.value}")
    typer.echo(f"  Model: {agent_model_config.default.model_name}")
    typer.echo(f"  Output Corrector: {'Enabled' if agent_model_config.output_corrector.enabled else 'Disabled'}")
    if seed:
        typer.echo(f"  Seed: {seed}")
    typer.echo("")

    try:
        result = orchestrator.run_game()
        print_game_result(result)

        # Save game log - use custom output path or default logs folder
        if result.game_log:
            if output:
                save_game_log(result.game_log, output)
                typer.echo(f"\nGame log saved to: {output}")
            else:
                # Save to default logs folder with timestamped filename
                default_logs_dir = Path.cwd() / "logs"
                default_logs_dir.mkdir(parents=True, exist_ok=True)
                default_log_path = default_logs_dir / f"logs-{orchestrator._game_id}.json"
                save_game_log(result.game_log, default_log_path)
                typer.echo(f"\nGame log saved to: {default_log_path}")

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
    language: str = typer.Option(
        "en",
        "--language",
        "--lang",
        help="Language for prompts and game content: 'en' (English) or 'zh' (Chinese)",
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
    # Set global language for prompts
    lang_setting = LanguageSetting(language.lower())
    set_language(Language(language.lower()))
    
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

    base_perf_config = get_performance_preset("simulation" if fast_mode else "standard")
    perf_config = PerformanceConfig(
        verbosity=base_perf_config.verbosity,
        language=lang_setting,
        enable_batching=base_perf_config.enable_batching,
        batch_size=base_perf_config.batch_size,
        skip_narration=base_perf_config.skip_narration,
        compact_logs=base_perf_config.compact_logs,
        max_speech_length=base_perf_config.max_speech_length,
        max_reasoning_length=base_perf_config.max_reasoning_length,
    )
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
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed analysis report",
    ),
    export_csv: Optional[Path] = typer.Option(
        None,
        "--export",
        "-e",
        help="Export statistics to CSV file",
    ),
) -> None:
    """Analyze multiple game logs and show aggregate statistics."""
    if not log_dir.exists():
        typer.echo(f"Error: Directory not found: {log_dir}", err=True)
        raise typer.Exit(code=1)

    if detailed:
        analyzer = AdvancedGameAnalyzer()
        count = analyzer.load_from_directory(log_dir)
        
        if count == 0:
            typer.echo("No valid game logs found in the directory.")
            raise typer.Exit(code=1)
        
        typer.echo(analyzer.format_detailed_report())
        
        if export_csv:
            analyzer.export_to_csv(export_csv)
            typer.echo(f"\nStatistics exported to: {export_csv}")
    else:
        analyzer = MultiGameAnalyzer()
        count = analyzer.load_from_directory(log_dir)
        
        if count == 0:
            typer.echo("No valid game logs found in the directory.")
            raise typer.Exit(code=1)
        
        typer.echo(analyzer.format_report())


@app.command()
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind the server to",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to run the server on",
    ),
    model_config: Optional[Path] = typer.Option(
        None,
        "--model-config",
        "-m",
        help="Path to model configuration YAML file (default: autowerewolf_models.yaml)",
    ),
    game_config: Optional[Path] = typer.Option(
        None,
        "--game-config",
        "-g",
        help="Path to game configuration YAML file (default: autowerewolf_config.yaml)",
    ),
) -> None:
    """Start the web UI server."""
    try:
        from autowerewolf.web.server import run_server
    except ImportError:
        typer.echo("Error: Web dependencies not installed. Run: pip install autowerewolf[web]", err=True)
        raise typer.Exit(code=1)
    
    display_host = "localhost" if host == "0.0.0.0" else host
    typer.echo(f"\n🐺 AutoWerewolf Web Server Starting...")
    typer.echo(f"=" * 50)
    typer.echo(f"  🎮 UI Page:    http://{display_host}:{port}/ui")
    typer.echo(f"  📡 API Base:   http://{display_host}:{port}/api")
    typer.echo(f"  📖 API Docs:   http://{display_host}:{port}/docs")
    typer.echo(f"=" * 50)
    
    if model_config:
        typer.echo(f"  📁 Model Config: {model_config}")
    else:
        typer.echo(f"  📁 Model Config: (auto-detect or defaults)")
    
    if game_config:
        typer.echo(f"  🎲 Game Config:  {game_config}")
    else:
        typer.echo(f"  🎲 Game Config:  (auto-detect or defaults)")
    
    typer.echo(f"=" * 50)
    typer.echo("Press Ctrl+C to stop\n")
    
    run_server(
        host=host, 
        port=port,
        model_config_path=str(model_config) if model_config else None,
        game_config_path=str(game_config) if game_config else None,
    )


@app.command(name="init-config")
def init_config(
    output: Path = typer.Option(
        Path("autowerewolf_config.yaml"),
        "--output",
        "-o",
        help="Output path for the configuration file",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration file",
    ),
    template: bool = typer.Option(
        False,
        "--template",
        "-t",
        help="Generate template with comments (recommended for first-time setup)",
    ),
) -> None:
    """Generate a default game rules configuration file.
    
    This creates a YAML configuration file with all default rule variants.
    You can customize the rules by editing this file and passing it to
    run-game with the --config option.
    """
    if output.exists() and not force:
        typer.echo(f"Error: File already exists: {output}", err=True)
        typer.echo("Use --force to overwrite.", err=True)
        raise typer.Exit(code=1)
    
    try:
        if template:
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w", encoding="utf-8") as f:
                f.write(get_config_template())
        else:
            save_default_config(output)
        
        typer.echo(f"Configuration file created: {output}")
        typer.echo("\nYou can now customize the rules and run a game with:")
        typer.echo(f"  autowerewolf run-game --config {output}")
        
    except Exception as e:
        typer.echo(f"Error creating configuration file: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def play(
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
    role_set: str = typer.Option(
        "A",
        "--role-set",
        "-r",
        help="Role set to use: 'A' (Guard) or 'B' (Village Idiot)",
    ),
    seat: int = typer.Option(
        1,
        "--seat",
        "-s",
        help="Your seat number (1-12)",
        min=1,
        max=12,
    ),
    name: str = typer.Option(
        "Human Player",
        "--name",
        "-n",
        help="Your player name",
    ),
) -> None:
    """Play a game as a human player with LLM opponents."""
    typer.echo("AutoWerewolf - Human Player Mode\n")
    typer.echo(f"You will be playing as {name} at seat {seat}")
    typer.echo("Other players will be controlled by LLM agents.\n")
    
    game_config = create_game_config(role_set=role_set, seed=None)
    agent_model_config = create_model_config(
        backend=backend,
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        ollama_base_url=ollama_base_url,
    )
    
    typer.echo(f"Backend: {backend}")
    typer.echo(f"Model: {model_name}")
    typer.echo(f"Role Set: {role_set}\n")
    
    typer.echo("Note: Human player mode integration requires game orchestrator modifications.")
    typer.echo("For now, please use the web UI with 'autowerewolf serve' for human play.\n")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
