from __future__ import annotations

from BaseClasses import Location

from .constants import (
    CIVILIZATIONS,
    GAME_NAME,
    civilization_location_name,
    civilization_win_location_name,
    win_location_name,
)

CIVILIZATION_LOCATION_ID_BASE = 7_411_000
WIN_LOCATION_ID_BASE = 7_412_000
CIVILIZATION_WIN_LOCATION_ID_BASE = 7_420_000
MAX_WIN_THRESHOLD = 50 * 100
MAX_WINS_PER_GOAL_CIVILIZATION = 50

LOCATION_NAME_TO_ID = {
    civilization_location_name(civilization): CIVILIZATION_LOCATION_ID_BASE + index
    for index, civilization in enumerate(CIVILIZATIONS, start=1)
}
LOCATION_NAME_TO_ID.update(
    {win_location_name(wins): WIN_LOCATION_ID_BASE + wins for wins in range(1, MAX_WIN_THRESHOLD + 1)}
)
LOCATION_NAME_TO_ID.update(
    {
        civilization_win_location_name(civilization, win_number): (
            CIVILIZATION_WIN_LOCATION_ID_BASE
            + civilization_index * MAX_WINS_PER_GOAL_CIVILIZATION
            + win_number
        )
        for civilization_index, civilization in enumerate(CIVILIZATIONS)
        for win_number in range(1, MAX_WINS_PER_GOAL_CIVILIZATION + 1)
    }
)


class AgeOfEmpiresIVLocation(Location):
    game = GAME_NAME
