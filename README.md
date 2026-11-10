# Vibes Video Editing

Agent skills for editing gameplay videos from the command line. You talk to an AI coding agent, it runs the scripts: finds the moments in a long recording, syncs them to a song, renders a preview, then the final.

No video editor is involved. Everything is FFmpeg + Python, and every editing decision lives in one `edl.json`, so a revision is a small file change plus a re-render.

## Skills

| Skill | What it does |
|---|---|
| [`game-montage`](skills/game-montage/SKILL.md) | Beat-synced 9:16 Shorts and 16:9 long-form cuts from game recordings: moment finding, song analysis, effects and transitions by name, audio mix, render recipes for re-rendering later |

## Use it

1. Make a folder for your channel (your project).
2. Put the skill in it, either way:
   - `npx skills add shaddamalbz/Vibes-Video-Editing` (installs into the right folder for your agent), or
   - download this repo and copy `skills/game-montage` into your agent's skills folder, e.g. `.claude/skills/game-montage` or `.agents/skills/game-montage`.
3. Create the project folders and check your tools (installs nothing, tells you what is missing):
   ```
   python <skill>/scripts/setup_project.py
   python <skill>/scripts/doctor.py
   python -m pip install -r <skill>/requirements.txt
   ```
4. Drop a recording into `Raw Assets/` and ask your agent for a montage, a Short or a long-form cut.

`setup_project.py` creates `video-project.json` (where your folders are) and a blank `profile/`: your channel's own rules, voice, per-game notes and brand. The skill reads the profile first, so it learns your taste once and keeps it. The profile is yours and is not part of this repo.

## Requirements

- Python 3.10+, FFmpeg, and the packages in `skills/game-montage/requirements.txt`.
- Optional: Demucs and Whisper (vocal separation, word finding), an NVIDIA GPU (faster encode).

## Status

Built for one channel and used in production there, then made portable. Developed and tested on Windows 11 with an NVIDIA GPU and 1920x1080 60 fps recordings. macOS, Linux and non-NVIDIA encoders have code paths but are untested. The killfeed detector is tuned for Valorant's default HUD; other games use the generic moment finder.

## License

MIT
