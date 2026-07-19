from __future__ import annotations

import asyncio

import pytest

from aoe4.client.api import AOE4WorldClient, AOE4WorldError, USER_AGENT


class FakeRequester:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, path, params, headers, timeout):
        self.requests.append((path, params, headers, timeout))
        return self.responses.pop(0)


def test_incremental_pagination_cursor_and_user_agent():
    requester = FakeRequester(
        [
            (200, {"page": 1, "count": 2, "offset": 0, "total_count": 3, "games": [{"game_id": 1}, {"game_id": 2}]}),
            (200, {"page": 2, "count": 1, "offset": 2, "total_count": 3, "games": [{"game_id": 3}]}),
        ]
    )
    client = AOE4WorldClient("secret-key", "https://example.invalid/api", requester)
    games = asyncio.run(client.games_since(123, 1_000))
    assert [entry["game_id"] for entry in games] == [1, 2, 3]
    assert [request[1]["page"] for request in requester.requests] == [1, 2]
    assert requester.requests[0][1]["since"].endswith("Z")
    assert requester.requests[0][1]["api_key"] == "secret-key"
    assert requester.requests[0][2]["User-Agent"] == USER_AGENT


def test_keyless_requests_omit_api_key_and_custom_parameters():
    requester = FakeRequester(
        [(200, {"profile_id": 123}), (200, {}), (200, {"games": [], "count": 0})]
    )
    client = AOE4WorldClient(None, "https://example.invalid/api", requester)
    asyncio.run(client.profile(123))
    asyncio.run(client.last_game(123, include_custom=True))
    asyncio.run(client.games_since(123, 1_000))

    assert requester.requests[0][0] == "/players/123"
    assert requester.requests[0][1] is None
    assert requester.requests[1][1] is None
    assert "api_key" not in requester.requests[2][1]
    assert "include_custom" not in requester.requests[2][1]


def test_keyed_last_game_requests_custom_visibility_without_keying_profile():
    requester = FakeRequester([(200, {"profile_id": 123}), (200, {"game_id": 9})])
    client = AOE4WorldClient("session-secret", "https://example.invalid/api", requester)
    asyncio.run(client.profile(123))
    asyncio.run(client.last_game(123, include_custom=True))

    assert requester.requests[0][1] is None
    assert requester.requests[1][1] == {
        "api_key": "session-secret",
        "include_custom": "true",
    }


def test_exact_game_retry_uses_the_player_game_endpoint_and_optional_key():
    requester = FakeRequester([(200, {"game_id": 243_446_997})])
    client = AOE4WorldClient("session-secret", "https://example.invalid/api", requester)

    game = asyncio.run(client.game(3_454_795, 243_446_997))

    assert game["game_id"] == 243_446_997
    assert requester.requests[0][0] == "/players/3454795/games/243446997"
    assert requester.requests[0][1] == {"api_key": "session-secret"}


def test_api_errors_redact_key():
    requester = FakeRequester([(401, {})])
    client = AOE4WorldClient("do-not-leak", "https://example.invalid/api", requester)
    with pytest.raises(AOE4WorldError) as error:
        asyncio.run(client.games_since(123, 1_000))
    assert "do-not-leak" not in str(error.value)
