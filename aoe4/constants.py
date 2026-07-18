from __future__ import annotations

from collections import OrderedDict

GAME_NAME = "Age of Empires IV"
WORLD_VERSION = "0.4.0"
MINIMUM_AP_VERSION = "0.6.7"

# Stable YAML/API identifiers mapped to the names shown by AOE4World and the AP client.
CIVILIZATIONS: OrderedDict[str, str] = OrderedDict(
    (
        ("abbasid_dynasty", "Abbasid Dynasty"),
        ("ayyubids", "Ayyubids"),
        ("byzantines", "Byzantines"),
        ("chinese", "Chinese"),
        ("delhi_sultanate", "Delhi Sultanate"),
        ("english", "English"),
        ("french", "French"),
        ("golden_horde", "Golden Horde"),
        ("house_of_lancaster", "House of Lancaster"),
        ("holy_roman_empire", "Holy Roman Empire"),
        ("japanese", "Japanese"),
        ("jeanne_darc", "Jeanne d'Arc"),
        ("jin_dynasty", "Jin Dynasty"),
        ("knights_templar", "Knights Templar"),
        ("macedonian_dynasty", "Macedonian Dynasty"),
        ("malians", "Malians"),
        ("mongols", "Mongols"),
        ("order_of_the_dragon", "Order of the Dragon"),
        ("ottomans", "Ottomans"),
        ("rus", "Rus"),
        ("sengoku_daimyo", "Sengoku Daimyo"),
        ("tughlaq_dynasty", "Tughlaq Dynasty"),
        ("zhu_xis_legacy", "Zhu Xi's Legacy"),
    )
)

CIVILIZATION_ALIASES = {
    "abbasid": "abbasid_dynasty",
    "delhi": "delhi_sultanate",
    "hre": "holy_roman_empire",
    "jeanne_d_arc": "jeanne_darc",
    "jeanne": "jeanne_darc",
    "order_dragon": "order_of_the_dragon",
    "zhu_xi": "zhu_xis_legacy",
}

ELIGIBLE_MATCH_MODES = (
    "rm_solo",
    "rm_team",
    "qm_1v1",
    "qm_2v2",
    "qm_3v3",
    "qm_4v4",
)

RANKS = (
    "bronze_1", "bronze_2", "bronze_3",
    "silver_1", "silver_2", "silver_3",
    "gold_1", "gold_2", "gold_3",
    "platinum_1", "platinum_2", "platinum_3",
    "diamond_1", "diamond_2", "diamond_3",
    "conqueror_1", "conqueror_2", "conqueror_3",
)

# AOE4World may report a non-selectable tier above the pinned goal roster. It
# still satisfies every selectable target because rank goals use >= semantics.
OBSERVED_RANKS = RANKS + ("conqueror_4",)

RANK_DISPLAY_NAMES = {
    rank: rank.replace("_", " ").title().replace(" 1", " I").replace(" 2", " II").replace(" 3", " III")
    for rank in OBSERVED_RANKS
}
RANK_DISPLAY_NAMES["conqueror_4"] = "Conqueror IV"


def civilization_unlock_name(civilization: str) -> str:
    return f"{CIVILIZATIONS[civilization]} Civilization Unlock"


def civilization_location_name(civilization: str) -> str:
    return f"Civilization Victory: {CIVILIZATIONS[civilization]}"


def civilization_win_location_name(civilization: str, win_number: int) -> str:
    return f"{CIVILIZATIONS[civilization]} Win {win_number}"


def win_location_name(wins: int) -> str:
    return f"Win {wins} {'Match' if wins == 1 else 'Matches'}"
