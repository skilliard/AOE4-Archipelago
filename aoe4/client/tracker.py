from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ..constants import (
    CIVILIZATIONS,
    OBSERVED_RANKS,
    RANKS,
    civilization_location_name,
    civilization_win_location_name,
    win_location_name,
)

DEATH_LINK_WINDOW_SECONDS = 60 * 60


def parse_timestamp(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return float(text)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TrackerConfig:
    profile_id: int
    tracking_started_at: float
    goal: str
    total_win_goal: int
    wins_per_goal_civilization: int
    goal_civilizations: frozenset[str]
    target_rank: str
    civilization_pool: frozenset[str]
    eligible_match_modes: frozenset[str]
    include_custom_games: bool
    api_key_available: bool
    civ_sanity: bool
    win_thresholds: tuple[int, ...]
    death_link: bool
    numbered_civilization_win_checks: bool = False

    @classmethod
    def from_slot_data(
        cls,
        profile_id: int,
        tracking_started_at: float,
        slot_data: Mapping[str, Any],
        api_key_available: bool = False,
    ) -> "TrackerConfig":
        return cls(
            profile_id=profile_id,
            tracking_started_at=tracking_started_at,
            goal=str(slot_data["goal"]),
            total_win_goal=int(slot_data["total_win_goal"]),
            wins_per_goal_civilization=int(slot_data["wins_per_goal_civilization"]),
            goal_civilizations=frozenset(slot_data["goal_civilizations"]),
            target_rank=str(slot_data["target_rank"]),
            civilization_pool=frozenset(slot_data["civilization_pool"]),
            eligible_match_modes=frozenset(slot_data["eligible_match_modes"]),
            include_custom_games=bool(slot_data.get("include_custom_games", False)),
            api_key_available=api_key_available,
            civ_sanity=bool(slot_data["civ_sanity"]),
            win_thresholds=tuple(int(value) for value in slot_data["win_thresholds"]),
            death_link=bool(slot_data["death_link"]),
            numbered_civilization_win_checks=bool(
                slot_data.get("civilization_win_location_ids")
            ),
        )


@dataclass
class TrackerState:
    schema_version: int = 2
    total_wins: int = 0
    civilization_wins: dict[str, int] = field(default_factory=dict)
    seen_game_ids: list[int] = field(default_factory=list)
    completed_checks: list[str] = field(default_factory=list)
    sent_death_game_ids: list[int] = field(default_factory=list)
    cursor_started_at: float | None = None
    credentialed_cursor_started_at: float | None = None
    last_game_id: int | None = None
    last_api_game_signature: str | None = None
    last_game_summary: str = "No eligible match observed"
    solo_rank: str | None = None
    team_rank: str | None = None
    rank_goal_reached: bool = False
    goal_sent: bool = False
    pending_death_received_at: float | None = None
    pending_death_expires_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrackerState":
        fields = cls.__dataclass_fields__
        values = {name: data[name] for name in fields if name in data}
        try:
            schema_version = int(data.get("schema_version", 1))
        except (TypeError, ValueError):
            schema_version = 1
        if schema_version < 2:
            # Version 0.1 always required a key, so its sole cursor is also the
            # correct starting point for credentialed history.
            values["credentialed_cursor_started_at"] = data.get("cursor_started_at")
        values["schema_version"] = 2
        return cls(**values)


@dataclass(frozen=True)
class ParsedMatch:
    game_id: int
    mode: str
    is_custom: bool
    result: str
    civilization: str | None
    completed_at: float
    started_at: float
    ongoing: bool


@dataclass
class TrackingOutcome:
    new_checks: list[str] = field(default_factory=list)
    send_deaths: list[str] = field(default_factory=list)
    goal_reached: bool = False
    processed_game_ids: list[int] = field(default_factory=list)
    suppressed_game_ids: list[int] = field(default_factory=list)
    ignored_locked_wins: list[int] = field(default_factory=list)

    def merge(self, other: "TrackingOutcome") -> None:
        self.new_checks.extend(other.new_checks)
        self.send_deaths.extend(other.send_deaths)
        self.goal_reached = self.goal_reached or other.goal_reached
        self.processed_game_ids.extend(other.processed_game_ids)
        self.suppressed_game_ids.extend(other.suppressed_game_ids)
        self.ignored_locked_wins.extend(other.ignored_locked_wins)


def _iter_players(game: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for team in game.get("teams") or ():
        if isinstance(team, Mapping):
            team = team.get("players") or team.get("team") or ()
        for entry in team or ():
            if not isinstance(entry, Mapping):
                continue
            player = entry.get("player", entry)
            if isinstance(player, Mapping):
                yield player


def parse_match(game: Mapping[str, Any], profile_id: int) -> ParsedMatch | None:
    try:
        game_id = int(game["game_id"])
    except (KeyError, TypeError, ValueError):
        return None

    player = next(
        (
            candidate
            for candidate in _iter_players(game)
            if str(candidate.get("profile_id")) == str(profile_id)
        ),
        None,
    )
    if player is None:
        return None

    started_at = parse_timestamp(game.get("started_at"))
    duration = game.get("duration")
    if started_at is not None and isinstance(duration, (int, float)):
        completed_at = started_at + float(duration)
    else:
        completed_at = parse_timestamp(game.get("updated_at")) or started_at
    if completed_at is None:
        return None

    leaderboard = str(game.get("leaderboard") or "").strip().lower()
    kind = str(game.get("kind") or "").strip().lower()
    is_custom = leaderboard == "custom" or kind == "custom"

    return ParsedMatch(
        game_id=game_id,
        mode="custom" if is_custom else leaderboard or kind,
        is_custom=is_custom,
        result=str(player.get("result") or "unknown").lower(),
        civilization=normalize_civilization(player.get("civilization")),
        completed_at=completed_at,
        started_at=started_at or completed_at,
        ongoing=bool(game.get("ongoing", False)),
    )


def normalize_civilization(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("slug") or value.get("id") or value.get("name")
    if value is None:
        return None
    slug = str(value).strip().lower().replace("'", "").replace(" ", "_").replace("-", "_")
    aliases = {
        "jeanne_darc": "jeanne_darc",
        "zhu_xis_legacy": "zhu_xis_legacy",
    }
    slug = aliases.get(slug, slug)
    return slug if slug in CIVILIZATIONS else None


class MatchTracker:
    def __init__(self, config: TrackerConfig, state: TrackerState | None = None):
        self.config = config
        self.state = state or TrackerState()
        self._seen = set(self.state.seen_game_ids)
        self._checks = set(self.state.completed_checks)
        self._sent_deaths = set(self.state.sent_death_game_ids)

    def receive_death_link(self, received_at: float) -> bool:
        self.expire_death_link(received_at)
        if self.state.pending_death_expires_at is not None:
            return False
        self.state.pending_death_received_at = received_at
        self.state.pending_death_expires_at = received_at + DEATH_LINK_WINDOW_SECONDS
        return True

    def expire_death_link(self, now: float) -> bool:
        expires_at = self.state.pending_death_expires_at
        if expires_at is not None and now >= expires_at:
            self._clear_death_link()
            return True
        return False

    def process_games(
        self,
        games: Iterable[Mapping[str, Any]],
        unlocked_civilizations: set[str] | frozenset[str],
        observed_at: float,
    ) -> TrackingOutcome:
        parsed = [parse_match(game, self.config.profile_id) for game in games]
        matches = sorted((match for match in parsed if match is not None), key=lambda match: (match.completed_at, match.game_id))
        outcome = TrackingOutcome()
        for match in matches:
            outcome.merge(self.process_match(match, unlocked_civilizations, observed_at))
        outcome.goal_reached = outcome.goal_reached or self.goal_reached()
        return outcome

    def process_match(
        self,
        match: ParsedMatch,
        unlocked_civilizations: set[str] | frozenset[str],
        observed_at: float,
    ) -> TrackingOutcome:
        outcome = TrackingOutcome()
        if match.game_id in self._seen or match.ongoing:
            return outcome
        if match.completed_at < self.config.tracking_started_at:
            self._remember_game(match)
            return outcome

        if match.is_custom and self.config.include_custom_games and not self.config.api_key_available:
            # Do not make the game permanently ineligible. A later keyed fetch
            # can retrieve and credit it from the credentialed cursor.
            return outcome

        eligible_mode = (
            self.config.include_custom_games and self.config.api_key_available
            if match.is_custom
            else match.mode in self.config.eligible_match_modes
        )
        if not eligible_mode or match.result not in {"win", "loss"}:
            self._remember_game(match)
            return outcome

        suppressed = self._consume_death_link_if_applicable(match.completed_at)
        if suppressed:
            outcome.suppressed_game_ids.append(match.game_id)

        if match.result == "loss":
            if (
                self.config.death_link
                and match.game_id not in self._sent_deaths
                and 0 <= observed_at - match.completed_at <= DEATH_LINK_WINDOW_SECONDS
            ):
                civilization = CIVILIZATIONS.get(match.civilization or "", "Unknown Civilization")
                outcome.send_deaths.append(f"lost an AOE4 match as {civilization}")
                self._sent_deaths.add(match.game_id)
                self.state.sent_death_game_ids.append(match.game_id)
        elif not suppressed:
            if match.civilization not in unlocked_civilizations:
                outcome.ignored_locked_wins.append(match.game_id)
            elif match.civilization is not None:
                self._credit_win(match.civilization, outcome)

        self._remember_game(match)
        outcome.processed_game_ids.append(match.game_id)
        outcome.goal_reached = self.goal_reached()
        return outcome

    def update_ranks(self, profile: Mapping[str, Any]) -> bool:
        modes = profile.get("modes") or {}
        self.state.solo_rank = _rank_from_mode(modes.get("rm_solo"))
        self.state.team_rank = _rank_from_mode(modes.get("rm_team"))
        if self.config.goal == "solo_rank":
            observed = self.state.solo_rank
        elif self.config.goal == "team_rank":
            observed = self.state.team_rank
        else:
            observed = None
        if observed is not None and rank_at_least(observed, self.config.target_rank):
            self.state.rank_goal_reached = True
        return self.goal_reached()

    def goal_reached(self) -> bool:
        if self.config.goal == "total_wins":
            return self.state.total_wins >= self.config.total_win_goal
        if self.config.goal == "civilization_wins":
            return all(
                self.state.civilization_wins.get(civilization, 0) >= self.config.wins_per_goal_civilization
                for civilization in self.config.goal_civilizations
            )
        if self.config.goal in {"solo_rank", "team_rank"}:
            return self.state.rank_goal_reached
        return False

    def _credit_win(self, civilization: str, outcome: TrackingOutcome) -> None:
        previous_wins = self.state.total_wins
        previous_civilization_wins = self.state.civilization_wins.get(civilization, 0)
        self.state.total_wins += 1
        self.state.civilization_wins[civilization] = previous_civilization_wins + 1

        if (
            self.config.goal == "civilization_wins"
            and self.config.numbered_civilization_win_checks
        ):
            if civilization in self.config.goal_civilizations:
                current_civilization_wins = self.state.civilization_wins[civilization]
                for win_number in range(
                    previous_civilization_wins + 1,
                    min(current_civilization_wins, self.config.wins_per_goal_civilization) + 1,
                ):
                    name = civilization_win_location_name(civilization, win_number)
                    if name not in self._checks:
                        self._add_check(name, outcome)
        else:
            for threshold in self.config.win_thresholds:
                name = win_location_name(threshold)
                if previous_wins < threshold <= self.state.total_wins and name not in self._checks:
                    self._add_check(name, outcome)

            if self.config.civ_sanity:
                name = civilization_location_name(civilization)
                if name not in self._checks:
                    self._add_check(name, outcome)

    def _add_check(self, name: str, outcome: TrackingOutcome) -> None:
        self._checks.add(name)
        self.state.completed_checks.append(name)
        outcome.new_checks.append(name)

    def _remember_game(self, match: ParsedMatch) -> None:
        self._seen.add(match.game_id)
        self.state.seen_game_ids.append(match.game_id)
        self.state.last_game_id = match.game_id
        self.state.last_game_summary = (
            f"{match.result.title()} as {CIVILIZATIONS.get(match.civilization or '', 'Unknown')} "
            f"in {match.mode}"
        )
        if self.state.cursor_started_at is None or match.started_at > self.state.cursor_started_at:
            self.state.cursor_started_at = match.started_at

    def _consume_death_link_if_applicable(self, completion: float) -> bool:
        received = self.state.pending_death_received_at
        expires = self.state.pending_death_expires_at
        if received is None or expires is None:
            return False
        if completion >= expires:
            self._clear_death_link()
            return False
        if completion >= received:
            self._clear_death_link()
            return True
        return False

    def _clear_death_link(self) -> None:
        self.state.pending_death_received_at = None
        self.state.pending_death_expires_at = None


def _rank_from_mode(mode: Any) -> str | None:
    if not isinstance(mode, Mapping):
        return None
    rank = mode.get("rank_level")
    normalized = str(rank).lower() if rank is not None else ""
    return normalized if normalized in OBSERVED_RANKS else None


def rank_at_least(observed: str, target: str) -> bool:
    try:
        return OBSERVED_RANKS.index(observed) >= RANKS.index(target)
    except ValueError:
        return False
