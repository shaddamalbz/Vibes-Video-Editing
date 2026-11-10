# edl.json cheat sheet

`edl.json` holds every editing decision. Revisions = edit it, then re-render. Beats are counted from the start of the song window; 1 beat = `song.beat_period` seconds.
Presets (`{"preset": ...}`) are expanded by `load_edl()`; see [effects.md](effects.md).

## Top level
| Key | What it controls |
|---|---|
| `project.video` | the recording (never modified); the default for clips without their own `video` |
| `song` | `file`, `window_start` (s in the song), `window_beats`, `beat_period` |
| `grade` | contrast, brightness, saturation, gamma, sharpen (`sharpen_final` for the final), `vignette_angle` (`PI/8`) |
| `grade_ramp` | opening look (desaturated, softer) that ramps into `grade` at `at_beat` (the first drop) |
| `tint` | warm opening -> cool brand tint at `at_beat` |
| `fades` | `video_in`, `video_out` seconds |
| `render.slowmo_interp` | `flow` (optical flow, no ghosting) or `blend` |
| `endcard` | brand card from `start_beat`: logo + wordmark from the channel profile's `brand.json` (brand.py; no logo there = no card unless this dict names one), sizes and positions |
| `audio` | `kill_hit` (level, decay, bass, lead-in crescendo), `shots`, `duck`, `song_gain_db`, `target_lufs` (-14); `game_file` (default game track, `scan/game_audio_st48.wav`), `bed` (continuous game sound under every clip; `gain_db` = fixed level instead of leveling against the song, for long-form where the game sound leads), `sfx` (extra samples on beats, e.g. a bonk) |
| `panels` | manga pages (anime.py): `[{"start", "end", "bg", "border", "exit": {"type": "shatter", "dur": 0.22}, "items": [{"in", "poly" (screen fractions), "src" (source s at `in`), "speed", "crop": {"cx", "cy", "w"} (source px), "style": "color"|"impact", "impact_at", "video"}]}]`. The page covers the timeline (keep a clip underneath; its game sound plays) and shatters onto the next clip at `end`. Worked example: see the channel profile's `examples.md` if present |
| `overlays` | keyed characters over the footage (overlay.py, frames from chroma_key.py): `[{"dir", "start", "end" (beats), "x" (body centre), "bottom", "height" (canvas fractions), "rate", "src_start", "loop", "flip", "fade", "pop", "opacity"}]`, drawn under texts / end card |
| `film_bars` | thin black cinema bars over the whole edit (fraction of the height, e.g. 0.045) |
| `wide_bg` | background of `wide` clips: `{"blur": 1.6, "dim": 0.30}` |
| `canvas` | `"16:9"` = landscape long-form (960x540 @30 preview, 1920x1080 @60 final): every clip shows the whole frame (decoded at the output width, `decode_w` overrides), frames are streamed (clips may be minutes long), the view zooms just enough that shake / roll never show the frame edge and stays inside the frame on a `zoom_to` near a HUD corner. Omit for 9:16 |
| `stings` | mid-video logo cards: a list of `endcard`-style dicts plus `end_beat` and `fade_out_beats` (the card fades back out to the footage) |
| `clips`, `texts` | below |

## A clip
```json
{"id": "c08", "kill_id": 20, "src_kill_frame": 128584, "section": "pair", "arc": "pair_a_long",
 "beats": {"start": 50, "kill": 55.924, "end": 56.45}, "crop_x": 960,
 "speed": {"preset": "pair_a_long"}, "push_in": 0.0, "intensity": 1.43,
 "effects": [{"preset": "flash_2"}, {"preset": "zoom_2"}, {"preset": "shake_2"}],
 "transition_out": {"preset": "glitch_cut_1"},
 "audio_kill_hit": {"lead": 0.0, "decay_tau": 0.28}, "audio_duck_db": 6.0}
```
- `beats.kill` = where the kill frame lands in the song. Clips must butt together (`end` of one = `start` of the next).
- `src_kill_frame` comes from `kills.json` (60 fps frame index). Never let a clip's source range contain another kill or reuse footage of another clip (check source ranges after every plan change).
- `crop_x` = horizontal centre of the 9:16 crop in the 1920-wide source (960 = crosshair).
- `speed`: preset, or raw `{"keys": [[beats relative to the kill, speed], ...]}` for special lead-ins (e.g. the satchel chase).
- `intensity` scales every effect on the clip (about 1.2 quiet .. 2.0 drop).
- `push_in`: slow zoom toward the kill (0.05 normal, 0.09 hero).
- `calm: true` = a clip without a kill (ambient game sound, normal speed).
- Per-clip audio overrides: `audio_kill_hit` (merged into `audio.kill_hit`), `audio_duck_db`, `bed_gain` (scales the game-sound bed on this clip), `audio_lag` (s the clip's game audio trails its picture; hit, shots and bed are read that much later and the onset auto-trim is skipped).
- `base_zoom` + `view_y`: static zoom and vertical view centre (source pixels), e.g. `1.2` + `465` hides game subtitles at the bottom.
- `wide`: 0..1 or `{"keys": [[s rel. anchor, w], ...]}`: 0 = the 9:16 crop, 1 = the whole 16:9 frame fitted to the width, over a blurred copy (0.7-0.85 reads best on a phone). Wide clips are decoded uncropped at `decode_w` (default 1280 final / 960 preview).
- `decode_w`: decode the uncropped frame at this width (1920 for a sharp `zoom_to`), shown as a normal 9:16 crop around `crop_x` unless `wide` is set.
- Effect `{"type": "zoom_to", "x": 1423, "y": 132, "z": 2.1, "from": 0.45, "to": 1.35}`: glide the view onto a source point and zoom in (e.g. a boss HP bar); optional `"back_from"`, `"back_to"` glide back out (freeze -> zoom on the number -> back out as the game resumes). Any effect may carry `"at": s` to start later than the anchor.
- `"hit": false`: no impact sample / shots / ambience for this clip, only the bed (long real-time stretches). `bed_edge_in` / `bed_edge_out`: 0 where the neighbouring clip continues the same source, so the game sound has no dip at the join.
- Long-form (16:9): split a minutes-long source run into clips at the accents and butt them together so the joins are seamless; worked example: see the channel profile's `examples.md` if present.
- A speed below 0.05 holds one real frame (no flow blending), e.g. `[[0.5, 1.0], [0.75, 0.01], [3.0, 0.01]]` freezes 0.75 s after the anchor.
- Several recordings in one edit: give each clip its own `"video"` (recording path) and `"game_audio"` (that recording's 48 kHz game track, absolute or relative to the work folder). `src_kill_frame` is then a frame of that recording. `kill_id` may be a string such as `"A3"` (recording A, kill 3). Clips without them use `project.video` and `audio.game_file`.
  Analyse each recording in its own work folder (scan, kills, game audio), then build the montage in a third folder (worked example: see the channel profile's `examples.md` if present).

## A text
```json
{"text": "BANG", "beat": 24.0, "dur": 2.8, "style": "chrome", "anim": "pop", "pos": [0.5, 0.38], "width": 0.78}
```
Styles: `chrome` (big word), `counter` (x1, x2 ...), `badge`, `caption`, `manga` (Japanese SFX letters: ink fill + white outline, `ink` colour). Anim: `pop`, `float` or `menace` (trembling, JoJo ゴゴゴ). Lyric words use a fixed `size` (fraction of the canvas width; also works for panel styles, e.g. a 16:9 caption at 0.0185). `"align": "left"` makes `pos` x the left edge (lower-third notes).
Only words from the song (typed by the user) and kill counters; no invented captions.

## Order of scripts after a change
`make_edl.py` (only if the plan changed; it overwrites edl.json) -> `exposure.py` -> `render.py --mode preview` -> `verify.py` / `check_hits.py`.
