from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoe4.client.state import StateStore
from aoe4.client.tracker import (
    DEATH_LINK_WINDOW_SECONDS,
    MatchTracker,
    TrackerConfig,
    TrackerState,
    rank_at_least,
)
from aoe4.constants import civilization_win_location_name


def config(**overrides) -> TrackerConfig:
    values = {
        "profile_id": 1001,
        "tracking_started_at": 1_000.0,
        "goal": "total_wins",
        "total_win_goal": 3,
        "wins_per_goal_civilization": 2,
        "goal_civilizations": frozenset({"english"}),
        "target_rank": "gold_1",
        "civilization_pool": frozenset({"english", "french"}),
        "eligible_match_modes": frozenset({"rm_solo", "rm_team", "qm_1v1", "qm_2v2", "qm_3v3", "qm_4v4"}),
        "include_custom_games": False,
        "api_key_available": False,
        "civ_sanity": True,
        "win_thresholds": (1, 2, 3),
        "death_link": False,
    }
    values.update(overrides)
    return TrackerConfig(**values)


def game(game_id: int, *, result="win", civ="english", mode="rm_solo", started=1_100.0, duration=100, ongoing=False):
    return {
        "game_id": game_id,
        "started_at": started,
        "updated_at": started + duration,
        "duration": duration,
        "leaderboard": mode,
        "ongoing": ongoing,
        "teams": [
            [{"player": {"profile_id": 1001, "result": result, "civilization": civ, "civilization_randomized": True}}],
            [{"player": {"profile_id": 2001, "result": "loss" if result == "win" else "win", "civilization": "french"}}],
        ],
    }


def test_all_supported_queues_and_team_layout_fixture():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "standard_queues.json").read_text(encoding="utf-8"))
    tracker = MatchTracker(config(tracking_started_at=1_767_225_600.0, total_win_goal=6))
    outcome = tracker.process_games(fixture["games"], {"english"}, observed_at=1_767_250_000.0)
    assert tracker.state.total_wins == 6
    assert outcome.goal_reached
    assert len(outcome.processed_game_ids) == 6


def test_locked_randomized_ongoing_unknown_and_deduplication():
    tracker = MatchTracker(config())
    locked = tracker.process_games([game(1, civ="french")], {"english"}, 1_300)
    assert locked.ignored_locked_wins == [1]
    assert tracker.state.total_wins == 0
    tracker.process_games([game(1, civ="french")], {"english", "french"}, 1_300)
    assert tracker.state.total_wins == 0
    tracker.process_games([game(2, ongoing=True), game(3, result="unknown")], {"english"}, 1_300)
    assert tracker.state.total_wins == 0
    assert 2 not in tracker.state.seen_game_ids
    assert 3 in tracker.state.seen_game_ids


def test_multi_threshold_backfill_and_civ_sanity():
    tracker = MatchTracker(config())
    games = [game(index, started=1_000 + index * 100) for index in range(1, 4)]
    outcome = tracker.process_games(games, {"english"}, 1_500)
    assert outcome.new_checks == [
        "Win 1 Match",
        "Civilization Victory: English",
        "Win 2 Matches",
        "Win 3 Matches",
    ]
    assert outcome.goal_reached


def test_custom_games_require_slot_option_and_api_key():
    by_kind = game(10, mode="rm_solo")
    by_kind["kind"] = "custom"
    disabled = MatchTracker(config(api_key_available=True))
    disabled.process_games([by_kind], {"english"}, 1_300)
    assert disabled.state.total_wins == 0
    assert 10 in disabled.state.seen_game_ids

    by_leaderboard = game(11, mode="custom")
    missing_key = MatchTracker(config(include_custom_games=True))
    missing_key.process_games([by_leaderboard], {"english"}, 1_300)
    assert missing_key.state.total_wins == 0
    assert 11 not in missing_key.state.seen_game_ids

    with_key = MatchTracker(
        config(include_custom_games=True, api_key_available=True),
        missing_key.state,
    )
    outcome = with_key.process_games([by_leaderboard], {"english"}, 1_300)
    assert with_key.state.total_wins == 1
    assert outcome.new_checks == ["Win 1 Match", "Civilization Victory: English"]


def test_custom_games_follow_locked_civ_and_deathlink_rules():
    tracker = MatchTracker(
        config(include_custom_games=True, api_key_available=True, death_link=True)
    )
    tracker.receive_death_link(1_050)
    suppressed = tracker.process_games(
        [game(20, mode="custom", started=1_060, duration=10)],
        {"english"},
        1_100,
    )
    assert suppressed.suppressed_game_ids == [20]
    assert tracker.state.total_wins == 0

    locked = tracker.process_games(
        [game(21, mode="custom", civ="french", started=1_200)],
        {"english"},
        1_350,
    )
    assert locked.ignored_locked_wins == [21]

    loss = tracker.process_games(
        [game(22, mode="custom", result="loss", started=1_300, duration=10)],
        {"english"},
        1_350,
    )
    assert len(loss.send_deaths) == 1


def test_every_goal_and_rank_ordering():
    total = MatchTracker(config(total_win_goal=1))
    assert total.process_games([game(1)], {"english"}, 1_300).goal_reached

    civilization = MatchTracker(config(goal="civilization_wins", goal_civilizations=frozenset({"english", "french"}), wins_per_goal_civilization=1))
    civilization.process_games([game(1, civ="english"), game(2, civ="french", started=1_300)], {"english", "french"}, 1_500)
    assert civilization.goal_reached()

    solo = MatchTracker(config(goal="solo_rank", target_rank="diamond_2"))
    assert solo.update_ranks({"modes": {"rm_solo": {"rank_level": "conqueror_4"}}})
    solo.update_ranks({"modes": {"rm_solo": {"rank_level": "bronze_1"}}})
    assert solo.goal_reached()

    team = MatchTracker(config(goal="team_rank", target_rank="gold_1"))
    assert team.update_ranks({"modes": {"rm_team": {"rank_level": "gold_1"}}})
    assert rank_at_least("conqueror_3", "bronze_1")
    assert not rank_at_least("silver_3", "gold_1")


def test_civilization_goal_sends_one_numbered_check_per_required_win():
    civilizations = ("english", "french", "malians")
    tracker = MatchTracker(
        config(
            goal="civilization_wins",
            goal_civilizations=frozenset(civilizations),
            civilization_pool=frozenset(civilizations),
            wins_per_goal_civilization=5,
            # These are ignored for civilization-win goals even if malformed
            # slot data or a direct unit configuration supplies them.
            civ_sanity=True,
            win_thresholds=(1, 2, 3),
            numbered_civilization_win_checks=True,
        )
    )
    games = []
    game_id = 1
    for civilization in civilizations:
        for _win_number in range(1, 6):
            games.append(
                game(
                    game_id,
                    civ=civilization,
                    started=1_000 + game_id * 100,
                )
            )
            game_id += 1

    outcome = tracker.process_games(games, set(civilizations), observed_at=3_000)
    assert outcome.new_checks == [
        civilization_win_location_name(civilization, win_number)
        for civilization in civilizations
        for win_number in range(1, 6)
    ]
    assert len(outcome.new_checks) == 15
    assert tracker.goal_reached()
    assert not any(name.startswith("Win ") for name in outcome.new_checks)
    assert not any(name.startswith("Civilization Victory:") for name in outcome.new_checks)


def test_legacy_civilization_goal_slot_keeps_legacy_check_mapping():
    tracker = MatchTracker(
        config(
            goal="civilization_wins",
            goal_civilizations=frozenset({"english"}),
            wins_per_goal_civilization=1,
            numbered_civilization_win_checks=False,
        )
    )
    outcome = tracker.process_games([game(1)], {"english"}, 1_300)
    assert outcome.new_checks == ["Win 1 Match", "Civilization Victory: English"]


def test_deathlink_nonstack_expiry_and_win_consumption():
    tracker = MatchTracker(config(death_link=True))
    assert tracker.receive_death_link(1_050)
    original_expiry = tracker.state.pending_death_expires_at
    assert not tracker.receive_death_link(1_060)
    assert tracker.state.pending_death_expires_at == original_expiry
    outcome = tracker.process_games([game(1, started=1_060, duration=10)], {"english"}, 1_100)
    assert outcome.suppressed_game_ids == [1]
    assert tracker.state.total_wins == 0
    assert tracker.state.pending_death_expires_at is None

    assert tracker.receive_death_link(2_000)
    assert tracker.expire_death_link(2_000 + DEATH_LINK_WINDOW_SECONDS)


def test_deathlink_late_backfill_uses_completion_time_before_expiring():
    tracker = MatchTracker(config(death_link=True))
    tracker.receive_death_link(1_050)
    outcome = tracker.process_games(
        [game(1, started=1_060, duration=10)],
        {"english"},
        observed_at=1_050 + DEATH_LINK_WINDOW_SECONDS + 500,
    )
    assert outcome.suppressed_game_ids == [1]
    assert tracker.state.total_wins == 0
    assert tracker.state.pending_death_expires_at is None


def test_deathlink_loss_consumes_and_still_sends_but_stale_loss_does_not():
    tracker = MatchTracker(config(death_link=True))
    tracker.receive_death_link(1_050)
    outcome = tracker.process_games([game(1, result="loss", started=1_060, duration=10)], {"english"}, 1_100)
    assert outcome.suppressed_game_ids == [1]
    assert len(outcome.send_deaths) == 1

    stale = tracker.process_games([game(2, result="loss", started=2_000, duration=10)], {"english"}, 2_010 + DEATH_LINK_WINDOW_SECONDS + 1)
    assert stale.send_deaths == []


def test_state_restart_persistence_prevents_duplicates(tmp_path):
    first = MatchTracker(config(death_link=True))
    first.process_games([game(1, result="loss")], {"english"}, 1_250)
    first.receive_death_link(1_300)
    store = StateStore(tmp_path)
    store.save("state.json", first.state)

    second = MatchTracker(config(death_link=True), store.load("state.json"))
    duplicate = second.process_games([game(1, result="loss")], {"english"}, 1_250)
    assert duplicate.send_deaths == []
    assert second.state.pending_death_expires_at == 1_300 + DEATH_LINK_WINDOW_SECONDS


def test_version_one_state_migrates_legacy_cursor_to_credentialed_cursor():
    migrated = TrackerState.from_dict({"schema_version": 1, "cursor_started_at": 1_234.0})
    assert migrated.schema_version == 2
    assert migrated.cursor_started_at == 1_234.0
    assert migrated.credentialed_cursor_started_at == 1_234.0

    fresh = TrackerState()
    assert fresh.schema_version == 2
    assert fresh.credentialed_cursor_started_at is None
