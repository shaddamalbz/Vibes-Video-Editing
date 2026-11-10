# Per-game recipes

The engine is the same for every game. What changes per game: how moments are found, how the game sound is treated, what text is allowed, and the story shape.

**The channel's real per-game recipes belong in `<profile_dir>/games.md`** (private, one section per game). Read that file first when it exists; this page holds only the checklist for a new game, the template for a recipe, and three anonymised patterns to start from.

## A new game
1. Watch a 1-fps contact sheet of the whole recording (`tools/seek_sheet.py`); note the satisfying moments and what marks them (HUD text, flash, sound).
2. Does the recording carry the game's own music? If it clashes with the song, use `game_sfx.py` (hits only) or `tools/split_music.py`; otherwise keep the original game audio as the bed.
3. Ask the owner for the story shape and the text rule (none / song words / SFX words / reaction captions) before writing the edit.
4. Note the HUD: where subtitles, health bars, button hints and damage numbers sit in the 1920x1080 frame, so crops can hide or feature them.
5. When the video is done, add the game's recipe to `<profile_dir>/games.md` using the template below.

## Recipe template (copy into `<profile_dir>/games.md`)
```
## <Game> (<kind of video>)
- Moments: what counts as a moment, the on-screen or audio signal that marks it, the scripts and thresholds that found it, traps.
- Sound: original game audio or music-free track; bed level; impact-hit settings; what the owner disliked.
- Text: what is allowed on screen (none / song words / SFX words / reactions), which game UI must stay visible.
- Story: the order of beats from opening to end card; where the biggest moment lands in the song.
- HUD positions: subtitles, HP bars, damage numbers, button hints (source px); crops / `base_zoom` + `view_y` that hide them.
- Speed: slow-mo style or real speed only.
- Thumbnail: layout, what the photo shows, hook style.
- Upload pack: anything the description must always say.
- Template: the work folder whose make_edl.py to copy (also list it in examples.md).
- Rejected: things tried that the owner turned down, so they are not proposed again.
```

## Pattern: FPS kill montage (9:16)
- Moments: only the player's own kills. A killfeed row with the player's highlight marks them; assists, teammates' kills and deaths look similar and must be excluded on contact sheets. Full method (written for Valorant's HUD): [kill-detection.md](kill-detection.md).
- Sound: the game's kill sound becomes a drum hit on the beat (`audio.kill_hit`), gunshots before the kill are retimed through the speed ramp, the song ducks a little on every kill.
- Story: relaxed opening, then a kill on every beat or every sung hook word, the best kill on the drop, a round-winning kill last, logo card.
- Picking: clearly visible, satisfying kills first (headshots, through smoke, wallbangs, ability plays); weak kills still work as 2-beat `rapid` clips. Speed ramps keep kills from flashing by.
- Text: a kill counter (`counter`) and song words the owner typed are safe; ask before anything else.
- Recordings whose audio trails the picture need per-clip `audio_lag` (see SKILL.md, Lessons).

## Pattern: action-RPG boss hunt (9:16)
- Story: intro card or first appearance of the boss at real speed (a UI element landing on a beat) -> fight montage (dodges, big attacks) -> build-up in the song's quiet break -> the decisive hit or big damage number ON the drop -> the game's own victory banner -> logo card. If the boss survives the "finishing" blow, that twist can be the story (composite song, freeze, second round).
- Moments: `moments.py scan <fight start> <fight end>` -> `moments.py peaks --top 45` (brightness jumps + loud onsets) -> check on `anchor_sheet.py` sheets. Story moments (intro card, stagger / break state, damage totals, victory banner) are found on 1-4 fps contact sheets. `tools/banner_scan.py`, `tools/find_stagger.py`, `tools/screen_scan.py` and `tools/hud_log.py` are template-based finders written for one game's HUD; adapt their crop boxes.
- Sound: such recordings always carry battle music. Two options: the original game audio as the bed under the song (`"audio": {"game_file": "scan/game_audio_st48.wav", "bed": {"on": true, "rel_db": -6}, "shots": {"max": 0}}`, impact hit per clip `{"lead": 0, "rms_db": -8, "post": 0.6}`, louder on the drops, e.g. `rms_db -7, post 1.2, decay_tau 0.6`, duck 6 dB), or the Demucs hits-only track from `game_sfx.py` when the two musics clash. The hits-only track can sound thin; let the owner hear both.
- Subtitles: dialogue subtitles near the bottom (y > 930) are hidden with `"base_zoom": 1.2, "view_y": 465`.
- Huge bosses: `wide` shots for scale, `zoom_to` on the HP bar or damage number during a freeze, speed preset `heavy`. Alternate boss attack and player answer from the start; footage of only dodging reads as weak.
- The game's own UI (name plates, damage numbers, victory banner) usually tells the story better than added text.

## Pattern: story playthrough long-form (16:9)
- Canvas: `"canvas": "16:9"`, game audio only (`audio.bed.gain_db: 0`, a silent `song.wav`, `"hit": false` on real-time stretches), `dip_black_1` between chapters, outro only at the very end (leave time for the platform's end screen).
- Structure: one video, chapter by chapter in play order; start each chapter ~2 s before its in-game title or card. Trim only repositioning, dark lulls, map and menu screens, and land each cut on an action. A few slow-mo accents per chapter; freeze + `zoom_to` on the key number or banner (check each frame: screen-anchored UI stays put, world-anchored bars move).
- Finding trims: a per-2-s activity track (hit level from the music-free audio + motion) plus 1-2 s contact sheets (`tools/seek_sheet.py`, `tools/range_sheet.py`); `tools/sub_scan.py` times dialogue by when subtitles are on screen; `tools/screen_scan.py` finds game-over and loading screens.
- Keyframes: recordings with a regular keyframe interval scan fast with `-skip_frame nokey`; check the interval first, it is not always regular.
- Before the final, scan the preview for menus: map and settings screens often sit right after the moment a chapter ends on (the button-hint strip at the bottom is a reliable signal).
- Thumbnail (16:9): keep text clear of the bottom-right corner (duration badge).
- A 9:16 Short cut from the same footage can show the 16:9 picture as a band in the middle of the canvas (cropped so the game's subtitles fall outside), with a header above and captions below.
