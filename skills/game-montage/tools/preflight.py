"""One command before rendering a final, and again on the rendered file: every check, one PASS / WARN / FAIL / SKIP line each.

  preflight.py [edit folder] [--preview <file>] [--final <file>] [--thumb <image>] [--skip src,edges,...] [--min-free-gb 35]

The edit folder (default: the current directory) holds edl.json and usually runs.json ([{cid, src, lo, hi, out}]).
recordings.json is found by walking up from it (see reclib.py). Checks, in order:
  config      recordings.json found, every src of runs.json is an existing video, which template kinds exist
  src         qa.scan_src on runs.json: map / card / dead / menu = FAIL, dark frames = WARN
  edges       qa.scan_edges: map / card = FAIL, fades = WARN (a fade right after a bright finisher can be intended)
  loading     qa.scan_loading: any hit = FAIL (SKIP without loading templates)
  with --preview / --final, per file:
  video       qa.scan_video: map frames or hint-strip spans = FAIL
  duration    file length against edl.json song.window_beats x song.beat_period (0.25 s; FAIL for a final, WARN for a preview)
  firstframe  first frame not black (mean luma > 5) unless the edl fades in
  audio       mean volume of the last 20 s before the end card (or the end) above -50 dB
  loudness    integrated loudness (ebur128), WARN outside -15.5 .. -12.5 LUFS
  thumb       not implemented yet (SKIP)
  disk        free space on the drive of editing_dir >= --min-free-gb
Exit code 0 only when nothing failed. The report goes to <edit folder>/preflight_report.txt and .json (--out for another folder).
--skip takes the check names above. --limit-runs N (debugging) scans only the first N runs and marks the report PARTIAL.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

CHECKS = ("config", "src", "edges", "loading", "video", "duration", "firstframe", "audio", "loudness", "thumb", "disk")
BAD_SRC = ("map", "card", "dead", "menu")
LUFS = (-15.5, -12.5)
TAIL_S, TAIL_DB, DUR_TOL, BLACK = 20.0, -50.0, 0.25, 5.0


class Report:
    def __init__(self):
        self.rows = []

    def add(self, check, status, summary, evidence=()):
        row = {"check": check, "status": status, "summary": summary, "evidence": [str(e) for e in evidence]}
        self.rows.append(row)
        for line in self.lines(row):
            print(line, flush=True)

    @staticmethod
    def lines(row):
        return [f'{row["status"]:4}  {row["check"]:18} {row["summary"]}'] + ["        " + e for e in row["evidence"]]

    def count(self, status):
        return sum(r["status"] == status for r in self.rows)


def _run_check(rep, name, fn):
    """run one check; a crash or a SystemExit inside it is a FAIL line, never a traceback or a silent pass"""
    t = time.time()
    try:
        fn()
    except (SystemExit, Exception) as e:
        rep.add(name, "FAIL", f"check could not run: {e!r}" if not isinstance(e, SystemExit) else f"check could not run: {e}")
    rep.rows[-1]["seconds"] = round(time.time() - t, 1)


def _ffmpeg_err(args):
    from reclib import projcfg
    return subprocess.run([projcfg.ffmpeg(), "-hide_banner", "-nostats", *args], capture_output=True, text=True, errors="replace").stderr


def main():
    ap = argparse.ArgumentParser(description="Every pre-render check of an edit in one command (and the checks of a rendered file).")
    ap.add_argument("folder", nargs="?", default=".", help="edit folder with edl.json / runs.json (default: current directory)")
    ap.add_argument("--preview", help="rendered preview to check")
    ap.add_argument("--final", help="rendered final to check")
    ap.add_argument("--thumb", help="thumbnail image (check not implemented yet)")
    ap.add_argument("--skip", default="", help="comma list of checks to skip: " + ",".join(CHECKS))
    ap.add_argument("--min-free-gb", type=float, default=35.0)
    ap.add_argument("--runs", default="runs.json", help="runs file inside the edit folder (default runs.json)")
    ap.add_argument("--workers", type=int, default=4, help="ffmpeg decodes at once in the src scan (default 4)")
    ap.add_argument("--limit-runs", type=int, default=0, metavar="N", help="debugging: only the first N runs (report is marked PARTIAL)")
    ap.add_argument("--out", help="folder for preflight_report.txt/.json and the edges sheet (default: the edit folder)")
    a = ap.parse_args()

    edit = os.path.abspath(a.folder)
    if not os.path.isdir(edit):
        raise SystemExit(f"preflight.py: edit folder not found: {edit}")
    out_dir = os.path.abspath(a.out) if a.out else edit
    files = {k: os.path.abspath(v) for k, v in (("preview", a.preview), ("final", a.final)) if v}
    thumb = os.path.abspath(a.thumb) if a.thumb else None
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    if skip - set(CHECKS):
        raise SystemExit(f'preflight.py: unknown check in --skip: {", ".join(sorted(skip - set(CHECKS)))} (known: {", ".join(CHECKS)})')
    os.makedirs(out_dir, exist_ok=True)
    os.chdir(edit)                      # reclib and projcfg look for their config files from here
    import qa, reclib
    from reclib import projcfg

    rep = Report()
    t0 = time.time()
    print(f"preflight {edit}", flush=True)
    runs_file = os.path.join(edit, a.runs)
    runs = None
    edl = None
    state = {"runs": None, "partial": None}

    def skipped(name):
        if name in skip:
            rep.add(name, "SKIP", "skipped by --skip")
            return True
        return False

    def capture():
        lines = []
        return lines, lambda *x: lines.append(" ".join(str(v) for v in x))

    def not_done(res):
        """evidence lines for anything a scan could not look at"""
        return [n for n in res["notes"] if n.startswith("NOT ")]

    # ---- 1 config
    def config():
        nonlocal edl
        ev, bad = [], []
        r = reclib.rec()
        if r["file"]:
            ev.append(f'recordings.json: {r["file"]} (game {r["game"]}, recordings {", ".join(r["recordings"]) or "none"})')
        else:
            bad.append(f"no recordings.json at or above {edit}")
        if r["file"] and not reclib.game():
            ev.append(f'WARN no game profile games/{r["game"]}.json in {projcfg.cfg()["profile_dir"]}: default boxes and thresholds')
        if os.path.isfile(os.path.join(edit, "edl.json")):
            try:
                edl = json.load(open(os.path.join(edit, "edl.json"), encoding="utf-8"))
                ev.append("edl.json: ok")
            except ValueError as e:
                bad.append(f"edl.json does not parse: {e}")
        else:
            ev.append("edl.json: none (duration, fade-in and end-card checks have nothing to compare with)")
        if os.path.isfile(runs_file):
            rr = qa.load_runs(runs_file)
            if a.limit_runs and a.limit_runs < len(rr):
                state["partial"] = f"--limit-runs {a.limit_runs}: only the first {a.limit_runs} of {len(rr)} runs were scanned"
                rr = rr[:a.limit_runs]
            state["runs"] = rr
            srcs = sorted({x["src"] for x in rr})
            for s in srcs:
                v = reclib.video(s)
                (ev if os.path.isfile(v) else bad).append(f'src {s}: {v}{"" if os.path.isfile(v) else "  MISSING"}')
            ev.append(f'{a.runs}: {len(rr)} runs, {sum(x["hi"] - x["lo"] for x in rr):.1f} s of source')
        else:
            ev.append(f"{a.runs}: none in the edit folder (src, edges and loading checks are skipped)")
        if "config" in skip:
            rep.add("config", "SKIP", "skipped by --skip (files still loaded)")
            return
        rep.add("config", "FAIL" if bad else "PASS", "; ".join(bad) if bad else "recordings, sources and edit files found", bad + ev)
        for kind in ("map", "card", "dead", "menu", "loading"):
            n = len(reclib.templates(kind))
            if not n:
                rep.add(f"tpl:{kind}", "SKIP", f'no "{kind}" templates in recordings.json: {kind} screens are NOT checked')
        have = [f'{k} {len(reclib.templates(k))}' for k in ("map", "card", "dead", "menu", "loading") if reclib.templates(k)]
        rep.rows[-1]["templates"] = have
    _run_check(rep, "config", config)
    runs = state["runs"]

    # ---- 2 src
    def src():
        lines, say = capture()
        res = qa.scan_src(runs, a.workers, say=say, label=a.runs)
        hits = [x for x in lines if x.split(" ", 1)[0] in BAD_SRC]
        dark = [x for x in lines if x.startswith("dark")]
        gaps = not_done(res)
        kinds = [k for k in BAD_SRC if k not in res["skipped"]]
        head = f'{res["seconds"]:.0f} s of raw footage at fps=4, checked: {", ".join(kinds + ["dark"])}'
        if hits or gaps:
            rep.add("src", "FAIL", f"{len(hits)} bad spans, {len(gaps)} not scanned; {head}", hits + gaps + dark)
        elif dark:
            rep.add("src", "WARN", f"{len(dark)} dark spans (listed), no map/card/dead/menu; {head}", dark)
        else:
            rep.add("src", "PASS", f"0 hits; {head}")
        rep.rows[-1]["result"] = res

    # ---- 3 edges
    def edges():
        lines, say = capture()
        res = qa.scan_edges(runs, os.path.join(out_dir, "preflight_edges.jpg"), say=say, label=a.runs)
        bad = [x for x in lines if x.split(" ", 1)[0] in ("map", "card")]
        fades = [x for x in lines if x.startswith("fade ")]
        gaps = not_done(res)
        head = f'first + last frame of {len(runs)} runs'
        sheet = [f"sheet: {os.path.join(out_dir, 'preflight_edges.jpg')}"] if res["hits"] else []
        if bad or gaps:
            rep.add("edges", "FAIL", f"{len(bad)} map/card edges, {len(gaps)} not checked; {head}", bad + gaps + fades + sheet)
        elif fades:
            rep.add("edges", "WARN", f"{len(fades)} fades at run ends (look at them: intended after a finisher, else trim with qa.py fadeback); {head}", fades + sheet)
        else:
            rep.add("edges", "PASS", f"0 hits; {head}")
        rep.rows[-1]["result"] = res

    # ---- 4 loading
    def loading():
        if not reclib.templates("loading"):
            rep.add("loading", "SKIP", 'no "loading" templates in recordings.json')
            return
        lines, say = capture()
        res = qa.scan_loading(runs, say=say)
        hits = [x for x in lines if " loading until " in x]
        gaps = not_done(res)
        if hits or gaps:
            rep.add("loading", "FAIL", f"{len(hits)} runs start on a loading screen, {len(gaps)} not scanned", hits + gaps)
        else:
            rep.add("loading", "PASS", f"0 hits in the first 5 s of {len(runs)} runs")
        rep.rows[-1]["result"] = res

    for name, fn in (("src", src), ("edges", edges), ("loading", loading)):
        if skipped(name):
            continue
        if not runs:
            rep.add(name, "SKIP", f"no {a.runs} in the edit folder")
            continue
        _run_check(rep, name, fn)

    # ---- 5 rendered file
    song = (edl or {}).get("song", {})
    expected = song["window_beats"] * song.get("beat_period", 1.0) if "window_beats" in song else None

    def video_checks(role, path):
        tag = lambda n: f"{n}:{role}"
        if not os.path.isfile(path):
            rep.add(tag("video"), "FAIL", f"file not found: {path}")
            return
        from probe import probe
        info = probe(path)
        dur = float(info["format"].get("duration") or 0)
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])

        def scan():
            lines, say = capture()
            res = qa.scan_video(path, say=say)
            gaps = not_done(res)
            n = len(res["map_frames"]) + len(res["hint_spans"])
            head = f'{res.get("seconds", 0):.0f} s at fps=4'
            status = "FAIL" if n or gaps else "SKIP" if len(res["skipped"]) == 2 else "PASS"
            if res["skipped"]:
                head += "; NOT checked (no templates): " + ", ".join(res["skipped"])
            rep.add(tag("video"), status, f'{len(res["map_frames"])} map frames, {len(res["hint_spans"])} hint-strip spans; {head}; {path}',
                    [x for x in lines if not x.startswith("note:")] if n else gaps)
            rep.rows[-1]["result"] = res

        def duration():
            if expected is None:
                rep.add(tag("duration"), "SKIP", f"file is {dur:.2f} s; edl.json has no song.window_beats to compare with")
                return
            d = dur - expected
            ok = abs(d) <= DUR_TOL
            status = "PASS" if ok else "FAIL" if role == "final" else "WARN"
            why = "" if ok or role == "final" else " (a preview older than edl.json? render a new one before judging it)"
            rep.add(tag("duration"), status, f"file {dur:.2f} s, edl {expected:.2f} s ({song['window_beats']} beats x {song.get('beat_period', 1.0)} s), "
                    f"difference {d:+.2f} s, tolerance {DUR_TOL} s{why}")

        def firstframe():
            fade_in = (edl or {}).get("fades", {}).get("video_in", 0) or 0
            if fade_in > 0:
                rep.add(tag("firstframe"), "SKIP", f"edl fades in over {fade_in} s, a dark first frame is expected")
                return
            im = reclib.still(path, 0)
            if im is None:
                rep.add(tag("firstframe"), "FAIL", "first frame could not be decoded")
            else:
                m = float(im.mean())
                rep.add(tag("firstframe"), "PASS" if m > BLACK else "FAIL", f"mean luma {m:.1f} (black is {BLACK:.0f} or less)")

        def audio():
            if not has_audio:
                rep.add(tag("audio"), "FAIL", "the file has no audio stream")
                return
            ec = (edl or {}).get("endcard") or {}
            end = ec["start_beat"] * song.get("beat_period", 1.0) if "start_beat" in ec else dur
            what = f'before the end card at {end:.2f} s' if "start_beat" in ec else "of the file (no end card in the edl)"
            end = min(end, dur)
            a0 = max(0.0, end - TAIL_S)
            err = _ffmpeg_err(["-ss", f"{a0:.3f}", "-t", f"{end - a0:.3f}", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"])
            m, p = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", err), re.search(r"max_volume: (-?[\d.]+|-inf) dB", err)
            if not m:
                rep.add(tag("audio"), "FAIL", f"volumedetect gave no result for {a0:.2f}-{end:.2f} s")
                return
            mean = float(m[1])
            rep.add(tag("audio"), "PASS" if mean > TAIL_DB else "FAIL",
                    f"last {end - a0:.0f} s {what}: mean {mean:.1f} dB, peak {p[1] if p else '?'} dB (silent is {TAIL_DB:.0f} dB or less)")

        def loudness():
            if not has_audio:
                rep.add(tag("loudness"), "SKIP", "no audio stream")
                return
            err = _ffmpeg_err(["-i", path, "-vn", "-af", "ebur128=framelog=verbose", "-f", "null", "-"])
            m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err[err.rfind("Summary"):] if "Summary" in err else "")
            if not m:
                rep.add(tag("loudness"), "WARN", "ebur128 gave no integrated loudness (filter missing in this ffmpeg build?)")
                return
            i = float(m[0])
            ok = LUFS[0] <= i <= LUFS[1]
            rep.add(tag("loudness"), "PASS" if ok else "WARN", f"integrated {i:.1f} LUFS (wanted {LUFS[0]} .. {LUFS[1]})")

        for name, fn in (("video", scan), ("duration", duration), ("firstframe", firstframe), ("audio", audio), ("loudness", loudness)):
            if name in skip:
                rep.add(tag(name), "SKIP", "skipped by --skip")
            else:
                _run_check(rep, tag(name), fn)

    for role, path in files.items():
        video_checks(role, path)
    if not files:
        rep.add("video", "SKIP", "no --preview or --final given: rendered-file checks (video, duration, firstframe, audio, loudness) not run")

    # ---- 6 thumbnail
    # TODO: compare the thumbnail with the video (photo region against the first frame / the hook moment, text inside the safe area).
    if thumb:
        rep.add("thumb", "SKIP", f'not implemented ({thumb}{"" if os.path.isfile(thumb) else ", file not found"})')

    # ---- 7 disk
    def disk():
        d = projcfg.cfg()["editing_dir"]
        p = d
        while not os.path.exists(p) and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        free = shutil.disk_usage(p).free / 1024 ** 3
        rep.add("disk", "PASS" if free >= a.min_free_gb else "FAIL", f"{free:.1f} GB free on the drive of {d}, needed {a.min_free_gb:g} GB")
    if not skipped("disk"):
        _run_check(rep, "disk", disk)

    # ---- summary + report files
    n = {s: rep.count(s) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    verdict = "FAIL" if n["FAIL"] else "PASS"
    tail = [f'preflight {verdict}{" (PARTIAL: " + state["partial"] + ")" if state["partial"] else ""}: '
            f'{n["PASS"]} pass, {n["WARN"]} warn, {n["FAIL"]} fail, {n["SKIP"]} skip, {time.time() - t0:.0f} s']
    tail += [f'  FAIL {r["check"]}: {r["summary"]}' for r in rep.rows if r["status"] == "FAIL"]
    tail += [f'  WARN {r["check"]}: {r["summary"]}' for r in rep.rows if r["status"] == "WARN"]
    print("\n".join(tail), flush=True)
    txt = [f"preflight {edit}", time.strftime("%Y-%m-%d %H:%M:%S")] + [ln for r in rep.rows for ln in Report.lines(r)] + tail
    open(os.path.join(out_dir, "preflight_report.txt"), "w", encoding="utf-8").write("\n".join(txt) + "\n")
    json.dump({"folder": edit.replace("\\", "/"), "time": time.strftime("%Y-%m-%d %H:%M:%S"), "verdict": verdict, "partial": state["partial"],
               "counts": n, "files": files, "checks": rep.rows},
              open(os.path.join(out_dir, "preflight_report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f'report: {os.path.join(out_dir, "preflight_report.txt")}', flush=True)
    sys.exit(1 if n["FAIL"] else 0)


if __name__ == "__main__":
    main()
