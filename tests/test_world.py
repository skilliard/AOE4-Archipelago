from __future__ import annotations

import pytest

import aoe4
from BaseClasses import CollectionState, ItemClassification
from Options import OptionError
from test.bases import WorldTestBase

from aoe4.constants import (
    CIVILIZATIONS,
    PROGRESSIVE_TOTAL_WIN_CAP,
    civilization_location_name,
    civilization_unlock_name,
    civilization_win_location_name,
    progressive_civilization_name,
    progressive_civilization_win_cap_name,
    progressive_win_cap_stages,
    win_location_name,
)
from aoe4.items import FILLER_ITEM_NAME, ITEM_ID_BASE, ITEM_NAME_TO_ID


class DefaultWorldTests(WorldTestBase):
    game = "Age of Empires IV"

    def test_default_counts_and_precollect(self):
        regular_locations = [location for location in self.multiworld.get_locations(1) if location.address is not None]
        assert len(regular_locations) == 48
        assert len(self.multiworld.itempool) == 48
        precollected = self.multiworld.precollected_items[1]
        assert len(precollected) == 1
        assert precollected[0].name.startswith("Progressive ")
        assert precollected[0].name.endswith(" Civilization")
        assert sum(item.name == FILLER_ITEM_NAME for item in self.multiworld.itempool) == 22
        assert sum(item.name == PROGRESSIVE_TOTAL_WIN_CAP for item in self.multiworld.itempool) == 4
        assert all(
            item.classification & ItemClassification.progression
            for item in self.multiworld.itempool
            if item.name == PROGRESSIVE_TOTAL_WIN_CAP
        )
        civilization_items = [
            item
            for item in self.multiworld.itempool
            if item.name.startswith("Progressive ")
            and item.name.endswith(" Civilization")
        ]
        assert len(civilization_items) == 22
        assert all(
            item.classification & ItemClassification.progression
            for item in civilization_items
        )

    def test_civilization_location_requires_unlock(self):
        civilization = next(civ for civ in self.world.civilization_pool if civ != self.world.starting_civilization)
        state = CollectionState(self.multiworld)
        location = self.multiworld.get_location(civilization_location_name(civilization), 1)
        assert not location.can_reach(state)
        state.collect(self.world.create_item(progressive_civilization_name(civilization)))
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
            "total_win_goal": 1,
            "win_check_count": 1,
        }
    )
    assert selected.world.starting_civilization == "french"
    assert selected.multiworld.precollected_items[1][0].name == progressive_civilization_name("french")

    first = build_world(
        {
            "civilization_pool": ["english", "french"],
            "goal_civilizations": ["english"],
            "starting_civilization": "random",
            "civ_sanity": False,
            "total_win_goal": 1,
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
            "total_win_goal": 1,
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
        "total_win_goal": 1,
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
        progressive_civilization_name(civilization)
        for civilization in first.world.starting_civilizations
    }
    progression_items = [
        item for item in first.multiworld.itempool
        if item.name.startswith("Progressive ")
        and item.name.endswith(" Civilization")
    ]
    assert len(progression_items) == 1


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
        item.name.startswith("Progressive ")
        and item.name.endswith(" Civilization")
        for item in harness.multiworld.itempool
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
    assert sum(item.name == FILLER_ITEM_NAME for item in harness.multiworld.itempool) == 1
    assert sum(
        item.name.startswith("Progressive ") and item.name.endswith(" Civilization")
        for item in harness.multiworld.itempool
    ) == 14
    assert not any(
        item.name.endswith(" Civilization Unlock")
        or item.name.endswith(" Win Cap") and item.name != PROGRESSIVE_TOTAL_WIN_CAP
        for item in harness.multiworld.itempool
    )

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
    state.collect(
        harness.world.create_item(progressive_civilization_name(locked_civilization))
    )
    assert harness.multiworld.get_location(
        civilization_win_location_name(locked_civilization, 1), 1
    ).can_reach(state)
    assert not harness.multiworld.get_location(
        civilization_win_location_name(locked_civilization, 2), 1
    ).can_reach(state)
    for _ in range(4):
        state.collect(
            harness.world.create_item(progressive_civilization_name(locked_civilization))
        )
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
            "total_win_goal": 1,
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


def test_single_civilization_win_goal_precollects_first_tier():
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
    assert sum(
        item.name == progressive_civilization_name("english")
        for item in harness.multiworld.itempool
    ) == 2
    assert not any(item.name.endswith(" Civilization Unlock") for item in harness.multiworld.itempool)


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
        {"civilization_pool": ["english", "french"], "starting_civilizations": ["english", "rus"]},
        {
            "civilization_pool": ["english", "french", "malians", "rus", "mongols", "chinese"],
            "starting_civilizations": ["english", "french", "malians", "rus", "mongols", "chinese"],
        },
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
            "win_check_count": 5,
            "total_win_goal": 6,
            "include_custom_games": True,
        }
    )
    data = harness.world.fill_slot_data()
    assert data["starting_civilization"] in {"english", "french"}
    assert data["starting_civs"] == 1
    assert data["starting_civilizations"] == [data["starting_civilization"]]
    assert data["win_thresholds"] == [3, 6, 9, 12, 15]
    assert data["total_win_cap_stages"] == [3, 6, 9, 12, 15]
    assert data["include_custom_games"] is True
    assert data["civilization_win_location_ids"] == {}
    assert data["world_version"] == "0.5.1"
    assert set(data["progressive_civilization_item_ids"]) == {"english", "french"}
    assert "item_name_to_id" not in data
    assert "progressive_civilization_win_cap_item_ids" not in data
    serialized_keys = " ".join(data).lower()
    assert "api" not in serialized_keys
    assert "profile" not in serialized_keys


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (50, (10, 20, 30, 40, 50)),
        (25, (5, 10, 15, 20, 25)),
        (6, (2, 3, 4, 5, 6)),
        (4, (1, 2, 3, 4)),
        (1, (1,)),
    ],
)
def test_progressive_win_cap_stage_math(target, expected):
    assert progressive_win_cap_stages(target) == expected


def test_total_win_caps_use_largest_target_and_gate_locations_and_goal():
    harness = build_world(
        {
            "civilization_pool": ["english", "french"],
            "starting_civilizations": ["english", "french"],
            "civ_sanity": False,
            "total_win_goal": 50,
            "win_check_interval": 1,
            "win_check_count": 50,
        }
    )
    assert harness.world.total_win_cap_stages == (10, 20, 30, 40, 50)
    assert sum(item.name == PROGRESSIVE_TOTAL_WIN_CAP for item in harness.multiworld.itempool) == 4

    state = CollectionState(harness.multiworld)
    assert harness.multiworld.get_location(win_location_name(10), 1).can_reach(state)
    assert not harness.multiworld.get_location(win_location_name(11), 1).can_reach(state)
    assert not harness.multiworld.get_location("AOE4 Goal Achieved", 1).can_reach(state)
    state.collect(harness.world.create_item(PROGRESSIVE_TOTAL_WIN_CAP))
    assert harness.multiworld.get_location(win_location_name(20), 1).can_reach(state)
    assert not harness.multiworld.get_location(win_location_name(21), 1).can_reach(state)
    for _ in range(3):
        state.collect(harness.world.create_item(PROGRESSIVE_TOTAL_WIN_CAP))
    assert harness.multiworld.get_location(win_location_name(50), 1).can_reach(state)
    assert harness.multiworld.get_location("AOE4 Goal Achieved", 1).can_reach(state)


def test_total_cap_target_uses_goal_when_it_exceeds_highest_check():
    harness = build_world(
        {
            "civilization_pool": ["english", "french"],
            "starting_civilizations": ["english", "french"],
            "civ_sanity": False,
            "total_win_goal": 25,
            "win_check_interval": 2,
            "win_check_count": 5,
        }
    )
    assert harness.world.win_thresholds[-1] == 10
    assert harness.world.total_win_cap_stages == (5, 10, 15, 20, 25)


def test_explicit_starting_list_is_exact_and_takes_precedence():
    harness = build_world(
        {
            "civilization_pool": ["english", "french", "malians", "rus"],
            "starting_civilizations": ["rus", "english", "french"],
            "starting_civilization": "malians",
            "starting_civs": 1,
            "civ_sanity": False,
            "total_win_goal": 1,
            "win_check_count": 1,
        }
    )
    assert harness.world.starting_civilizations == ("english", "french", "rus")
    assert {
        item.name for item in harness.multiworld.precollected_items[1]
    } == {
        progressive_civilization_name("english"),
        progressive_civilization_name("french"),
        progressive_civilization_name("rus"),
    }


def test_multi_win_civ_sanity_generates_numbered_checks_and_independent_caps():
    harness = build_world(
        {
            "goal": "solo_rank",
            "eligible_match_modes": ["rm_solo"],
            "civilization_pool": ["english", "french"],
            "starting_civilizations": ["english", "french"],
            "civ_sanity": True,
            "civ_sanity_win_count": 3,
            "win_check_count": 5,
        }
    )
    assert harness.world.civilization_win_cap_stages == (1, 2, 3)
    assert sum(
        item.name == progressive_civilization_name("english")
        for item in harness.multiworld.itempool
    ) == 2
    data = harness.world.fill_slot_data()
    assert data["civilization_location_ids"] == {}
    assert set(data["civilization_win_location_ids"]) == {"english", "french"}

    state = CollectionState(harness.multiworld)
    second_english = harness.multiworld.get_location(
        civilization_win_location_name("english", 2), 1
    )
    second_french = harness.multiworld.get_location(
        civilization_win_location_name("french", 2), 1
    )
    assert not second_english.can_reach(state)
    state.collect(harness.world.create_item(progressive_civilization_name("english")))
    assert second_english.can_reach(state)
    assert not second_french.can_reach(state)


def test_six_win_civilization_progression_uses_five_tiers():
    harness = build_world(
        {
            "goal": "civilization_wins",
            "goal_civilizations": ["english", "french"],
            "wins_per_goal_civilization": 6,
            "starting_civilization": "english",
        }
    )
    assert harness.world.civilization_win_cap_stages == (2, 3, 4, 5, 6)
    assert harness.world.civilization_progression_tiers == 5
    assert sum(
        item.name == progressive_civilization_name("english")
        for item in harness.multiworld.itempool
    ) == 4
    assert sum(
        item.name == progressive_civilization_name("french")
        for item in harness.multiworld.itempool
    ) == 5

    state = CollectionState(harness.multiworld)
    french_two = harness.multiworld.get_location(
        civilization_win_location_name("french", 2), 1
    )
    french_three = harness.multiworld.get_location(
        civilization_win_location_name("french", 3), 1
    )
    assert not french_two.can_reach(state)
    state.collect(harness.world.create_item(progressive_civilization_name("french")))
    assert french_two.can_reach(state)
    assert not french_three.can_reach(state)
    for _ in range(4):
        state.collect(harness.world.create_item(progressive_civilization_name("french")))
    assert harness.multiworld.get_location(
        civilization_win_location_name("french", 6), 1
    ).can_reach(state)
    assert not harness.multiworld.get_location("AOE4 Goal Achieved", 1).can_reach(state)
    for _ in range(4):
        state.collect(harness.world.create_item(progressive_civilization_name("english")))
    assert harness.multiworld.get_location("AOE4 Goal Achieved", 1).can_reach(state)


def test_unified_items_use_fresh_ids_and_keep_legacy_ids_registered():
    for index, civilization in enumerate(CIVILIZATIONS, start=1):
        assert ITEM_NAME_TO_ID[progressive_civilization_name(civilization)] == (
            ITEM_ID_BASE + 400 + index
        )
        assert civilization_unlock_name(civilization) in ITEM_NAME_TO_ID
        assert progressive_civilization_win_cap_name(civilization) in ITEM_NAME_TO_ID


def test_progressive_items_require_enough_locations():
    with pytest.raises(OptionError, match="progressive civilization"):
        build_world(
            {
                "civilization_pool": ["english", "french"],
                "civ_sanity": False,
                "total_win_goal": 50,
                "win_check_count": 1,
            }
        )
