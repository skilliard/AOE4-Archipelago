from __future__ import annotations

from importlib import resources

from aoe4.client.tracker_view import (
    CIVILIZATION_FLAG_FILES,
    build_civilization_tracker_entries,
)
from aoe4.constants import CIVILIZATIONS


def slot_data(**overrides):
    data = {
        "goal": "civilization_wins",
        "wins_per_goal_civilization": 3,
        "goal_civilizations": ["english", "french", "rus"],
        "civilization_pool": ["english", "french", "rus"],
        "civ_sanity": False,
    }
    data.update(overrides)
    return data


def test_tracker_shows_per_civilization_goal_requirements_for_effective_pool():
    entries = build_civilization_tracker_entries(
        slot_data(),
        {"english", "french"},
        {"english": 1, "french": 1},
    )
    by_civilization = {entry.civilization: entry for entry in entries}

    english = by_civilization["english"]
    assert english.unlocked
    assert english.required_wins == 3
    assert english.credited_wins == 1
    assert english.wins_remaining == 2
    assert not english.requirement_complete

    french = by_civilization["french"]
    assert french.unlocked
    assert french.required_wins == 3
    assert french.wins_remaining == 2
    assert not french.requirement_complete

    rus = by_civilization["rus"]
    assert not rus.unlocked
    assert rus.required_wins == 3


def test_tracker_handles_slots_without_civilization_specific_requirements():
    entries = build_civilization_tracker_entries(
        slot_data(goal="total_wins", civ_sanity=False),
        {"english"},
        {},
    )
    assert all(entry.required_wins == 0 for entry in entries)
    assert all(entry.requirement_complete for entry in entries)


def test_tracker_exposes_earned_and_attainable_civilization_wins():
    entries = build_civilization_tracker_entries(
        slot_data(
            wins_per_goal_civilization=6,
            civilization_win_cap_stages=[2, 3, 4, 5, 6],
        ),
        {"english"},
        {"english": 6},
        {"english": 2},
    )
    english = next(entry for entry in entries if entry.civilization == "english")
    assert english.credited_wins == 6
    assert english.attainable_wins == 2
    assert english.wins_remaining == 0
    assert english.cap_blocked
    assert not english.requirement_complete


def test_every_pinned_civilization_has_a_packaged_png_flag():
    assert set(CIVILIZATION_FLAG_FILES) == set(CIVILIZATIONS)
    asset_root = resources.files("aoe4.client").joinpath("assets", "civilization_flags")
    for filename in CIVILIZATION_FLAG_FILES.values():
        data = asset_root.joinpath(filename).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(data) > 1_000
