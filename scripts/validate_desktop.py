from __future__ import annotations

import asyncio
import os
import tempfile

import platformdirs


# Keep this smoke test isolated from the user's real Archipelago/Kivy config.
platformdirs.user_config_dir = lambda *_args, **_kwargs: os.path.join(  # type: ignore[assignment]
    tempfile.gettempdir(), "aoe4-archipelago-ui-smoke-test"
)


async def main() -> None:
    from worlds.aoe4.client.context import AgeOfEmpiresIVContext
    from worlds.aoe4.client.ui import AgeOfEmpiresIVManager
    from kivy.core.window import Window

    context = AgeOfEmpiresIVContext(initial_profile_id=123)
    context.slot_data = {
        "goal": "civilization_wins",
        "wins_per_goal_civilization": 3,
        "goal_civilizations": ["english", "french", "rus"],
        "civilization_pool": ["english", "french", "rus"],
        "starting_civilization": "english",
        "starting_civs": 2,
        "starting_civilizations": ["english", "french"],
        "civ_sanity": False,
    }

    manager = AgeOfEmpiresIVManager(context)
    manager.build()
    manager._refresh_tracker()

    assert "Tracker" in [screen.name for screen in manager.screens.screens]
    assert len(manager.tracker_content.children) == 8
    assert manager._flag_texture("english").size == (104, 56)

    await context.shutdown()
    Window.close()
    print("Desktop tracker layout constructed: OK")


if __name__ == "__main__":
    asyncio.run(main())
