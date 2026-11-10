"""Shared helpers for the whole-recording scan and check tools (ingest.py, sheets.py, qa.py, preflight.py).

Two small config files replace the per-recording copies of constants:

  <work folder>/recordings.json      which recordings this work folder uses, found by walking up from the current directory
      {"game": "pb0",
       "recordings": {"W": {"video": "<path, absolute or relative to raw_dir>",
                            "audio": "scan/W_audio.flac", "keys": "scan/W_keys.txt"}},
       "templates": {"map": [["W", 1115.0], ["W", 1150.0]], "card": [...], "dead": [...], "menu": [], "loading": []}}
    "audio" / "keys" default to scan/<tag>_audio.flac and scan/<tag>_keys.txt (written by ingest.py).
    A template entry is [tag, seconds]: a frame of that recording that shows the screen to look for
    (a map, an item card, the death screen ...). They are re-picked for a new recording when the old one is gone.

  <profile_dir>/games/<game>.json    per-game HUD boxes and thresholds (private, part of the channel profile)
      {"game": "Phantom Blade Zero", "scan_size": [960, 540],
       "tabbar": {"box": [100, 8, 860, 40], "sigma": 3, "thr": 0.4}, ...}
    Boxes are [x0, y0, x1, y1] in scan_size pixels unless a key says otherwise. Every tool has its own defaults,
    so a game without a profile still gets sheets and the generic checks.
"""
import functools, json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "scripts"))
import numpy as np, cv2
import projcfg

NAME = "recordings.json"


def _fwd(p):
    return os.path.abspath(p).replace("\\", "/")


@functools.lru_cache(maxsize=None)
def find(start=None):
    """path of the nearest recordings.json at or above the current directory, or None"""
    d = os.path.abspath(start or os.getcwd())
    while True:
        f = os.path.join(d, NAME)
        if os.path.isfile(f):
            return _fwd(f)
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


@functools.lru_cache(maxsize=None)
def rec():
    """recordings.json as a dict with absolute paths; {"recordings": {}} when there is none"""
    f = find()
    if not f:
        return {"game": None, "recordings": {}, "templates": {}, "dir": _fwd(os.getcwd()), "file": None}
    r = json.load(open(f, encoding="utf-8"))
    base = os.path.dirname(f)
    raw = projcfg.cfg()["raw_dir"]
    out = {"game": r.get("game"), "recordings": {}, "templates": r.get("templates", {}), "dir": base, "file": f}
    for tag, v in r.get("recordings", {}).items():
        v = {"video": v} if isinstance(v, str) else dict(v)
        vid = v["video"]
        v["video"] = _fwd(vid if os.path.isabs(vid) else os.path.join(raw, vid))
        for k, default in (("audio", f"scan/{tag}_audio.flac"), ("keys", f"scan/{tag}_keys.txt")):
            p = v.get(k, default)
            v[k] = _fwd(p if os.path.isabs(p) else os.path.join(base, p))
        out["recordings"][tag] = v
    return out


def tags():
    return list(rec()["recordings"])


def _r(tag):
    try:
        return rec()["recordings"][tag]
    except KeyError:
        raise SystemExit(f'recording "{tag}" is not in {rec()["file"] or NAME} (known: {", ".join(tags()) or "none"}); add it with ingest.py')


def video(src):
    """a tag from recordings.json -> its video path; anything else is taken as a path"""
    return _r(src)["video"] if src in rec()["recordings"] else src


def audio(tag):
    return _r(tag)["audio"]


def keys(tag):
    """real keyframe times of a recording (s). Recorders add keyframes at scene cuts, so the spacing is not constant."""
    return np.atleast_1d(np.loadtxt(_r(tag)["keys"]))


def workdir():
    """the folder that holds recordings.json (scan/, sheets/, subs/ ... live there)"""
    return rec()["dir"]


@functools.lru_cache(maxsize=None)
def game():
    """the game profile dict, {} when the work folder names no game or the profile has no file for it"""
    g = rec()["game"]
    p = projcfg.profile(f"games/{g}.json") if g else None
    return json.load(open(p, encoding="utf-8")) if p else {}


def scan_size():
    return tuple(game().get("scan_size", (960, 540)))


def val(section, key, default):
    """game()[section][key] with a default, e.g. val("tabbar", "thr", 0.4)"""
    return game().get(section, {}).get(key, default)


def box(section, default, key="box"):
    """(slice(y0, y1), slice(x0, x1)) for numpy indexing, from a [x0, y0, x1, y1] box"""
    x0, y0, x1, y1 = val(section, key, default)
    return (slice(int(y0), int(y1)), slice(int(x0), int(x1)))


def templates(kind):
    """[(tag, t), ...] from recordings.json "templates"[kind]"""
    return [(a, float(b)) for a, b in rec()["templates"].get(kind, [])]


def hp(g, sigma=3):
    """high-pass: the image minus its Gaussian blur (UI lines and text survive, lighting does not)"""
    g = g.astype(np.float32)
    return g - cv2.GaussianBlur(g, (0, 0), sigma)


def ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))


def still(src, t, size=None, gray=True):
    """one frame of a recording (tag or path) at t seconds, scaled to size (default scan_size); None when the decode fails"""
    w, h = size or scan_size()
    c = 1 if gray else 3
    raw = subprocess.run([projcfg.ffmpeg(), "-v", "error", "-ss", str(t), "-i", video(src), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "gray" if gray else "bgr24", "-"], capture_output=True).stdout
    if len(raw) < w * h * c:
        return None
    a = np.frombuffer(raw[:w * h * c], np.uint8)
    return a.reshape(h, w) if gray else a.reshape(h, w, 3)


def frames(src, fps, size=None, ss=None, dur=None, gray=True, threads=2, vf=None):
    """yield (n, frame) at a fixed fps, decoded straight through (no seeks). src = tag or path.
    vf replaces the default "fps=<fps>,scale=<w>:<h>" filter chain (size must then match what it outputs)."""
    w, h = size or scan_size()
    c = 1 if gray else 3
    cmd = [projcfg.ffmpeg(), "-v", "error", "-threads", str(threads)]
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", video(src), "-vf", vf or f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray" if gray else "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = 0
    try:
        while True:
            raw = p.stdout.read(w * h * c)
            if len(raw) < w * h * c:
                break
            a = np.frombuffer(raw, np.uint8)
            yield n, (a.reshape(h, w) if gray else a.reshape(h, w, 3))
            n += 1
    finally:
        p.stdout.close()
        p.wait()


def clock(t):
    t = float(t)
    return f"{int(t) // 3600}:{int(t) % 3600 // 60:02d}:{t % 60:04.1f}"


if __name__ == "__main__":
    r = rec()
    print("recordings.json:", r["file"])
    print("game:", r["game"], "| profile keys:", ", ".join(game()) or "none")
    for t, v in r["recordings"].items():
        print(f'  {t}: {v["video"]}  video {"ok" if os.path.isfile(v["video"]) else "MISSING"}, '
              f'audio {"ok" if os.path.isfile(v["audio"]) else "-"}, keys {"ok" if os.path.isfile(v["keys"]) else "-"}')
    for k, v in r["templates"].items():
        print(f"  templates {k}: {len(v)}")
