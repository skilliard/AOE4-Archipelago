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
    PROGRESSIVE_TOTAL_WIN_CAP,
    WORLD_VERSION,
    civilization_location_name,
    civilization_win_location_name,
    progressive_civilization_name,
    progressive_items_required,
    progressive_win_cap_stages,
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
    total_win_cap_stages: tuple[int, ...]
    civilization_win_cap_stages: tuple[int, ...]
    civilization_progression_tiers: int
    civilization_win_check_count: int
    civ_sanity_win_count: int
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
            self.civ_sanity_win_count = 0
            self.civilization_win_check_count = self.options.wins_per_goal_civilization.value
        else:
            self.win_thresholds = tuple(
                self.options.win_check_interval.value * index
                for index in range(1, self.options.win_check_count.value + 1)
            )
            self.civ_sanity_enabled = bool(self.options.civ_sanity.value)
            self.civ_sanity_win_count = (
                self.options.civ_sanity_win_count.value if self.civ_sanity_enabled else 0
            )
            self.civilization_win_check_count = self.civ_sanity_win_count

        if self.goal == "civilization_wins":
            total_win_cap_target = 0
        else:
            highest_win_check = self.win_thresholds[-1]
            total_win_cap_target = (
                max(highest_win_check, self.options.total_win_goal.value)
                if self.goal == "total_wins"
                else highest_win_check
            )
        self.total_win_cap_stages = progressive_win_cap_stages(total_win_cap_target)
        self.civilization_win_cap_stages = progressive_win_cap_stages(
            self.civilization_win_check_count
        )
        self.civilization_progression_tiers = max(
            1, len(self.civilization_win_cap_stages)
        )

        prefix = f"[{GAME_NAME} - {self.player_name}]"
        explicit_starts = tuple(
            civilization
            for civilization in CIVILIZATIONS
            if civilization in self.options.starting_civilizations.value
        )
        if explicit_starts:
            if len(explicit_starts) > 5:
                raise OptionError(f"{prefix} starting_civilizations may contain at most 5 civilizations.")
            invalid_starts = tuple(
                civilization for civilization in explicit_starts if civilization not in self.civilization_pool
            )
            if invalid_starts:
                raise OptionError(
                    f"{prefix} starting_civilizations contains civilizations outside {active_pool_name}: "
                    f"{', '.join(invalid_starts)}."
                )
            self.starting_civilizations = explicit_starts
            self.starting_civilization = explicit_starts[0]
        else:
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

        location_count = len(self.win_thresholds)
        if self.civilization_win_check_count:
            location_count += len(self.civilization_pool) * self.civilization_win_check_count
        required_unlocks = len(self.civilization_pool) - len(self.starting_civilizations)
        required_progression_items = (
            required_unlocks
            + max(0, len(self.total_win_cap_stages) - 1)
            + len(self.civilization_pool) * (self.civilization_progression_tiers - 1)
        )
        if location_count < required_progression_items:
            raise OptionError(
                f"{prefix} generates {location_count} locations but needs at least "
                f"{required_progression_items} locations for progressive civilization and win-cap items. "
                "Increase win_check_count or civilization win checks, enable civ_sanity, or add starting civilizations."
            )

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        if self.civilization_win_check_count > 1 or self.goal == "civilization_wins":
            menu.add_locations(
                {
                    civilization_win_location_name(civilization, win_number): self.location_name_to_id[
                        civilization_win_location_name(civilization, win_number)
                    ]
                    for civilization in self.civilization_pool
                    for win_number in range(1, self.civilization_win_check_count + 1)
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
        if self.civilization_win_check_count > 1 or self.goal == "civilization_wins":
            for civilization in self.civilization_pool:
                for win_number in range(1, self.civilization_win_check_count + 1):
                    cap_items = progressive_items_required(
                        win_number, self.civilization_win_cap_stages
                    )
                    set_rule(
                        self.get_location(civilization_win_location_name(civilization, win_number)),
                        lambda state,
                        progressive_name=progressive_civilization_name(civilization),
                        tier=cap_items + 1: state.has(
                            progressive_name, self.player, tier
                        ),
                    )
        elif self.civ_sanity_enabled:
            for civilization in self.civilization_pool:
                set_rule(
                    self.get_location(civilization_location_name(civilization)),
                    lambda state,
                    progressive_name=progressive_civilization_name(civilization): state.has(
                        progressive_name, self.player
                    ),
                )

        for threshold in self.win_thresholds:
            cap_items = progressive_items_required(threshold, self.total_win_cap_stages)
            set_rule(
                self.get_location(win_location_name(threshold)),
                lambda state, cap_count=cap_items: state.has(
                    PROGRESSIVE_TOTAL_WIN_CAP, self.player, cap_count
                ),
            )

        if self.goal == "civilization_wins":
            progressive_names = tuple(
                progressive_civilization_name(civ) for civ in self.goal_civilizations
            )
            set_rule(
                self.get_location("AOE4 Goal Achieved"),
                lambda state: all(
                    state.has(
                        progressive_name,
                        self.player,
                        self.civilization_progression_tiers,
                    )
                    for progressive_name in progressive_names
                ),
            )
        elif self.goal == "total_wins":
            goal_cap_items = progressive_items_required(
                self.options.total_win_goal.value, self.total_win_cap_stages
            )
            set_rule(
                self.get_location("AOE4 Goal Achieved"),
                lambda state: state.has(
                    PROGRESSIVE_TOTAL_WIN_CAP, self.player, goal_cap_items
                ),
            )

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

    def create_items(self) -> None:
        for civilization in self.starting_civilizations:
            self.push_precollected(
                self.create_item(progressive_civilization_name(civilization))
            )

        starting_civilizations = set(self.starting_civilizations)
        itempool = [
            self.create_item(progressive_civilization_name(civilization))
            for civilization in self.civilization_pool
            for _ in range(
                self.civilization_progression_tiers
                - int(civilization in starting_civilizations)
            )
        ]
        itempool.extend(
            self.create_item(PROGRESSIVE_TOTAL_WIN_CAP)
            for _ in range(max(0, len(self.total_win_cap_stages) - 1))
        )
        empty_location_count = len(self.multiworld.get_unfilled_locations(self.player))
        filler_count = empty_location_count - len(itempool)
        if filler_count < 0:
            raise OptionError(
                f"[{GAME_NAME} - {self.player_name}] generated fewer locations than required progression items."
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
            "civ_sanity_win_count": self.civ_sanity_win_count,
            "win_check_interval": self.options.win_check_interval.value,
            "win_check_count": self.options.win_check_count.value,
            "win_thresholds": list(self.win_thresholds),
            "total_win_cap_stages": list(self.total_win_cap_stages),
            "civilization_win_cap_stages": list(self.civilization_win_cap_stages),
            "include_custom_games": bool(self.options.include_custom_games.value),
            "death_link": bool(self.options.death_link.value),
            "progressive_civilization_item_ids": {
                civilization: self.item_name_to_id[
                    progressive_civilization_name(civilization)
                ]
                for civilization in self.civilization_pool
            },
            "progressive_total_win_cap_item_id": self.item_name_to_id[
                PROGRESSIVE_TOTAL_WIN_CAP
            ] if self.total_win_cap_stages else None,
            "civilization_location_ids": {
                civilization: self.location_name_to_id[civilization_location_name(civilization)]
                for civilization in self.civilization_pool
            } if self.civ_sanity_enabled and self.civilization_win_check_count == 1 else {},
            "win_location_ids": {
                str(threshold): self.location_name_to_id[win_location_name(threshold)]
                for threshold in self.win_thresholds
            },
            "civilization_win_location_ids": {
                civilization: {
                    str(win_number): self.location_name_to_id[
                        civilization_win_location_name(civilization, win_number)
                    ]
                    for win_number in range(1, self.civilization_win_check_count + 1)
                }
                for civilization in self.civilization_pool
            } if self.civilization_win_check_count > 1 or self.goal == "civilization_wins" else {},
        }
