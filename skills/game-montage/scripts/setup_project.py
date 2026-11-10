"""Turn a folder into a video project: writes video-project.json, creates the folders and a blank channel profile.

    python setup_project.py                 in the folder that should become the project
    python setup_project.py D:/MyChannel    or name the folder

Nothing is downloaded or installed. Existing files are never overwritten. Afterwards run `python doctor.py`.
"""
import json, os, sys

import projcfg

BRAND = {
    "_help": "Optional. Paths are relative to this folder. Leave a key out to switch that layer off.",
    "channel": "",
    "logo": "",
    "wordmark": "",
    "endcard_bg": "#000000",
    "palette": {},
    "outro_9x16": "",
    "outro_16x9": "",
}
PROFILE_README = """# Channel profile (private)

Everything here is yours and stays out of the public skill: how your channel looks and sounds.
The skill reads these files when they exist and falls back to neutral defaults when they do not.

- `brand.json`     logo, wordmark, end-card colour, palette, outro clips
- `rules.md`       your ground rules for every edit (length limits, sound taste, what never to do)
- `games.md`       one section per game: how moments are found, text rules, story shape, HUD positions
- `copy-voice.md`  language and voice of titles, descriptions, on-screen text
- `hashtags.md`    your hashtag / tag sets and research notes
- `games/<game>.json`  HUD boxes and thresholds for the scan + check tools
"""


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    os.makedirs(root, exist_ok=True)
    f = os.path.join(root, projcfg.NAME)
    if os.path.exists(f):
        print("kept   ", f)
        conf = json.load(open(f, encoding="utf-8"))
    else:
        conf = {k: v for k, v in projcfg.DEFAULTS.items()}
        json.dump(conf, open(f, "w", encoding="utf-8"), indent=1)
        print("created", f)
    for k in projcfg.DIR_KEYS:
        d = conf.get(k, projcfg.DEFAULTS[k])
        d = d if os.path.isabs(d) else os.path.join(root, d)
        print("kept   " if os.path.isdir(d) else "created", d)
        os.makedirs(d, exist_ok=True)
    prof = conf.get("profile_dir", projcfg.DEFAULTS["profile_dir"])
    prof = prof if os.path.isabs(prof) else os.path.join(root, prof)
    for name, text in (("brand.json", json.dumps(BRAND, indent=1)), ("README.md", PROFILE_README)):
        p = os.path.join(prof, name)
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").write(text)
            print("created", p)
    reuse = conf.get("reusable_dir", projcfg.DEFAULTS["reusable_dir"])
    reuse = reuse if os.path.isabs(reuse) else os.path.join(root, reuse)
    for sub in ("SFX", "Music", "Stickers", "Outro"):
        os.makedirs(os.path.join(reuse, sub), exist_ok=True)
    print("\nNext: python", os.path.join(projcfg.SCRIPTS_DIR, "doctor.py").replace("\\", "/"))


if __name__ == "__main__":
    main()
