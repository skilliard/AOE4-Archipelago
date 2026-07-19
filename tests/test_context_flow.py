from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import aoe4.client.context as context_module
import CommonClient
from aoe4.client.context import (
    AgeOfEmpiresIVContext,
    ProfileBindingError,
    ProfileRebindError,
    ProfileRebindPreview,
)
from aoe4.client.launch import parse_launch_args
from aoe4.client.state import state_key
from aoe4.client.tracker import MatchTracker, TrackerConfig, TrackerState
from aoe4.constants import (
    PROGRESSIVE_TOTAL_WIN_CAP,
    civilization_unlock_name,
    civilization_win_location_name,
)
from aoe4.items import ITEM_NAME_TO_ID
from aoe4.locations import LOCATION_NAME_TO_ID


def install_test_datapackage(monkeypatch):
    games = CommonClient.network_data_package["games"]
    monkeypatch.setitem(
        games,
        "Age of Empires IV",
        {
            "checksum": "test-checksum",
            "item_name_to_id": ITEM_NAME_TO_ID,
            "location_name_to_id": LOCATION_NAME_TO_ID,
        },
    )


def slot_data(*, death_link=True, include_custom_games=False):
    return {
        "goal": "total_wins",
        "total_win_goal": 1,
        "wins_per_goal_civilization": 1,
        "goal_civilizations": ["english"],
        "target_rank": "gold_1",
        "civilization_pool": ["english", "french"],
        "starting_civilization": "english",
        "starting_civs": 1,
        "starting_civilizations": ["english"],
        "eligible_match_modes": ["rm_solo"],
        "civ_sanity": True,
        "win_thresholds": [1, 2],
        "include_custom_games": include_custom_games,
        "death_link": death_link,
        "item_name_to_id": {
            "english": ITEM_NAME_TO_ID[civilization_unlock_name("english")],
            "french": ITEM_NAME_TO_ID[civilization_unlock_name("french")],
        },
        "civilization_location_ids": {"english": 7411006, "french": 7411007},
        "win_location_ids": {"1": 7412001, "2": 7412002},
    }


def make_game(game_id, result, civ, started_at, duration=20):
    return {
        "game_id": game_id,
        "started_at": started_at,
        "updated_at": started_at + duration,
        "duration": duration,
        "leaderboard": "rm_solo",
        "ongoing": False,
        "teams": [
            [{"player": {"profile_id": 123, "result": result, "civilization": civ}}],
            [{"player": {"profile_id": 456, "result": "loss" if result == "win" else "win", "civilization": "french"}}],
        ],
    }


@pytest.mark.asyncio
async def test_unlocked_civilizations_uses_resolved_starting_list_and_legacy_fallback(
    tmp_path, monkeypatch
):
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    ctx.slot_data = slot_data()
    ctx.slot_data["starting_civs"] = 2
    ctx.slot_data["starting_civilizations"] = ["english", "french"]
    assert ctx.unlocked_civilizations() == {"english", "french"}

    ctx.slot_data.pop("starting_civilizations")
    assert ctx.unlocked_civilizations() == {"english"}
    await ctx.shutdown()


class FakeAPI:
    def __init__(self, baseline):
        self.baseline = baseline
        self.games = []
        self.last = {"game_id": None, "updated_at": None, "ongoing": False}
        self.last_calls = []
        self.since_calls = []
        self.game_calls = []

    async def profile(self, profile_id):
        return {
            "profile_id": profile_id,
            "name": f"Profile {profile_id}",
            "modes": {
                "rm_solo": {"rank_level": "gold_1"},
                "rm_team": {"rank_level": "silver_1"},
            },
        }

    async def last_game(self, _profile_id, include_custom=False):
        self.last_calls.append(include_custom)
        return self.last

    async def games_since(self, _profile_id, since):
        assert since >= self.baseline
        self.since_calls.append(since)
        return list(self.games)

    async def game(self, _profile_id, game_id):
        self.game_calls.append(game_id)
        return next(game for game in self.games if game["game_id"] == game_id)


@pytest.mark.asyncio
async def test_unknown_result_is_repolled_until_the_same_game_resolves(tmp_path, monkeypatch):
    baseline = time.time() - 300
    fake_api = FakeAPI(baseline)
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)

    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    ctx.team, ctx.slot, ctx.seed_name = 0, 1, "Delayed Result Seed"
    ctx.slot_data = slot_data(death_link=False)
    ctx._api = fake_api
    ctx._cap_inventory_dirty = False

    async def check_locations(locations):
        return set(locations)

    ctx.check_locations = check_locations
    ctx.send_msgs = lambda messages: _record_messages([], messages)

    async def set_default(key, default):
        return 123 if "profile" in key else baseline

    ctx._set_default = set_default
    await ctx._initialize_tracking((ctx._connected_nonce, ctx._credentials_nonce))

    delayed = make_game(243_446_997, "unknown", "english", baseline + 30)
    fake_api.games = [delayed]
    # Deliberately keep this signature unchanged when the result resolves.
    fake_api.last = {"game_id": 243_446_997, "updated_at": baseline + 50, "ongoing": False}

    await ctx._poll()
    await ctx._poll()
    assert len(fake_api.since_calls) == 1
    assert fake_api.game_calls == [243_446_997]
    assert ctx.tracker.state.total_wins == 0
    assert ctx.tracker.state.pending_games == {"243446997": baseline + 30}

    fake_api.games = [make_game(243_446_997, "win", "english", baseline + 30)]
    await ctx._poll()
    assert len(fake_api.since_calls) == 1
    assert fake_api.game_calls == [243_446_997, 243_446_997]
    assert ctx.tracker.state.total_wins == 1
    assert ctx.tracker.state.pending_games == {}
    assert ctx.tracker.state.last_game_summary == "Win as English in rm_solo"

    await ctx._poll()
    assert len(fake_api.since_calls) == 1
    assert fake_api.game_calls == [243_446_997, 243_446_997]
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_mocked_ap_api_reconnect_items_deathlink_and_goal(tmp_path, monkeypatch):
    baseline = time.time() - 300
    fake_api = FakeAPI(baseline)
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)

    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    sent_messages = []
    sent_checks = []
    sent_deaths = []

    async def send_msgs(messages):
        sent_messages.extend(messages)

    async def check_locations(locations):
        sent_checks.extend(locations)
        return set(locations)

    async def send_death(cause):
        sent_deaths.append(cause)

    async def set_default(key, default):
        return 123 if "profile" in key else baseline

    ctx.send_msgs = send_msgs
    ctx.check_locations = check_locations
    ctx.send_death = send_death
    ctx._set_default = set_default
    ctx.team = 0
    ctx.slot = 1
    ctx.seed_name = "Mock Seed"
    ctx.player_names[1] = "Tester"
    ctx.configure_credentials("123", "session-secret")
    ctx.on_package("Connected", {"slot_data": slot_data()})
    await ctx._initialize_tracking((ctx._connected_nonce, ctx._credentials_nonce))

    assert ctx.binding_status.startswith("Profile 123 bound")
    assert ctx.profile_store.load() == 123
    assert ctx.tracker.state.solo_rank == "gold_1"

    first_game = make_game(1, "win", "english", baseline + 30)
    fake_api.games = [first_game]
    fake_api.last = {"game_id": 1, "updated_at": baseline + 50, "ongoing": False}
    await ctx._poll()
    assert {7411006, 7412001}.issubset(sent_checks)
    assert any(message.get("status") == 30 for message in sent_messages)
    assert ctx.tracker.state.goal_sent

    # A received death suppresses the next eligible match. The newly received civ item is honored.
    ctx.items_received.append(SimpleNamespace(item=ITEM_NAME_TO_ID[civilization_unlock_name("french")]))
    ctx.on_deathlink({"time": time.time() - 1, "source": "Friend", "cause": "test"})
    await asyncio.sleep(0.01)
    second_game = make_game(2, "win", "french", time.time(), duration=0)
    fake_api.games = [first_game, second_game]
    fake_api.last = {"game_id": 2, "updated_at": time.time(), "ongoing": False}
    await ctx._poll()
    assert ctx.tracker.state.total_wins == 1
    assert ctx.tracker.state.pending_death_expires_at is None

    # Reconnect reloads the atomic state and a fresh eligible loss emits one DeathLink.
    ctx.on_package("Connected", {"slot_data": slot_data()})
    await ctx._initialize_tracking((ctx._connected_nonce, ctx._credentials_nonce))
    loss = make_game(3, "loss", "french", time.time() - 20, duration=10)
    fake_api.games = [first_game, second_game, loss]
    fake_api.last = {"game_id": 3, "updated_at": time.time(), "ongoing": False}
    await ctx._poll()
    assert len(sent_deaths) == 1
    assert "session-secret" not in " ".join(sent_deaths)

    await ctx.shutdown()


@pytest.mark.asyncio
async def test_profile_binding_rejects_another_profile(tmp_path, monkeypatch):
    baseline = time.time()
    fake_api = FakeAPI(baseline)
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)
    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    ctx.team, ctx.slot, ctx.seed_name = 0, 1, "Seed"
    ctx.slot_data = slot_data()
    ctx.configure_credentials("123", "key")

    async def wrong_binding(_key, _default):
        return 999

    ctx._set_default = wrong_binding
    with pytest.raises(ProfileBindingError):
        await ctx._initialize_tracking((0, 1))
    assert ctx.bound_profile_id == 999
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_profile_only_tracking_and_late_keyed_custom_backfill(tmp_path, monkeypatch):
    baseline = time.time() - 600
    fake_api = FakeAPI(baseline)
    created_with_keys = []
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))

    def make_api(key=None):
        created_with_keys.append(key)
        return fake_api

    monkeypatch.setattr(context_module, "AOE4WorldClient", make_api)
    ctx = AgeOfEmpiresIVContext()
    ctx.team, ctx.slot, ctx.seed_name = 0, 1, "Optional Key Seed"
    ctx.slot_data = slot_data(death_link=False, include_custom_games=True)

    async def set_default(key, default):
        return 123 if "profile" in key else baseline

    ctx._set_default = set_default
    success, message = ctx.configure_credentials("123", "")
    assert success
    assert "does not require" in message
    await ctx._initialize_tracking((0, ctx._credentials_nonce))
    assert created_with_keys == [None]
    assert any("Custom games: inactive" in line for line in ctx.status_lines())

    public_game = make_game(30, "win", "english", baseline + 300)
    fake_api.games = [public_game]
    fake_api.last = {"game_id": 30, "updated_at": baseline + 320, "ongoing": False}
    await ctx._poll()
    assert ctx.tracker.state.total_wins == 1
    assert ctx.tracker.state.credentialed_cursor_started_at is None
    assert fake_api.last_calls[-1] is False

    # The saved profile is sufficient for a later client to start public tracking.
    saved_profile_context = AgeOfEmpiresIVContext()
    assert saved_profile_context.profile_id == 123
    await saved_profile_context.shutdown()

    custom_game = make_game(31, "win", "english", baseline + 100)
    custom_game["kind"] = "custom"
    fake_api.games = [custom_game, public_game]
    fake_api.last = {"game_id": 31, "updated_at": baseline + 120, "ongoing": False}
    success, message = ctx.configure_credentials("123", "session-secret")
    assert success
    assert "enabled" in message
    await ctx._initialize_tracking((0, ctx._credentials_nonce))
    await ctx._poll()

    assert created_with_keys[-1] == "session-secret"
    assert fake_api.last_calls[-1] is True
    assert fake_api.since_calls[-1] == baseline
    assert ctx.tracker.state.total_wins == 2
    assert ctx.tracker.state.credentialed_cursor_started_at == baseline + 300
    assert "session-secret" not in " ".join(ctx.status_lines())
    await ctx.shutdown()


def test_launcher_uri_parsing():
    args = parse_launch_args(["archipelago://Slot%20Name:roompass@example.org:38281"])
    assert args.name == "Slot Name"
    assert args.password == "roompass"
    assert args.connect.endswith("example.org:38281")


@pytest.mark.asyncio
async def test_civilization_win_checks_map_to_nested_slot_location_ids(tmp_path, monkeypatch):
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    ctx.slot_data = slot_data()
    ctx.slot_data["civilization_location_ids"] = {}
    ctx.slot_data["win_location_ids"] = {}
    ctx.slot_data["civilization_win_location_ids"] = {
        "english": {str(number): 7_420_250 + number for number in range(1, 6)},
        "french": {str(number): 7_420_300 + number for number in range(1, 6)},
        "malians": {str(number): 7_420_750 + number for number in range(1, 6)},
    }

    names = [
        civilization_win_location_name(civilization, number)
        for civilization in ("english", "french", "malians")
        for number in range(1, 6)
    ]
    assert len(ctx._configured_location_ids()) == 15
    assert ctx._location_ids(names) == ctx._configured_location_ids()
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_received_progressive_item_backfills_without_an_api_fetch(tmp_path, monkeypatch):
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    ctx.slot_data = slot_data(death_link=False)
    ctx.slot_data.update(
        {
            "total_win_goal": 20,
            "civ_sanity": False,
            "win_thresholds": list(range(1, 21)),
            "win_location_ids": {
                str(value): 7_412_000 + value for value in range(1, 21)
            },
            "total_win_cap_stages": [4, 8, 12, 16, 20],
            "civilization_win_cap_stages": [],
            "progressive_total_win_cap_item_id": ITEM_NAME_TO_ID[
                PROGRESSIVE_TOTAL_WIN_CAP
            ],
            "progressive_civilization_win_cap_item_ids": {},
        }
    )
    config = TrackerConfig.from_slot_data(123, 1_000.0, ctx.slot_data)
    ctx.tracker = MatchTracker(config, TrackerState(total_wins=20))
    sent_checks = []
    sent_messages = []

    async def check_locations(locations):
        sent_checks.extend(sorted(locations))
        return set(locations)

    ctx.check_locations = check_locations
    ctx.send_msgs = lambda messages: _record_messages(sent_messages, messages)
    await ctx._reconcile_cap_inventory()
    assert sent_checks == [7_412_001, 7_412_002, 7_412_003, 7_412_004]
    assert ctx.total_win_tracker_progress() == (20, 4, 20)

    ctx.items_received.append(
        SimpleNamespace(item=ITEM_NAME_TO_ID[PROGRESSIVE_TOTAL_WIN_CAP])
    )
    ctx.on_package("ReceivedItems", {"index": 0, "items": []})
    assert ctx._cap_inventory_dirty
    await ctx._reconcile_cap_inventory()
    assert sent_checks[-4:] == [7_412_005, 7_412_006, 7_412_007, 7_412_008]
    assert ctx.total_win_tracker_progress() == (20, 8, 20)
    assert not ctx._cap_inventory_dirty

    ctx.missing_locations = {7_412_001}
    await ctx._reconcile_cap_inventory()
    assert sent_checks[-1] == 7_412_001
    ctx.missing_locations.clear()

    ctx.items_received.extend(
        SimpleNamespace(item=ITEM_NAME_TO_ID[PROGRESSIVE_TOTAL_WIN_CAP])
        for _ in range(3)
    )
    ctx.on_package("ReceivedItems", {"index": 1, "items": []})
    await ctx._reconcile_cap_inventory()
    assert sent_checks[-12:] == list(range(7_412_009, 7_412_021))
    assert any(message.get("status") == 30 for message in sent_messages)
    assert ctx.tracker.state.goal_sent
    await ctx.shutdown()


async def _record_messages(target, messages):
    target.extend(messages)


@pytest.mark.asyncio
async def test_datastorage_default_packet_and_set_reply(tmp_path, monkeypatch):
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ctx = AgeOfEmpiresIVContext(initial_profile_id=123)
    packets = []

    async def mock_server(messages):
        packets.extend(messages)
        packet = messages[0]
        ctx.on_package("SetReply", {"key": packet["key"], "value": packet["default"]})

    ctx.send_msgs = mock_server
    result = await ctx._set_default("aoe4_profile_0_1", 123)
    assert result == 123
    assert packets == [
        {
            "cmd": "Set",
            "key": "aoe4_profile_0_1",
            "default": 123,
            "want_reply": True,
            "operations": [{"operation": "default", "value": None}],
        }
    ]
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_confirmed_profile_rebind_preserves_start_and_records_audit(tmp_path, monkeypatch):
    baseline = time.time() - 1_000
    fake_api = FakeAPI(baseline)
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)

    ctx = AgeOfEmpiresIVContext(initial_profile_id=111)
    ctx.server = SimpleNamespace()
    ctx.team, ctx.slot, ctx.seed_name = 0, 1, "Correction Seed"
    ctx.slot_data = slot_data(death_link=False)
    ctx.bound_profile_id = 111
    ctx._connected_nonce = 7
    ctx.checked_locations.add(7411006)
    ctx.finished_game = True

    old_state_key = state_key(ctx.seed_name, 0, 1, 111)
    ctx.state_store.save(old_state_key, TrackerState(total_wins=9))

    profile_key = "aoe4_profile_0_1"
    start_key = "aoe4_tracking_started_at_0_1"
    history_key = "aoe4_profile_history_0_1"
    storage = {profile_key: 111, start_key: baseline, history_key: []}
    packets = []

    async def mock_server(messages):
        packet = messages[0]
        packets.append(packet)
        value = storage.get(packet["key"], packet["default"])
        for operation in packet["operations"]:
            if operation["operation"] == "replace":
                value = operation["value"]
            elif operation["operation"] == "add":
                value = value + operation["value"]
            elif operation["operation"] != "default":
                raise AssertionError(f"Unexpected operation: {operation}")
        storage[packet["key"]] = value
        ctx.on_package("SetReply", {"key": packet["key"], "value": value})

    ctx.send_msgs = mock_server
    preview = await ctx.prepare_profile_rebind("222", "session-secret")
    assert preview.old_profile_id == 111
    assert preview.new_profile_id == 222
    assert preview.new_profile_name == "Profile 222"
    assert preview.confirmed_checks == 1
    assert preview.goal_completed

    # Merely previewing/cancelling does not alter the server binding.
    assert storage[profile_key] == 111
    assert packets == []

    message = await ctx.rebind_profile(preview, "session-secret")
    assert "audit history recorded" in message
    assert storage[profile_key] == 222
    assert storage[start_key] == baseline
    assert storage[history_key] == [
        {
            "old_profile_id": 111,
            "new_profile_id": 222,
            "changed_at": storage[history_key][0]["changed_at"],
            "team": 0,
            "slot": 1,
        }
    ]
    assert ctx.profile_id == 222
    assert ctx.bound_profile_id == 222
    assert ctx.profile_store.load() == 222
    assert ctx.tracker is None
    assert ctx._force_incremental_fetch
    assert ctx.next_poll_at == 0.0
    assert ctx.state_store.load(old_state_key).total_wins == 9
    assert "session-secret" not in message
    assert all(packet["key"] != start_key for packet in packets)

    # Reinitialization reads but does not replace the original tracking start.
    await ctx._initialize_tracking((ctx._connected_nonce, ctx._credentials_nonce))
    assert ctx.tracker.config.profile_id == 222
    assert ctx.tracker.config.tracking_started_at == baseline
    assert storage[start_key] == baseline
    start_packets = [packet for packet in packets if packet["key"] == start_key]
    assert start_packets[-1]["operations"] == [{"operation": "default", "value": None}]
    ctx.server = None
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_profile_rebind_rejects_invalid_same_stale_and_disconnected_requests(tmp_path, monkeypatch):
    fake_api = FakeAPI(time.time())
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)
    ctx = AgeOfEmpiresIVContext(initial_profile_id=111)

    with pytest.raises(ProfileRebindError, match="Connect"):
        await ctx.prepare_profile_rebind("222", "")

    ctx.server = SimpleNamespace()
    ctx.team, ctx.slot = 0, 1
    ctx.slot_data = slot_data()
    ctx.bound_profile_id = 111
    with pytest.raises(ProfileRebindError, match="positive"):
        await ctx.prepare_profile_rebind("not-a-number", "")
    with pytest.raises(ProfileRebindError, match="already bound"):
        await ctx.prepare_profile_rebind("111", "")

    class MismatchedAPI:
        async def profile(self, _profile_id):
            return {"profile_id": 999, "name": "Different profile"}

    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: MismatchedAPI())
    with pytest.raises(ProfileRebindError, match="did not match"):
        await ctx.prepare_profile_rebind("222", "")
    assert ctx.profile_id == 111

    monkeypatch.setattr(context_module, "AOE4WorldClient", lambda _key=None: fake_api)
    preview = await ctx.prepare_profile_rebind("222", "")
    ctx._connected_nonce += 1
    with pytest.raises(ProfileRebindError, match="connection changed"):
        await ctx.rebind_profile(preview, "")
    assert ctx.profile_id == 111
    ctx.server = None
    await ctx.shutdown()


@pytest.mark.asyncio
async def test_profile_rebind_timeout_is_uncertain_and_does_not_change_local_profile(tmp_path, monkeypatch):
    install_test_datapackage(monkeypatch)
    monkeypatch.setattr(context_module.Utils, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ctx = AgeOfEmpiresIVContext(initial_profile_id=111)
    ctx.server = SimpleNamespace()
    ctx.team, ctx.slot = 0, 1
    ctx.slot_data = slot_data()
    ctx.bound_profile_id = 111
    preview = ProfileRebindPreview(111, 222, "Profile 222", 0, 1, 0, 0, False)

    async def timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError

    ctx._set_storage_value = timeout
    with pytest.raises(ProfileRebindError, match="did not confirm"):
        await ctx.rebind_profile(preview, "do-not-log")
    assert ctx.profile_id == 111
    assert ctx.bound_profile_id is None
    assert ctx._tracking_blocked
    assert "uncertain" in ctx.binding_status
    assert "do-not-log" not in ctx.binding_status
    ctx.server = None
    await ctx.shutdown()
