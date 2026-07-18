from __future__ import annotations

import shutil
import sys
from pathlib import Path


class _UnrelatedWorldLoadFilter:
    def filter(self, record) -> bool:
        return not record.getMessage().startswith("Could not load world WorldSource(")


def main() -> None:
    upstream = Path.cwd().resolve()
    if not (upstream / "Launcher.py").is_file():
        raise RuntimeError("Run this helper with the Archipelago checkout as the working directory")
    sys.path.insert(0, str(upstream))
    # The builder only needs worlds that can load with the base dependency set.
    # Do not let unrelated upstream worlds prompt for their optional clients.
    import os
    os.environ.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")

    import logging
    logging.getLogger().addFilter(_UnrelatedWorldLoadFilter())

    import Launcher
    from Options import generate_yaml_templates
    from worlds.LauncherComponents import components

    Launcher.open_folder = lambda _path: None
    builder = next(component for component in components if component.display_name == "Build APWorlds")
    if builder.func is None:
        raise RuntimeError("Archipelago's Build APWorlds component is unavailable")
    builder.func("Age of Empires IV")

    template_staging = upstream / "build" / "aoe4_templates"
    if template_staging.exists():
        shutil.rmtree(template_staging)
    generate_yaml_templates(template_staging, False)


if __name__ == "__main__":
    main()
