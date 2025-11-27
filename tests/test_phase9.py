import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime
import tempfile
import json

from autowerewolf.agents.human import (
    HumanPlayerAgent,
    CLIInputHandler,
    WebInputHandler,
    create_human_agent,
)
from autowerewolf.agents.player_base import GameView
from autowerewolf.agents.schemas import (
    WerewolfNightOutput,
    SeerNightOutput,
    WitchNightOutput,
    GuardNightOutput,
    SpeechOutput,
    VoteOutput,
    SheriffDecisionOutput,
    BadgeDecisionOutput,
    HunterShootOutput,
)
from autowerewolf.engine.roles import Role
from autowerewolf.io.analysis import AdvancedGameAnalyzer, GameStatistics
from autowerewolf.io.persistence import GameLog, PlayerLog


class TestCLIInputHandler:
    def test_get_target_selection_valid(self, monkeypatch):
        handler = CLIInputHandler()
        monkeypatch.setattr("builtins.input", lambda _: "player1")
        
        result = handler.get_target_selection(
            "Choose:",
            ["player1", "player2"],
            allow_skip=False,
        )
        assert result == "player1"
    
    def test_get_target_selection_skip(self, monkeypatch):
        handler = CLIInputHandler()
        monkeypatch.setattr("builtins.input", lambda _: "skip")
        
        result = handler.get_target_selection(
            "Choose:",
            ["player1", "player2"],
            allow_skip=True,
        )
        assert result is None
    
    def test_get_yes_no_yes(self, monkeypatch):
        handler = CLIInputHandler()
        monkeypatch.setattr("builtins.input", lambda _: "y")
        
        result = handler.get_yes_no("Question?")
        assert result is True
    
    def test_get_yes_no_no(self, monkeypatch):
        handler = CLIInputHandler()
        monkeypatch.setattr("builtins.input", lambda _: "n")
        
        result = handler.get_yes_no("Question?")
        assert result is False
    
    def test_get_text_input(self, monkeypatch):
        handler = CLIInputHandler()
        monkeypatch.setattr("builtins.input", lambda _: "test input")
        
        result = handler.get_text_input("Enter text:")
        assert result == "test input"


class TestWebInputHandler:
    def test_set_and_get_input(self):
        handler = WebInputHandler()
        handler.set_input({"target": "player1"})
        
        result = handler._wait_for_input_sync(timeout=0.1)
        assert result == {"target": "player1"}
    
    def test_get_target_selection(self):
        handler = WebInputHandler()
        handler._pending_input = {"target": "player1"}
        
        result = handler.get_target_selection("Choose:", ["player1", "player2"])
        assert result == "player1"
    
    def test_get_yes_no(self):
        handler = WebInputHandler()
        handler._pending_input = {"value": True}
        
        result = handler.get_yes_no("Question?")
        assert result is True
    
    def test_get_text_input(self):
        handler = WebInputHandler()
        handler._pending_input = {"text": "hello"}
        
        result = handler.get_text_input("Enter:")
        assert result == "hello"


class TestHumanPlayerAgent:
    def create_game_view(self, role: Role = Role.VILLAGER) -> GameView:
        return GameView(
            player_id="p1",
            player_name="TestPlayer",
            role=role,
            phase="night",
            day_number=1,
            alive_players=[
                {"id": "p1", "name": "TestPlayer", "seat_number": 1, "is_alive": True},
                {"id": "p2", "name": "Player2", "seat_number": 2, "is_alive": True},
            ],
            public_history=[],
            private_info={},
            action_context={"valid_targets": ["p2"]},
        )
    
    def test_create_human_agent(self):
        agent = create_human_agent(
            player_id="p1",
            player_name="Test",
            role=Role.VILLAGER,
        )
        assert isinstance(agent, HumanPlayerAgent)
        assert agent.player_id == "p1"
        assert agent.role == Role.VILLAGER
    
    def test_werewolf_night_action(self, monkeypatch):
        handler = MagicMock()
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Wolf",
            role=Role.WEREWOLF,
            input_handler=handler,
        )
        
        game_view = self.create_game_view(Role.WEREWOLF)
        result = agent.decide_night_action(game_view)
        
        assert isinstance(result, WerewolfNightOutput)
        assert result.kill_target_id == "p2"
    
    def test_seer_night_action(self, monkeypatch):
        handler = MagicMock()
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Seer",
            role=Role.SEER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view(Role.SEER)
        result = agent.decide_night_action(game_view)
        
        assert isinstance(result, SeerNightOutput)
        assert result.check_target_id == "p2"
    
    def test_witch_night_action(self, monkeypatch):
        handler = MagicMock()
        handler.get_yes_no.side_effect = [True, False]
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Witch",
            role=Role.WITCH,
            input_handler=handler,
        )
        
        game_view = self.create_game_view(Role.WITCH)
        game_view.private_info = {
            "attack_target": {"id": "p2", "name": "Player2"},
            "has_cure": True,
            "has_poison": True,
        }
        
        result = agent.decide_night_action(game_view)
        
        assert isinstance(result, WitchNightOutput)
        assert result.use_cure is True
        assert result.use_poison is False
    
    def test_guard_night_action(self, monkeypatch):
        handler = MagicMock()
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Guard",
            role=Role.GUARD,
            input_handler=handler,
        )
        
        game_view = self.create_game_view(Role.GUARD)
        result = agent.decide_night_action(game_view)
        
        assert isinstance(result, GuardNightOutput)
        assert result.protect_target_id == "p2"
    
    def test_day_speech(self, monkeypatch):
        handler = MagicMock()
        handler.get_text_input.return_value = "I am a villager"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Test",
            role=Role.VILLAGER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view()
        result = agent.decide_day_speech(game_view)
        
        assert isinstance(result, SpeechOutput)
        assert result.content == "I am a villager"
    
    def test_vote(self, monkeypatch):
        handler = MagicMock()
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Test",
            role=Role.VILLAGER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view()
        result = agent.decide_vote(game_view)
        
        assert isinstance(result, VoteOutput)
        assert result.target_player_id == "p2"
    
    def test_sheriff_run(self, monkeypatch):
        handler = MagicMock()
        handler.get_yes_no.return_value = True
        handler.get_text_input.return_value = "Vote for me!"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Test",
            role=Role.VILLAGER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view()
        result = agent.decide_sheriff_run(game_view)
        
        assert isinstance(result, SheriffDecisionOutput)
        assert result.run_for_sheriff is True
    
    def test_badge_pass(self, monkeypatch):
        handler = MagicMock()
        handler.get_yes_no.return_value = True
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Test",
            role=Role.VILLAGER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view()
        result = agent.decide_badge_pass(game_view)
        
        assert isinstance(result, BadgeDecisionOutput)
        assert result.action == "pass"
        assert result.target_player_id == "p2"
    
    def test_hunter_shot(self, monkeypatch):
        handler = MagicMock()
        handler.get_yes_no.return_value = True
        handler.get_target_selection.return_value = "p2"
        
        agent = HumanPlayerAgent(
            player_id="p1",
            player_name="Hunter",
            role=Role.HUNTER,
            input_handler=handler,
        )
        
        game_view = self.create_game_view(Role.HUNTER)
        result = agent.decide_hunter_shot(game_view)
        
        assert isinstance(result, HunterShootOutput)
        assert result.shoot is True
        assert result.target_player_id == "p2"


class TestAdvancedGameAnalyzer:
    def create_sample_game_log(self) -> GameLog:
        return GameLog(
            game_id="test_game",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            config={},
            role_set="A",
            winning_team="village",
            final_day=3,
            players=[
                PlayerLog(
                    id="p1", name="Player1", seat_number=1,
                    role="werewolf", alignment="werewolf", is_alive=False
                ),
                PlayerLog(
                    id="p2", name="Player2", seat_number=2,
                    role="villager", alignment="good", is_alive=True
                ),
                PlayerLog(
                    id="p3", name="Player3", seat_number=3,
                    role="seer", alignment="good", is_alive=True
                ),
            ],
            events=[],
        )
    
    def test_analyzer_initialization(self):
        analyzer = AdvancedGameAnalyzer()
        assert len(analyzer.games) == 0
    
    def test_add_game(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        assert len(analyzer.games) == 1
    
    def test_get_role_performance(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        
        perf = analyzer.get_role_performance()
        
        assert "werewolf" in perf
        assert "villager" in perf
        assert "seer" in perf
        assert perf["villager"]["survivals"] == 1
        assert perf["werewolf"]["survivals"] == 0
    
    def test_get_game_duration_stats(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        
        stats = analyzer.get_game_duration_stats()
        
        assert stats["average_days"] == 3
        assert stats["min_days"] == 3
        assert stats["max_days"] == 3
    
    def test_format_detailed_report(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        
        report = analyzer.format_detailed_report()
        
        assert "ADVANCED GAME ANALYSIS REPORT" in report
        assert "Total Games Analyzed: 1" in report
        assert "WIN RATES" in report
        assert "ROLE PERFORMANCE" in report
    
    def test_export_to_csv(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        
        try:
            analyzer.export_to_csv(path)
            assert path.exists()
            content = path.read_text()
            assert "game_id" in content
            assert "test_game" in content
        finally:
            path.unlink()
    
    def test_export_player_data_to_csv(self):
        analyzer = AdvancedGameAnalyzer()
        game = self.create_sample_game_log()
        analyzer.add_game(game)
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        
        try:
            analyzer.export_player_data_to_csv(path)
            assert path.exists()
            content = path.read_text()
            assert "player_id" in content
            assert "Player1" in content
        finally:
            path.unlink()


class TestWebServer:
    def test_web_module_imports(self):
        from autowerewolf.web.server import app, run_server
        from autowerewolf.web.session import session_manager, GameSession
        
        assert app is not None
        assert run_server is not None
        assert session_manager is not None
        assert GameSession is not None
    
    def test_game_manager_initialization(self):
        from autowerewolf.web.session import session_manager
        
        # Session manager is a singleton
        assert hasattr(session_manager, '_sessions')
        assert isinstance(session_manager._sessions, dict)
