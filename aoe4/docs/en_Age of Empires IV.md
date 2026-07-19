# Age of Empires IV

Age of Empires IV for Archipelago is an honor-system integration that watches AOE4World match history. It does not modify, inject into, read memory from, or control Age of Empires IV.

Public ranked and quick-match tracking requires only an AOE4World profile ID. A session-only API key is optional for private-game visibility and required when the slot enables custom-game tracking.

The desktop client can correct an accidentally bound profile without modifying Archipelago itself. Corrections preserve the original tracking start, are recorded in AP DataStorage, and cannot undo progress already submitted by the previous profile.

The desktop client's **Tracker** tab uses AOE4World Explorer civilization flags to show all currently available civilizations and a focused list of unlocked civilizations that still need their configured wins. It refreshes automatically when items arrive or tracked wins are credited.

## Checks

- For a **civilization-wins goal**, every civilization in `goal_civilizations` receives numbered checks from win 1 through `wins_per_goal_civilization`. Three civilizations at five wins each therefore produce exactly 15 checks. Civilization sanity and global win milestones are ignored for this goal.
- For a **total-win or rank goal**, civilization sanity creates `civ_sanity_win_count` checks with each civilization in `civilization_pool`. A count of 1 retains the **Civilization Victory** check name; larger counts use numbered civilization wins.
- For a **total-win or rank goal**, **Win Matches** checks are awarded at every configured interval. The final total-win cap covers the larger of the highest milestone and the total-wins goal target.

Wins are always recorded even when they exceed the current cap. The first global 20% band is attainable immediately. A civilization's first progressive tier, such as **Progressive English Civilization**, unlocks that civilization and its initial band; each later tier unlocks the next cumulative, rounded-up 20% band. Targets below five advance one win at a time. Receiving a later tier immediately submits any already-earned checks it unlocks; total-win and civilization-win goals follow the same cap rule.

## Items

The number configured by `starting_civs` begins unlocked (1 by default, maximum 5). `starting_civilization` selects one guaranteed member of that random starting set. Alternatively, a non-empty `starting_civilizations` list supplies the exact 1-5 starts and overrides both legacy selectors. For a civilization-wins goal, all starting tiers come from `goal_civilizations`; for total-win and rank goals, they come from `civilization_pool`. Each start receives its first progressive civilization tier before play. Non-starting civilizations place that tier in the multiworld, and configurations with multiple civilization wins add later copies for higher cap stages. Remaining locations contain **Strategic Insight**, a no-op filler item.

## Goals

The slot can require total credited wins, wins with every selected civilization, a ranked 1v1 rank, or a ranked teams rank. `goal_civilizations` is used only by the civilization-wins goal; `civilization_pool` is used by the other three goals. Total-win and civilization-win goals cannot complete until the cap covering their target is attainable. Rank completion is permanent once observed and is never gated by win caps. DeathLink suppression affects win-derived progress but never rank progress.

When enabled in the YAML, completed custom games follow the same unlocked-civilization, win, check, goal, and DeathLink rules as standard queues.
