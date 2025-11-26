import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from autowerewolf.engine.roles import RoleSet, WinningTeam
from autowerewolf.io.analysis import (
    GameStatistics,
    MultiGameAnalyzer,
    analyze_game,
    format_player_summary,
    format_summary,
    format_timeline,
)
from autowerewolf.io.logging import GameLogLevel, create_game_logger
from autowerewolf.io.persistence import (
    EventLog,
    GameLog,
    PlayerLog,
    create_game_log,
    load_game_log,
    save_game_log,
)


@pytest.fixture
def sample_game_log() -> GameLog:
    game_log = create_game_log(
        game_id="test_game_001",
        config={"num_players": 12, "role_set": "A"},
        role_set=RoleSet.A,
        random_seed=42,
    )
    
    game_log.players = [
        PlayerLog(id="p1", name="Player 1", seat_number=1, role="werewolf", alignment="evil", is_alive=True),
        PlayerLog(id="p2", name="Player 2", seat_number=2, role="werewolf", alignment="evil", is_alive=True),
        PlayerLog(id="p3", name="Player 3", seat_number=3, role="werewolf", alignment="evil", is_alive=False),
        PlayerLog(id="p4", name="Player 4", seat_number=4, role="werewolf", alignment="evil", is_alive=False),
        PlayerLog(id="p5", name="Player 5", seat_number=5, role="villager", alignment="good", is_alive=True),
        PlayerLog(id="p6", name="Player 6", seat_number=6, role="villager", alignment="good", is_alive=False),
        PlayerLog(id="p7", name="Player 7", seat_number=7, role="villager", alignment="good", is_alive=False),
        PlayerLog(id="p8", name="Player 8", seat_number=8, role="villager", alignment="good", is_alive=False),
        PlayerLog(id="p9", name="Player 9", seat_number=9, role="seer", alignment="good", is_alive=True),
        PlayerLog(id="p10", name="Player 10", seat_number=10, role="witch", alignment="good", is_alive=False),
        PlayerLog(id="p11", name="Player 11", seat_number=11, role="hunter", alignment="good", is_alive=False),
        PlayerLog(id="p12", name="Player 12", seat_number=12, role="guard", alignment="good", is_alive=False),
    ]
    
    game_log.add_event("night_kill", day_number=1, phase="night", target_id="p6", public=False)
    game_log.add_event("seer_check", day_number=1, phase="night", actor_id="p9", target_id="p1", public=False)
    game_log.add_event("death_announcement", day_number=1, phase="day", target_id="p6")
    game_log.add_event("speech", day_number=1, phase="day", actor_id="p1", data={"content": "I am a villager."})
    game_log.add_event("vote_cast", day_number=1, phase="day", actor_id="p5", target_id="p3")
    game_log.add_event("lynch", day_number=1, phase="day", target_id="p3")
    
    game_log.add_event("night_kill", day_number=2, phase="night", target_id="p7", public=False)
    game_log.add_event("witch_save", day_number=2, phase="night", actor_id="p10", target_id="p7", public=False)
    
    game_log.set_result(WinningTeam.WEREWOLF, final_day=5)
    game_log.narration_log = ["Night 1 begins...", "Day 1 begins...", "The werewolves win!"]
    
    return game_log


class TestGameLog:
    def test_create_game_log(self):
        game_log = create_game_log(
            game_id="test_001",
            config={"num_players": 12},
            role_set=RoleSet.A,
            random_seed=123,
        )
        
        assert game_log.game_id == "test_001"
        assert game_log.role_set == "A"
        assert game_log.random_seed == 123
        assert game_log.winning_team == "none"
        assert len(game_log.events) == 0
        assert len(game_log.players) == 0

    def test_add_event(self, sample_game_log: GameLog):
        initial_count = len(sample_game_log.events)
        
        sample_game_log.add_event(
            event_type="speech",
            day_number=2,
            phase="day",
            actor_id="p5",
            data={"content": "Test speech"},
        )
        
        assert len(sample_game_log.events) == initial_count + 1
        assert sample_game_log.events[-1].event_type == "speech"
        assert sample_game_log.events[-1].data["content"] == "Test speech"

    def test_set_result(self, sample_game_log: GameLog):
        assert sample_game_log.winning_team == "werewolf"
        assert sample_game_log.final_day == 5
        assert sample_game_log.end_time is not None

    def test_get_public_events(self, sample_game_log: GameLog):
        public_events = sample_game_log.get_public_events()
        
        assert all(e.public for e in public_events)
        
        private_events = [e for e in sample_game_log.events if not e.public]
        assert len(private_events) > 0

    def test_get_events_by_type(self, sample_game_log: GameLog):
        speeches = sample_game_log.get_events_by_type("speech")
        assert all(e.event_type == "speech" for e in speeches)

    def test_get_events_for_day(self, sample_game_log: GameLog):
        day1_events = sample_game_log.get_events_for_day(1)
        assert all(e.day_number == 1 for e in day1_events)


class TestPersistence:
    def test_save_and_load_json(self, sample_game_log: GameLog):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            save_game_log(sample_game_log, temp_path)
            
            assert temp_path.exists()
            
            loaded_log = load_game_log(temp_path)
            
            assert loaded_log.game_id == sample_game_log.game_id
            assert loaded_log.winning_team == sample_game_log.winning_team
            assert loaded_log.final_day == sample_game_log.final_day
            assert len(loaded_log.players) == len(sample_game_log.players)
            assert len(loaded_log.events) == len(sample_game_log.events)
        finally:
            temp_path.unlink()


class TestGameLogger:
    def test_create_game_logger(self):
        logger = create_game_logger(
            game_id="test_logger",
            log_level=GameLogLevel.STANDARD,
        )
        
        assert logger.game_id == "test_logger"
        assert logger.log_level == GameLogLevel.STANDARD

    def test_log_game_start(self):
        logger = create_game_logger(
            game_id="test_logger",
            log_level=GameLogLevel.VERBOSE,
            enable_console=False,
        )
        
        from autowerewolf.engine.state import GameConfig
        config = GameConfig()
        players = [{"id": "p1", "name": "Player 1", "role": "werewolf"}]
        
        logger.log_game_start(config, players)
        
        entries = logger.get_entries(category="game")
        assert len(entries) == 1
        assert entries[0].message == "Game started"

    def test_log_death(self):
        logger = create_game_logger(
            game_id="test_logger",
            enable_console=False,
        )
        
        logger.log_death("p1", "Player 1", "werewolf", "lynched")
        
        entries = logger.get_entries(category="death")
        assert len(entries) == 1
        assert "Player 1" in entries[0].message

    def test_export_json(self):
        logger = create_game_logger(
            game_id="test_logger",
            enable_console=False,
        )
        
        logger.log_death("p1", "Player 1", "werewolf", "lynched")
        
        json_str = logger.export_json()
        data = json.loads(json_str)
        
        assert isinstance(data, list)
        assert len(data) == 1


class TestAnalysis:
    def test_analyze_game(self, sample_game_log: GameLog):
        stats = analyze_game(sample_game_log)
        
        assert isinstance(stats, GameStatistics)
        assert stats.total_events == len(sample_game_log.events)
        assert stats.night_kills == 2
        assert stats.lynches == 1
        assert stats.witch_saves == 1
        assert len(stats.survivors) == 4

    def test_format_summary(self, sample_game_log: GameLog):
        summary = format_summary(sample_game_log)
        
        assert "GAME SUMMARY" in summary
        assert "test_game_001" in summary
        assert "WEREWOLF" in summary.upper()

    def test_format_player_summary(self, sample_game_log: GameLog):
        player_summary = format_player_summary(sample_game_log)
        
        assert "PLAYER STATUS" in player_summary
        assert "Player 1" in player_summary
        assert "WEREWOLF" in player_summary.upper()

    def test_format_timeline(self, sample_game_log: GameLog):
        timeline = format_timeline(sample_game_log)
        
        assert "GAME TIMELINE" in timeline
        assert "Day 1" in timeline


class TestMultiGameAnalyzer:
    def test_add_game(self, sample_game_log: GameLog):
        analyzer = MultiGameAnalyzer()
        analyzer.add_game(sample_game_log)
        
        assert len(analyzer.games) == 1

    def test_aggregate_statistics(self, sample_game_log: GameLog):
        analyzer = MultiGameAnalyzer()
        analyzer.add_game(sample_game_log)
        
        village_log = create_game_log(
            game_id="village_win",
            config={},
            role_set=RoleSet.A,
        )
        village_log.set_result(WinningTeam.VILLAGE, final_day=3)
        village_log.players = sample_game_log.players.copy()
        analyzer.add_game(village_log)
        
        stats = analyzer.get_aggregate_statistics()
        
        assert stats["total_games"] == 2
        assert stats["village_wins"] == 1
        assert stats["werewolf_wins"] == 1
        assert stats["village_win_rate"] == 0.5

    def test_format_report(self, sample_game_log: GameLog):
        analyzer = MultiGameAnalyzer()
        analyzer.add_game(sample_game_log)
        
        report = analyzer.format_report()
        
        assert "MULTI-GAME ANALYSIS REPORT" in report
        assert "Total Games Analyzed" in report

    def test_load_from_directory(self, sample_game_log: GameLog):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            for i in range(3):
                log_path = temp_path / f"game_{i}.json"
                save_game_log(sample_game_log, log_path)
            
            analyzer = MultiGameAnalyzer()
            count = analyzer.load_from_directory(temp_path)
            
            assert count == 3
            assert len(analyzer.games) == 3
