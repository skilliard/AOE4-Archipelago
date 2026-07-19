# Age of Empires IV Archipelago

Custom Archipelago 0.6.7 world and launcher-integrated desktop client for Age of Empires IV. Match completion is tracked through AOE4World; the game itself is never modified.

The desktop client requires an AOE4World profile ID. Its session-only API key is optional for public games and enables private/custom-game visibility when configured by the slot.

An accidentally bound profile can be corrected from the AOE4 client tab through the standard Archipelago DataStorage protocol; no upstream client or server fork is required.

The client also includes a live **Tracker** tab showing available civilizations, unlocked civilizations that still need required wins, earned/attainable total and per-civilization progress, and locked civilizations. Civilization flags are packaged from AOE4World Explorer for offline display.

Civilization selection is goal-dependent. A `civilization_wins` seed uses `goal_civilizations` as its complete unlock pool and creates one numbered check for every required win with every selected civilization. Total-win and rank seeds use `civilization_pool` instead and retain configurable global-win and civilization-sanity checks. The first civilization item, such as **Progressive English Civilization**, unlocks that civilization and its initial win band; later copies raise that cap while earned wins continue accumulating for retroactive credit. `starting_civs` selects up to five deterministic random starts, while a non-empty `starting_civilizations` list supplies the exact starting set.

See [the setup guide](aoe4/docs/setup_en.md) for installation and play instructions. Source builds use Python 3.11–3.13. Build the distributable and an upstream-generated YAML template with `powershell -ExecutionPolicy Bypass -File scripts/build_apworld.ps1`. On a fresh development machine, add `-InstallDependencies`. Run the automated suite with `powershell -ExecutionPolicy Bypass -File scripts/test.ps1`.
