# Overview

This implementation of Archipelago for Age of Empires IV works by using the AOE4world API. It does not mod the game client in any way. Your civilization unlocks are spread out in other games in the Archipelago, and you send locations by winning games or winning as specific civs.

# Easy Setup:

1. Download and double click the .APWorld.
2. Open options creator in the Archipelago client to create a YAML
3. When game is generated, open the Age of Empires IV client in your archipelago launcher, then enter your AOE4world ID, then click "start tracking.
(visit aoe4world.com, look up your username, then take the numbers in the URL. For example for Skilliard(https://aoe4world.com/players/3454795), the player ID is 3454795.

# Options:
Goals:
1. Civilization wins: Win X amount of times as all available civs.
2. Total wins: Win X amount of games
3. Rank: Reach a specific rank(Not yet tested)

Other options:

Civsanity: send one or more location checks for winning as each civ

Civilization selection is goal-dependent. A `civilization_wins` seed uses `goal_civilizations` as its complete unlock pool and creates one numbered check for every required win with every selected civilization. Total-win and rank seeds use `civilization_pool` instead and retain configurable global-win and civilization-sanity checks. The first civilization item, such as **Progressive English Civilization**, unlocks that civilization and its initial win band; later copies raise that cap while earned wins continue accumulating for retroactive credit. `starting_civs` selects up to five deterministic random starts, while a non-empty `starting_civilizations` list supplies the exact starting set.

# Note: If civsanity is disabled, you will need to have at least as many win checks as civilizations in your civ pool for the game to generate.

# Tracker

The client also includes a live **Tracker** tab showing available civilizations, unlocked civilizations that still need required wins, earned/attainable total and per-civilization progress, and locked civilizations. Civilization flags are packaged from AOE4World Explorer for offline display.

# FAQ:

# I won, why didn't my checks show up?

1. Make sure you remembered to enter your player ID and click set tracking.
2. It usually takes ~2 minutes for checks to show up as the client polls the API every 60 seconds and the API can take time to update with game results.

# What if I bound the wrong account by mistake?

You can change the profile you are tracking and it will fix future checks, but you cannot unsend already sent checks.




