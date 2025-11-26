from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Union

from autowerewolf.io.persistence import GameLog, load_game_log


class GameStatistics:
    def __init__(self, game_log: GameLog):
        self.game_log = game_log
        self._compute_statistics()

    def _compute_statistics(self) -> None:
        self.total_events = len(self.game_log.events)
        self.total_deaths = sum(
            1 for e in self.game_log.events
            if e.event_type in ("night_kill", "lynch", "hunter_shot", "witch_poison")
        )
        
        self.night_kills = len(self.game_log.get_events_by_type("night_kill"))
        self.lynches = len(self.game_log.get_events_by_type("lynch"))
        self.hunter_shots = len(self.game_log.get_events_by_type("hunter_shot"))
        self.witch_saves = len(self.game_log.get_events_by_type("witch_save"))
        self.witch_poisons = len(self.game_log.get_events_by_type("witch_poison"))
        self.seer_checks = len(self.game_log.get_events_by_type("seer_check"))
        
        self.speeches = len(self.game_log.get_events_by_type("speech"))
        self.votes = len(self.game_log.get_events_by_type("vote_cast"))
        
        if self.game_log.start_time and self.game_log.end_time:
            self.duration = self.game_log.end_time - self.game_log.start_time
        else:
            self.duration = None
        
        self.survivors = [p for p in self.game_log.players if p.is_alive]
        self.dead_players = [p for p in self.game_log.players if not p.is_alive]
        
        self.werewolf_survivors = [p for p in self.survivors if p.role == "werewolf"]
        self.villager_survivors = [p for p in self.survivors if p.role == "villager"]
        self.special_role_survivors = [
            p for p in self.survivors 
            if p.role not in ("werewolf", "villager")
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "total_deaths": self.total_deaths,
            "night_kills": self.night_kills,
            "lynches": self.lynches,
            "hunter_shots": self.hunter_shots,
            "witch_saves": self.witch_saves,
            "witch_poisons": self.witch_poisons,
            "seer_checks": self.seer_checks,
            "speeches": self.speeches,
            "votes": self.votes,
            "duration_seconds": self.duration.total_seconds() if self.duration else None,
            "survivors_count": len(self.survivors),
            "werewolf_survivors": len(self.werewolf_survivors),
            "villager_survivors": len(self.villager_survivors),
            "special_role_survivors": len(self.special_role_survivors),
        }


def analyze_game(game_log: GameLog) -> GameStatistics:
    return GameStatistics(game_log)


def format_player_summary(game_log: GameLog) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("PLAYER STATUS")
    lines.append("=" * 60)
    
    for player in sorted(game_log.players, key=lambda p: p.seat_number):
        status = "ALIVE" if player.is_alive else "DEAD"
        sheriff = " [Sheriff]" if player.is_sheriff else ""
        lines.append(
            f"  Seat {player.seat_number:2d}: {player.name:12s} - "
            f"{player.role.upper():12s} ({player.alignment}) - {status}{sheriff}"
        )
    
    return "\n".join(lines)


def format_timeline(game_log: GameLog) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("GAME TIMELINE")
    lines.append("=" * 60)
    
    player_map = {p.id: p.name for p in game_log.players}
    
    current_day = -1
    current_phase = ""
    
    for event in game_log.events:
        if event.day_number != current_day or event.phase != current_phase:
            current_day = event.day_number
            current_phase = event.phase
            lines.append(f"\n--- Day {current_day} - {current_phase.upper()} ---")
        
        actor = player_map.get(event.actor_id, event.actor_id) if event.actor_id else None
        target = player_map.get(event.target_id, event.target_id) if event.target_id else None
        
        desc = _format_event_description(event.event_type, actor, target, event.data)
        if desc:
            lines.append(f"  {desc}")
    
    return "\n".join(lines)


def _format_event_description(
    event_type: str,
    actor: Optional[str],
    target: Optional[str],
    data: dict[str, Any],
) -> str:
    descriptions = {
        "game_start": "Game started",
        "game_end": f"Game ended",
        "night_kill": f"{target} was killed by werewolves" if target else "Night kill",
        "witch_save": f"Witch saved {target}" if target else "Witch saved someone",
        "witch_poison": f"Witch poisoned {target}" if target else "Witch used poison",
        "seer_check": f"Seer checked {target}" if target else "Seer checked someone",
        "guard_protect": f"Guard protected {target}" if target else "Guard protected someone",
        "death_announcement": f"{target} was found dead" if target else "Death announced",
        "speech": f"{actor}: {data.get('content', '')[:50]}..." if actor and data.get('content') else f"{actor} spoke",
        "vote_cast": f"{actor} voted for {target}" if actor and target else "Vote cast",
        "lynch": f"{target} was lynched" if target else "Lynch",
        "sheriff_elected": f"{target} elected as Sheriff" if target else "Sheriff elected",
        "hunter_shot": f"{actor} shot {target}" if actor and target else "Hunter shot",
        "badge_pass": f"Badge passed to {target}" if target else "Badge passed",
        "badge_tear": "Badge was torn",
        "village_idiot_reveal": f"{target} revealed as Village Idiot" if target else "Village Idiot revealed",
        "wolf_self_explode": f"{actor} self-exploded" if actor else "Werewolf self-exploded",
    }
    return descriptions.get(event_type, "")


def format_summary(game_log: GameLog) -> str:
    stats = analyze_game(game_log)
    
    lines = []
    lines.append("=" * 60)
    lines.append("GAME SUMMARY")
    lines.append("=" * 60)
    lines.append(f"\nGame ID: {game_log.game_id}")
    lines.append(f"Role Set: {game_log.role_set}")
    if game_log.random_seed:
        lines.append(f"Seed: {game_log.random_seed}")
    
    lines.append(f"\nWinner: {game_log.winning_team.upper()}")
    lines.append(f"Final Day: {game_log.final_day}")
    
    if stats.duration:
        minutes = int(stats.duration.total_seconds() // 60)
        seconds = int(stats.duration.total_seconds() % 60)
        lines.append(f"Duration: {minutes}m {seconds}s")
    
    lines.append(f"\n--- Statistics ---")
    lines.append(f"Night Kills: {stats.night_kills}")
    lines.append(f"Lynches: {stats.lynches}")
    lines.append(f"Witch Saves: {stats.witch_saves}")
    lines.append(f"Witch Poisons: {stats.witch_poisons}")
    lines.append(f"Hunter Shots: {stats.hunter_shots}")
    lines.append(f"Seer Checks: {stats.seer_checks}")
    lines.append(f"Total Speeches: {stats.speeches}")
    lines.append(f"Total Votes: {stats.votes}")
    
    lines.append(f"\n--- Survivors ({len(stats.survivors)}) ---")
    for p in stats.survivors:
        lines.append(f"  {p.name} ({p.role})")
    
    return "\n".join(lines)


def print_game_summary(game_log: GameLog) -> None:
    print(format_summary(game_log))
    print()
    print(format_player_summary(game_log))


def print_game_timeline(game_log: GameLog) -> None:
    print(format_timeline(game_log))


def replay_game(path: Union[str, Path]) -> None:
    game_log = load_game_log(path)
    print_game_summary(game_log)
    print()
    print_game_timeline(game_log)


class MultiGameAnalyzer:
    def __init__(self):
        self.games: list[GameLog] = []
    
    def add_game(self, game_log: GameLog) -> None:
        self.games.append(game_log)
    
    def load_from_directory(self, directory: Union[str, Path]) -> int:
        directory = Path(directory)
        count = 0
        for file_path in directory.glob("*.json"):
            try:
                game_log = load_game_log(file_path)
                self.games.append(game_log)
                count += 1
            except Exception:
                continue
        return count
    
    def get_aggregate_statistics(self) -> dict[str, Any]:
        if not self.games:
            return {}
        
        village_wins = sum(1 for g in self.games if g.winning_team == "village")
        werewolf_wins = sum(1 for g in self.games if g.winning_team == "werewolf")
        
        total_days = sum(g.final_day for g in self.games)
        avg_days = total_days / len(self.games) if self.games else 0
        
        role_survival_counts: dict[str, tuple[int, int]] = {}
        for game in self.games:
            for player in game.players:
                if player.role not in role_survival_counts:
                    role_survival_counts[player.role] = (0, 0)
                alive, total = role_survival_counts[player.role]
                role_survival_counts[player.role] = (
                    alive + (1 if player.is_alive else 0),
                    total + 1,
                )
        
        role_survival_rates = {
            role: alive / total if total > 0 else 0
            for role, (alive, total) in role_survival_counts.items()
        }
        
        witch_save_rate = 0
        witch_poison_rate = 0
        witch_games = 0
        for game in self.games:
            stats = analyze_game(game)
            if any(p.role == "witch" for p in game.players):
                witch_games += 1
                witch_save_rate += 1 if stats.witch_saves > 0 else 0
                witch_poison_rate += 1 if stats.witch_poisons > 0 else 0
        
        if witch_games > 0:
            witch_save_rate /= witch_games
            witch_poison_rate /= witch_games
        
        return {
            "total_games": len(self.games),
            "village_wins": village_wins,
            "werewolf_wins": werewolf_wins,
            "village_win_rate": village_wins / len(self.games) if self.games else 0,
            "werewolf_win_rate": werewolf_wins / len(self.games) if self.games else 0,
            "average_game_days": avg_days,
            "role_survival_rates": role_survival_rates,
            "witch_save_usage_rate": witch_save_rate,
            "witch_poison_usage_rate": witch_poison_rate,
        }
    
    def format_report(self) -> str:
        stats = self.get_aggregate_statistics()
        if not stats:
            return "No games to analyze."
        
        lines = []
        lines.append("=" * 60)
        lines.append("MULTI-GAME ANALYSIS REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nTotal Games Analyzed: {stats['total_games']}")
        lines.append(f"\nWin Rates:")
        lines.append(f"  Village: {stats['village_win_rate']:.1%} ({stats['village_wins']} wins)")
        lines.append(f"  Werewolf: {stats['werewolf_win_rate']:.1%} ({stats['werewolf_wins']} wins)")
        
        lines.append(f"\nAverage Game Length: {stats['average_game_days']:.1f} days")
        
        lines.append(f"\nRole Survival Rates:")
        for role, rate in sorted(stats['role_survival_rates'].items()):
            lines.append(f"  {role.title():15s}: {rate:.1%}")
        
        lines.append(f"\nWitch Usage:")
        lines.append(f"  Cure Used: {stats['witch_save_usage_rate']:.1%}")
        lines.append(f"  Poison Used: {stats['witch_poison_usage_rate']:.1%}")
        
        return "\n".join(lines)


def analyze_multiple_games(directory: Union[str, Path]) -> MultiGameAnalyzer:
    analyzer = MultiGameAnalyzer()
    analyzer.load_from_directory(directory)
    return analyzer
