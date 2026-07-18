from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from BaseClasses import ItemClassification, Region
from Options import OptionError
from worlds.AutoWorld import World
from worlds.generic.Rules import set_rule

from . import items, locations, options
from .constants import (
    CIVILIZATIONS,
    GAME_NAME,
    WORLD_VERSION,
    civilization_location_name,
    civilization_unlock_name,
    civilization_win_location_name,
    win_location_name,
)
from .web import AgeOfEmpiresIVWebWorld


class AgeOfEmpiresIVWorld(World):
    """Honor-system Age of Empires IV randomizer tracked through AOE4World match history."""

    game = GAME_NAME
    web = AgeOfEmpiresIVWebWorld()
    options_dataclass = options.AgeOfEmpiresIVOptions
    options: options.AgeOfEmpiresIVOptions
    item_name_to_id = items.ITEM_NAME_TO_ID
    location_name_to_id = locations.LOCATION_NAME_TO_ID

    civilization_pool: tuple[str, ...]
    goal_civilizations: tuple[str, ...]
    eligible_match_modes: tuple[str, ...]
    starting_civilization: str
    starting_civilizations: tuple[str, ...]
    win_thresholds: tuple[int, ...]
    civ_sanity_enabled: bool
    goal: str

    def generate_early(self) -> None:
        configured_civilization_pool = tuple(
            civilization for civilization in CIVILIZATIONS if civilization in self.options.civilization_pool.value
        )
        self.goal_civilizations = tuple(
            civilization for civilization in CIVILIZATIONS if civilization in self.options.goal_civilizations.value
        )
        self.goal = self.options.goal.current_key
        if self.goal == "civilization_wins":
            if not self.goal_civilizations:
                raise OptionError(
                    f"[{GAME_NAME} - {self.player_name}] civilization_wins requires at least one "
                    "goal_civilization."
                )
            self.civilization_pool = self.goal_civilizations
            active_pool_name = "goal_civilizations"
        else:
            if len(configured_civilization_pool) < 2:
                raise OptionError(
                    f"[{GAME_NAME} - {self.player_name}] civilization_pool must contain at least two "
                    "civilizations for total-win and rank goals."
                )
            self.civilization_pool = configured_civilization_pool
            active_pool_name = "civilization_pool"

        self.eligible_match_modes = tuple(sorted(self.options.eligible_match_modes.value))
        if self.goal == "civilization_wins":
            self.win_thresholds = ()
            self.civ_sanity_enabled = False
        else:
            self.win_thresholds = tuple(
                self.options.win_check_interval.value * index
                for index in range(1, self.options.win_check_count.value + 1)
            )
            self.civ_sanity_enabled = bool(self.options.civ_sanity.value)

        prefix = f"[{GAME_NAME} - {self.player_name}]"
        configured_start = self.options.starting_civilization.current_key
        if configured_start == "random":
            self.starting_civilization = self.random.choice(self.civilization_pool)
        elif configured_start not in self.civilization_pool:
            raise OptionError(
                f"{prefix} starting_civilization '{configured_start}' is not in {active_pool_name}."
            )
        else:
            self.starting_civilization = configured_start

        starting_civs = self.options.starting_civs.value
        if starting_civs > len(self.civilization_pool):
            raise OptionError(
                f"{prefix} starting_civs is {starting_civs}, but {active_pool_name} contains only "
                f"{len(self.civilization_pool)} civilization(s)."
            )
        additional_candidates = [
            civilization
            for civilization in self.civilization_pool
            if civilization != self.starting_civilization
        ]
        additional_starts = self.random.sample(additional_candidates, starting_civs - 1)
        self.starting_civilizations = (
            self.starting_civilization,
            *additional_starts,
        )

        if self.goal == "solo_rank" and "rm_solo" not in self.eligible_match_modes:
            raise OptionError(f"{prefix} solo_rank requires rm_solo in eligible_match_modes.")
        if self.goal == "team_rank" and "rm_team" not in self.eligible_match_modes:
            raise OptionError(f"{prefix} team_rank requires rm_team in eligible_match_modes.")

        if self.goal == "civilization_wins":
            location_count = (
                len(self.goal_civilizations) * self.options.wins_per_goal_civilization.value
            )
        else:
            location_count = len(self.win_thresholds)
        if self.civ_sanity_enabled:
            location_count += len(self.civilization_pool)
        required_unlocks = len(self.civilization_pool) - len(self.starting_civilizations)
        if location_count < required_unlocks:
            raise OptionError(
                f"{prefix} generates {location_count} locations but needs at least {required_unlocks} "
                "locations for civilization unlocks. Increase win_check_count or enable civ_sanity."
            )

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        if self.goal == "civilization_wins":
            menu.add_locations(
                {
                    civilization_win_location_name(civilization, win_number): self.location_name_to_id[
                        civilization_win_location_name(civilization, win_number)
                    ]
                    for civilization in self.goal_civilizations
                    for win_number in range(1, self.options.wins_per_goal_civilization.value + 1)
                },
                locations.AgeOfEmpiresIVLocation,
            )
        elif self.civ_sanity_enabled:
            menu.add_locations(
                {
                    civilization_location_name(civilization): self.location_name_to_id[
                        civilization_location_name(civilization)
                    ]
                    for civilization in self.civilization_pool
                },
                locations.AgeOfEmpiresIVLocation,
            )

        if self.goal != "civilization_wins":
            menu.add_locations(
                {
                    win_location_name(threshold): self.location_name_to_id[win_location_name(threshold)]
                    for threshold in self.win_thresholds
                },
                locations.AgeOfEmpiresIVLocation,
            )
        menu.add_event(
            "AOE4 Goal Achieved",
            "Victory",
            location_type=locations.AgeOfEmpiresIVLocation,
            item_type=items.AgeOfEmpiresIVItem,
        )

    def set_rules(self) -> None:
        if self.goal == "civilization_wins":
            for civilization in self.goal_civilizations:
                for win_number in range(1, self.options.wins_per_goal_civilization.value + 1):
                    set_rule(
                        self.get_location(civilization_win_location_name(civilization, win_number)),
                        lambda state, unlock=civilization_unlock_name(civilization): state.has(
                            unlock, self.player
                        ),
                    )
        elif self.civ_sanity_enabled:
            for civilization in self.civilization_pool:
                set_rule(
                    self.get_location(civilization_location_name(civilization)),
                    lambda state, unlock=civilization_unlock_name(civilization): state.has(unlock, self.player),
                )

        if self.goal == "civilization_wins":
            goal_unlocks = tuple(civilization_unlock_name(civ) for civ in self.goal_civilizations)
            set_rule(
                self.get_location("AOE4 Goal Achieved"),
                lambda state: state.has_all(goal_unlocks, self.player),
            )

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

    def create_items(self) -> None:
        for civilization in self.starting_civilizations:
            self.push_precollected(self.create_item(civilization_unlock_name(civilization)))

        starting_civilizations = set(self.starting_civilizations)
        itempool = [
            self.create_item(civilization_unlock_name(civilization))
            for civilization in self.civilization_pool
            if civilization not in starting_civilizations
        ]
        empty_location_count = len(self.multiworld.get_unfilled_locations(self.player))
        filler_count = empty_location_count - len(itempool)
        if filler_count < 0:
            raise OptionError(
                f"[{GAME_NAME} - {self.player_name}] generated fewer locations than required unlock items."
            )
        itempool.extend(self.create_filler() for _ in range(filler_count))
        self.multiworld.itempool += itempool

    def create_item(self, name: str) -> items.AgeOfEmpiresIVItem:
        return items.create_item(self, name)

    def get_filler_item_name(self) -> str:
        return items.FILLER_ITEM_NAME

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "world_version": WORLD_VERSION,
            "goal": self.goal,
            "total_win_goal": self.options.total_win_goal.value,
            "wins_per_goal_civilization": self.options.wins_per_goal_civilization.value,
            "goal_civilizations": list(self.goal_civilizations),
            "target_rank": self.options.target_rank.current_key,
            "civilization_pool": list(self.civilization_pool),
            "starting_civilization": self.starting_civilization,
            "starting_civs": len(self.starting_civilizations),
            "starting_civilizations": list(self.starting_civilizations),
            "eligible_match_modes": list(self.eligible_match_modes),
            "civ_sanity": self.civ_sanity_enabled,
            "win_check_interval": self.options.win_check_interval.value,
            "win_check_count": self.options.win_check_count.value,
            "win_thresholds": list(self.win_thresholds),
            "include_custom_games": bool(self.options.include_custom_games.value),
            "death_link": bool(self.options.death_link.value),
            "item_name_to_id": {
                civilization: self.item_name_to_id[civilization_unlock_name(civilization)]
                for civilization in self.civilization_pool
            },
            "civilization_location_ids": {
                civilization: self.location_name_to_id[civilization_location_name(civilization)]
                for civilization in self.civilization_pool
            } if self.civ_sanity_enabled else {},
            "win_location_ids": {
                str(threshold): self.location_name_to_id[win_location_name(threshold)]
                for threshold in self.win_thresholds
            },
            "civilization_win_location_ids": {
                civilization: {
                    str(win_number): self.location_name_to_id[
                        civilization_win_location_name(civilization, win_number)
                    ]
                    for win_number in range(1, self.options.wins_per_goal_civilization.value + 1)
                }
                for civilization in self.goal_civilizations
            } if self.goal == "civilization_wins" else {},
        }
