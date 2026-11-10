"""Project config for the skill: where this user's folders, tools and channel profile live.

A project is any folder that holds a `video-project.json`. The scripts find it by walking up from the work folder
(the current directory or MONTAGE_DIR). If the work folder sits outside the project, point at it with the
VIDEO_PROJECT environment variable (the json file or its folder) or a one-line file `~/.video-project` holding that path.

    {
      "raw_dir": "Raw Assets",            recordings, read only
      "reusable_dir": "Reusable Assets",  SFX, stickers, music, outro
      "editing_dir": "Editing",           finals + upload packs, one folder per upload day
      "projects_dir": "Projects",         one work folder per video
      "recipes_dir": "Render Recipes",    how to re-render every final
      "profile_dir": "profile",           private channel profile (brand.json, games.md, copy voice ...)
      "ffmpeg": "ffmpeg",
      "encoder": "auto",                  auto | h264_nvenc | libx264 | h264_videotoolbox | h264_qsv | h264_amf
      "hwaccel": "auto",                  auto | cuda | none
      "extra_pythonpath": [],
      "fonts": {"black": "C:/Windows/Fonts/seguibl.ttf"}
    }

Relative paths resolve against the project folder. Every key is optional; without a config file the defaults above
resolve against the current directory, so the scripts still run.
Run `python setup_project.py` in a new project folder to create the file and the folders, `python doctor.py` to check tools.
"""
import functools, json, os, shutil, subprocess, sys

NAME = "video-project.json"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
TOOLS_DIR = os.path.join(SKILL_DIR, "tools")

DIR_KEYS = ("raw_dir", "reusable_dir", "editing_dir", "projects_dir", "recipes_dir", "profile_dir")
DEFAULTS = {"raw_dir": "Raw Assets", "reusable_dir": "Reusable Assets", "editing_dir": "Editing", "projects_dir": "Projects",
            "recipes_dir": "Render Recipes", "profile_dir": "profile", "ffmpeg": "ffmpeg", "encoder": "auto", "hwaccel": "auto",
            "extra_pythonpath": [], "fonts": {}}


def _fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def find_config(start=None):
    """path of video-project.json, or None"""
    env = os.environ.get("VIDEO_PROJECT")
    cands = [env] if env else []
    d = os.path.abspath(start or os.environ.get("MONTAGE_DIR") or os.getcwd())
    while True:
        cands.append(d)
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    ptr = os.path.join(os.path.expanduser("~"), ".video-project")
    if os.path.isfile(ptr):
        cands.append(open(ptr, encoding="utf-8").read().strip())
    for c in cands:
        if not c:
            continue
        f = c if c.lower().endswith(".json") else os.path.join(c, NAME)
        if os.path.isfile(f):
            return _fwd(f)
    return None


@functools.lru_cache(maxsize=None)
def cfg(start=None):
    """merged config; folder keys are absolute paths with forward slashes; "root" is the project folder (None without a config)"""
    f = find_config(start)
    c = dict(DEFAULTS)
    root = os.getcwd()
    if f:
        c.update(json.load(open(f, encoding="utf-8")))
        root = os.path.dirname(f)
    for k in DIR_KEYS:
        c[k] = _fwd(c[k] if os.path.isabs(c[k]) else os.path.join(root, c[k]))
    c["root"] = _fwd(root) if f else None
    c["config_file"] = f
    return c


def path(key, *parts):
    """e.g. path("reusable_dir", "SFX", "bonk.wav")"""
    return _fwd(os.path.join(cfg()[key], *parts))


def profile(name):
    """a file of the private channel profile, or None when the user has none"""
    p = os.path.join(cfg()["profile_dir"], name)
    return _fwd(p) if os.path.exists(p) else None


def brand():
    """profile/brand.json (logo, wordmark, palette ...) or {}. Relative paths in it resolve against the profile folder."""
    p = profile("brand.json")
    if not p:
        return {}
    b = json.load(open(p, encoding="utf-8"))
    base = os.path.dirname(p)

    def fix(v):
        if isinstance(v, str) and v.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm")) and not os.path.isabs(v):
            return _fwd(os.path.join(base, v))
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v
    return {k: fix(v) for k, v in b.items()}


# font roles the text renderers ask for -> files to try, first hit wins (Windows, macOS, Linux)
FONT_CANDIDATES = {
    "black": ["C:/Windows/Fonts/seguibl.ttf", "C:/Windows/Fonts/ariblk.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semibold": ["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "mono": ["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"],
}


def font(role, *prefer):
    """font file for a role: config "fonts" first, then the files in `prefer`, then the built-in candidates"""
    for f in [cfg()["fonts"].get(role), *prefer, *FONT_CANDIDATES.get(role, []), *FONT_CANDIDATES["bold"]]:
        if f and os.path.isfile(f):
            return f
    raise SystemExit(f'no font found for "{role}": set "fonts": {{"{role}": "<path to a .ttf>"}} in {NAME}')


class FontMap:
    """lazy name -> font file table for the text renderers: {"name": (role, preferred file)}.
    Lookup order: config "fonts"[name], the preferred file, config "fonts"[role], the role's candidates.
    Nothing is resolved until a font is actually drawn."""
    def __init__(self, spec):
        self.spec, self._hit = dict(spec), {}

    def update(self, spec):
        self.spec.update(spec)

    def __contains__(self, k):
        return k in self.spec

    def __getitem__(self, k):
        if k not in self._hit:
            role, prefer = self.spec[k]
            named = cfg()["fonts"].get(k)
            self._hit[k] = named if named and os.path.isfile(named) else font(role, prefer)
        return self._hit[k]

    def get(self, k, default=None):
        return self[k] if k in self.spec else default


def ffmpeg():
    return cfg()["ffmpeg"]


@functools.lru_cache(maxsize=None)
def _encoders():
    try:
        return subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace").stdout
    except OSError:
        return ""


def encoder():
    """H.264 encoder name: the configured one, or the first that this ffmpeg build has"""
    e = cfg()["encoder"]
    if e != "auto":
        return e
    for name in ("h264_nvenc", "libx264", "h264_videotoolbox", "h264_qsv", "h264_amf"):
        if f" {name} " in _encoders():
            return name
    return "libx264"


def hwaccel():
    """["-hwaccel", "cuda"] or [] for decoding in the scan scripts"""
    h = cfg()["hwaccel"]
    if h == "auto":
        h = "cuda" if encoder() == "h264_nvenc" else "none"
    return [] if h in ("none", "", None) else ["-hwaccel", h]


def use_tools():
    """make the helper scripts in tools/ importable (probe.py, recipe.py ...)"""
    for d in (TOOLS_DIR, *cfg()["extra_pythonpath"]):
        if d and d not in sys.path:
            sys.path.insert(0, d)


if __name__ == "__main__":
    c = cfg()
    print(json.dumps(c, indent=1, ensure_ascii=False))
    print("encoder:", encoder(), "| ffmpeg:", shutil.which(ffmpeg()) or "NOT FOUND")
