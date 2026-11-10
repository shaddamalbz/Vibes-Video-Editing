# Finding the player's kills in a long recording

Assumes a 1920x1080, 60 fps CFR recording with the default Valorant HUD (frame index / 60 = exact time).
The first run (43-min recording, 23 kills) took several iterations; this is the version that worked.

## Signals
| Signal | Where | What it means |
|---|---|---|
| Own killfeed row | top right, crop 1400,80 520x240 (full res) | The player's own rows carry a **yellow outline** on their block. Teal row body = the player got the kill. Red row body = the player died. |
| Centre kill icon | centre bottom, around 920,800 | Skull or wolf icon pops on every own kill (white blob, then a flash). |
| Game audio | 6-11 kHz band | Short high-band bump on the kill. Weak alone, good as a tie-breaker. |

Traps seen on the first video:
- Assists also show yellow, but only on the small icons, not the whole block. Exclude them.
- Yellow scenery (Ascent/Haven walls, smokes) creates noise. Track rows over time (a row lives about 5 s and moves up as older rows expire) and reject short-lived blobs.
- A kill landed after the player died (ability, "death-cam") still counts: the footage then shows the death camera.
- Teammates' kills look the same apart from the yellow outline. Never include them.

## Steps (run from the work folder, `montage.json` holds the video path)
1. `scan_video.py`: 5 fps HUD crops (`scan/kf.raw`, `scan/cb.raw`) + game audio (`scan/game_audio.wav`, `scan/game_audio_st48.wav`). GPU decode.
2. `detect_coarse.py`: coarse candidates from the yellow marker at the left (kill) or right (death) end of a row -> `scan/coarse_events.json`.
3. `extract_features.py`: full 60 fps pass, tiny per-frame features of the killfeed and the centre icon -> `scan/feat60.npz` (the slowest step).
4. `detect_events.py`: tracks the yellow row bands at 60 fps, classifies teal/red, refines the onset -> `scan/events60.json`.
5. `make_sheets.py`: contact sheets `probe/verify_N.png` (killfeed crop + centre icon) for every candidate. **Look at every sheet**, drop teammates' kills, assists and deaths.
6. Write `verified.json` in the work folder: `[{"t": 245.37, "note": ""}, {"t": 323.13, "note": "ability kill"}, ...]` (approximate seconds are fine).
7. `finalize_kills.py`: re-localises each verified kill to the exact frame (row pop / icon start, whichever is earlier) and groups sequences (same round, gap <= 30 s) -> `kills.json`.
8. Add attributes by eye for choosing kills (callout, weapon, headshot, wallbang, through_smoke, highlight_note), then show the list to the user and wait for confirmation before any render.

## Choosing kills
The user prefers satisfying kills: headshots, through smoke, wallbangs, satchel (Blast Pack) plays, round-winning kills, clearly visible enemies.
Weak kills (far, ability, enemy not visible, death-cam) still work in 2-beat "rapid" clips when the user wants every kill in.
