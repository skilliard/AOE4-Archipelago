# Age of Empires IV

Age of Empires IV for Archipelago is an honor-system integration that watches AOE4World match history. It does not modify, inject into, read memory from, or control Age of Empires IV.

Public ranked and quick-match tracking requires only an AOE4World profile ID. A session-only API key is optional for private-game visibility and required when the slot enables custom-game tracking.

The desktop client can correct an accidentally bound profile without modifying Archipelago itself. Corrections preserve the original tracking start, are recorded in AP DataStorage, and cannot undo progress already submitted by the previous profile.

The desktop client's **Tracker** tab uses AOE4World Explorer civilization flags to show all currently available civilizations and a focused list of unlocked civilizations that still need their configured wins. It refreshes automatically when items arrive or tracked wins are credited.

## Checks

- For a **civilization-wins goal**, every civilization in `goal_civilizations` receives numbered checks from win 1 through `wins_per_goal_civilization`. Three civilizations at five wins each therefore produce exactly 15 checks. Civilization sanity and global win milestones are ignored for this goal.
- For a **total-win or rank goal**, **Civilization Victory** checks are awarded on the first credited win with each civilization in `civilization_pool` when civilization sanity is enabled.
- For a **total-win or rank goal**, **Win Matches** checks are awarded at every configured interval. Backfilled games may cross and send multiple milestones at once.

## Items

The number configured by `starting_civs` begins unlocked (1 by default). `starting_civilization` selects one guaranteed member of that starting set. For a civilization-wins goal, all starting unlocks come from `goal_civilizations`; for total-win and rank goals, they come from `civilization_pool`. Every other civilization in that active pool appears once as a progression item. Remaining item slots contain **Strategic Insight**, a no-op filler item.

## Goals

The slot can require total credited wins, wins with every selected civilization, a ranked 1v1 rank, or a ranked teams rank. `goal_civilizations` is used only by the civilization-wins goal; `civilization_pool` is used by the other three goals. Rank completion is permanent once observed. DeathLink suppression affects win-derived progress but never rank progress.

When enabled in the YAML, completed custom games follow the same unlocked-civilization, win, check, goal, and DeathLink rules as standard queues.
