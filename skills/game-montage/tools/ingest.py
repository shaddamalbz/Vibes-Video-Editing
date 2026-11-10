"""Prepare a NEW recording in the current work folder, so that later analysis only reads files.

  ingest.py <tag> <video path or file name in raw_dir> [--game <name>] [--steps keys,audio,sheets,hud] [--every 1] [--force]

Steps (default keys,audio,sheets,hud; each skips itself when its output exists, --force redoes it):
  register  always: adds/updates <tag> in ./recordings.json (created when missing, "game" from --game; other keys are kept)
  keys      scan/<tag>_keys.txt    time (s) of every keyframe, one per line (read from the packets, no decode)
  audio     scan/<tag>_audio.flac  first audio stream, 48 kHz stereo
  sheets    sheets/all_<tag>_<start>.jpg  contact sheets of every --every-th keyframe (sheets.py all)
  hud       only when the game profile (profile/games/<game>.json) has subs_band, boss_bar and dead.red:
            one keyframe-only pass that saves  subs/<tag>/<sec*10>.png  subtitle band when it holds outlined white text,
            bars/<tag>/<sec*10>.png  boss-name band when a boss HP bar sits above it (both 2x upscaled for OCR),
            dead_<tag>.txt  times of the red death-screen candidates
  ocr       (Windows only, off unless listed) Windows OCR over the crops -> subs/ocr_<tag>.tsv, bars/ocr_<tag>.tsv, then
            subs/dialog_<tag>.txt (one entry per line of dialogue) and bars/runs_<tag>.txt (boss-name runs)

Test options: --span a b (hud over that span only), --until s (sheets up to s), --audio-span a b (writes scan/<tag>_audio_<a>-<b>.flac
instead of the full file), --ocr-first N (OCR only the first N crops of each folder).
"""
import argparse, difflib, glob, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import numpy as np, cv2
import reclib, projcfg, sheets, probe

HERE = os.path.dirname(os.path.realpath(__file__))
STEPS = ("keys", "audio", "sheets", "hud", "ocr")


def _fwd(p):
    return os.path.abspath(p).replace("\\", "/")


# ---------------------------------------------------------------- register

def find_video(arg):
    raw = projcfg.cfg()["raw_dir"]
    for c in (arg, os.path.join(raw, arg)):
        if os.path.isfile(c):
            return _fwd(c)
    raise SystemExit(f'video not found: "{arg}" is neither a file here ({_fwd(os.getcwd())}) nor in raw_dir ({raw})')


def dump(d):
    """recordings.json text: one line per recording / top-level key (keeps long template lists readable)"""
    lines = []
    for k, v in d.items():
        if k == "recordings" and v:
            inner = ",\n".join(f"  {json.dumps(a, ensure_ascii=False)}: {json.dumps(b, ensure_ascii=False)}" for a, b in v.items())
            lines.append(f' {json.dumps(k)}: {{\n{inner}\n }}')
        elif isinstance(v, dict) and v:
            inner = ",\n".join(f"  {json.dumps(a, ensure_ascii=False)}: {json.dumps(b, ensure_ascii=False)}" for a, b in v.items())
            lines.append(f' {json.dumps(k)}: {{\n{inner}\n }}')
        else:
            lines.append(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def register(tag, video, game):
    """add / update the tag in ./recordings.json; returns a note for the summary"""
    f = os.path.join(os.getcwd(), reclib.NAME)
    new = not os.path.isfile(f)
    if new:
        up = reclib.find()
        if up:
            print(f"note: creating {reclib.NAME} here although one exists above ({up})")
        d = {"game": game, "recordings": {}}
    else:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except ValueError as e:
            raise SystemExit(f"{f} is not valid JSON ({e}); fix it by hand, nothing was changed")
        if game and d.get("game") != game:
            print(f'note: game {d.get("game")!r} -> {game!r}')
            d["game"] = game
        d.setdefault("game", None)
        d.setdefault("recordings", {})
    raw = _fwd(projcfg.cfg()["raw_dir"]).rstrip("/") + "/"
    store = video[len(raw):] if video.lower().startswith(raw.lower()) else video
    old = d["recordings"].get(tag)
    entry = dict(old) if isinstance(old, dict) else {}
    was = old.get("video") if isinstance(old, dict) else old
    if was and was != store:
        print(f"note: {tag} pointed at {was}; now {store}. Old scan files of {tag} belong to the old video: rerun with --force")
    entry["video"] = store
    d["recordings"][tag] = entry
    text = dump(d)
    if new or open(f, encoding="utf-8").read() != text:
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    for fn in (reclib.find, reclib.rec, reclib.game):
        fn.cache_clear()
    return ("created " if new else "updated ") + _fwd(f)


# ---------------------------------------------------------------- keys / audio

def key_times(video):
    """times (s) of every keyframe. Packet flags first (no decode, as fast as the disk reads); a keyframe-only decode as fallback."""
    ff = projcfg.ffmpeg()
    r = subprocess.run([ff, "-v", "error", "-i", video, "-map", "0:v:0", "-c", "copy", "-bsf:v", "noise=drop=not(key)", "-f", "framecrc", "-"],
                       capture_output=True, text=True, errors="replace")
    tb, ts = 1 / 1000, []
    for ln in r.stdout.splitlines():
        m = re.match(r"#tb 0: (\d+)/(\d+)", ln)
        if m:
            tb = int(m[1]) / int(m[2])
        elif ln and ln[0] != "#":
            p = ln.split(",")
            if len(p) >= 3 and p[2].strip().lstrip("-").isdigit():
                ts.append(int(p[2]) * tb)
    how = "packet flags"
    if r.returncode or not ts:
        how = "keyframe decode"
        r = subprocess.run([ff, "-hide_banner", "-skip_frame", "nokey", "-i", video, "-an", "-vsync", "0", "-vf", "showinfo", "-f", "null", "-"],
                           capture_output=True, text=True, errors="replace")
        ts = [float(x) for x in re.findall(r"pts_time:\s*(-?[\d.]+)", r.stderr)]
    if not ts:
        raise SystemExit(f"could not read keyframe times from {video}:\n{(r.stderr or '').strip()[-400:]}")
    return sorted(ts), how


def step_keys(tag, force):
    out = reclib.rec()["recordings"][tag]["keys"]
    if os.path.isfile(out) and not force:
        return "exists", []
    ts, how = key_times(reclib.video(tag))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".tmp", "w", newline="\n") as f:
        f.write("".join(f"{t:.3f}\n" for t in ts))
    os.replace(out + ".tmp", out)
    return f"{len(ts)} keyframes ({how})", [out]


def step_audio(tag, force, span=None):
    out = reclib.audio(tag)
    seek = []
    if span:
        out = f"{os.path.splitext(out)[0]}_{span[0]:g}-{span[1]:g}.flac"
        seek = ["-ss", f"{span[0]:.3f}", "-t", f"{span[1] - span[0]:.3f}"]
    if os.path.isfile(out) and not force:
        return "exists", []
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out[:-5] + ".part.flac"
    # s32 into FLAC = 24-bit samples, the format of the existing scan/<tag>_audio.flac files
    r = subprocess.run([projcfg.ffmpeg(), "-v", "error", "-y", "-i", reclib.video(tag), *seek, "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "48000",
                        "-sample_fmt", "s32", "-c:a", "flac", tmp], capture_output=True, text=True, errors="replace")
    if r.returncode or not os.path.isfile(tmp):
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise SystemExit(f"audio extraction failed (no audio stream?):\n{r.stderr.strip()[-400:]}")
    os.replace(tmp, out)
    return f"{os.path.getsize(out) / 1e6:.0f} MB", [out]


# ---------------------------------------------------------------- hud (the old pb_scan.py pass)

def hud_rules():
    """detection boxes / thresholds from the game profile (1920x1080 pixels, [x0, y0, x1, y1]); the old constants as defaults"""
    v = reclib.val

    def b(section, key, default):
        x0, y0, x1, y1 = (int(x) for x in v(section, key, default))
        return (slice(y0, y1), slice(x0, x1))
    red = reclib.game().get("dead", {}).get("red", {})
    rx0, ry0, rx1, ry1 = (int(x) for x in red.get("box_1080", [780, 150, 1140, 560]))
    return {
        "subs": b("subs_band", "box_1080", [360, 860, 1560, 1000]),
        "bright": v("subs_band", "bright", 215), "dark": v("subs_band", "dark", 90), "sub_px": v("subs_band", "min_px", 150),
        "fill": b("boss_bar", "fill_box_1080", [710, 86, 1210, 98]),
        "fill_thr": v("boss_bar", "fill_thr", 150), "fill_frac": v("boss_bar", "fill_frac", 0.3), "min_cols": v("boss_bar", "min_cols", 15),
        "name": b("boss_bar", "name_box_1080", [700, 118, 1220, 150]),
        "name_bright": v("boss_bar", "name_bright", 190), "name_px": v("boss_bar", "name_min_px", 150),
        "name_crop": b("boss_bar", "name_crop_1080", [680, 114, 1280, 152]),
        "red": (slice(ry0, ry1), slice(rx0, rx1)),
        "r": red.get("r", 110), "dr": red.get("dr", 70), "red_px": red.get("min_px", 2500), "rest_mean": red.get("rest_mean", 45),
    }


def look(t, im, R, sub_dir, bar_dir):
    """one keyframe -> (subtitle?, boss bar?, death screen?); saves the crops"""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    name = f"{int(round(t * 10)):06d}.png"
    sg = g[R["subs"]]
    s = int(((sg > R["bright"]) & (cv2.dilate((sg < R["dark"]).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)).sum() > R["sub_px"])
    if s:
        sheets.save(f"{sub_dir}/{name}", cv2.resize(im[R["subs"]], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    fill = (g[R["fill"]] > R["fill_thr"]).mean(0)
    b = int((fill > R["fill_frac"]).sum() > R["min_cols"] and (g[R["name"]] > R["name_bright"]).sum() > R["name_px"])
    if b:
        sheets.save(f"{bar_dir}/{name}", cv2.resize(im[R["name_crop"]], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    c = im[R["red"]].astype(np.int16)
    red = ((c[..., 2] > R["r"]) & (c[..., 2] - c[..., 1] > R["dr"]) & (c[..., 2] - c[..., 0] > R["dr"])).sum()
    rest = g.copy()
    rest[R["red"]] = 0
    return s, b, int(red > R["red_px"] and rest.mean() < R["rest_mean"])


def step_hud(tag, force, span=None, decoders=4):
    g = reclib.game()
    if not ("subs_band" in g and "boss_bar" in g and "red" in g.get("dead", {})):
        return f'skipped: game profile {reclib.rec()["game"]!r} has no subs_band / boss_bar / dead.red', []
    wd = reclib.workdir()
    dead_f = f"{wd}/dead_{tag}.txt"
    if os.path.isfile(dead_f) and not force:
        return "exists", []
    sub_dir, bar_dir = f"{wd}/subs/{tag}", f"{wd}/bars/{tag}"
    os.makedirs(sub_dir, exist_ok=True)
    os.makedirs(bar_dir, exist_ok=True)
    R = hud_rules()
    W, H = g.get("ref_size", (1920, 1080))
    v = next((s for s in probe.probe(reclib.video(tag))["streams"] if s["codec_type"] == "video"), {})
    vf = None if (v.get("width"), v.get("height")) == (W, H) else f"scale={W}:{H}"
    keys = reclib.keys(tag)
    a, b = span or (0.0, float(keys[-1]) + 1.0)
    sel = keys[(keys >= a - 0.05) & (keys < b - 0.05)]   # the old pb_scan.py edge rule
    if not len(sel):
        return "no keyframes in the span", []
    parts = [p for p in np.array_split(sel, max(1, min(sheets.MAXPROC, decoders))) if len(p)]

    def seg(p):
        return [(t, *look(t, im, R, sub_dir, bar_dir)) for t, im in sheets.keyframes(tag, float(p[0]), float(p[-1]) + 1e-3, (W, H), 3, keys, vf)]

    with ThreadPoolExecutor(len(parts)) as ex:
        res = [r for part in ex.map(seg, parts) for r in part]
    dead = {round(r[0], 1) for r in res if r[3]}
    if os.path.isfile(dead_f):     # redo / another span: keep times outside the scanned span, replace the ones inside
        for ln in open(dead_f):
            if ln.strip() and not (sel[0] - 0.06 <= float(ln) <= sel[-1] + 0.06):
                dead.add(float(ln))
    with open(dead_f, "w", newline="\n") as f:
        f.write("".join(f"{t}\n" for t in sorted(dead)))
    return (f"{len(res)} keyframes, {sum(r[1] for r in res)} subs, {sum(r[2] for r in res)} bars, {sum(r[3] for r in res)} dead frames",
            [sub_dir + "/", bar_dir + "/", dead_f])


# ---------------------------------------------------------------- ocr + dedupe (the old ocr.ps1 + subs_dedupe.py)

def _tsv(path):
    for ln in open(path, encoding="utf-8-sig", errors="replace"):
        if "\t" in ln:
            k, txt = ln.rstrip("\r\n").split("\t", 1)
            if k.strip().isdigit():
                yield int(k) / 10, " ".join(txt.split())


def dedupe_subs(tsv, out, gap=4.0):
    """collapse the OCR lines of consecutive subtitle crops into one entry per line of dialogue. Returns the entry count."""
    res = []
    for t, txt in _tsv(tsv):
        if len(txt) < 8 or sum(c.isalpha() for c in txt) < 0.6 * len(txt):
            continue
        if res and t - res[-1][1] <= gap and difflib.SequenceMatcher(None, res[-1][2], txt).ratio() > 0.6:
            res[-1][1] = t
            if len(txt) > len(res[-1][2]):
                res[-1][2] = txt
        else:
            res.append([t, t, txt])
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"{a:.0f}-{b:.0f}  {txt}\n" for a, b, txt in res))
    return len(res)


def dedupe_bars(tsv, out, gap=40.0):
    """boss-name runs (same name seen again within gap seconds); single sightings are dropped. Returns the run count."""
    runs = []
    for t, txt in _tsv(tsv):
        if len(txt) < 5:
            continue
        if runs and t - runs[-1][1] <= gap and difflib.SequenceMatcher(None, runs[-1][2].lower(), txt.lower()).ratio() > 0.6:
            runs[-1][1] = t
        else:
            runs.append([t, t, txt])
    runs = [r for r in runs if r[1] > r[0]]
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"{a:.0f}-{b:.0f}  {txt}\n" for a, b, txt in runs))
    return len(runs)


def step_ocr(tag, force, first=0):
    if os.name != "nt":
        return "skipped: Windows OCR only", []
    wd = reclib.workdir()
    dialog, runs = f"{wd}/subs/dialog_{tag}.txt", f"{wd}/bars/runs_{tag}.txt"
    if os.path.isfile(dialog) and not force:
        return "exists", []
    files, note = [], []
    for kind in ("subs", "bars"):
        d = f"{wd}/{kind}/{tag}"
        if not glob.glob(d + "/*.png"):
            note.append(f"no crops in {kind}/{tag}")
            continue
        tsv = f"{wd}/{kind}/ocr_{tag}.tsv"
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "ocr_win.ps1"), d.replace("/", "\\"),
                            "-out", tsv.replace("/", "\\"), "-first", str(first)], capture_output=True, text=True, errors="replace")
        if r.returncode or not os.path.isfile(tsv):
            raise SystemExit(f"Windows OCR failed on {d}:\n{(r.stderr or r.stdout).strip()[-400:]}")
        files.append(tsv)
    # the same line of dialogue on two neighbouring keyframes is one entry: allow 1.5 keyframe intervals (the old fixed 4 s
    # was written for 2 s keyframes and never merges at 4.17 s)
    keys_f = reclib.rec()["recordings"][tag]["keys"]
    gap = max(4.0, 1.5 * sheets.gop(reclib.keys(tag))) if os.path.isfile(keys_f) else 4.0
    if os.path.isfile(f"{wd}/subs/ocr_{tag}.tsv"):
        note.append(f"{dedupe_subs(f'{wd}/subs/ocr_{tag}.tsv', dialog, gap)} dialogue lines")
        files.append(dialog)
    if os.path.isfile(f"{wd}/bars/ocr_{tag}.tsv"):
        note.append(f"{dedupe_bars(f'{wd}/bars/ocr_{tag}.tsv', runs)} boss-name runs")
        files.append(runs)
    return ", ".join(note), files


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("video")
    ap.add_argument("--game")
    ap.add_argument("--steps", default="keys,audio,sheets,hud")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--span", type=float, nargs=2, metavar=("A", "B"))
    ap.add_argument("--until", type=float)
    ap.add_argument("--audio-span", type=float, nargs=2, metavar=("A", "B"))
    ap.add_argument("--ocr-first", type=int, default=0)
    a = ap.parse_args(argv)
    steps = [s.strip() for s in a.steps.split(",") if s.strip()]
    bad = [s for s in steps if s not in STEPS]
    if bad:
        raise SystemExit(f'unknown step {", ".join(bad)} (steps: {", ".join(STEPS)})')
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.tag):
        raise SystemExit(f'tag "{a.tag}" must be letters, digits, _ or - only (it becomes part of file names)')

    t_all = time.time()
    video = find_video(a.video)
    print(register(a.tag, video, a.game))
    tag, keys_f = a.tag, reclib.rec()["recordings"][a.tag]["keys"]
    info = probe.probe(video)
    dur = float(info["format"].get("duration", 0))
    print(f'{tag}: {video}  {reclib.clock(dur)}  game {reclib.rec()["game"] or "-"}', flush=True)

    took, written = [], []
    for s in STEPS:
        if s not in steps:
            continue
        if s in ("sheets", "hud") and not os.path.isfile(keys_f):
            raise SystemExit(f"step {s} needs {keys_f}: add keys to --steps")
        t0 = time.time()
        if s == "keys":
            note, files = step_keys(tag, a.force)
        elif s == "audio":
            note, files = step_audio(tag, a.force, a.audio_span)
        elif s == "sheets":
            res = sheets.all_sheets(tag, every=a.every, until=a.until, force=a.force, quiet=True)
            note, files = f"{len(res)} new sheets, {sum(n for _, n in res)} frames", [f for f, _ in res]
        elif s == "hud":
            note, files = step_hud(tag, a.force, a.span)
        else:
            note, files = step_ocr(tag, a.force, a.ocr_first)
        took.append((s, time.time() - t0, note))
        written += files
        print(f"  {s:<6} {time.time() - t0:7.1f} s  {note}", flush=True)

    print(f"\n{tag} summary: duration {reclib.clock(dur)} ({dur:.0f} s)")
    if os.path.isfile(keys_f):
        k = reclib.keys(tag)
        med = float(np.median(np.diff(k))) if len(k) > 1 else 0
        print(f"  keyframes {len(k)}, median spacing {med:.3f} s, {int((np.abs(np.diff(k) - med) > 0.01).sum())} irregular gaps")
    print("  steps: " + ", ".join(f"{s} {t:.1f} s" for s, t, _ in took) + f"  (total {time.time() - t_all:.1f} s)")
    if written:
        wd = reclib.workdir().rstrip("/") + "/"
        short = [f[len(wd):] if f.startswith(wd) else f for f in written]
        shown = short if len(short) <= 8 else short[:4] + [f"... {len(short) - 7} more ..."] + short[-3:]
        print("  written: " + ", ".join(shown))
    else:
        print("  written: nothing new")


if __name__ == "__main__":
    main()
