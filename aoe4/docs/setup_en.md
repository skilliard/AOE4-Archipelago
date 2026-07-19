# Age of Empires IV Multiworld Setup Guide

## Requirements

- Age of Empires IV on any platform whose matches appear on AOE4World
- Archipelago 0.6.7 or newer
- An AOE4World profile ID
- An optional AOE4World API key for private and custom-game visibility
- The `aoe4.apworld` file

This integration does not install a game mod. It reads completed match data from AOE4World and applies the honor-system rules configured in your YAML.

## Install the APWorld

1. Close Archipelago.
2. Open `aoe4.apworld`, or copy it into Archipelago's `custom_worlds` directory.
3. Start the Archipelago Launcher again.
4. Use **Generate Template Options** to create an up-to-date YAML, or start from the example in this project.

## Configure a Slot

Civilizations and match modes are written with lower-case identifiers such as `english`, `holy_roman_empire`, and `rm_solo`. A rank goal needs its matching ranked queue (`rm_solo` or `rm_team`) enabled.

The selected goal determines the civilization unlock set and checks:

- With `goal: civilization_wins`, `goal_civilizations` is the complete civilization pool and `civilization_pool` is ignored. The client creates and sends one numbered check for every required win with every selected civilization. For example, English, French, and Malians with five wins per civilization creates exactly 15 checks: wins 1-5 for each civ. `civ_sanity`, `civ_sanity_win_count`, `win_check_interval`, and `win_check_count` are ignored for this goal.
- With `goal: total_wins`, `goal: solo_rank`, or `goal: team_rank`, `civilization_pool` controls the starting civilizations and unlock items, while `goal_civilizations` is ignored. `civ_sanity_win_count` controls how many checks each civilization receives when civilization sanity is enabled; global wins retain their configured interval and count.

`starting_civs` controls how many civilizations from the goal's active list begin unlocked and accepts 1-5. A specifically selected `starting_civilization` must be in the active list and is guaranteed to be among those deterministic random unlocks. A non-empty `starting_civilizations` list instead supplies the exact 1-5 starting civilizations and overrides both other starting options.

Global and per-civilization win targets are divided into five cumulative, rounded-up 20% cap stages. The first stage is available immediately and repeated **Progressive Win Cap** items unlock later stages; targets below five advance one win per stage. The client continues recording eligible wins above a current cap, then retroactively sends unlocked checks and goal completion when the corresponding cap arrives. Configurations must generate enough locations for all civilization unlock and progressive cap items.

API keys and AOE4World profile IDs never belong in the YAML. Share only the YAML with the host.

## Connect and Track

1. Launch **Age of Empires IV Client** from the Archipelago Launcher, or use the room-page launch link.
2. Connect to the AP room in the Archipelago tab.
3. In the AOE4 tab, enter the numeric profile ID from the player's AOE4World URL. Optionally enter an API key for private/custom games.
4. Select **Start Tracking**. When supplied, the key is held only in memory and displayed as masked text.

The **Tracker** tab updates automatically as civilization unlock and progressive cap items arrive and as AOE4World wins are credited. It shows total and per-civilization wins as earned versus currently attainable, including wins stored above the current cap. Its first section lists unlocked civilizations whose win or cap requirement is incomplete. The available section shows every civilization you may currently play for credit, and the locked section previews the rest of the active pool. The packaged flag artwork comes from AOE4World Explorer, so no separate image download is needed while playing.

API keys for private-game visibility are managed through the player's AOE4World account/profile settings. Public ranked and quick-match tracking needs only the profile ID. Enabling `include_custom_games` in the YAML also requires entering a key during each client launch; without one, standard public games continue tracking and the client reports custom tracking as inactive.

On the first successful AP and AOE4World connection, the profile ID and tracking start time are bound to that AP slot. A later client must use the same profile. Match progress is saved locally, but the API key is never saved.

### Correct an Accidental Profile Binding

If a valid but incorrect profile ID was bound, enter the correct ID in the AOE4 tab and select **Correct Bound Profile**. The client validates the AOE4World profile and shows its name and ID before asking for explicit confirmation. The original tracking start time is preserved, so the corrected profile is backfilled from the same point.

Every correction is recorded in AP DataStorage with the old ID, new ID, time, team, and slot. Archipelago cannot retract checks, delivered items, DeathLinks, or goal completion that the wrong profile already caused; the confirmation dialog reports this before applying the correction. If the server does not confirm the replacement, reconnect so the client can reload the authoritative binding before trying again.

Use only one active client for an AP slot. Two clients can observe and send the same loss before their local state synchronizes, causing duplicate DeathLinks.

## Rules and Limitations

- Configured ranked and quick-match queues count. API-reported custom games also count when `include_custom_games` is enabled and the client has a key; console-only queues remain excluded.
- A win earns credit only when the civilization was unlocked before that game was processed. The client cannot stop you from selecting a locked civilization in AoE4.
- Team wins count as one win for the bound player.
- The API key is optional for public games, and the documented API cannot prove that a supplied key belongs to the bound public profile.
- Custom-game tracking is also honor-system based. Any completed custom match with an API-reported win or loss is eligible; the client does not inspect map, participant, AI, tuning-pack, or lobby rules.
- Received DeathLinks are not replayed while this client is offline. See the in-client DeathLink timer for an active suppression.

When DeathLink is enabled, an eligible loss sends a death even if its civilization was locked. One received death arms a one-hour suppression; additional deaths do not stack. The first eligible match completed during that hour consumes it whether the result is a win or loss. A suppressed win earns no win-based progress, while a suppressed loss still sends its own death. Backfilled losses send only when first observed within one hour of completion.
