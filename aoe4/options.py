from __future__ import annotations

from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, OptionGroup, OptionSet, PerGameCommonOptions, Range, TextChoice, Toggle

from .constants import CIVILIZATIONS, ELIGIBLE_MATCH_MODES


class Goal(Choice):
    """The achievement that completes the slot."""
    display_name = "Goal"
    option_total_wins = 0
    option_solo_rank = 1
    option_team_rank = 2
    option_civilization_wins = 3
    default = option_total_wins


class TotalWinGoal(Range):
    """Number of credited victories required for the total-wins goal."""
    display_name = "Total Win Goal"
    range_start = 1
    range_end = 500
    default = 20


class WinsPerGoalCivilization(Range):
    """Victories required with every selected goal civilization."""
    display_name = "Wins Per Goal Civilization"
    range_start = 1
    range_end = 50
    default = 3


class GoalCivilizations(OptionSet):
    """Civilizations unlocked and required when the goal is civilization wins. Civilization pool is then ignored."""
    display_name = "Goal Civilizations"
    valid_keys = frozenset(CIVILIZATIONS)
    default = frozenset({"english"})


class TargetRank(Choice):
    """Rank which must be observed for the selected ranked goal. Rank completion is permanent."""
    display_name = "Target Rank"
    option_bronze_1 = 0
    option_bronze_2 = 1
    option_bronze_3 = 2
    option_silver_1 = 3
    option_silver_2 = 4
    option_silver_3 = 5
    option_gold_1 = 6
    option_gold_2 = 7
    option_gold_3 = 8
    option_platinum_1 = 9
    option_platinum_2 = 10
    option_platinum_3 = 11
    option_diamond_1 = 12
    option_diamond_2 = 13
    option_diamond_3 = 14
    option_conqueror_1 = 15
    option_conqueror_2 = 16
    option_conqueror_3 = 17
    default = option_gold_1


class CivilizationPool(OptionSet):
    """Civilizations unlocked for total-wins and rank goals. Ignored by the civilization-wins goal."""
    display_name = "Civilization Pool"
    valid_keys = frozenset(CIVILIZATIONS)
    default = frozenset(CIVILIZATIONS)


class StartingCivilization(TextChoice):
    """A guaranteed starting unlock. Random uses the active goal-dependent civilization pool."""
    display_name = "Starting Civilization"
    option_abbasid_dynasty = 0
    option_ayyubids = 1
    option_byzantines = 2
    option_chinese = 3
    option_delhi_sultanate = 4
    option_english = 5
    option_french = 6
    option_golden_horde = 7
    option_house_of_lancaster = 8
    option_holy_roman_empire = 9
    option_japanese = 10
    option_jeanne_darc = 11
    option_jin_dynasty = 12
    option_knights_templar = 13
    option_macedonian_dynasty = 14
    option_malians = 15
    option_mongols = 16
    option_order_of_the_dragon = 17
    option_ottomans = 18
    option_rus = 19
    option_sengoku_daimyo = 20
    option_tughlaq_dynasty = 21
    option_zhu_xis_legacy = 22
    default = "random"

    @classmethod
    def from_text(cls, text: str):
        # Choice reserves the word "random" for an immediate roll across every option.
        # Preserve it so generate_early can roll only within the goal's active civilization set.
        if text.lower() == "random":
            return cls("random")
        return super().from_text(text)


class StartingCivilizations(Range):
    """Number of civilizations to start unlocked from the active goal-dependent pool."""
    display_name = "Starting Civilizations"
    range_start = 1
    range_end = len(CIVILIZATIONS)
    default = 1


class EligibleMatchModes(OptionSet):
    """Standard queues which can produce wins, losses, checks, and DeathLinks."""
    display_name = "Eligible Match Modes"
    valid_keys = frozenset(ELIGIBLE_MATCH_MODES)
    default = frozenset(ELIGIBLE_MATCH_MODES)


class CivilizationSanity(DefaultOnToggle):
    """Add a first-win check per pool civilization for total-win/rank goals. Civilization-win goals ignore this."""
    display_name = "Civilization Sanity"


class WinCheckInterval(Range):
    """Credited victories between total-win checks. Civilization-win goals use numbered per-civ checks instead."""
    display_name = "Win Check Interval"
    range_start = 1
    range_end = 50
    default = 1


class WinCheckCount(Range):
    """Number of total-win milestone checks. Ignored by civilization-win goals."""
    display_name = "Win Check Count"
    range_start = 1
    range_end = 100
    default = 25


class IncludeCustomGames(Toggle):
    """Count completed custom games when the client has a session-only AOE4World API key."""
    display_name = "Include Custom Games"


class DeathLink(Toggle):
    """Send a DeathLink on eligible losses and suppress one eligible match after a received DeathLink."""
    display_name = "Death Link"


@dataclass
class AgeOfEmpiresIVOptions(PerGameCommonOptions):
    goal: Goal
    total_win_goal: TotalWinGoal
    wins_per_goal_civilization: WinsPerGoalCivilization
    goal_civilizations: GoalCivilizations
    target_rank: TargetRank
    civilization_pool: CivilizationPool
    starting_civilization: StartingCivilization
    starting_civs: StartingCivilizations
    eligible_match_modes: EligibleMatchModes
    civ_sanity: CivilizationSanity
    win_check_interval: WinCheckInterval
    win_check_count: WinCheckCount
    include_custom_games: IncludeCustomGames
    death_link: DeathLink


option_groups = [
    OptionGroup("Goal", [Goal, TotalWinGoal, WinsPerGoalCivilization, GoalCivilizations, TargetRank]),
    OptionGroup(
        "Civilizations",
        [CivilizationPool, StartingCivilization, StartingCivilizations, CivilizationSanity],
    ),
    OptionGroup(
        "Match Tracking",
        [EligibleMatchModes, WinCheckInterval, WinCheckCount, IncludeCustomGames, DeathLink],
    ),
]


option_presets = {
    "Standard": {
        "goal": "total_wins",
        "total_win_goal": 20,
        "starting_civilization": "random",
        "starting_civs": 1,
        "civ_sanity": True,
        "win_check_interval": 1,
        "win_check_count": 25,
        "include_custom_games": False,
        "death_link": False,
    },
    "Civilization Gauntlet": {
        "goal": "civilization_wins",
        "goal_civilizations": list(CIVILIZATIONS),
        "wins_per_goal_civilization": 1,
        "starting_civilization": "random",
        "starting_civs": 1,
        "civ_sanity": False,
        "include_custom_games": False,
    },
    "Ranked Climb": {
        "goal": "solo_rank",
        "target_rank": "gold_1",
        "eligible_match_modes": ["rm_solo"],
        "starting_civilization": "random",
        "starting_civs": 1,
        "win_check_interval": 1,
        "win_check_count": 25,
        "include_custom_games": False,
    },
}
