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


class AdvancedGameAnalyzer:
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
    
    def get_role_performance(self) -> dict[str, dict[str, Any]]:
        role_stats: dict[str, dict[str, Any]] = {}
        
        for game in self.games:
            winning_team = game.winning_team
            
            for player in game.players:
                role = player.role
                if role not in role_stats:
                    role_stats[role] = {
                        "total_games": 0,
                        "wins": 0,
                        "survivals": 0,
                        "first_deaths": 0,
                    }
                
                role_stats[role]["total_games"] += 1
                if player.is_alive:
                    role_stats[role]["survivals"] += 1
                
                is_village_role = player.alignment == "good"
                won = (winning_team == "village" and is_village_role) or \
                      (winning_team == "werewolf" and not is_village_role)
                if won:
                    role_stats[role]["wins"] += 1
        
        for role, stats in role_stats.items():
            total = stats["total_games"]
            if total > 0:
                stats["win_rate"] = stats["wins"] / total
                stats["survival_rate"] = stats["survivals"] / total
        
        return role_stats
    
    def get_voting_patterns(self) -> dict[str, Any]:
        patterns = {
            "correct_lynch_rate": 0,
            "mislynch_rate": 0,
            "total_lynches": 0,
            "wolf_lynch_count": 0,
            "villager_lynch_count": 0,
        }
        
        for game in self.games:
            player_map = {p.id: p for p in game.players}
            
            lynch_events = game.get_events_by_type("lynch")
            for event in lynch_events:
                patterns["total_lynches"] += 1
                target = player_map.get(event.target_id)
                if target:
                    if target.alignment == "werewolf":
                        patterns["wolf_lynch_count"] += 1
                    else:
                        patterns["villager_lynch_count"] += 1
        
        if patterns["total_lynches"] > 0:
            patterns["correct_lynch_rate"] = patterns["wolf_lynch_count"] / patterns["total_lynches"]
            patterns["mislynch_rate"] = patterns["villager_lynch_count"] / patterns["total_lynches"]
        
        return patterns
    
    def get_special_role_impact(self) -> dict[str, dict[str, Any]]:
        impact = {
            "seer": {"checks_per_game": 0, "found_wolves": 0},
            "witch": {"saves_per_game": 0, "poisons_per_game": 0, "save_success_rate": 0},
            "hunter": {"shots_per_game": 0, "wolf_kills": 0},
            "guard": {"protects_per_game": 0, "successful_blocks": 0},
        }
        
        total_games = len(self.games)
        if total_games == 0:
            return impact
        
        seer_checks = 0
        witch_saves = 0
        witch_poisons = 0
        hunter_shots = 0
        guard_protects = 0
        
        for game in self.games:
            stats = GameStatistics(game)
            seer_checks += stats.seer_checks
            witch_saves += stats.witch_saves
            witch_poisons += stats.witch_poisons
            hunter_shots += stats.hunter_shots
        
        impact["seer"]["checks_per_game"] = seer_checks / total_games
        impact["witch"]["saves_per_game"] = witch_saves / total_games
        impact["witch"]["poisons_per_game"] = witch_poisons / total_games
        impact["hunter"]["shots_per_game"] = hunter_shots / total_games
        
        return impact
    
    def get_game_duration_stats(self) -> dict[str, Any]:
        durations = []
        day_counts = []
        
        for game in self.games:
            day_counts.append(game.final_day)
            stats = GameStatistics(game)
            if stats.duration:
                durations.append(stats.duration.total_seconds())
        
        result = {
            "average_days": sum(day_counts) / len(day_counts) if day_counts else 0,
            "min_days": min(day_counts) if day_counts else 0,
            "max_days": max(day_counts) if day_counts else 0,
        }
        
        if durations:
            result["average_duration_seconds"] = sum(durations) / len(durations)
            result["min_duration_seconds"] = min(durations)
            result["max_duration_seconds"] = max(durations)
        
        return result
    
    def get_werewolf_strategy_analysis(self) -> dict[str, Any]:
        analysis = {
            "average_wolves_at_end": 0,
            "self_explode_count": 0,
            "wolf_caught_by_seer_rate": 0,
            "coordination_events": 0,
        }
        
        total_games = len(self.games)
        if total_games == 0:
            return analysis
        
        wolves_at_end = 0
        self_explodes = 0
        
        for game in self.games:
            wolf_survivors = [p for p in game.players if p.role == "werewolf" and p.is_alive]
            wolves_at_end += len(wolf_survivors)
            
            explode_events = game.get_events_by_type("wolf_self_explode")
            self_explodes += len(explode_events)
        
        analysis["average_wolves_at_end"] = wolves_at_end / total_games
        analysis["self_explode_count"] = self_explodes
        
        return analysis
    
    def format_detailed_report(self) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("ADVANCED GAME ANALYSIS REPORT")
        lines.append("=" * 70)
        lines.append(f"\nTotal Games Analyzed: {len(self.games)}")
        
        basic = MultiGameAnalyzer()
        basic.games = self.games
        basic_stats = basic.get_aggregate_statistics()
        
        lines.append(f"\n{'─' * 40}")
        lines.append("WIN RATES")
        lines.append(f"{'─' * 40}")
        lines.append(f"  Village: {basic_stats.get('village_win_rate', 0):.1%}")
        lines.append(f"  Werewolf: {basic_stats.get('werewolf_win_rate', 0):.1%}")
        
        duration = self.get_game_duration_stats()
        lines.append(f"\n{'─' * 40}")
        lines.append("GAME DURATION")
        lines.append(f"{'─' * 40}")
        lines.append(f"  Average Days: {duration['average_days']:.1f}")
        lines.append(f"  Range: {duration['min_days']} - {duration['max_days']} days")
        if duration.get('average_duration_seconds'):
            avg_min = duration['average_duration_seconds'] / 60
            lines.append(f"  Average Time: {avg_min:.1f} minutes")
        
        role_perf = self.get_role_performance()
        lines.append(f"\n{'─' * 40}")
        lines.append("ROLE PERFORMANCE")
        lines.append(f"{'─' * 40}")
        for role, stats in sorted(role_perf.items()):
            win_rate = stats.get('win_rate', 0) * 100
            surv_rate = stats.get('survival_rate', 0) * 100
            lines.append(f"  {role.title():15s}: Win {win_rate:5.1f}%  Survival {surv_rate:5.1f}%")
        
        voting = self.get_voting_patterns()
        lines.append(f"\n{'─' * 40}")
        lines.append("VOTING PATTERNS")
        lines.append(f"{'─' * 40}")
        lines.append(f"  Total Lynches: {voting['total_lynches']}")
        lines.append(f"  Correct Lynch Rate: {voting['correct_lynch_rate']:.1%}")
        lines.append(f"  Mislynch Rate: {voting['mislynch_rate']:.1%}")
        
        impact = self.get_special_role_impact()
        lines.append(f"\n{'─' * 40}")
        lines.append("SPECIAL ROLE IMPACT")
        lines.append(f"{'─' * 40}")
        lines.append(f"  Seer Checks/Game: {impact['seer']['checks_per_game']:.1f}")
        lines.append(f"  Witch Saves/Game: {impact['witch']['saves_per_game']:.1f}")
        lines.append(f"  Witch Poisons/Game: {impact['witch']['poisons_per_game']:.1f}")
        lines.append(f"  Hunter Shots/Game: {impact['hunter']['shots_per_game']:.1f}")
        
        wolf_strategy = self.get_werewolf_strategy_analysis()
        lines.append(f"\n{'─' * 40}")
        lines.append("WEREWOLF STRATEGY")
        lines.append(f"{'─' * 40}")
        lines.append(f"  Average Wolves at End: {wolf_strategy['average_wolves_at_end']:.1f}")
        lines.append(f"  Self-Explode Count: {wolf_strategy['self_explode_count']}")
        
        return "\n".join(lines)
    
    def export_to_csv(self, path: Union[str, Path]) -> None:
        import csv
        
        path = Path(path)
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'game_id', 'winning_team', 'final_day', 'role_set',
                'night_kills', 'lynches', 'witch_saves', 'witch_poisons',
                'hunter_shots', 'seer_checks'
            ])
            
            for game in self.games:
                stats = GameStatistics(game)
                writer.writerow([
                    game.game_id,
                    game.winning_team,
                    game.final_day,
                    game.role_set,
                    stats.night_kills,
                    stats.lynches,
                    stats.witch_saves,
                    stats.witch_poisons,
                    stats.hunter_shots,
                    stats.seer_checks,
                ])
    
    def export_player_data_to_csv(self, path: Union[str, Path]) -> None:
        import csv
        
        path = Path(path)
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'game_id', 'player_id', 'player_name', 'seat_number',
                'role', 'alignment', 'is_alive', 'is_sheriff', 'won'
            ])
            
            for game in self.games:
                for player in game.players:
                    is_village = player.alignment == "good"
                    won = (game.winning_team == "village" and is_village) or \
                          (game.winning_team == "werewolf" and not is_village)
                    
                    writer.writerow([
                        game.game_id,
                        player.id,
                        player.name,
                        player.seat_number,
                        player.role,
                        player.alignment,
                        player.is_alive,
                        player.is_sheriff,
                        won,
                    ])
