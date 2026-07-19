from __future__ import annotations

from BaseClasses import Item, ItemClassification

from .constants import (
    CIVILIZATIONS,
    GAME_NAME,
    PROGRESSIVE_TOTAL_WIN_CAP,
    civilization_unlock_name,
    progressive_civilization_name,
    progressive_civilization_win_cap_name,
)

ITEM_ID_BASE = 7_410_000
FILLER_ITEM_NAME = "Strategic Insight"

ITEM_NAME_TO_ID = {
    civilization_unlock_name(civilization): ITEM_ID_BASE + index
    for index, civilization in enumerate(CIVILIZATIONS, start=1)
}
ITEM_NAME_TO_ID[FILLER_ITEM_NAME] = ITEM_ID_BASE + 100
ITEM_NAME_TO_ID[PROGRESSIVE_TOTAL_WIN_CAP] = ITEM_ID_BASE + 200
# Keep the 0.4/0.5.0 civilization IDs registered so legacy seed data remains
# decodable. New worlds generate only the unified +400 progressive items.
ITEM_NAME_TO_ID.update(
    {
        progressive_civilization_win_cap_name(civilization): ITEM_ID_BASE + 300 + index
        for index, civilization in enumerate(CIVILIZATIONS, start=1)
    }
)
ITEM_NAME_TO_ID.update(
    {
        progressive_civilization_name(civilization): ITEM_ID_BASE + 400 + index
        for index, civilization in enumerate(CIVILIZATIONS, start=1)
    }
)


class AgeOfEmpiresIVItem(Item):
    game = GAME_NAME


def create_item(world, name: str) -> AgeOfEmpiresIVItem:
    classification = (
        ItemClassification.filler
        if name == FILLER_ITEM_NAME
        else ItemClassification.progression
    )
    return AgeOfEmpiresIVItem(name, classification, ITEM_NAME_TO_ID[name], world.player)
