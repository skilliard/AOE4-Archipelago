from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld

from .constants import GAME_NAME
from .options import option_groups, option_presets


class AgeOfEmpiresIVWebWorld(WebWorld):
    game = GAME_NAME
    theme = "stone"
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "Install and use the Age of Empires IV APWorld and tracking client.",
            "English",
            "setup_en.md",
            "setup/en",
            ["AOE4 Archipelago contributors"],
        )
    ]
    option_groups = option_groups
    options_presets = option_presets

