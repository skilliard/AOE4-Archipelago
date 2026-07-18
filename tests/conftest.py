from __future__ import annotations

import sys
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / ".vendor" / "archipelago"

if not UPSTREAM.is_dir():
    raise RuntimeError("Archipelago 0.6.7 is missing; run scripts/build_apworld.ps1 first")

sys.path.insert(0, str(UPSTREAM))
sys.path.insert(0, str(ROOT))

# The build script overlays the package into upstream/worlds/aoe4. If that overlay is
# present, use the already registered package instead of importing a second copy from
# the repository root under the top-level name.
if (UPSTREAM / "worlds" / "aoe4" / "__init__.py").is_file():
    installed = importlib.import_module("worlds.aoe4")
    sys.modules["aoe4"] = installed
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("worlds.aoe4."):
            sys.modules[module_name.removeprefix("worlds.")] = module
