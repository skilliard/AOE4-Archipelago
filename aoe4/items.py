from __future__ import annotations

from BaseClasses import Item, ItemClassification

from .constants import CIVILIZATIONS, GAME_NAME, civilization_unlock_name

ITEM_ID_BASE = 7_410_000
FILLER_ITEM_NAME = "Strategic Insight"

ITEM_NAME_TO_ID = {
    civilization_unlock_name(civilization): ITEM_ID_BASE + index
    for index, civilization in enumerate(CIVILIZATIONS, start=1)
}
ITEM_NAME_TO_ID[FILLER_ITEM_NAME] = ITEM_ID_BASE + 100


class AgeOfEmpiresIVItem(Item):
    game = GAME_NAME


def create_item(world, name: str) -> AgeOfEmpiresIVItem:
    classification = (
        ItemClassification.filler
        if name == FILLER_ITEM_NAME
        else ItemClassification.progression
    )
    return AgeOfEmpiresIVItem(name, classification, ITEM_NAME_TO_ID[name], world.player)

