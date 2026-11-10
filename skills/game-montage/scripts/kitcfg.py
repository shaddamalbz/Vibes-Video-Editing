"""Per-montage settings, read from montage.json in the work folder (the current directory or MONTAGE_DIR).
    {"video": "<raw_dir>/2026-01-31_20-00-00.mkv", "player": "<player name as shown in the game>"}
"""
import json, os

HERE = os.path.abspath(os.environ.get("MONTAGE_DIR", os.getcwd()))
_p = os.path.join(HERE, "montage.json")
CFG = json.load(open(_p, encoding="utf-8")) if os.path.exists(_p) else {}
VIDEO = CFG.get("video", "")
PLAYER = CFG.get("player", "")
if not VIDEO:
    raise SystemExit(f"montage.json with a 'video' path is missing in {HERE}")
