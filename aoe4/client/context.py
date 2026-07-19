from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, logger
from NetUtils import ClientStatus

from ..constants import (
    CIVILIZATIONS,
    GAME_NAME,
    RANK_DISPLAY_NAMES,
    civilization_win_location_name,
)
from .api import AOE4WorldClient, AOE4WorldError
from .state import ProfileStore, StateStore, state_key
from .tracker import MatchTracker, TrackerConfig, TrackingOutcome, format_timestamp
from .tracker_view import CivilizationTrackerEntry, build_civilization_tracker_entries

POLL_INTERVAL_SECONDS = 60
CURSOR_OVERLAP_SECONDS = 120
MAX_BACKOFF_SECONDS = 15 * 60


class ProfileBindingError(RuntimeError):
    pass


class ProfileRebindError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProfileRebindPreview:
    old_profile_id: int
    new_profile_id: int
    new_profile_name: str
    team: int
    slot: int
    connected_nonce: int
    confirmed_checks: int
    goal_completed: bool


class AgeOfEmpiresIVCommandProcessor(ClientCommandProcessor):
    ctx: "AgeOfEmpiresIVContext"

    def _cmd_aoe4(self) -> bool:
        """Display AOE4World tracking status. Credentials are entered only in the AOE4 tab."""
        for line in self.ctx.status_lines():
            self.output(line)
        return True


class AgeOfEmpiresIVContext(CommonContext):
    game = GAME_NAME
    # Starting civilization tiers come from slot data. Excluding precollected
    # items here prevents those tiers from also appearing in items_received.
    items_handling = 0b011
    command_processor = AgeOfEmpiresIVCommandProcessor

    def __init__(
        self,
        server_address: str | None = None,
        password: str | None = None,
        initial_profile_id: int | None = None,
    ) -> None:
        super().__init__(server_address, password)
        data_directory = Path(Utils.user_path("aoe4"))
        self.profile_store = ProfileStore(data_directory / "profile.json")
        self.state_store = StateStore(data_directory / "state")

        self.slot_data: dict[str, Any] = {}
        self.profile_id = initial_profile_id or self.profile_store.load()
        self.bound_profile_id: int | None = None
        self._api_key: str | None = None
        self._api: AOE4WorldClient | None = None
        self.tracker: MatchTracker | None = None
        self._state_file_key: str | None = None

        self.api_health = "Profile ready; waiting for AP connection" if self.profile_id else "Waiting for profile ID"
        self.binding_status = "Not bound"
        self.next_poll_at = 0.0
        self._backoff_seconds = POLL_INTERVAL_SECONDS
        self._force_incremental_fetch = True
        self._connected_nonce = 0
        self._credentials_nonce = 0
        self._initialized_token: tuple[int, int] | None = None
        self._tracking_blocked = False
        self._storage_waiters: dict[str, asyncio.Future[Any]] = {}
        self._queued_death_received_at: float | None = None
        self._tracking_task: asyncio.Task[None] | None = None
        self._cap_inventory_dirty = True

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect(game=self.game)

    def make_gui(self):
        from .ui import AgeOfEmpiresIVManager

        return AgeOfEmpiresIVManager

    def configure_credentials(self, profile_id_text: str, api_key: str) -> tuple[bool, str]:
        try:
            profile_id = int(profile_id_text.strip())
            if profile_id <= 0:
                raise ValueError
        except ValueError:
            return False, "Profile ID must be a positive number."
        normalized_key = api_key.strip() or None
        changed = profile_id != self.profile_id or normalized_key != self._api_key
        self.profile_id = profile_id
        self._api_key = normalized_key
        self.api_health = "Profile ready; waiting for AP connection"
        if changed:
            self._credentials_nonce += 1
            self._initialized_token = None
            self._api = None
            self.tracker = None
            self._state_file_key = None
            self._force_incremental_fetch = True
            self._tracking_blocked = False
            self.next_poll_at = 0.0
        if self._api_key:
            return True, "Profile accepted. Optional API key enabled for this launch."
        return True, "Profile accepted. Public standard-game tracking does not require an API key."

    async def prepare_profile_rebind(
        self,
        profile_id_text: str,
        api_key: str,
    ) -> ProfileRebindPreview:
        if not self.server or self.slot is None or self.team is None or not self.slot_data:
            raise ProfileRebindError("Connect to the Archipelago slot before correcting its profile.")
        if self.bound_profile_id is None:
            raise ProfileRebindError("Wait for the current AP profile binding to finish loading.")
        try:
            new_profile_id = int(profile_id_text.strip())
            if new_profile_id <= 0:
                raise ValueError
        except ValueError:
            raise ProfileRebindError("Profile ID must be a positive number.") from None
        if new_profile_id == self.bound_profile_id:
            raise ProfileRebindError(f"Profile {new_profile_id} is already bound to this AP slot.")

        api = AOE4WorldClient(api_key.strip() or None)
        try:
            profile = await api.profile(new_profile_id)
        except AOE4WorldError as error:
            raise ProfileRebindError(str(error)) from None
        try:
            returned_profile_id = int(profile.get("profile_id", -1))
        except (TypeError, ValueError):
            returned_profile_id = -1
        if returned_profile_id != new_profile_id:
            raise ProfileRebindError("AOE4World profile response did not match the requested profile.")
        profile_name = str(profile.get("name") or "Unknown player")
        return ProfileRebindPreview(
            old_profile_id=self.bound_profile_id,
            new_profile_id=new_profile_id,
            new_profile_name=profile_name,
            team=int(self.team),
            slot=int(self.slot),
            connected_nonce=self._connected_nonce,
            confirmed_checks=len(self._configured_location_ids().intersection(self.checked_locations)),
            goal_completed=bool(
                self.finished_game or (self.tracker is not None and self.tracker.state.goal_sent)
            ),
        )

    async def rebind_profile(self, preview: ProfileRebindPreview, api_key: str) -> str:
        if (
            not self.server
            or self.slot is None
            or self.team is None
            or int(self.team) != preview.team
            or int(self.slot) != preview.slot
            or self._connected_nonce != preview.connected_nonce
        ):
            raise ProfileRebindError("The AP connection changed. Validate the corrected profile again.")
        if self.bound_profile_id != preview.old_profile_id:
            raise ProfileRebindError("The stored profile binding changed. Validate the corrected profile again.")

        try:
            replaced_value = await self._set_storage_value(
                self._profile_storage_key(),
                preview.old_profile_id,
                [{"operation": "replace", "value": preview.new_profile_id}],
            )
        except asyncio.TimeoutError:
            self.bound_profile_id = None
            self._tracking_blocked = True
            self._initialized_token = None
            self.binding_status = "Profile correction result uncertain; reconnect to reload the server binding"
            raise ProfileRebindError(
                "The server did not confirm the correction. Reconnect before trying again; the server may have applied it."
            ) from None

        try:
            stored_profile_id = int(replaced_value)
        except (TypeError, ValueError):
            stored_profile_id = -1
        if stored_profile_id != preview.new_profile_id:
            raise ProfileRebindError("The server did not store the corrected profile ID.")

        pending_death_received_at = None
        if self.tracker is not None and self.tracker.state.pending_death_expires_at is not None:
            pending_death_received_at = self.tracker.state.pending_death_received_at

        normalized_key = api_key.strip() or None
        self.profile_id = preview.new_profile_id
        self.bound_profile_id = preview.new_profile_id
        self._api_key = normalized_key
        self.profile_store.save(preview.new_profile_id)
        self._credentials_nonce += 1
        self._initialized_token = None
        self._api = None
        self.tracker = None
        self._state_file_key = None
        self._force_incremental_fetch = True
        self._tracking_blocked = False
        self._queued_death_received_at = pending_death_received_at
        self.next_poll_at = 0.0
        self._backoff_seconds = POLL_INTERVAL_SECONDS
        self.binding_status = (
            f"Profile corrected from {preview.old_profile_id} to {preview.new_profile_id}; reinitializing"
        )
        self.api_health = "Profile correction confirmed; syncing match history"

        audit_record = {
            "old_profile_id": preview.old_profile_id,
            "new_profile_id": preview.new_profile_id,
            "changed_at": format_timestamp(time.time()),
            "team": preview.team,
            "slot": preview.slot,
        }
        try:
            await self._set_storage_value(
                self._profile_history_storage_key(),
                [],
                [{"operation": "add", "value": [audit_record]}],
            )
        except asyncio.TimeoutError:
            logger.warning(
                "AOE4 profile correction succeeded, but the audit-history reply timed out for team %d slot %d.",
                preview.team,
                preview.slot,
            )
            return "Profile corrected. Audit-history confirmation timed out; tracking will resync automatically."

        logger.info(
            "AOE4 profile binding corrected from %d to %d for team %d slot %d.",
            preview.old_profile_id,
            preview.new_profile_id,
            preview.team,
            preview.slot,
        )
        return "Profile corrected and audit history recorded. Match history will resync automatically."

    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        if cmd == "RoomInfo":
            self.seed_name = args.get("seed_name")
        elif cmd == "Connected":
            self.slot_data = dict(args.get("slot_data") or {})
            self.bound_profile_id = None
            self._connected_nonce += 1
            self._initialized_token = None
            self._tracking_blocked = False
            self._force_incremental_fetch = True
            self._cap_inventory_dirty = True
            death_link = bool(self.slot_data.get("death_link", False))
            asyncio.create_task(self.update_death_link(death_link), name="AOE4 DeathLink tag update")
            if not death_link:
                self._queued_death_received_at = None
        elif cmd == "ReceivedItems":
            # CommonContext updates items_received before dispatching this hook.
            self._cap_inventory_dirty = True
        elif cmd == "SetReply":
            future = self._storage_waiters.pop(args.get("key"), None)
            if future is not None and not future.done():
                future.set_result(args.get("value"))

    def on_deathlink(self, data: dict[str, Any]) -> None:
        super().on_deathlink(data)
        if not self.slot_data.get("death_link", False):
            return
        received_at = time.time()
        if self.tracker is not None:
            if self.tracker.receive_death_link(received_at):
                logger.info("AOE4 DeathLink suppression armed for one hour.")
                self._save_state()
            else:
                logger.info("AOE4 DeathLink suppression is already pending; additional death ignored.")
        elif self._queued_death_received_at is None:
            self._queued_death_received_at = received_at

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        # Prevent CommonClient from forwarding a completed status to a different
        # room/slot before its own persisted tracker state has been loaded.
        self.finished_game = False
        await super().disconnect(allow_autoreconnect)

    async def tracking_loop(self) -> None:
        self._tracking_task = asyncio.current_task()
        while not self.exit_event.is_set():
            try:
                if self._ready_to_track():
                    token = (self._connected_nonce, self._credentials_nonce)
                    if self._initialized_token != token:
                        await self._initialize_tracking(token)
                    if self._initialized_token == token:
                        if self._cap_inventory_dirty:
                            await self._reconcile_cap_inventory()
                        if time.time() >= self.next_poll_at:
                            await self._poll()
            except ProfileBindingError as error:
                self.binding_status = str(error)
                self.api_health = "Tracking blocked by profile binding"
                self._tracking_blocked = True
                logger.error(str(error))
            except (AOE4WorldError, asyncio.TimeoutError) as error:
                self.api_health = f"API error; retrying in {self._backoff_seconds // 60 or 1} minute(s)"
                logger.warning("AOE4World polling failed safely: %s", error)
                self.next_poll_at = time.time() + self._backoff_seconds
                self._backoff_seconds = min(self._backoff_seconds * 2, MAX_BACKOFF_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.api_health = "Unexpected tracking error; see client log"
                logger.exception("AOE4 tracking error: %s", type(error).__name__)
                self.next_poll_at = time.time() + POLL_INTERVAL_SECONDS
            await asyncio.sleep(1)

    def _ready_to_track(self) -> bool:
        return bool(
            self.server
            and self.slot is not None
            and self.team is not None
            and self.slot_data
            and self.profile_id
            and not self._tracking_blocked
        )

    async def _initialize_tracking(self, token: tuple[int, int]) -> None:
        assert self.profile_id is not None
        self._api = AOE4WorldClient(self._api_key)

        self.api_health = "Validating AOE4World profile"
        profile = await self._api.profile(self.profile_id)
        if int(profile.get("profile_id", -1)) != self.profile_id:
            raise AOE4WorldError("AOE4World profile response did not match the requested profile")

        bound_profile = await self._set_default(self._profile_storage_key(), self.profile_id)
        try:
            self.bound_profile_id = int(bound_profile)
        except (TypeError, ValueError):
            raise ProfileBindingError("This AP slot contains an invalid AOE4World profile binding.") from None
        if self.bound_profile_id != self.profile_id:
            raise ProfileBindingError(
                f"This AP slot is bound to AOE4World profile {self.bound_profile_id}; "
                f"profile {self.profile_id} cannot track it."
            )
        tracking_started_at = float(
            await self._set_default(self._start_storage_key(), time.time())
        )
        self.binding_status = (
            f"Profile {self.profile_id} bound; tracking since {format_timestamp(tracking_started_at)}"
        )

        key = state_key(
            self.seed_name or "unknown_seed",
            int(self.team),
            int(self.slot),
            self.profile_id,
        )
        state = self.state_store.load(key)
        config = TrackerConfig.from_slot_data(
            self.profile_id,
            tracking_started_at,
            self.slot_data,
            api_key_available=bool(self._api_key),
        )
        self.tracker = MatchTracker(config, state)
        self._state_file_key = key
        if self._queued_death_received_at is not None:
            self.tracker.receive_death_link(self._queued_death_received_at)
            self._queued_death_received_at = None
        self.tracker.update_ranks(profile)
        self.profile_store.save(self.profile_id)
        await self._reconcile_cap_inventory()

        self._initialized_token = token
        self._force_incremental_fetch = True
        self._backoff_seconds = POLL_INTERVAL_SECONDS
        self.next_poll_at = 0.0
        self.api_health = "AOE4World connected"

    async def _poll(self) -> None:
        assert self._api is not None and self.tracker is not None and self.profile_id is not None
        now = time.time()

        include_custom = bool(self.slot_data.get("include_custom_games", False) and self._api_key)
        last_game = await self._api.last_game(self.profile_id, include_custom=include_custom)
        signature = json.dumps(
            {
                "game_id": last_game.get("game_id"),
                "updated_at": last_game.get("updated_at"),
                "ongoing": last_game.get("ongoing"),
            },
            sort_keys=True,
        )
        should_fetch = (
            self._force_incremental_fetch
            or signature != self.tracker.state.last_api_game_signature
        )
        if should_fetch:
            if self._api_key:
                cursor = (
                    self.tracker.state.credentialed_cursor_started_at
                    or self.tracker.config.tracking_started_at
                )
            else:
                cursor = self.tracker.state.cursor_started_at or self.tracker.config.tracking_started_at
            pending_cursor = self.tracker.pending_cursor_started_at()
            if pending_cursor is not None:
                cursor = min(cursor, pending_cursor)
            since = max(self.tracker.config.tracking_started_at, cursor - CURSOR_OVERLAP_SECONDS)
            games = await self._api.games_since(self.profile_id, since)
            profile = await self._api.profile(self.profile_id)
            if self._cap_inventory_dirty:
                await self._reconcile_cap_inventory()
            outcome = self.tracker.process_games(games, self.unlocked_civilizations(), now)
            if self._api_key and self.tracker.state.cursor_started_at is not None:
                credentialed_cursor = self.tracker.state.credentialed_cursor_started_at
                self.tracker.state.credentialed_cursor_started_at = max(
                    credentialed_cursor or self.tracker.config.tracking_started_at,
                    self.tracker.state.cursor_started_at,
                )
            self.tracker.update_ranks(profile)
            self.tracker.state.last_api_game_signature = signature
            # Expire only after backfilled matches have had the opportunity to
            # consume a suppression based on their completion timestamp.
            self.tracker.expire_death_link(now)
            self._save_state()

            await self._submit_tracking_outcome(outcome)
        elif self.tracker.state.pending_games:
            # The cached last-game endpoint is cheap to poll, but its signature
            # may remain stable while AOE4World fills in a delayed result. Retry
            # only the unresolved game records instead of refetching all history.
            pending_games = await asyncio.gather(
                *(
                    self._api.game(self.profile_id, int(game_id))
                    for game_id in self.tracker.state.pending_games
                )
            )
            outcome = self.tracker.process_games(
                pending_games, self.unlocked_civilizations(), now
            )
            if self._api_key and self.tracker.state.cursor_started_at is not None:
                credentialed_cursor = self.tracker.state.credentialed_cursor_started_at
                self.tracker.state.credentialed_cursor_started_at = max(
                    credentialed_cursor or self.tracker.config.tracking_started_at,
                    self.tracker.state.cursor_started_at,
                )
            self.tracker.expire_death_link(now)
            self._save_state()
            await self._submit_tracking_outcome(outcome)
        elif self.tracker.expire_death_link(now):
            self._save_state()

        self._force_incremental_fetch = False
        self._backoff_seconds = POLL_INTERVAL_SECONDS
        self.next_poll_at = time.time() + POLL_INTERVAL_SECONDS
        self.api_health = "Healthy; polling every 60 seconds"

    def _cap_inventory(self) -> tuple[int, dict[str, int]]:
        received_item_counts = Counter(int(item.item) for item in self.items_received)
        total_item_id = self.slot_data.get("progressive_total_win_cap_item_id")
        total_count = (
            received_item_counts[int(total_item_id)] if total_item_id is not None else 0
        )
        if "progressive_civilization_item_ids" in self.slot_data:
            starting_civilizations = self._resolved_starting_civilizations()
            civilization_counts = {
                str(civilization): max(
                    0,
                    received_item_counts[int(item_id)]
                    + int(str(civilization) in starting_civilizations)
                    - 1,
                )
                for civilization, item_id in self.slot_data.get(
                    "progressive_civilization_item_ids", {}
                ).items()
            }
        else:
            civilization_counts = {
                str(civilization): received_item_counts[int(item_id)]
                for civilization, item_id in self.slot_data.get(
                    "progressive_civilization_win_cap_item_ids", {}
                ).items()
            }
        return total_count, civilization_counts

    async def _reconcile_cap_inventory(self) -> None:
        if self.tracker is None:
            return
        self._cap_inventory_dirty = False
        try:
            total_count, civilization_counts = self._cap_inventory()
            outcome = self.tracker.update_cap_inventory(total_count, civilization_counts)
            self._save_state()
            await self._submit_tracking_outcome(outcome)
        except Exception:
            self._cap_inventory_dirty = True
            raise

    async def _submit_tracking_outcome(self, outcome: TrackingOutcome) -> None:
        location_ids = self._location_ids(outcome.new_checks)
        if self.tracker is not None and self.missing_locations:
            # Local completion is durable. If an earlier send was interrupted,
            # use the server's missing set to retry without reprocessing matches.
            location_ids.update(
                self._location_ids(self.tracker.state.completed_checks).intersection(
                    self.missing_locations
                )
            )
        if location_ids:
            sent = await self.check_locations(location_ids)
            if sent:
                logger.info("Sent %d AOE4 location check(s).", len(sent))
        for cause in outcome.send_deaths:
            player_name = self.player_names.get(self.slot, "AOE4 player")
            await self.send_death(f"{player_name} {cause}.")
        await self._send_goal_if_needed()

    async def _send_goal_if_needed(self) -> None:
        if self.tracker is None or not self.tracker.goal_reached() or self.tracker.state.goal_sent:
            return
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        self.finished_game = True
        self.tracker.state.goal_sent = True
        self._save_state()
        logger.info("Age of Empires IV goal completed.")

    def _resolved_starting_civilizations(self) -> set[str]:
        resolved_starts = self.slot_data.get("starting_civilizations")
        if resolved_starts is None:
            legacy_start = self.slot_data.get("starting_civilization")
            resolved_starts = [legacy_start] if legacy_start else []
        return {str(civilization) for civilization in resolved_starts}

    def unlocked_civilizations(self) -> set[str]:
        if not self.slot_data:
            return set()
        unlocked = self._resolved_starting_civilizations()
        if "progressive_civilization_item_ids" in self.slot_data:
            configured_item_ids = self.slot_data.get(
                "progressive_civilization_item_ids", {}
            )
        else:
            configured_item_ids = self.slot_data.get("item_name_to_id", {})
        item_ids = {
            int(item_id): str(civilization)
            for civilization, item_id in configured_item_ids.items()
        }
        for network_item in self.items_received:
            civilization = item_ids.get(int(network_item.item))
            if civilization:
                unlocked.add(civilization)
        return unlocked.intersection(self.slot_data.get("civilization_pool", ()))

    def civilization_tracker_entries(self) -> tuple[CivilizationTrackerEntry, ...]:
        if not self.slot_data:
            return ()
        wins = self.tracker.state.civilization_wins if self.tracker is not None else {}
        caps = (
            {
                civilization: self.tracker.current_civilization_win_cap(civilization)
                for civilization in self.slot_data.get("civilization_pool", ())
            }
            if self.tracker is not None
            else {}
        )
        return build_civilization_tracker_entries(
            self.slot_data,
            self.unlocked_civilizations(),
            wins,
            caps,
        )

    def total_win_tracker_progress(self) -> tuple[int, int | None, int | None]:
        stages = tuple(int(value) for value in self.slot_data.get("total_win_cap_stages", ()))
        earned = self.tracker.state.total_wins if self.tracker is not None else 0
        if self.tracker is not None:
            current_cap = self.tracker.current_total_win_cap()
        else:
            current_cap = stages[0] if stages else None
        return earned, current_cap, stages[-1] if stages else None

    def _location_ids(self, names: list[str]) -> set[int]:
        civ_ids = self.slot_data.get("civilization_location_ids", {})
        win_ids = self.slot_data.get("win_location_ids", {})
        name_to_id = {
            f"Civilization Victory: {CIVILIZATIONS[civilization]}": int(location_id)
            for civilization, location_id in civ_ids.items()
        }
        for threshold, location_id in win_ids.items():
            count = int(threshold)
            name_to_id[f"Win {count} {'Match' if count == 1 else 'Matches'}"] = int(location_id)
        for civilization, win_ids_by_number in self.slot_data.get(
            "civilization_win_location_ids", {}
        ).items():
            for win_number, location_id in win_ids_by_number.items():
                name_to_id[civilization_win_location_name(civilization, int(win_number))] = int(
                    location_id
                )
        return {name_to_id[name] for name in names if name in name_to_id}

    def _configured_location_ids(self) -> set[int]:
        configured = {
            int(location_id)
            for location_id in self.slot_data.get("civilization_location_ids", {}).values()
        } | {
            int(location_id)
            for location_id in self.slot_data.get("win_location_ids", {}).values()
        }
        configured.update(
            int(location_id)
            for win_ids_by_number in self.slot_data.get(
                "civilization_win_location_ids", {}
            ).values()
            for location_id in win_ids_by_number.values()
        )
        return configured

    def _profile_storage_key(self) -> str:
        return f"aoe4_profile_{self.team}_{self.slot}"

    def _start_storage_key(self) -> str:
        return f"aoe4_tracking_started_at_{self.team}_{self.slot}"

    def _profile_history_storage_key(self) -> str:
        return f"aoe4_profile_history_{self.team}_{self.slot}"

    async def _set_default(self, key: str, default: Any) -> Any:
        return await self._set_storage_value(
            key,
            default,
            [{"operation": "default", "value": None}],
        )

    async def _set_storage_value(
        self,
        key: str,
        default: Any,
        operations: list[dict[str, Any]],
    ) -> Any:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        old_future = self._storage_waiters.pop(key, None)
        if old_future is not None and not old_future.done():
            old_future.cancel()
        self._storage_waiters[key] = future
        await self.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": key,
                    "default": default,
                    "want_reply": True,
                    "operations": operations,
                }
            ]
        )
        try:
            return await asyncio.wait_for(future, timeout=15)
        finally:
            self._storage_waiters.pop(key, None)

    def _save_state(self) -> None:
        if self.tracker is not None and self._state_file_key is not None:
            self.state_store.save(self._state_file_key, self.tracker.state)

    def status_lines(self) -> list[str]:
        lines = [f"AOE4World: {self.api_health}", f"Binding: {self.binding_status}"]
        if self.profile_id:
            lines.append(f"Profile: {self.profile_id} (API key: {'set for this launch' if self._api_key else 'not set'})")
        if self.slot_data.get("include_custom_games", False):
            if self._api_key:
                lines.append("Custom games: active for this launch")
            else:
                lines.append("Custom games: inactive until an optional API key is entered; public standard games still track")
        elif self.slot_data:
            lines.append("Custom games: disabled by slot options")
        if self.tracker is None:
            return lines
        state = self.tracker.state
        lines.append(self.goal_progress())
        configured_location_ids = self._configured_location_ids()
        checked_count = len(configured_location_ids.intersection(self.checked_locations))
        lines.append(f"Checks: {checked_count}/{len(configured_location_ids)} confirmed by the AP server")
        current_cap = self.tracker.current_total_win_cap()
        cap_text = str(current_cap) if current_cap is not None else "unrestricted"
        lines.append(
            f"Total wins: {state.total_wins} earned / {cap_text} currently attainable; "
            f"recent match: {state.last_game_summary}"
        )
        lines.append(
            f"Ranks: Solo {RANK_DISPLAY_NAMES.get(state.solo_rank or '', state.solo_rank or 'Unranked')}; "
            f"Team {RANK_DISPLAY_NAMES.get(state.team_rank or '', state.team_rank or 'Unranked')}"
        )
        unlocked = ", ".join(CIVILIZATIONS[civ] for civ in sorted(self.unlocked_civilizations()))
        lines.append(f"Unlocked civilizations ({len(self.unlocked_civilizations())}): {unlocked or 'none'}")
        expires = state.pending_death_expires_at
        if expires is None:
            lines.append("DeathLink suppression: none pending")
        else:
            remaining = max(0, int(expires - time.time()))
            lines.append(f"DeathLink suppression: pending for {remaining // 60}:{remaining % 60:02d}")
        return lines

    def goal_progress(self) -> str:
        if self.tracker is None:
            return "Goal: waiting for tracking"
        config, state = self.tracker.config, self.tracker.state
        if config.goal == "total_wins":
            cap = self.tracker.current_total_win_cap()
            cap_text = str(cap) if cap is not None else "unrestricted"
            return (
                f"Goal: {state.total_wins} earned / {cap_text} currently attainable / "
                f"{config.total_win_goal} required total wins"
            )
        if config.goal == "civilization_wins":
            progress = ", ".join(
                f"{CIVILIZATIONS[civ]} {state.civilization_wins.get(civ, 0)} earned / "
                f"{self.tracker.current_civilization_win_cap(civ) or 'unrestricted'} attainable / "
                f"{config.wins_per_goal_civilization} required"
                for civ in sorted(config.goal_civilizations)
            )
            return f"Goal: {progress}"
        rank = state.solo_rank if config.goal == "solo_rank" else state.team_rank
        return (
            f"Goal: {RANK_DISPLAY_NAMES[config.target_rank]}; current "
            f"{RANK_DISPLAY_NAMES.get(rank or '', rank or 'Unranked')}"
        )
