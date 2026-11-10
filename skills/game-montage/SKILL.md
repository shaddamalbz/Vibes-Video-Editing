---
name: game-montage
description: Make beat-synced 9:16 gameplay shorts (YouTube Shorts, Reels, TikTok) and 16:9 long-form cuts from game recordings, entirely with command-line tools (FFmpeg, Python/OpenCV, librosa, optional Demucs and Whisper). Works for any game - shooter kill montages, boss fights, story playthroughs. Use when the user wants a montage, edit or short from a gameplay recording, wants kills or big moments found in a long video, asks for a named effect, transition, speed style or text on a moment ("put shake_3 on kill 5"), wants a song synced to the action, wants a long-form cut of a playthrough, or asks about the effect catalog.
---

# Game montage

One engine for every game: find the satisfying moments in a recording, put each one ON a beat of the song (the biggest on the drop), slow down into it, add effects, mix the game sound into the music, and close with the channel's logo card. The same engine cuts 16:9 long-form videos (boss compilations, story playthroughs) with game sound only. Every editing decision lives in one `edl.json`, so a revision is an edit to that file plus a re-render.

`<skill>` below is the folder this file is in (for example `.claude/skills/game-montage` or `.agents/skills/game-montage` inside the project, depending on the agent harness). "Owner" is the person whose channel and recordings these are.

## First time in a project
1. `python <skill>/scripts/setup_project.py [folder]` writes `video-project.json`, creates the folders below and a blank channel profile. It never overwrites existing files and downloads nothing.
2. `python <skill>/scripts/doctor.py` checks ffmpeg, the H.264 encoder, Python packages, fonts and folders, and prints the install command for anything missing. It installs nothing; ask the owner before installing.

`video-project.json` marks the project root. The scripts find it by walking up from the work folder; for a work folder outside the project, set the environment variable `VIDEO_PROJECT` (the file or its folder) or put that path in a one-line file `~/.video-project`. Relative paths resolve against the project folder; every key is optional.

| Key | Default | Holds |
|---|---|---|
| `raw_dir` | `Raw Assets` | the recordings, read only |
| `reusable_dir` | `Reusable Assets` | SFX, music, stickers, outro clips used across videos |
| `editing_dir` | `Editing` | finals + upload packs, one subfolder per upload day |
| `projects_dir` | `Projects` | one work folder per video (scans, edit list, previews, drafts) |
| `recipes_dir` | `Render Recipes` | how to re-render every final |
| `profile_dir` | `profile` | the private channel profile (below) |

Other keys: `ffmpeg` (command or path), `encoder` (`auto` \| `h264_nvenc` \| `libx264` \| `h264_videotoolbox` \| `h264_qsv` \| `h264_amf`), `hwaccel` (`auto` \| `cuda` \| `none`, decode in the scan scripts), `extra_pythonpath` (list of folders), `fonts` (role or font name -> `.ttf` path). Full description: the docstring of `scripts/projcfg.py`.

## Read the channel profile first
`<profile_dir>` is the owner's private knowledge and is never part of this skill. Before starting, read the files that exist and matter for the task; **they override the defaults in this file**:

| File | Holds |
|---|---|
| `rules.md` | the owner's ground rules for every edit (length limits, sound taste, language, machine quirks) |
| `games.md` | one section per game: how moments are found, sound, text rules, story shape, HUD positions |
| `copy-voice.md` | language and voice of on-screen text, titles, descriptions |
| `hashtags.md` | the channel's hashtag / tag sets and research log |
| `brief.md` | the owner's brief template with their defaults |
| `examples.md` | which earlier work folder demonstrates which technique (copy its `make_edl.py` as a start) |
| `brand.json` | logo, wordmark, end-card colour, palette, outro clips. Without a logo here an edit has no logo end card unless its own `endcard` gives one |

No profile yet: ask the owner for the brief ([reference/brief.md](reference/brief.md)), and write what you learn (rules, per-game recipe, voice, tag sets, example folders) into those files as you go, so the next video starts from them.

## Default ground rules
- Never modify the recordings or the brand masters. Work in a new work folder under `<projects_dir>`, never inside the skill folder.
- Every download (song audio, sound effects, reference clips, model weights) and every install needs the owner's explicit yes first.
- Lyrics: never write, transcribe or fetch them. On-screen lyric words come only from words the owner types.
- Show a low-res preview first (9:16: 540x960 at 30 fps; 16:9: 960x540 at 30 fps); render the final (1080p, 60 fps) only after the owner approves it.
- Previews and drafts live only in the work folder; finals (video + thumbnail + upload text) live only in `<editing_dir>/<date>/`. Never keep the same file in both places.
- Never invent events in captions, titles or descriptions (names, deaths, wins, outcomes). See [reference/copy-voice.md](reference/copy-voice.md).
- Asked "where is moment X": offer several timestamped candidates with frame strips (contact sheets) instead of one guess, and let the owner pick.
- The game sound should stay clearly audible under the song unless the owner wants otherwise.
- Explain choices to the owner in plain words, without audio/video jargon.

## Pipeline
New work folder `<projects_dir>/<game>/<name>/` with `montage.json`: `{"video": "<recording path, forward slashes>", "player": "<who>"}` (backslashes break the JSON). Run every script **from the work folder**: `python <skill>/scripts/<script>.py`. Start by asking for the brief.

| # | Step | Scripts (in order) | Result |
|---|------|--------------------|--------|
| 1 | Find the moments | Shooter with a killfeed (tuned for Valorant's HUD): `scan_video.py`, `detect_coarse.py`, `extract_features.py`, `detect_events.py`, `make_sheets.py` -> `verified.json` -> `finalize_kills.py`. Other games: `moments.py scan <a> <b>`, `moments.py peaks`, `moments.py find <t...>`. Always check `anchor_sheet.py sheets/x.jpg <t...>` | list of moments (show it, **wait for the owner's OK** when picking matters) |
| 2 | Game sound | Game audio comes from `scan_video.py` / `moments.py scan`. Recording carries the game's own music and it clashes with the song: `game_sfx.py <a> <b>` (music-free hits track, needs Demucs) | `scan/game_audio_st48.wav` / `scan/game_sfx_st48.wav` |
| 3 | Read the song | `analyze_song2.py song.wav` (tempo), `analyze_song.py song.wav <bpm> beats.json`, then **check the drop per beat** (loudness per beat); `find_vocal_hits.py song.wav <start> <len> --word <hook> --strips` for sung hooks | `beats.json`, `vocal_hits.json` |
| 4 | Write the edit | copy `make_edl_example.py` (or the `make_edl.py` of a similar earlier video, see the profile's `examples.md`) to `make_edl.py` in the work folder, adapt, run; then `exposure.py` | `edl.json` |
| 5 | Preview | `render.py --mode preview --out preview_v1.mp4`, `verify.py preview preview_v1.mp4`, `check_hits.py 30`, then look at frames around every moment. Show the preview from the work folder | `preview_vN.mp4` (work folder only) |
| 6 | Final | create `<editing_dir>/<date>/` first, then render straight into it: `render.py --mode final --out "<editing_dir>/<date>/<game>_<name>_final.mp4"`, `verify.py final "<same path>"` (the render report stays in the work folder) | the final, with no copy in the work folder |
| 7 | Upload pack | thumbnail (no thumbnail builder is bundled: write a small script in the work folder; `<skill>/tools/ai_photo.py` can polish an in-game frame if the owner uses the Codex CLI; drafts stay in the work folder, the approved image is **moved** to the editing folder), plus titles + description + tags in a text file, in the channel's voice ([copy-voice](reference/copy-voice.md)) with hashtags by the research flow in [hashtags](reference/hashtags.md) | `<editing_dir>/<date>/` |
| 8 | Render recipe (every final) | `<skill>/tools/recipe.py new <name> --date <date> --project <work folder>` when the final is approved; run every command the final needs from the raw recording onward (song cut/mix, Demucs, `make_edl.py`, `render.py --mode final`, thumbnail script) through `recipe.py step <name> --name "<what>" --out <file> -- <command>` (`--record-only` for one already run, same command and cwd); after the upload pack `recipe.py seal <name>` and read its warnings (a missing media path the final uses needs its step or `--keep`) | `<recipes_dir>/<date>/<name>/` (recipe.json + snapshot.zip + cache/) |

A sealed recipe lets the owner delete finals and keep only the raw recordings. Re-render later: `recipe.py check <name>`, then `recipe.py rerender <name>` (run it in the background, it can take hours): it checks the raw files by size and fingerprint, puts the scripts back to their snapshot versions for the run (and restores the newer versions afterwards), restores cached audio and upload text, and runs only the steps whose output is gone. `recipe.py list` shows every recipe and whether its raw files are still there.

## Whole recordings and pre-render checks
For hours-long recordings (story playthroughs), prepare the recording once and check every edit before its final. All four tools are in `<skill>/tools/` and read two small files: `recordings.json` in the work folder (which recordings, plus template frames that show the screens to look for) and the per-game profile `<profile_dir>/games/<game>.json` (HUD boxes and thresholds); both are described in `tools/reclib.py`.
- `ingest.py <tag> <video> --game <name>`: registers the recording, writes its keyframe times and audio track, contact sheets of every keyframe, and (when the game profile has the boxes) subtitle crops, boss-name crops and death-screen candidates. About 4 minutes for a 2-hour recording; afterwards analysis only reads files, so several agents can log it in parallel without each starting decoders.
- `sheets.py all | dense | range | frame | times | strips`: every kind of labelled contact sheet. A whole-recording sheet shows one frame per keyframe (a few seconds apart), which misses 1-2 s moments: for "where is moment X", run `dense` or `strips` on the likely span and offer the candidates.
- `qa.py src | edges | loading | video | fadeback | deaths`: looks for screens that must not be in an edit (maps, menus, item cards, death and loading screens, dark frames, fades at cut ends), on the raw footage of every run of the edit (`runs.json`: `[{cid, src, lo, hi, out}]`) or in a rendered file.
- `preflight.py [edit folder] [--preview f] [--final f]`: all of those in one command plus duration vs the edit, first frame, audio to the end, loudness and free disk space. One PASS / WARN / FAIL / SKIP line per check, exit code 0 only without a FAIL. **Run it on the preview before every final, and on the final before the upload pack**; a kind without templates is reported as SKIP "not checked", never as passed.

Details: [per-game recipes](reference/games.md) · [brief](reference/brief.md) · [copy & captions](reference/copy-voice.md) · [hashtags & tags](reference/hashtags.md) · [kill detection (killfeed shooters)](reference/kill-detection.md) · [song analysis](reference/song-analysis.md) · [edl.json cheat sheet](reference/edl.md) · [effect catalog](reference/effects.md) · [helper tools](tools/README.md).

## Engine options (work for any game)
For a worked example of any of these, see the channel profile's `examples.md` if present.
- Per clip `"base_zoom": 1.2, "view_y": 465`: static zoom and vertical view centre, e.g. to hide game subtitles at the bottom of the screen.
- `audio.game_file`: which game track the mix reads (default `scan/game_audio_st48.wav`).
- `audio.bed`: `{"on": true, "rel_db": -5, "edge": 0.008}` plays every clip's game sound continuously under the song, through its speed ramp; per clip `"bed_gain"` scales it (e.g. 0.6 on a loud stinger).
- `audio.sfx`: extra samples on beats, e.g. `[{"file": "<reusable_dir>/SFX/bonk.wav", "beat": 12, "peak_db": -4, "duck_db": 4}]` (`"t"` in seconds instead of `"beat"`; `"offset"` shifts it).
- Calm clips (`"calm": true`) play at real speed from their start frame; give them `"speed": {"keys": [[-100, 1], [100, 1]]}`.
- Composite songs (several songs or tempo changes in one edit, e.g. battle theme -> fanfare -> record scratch -> second song): build one composite `song.wav` yourself and set `"beat_period": 1.0`, `"window_start": 0`, `"window_beats": <length in s>`; every beat value (clip beats, speed keys, sfx, texts, endcard) is then an output time in seconds. Speed presets still work (they are relative to each clip).
- Long songs: a repeated phrase lets the song jump forward seamlessly. Compare chroma per bar to find two matching bars, then cross-correlate within ±40 ms for the exact splice point.
- Anime looks (`scripts/anime.py`): impact frames (`impact_1/2/3`, `impact_bw`: the shot redrawn white/red/black for 1-4 frames; a blown-out flash frame is redrawn from 0.15 s earlier), speed lines (`speedlines_in/out/hold`), manga pages (top-level `"panels"`: panels slam in on beats, then shatter onto the next clip), manga SFX letters (text presets `menace`, `manga_pop`).
- Big-boss looks: per clip `"wide": 0.7` (or keys `{"keys": [[s rel. anchor, w], ...]}`) shows more of the 16:9 frame inside the 9:16 canvas over a blurred, darkened copy (1 = the whole frame; top-level `"wide_bg": {"blur", "dim"}`), so a huge monster isn't cut to a sliver; effect `{"type": "zoom_to", "x", "y" (source px), "z", "from", "to"}` glides onto a point (e.g. the boss HP bar): give that clip `"decode_w": 1920` for a sharp zoom; speed below 0.05 holds one real frame (freeze without ghosting); top-level `"film_bars": 0.045`; any effect can carry `"at": <s>` to fire later in the clip (a second hit); speed preset `heavy` (real speed, short slow-mo on the hit).
- Ice / freeze look (`scripts/frost.py`): effect `freeze_1` / `freeze_2` (the shot turns icy, frost creeps in from the edges toward `focus`; `freeze_2` adds ice cracks from `center` at `crack` s) on a freeze frame (speed key < 0.05), then transition `ice_shatter_1` (the frozen frame breaks into glass shards over the next clip). Glide onto the frozen subject with `zoom_to` (+ `decode_w: 1920`). Sounds: `scripts/make_ice_sfx.py` synthesizes `ice_freeze.wav` (lock click at 0.62 s, use `"offset": -0.62`), `ice_crack.wav`, `ice_shatter.wav` into `<reusable_dir>/SFX/` (peak_db about -5 / -3 / -1.5). `scripts/make_modern_sfx.py` does the same for a sub drop, UI tick, riser and whoosh.
- Overlays (a green-screen character over the footage): `chroma_key.py <video> <out_dir> --start s --end s` (RGBA PNG frames + meta.json, body centre, border lines removed), then top-level `"overlays"` (`overlay.py`: dir, start/end beat, x = body centre, bottom, height, rate = source s per output s to match a dance to the song tempo, src_start, flip, fade, pop). Keep them off the densest action.
- 16:9 long-form canvas (not a Short): top-level `"canvas": "16:9"` (whole frame, streamed decode for minutes-long clips, auto cover-zoom under shake), `"stings"` (mid-video logo cards), clip `"hit": false` (game sound only), `audio.bed.gain_db` (fixed game-sound level), `zoom_to` `back_from`/`back_to`, caption `"size"` + `"align": "left"`, transition `dip_black_1` between chapters. Split a continuous source run into clips at the slow-mo accents and butt them together so the joins are seamless. The final is 16 Mbps by default; top-level `"final_bitrate": "40M"` overrides it for one video (9:16 finals are quality-based and unaffected).
- Multi-recording edits: per clip `"video"` + `"game_audio"` (that recording's game track); `kill_id` may then be a string like `"A3"`. Analyse each recording in its own work folder first, then build the edit in another. Details in [reference/edl.md](reference/edl.md).
- Funny / meme text looks (`scripts/memetext.py` styles `meme`, `tiktok`, `chat`; `<skill>/tools/meme_caption.py` for a caption + sticker overlay) are separate from the brand text look in `scripts/textfx.py`.

## Named presets ("put effect X on kill Y")
All looks have names in `scripts/fx_catalog.py`; the list is [reference/effects.md](reference/effects.md) (generated by `fx_docs.py`). Demo clips are not bundled: `fx_gallery.py` renders one per preset from your own recording into `gallery/fx/<name>.mp4`.
- Moment effect(s): on the clip whose `kill_id` is Y (or whose time matches the second the owner names): `"effects": [{"preset": "shake_3"}, {"preset": "flash_2"}]`. Several presets = a combination. Extra keys override one value: `{"preset": "shake_2", "decay": 0.3}`.
- Transition on the cut after a clip: `"transition_out": {"preset": "whip_1"}`.
- Speed style: `"speed": {"preset": "hero"}`, or explicit keys `{"keys": [[beats rel. moment, speed], ...]}`.
- Text: append to `texts`: `{"preset": "word_pop", "text": "BANG", "beat": <beat>, "dur": 2}` (song words the owner typed, or SFX words where the game's rules allow).
- Then render a new preview. `make_edl.py` overwrites `edl.json`, so either edit `edl.json` and stop re-running the generator, or make the change inside `make_edl.py`.
- A look that does not exist yet: add a preset to `fx_catalog.py` (a brand-new effect type also needs a branch in `render.py` `kill_effects` + `clip_frame`), run `fx_gallery.py --only <name>` from `gallery/` for its demo clip, then `fx_docs.py`.

## Lessons that save time
- Drops: `analyze_song.py` drop candidates can be off by a few beats. Print the loudness (and the part below 150 Hz) per beat and place the hero moment where the song really slams back.
- Sung hooks: separate the vocal with Demucs first. Centre-channel tricks and pitch tracking on the full mix pick up bass/kick and put the moments 1-2 s off; Whisper alone invents words. Hooks often come right after an a cappella stop. If unsure, ask the owner for the second they hear it.
- Audio: lower the song (`song_gain_db` -6 to -7.5) before the limiter or the hits get squashed; duck only above 220 Hz so the song never sounds "edited".
- A/V lag: some recordings' sound trails the picture (seen: 0.06-0.28 s, varying from clip to clip). Per clip `"audio_lag": <s>` reads the hit that much later and skips the onset auto-trim. Measure it as the first >2 kHz crack of the shot or hit (a bass boom peaks ~100 ms later); the auto-trim alone locks onto the boom or onto earlier noise.
- Single-shot edits (no spray sound): find the shots from the HUD ammo counter, not from audio; mix with `bed.on false`, `shots.max 0`, `kill_hit.lead 0`.
- Slow-mo uses optical flow (no ghosting). Run `exposure.py` after every `make_edl.py`. `kill_id` is a number (a string only in multi-recording edits).
- Never let a clip's source range contain another moment or reuse another clip's footage; recheck source ranges after every plan change.
- FFmpeg: `vignette` with a larger angle is darker, use `PI/8`. `drawtext` with `fontfile=` breaks on a Windows drive colon; leave the font out. An ffmpeg build without ffprobe is fine (`tools/probe.py` stands in).
- Shell heredocs break on apostrophes; write scripts with your file-writing tool, then run them.
- Timing, rough guidance for a mid-range NVIDIA laptop: 9:16 preview 2-9 min, final about 8 min for 50 s. Moment-vs-beat must stay under 1 frame (`verify.py` reports it). Demucs on ~3 min of game audio: about 7 min on CPU.
- 16:9 long-form: frames without zoom/shake skip the warp (fast, roughly 80 fps), but slow-mo (optical flow at 1080p) and zoom frames stay slow; a 14-minute final took about an hour, its 540p preview about 5 min. Don't run other heavy jobs during a final.
- NVDEC (`-hwaccel cuda`) decode is not pixel-identical to CPU decode, so the renderer keeps CPU decode; `hwaccel` only speeds up the scan scripts.
- Check previews for menus, maps and pause screens right after the moments you end on.

## Requirements
Run `python <skill>/scripts/doctor.py`; exit code 0 means the core pipeline can run.
- Core: Python 3.10+, FFmpeg (with the `loudnorm` and `ebur128` filters and an H.264 encoder), and the packages numpy, opencv-python, soundfile, scipy, Pillow, librosa (`python -m pip install -r <skill>/requirements.txt`).
- Optional: demucs + torch (vocal / music separation: `find_vocal_hits.py`, `game_sfx.py`, `tools/split_music.py`), openai-whisper (word hints, `tools/vo_check.py`), yt-dlp (song or reference download, only with the owner's yes).
- An NVIDIA GPU is optional. `encoder: "auto"` picks the first of `h264_nvenc`, `libx264`, `h264_videotoolbox`, `h264_qsv`, `h264_amf` that the ffmpeg build has; set it explicitly to force one. The non-NVIDIA paths use the same bitrate targets but are not tuned per vendor.
- Fonts: system fonts are found on Windows, macOS and Linux; set `fonts` in `video-project.json` to use your own.
- Honest status: developed and tested only on Windows 11 with an NVIDIA GPU, on 1920x1080 60 fps recordings. macOS, Linux and the other encoders are untested; the killfeed detector assumes Valorant's default HUD. A few helper tools still carry project-specific constants (see [tools/README.md](tools/README.md)).
