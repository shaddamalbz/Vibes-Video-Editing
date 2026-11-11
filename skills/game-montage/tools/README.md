# tools: helper scripts used across projects

The montage engine itself (`render.py`, `fx_catalog.py`, ...) is in `../scripts/`. These helpers sit beside it; engine scripts import them through `projcfg.use_tools()`.

Run them from a work folder that holds `montage.json` (`{"video": "<recording path>"}`), e.g. `python <skill>/tools/seek_sheet.py 5 0 600 ov`. Times are source seconds. Crop boxes assume a 1920x1080 recording. Tools marked "template" look for one game's HUD element at fixed positions: adapt the crop box and reference frame for another game.

| Tool | What it does | Usage |
|---|---|---|
| `recipe.py` | Render recipe per final: records every step, seals a snapshot, later re-renders from the raw recordings when the final was deleted. Recipes go to `<recipes_dir>/<date>/<name>/` | `recipe.py new <name> --date <date> --project <work folder>` · `step <name> --name "<what>" [--out PATH] [--record-only] -- <command>` · `seal <name> [--keep PATH]` · `check <name\|all>` · `rerender <name> [--dry-run] [--force-all] [--only N,M]` · `list` |
| `probe.py` | ffprobe stand-in for ffmpeg builds without ffprobe: parses `ffmpeg -i` into an ffprobe-like dict; importable (`from probe import probe`) | `probe.py <file>` (json) · `probe.py <file> duration` |
| `seek_sheet.py` | Overview contact sheets of a long recording (8x8 frames, time labels, parallel seeks) into `sheets/` | `seek_sheet.py <step_s> [start] [end] [tag]` (pass `end`: the default is one recording's length) |
| `range_sheet.py` | One compact sheet of several labelled source ranges | `range_sheet.py out.jpg <step_s> name=a-b name=a-b ...` |
| `crop_sheet.py` | One frame per time with source-x grid lines (every 240 px) to pick `crop_x` for the 9:16 crop | `crop_sheet.py out.jpg t1 t2 ...` (`id=t` to label) |
| `hud_log.py` | Sheet of the right-side HUD action log shortly after each time, to read which ability was used (template) | `hud_log.py out.jpg [d=<delay s>] t1 t2 ...` |
| `banner_scan.py` | Finds top-centre attack-name banners over a range and groups them into events (template) | `banner_scan.py <start_s> <end_s> [fps]` |
| `find_stagger.py` | Finds a fixed HUD label ("Stagger Damage") by multi-scale edge template; needs a reference frame in `frames/` (template) | `find_stagger.py <start_s> <end_s> [fps]` |
| `screen_scan.py` | Finds full-screen states (game over, death screen, loading screen); needs a reference frame in `frames/` (template) | `screen_scan.py <start_s> <end_s> [fps]` |
| `sub_scan.py` | Times when a game subtitle is on screen (bright low-saturation pixels in the bottom band): dialogue timing without speech recognition. Writes `scan/subs.json` | `sub_scan.py <start_s> <end_s>` |
| `split_music.py` | Demucs: splits the game sound of the used ranges into "no music" (effects + voices, `scan/nomusic.flac`) and "music" (`scan/music.flac`) | `split_music.py a1-b1 a2-b2 ...` (the timeline offset `OFF0` is a constant in the file) |
| `vo_check.py` | Whisper word-by-word confidence check of a voice-over take | `vo_check.py <wav> [model]` |
| `ai_photo.py` | Thumbnail photo polish: in-game frame -> image generation through the Codex CLI (the owner's own login) -> PNG without text; text and layout stay with the thumbnail script. Looks `dark` (default) or `keep` | `ai_photo.py <frame.png> <out.png> "<what it should show>" [--look dark\|keep] [--model <name>]` |
| `meme_caption.py` | Meme caption (bold rounded text, thick outline) plus an optional sticker from `<reusable_dir>/Stickers`; draws on a frame or writes a transparent overlay | `meme_caption.py <frame.png\|WxH> <out.png> "<text>" --at X Y [--sticker name] [--side right\|left\|below\|above] [--size N] [--fill white\|green]` |
| `frame.py` | One full-resolution frame, optionally cropped, to read small text (quest names, banners) | being reworked, see below |
| `cut_longform.py` | Merges per-chunk review logs into one cut list, snaps cuts to quiet moments, writes chapters, renders a long-form in one ffmpeg pass | being reworked, see below |

## Whole recordings and checks (config-driven)

These read `recordings.json` in the work folder and the game profile `<profile_dir>/games/<game>.json` through `reclib.py` (its docstring describes both files). Run them from the work folder.

| Tool | What it does | Usage |
|---|---|---|
| `reclib.py` | Shared library: recordings, game profile, frame grabbing, template matching. Run it to print what it found | `reclib.py` |
| `ingest.py` | Prepares a new recording: registers it, keyframe times, audio track, whole-recording sheets, HUD crops (subtitles, boss names, death candidates), optional Windows OCR | `ingest.py <tag> <video> [--game <name>] [--steps keys,audio,sheets,hud,ocr] [--force]` |
| `sheets.py` | Labelled contact sheets: whole recording from keyframes, dense span, range, single frame, list of times, strips per window | `sheets.py all\|dense\|range\|frame\|times\|strips ...` (`-h` for each) |
| `qa.py` | Finds unwanted screens in an edit: on the raw footage of every run, at run ends, in a rendered file; fade finder; death-candidate check | `qa.py src\|edges\|loading <runs.json>`, `qa.py video <file>...`, `qa.py fadeback <out.jpg> <SRC:end>...`, `qa.py deaths <tag>` |
| `preflight.py` | Every check in one command with PASS / WARN / FAIL / SKIP lines and a report file; exit code 0 only without a FAIL | `preflight.py [edit folder] [--preview f] [--final f] [--min-free-gb 35]` |
| `thumb.py` | Thumbnails and covers: Shorts cover + 3:4 cover with title and two-line hook, 16:9 thumbnail, text-free cover, in-game photo polish, subtitle removal from a frame. Style from the game profile's `"thumb"` section | `thumb.py short\|long\|cover\|photo\|clean ...` (`-h` for each) |
| `ocr_win.ps1` | Windows OCR over a folder of PNG crops (used by `ingest.py --steps ocr`) | called by ingest |

The older single-purpose scanners in the first table predate these and keep their own constants.

## Status
- `cut_longform.py` and `frame.py` still carry project-specific constants (recording paths, durations, chapter names) from the project they were written for and are being reworked. Do not use them as they are: read them as examples.
- The "template" tools and `split_music.py` have hard-coded crop boxes, reference-frame names or offsets from one game; check the constants at the top of each file before running.
- Optional dependencies: `split_music.py` needs demucs + torch, `vo_check.py` needs openai-whisper, `ai_photo.py` needs the Codex CLI. `python <skill>/scripts/doctor.py` reports what is installed.
