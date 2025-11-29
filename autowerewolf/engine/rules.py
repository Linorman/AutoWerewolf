import random
from copy import deepcopy
from typing import Optional

from .roles import (
    Alignment,
    Phase,
    Role,
    RoleSet,
    WinMode,
    WinningTeam,
    get_role_composition,
)
from .state import (
    Action,
    ActionType,
    BadgePassEvent,
    BadgeTearEvent,
    DeathAnnouncementEvent,
    Event,
    EventType,
    GameConfig,
    GameState,
    GuardProtectAction,
    GuardProtectEvent,
    HunterShotEvent,
    HunterShootAction,
    LynchEvent,
    NightKillEvent,
    NightResolution,
    Player,
    SeerCheckAction,
    SeerCheckEvent,
    SheriffElectedEvent,
    VillageIdiotRevealEvent,
    VoteCastEvent,
    VoteResult,
    VoteResultEvent,
    WitchCureAction,
    WitchPoisonAction,
    WitchPoisonEvent,
    WitchSaveEvent,
    WolfKillAction,
    WolfSelfExplodeEvent,
)

def create_game_state(config: GameConfig, player_names: Optional[list[str]] = None) -> GameState:
    """Create a new game state with assigned roles.
    
    Args:
        config: Game configuration
        player_names: Optional list of player names. If not provided, 
                     defaults to "Player 1" through "Player 12".
    
    Returns:
        Initialized GameState with players and roles assigned
    """
    # Set random seed if provided
    if config.random_seed is not None:
        random.seed(config.random_seed)
    
    # Generate default player names if not provided
    if player_names is None:
        player_names = [f"Player {i}" for i in range(1, config.num_players + 1)]
    
    if len(player_names) != config.num_players:
        raise ValueError(f"Expected {config.num_players} player names, got {len(player_names)}")
    
    # Get role composition and shuffle
    roles = get_role_composition(config.role_set)
    random.shuffle(roles)
    
    # Create players
    players = []
    for i, (name, role) in enumerate(zip(player_names, roles), start=1):
        player = Player(
            name=name,
            role=role,
            seat_number=i,
        )
        players.append(player)
    
    # Create initial game state
    state = GameState(
        config=config,
        day_number=0,  # Night 1 is day_number=0
        phase=Phase.NIGHT,
        players=players,
    )
    
    return state


def validate_role_composition(players: list[Player], role_set: RoleSet) -> bool:
    """Validate that the player roles match the expected composition.
    
    Args:
        players: List of players
        role_set: Expected role set (A or B)
    
    Returns:
        True if composition is valid, False otherwise
    """
    if len(players) != 12:
        return False
    
    expected_roles = get_role_composition(role_set)
    actual_roles = [p.role for p in players]
    
    return sorted(expected_roles) == sorted(actual_roles)


def get_night_action_order() -> list[Role]:
    """Get the order in which night actions are resolved.
    
    Returns:
        List of roles in action order
    """
    return [
        Role.GUARD,        # Guard protects first
        Role.WEREWOLF,     # Werewolves choose kill target
        Role.WITCH,        # Witch decides cure/poison
        Role.SEER,         # Seer checks (can be anywhere in order)
    ]


def resolve_night_actions(
    state: GameState,
    actions: list[Action],
) -> tuple[GameState, list[Event]]:
    """Resolve all night actions and update game state.
    
    Args:
        state: Current game state
        actions: List of night actions from all players
    
    Returns:
        Tuple of (new game state, list of events)
    """
    # Create a copy of state to modify
    new_state = deepcopy(state)
    events: list[Event] = []
    
    # Extract relevant actions by type
    wolf_kill_action = None
    witch_cure_action = None
    witch_poison_action = None
    guard_action = None
    seer_action = None
    
    for action in actions:
        if action.action_type == ActionType.WOLF_KILL:
            wolf_kill_action = action
        elif action.action_type == ActionType.WITCH_CURE:
            witch_cure_action = action
        elif action.action_type == ActionType.WITCH_POISON:
            witch_poison_action = action
        elif action.action_type == ActionType.GUARD_PROTECT:
            guard_action = action
        elif action.action_type == ActionType.SEER_CHECK:
            seer_action = action
    
    # Track protected player
    protected_player_id: Optional[str] = None
    
    # 1. Guard protection
    if guard_action and guard_action.target_id:
        guard = new_state.get_player(guard_action.actor_id)
        if guard and guard.is_alive and guard.role == Role.GUARD:
            # Validate guard target (cannot protect same person twice in a row)
            if guard.guard_last_protected != guard_action.target_id:
                protected_player_id = guard_action.target_id
                guard.guard_last_protected = guard_action.target_id
                
                events.append(GuardProtectEvent(
                    day_number=state.day_number,
                    phase=Phase.NIGHT,
                    actor_id=guard_action.actor_id,
                    target_id=guard_action.target_id,
                    visible_to=[guard_action.actor_id],
                ))
    
    # 2. Werewolf kill target
    wolf_target_id: Optional[str] = None
    if wolf_kill_action and wolf_kill_action.target_id:
        wolf_target_id = wolf_kill_action.target_id
        
        # Record kill attempt event (private to werewolves)
        werewolf_ids = [p.id for p in new_state.get_werewolves()]
        events.append(NightKillEvent(
            day_number=state.day_number,
            phase=Phase.NIGHT,
            actor_id=wolf_kill_action.actor_id,
            target_id=wolf_target_id,
            visible_to=werewolf_ids,
        ))
    
    # 3. Witch actions
    witch_saved_target: Optional[str] = None
    witch_poisoned_target: Optional[str] = None
    
    witch = None
    for p in new_state.players:
        if p.role == Role.WITCH and p.is_alive:
            witch = p
            break
    
    if witch:
        # Check if witch can use cure
        if witch_cure_action and witch.witch_has_cure and wolf_target_id:
            cure_target = witch_cure_action.target_id
            
            # Validate cure: can only cure the wolf's target
            if cure_target == wolf_target_id:
                # Check self-heal rules
                is_night_1 = state.day_number == 0
                can_self_heal = (
                    (is_night_1 and state.config.rule_variants.witch_can_self_heal_n1) or
                    (not is_night_1 and state.config.rule_variants.witch_can_self_heal)
                )
                
                if cure_target != witch.id or can_self_heal:
                    witch_saved_target = cure_target
                    witch.witch_has_cure = False
                    
                    events.append(WitchSaveEvent(
                        day_number=state.day_number,
                        phase=Phase.NIGHT,
                        actor_id=witch.id,
                        target_id=cure_target,
                        visible_to=[witch.id],
                    ))
        
        # Check if witch can use poison (and hasn't used cure if both_potions is False)
        if witch_poison_action and witch.witch_has_poison:
            can_use_poison = (
                state.config.rule_variants.witch_can_use_both_potions or
                witch_cure_action is None
            )
            
            if can_use_poison and witch_poison_action.target_id:
                witch_poisoned_target = witch_poison_action.target_id
                witch.witch_has_poison = False
                
                events.append(WitchPoisonEvent(
                    day_number=state.day_number,
                    phase=Phase.NIGHT,
                    actor_id=witch.id,
                    target_id=witch_poisoned_target,
                    visible_to=[witch.id],
                ))
    
    # 4. Seer check
    if seer_action and seer_action.target_id:
        seer = new_state.get_player(seer_action.actor_id)
        if seer and seer.is_alive and seer.role == Role.SEER:
            check_target = new_state.get_player(seer_action.target_id)
            if check_target:
                check_result = check_target.alignment
                seer.seer_checks.append((check_target.id, check_result))
                
                events.append(SeerCheckEvent(
                    day_number=state.day_number,
                    phase=Phase.NIGHT,
                    actor_id=seer.id,
                    target_id=check_target.id,
                    data={"result": check_result.value},
                    visible_to=[seer.id],
                ))
    
    # 5. Resolve deaths
    dead_player_ids: list[str] = []
    
    # Wolf kill resolution
    if wolf_target_id:
        target = new_state.get_player(wolf_target_id)
        if target and target.is_alive:
            # Check if protected by guard
            is_protected = (protected_player_id == wolf_target_id)
            
            # Check if saved by witch
            is_saved = (witch_saved_target == wolf_target_id)
            
            # Handle same_guard_same_save rule
            if is_protected and is_saved and state.config.rule_variants.same_guard_same_save_kills:
                # Double protection kills the target
                target.is_alive = False
                dead_player_ids.append(wolf_target_id)
                # Handle sheriff death
                # if target.is_sheriff:
                #     target.is_sheriff = False
                #     new_state.sheriff_id = None
            elif is_protected or is_saved:
                # Protected or saved - survives
                pass
            else:
                # Not protected and not saved - dies
                target.is_alive = False
                dead_player_ids.append(wolf_target_id)
                
                # Check if target is hunter
                if target.role == Role.HUNTER:
                    # If also poisoned, check poisoned rule; otherwise check night_killed rule
                    if witch_poisoned_target == wolf_target_id:
                        if not state.config.rule_variants.hunter_can_shoot_if_poisoned:
                            target.hunter_can_shoot = False
                    elif not state.config.rule_variants.hunter_can_shoot_if_night_killed:
                        target.hunter_can_shoot = False
    
    # Witch poison resolution
    if witch_poisoned_target:
        target = new_state.get_player(witch_poisoned_target)
        if target and target.is_alive:
            target.is_alive = False
            dead_player_ids.append(witch_poisoned_target)
            
            # Hunter can only shoot if poisoned when rule allows it
            if target.role == Role.HUNTER:
                if not state.config.rule_variants.hunter_can_shoot_if_poisoned:
                    target.hunter_can_shoot = False
            
    
    # Update state
    new_state.wolf_kill_target_id = wolf_target_id
    
    return new_state, events


def resolve_sheriff_election(
    state: GameState,
    candidates: list[str],
    votes: dict[str, str],
) -> tuple[GameState, list[Event]]:
    """Resolve sheriff election.
    
    Args:
        state: Current game state
        candidates: List of player IDs running for sheriff
        votes: Dict mapping voter_id -> candidate_id
    
    Returns:
        Tuple of (new game state, list of events)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    if not candidates:
        # No one ran for sheriff
        new_state.sheriff_election_complete = True
        return new_state, events
    
    # Count votes
    vote_counts: dict[str, int] = {c: 0 for c in candidates}
    for voter_id, candidate_id in votes.items():
        if candidate_id in vote_counts:
            vote_counts[candidate_id] += 1
    
    # Find winner(s)
    max_votes = max(vote_counts.values()) if vote_counts else 0
    winners = [c for c, v in vote_counts.items() if v == max_votes]
    
    if len(winners) == 1:
        # Clear winner
        sheriff_id = winners[0]
        sheriff = new_state.get_player(sheriff_id)
        if sheriff:
            sheriff.is_sheriff = True
            new_state.sheriff_id = sheriff_id
            
            events.append(SheriffElectedEvent(
                day_number=state.day_number,
                phase=Phase.SHERIFF_ELECTION,
                target_id=sheriff_id,
                data={"vote_counts": vote_counts},
            ))
    else:
        # Tie - need to handle (could be PK or random)
        # For now, choose randomly among tied candidates
        sheriff_id = random.choice(winners)
        sheriff = new_state.get_player(sheriff_id)
        if sheriff:
            sheriff.is_sheriff = True
            new_state.sheriff_id = sheriff_id
            
            events.append(SheriffElectedEvent(
                day_number=state.day_number,
                phase=Phase.SHERIFF_ELECTION,
                target_id=sheriff_id,
                data={"vote_counts": vote_counts, "was_tie": True},
            ))
    
    new_state.sheriff_election_complete = True
    return new_state, events


def resolve_vote(
    state: GameState,
    votes: dict[str, str],
) -> tuple[GameState, VoteResult]:
    """Resolve a day vote.
    
    Args:
        state: Current game state
        votes: Dict mapping voter_id -> target_id
    
    Returns:
        Tuple of (new game state, vote result)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    # Count votes with sheriff weight
    vote_counts: dict[str, float] = {}
    
    for voter_id, target_id in votes.items():
        voter = new_state.get_player(voter_id)
        if voter and voter.is_alive:
            # Village Idiot who has revealed loses voting power
            if voter.role == Role.VILLAGE_IDIOT and voter.village_idiot_revealed:
                continue
            
            weight = 1.0
            if voter.is_sheriff and not state.badge_torn:
                weight = state.config.rule_variants.sheriff_vote_weight
            
            if target_id not in vote_counts:
                vote_counts[target_id] = 0.0
            vote_counts[target_id] += weight
            
            events.append(VoteCastEvent(
                day_number=state.day_number,
                phase=Phase.DAY,
                actor_id=voter_id,
                target_id=target_id,
                data={"weight": weight},
            ))
    
    # Find highest vote count
    if not vote_counts:
        result = VoteResult(
            votes=votes,
            vote_counts=vote_counts,
            lynched_player_id=None,
            is_tie=False,
            events=events,
        )
        return new_state, result
    
    max_votes = max(vote_counts.values())
    top_targets = [t for t, v in vote_counts.items() if v == max_votes]
    
    is_tie = len(top_targets) > 1
    lynched_player_id: Optional[str] = None
    
    if not is_tie:
        lynched_player_id = top_targets[0]
    else:
        # Tie handling - typically no lynch or PK
        # For now, we do no lynch on tie
        pass
    
    events.append(VoteResultEvent(
        day_number=state.day_number,
        phase=Phase.DAY,
        data={
            "vote_counts": vote_counts,
            "is_tie": is_tie,
            "lynched_player_id": lynched_player_id,
        },
    ))
    
    result = VoteResult(
        votes=votes,
        vote_counts=vote_counts,
        lynched_player_id=lynched_player_id,
        is_tie=is_tie,
        events=events,
    )
    
    return new_state, result


def resolve_lynch(
    state: GameState,
    lynched_player_id: str,
) -> tuple[GameState, list[Event]]:
    """Resolve a lynch (player voted out).
    
    Args:
        state: Current game state
        lynched_player_id: ID of player being lynched
    
    Returns:
        Tuple of (new game state, list of events)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    player = new_state.get_player(lynched_player_id)
    if not player or not player.is_alive:
        return new_state, events
    
    # Check for Village Idiot
    if player.role == Role.VILLAGE_IDIOT and not player.village_idiot_revealed:
        # Village Idiot reveals and survives (loses vote)
        player.village_idiot_revealed = True
        
        events.append(VillageIdiotRevealEvent(
            day_number=state.day_number,
            phase=Phase.DAY,
            target_id=lynched_player_id,
        ))
        
        return new_state, events
    
    # Normal lynch - player dies
    player.is_alive = False

    events.append(LynchEvent(
        day_number=state.day_number,
        phase=Phase.DAY,
        target_id=lynched_player_id,
    ))
    
    return new_state, events


def resolve_badge_action(
    state: GameState,
    action: Action,
) -> tuple[GameState, list[Event]]:
    """Resolve a badge pass or tear action.
    
    Args:
        state: Current game state
        action: PassBadgeAction or TearBadgeAction
    
    Returns:
        Tuple of (new game state, list of events)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    if action.action_type == ActionType.PASS_BADGE and action.target_id:
        # Pass badge to target
        target = new_state.get_player(action.target_id)
        if target and target.is_alive:
            target.is_sheriff = True
            new_state.sheriff_id = target.id
            
            events.append(BadgePassEvent(
                day_number=state.day_number,
                phase=Phase.DAY,
                actor_id=action.actor_id,
                target_id=action.target_id,
            ))
    elif action.action_type == ActionType.TEAR_BADGE:
        # Tear badge - no more sheriff
        new_state.badge_torn = True
        new_state.sheriff_id = None
        
        events.append(BadgeTearEvent(
            day_number=state.day_number,
            phase=Phase.DAY,
            actor_id=action.actor_id,
        ))
    
    return new_state, events


def resolve_hunter_shot(
    state: GameState,
    action: HunterShootAction,
) -> tuple[GameState, list[Event]]:
    """Resolve a Hunter shooting action.
    
    Args:
        state: Current game state
        action: HunterShootAction
    
    Returns:
        Tuple of (new game state, list of events)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    hunter = new_state.get_player(action.actor_id)
    if not hunter or hunter.role != Role.HUNTER:
        return new_state, events
    
    # Check if hunter can shoot
    if not hunter.hunter_can_shoot:
        return new_state, events
    
    # Shoot target
    if action.target_id:
        target = new_state.get_player(action.target_id)
        if target and target.is_alive:
            target.is_alive = False
            
            events.append(HunterShotEvent(
                day_number=state.day_number,
                phase=state.phase,
                actor_id=hunter.id,
                target_id=target.id,
            ))
            
            # Handle sheriff death from hunter shot
            # When shot by hunter, the sheriff badge is automatically torn (no passing)
            if target.is_sheriff:
                target.is_sheriff = False
                new_state.sheriff_id = None
                new_state.badge_torn = True
    
    return new_state, events


def resolve_wolf_self_explode(
    state: GameState,
    actor_id: str,
) -> tuple[GameState, list[Event]]:
    """Resolve a werewolf self-explosion.
    
    Args:
        state: Current game state
        actor_id: ID of the werewolf self-exploding
    
    Returns:
        Tuple of (new game state, list of events)
    """
    new_state = deepcopy(state)
    events: list[Event] = []
    
    wolf = new_state.get_player(actor_id)
    if not wolf or wolf.role != Role.WEREWOLF or not wolf.is_alive:
        return new_state, events
    
    if not state.config.rule_variants.allow_wolf_self_explode:
        return new_state, events
    
    # Wolf dies
    wolf.is_alive = False

    events.append(WolfSelfExplodeEvent(
        day_number=state.day_number,
        phase=Phase.DAY,
        actor_id=actor_id,
        target_id=actor_id,
    ))
    
    return new_state, events


def check_win_condition(state: GameState) -> WinningTeam:
    """Check if a team has won the game.
    
    Win conditions depend on the configured win_mode:
    - SIDE_ELIMINATION: Werewolves win if all villagers OR all special roles are dead
    - CITY_ELIMINATION: Werewolves win if all good players are dead
    
    Village wins if all werewolves are eliminated.
    
    Args:
        state: Current game state
    
    Returns:
        WinningTeam enum value
    """
    alive_werewolves = state.get_alive_werewolves()
    alive_villagers = state.get_alive_villagers()
    alive_specials = state.get_alive_special_roles()
    
    # Village wins if all werewolves are dead
    if len(alive_werewolves) == 0:
        return WinningTeam.VILLAGE
    
    # Check werewolf win conditions
    win_mode = state.config.rule_variants.win_mode
    
    if win_mode == WinMode.SIDE_ELIMINATION:
        # Werewolves win if ALL villagers OR ALL special roles are dead
        if len(alive_villagers) == 0 or len(alive_specials) == 0:
            return WinningTeam.WEREWOLF
    elif win_mode == WinMode.CITY_ELIMINATION:
        # Werewolves win if ALL good players are dead
        alive_good = state.get_alive_players_by_alignment(Alignment.GOOD)
        if len(alive_good) == 0:
            return WinningTeam.WEREWOLF
    
    # Game continues
    return WinningTeam.NONE


def update_win_condition(state: GameState) -> GameState:
    """Update the game state with the current win condition.
    
    Args:
        state: Current game state
    
    Returns:
        Updated game state with winning_team set
    """
    new_state = deepcopy(state)
    new_state.winning_team = check_win_condition(new_state)
    
    if new_state.winning_team != WinningTeam.NONE:
        new_state.phase = Phase.GAME_OVER
    
    return new_state


def advance_to_day(state: GameState) -> GameState:
    """Advance the game state from night to day.
    
    Args:
        state: Current game state (should be in NIGHT phase)
    
    Returns:
        Updated game state in DAY phase
    """
    new_state = deepcopy(state)
    
    if state.phase != Phase.NIGHT:
        return new_state
    
    new_state.phase = Phase.DAY
    new_state.day_number += 1
    new_state.wolf_kill_target_id = None
    new_state.current_night_actions = {}
    
    return new_state


def advance_to_night(state: GameState) -> GameState:
    """Advance the game state from day to night.
    
    Args:
        state: Current game state (should be in DAY phase)
    
    Returns:
        Updated game state in NIGHT phase
    """
    new_state = deepcopy(state)
    
    if state.phase != Phase.DAY:
        return new_state
    
    new_state.phase = Phase.NIGHT
    
    return new_state


def get_valid_wolf_targets(state: GameState, include_self_knife: bool = True) -> list[str]:
    """Get valid targets for werewolf night kill.
    
    Args:
        state: Current game state
        include_self_knife: Whether to include fellow werewolves as targets
    
    Returns:
        List of valid target player IDs
    """
    targets = []
    
    for player in state.get_alive_players():
        if player.role == Role.WEREWOLF and not include_self_knife:
            continue
        targets.append(player.id)
    
    return targets


def get_valid_guard_targets(state: GameState, guard_id: str) -> list[str]:
    """Get valid targets for guard protection.
    
    Args:
        state: Current game state
        guard_id: ID of the guard player
    
    Returns:
        List of valid target player IDs
    """
    guard = state.get_player(guard_id)
    if not guard:
        return []
    
    targets = []
    for player in state.get_alive_players():
        # Cannot protect same person twice in a row
        if player.id == guard.guard_last_protected:
            continue
        
        # Check self-guard rule
        if player.id == guard_id and not state.config.rule_variants.guard_can_self_guard:
            continue
        
        targets.append(player.id)
    
    return targets


def get_valid_vote_targets(state: GameState, voter_id: str) -> list[str]:
    """Get valid targets for day vote.
    
    Args:
        state: Current game state
        voter_id: ID of the voting player
    
    Returns:
        List of valid target player IDs
    """
    targets = []
    
    for player in state.get_alive_players():
        # Cannot vote for yourself (in most variants)
        if player.id == voter_id:
            continue
        targets.append(player.id)
    
    return targets


def get_valid_hunter_targets(state: GameState, hunter_id: str) -> list[str]:
    """Get valid targets for hunter shot.
    
    Args:
        state: Current game state
        hunter_id: ID of the hunter player
    
    Returns:
        List of valid target player IDs
    """
    targets = []
    
    for player in state.get_alive_players():
        # Hunter cannot shoot themselves
        if player.id == hunter_id:
            continue
        targets.append(player.id)
    
    return targets


def can_witch_cure(state: GameState, witch_id: str, target_id: Optional[str]) -> bool:
    """Check if the Witch can use cure on a target.
    
    Args:
        state: Current game state
        witch_id: ID of the Witch player
        target_id: ID of target to cure (should be wolf's kill target)
    
    Returns:
        True if the Witch can cure this target
    """
    witch = state.get_player(witch_id)
    if not witch or witch.role != Role.WITCH or not witch.is_alive:
        return False
    
    if not witch.witch_has_cure:
        return False
    
    if not target_id:
        return False
    
    # Can only cure the wolf's target
    if target_id != state.wolf_kill_target_id:
        return False
    
    # Check self-heal rules
    if target_id == witch_id:
        is_night_1 = state.day_number == 0
        if is_night_1:
            return state.config.rule_variants.witch_can_self_heal_n1
        else:
            return state.config.rule_variants.witch_can_self_heal
    
    return True


def can_witch_poison(state: GameState, witch_id: str) -> bool:
    """Check if the Witch can use poison.
    
    Args:
        state: Current game state
        witch_id: ID of the Witch player
    
    Returns:
        True if the Witch can poison
    """
    witch = state.get_player(witch_id)
    if not witch or witch.role != Role.WITCH or not witch.is_alive:
        return False
    
    return witch.witch_has_poison


def can_hunter_shoot(state: GameState, hunter_id: str) -> bool:
    """Check if the Hunter can shoot.
    
    Args:
        state: Current game state
        hunter_id: ID of the Hunter player
    
    Returns:
        True if the Hunter can shoot
    """
    hunter = state.get_player(hunter_id)
    if not hunter or hunter.role != Role.HUNTER:
        return False
    
    return hunter.hunter_can_shoot
