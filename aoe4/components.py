from worlds.LauncherComponents import Component, Type, components, launch

from .constants import GAME_NAME


def run_client(*args: str) -> None:
    from .client.launch import launch_client

    launch(launch_client, name="Age of Empires IV Client", args=args)


components.append(
    Component(
        "Age of Empires IV Client",
        func=run_client,
        game_name=GAME_NAME,
        component_type=Type.CLIENT,
        supports_uri=True,
    )
)

