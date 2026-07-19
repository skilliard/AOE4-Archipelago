from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tracker import format_timestamp

API_BASE_URL = "https://aoe4world.com/api/v0"
USER_AGENT = "AOE4-Archipelago/0.1 (community APWorld; AOE4World API client)"
Requester = Callable[[str, Mapping[str, Any] | None, Mapping[str, str], int], tuple[int, Any]]


class AOE4WorldError(RuntimeError):
    pass


class AOE4WorldClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = API_BASE_URL,
        requester: Requester | None = None,
    ):
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self.base_url = base_url.rstrip("/")
        self._requester = requester or self._request_json

    async def profile(self, profile_id: int) -> Mapping[str, Any]:
        return await self._get_json(f"/players/{profile_id}")

    async def last_game(self, profile_id: int, include_custom: bool = False) -> Mapping[str, Any]:
        params: dict[str, Any] = {}
        if self._api_key:
            params["api_key"] = self._api_key
            if include_custom:
                params["include_custom"] = "true"
        return await self._get_json(f"/players/{profile_id}/games/last", params or None)

    async def game(self, profile_id: int, game_id: int) -> Mapping[str, Any]:
        params = {"api_key": self._api_key} if self._api_key else None
        return await self._get_json(f"/players/{profile_id}/games/{game_id}", params)

    async def games_since(self, profile_id: int, since: float) -> list[Mapping[str, Any]]:
        games: list[Mapping[str, Any]] = []
        page = 1
        while page <= 100:
            params: dict[str, Any] = {
                "page": page,
                "limit": 50,
                "since": format_timestamp(since),
            }
            if self._api_key:
                params["api_key"] = self._api_key
            payload = await self._get_json(f"/players/{profile_id}/games", params)
            page_games = payload.get("games") or []
            games.extend(game for game in page_games if isinstance(game, Mapping))
            count = int(payload.get("count", len(page_games)))
            offset = int(payload.get("offset", (page - 1) * max(count, 1)))
            total_count = int(payload.get("total_count", offset + count))
            if count == 0 or offset + count >= total_count:
                break
            page += 1
        return games

    async def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            status, payload = await asyncio.to_thread(self._requester, path, params, headers, 30)
            if status != 200:
                raise AOE4WorldError(f"AOE4World returned HTTP {status} for {path}")
        except AOE4WorldError:
            raise
        except Exception as error:
            # Never stringify transport exceptions: urllib errors may contain the query string and API key.
            raise AOE4WorldError(f"AOE4World request failed for {path}: {type(error).__name__}") from None
        if not isinstance(payload, Mapping):
            raise AOE4WorldError(f"AOE4World returned an invalid response for {path}")
        return payload

    def _request_json(
        self,
        path: str,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str],
        timeout: int,
    ) -> tuple[int, Any]:
        query = "?" + urlencode(params) if params else ""
        request = Request(self.base_url + path + query, headers=dict(headers), method="GET")
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
