from __future__ import annotations

import asyncio
from argparse import Namespace
from collections.abc import Sequence

import colorama

from CommonClient import get_base_parser, handle_url_arg, server_loop
from Utils import gui_enabled

from .context import AgeOfEmpiresIVContext


async def main(args: Namespace) -> None:
    if not gui_enabled:
        raise RuntimeError("The Age of Empires IV Client requires the Archipelago GUI components.")

    ctx = AgeOfEmpiresIVContext(args.connect, args.password, args.profile_id)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    ctx.run_gui()
    ctx.run_cli()
    tracking_task = asyncio.create_task(ctx.tracking_loop(), name="AOE4World tracking loop")

    await ctx.exit_event.wait()
    tracking_task.cancel()
    await asyncio.gather(tracking_task, return_exceptions=True)
    await ctx.shutdown()


def parse_launch_args(args: Sequence[str]) -> Namespace:
    parser = get_base_parser()
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--profile-id", type=int, default=None, help="Local AOE4World profile ID.")
    parser.add_argument("url", nargs="?", help="Archipelago connection URI.")
    return handle_url_arg(parser.parse_args(args), parser=parser)


def launch_client(*args: Sequence[str]) -> None:
    launch_args = parse_launch_args(args)

    colorama.just_fix_windows_console()
    asyncio.run(main(launch_args))
    colorama.deinit()
