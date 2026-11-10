"""Checks for screens that must not be in a video (maps, menus, item cards, death and loading screens, fades),
on the raw footage of an edit before a render and on a rendered preview or final afterwards.

Run it from a work folder: recordings.json (found by walking up, see reclib.py) names the recordings and the template
frames (one frame of a recording that shows the screen to look for); the game profile gives the HUD boxes and thresholds.
A check kind without templates is skipped and says so. Without a game profile the built-in default boxes are used.

  qa.py src <runs.json> [--workers 5]      every run on the raw footage at fps=4: map / card / dead / menu / dark spans
  qa.py video <video>...                   a rendered file in one pass: map frames (tab bar) and hint-strip spans
  qa.py edges <runs.json> <out.jpg>        first and last frame of every run (an fps=4 scan can step over them): map / card / fade
  qa.py fadeback <out.jpg> <SRC:end>...    where the game fade before a run end starts (0.05 s steps over the last 2 s)
  qa.py deaths <tag> [--file dead_<tag>.txt]   which death candidates are real death screens, grouped into deaths
  qa.py loading <runs.json> [--secs 5]     loading screens in the first seconds of every run (each run on its own src)
  every subcommand takes --json <file> for the structured result.

runs.json = [{"cid": "name", "src": "<tag or path>", "lo": s, "hi": s, "out": s on the timeline}, ...]
The scan functions (scan_src, scan_video, scan_edges, fadeback, deaths, scan_loading) return the result as a dict and
print through say=, so preflight.py imports this file and calls them directly.
Typical scores: maps 0.96+ (other footage under 0.12), cards ~1.0 (a dialogue "Skip" prompt ~0.65), real death screens near 1.0.
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import numpy as np, cv2
import reclib
from reclib import hp, ncc, projcfg

FPS = 4          # scan rate of src and video
GAP = 0.5        # hits this close together are one span
# defaults = the constants of the old per-project scripts, used when the game profile has no value
D_TAB, D_HINT, D_DEAD, D_MENU, D_LOAD = [100, 8, 860, 40], [650, 502, 950, 528], [390, 75, 570, 280], [395, 330, 600, 500], [440, 488, 520, 522]
D_PREVIEW_BOX = [1300, 1005, 600, 50]    # hint strip as x, y, w, h at 1920 wide
D_DEAD_CROP = [780, 150, 360, 410]       # death calligraphy as x, y, w, h at ref_size


def _say(*a):
    print(*a, flush=True)


def die(msg):
    raise SystemExit("qa.py: " + msg)


def _result(check, say):
    """a new result dict with the notes every check starts with (missing recordings.json / game profile)"""
    res = {"check": check, "hits": [], "notes": [], "skipped": [], "unscanned": []}
    r = reclib.rec()
    if not r["file"]:
        _note(res, say, f"no recordings.json at or above {os.getcwd()}: no templates, a run's src is taken as a file path")
    elif not reclib.game():
        _note(res, say, f'no game profile for "{r["game"]}": built-in default boxes and thresholds')
    return res


def _note(res, say, msg):
    res["notes"].append(msg)
    say("note: " + msg)


def load_runs(path):
    if not os.path.isfile(path):
        die(f"runs file not found: {path}")
    try:
        runs = json.load(open(path, encoding="utf-8"))
        for r in runs:
            r["cid"], r["src"], float(r["lo"]), float(r["hi"])
            r.setdefault("out", 0.0)
    except (ValueError, KeyError, TypeError) as e:
        die(f"{path} is not a runs.json ([{{cid, src, lo, hi, out}}, ...]): {e!r}")
    return runs


def _usable(runs, res, say):
    """the runs whose src resolves to an existing video; the others are reported, never dropped silently"""
    ok = []
    for r in runs:
        v = reclib.video(r["src"])
        if os.path.isfile(v):
            ok.append(r)
        else:
            res["unscanned"].append(r["cid"])
            _note(res, say, f'NOT SCANNED run {r["cid"]}: src "{r["src"]}" is not a recording in recordings.json nor a video file ({v})')
    return ok


def _templates(kind, cut, res, say, what=None):
    """template arrays of a kind; cut(tag, t) -> array or None. No usable template = the kind is skipped, with a note."""
    out = []
    for tag, t in reclib.templates(kind):
        a = cut(tag, t)
        if a is None:
            _note(res, say, f"{kind} template {tag} {t}: frame could not be read ({reclib.video(tag)})")
        else:
            out.append(a)
    if not out:
        res["skipped"].append(what or kind)
        _note(res, say, f'{what or kind} NOT CHECKED: no usable "{kind}" templates in recordings.json')
    return out


def _grab(src, t, vf, w, h, ss=None):
    """one grey frame through a filter chain that outputs w x h, as float32; None when the decode fails"""
    raw = subprocess.run([projcfg.ffmpeg(), "-v", "error", "-ss", ss or f"{t}", "-i", reclib.video(src), "-frames:v", "1", "-vf", vf,
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:w * h], np.uint8).reshape(h, w).astype(np.float32) if len(raw) >= w * h else None


def _best(a, tpls):
    return max((ncc(a, x) for x in tpls), default=0.0)


def _spans(hits, key):
    """merge time-ordered hits into spans: same key and at most GAP apart"""
    spans = []
    for h in hits:
        if spans and key(spans[-1]) == key(h) and h["a"] - spans[-1]["b"] <= GAP:
            spans[-1]["b"] = h["a"]
            spans[-1]["score"] = max(spans[-1]["score"], h["score"])
        else:
            spans.append(dict(h, b=h["a"]))
    return spans


# ---------------------------------------------------------------- src: every run on the raw footage

def scan_src(runs, workers=5, say=_say, label="runs"):
    res = _result("src", say)
    s_tab, s_hint, s_menu = reclib.val("tabbar", "sigma", 3), reclib.val("hint", "sigma", 3), reclib.val("menu", "sigma", 3)
    TOP, HINT, DEAD, SHR = reclib.box("tabbar", D_TAB), reclib.box("hint", D_HINT), reclib.box("dead", D_DEAD), reclib.box("menu", D_MENU)
    t_map, t_card, t_dead, t_menu = reclib.val("tabbar", "thr", 0.4), reclib.val("hint", "thr", 0.8), reclib.val("dead", "thr", 0.7), reclib.val("menu", "thr", 0.5)
    dark = reclib.game().get("dark_mean", 5)

    def cut(box, sigma=None):
        def f(tag, t):
            im = reclib.still(tag, t)
            return None if im is None else (hp(im, sigma)[box] if sigma else im[box].astype(np.float32))
        return f
    TT, TH = _templates("map", cut(TOP, s_tab), res, say), _templates("card", cut(HINT, s_hint), res, say)
    TD, TS = _templates("dead", cut(DEAD), res, say), _templates("menu", cut(SHR, s_menu), res, say)

    def scan(r):
        n, hits = 0, []
        for n0, im in reclib.frames(r["src"], FPS, ss=r["lo"], dur=r["hi"] - r["lo"]):
            g = {}
            for s in {s_tab, s_hint, s_menu}:
                g[s] = hp(im, s)
            m, c = _best(g[s_tab][TOP], TT), _best(g[s_hint][HINT], TH)
            k = _best(im[DEAD].astype(np.float32), TD)
            sh = _best(g[s_menu][SHR], TS)
            kind = "map" if m > t_map else "card" if c > t_card else "dead" if k > t_dead else "menu" if sh > t_menu else "dark" if im.mean() < dark else None
            if kind:
                hits.append({"kind": kind, "a": r["lo"] + n / FPS, "out": r["out"] + n / FPS, "score": round(max(m, c, k, sh), 2)})
            n += 1
        return r, n, hits

    total = 0
    with ThreadPoolExecutor(workers) as ex:
        for r, n, hits in ex.map(scan, _usable(runs, res, say)):
            total += n
            if not n and r["hi"] > r["lo"]:
                res["unscanned"].append(r["cid"])
                _note(res, say, f'NOT SCANNED run {r["cid"]}: no frames decoded from {r["src"]} {r["lo"]}-{r["hi"]}')
            for h in _spans(hits, lambda x: x["kind"]):
                t = h["out"]
                say(f'{h["kind"]:4} {r["cid"]:10} {r["src"]} {h["a"]:.2f}-{h["b"]:.2f}  out {int(t // 60)}:{t % 60:05.2f}  score {h["score"]}  (clip {r["lo"]}-{r["hi"]})')
                res["hits"].append(dict(h, cid=r["cid"], src=r["src"], lo=r["lo"], hi=r["hi"]))
    res["seconds"], res["runs"] = total / FPS, len(runs)
    say(f"{label} {total / FPS:.0f} s scanned")
    return res


# ---------------------------------------------------------------- video: a rendered preview or final, one decode

def scan_video(path, say=_say):
    """tabscan (map frames by the tab bar, at scan_size) + previewscan (hint strip cut at the video's own size) in one pass"""
    res = _result("video", say)
    res.update(video=path, map_frames=[], hint_spans=[])
    if not os.path.isfile(path):
        die(f"video not found: {path}")
    from probe import probe
    v = next((x for x in probe(path)["streams"] if x["codec_type"] == "video" and "width" in x), None)
    if not v:
        die(f"no video stream found in {path}")
    SW, SH = v["width"], v["height"]
    W, H = reclib.scan_size()
    TOP, s_tab, t_map = reclib.box("tabbar", D_TAB), reclib.val("tabbar", "sigma", 3), reclib.val("tabbar", "thr", 0.4)
    k = SW / 1920.0
    # even sizes: ffmpeg rounds a yuv420 crop down, an odd height misaligns the raw frames
    X, Y, w, h = [int(b * k) & ~1 for b in reclib.val("hint", "preview_box_1080", D_PREVIEW_BOX)]
    t_hint = reclib.val("hint", "thr_preview", 0.8)

    def tab(tag, t):
        im = reclib.still(tag, t)
        return None if im is None else hp(im, s_tab)[TOP]
    TT = _templates("map", tab, res, say, "map frames (tab bar)")
    strip = lambda tag, t: _grab(tag, t, f"scale={SW}:{SH},crop={w}:{h}:{X}:{Y}", w, h)
    quiet = {"check": "", "hits": [], "notes": [], "skipped": [], "unscanned": []}
    TH = _templates("map", strip, quiet, lambda *a: None) + _templates("card", strip, quiet, lambda *a: None)
    if not TH:
        res["skipped"].append("hint strip")
        _note(res, say, 'hint strip NOT CHECKED: no usable "map" or "card" templates in recordings.json')

    # one decode, both pictures stacked: the scan_size frame on top, the hint strip (native resolution) below
    pw = max(W, w)
    pad = lambda cur, hh: "" if cur == pw else f",pad={pw}:{hh}:0:0"
    vf = (f"fps={FPS},split[qa][qb];[qa]scale={W}:{H},format=gray{pad(W, H)}[qs];"
          f"[qb]crop={w}:{h}:{X}:{Y},format=gray{pad(w, h)}[qc];[qs][qc]vstack")
    n, tabs, hints = 0, [], []
    for n, im in reclib.frames(path, FPS, size=(pw, H + h), vf=vf, threads=3):
        if TT:
            s = _best(hp(im[:H, :W], s_tab)[TOP], TT)
            if s > t_map:
                tabs.append((n / FPS, round(s, 2)))
        if TH:
            sc = _best(im[H:, :w].astype(np.float32), TH)
            if sc > t_hint:
                hints.append({"a": n / FPS, "score": sc})
        n += 1
    spans = _spans(hints, lambda x: 0)
    res.update(seconds=n / FPS, size=[SW, SH], map_frames=[list(x) for x in tabs],
               hint_spans=[{"a": s["a"], "b": s["b"], "score": round(s["score"], 4)} for s in spans])
    res["hits"] = [{"kind": "map", "a": t, "b": t, "score": s} for t, s in tabs] + [dict(x, kind="hint") for x in res["hint_spans"]]
    if not n:
        res["unscanned"].append(path)
        _note(res, say, f"NOT SCANNED: no frames decoded from {path}")
    if TT:
        say(f"{path} {n / FPS:.0f} s, {len(tabs)} map frames {tabs}")                     # the tabscan.py line
    if TH:
        say(f"{path} {n / FPS:.0f} s scanned, {len(spans)} spans")                        # the previewscan.py lines
        for s in spans:
            say(f'  {int(s["a"] // 60)}:{s["a"] % 60:05.2f} - {s["b"] % 60:05.2f}  score {s["score"]:.2f}')
    return res


# ---------------------------------------------------------------- edges: first and last frame of every run

def scan_edges(runs, sheet=None, say=_say, label="runs", workers=4):
    res = _result("edges", say)
    TOP, HINT = reclib.box("tabbar", D_TAB), reclib.box("hint", D_HINT)
    s_tab, s_hint = reclib.val("tabbar", "sigma", 3), reclib.val("hint", "sigma", 3)
    t_map, t_card = reclib.val("tabbar", "thr", 0.4), reclib.val("hint", "thr_edge", 0.6)
    min_ref, ratio = reclib.val("fade", "min_ref", 25), reclib.val("fade", "ratio", 0.7)
    grey = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

    def cut(box, sigma):
        def f(tag, t):
            im = reclib.still(tag, t, gray=False)
            return None if im is None else hp(grey(im), sigma)[box]
        return f
    TT, TH = _templates("map", cut(TOP, s_tab), res, say), _templates("card", cut(HINT, s_hint), res, say)

    def check(j):
        r, side = j
        t, inner = (r["lo"] + 0.02, r["lo"] + 0.5) if side == "in" else (r["hi"] - 0.03, r["hi"] - 0.5)
        im, ref = reclib.still(r["src"], round(t, 3), gray=False), reclib.still(r["src"], round(inner, 3), gray=False)
        if im is None or ref is None:
            return None, r, side, t
        g = grey(im)
        m, c = _best(hp(g, s_tab)[TOP], TT), _best(hp(g, s_hint)[HINT], TH)
        lum, lref = float(im.mean()), float(ref.mean())
        why = "map" if m > t_map else "card" if c > t_card else "fade" if lref > min_ref and lum < ratio * lref else None
        return why, r, side, round(t, 2), round(m, 2), round(c, 2), round(lum), round(lref), im

    ok = _usable(runs, res, say)
    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(check, [(r, side) for r in ok for side in ("in", "out")]))
    ims = []
    for x in out:
        if len(x) == 4:
            res["unscanned"].append(f'{x[1]["cid"]} {x[2]}')
            _note(res, say, f'NOT CHECKED {x[1]["cid"]} {x[2]}: no frame at {x[1]["src"]} {x[3]:.2f}')
            continue
        why, r, side, t, m, c, lum, lref, im = x
        if not why:
            continue
        say(f'{why} {r["cid"]} {side} {r["src"]} {t} map {m} card {c} lum {lum} of {lref}')
        res["hits"].append({"kind": why, "cid": r["cid"], "side": side, "src": r["src"], "t": t, "map": m, "card": c, "lum": lum, "ref_lum": lref})
        im = cv2.resize(im, (320, 180))
        cv2.putText(im, f'{why} {r["cid"]} {side} {r["src"]}{t}', (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
        ims.append(im)
    res["runs"] = len(runs)
    say(f'{label} {len(runs)} clips, {len(res["hits"])} hits')
    _sheet(sheet, ims, 320, 180)
    return res


def _sheet(path, ims, w, h):
    if path and ims:
        while len(ims) % 6:
            ims.append(np.zeros((h, w, 3), np.uint8))
        ok, buf = cv2.imencode(".jpg", np.vstack([np.hstack(ims[i:i + 6]) for i in range(0, len(ims), 6)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
        open(path, "wb").write(buf.tobytes())      # not cv2.imwrite: that fails without a word on a non-ASCII path


# ---------------------------------------------------------------- fadeback: where the fade before a run end starts

def fadeback(sheet, specs, say=_say):
    """specs = ["SRC:end", ...]; walks back from each end to the last frame as bright as the first second of the 2 s window"""
    res = _result("fadeback", say)
    keep = reclib.val("fade", "keep_ratio", 0.93)
    W, H = 320, 180
    ims = []
    for sp in specs:
        s, _, end = sp.rpartition(":")
        try:
            end = float(end)
        except ValueError:
            die(f'fadeback wants SRC:end (for example W:4100.5), got "{sp}"')
        fr = [f.copy() for _, f in reclib.frames(s, 20, size=(W, H), ss=end - 2, dur=2, gray=False)] if os.path.isfile(reclib.video(s)) else []
        if not fr:
            res["unscanned"].append(sp)
            _note(res, say, f"NOT CHECKED {sp}: no frames decoded ({reclib.video(s)})")
            continue
        lum = np.array([f.mean() for f in fr])
        top = np.percentile(lum[:20], 80)
        k = len(lum) - 1
        while k > 0 and lum[k] < keep * top:
            k -= 1
        t = end - 2 + k / 20
        say(f"{s} {end}: last bright {t:.2f} (cut {end - t:.2f} s), lum {' '.join(str(round(x)) for x in lum[-16:])}")
        res["hits"].append({"src": s, "end": end, "last_bright": round(t, 2), "cut": round(end - t, 2), "lum": [round(float(x), 1) for x in lum[-16:]]})
        a, b = fr[k].copy(), fr[-1].copy()
        cv2.putText(a, f"{s}{t:.2f} keep", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
        cv2.putText(b, f"{s}{end} old end", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
        ims += [a, b]
    _sheet(sheet, ims, W, H)
    return res


# ---------------------------------------------------------------- deaths: which candidates are real death screens

def deaths(tag, file=None, say=_say, workers=4):
    res = _result("deaths", say)
    res.update(deaths=[], rejected=[])
    file = file or os.path.join(reclib.workdir(), f"dead_{tag}.txt")
    if not os.path.isfile(file):
        die(f"candidates file not found: {file} (one time in seconds per line)")
    vid = reclib.video(tag)
    if not os.path.isfile(vid):
        die(f'"{tag}" is not a recording in recordings.json nor a video file')
    x, y, w, h = reclib.val("dead", "crop_1080", D_DEAD_CROP)
    real, group = reclib.val("dead", "real", 0.8), reclib.val("dead", "group_s", 10)
    ref_size = tuple(reclib.game().get("ref_size", (1920, 1080)))

    def cropper(src):
        """t -> the calligraphy crop of a frame of src, cut at ref_size (no scaling when the video already has that size)"""
        from probe import probe
        v = next((s for s in probe(reclib.video(src))["streams"] if s["codec_type"] == "video" and "width" in s), {})
        pre = "" if (v.get("width"), v.get("height")) == ref_size else f"scale={ref_size[0]}:{ref_size[1]},"
        return lambda t: _grab(src, t, f"{pre}crop={w}:{h}:{x}:{y}", w, h, ss=f"{t:.2f}")
    tpl = reclib.templates("dead")
    ref = cropper(tpl[0][0])(tpl[0][1]) if tpl else None
    if ref is None:
        res["skipped"].append("dead")
        _note(res, say, 'deaths NOT CHECKED: no usable "dead" template in recordings.json')
        return res
    res["ref"] = list(tpl[0])
    say(f'note: reference = the first "dead" template, {tpl[0][0]} {tpl[0][1]} (crop {w}x{h} at {x},{y}); real death screens score above {real}')
    ts = sorted(set(float(v) for v in open(file, encoding="utf-8").read().split()))
    grab = cropper(tag)

    def sc(t):
        c = grab(t)
        return t, (float(cv2.matchTemplate(c, ref, cv2.TM_CCOEFF_NORMED)[0, 0]) if c is not None else -1)
    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(sc, ts))
    groups = []      # one death = consecutive hits within group_s
    for t in [t for t, s in out if s > real]:
        if not groups or t - groups[-1][-1] > group:
            groups.append([t])
        else:
            groups[-1].append(t)
    say(f"{len(groups)} deaths: " + " ".join(f"{d[0]:.1f}" for d in groups))
    say("rejected: " + " ".join(f"{t:.1f}:{s:.2f}" for t, s in out if s <= real))
    res.update(deaths=groups, rejected=[[t, round(s, 2)] for t, s in out if s <= real], candidates=len(ts))
    res["hits"] = [{"kind": "dead", "a": d[0], "b": d[-1]} for d in groups]
    return res


# ---------------------------------------------------------------- loading: loading screens at the start of a run

def scan_loading(runs, secs=5.0, say=_say, workers=3):
    """Each run is scanned on its own src. (The old loadscan.py always read recording V, whatever the run said.)"""
    res = _result("loading", say)
    SP, sigma = reclib.box("loading", D_LOAD), reclib.val("loading", "sigma", 2)
    thr, max_mean = reclib.val("loading", "thr", 0.6), reclib.val("loading", "max_mean", 40)

    def cut(tag, t):
        im = reclib.still(tag, t)
        return None if im is None else hp(im, sigma)[SP]
    T = _templates("loading", cut, res, say)
    if not T:
        say(f"done {len(runs)}")
        return res

    def scan(r):
        out, n = [], 0
        for n0, im in reclib.frames(r["src"], 10, ss=r["lo"], dur=min(secs, r["hi"] - r["lo"])):
            sc = _best(hp(im, sigma)[SP], T)
            if sc > thr and im.mean() < max_mean:
                out.append((round(r["lo"] + n / 10, 2), round(sc, 2)))
            n += 1
        return r, n, out
    with ThreadPoolExecutor(workers) as ex:
        for r, n, out in ex.map(scan, _usable(runs, res, say)):
            if not n and r["hi"] > r["lo"]:
                res["unscanned"].append(r["cid"])
                _note(res, say, f'NOT SCANNED run {r["cid"]}: no frames decoded from {r["src"]} {r["lo"]}')
            if out:
                say(f'{r["cid"]} {r["lo"]} loading until {out[-1][0]} max {max(s for _, s in out)}')
                res["hits"].append({"kind": "loading", "cid": r["cid"], "src": r["src"], "lo": r["lo"], "a": out[0][0], "b": out[-1][0], "score": max(s for _, s in out)})
    res["runs"] = len(runs)
    say(f"done {len(runs)}")
    return res


# ---------------------------------------------------------------- command line

def main():
    ap = argparse.ArgumentParser(description="QA scans for an edit: unwanted screens on the raw footage and in rendered files.",
                                 epilog="Run from a work folder (recordings.json is found by walking up).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, help):
        p = sub.add_parser(name, help=help)
        p.add_argument("--json", metavar="FILE", help="also write the structured result here")
        return p
    p = cmd("src", "every run of a runs.json on the raw footage: map / card / dead / menu / dark")
    p.add_argument("runs")
    p.add_argument("--workers", type=int, default=5, help="ffmpeg decodes at once (default 5)")
    p = cmd("video", "a rendered preview or final: map frames and hint-strip spans")
    p.add_argument("videos", nargs="+")
    p = cmd("edges", "first and last frame of every run: map / card / fade")
    p.add_argument("runs")
    p.add_argument("sheet", help="jpg sheet of the hits")
    p = cmd("fadeback", "where the fade before a run end starts")
    p.add_argument("sheet", help="jpg sheet: suggested last frame next to the old end")
    p.add_argument("ends", nargs="+", metavar="SRC:end")
    p = cmd("deaths", "check the death candidates of a recording")
    p.add_argument("tag")
    p.add_argument("--file", help="candidate times, default dead_<tag>.txt in the work folder")
    p = cmd("loading", "loading screens in the first seconds of every run")
    p.add_argument("runs")
    p.add_argument("--secs", type=float, default=5.0)
    a = ap.parse_args()

    if a.cmd == "src":
        out = scan_src(load_runs(a.runs), a.workers, label=a.runs)
    elif a.cmd == "video":
        out = [scan_video(v) for v in a.videos]
    elif a.cmd == "edges":
        out = scan_edges(load_runs(a.runs), a.sheet, label=a.runs)
    elif a.cmd == "fadeback":
        out = fadeback(a.sheet, a.ends)
    elif a.cmd == "deaths":
        out = deaths(a.tag, a.file)
    else:
        out = scan_loading(load_runs(a.runs), a.secs)
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
