"""Comprehensive unit tests for the Werewolf game rules engine.

Tests cover:
- Role assignment and validation
- Night kill + witch save + guard interactions
- Seer checks and result storage
- Sheriff election, badge pass/tear, and vote weights
- Hunter shot logic and edge cases
- Village Idiot lynch + reveal behavior
- Win condition evaluation for all end states
"""

import pytest

from autowerewolf.engine import (
    # Enums
    Role,
    Alignment,
    Phase,
    WinningTeam,
    WinMode,
    RoleSet,
    EventType,
    ActionType,
    # Models
    Player,
    GameConfig,
    RuleVariants,
    GameState,
    # Functions
    get_role_composition,
    create_game_state,
    validate_role_composition,
    resolve_night_actions,
    resolve_sheriff_election,
    resolve_vote,
    resolve_lynch,
    resolve_badge_action,
    resolve_hunter_shot,
    resolve_wolf_self_explode,
    check_win_condition,
    update_win_condition,
    advance_to_day,
    advance_to_night,
    get_valid_wolf_targets,
    get_valid_guard_targets,
    get_valid_vote_targets,
    get_valid_hunter_targets,
    can_witch_cure,
    can_witch_poison,
    can_hunter_shoot,
)
from autowerewolf.engine.state import (
    WolfKillAction,
    SeerCheckAction,
    WitchCureAction,
    WitchPoisonAction,
    GuardProtectAction,
    HunterShootAction,
    PassBadgeAction,
    TearBadgeAction,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> GameConfig:
    """Create a default game configuration."""
    return GameConfig(
        num_players=12,
        role_set=RoleSet.A,
        random_seed=42,
    )


@pytest.fixture
def config_set_b() -> GameConfig:
    """Create a game configuration with role set B."""
    return GameConfig(
        num_players=12,
        role_set=RoleSet.B,
        random_seed=42,
    )


@pytest.fixture
def game_state(default_config: GameConfig) -> GameState:
    """Create a default game state with players."""
    return create_game_state(default_config)


@pytest.fixture
def game_state_set_b(config_set_b: GameConfig) -> GameState:
    """Create a game state with role set B."""
    return create_game_state(config_set_b)


def create_test_game_state(
    roles: list[Role],
    config: GameConfig | None = None,
) -> GameState:
    """Create a game state with specific roles for testing."""
    if config is None:
        config = GameConfig(random_seed=42)
    
    players = []
    for i, role in enumerate(roles, start=1):
        player = Player(
            id=f"P{i:02d}",
            name=f"Player {i}",
            role=role,
            seat_number=i,
        )
        players.append(player)
    
    return GameState(
        config=config,
        day_number=0,
        phase=Phase.NIGHT,
        players=players,
    )


# =============================================================================
# Test Role Composition
# =============================================================================


class TestRoleComposition:
    """Tests for role assignment and validation."""
    
    def test_role_set_a_composition(self):
        """Test role set A contains correct roles."""
        roles = get_role_composition(RoleSet.A)
        
        assert len(roles) == 12
        assert roles.count(Role.WEREWOLF) == 4
        assert roles.count(Role.VILLAGER) == 4
        assert Role.SEER in roles
        assert Role.WITCH in roles
        assert Role.HUNTER in roles
        assert Role.GUARD in roles
        assert Role.VILLAGE_IDIOT not in roles
    
    def test_role_set_b_composition(self):
        """Test role set B contains correct roles."""
        roles = get_role_composition(RoleSet.B)
        
        assert len(roles) == 12
        assert roles.count(Role.WEREWOLF) == 4
        assert roles.count(Role.VILLAGER) == 4
        assert Role.SEER in roles
        assert Role.WITCH in roles
        assert Role.HUNTER in roles
        assert Role.VILLAGE_IDIOT in roles
        assert Role.GUARD not in roles
    
    def test_create_game_state_assigns_all_roles(self, game_state: GameState):
        """Test that game state creation assigns all expected roles."""
        assert len(game_state.players) == 12
        
        roles = [p.role for p in game_state.players]
        assert validate_role_composition(game_state.players, RoleSet.A)
    
    def test_create_game_state_set_b(self, game_state_set_b: GameState):
        """Test game state creation with role set B."""
        assert validate_role_composition(game_state_set_b.players, RoleSet.B)
    
    def test_create_game_state_with_seed_is_deterministic(self, default_config: GameConfig):
        """Test that the same seed produces the same role assignment."""
        state1 = create_game_state(default_config)
        state2 = create_game_state(default_config)
        
        roles1 = [(p.seat_number, p.role) for p in state1.players]
        roles2 = [(p.seat_number, p.role) for p in state2.players]
        
        assert roles1 == roles2
    
    def test_alignment_set_correctly(self, game_state: GameState):
        """Test that alignment is set correctly for all players."""
        for player in game_state.players:
            if player.role == Role.WEREWOLF:
                assert player.alignment == Alignment.WEREWOLF
            else:
                assert player.alignment == Alignment.GOOD


# =============================================================================
# Test Night Resolution
# =============================================================================


class TestNightResolution:
    """Tests for night action resolution."""
    
    def test_wolf_kill_no_protection(self):
        """Test basic wolf kill without any protection."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        wolf_id = state.get_werewolves()[0].id
        villager_id = state.get_villagers()[0].id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=villager_id)
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert not villager.is_alive
    
    def test_wolf_kill_with_guard_protection(self):
        """Test wolf kill blocked by guard protection."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        wolf_id = state.get_werewolves()[0].id
        villager_id = state.get_villagers()[0].id
        guard_id = state.get_players_by_role(Role.GUARD)[0].id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=villager_id),
            GuardProtectAction(actor_id=guard_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert villager.is_alive  # Protected by guard
    
    def test_wolf_kill_with_witch_save(self):
        """Test wolf kill blocked by witch cure."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        wolf_id = state.get_werewolves()[0].id
        villager_id = state.get_villagers()[0].id
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        
        # Set wolf kill target so witch knows who to save
        state.wolf_kill_target_id = villager_id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=villager_id),
            WitchCureAction(actor_id=witch_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert villager.is_alive  # Saved by witch
        
        # Witch should have used cure
        witch = new_state.get_player(witch_id)
        assert witch is not None
        assert not witch.witch_has_cure
    
    def test_same_guard_same_save_kills(self):
        """Test that double protection (guard + witch save) kills the target."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(same_guard_same_save_kills=True)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        wolf_id = state.get_werewolves()[0].id
        villager_id = state.get_villagers()[0].id
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        guard_id = state.get_players_by_role(Role.GUARD)[0].id
        
        state.wolf_kill_target_id = villager_id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=villager_id),
            GuardProtectAction(actor_id=guard_id, target_id=villager_id),
            WitchCureAction(actor_id=witch_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert not villager.is_alive  # Dies due to same_guard_same_save_kills rule
    
    def test_same_guard_same_save_disabled(self):
        """Test that double protection saves when rule is disabled."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(same_guard_same_save_kills=False)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        wolf_id = state.get_werewolves()[0].id
        villager_id = state.get_villagers()[0].id
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        guard_id = state.get_players_by_role(Role.GUARD)[0].id
        
        state.wolf_kill_target_id = villager_id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=villager_id),
            GuardProtectAction(actor_id=guard_id, target_id=villager_id),
            WitchCureAction(actor_id=witch_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert villager.is_alive  # Survives when rule disabled
    
    def test_guard_cannot_protect_same_twice(self):
        """Test that guard cannot protect the same player two nights in a row."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        guard = state.get_players_by_role(Role.GUARD)[0]
        villager_id = state.get_villagers()[0].id
        
        # Simulate guard protected this villager last night
        guard.guard_last_protected = villager_id
        
        valid_targets = get_valid_guard_targets(state, guard.id)
        assert villager_id not in valid_targets
    
    def test_witch_poison(self):
        """Test witch poison kills target."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        villager_id = state.get_villagers()[0].id
        
        actions = [
            WitchPoisonAction(actor_id=witch_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        villager = new_state.get_player(villager_id)
        assert villager is not None
        assert not villager.is_alive
        
        witch = new_state.get_player(witch_id)
        assert witch is not None
        assert not witch.witch_has_poison


# =============================================================================
# Test Seer Checks
# =============================================================================


class TestSeerChecks:
    """Tests for Seer check mechanics."""
    
    def test_seer_check_werewolf(self):
        """Test Seer checking a werewolf."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        seer_id = state.get_players_by_role(Role.SEER)[0].id
        wolf_id = state.get_werewolves()[0].id
        
        actions = [
            SeerCheckAction(actor_id=seer_id, target_id=wolf_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        seer = new_state.get_player(seer_id)
        assert seer is not None
        assert len(seer.seer_checks) == 1
        assert seer.seer_checks[0] == (wolf_id, Alignment.WEREWOLF)
    
    def test_seer_check_good_player(self):
        """Test Seer checking a good player."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        seer_id = state.get_players_by_role(Role.SEER)[0].id
        villager_id = state.get_villagers()[0].id
        
        actions = [
            SeerCheckAction(actor_id=seer_id, target_id=villager_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        seer = new_state.get_player(seer_id)
        assert seer is not None
        assert len(seer.seer_checks) == 1
        assert seer.seer_checks[0] == (villager_id, Alignment.GOOD)
    
    def test_seer_check_creates_private_event(self):
        """Test that Seer check creates a private event."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        seer_id = state.get_players_by_role(Role.SEER)[0].id
        wolf_id = state.get_werewolves()[0].id
        
        actions = [
            SeerCheckAction(actor_id=seer_id, target_id=wolf_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        seer_events = [e for e in events if e.event_type == EventType.SEER_CHECK]
        assert len(seer_events) == 1
        assert not seer_events[0].public
        assert seer_events[0].visible_to == [seer_id]


# =============================================================================
# Test Sheriff Mechanics
# =============================================================================


class TestSheriffMechanics:
    """Tests for Sheriff election and badge mechanics."""
    
    def test_sheriff_election_clear_winner(self):
        """Test sheriff election with a clear winner."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        candidates = [state.players[0].id, state.players[1].id]
        votes = {
            state.players[2].id: candidates[0],
            state.players[3].id: candidates[0],
            state.players[4].id: candidates[1],
        }
        
        new_state, events = resolve_sheriff_election(state, candidates, votes)
        
        assert new_state.sheriff_id == candidates[0]
        assert new_state.sheriff_election_complete
        
        sheriff = new_state.get_player(candidates[0])
        assert sheriff is not None
        assert sheriff.is_sheriff
    
    def test_sheriff_vote_weight(self):
        """Test that sheriff has 1.5x vote weight."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        # Make player 0 the sheriff
        state.sheriff_id = state.players[0].id
        state.players[0].is_sheriff = True
        
        target_a = state.players[1].id
        target_b = state.players[2].id
        
        # Sheriff votes for A, two others vote for B
        votes = {
            state.players[0].id: target_a,  # Sheriff vote (1.5)
            state.players[3].id: target_b,  # Normal vote (1.0)
            state.players[4].id: target_b,  # Normal vote (1.0)
        }
        
        new_state, result = resolve_vote(state, votes)
        
        # Target B has 2.0 votes, Target A has 1.5 - B should be lynched
        assert result.lynched_player_id == target_b
        assert result.vote_counts[target_a] == 1.5
        assert result.vote_counts[target_b] == 2.0
    
    def test_badge_pass(self):
        """Test sheriff passing the badge on death."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        sheriff_id = state.players[0].id
        successor_id = state.players[1].id
        
        state.sheriff_id = sheriff_id
        state.players[0].is_sheriff = True
        
        action = PassBadgeAction(actor_id=sheriff_id, target_id=successor_id)
        new_state, events = resolve_badge_action(state, action)
        
        assert new_state.sheriff_id == successor_id
        
        successor = new_state.get_player(successor_id)
        assert successor is not None
        assert successor.is_sheriff
    
    def test_badge_tear(self):
        """Test sheriff tearing the badge."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        sheriff_id = state.players[0].id
        state.sheriff_id = sheriff_id
        state.players[0].is_sheriff = True
        
        action = TearBadgeAction(actor_id=sheriff_id, target_id=None)
        new_state, events = resolve_badge_action(state, action)
        
        assert new_state.sheriff_id is None
        assert new_state.badge_torn
    
    def test_torn_badge_no_vote_bonus(self):
        """Test that torn badge removes vote bonus."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        # Player 0 was sheriff but badge is torn
        state.players[0].is_sheriff = True
        state.badge_torn = True
        
        target_a = state.players[1].id
        target_b = state.players[2].id
        
        votes = {
            state.players[0].id: target_a,  # Former sheriff (now 1.0)
            state.players[3].id: target_b,
            state.players[4].id: target_b,
        }
        
        new_state, result = resolve_vote(state, votes)
        
        # All votes are 1.0, so B wins with 2 votes
        assert result.lynched_player_id == target_b
        assert result.vote_counts[target_a] == 1.0


# =============================================================================
# Test Hunter Mechanics
# =============================================================================


class TestHunterMechanics:
    """Tests for Hunter shooting mechanics."""
    
    def test_hunter_can_shoot_on_lynch(self):
        """Test Hunter can shoot when lynched."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        hunter_id = state.get_players_by_role(Role.HUNTER)[0].id
        target_id = state.get_werewolves()[0].id
        
        action = HunterShootAction(actor_id=hunter_id, target_id=target_id)
        new_state, events = resolve_hunter_shot(state, action)
        
        target = new_state.get_player(target_id)
        assert target is not None
        assert not target.is_alive
    
    def test_hunter_cannot_shoot_if_poisoned(self):
        """Test Hunter cannot shoot if killed by witch poison."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        hunter = state.get_players_by_role(Role.HUNTER)[0]
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        
        # Poison the hunter
        actions = [
            WitchPoisonAction(actor_id=witch_id, target_id=hunter.id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        hunter = new_state.get_player(hunter.id)
        assert hunter is not None
        assert not hunter.is_alive
        assert not hunter.hunter_can_shoot  # Cannot shoot because poisoned
    
    def test_hunter_cannot_shoot_if_flag_false(self):
        """Test Hunter shot does nothing if hunter_can_shoot is False."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        hunter = state.get_players_by_role(Role.HUNTER)[0]
        target_id = state.get_werewolves()[0].id
        
        # Disable hunter shooting
        hunter.hunter_can_shoot = False
        
        action = HunterShootAction(actor_id=hunter.id, target_id=target_id)
        new_state, events = resolve_hunter_shot(state, action)
        
        target = new_state.get_player(target_id)
        assert target is not None
        assert target.is_alive  # Should not be killed


# =============================================================================
# Test Village Idiot Mechanics
# =============================================================================


class TestVillageIdiotMechanics:
    """Tests for Village Idiot mechanics."""
    
    def test_village_idiot_survives_first_lynch(self):
        """Test Village Idiot survives first lynch and reveals."""
        config = GameConfig(role_set=RoleSet.B, random_seed=42)
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGE_IDIOT
        ]
        state = create_test_game_state(roles, config)
        
        idiot_id = state.get_players_by_role(Role.VILLAGE_IDIOT)[0].id
        
        new_state, events = resolve_lynch(state, idiot_id)
        
        idiot = new_state.get_player(idiot_id)
        assert idiot is not None
        assert idiot.is_alive  # Survives
        assert idiot.village_idiot_revealed  # Revealed
        
        # Check for reveal event
        reveal_events = [e for e in events if e.event_type == EventType.VILLAGE_IDIOT_REVEAL]
        assert len(reveal_events) == 1
    
    def test_village_idiot_loses_vote_after_reveal(self):
        """Test Village Idiot loses voting power after reveal."""
        config = GameConfig(role_set=RoleSet.B, random_seed=42)
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGE_IDIOT
        ]
        state = create_test_game_state(roles, config)
        
        idiot = state.get_players_by_role(Role.VILLAGE_IDIOT)[0]
        idiot.village_idiot_revealed = True
        
        target_a = state.players[0].id
        target_b = state.players[1].id
        
        votes = {
            idiot.id: target_a,  # Should not count
            state.players[2].id: target_b,
        }
        
        new_state, result = resolve_vote(state, votes)
        
        # Village Idiot's vote should not be counted
        assert target_a not in result.vote_counts or result.vote_counts[target_a] == 0
        assert result.vote_counts[target_b] == 1.0
    
    def test_village_idiot_dies_at_night(self):
        """Test Village Idiot dies normally if killed at night."""
        config = GameConfig(role_set=RoleSet.B, random_seed=42)
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGE_IDIOT
        ]
        state = create_test_game_state(roles, config)
        
        wolf_id = state.get_werewolves()[0].id
        idiot_id = state.get_players_by_role(Role.VILLAGE_IDIOT)[0].id
        
        actions = [
            WolfKillAction(actor_id=wolf_id, target_id=idiot_id),
        ]
        
        new_state, events = resolve_night_actions(state, actions)
        
        idiot = new_state.get_player(idiot_id)
        assert idiot is not None
        assert not idiot.is_alive  # Dies normally at night


# =============================================================================
# Test Win Conditions
# =============================================================================


class TestWinConditions:
    """Tests for win condition evaluation."""
    
    def test_village_wins_all_wolves_dead(self):
        """Test village wins when all werewolves are dead."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        # Kill all werewolves
        for wolf in state.get_werewolves():
            wolf.is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.VILLAGE
    
    def test_wolves_win_all_villagers_dead_side_elimination(self):
        """Test werewolves win when all villagers are dead (side elimination)."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(win_mode=WinMode.SIDE_ELIMINATION)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        # Kill all villagers
        for villager in state.get_villagers():
            villager.is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.WEREWOLF
    
    def test_wolves_win_all_specials_dead_side_elimination(self):
        """Test werewolves win when all special roles are dead (side elimination)."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(win_mode=WinMode.SIDE_ELIMINATION)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        # Kill all special roles
        for player in state.get_special_roles():
            player.is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.WEREWOLF
    
    def test_game_continues_some_villagers_dead(self):
        """Test game continues when only some villagers are dead."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        # Kill some villagers but not all
        state.get_villagers()[0].is_alive = False
        state.get_villagers()[1].is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.NONE
    
    def test_wolves_win_city_elimination(self):
        """Test werewolves win in city elimination mode."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(win_mode=WinMode.CITY_ELIMINATION)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        # Kill all good players
        for player in state.get_players_by_alignment(Alignment.GOOD):
            player.is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.WEREWOLF
    
    def test_city_elimination_continues_with_some_good_alive(self):
        """Test city elimination continues when some good players alive."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(win_mode=WinMode.CITY_ELIMINATION)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        
        # Kill all villagers but keep special roles alive
        for villager in state.get_villagers():
            villager.is_alive = False
        
        result = check_win_condition(state)
        assert result == WinningTeam.NONE  # Game continues


# =============================================================================
# Test Wolf Self-Explode
# =============================================================================


class TestWolfSelfExplode:
    """Tests for werewolf self-explosion mechanics."""
    
    def test_wolf_self_explode(self):
        """Test werewolf can self-explode."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        state.phase = Phase.DAY
        
        wolf_id = state.get_werewolves()[0].id
        
        new_state, events = resolve_wolf_self_explode(state, wolf_id)
        
        wolf = new_state.get_player(wolf_id)
        assert wolf is not None
        assert not wolf.is_alive
    
    def test_wolf_self_explode_disabled(self):
        """Test wolf cannot self-explode when disabled."""
        config = GameConfig(
            random_seed=42,
            rule_variants=RuleVariants(allow_wolf_self_explode=False)
        )
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles, config)
        state.phase = Phase.DAY
        
        wolf_id = state.get_werewolves()[0].id
        
        new_state, events = resolve_wolf_self_explode(state, wolf_id)
        
        wolf = new_state.get_player(wolf_id)
        assert wolf is not None
        assert wolf.is_alive  # Should not die when disabled


# =============================================================================
# Test Phase Transitions
# =============================================================================


class TestPhaseTransitions:
    """Tests for phase transition logic."""
    
    def test_advance_to_day(self):
        """Test advancing from night to day."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        state.day_number = 0
        state.phase = Phase.NIGHT
        
        new_state = advance_to_day(state)
        
        assert new_state.phase == Phase.DAY
        assert new_state.day_number == 1
    
    def test_advance_to_night(self):
        """Test advancing from day to night."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        state.day_number = 1
        state.phase = Phase.DAY
        
        new_state = advance_to_night(state)
        
        assert new_state.phase == Phase.NIGHT
        assert new_state.day_number == 1  # Day number stays same until next day


# =============================================================================
# Test Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_get_valid_wolf_targets(self):
        """Test valid wolf targets include all alive players."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        targets = get_valid_wolf_targets(state, include_self_knife=False)
        
        # Should include all non-werewolf alive players
        assert len(targets) == 8  # 4 villagers + 4 special roles
        
        for wolf in state.get_werewolves():
            assert wolf.id not in targets
    
    def test_get_valid_wolf_targets_with_self_knife(self):
        """Test valid wolf targets include werewolves when self-knife enabled."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        targets = get_valid_wolf_targets(state, include_self_knife=True)
        
        # Should include all alive players including werewolves
        assert len(targets) == 12
    
    def test_get_valid_vote_targets(self):
        """Test valid vote targets exclude self."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        voter_id = state.players[0].id
        targets = get_valid_vote_targets(state, voter_id)
        
        assert voter_id not in targets
        assert len(targets) == 11  # All except self
    
    def test_can_witch_cure_wolf_target(self):
        """Test witch can cure the wolf's target."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        target_id = state.get_villagers()[0].id
        
        state.wolf_kill_target_id = target_id
        
        assert can_witch_cure(state, witch_id, target_id)
    
    def test_cannot_witch_cure_wrong_target(self):
        """Test witch cannot cure a different target."""
        roles = [Role.WEREWOLF] * 4 + [Role.VILLAGER] * 4 + [
            Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD
        ]
        state = create_test_game_state(roles)
        
        witch_id = state.get_players_by_role(Role.WITCH)[0].id
        target_id = state.get_villagers()[0].id
        wrong_target_id = state.get_villagers()[1].id
        
        state.wolf_kill_target_id = target_id
        
        assert not can_witch_cure(state, witch_id, wrong_target_id)


# =============================================================================
# Test GameState Helper Methods
# =============================================================================


class TestGameStateHelpers:
    """Tests for GameState helper methods."""
    
    def test_get_player(self, game_state: GameState):
        """Test getting player by ID."""
        player = game_state.players[0]
        found = game_state.get_player(player.id)
        
        assert found is not None
        assert found.id == player.id
    
    def test_get_player_not_found(self, game_state: GameState):
        """Test getting non-existent player."""
        found = game_state.get_player("nonexistent")
        assert found is None
    
    def test_get_alive_players(self, game_state: GameState):
        """Test getting all alive players."""
        alive = game_state.get_alive_players()
        assert len(alive) == 12  # All alive initially
        
        # Kill one player
        game_state.players[0].is_alive = False
        alive = game_state.get_alive_players()
        assert len(alive) == 11
    
    def test_get_players_by_role(self, game_state: GameState):
        """Test getting players by role."""
        wolves = game_state.get_players_by_role(Role.WEREWOLF)
        assert len(wolves) == 4
        
        for wolf in wolves:
            assert wolf.role == Role.WEREWOLF
    
    def test_get_sheriff(self, game_state: GameState):
        """Test getting sheriff."""
        assert game_state.get_sheriff() is None
        
        game_state.sheriff_id = game_state.players[0].id
        game_state.players[0].is_sheriff = True
        
        sheriff = game_state.get_sheriff()
        assert sheriff is not None
        assert sheriff.id == game_state.players[0].id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
