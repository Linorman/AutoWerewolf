import pytest

from autowerewolf.engine.state import GameConfig, EventType, Action
from autowerewolf.engine.rules import create_game_state, resolve_night_actions, resolve_badge_action
from autowerewolf.engine.state import WolfKillAction
from autowerewolf.engine.state import PassBadgeAction


def test_integration_sheriff_badge_pass_flow():
    """Integration test: sheriff is elected, gets night-killed, and badge is passed at day."""
    # Create a game state with default config
    config = GameConfig()
    state = create_game_state(config)

    # Pick a sheriff (player 0) and a successor (player 1)
    sheriff = state.players[0]
    successor = state.players[1]

    # Set initial sheriff
    state.sheriff_id = sheriff.id
    sheriff.is_sheriff = True

    # Choose a werewolf to perform the night kill (find first werewolf)
    wolf = next((p for p in state.players if p.role.name == 'WEREWOLF'), None)
    assert wolf is not None

    # Resolve night actions: wolf kills the sheriff
    actions: list[Action] = [WolfKillAction(actor_id=wolf.id, target_id=sheriff.id)]
    night_state, events = resolve_night_actions(state, actions)

    # Sanity: sheriff should be dead but still marked as sheriff until day processing
    dead_player = night_state.get_player(sheriff.id)
    assert dead_player is not None
    assert not dead_player.is_alive
    # is_sheriff should be True here (we expect rules to preserve it until day)
    assert dead_player.is_sheriff

    # Simulate orchestrator applying the sheriff's decision by calling
    # resolve_badge_action (what the orchestrator does after asking the
    # dead sheriff or applying automatic rules). Here we assert that the
    # badge can be passed when invoked.
    action = PassBadgeAction(actor_id=sheriff.id, target_id=successor.id)
    final_state, events = resolve_badge_action(night_state, action)

    # After handling, the badge should be passed to successor
    assert final_state.sheriff_id == successor.id
    succ = final_state.get_player(successor.id)
    assert succ is not None and succ.is_sheriff

    # And an event should be emitted
    badge_events = [e for e in events if e.event_type.value in (EventType.BADGE_PASS, EventType.BADGE_TEAR)]
    assert len(badge_events) == 1
    assert badge_events[0].event_type.value == EventType.BADGE_PASS
