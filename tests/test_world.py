from __future__ import annotations

import pytest

import aoe4
from BaseClasses import CollectionState, ItemClassification
from Options import OptionError
from test.bases import WorldTestBase

from aoe4.constants import (
    civilization_location_name,
    civilization_unlock_name,
    civilization_win_location_name,
    win_location_name,
)
from aoe4.items import FILLER_ITEM_NAME


class DefaultWorldTests(WorldTestBase):
    game = "Age of Empires IV"

    def test_default_counts_and_precollect(self):
        regular_locations = [location for location in self.multiworld.get_locations(1) if location.address is not None]
        assert len(regular_locations) == 48
        assert len(self.multiworld.itempool) == 48
        precollected = self.multiworld.precollected_items[1]
        assert len(precollected) == 1
        assert precollected[0].name.endswith(" Civilization Unlock")
        assert sum(item.name == FILLER_ITEM_NAME for item in self.multiworld.itempool) == 26
        unlocks = [item for item in self.multiworld.itempool if item.name.endswith(" Civilization Unlock")]
        assert len(unlocks) == 22
        assert all(item.classification & ItemClassification.progression for item in unlocks)

    def test_civilization_location_requires_unlock(self):
        civilization = next(civ for civ in self.world.civilization_pool if civ != self.world.starting_civilization)
        state = CollectionState(self.multiworld)
        location = self.multiworld.get_location(civilization_location_name(civilization), 1)
        assert not location.can_reach(state)
        state.collect(self.world.create_item(civilization_unlock_name(civilization)))
        assert location.can_reach(state)


class ManualWorldHarness(WorldTestBase):
    game = "Age of Empires IV"
    auto_construct = False


def build_world(options: dict, seed: int = 12345) -> WorldTestBase:
    harness = ManualWorldHarness(methodName="runTest")
    harness.options = options
    harness.world_setup(seed)
    return harness


def test_selected_and_random_starting_civilizations():
    selected = build_world(
        {
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["english"],
            "starting_civilization": "french",
            "civ_sanity": False,
            "win_check_count": 1,
        }
    )
    assert selected.world.starting_civilization == "french"
    assert selected.multiworld.precollected_items[1][0].name == civilization_unlock_name("french")

    first = build_world(
        {
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["english"],
            "starting_civilization": "random",
            "civ_sanity": False,
            "win_check_count": 1,
        },
        seed=88,
    )
    second = build_world(
        {
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["english"],
            "starting_civilization": "random",
            "civ_sanity": False,
            "win_check_count": 1,
        },
        seed=88,
    )
    assert first.world.starting_civilization == second.world.starting_civilization
    assert first.world.starting_civilization in {"english", "french"}


def test_multiple_starting_civilizations_are_deterministic_and_reduce_unlock_items():
    options = {
        "civilization_pool": ["english", "french", "malians", "rus"],
        "goal_civilizations": ["english"],
        "starting_civilization": "french",
        "starting_civs": 3,
        "civ_sanity": False,
        "win_check_count": 1,
    }
    first = build_world(options, seed=77)
    second = build_world(options, seed=77)

    assert first.world.starting_civilizations == second.world.starting_civilizations
    assert first.world.starting_civilizations[0] == "french"
    assert len(first.world.starting_civilizations) == 3
    assert set(first.world.starting_civilizations) <= {
        "english", "french", "malians", "rus"
    }
    assert {
        item.name for item in first.multiworld.precollected_items[1]
    } == {
        civilization_unlock_name(civilization)
        for civilization in first.world.starting_civilizations
    }
    unlocks = [
        item for item in first.multiworld.itempool
        if item.name.endswith(" Civilization Unlock")
    ]
    assert len(unlocks) == 1


def test_civilization_win_goal_takes_multiple_starts_from_goal_civilizations():
    harness = build_world(
        {
            "goal": "civilization_wins",
            "civilization_pool": ["rus", "mongols"],
            "goal_civilizations": ["english", "french", "malians"],
            "wins_per_goal_civilization": 1,
            "starting_civilization": "english",
            "starting_civs": 2,
        },
        seed=91,
    )

    assert harness.world.starting_civilizations[0] == "english"
    assert len(harness.world.starting_civilizations) == 2
    assert set(harness.world.starting_civilizations) <= {"english", "french", "malians"}
    assert len(harness.multiworld.precollected_items[1]) == 2
    assert sum(
        item.name.endswith(" Civilization Unlock") for item in harness.multiworld.itempool
    ) == 1


def test_civilization_win_goal_uses_goal_civilizations_and_creates_numbered_checks():
    harness = build_world(
        {
            "goal": "civilization_wins",
            "civilization_pool": ["rus", "mongols"],
            "goal_civilizations": ["english", "french", "malians"],
            "wins_per_goal_civilization": 5,
            "starting_civilization": "random",
            # These options are deliberately enabled/configured to prove the
            # civilization-win goal ignores both check systems.
            "civ_sanity": True,
            "win_check_interval": 2,
            "win_check_count": 7,
        }
    )

    assert set(harness.world.civilization_pool) == {"english", "french", "malians"}
    assert harness.world.starting_civilization in harness.world.civilization_pool
    regular_locations = {
        location.name
        for location in harness.multiworld.get_locations(1)
        if location.address is not None
    }
    expected_locations = {
        civilization_win_location_name(civilization, win_number)
        for civilization in ("english", "french", "malians")
        for win_number in range(1, 6)
    }
    assert regular_locations == expected_locations
    assert len(harness.multiworld.itempool) == 15
    assert sum(item.name == FILLER_ITEM_NAME for item in harness.multiworld.itempool) == 13
    assert sum(
        item.name.endswith(" Civilization Unlock") for item in harness.multiworld.itempool
    ) == 2

    locked_civilization = next(
        civilization
        for civilization in harness.world.civilization_pool
        if civilization != harness.world.starting_civilization
    )
    state = CollectionState(harness.multiworld)
    for win_number in range(1, 6):
        location = harness.multiworld.get_location(
            civilization_win_location_name(locked_civilization, win_number), 1
        )
        assert not location.can_reach(state)
    state.collect(harness.world.create_item(civilization_unlock_name(locked_civilization)))
    assert all(
        harness.multiworld.get_location(
            civilization_win_location_name(locked_civilization, win_number), 1
        ).can_reach(state)
        for win_number in range(1, 6)
    )

    data = harness.world.fill_slot_data()
    assert set(data["civilization_pool"]) == {"english", "french", "malians"}
    assert data["civ_sanity"] is False
    assert data["win_thresholds"] == []
    assert data["civilization_location_ids"] == {}
    assert data["win_location_ids"] == {}
    assert sum(len(ids) for ids in data["civilization_win_location_ids"].values()) == 15


def test_total_and_rank_goals_use_civilization_pool_and_ignore_goal_civilizations():
    total = build_world(
        {
            "goal": "total_wins",
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["malians"],
            "starting_civilization": "french",
            "civ_sanity": False,
            "win_check_count": 1,
        }
    )
    assert total.world.civilization_pool == ("english", "french")
    assert total.world.starting_civilization == "french"
    assert {
        location.name
        for location in total.multiworld.get_locations(1)
        if location.address is not None
    } == {win_location_name(1)}

    rank = build_world(
        {
            "goal": "solo_rank",
            "civilization_pool": ["english", "rus"],
            "goal_civilizations": ["malians"],
            "starting_civilization": "rus",
            "eligible_match_modes": ["rm_solo"],
            "civ_sanity": False,
            "win_check_count": 1,
        }
    )
    assert rank.world.civilization_pool == ("english", "rus")


def test_single_civilization_win_goal_is_valid_and_needs_no_unlock_item():
    harness = build_world(
        {
            "goal": "civilization_wins",
            "goal_civilizations": ["english"],
            "wins_per_goal_civilization": 3,
            "starting_civilization": "random",
        }
    )
    regular_locations = [
        location
        for location in harness.multiworld.get_locations(1)
        if location.address is not None
    ]
    assert [location.name for location in regular_locations] == [
        civilization_win_location_name("english", number) for number in range(1, 4)
    ]
    assert not any(
        item.name.endswith(" Civilization Unlock") for item in harness.multiworld.itempool
    )


@pytest.mark.parametrize(
    "options",
    [
        {"civilization_pool": ["english"], "goal_civilizations": ["english"]},
        {"civilization_pool": ["english", "french"], "goal_civilizations": ["english"], "starting_civilization": "rus"},
        {"civilization_pool": ["english", "french"], "goal": "civilization_wins", "goal_civilizations": []},
        {"civilization_pool": ["english", "french"], "goal": "civilization_wins", "goal_civilizations": ["english"], "starting_civilization": "french"},
        {"civilization_pool": ["english", "french"], "goal_civilizations": ["english"], "goal": "solo_rank", "eligible_match_modes": ["qm_1v1"]},
        {"civilization_pool": ["english", "french"], "goal_civilizations": ["english"], "goal": "team_rank", "eligible_match_modes": ["rm_solo"]},
        {"civilization_pool": ["english", "french", "rus"], "goal_civilizations": ["english"], "civ_sanity": False, "win_check_count": 1},
        {"civilization_pool": ["english", "french"], "goal_civilizations": ["english"], "starting_civs": 3},
        {"goal": "civilization_wins", "goal_civilizations": ["english", "french"], "starting_civs": 3},
    ],
)
def test_invalid_options(options):
    with pytest.raises(OptionError):
        build_world(options)


def test_slot_data_has_resolved_values_and_no_credentials():
    harness = build_world(
        {
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["english"],
            "starting_civilization": "random",
            "civ_sanity": False,
            "win_check_interval": 3,
            "win_check_count": 2,
            "include_custom_games": True,
        }
    )
    data = harness.world.fill_slot_data()
    assert data["starting_civilization"] in {"english", "french"}
    assert data["starting_civs"] == 1
    assert data["starting_civilizations"] == [data["starting_civilization"]]
    assert data["win_thresholds"] == [3, 6]
    assert data["include_custom_games"] is True
    assert data["civilization_win_location_ids"] == {}
    assert data["world_version"] == "0.4.0"
    serialized_keys = " ".join(data).lower()
    assert "api" not in serialized_keys
    assert "profile" not in serialized_keys
