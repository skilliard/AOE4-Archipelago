from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..constants import CIVILIZATIONS


# File names from AOE4World Explorer's civilization flag asset set. Keeping
# this mapping explicit makes future roster updates fail visibly in tests.
CIVILIZATION_FLAG_FILES: dict[str, str] = {
    "abbasid_dynasty": "abbasid.png",
    "ayyubids": "ayyubids.png",
    "byzantines": "byzantines.png",
    "chinese": "chinese.png",
    "delhi_sultanate": "delhi.png",
    "english": "english.png",
    "french": "french.png",
    "golden_horde": "goldenhorde.png",
    "house_of_lancaster": "lancaster.png",
    "holy_roman_empire": "hre.png",
    "japanese": "japanese.png",
    "jeanne_darc": "jeannedarc.png",
    "jin_dynasty": "jindynasty.png",
    "knights_templar": "templar.png",
    "macedonian_dynasty": "macedonian.png",
    "malians": "malians.png",
    "mongols": "mongols.png",
    "order_of_the_dragon": "orderofthedragon.png",
    "ottomans": "ottomans.png",
    "rus": "rus.png",
    "sengoku_daimyo": "sengoku.png",
    "tughlaq_dynasty": "tughlaq.png",
    "zhu_xis_legacy": "zhuxi.png",
}


@dataclass(frozen=True)
class CivilizationTrackerEntry:
    civilization: str
    name: str
    unlocked: bool
    credited_wins: int
    required_wins: int

    @property
    def wins_remaining(self) -> int:
        return max(0, self.required_wins - self.credited_wins)

    @property
    def requirement_complete(self) -> bool:
        return self.wins_remaining == 0


def build_civilization_tracker_entries(
    slot_data: Mapping[str, Any],
    unlocked_civilizations: Iterable[str],
    civilization_wins: Mapping[str, int],
) -> tuple[CivilizationTrackerEntry, ...]:
    """Build the read-only civilization progress shown in the Tracker tab.

    Civilization-win seeds use their goal list as the effective pool and show
    the configured numbered-win target. Other goals show the optional
    civ-sanity first-win requirement for their civilization pool.
    """

    pool = {str(civilization) for civilization in slot_data.get("civilization_pool", ())}
    unlocked = set(unlocked_civilizations).intersection(pool)
    goal_civilizations = {
        str(civilization) for civilization in slot_data.get("goal_civilizations", ())
    }
    per_goal_target = int(slot_data.get("wins_per_goal_civilization", 1))
    civilization_goal = slot_data.get("goal") == "civilization_wins"
    civ_sanity = bool(slot_data.get("civ_sanity", False))

    entries: list[CivilizationTrackerEntry] = []
    for civilization, name in CIVILIZATIONS.items():
        if civilization not in pool:
            continue
        required_wins = 1 if civ_sanity else 0
        if civilization_goal and civilization in goal_civilizations:
            required_wins = max(required_wins, per_goal_target)
        entries.append(
            CivilizationTrackerEntry(
                civilization=civilization,
                name=name,
                unlocked=civilization in unlocked,
                credited_wins=max(0, int(civilization_wins.get(civilization, 0))),
                required_wins=required_wins,
            )
        )
    return tuple(entries)
