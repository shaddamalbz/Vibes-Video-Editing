"""Labelled contact sheets of a recording (tag from recordings.json, see reclib.py). Every frame carries its time.

  sheets.py all <tag>... [--every 1] [--cols 6] [--per-sheet 42] [--size 400x225] [--decoders 4] [--until s] [--force]
        whole recording in one keyframe-only pass (far lighter than seek grabs): sheets/all_<tag>_<start>.jpg,
        one sheet per (per-sheet x every) keyframe intervals (42 x 4.167 s = 175 s). Needs scan/<tag>_keys.txt (ingest.py).
        Denser than the keyframes needs a full decode: use "dense" on the span.
  sheets.py dense <tag> <start> <end> <fps> <name>
        fps frames per second, decoded straight through: sheets/<name>_<start>.jpg, 48 frames per sheet
  sheets.py range <tag> <a> <b> <step> <out.jpg> [--cols 6] [--w 400]
        one seek grab every <step> seconds
  sheets.py frame <tag> <t> <out.png> [--crop x y w h]
        one full-resolution frame, optionally cropped
  sheets.py times <tag> <out.jpg> [--offset s] <t>...
        frames at a list of times (each grabbed at t + offset, labelled with t)
  sheets.py strips <tag> <out.jpg> <fps> <a-b>... [--size 320x180] [--cols 12]
        one row per time window (longer windows wrap): the "where is moment X" candidates sheet

An output given as a bare file name lands in <work folder>/sheets/; a path with a folder is used as given.
--label sec (dense, times, strips) writes the seconds only, as the old per-project scripts did.
Never more than 4 ffmpeg processes run at once.
"""
import argparse, os, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import numpy as np, cv2
import reclib, projcfg

MAXPROC = 4                                   # hard cap on parallel ffmpeg processes (seek storms on 30-60 GB files crash the machine)
_SLOT = threading.BoundedSemaphore(MAXPROC)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def label(im, text, org=(4, 18), scale=0.5, thick=4):
    """yellow text with a black outline, in place"""
    cv2.putText(im, text, org, FONT, scale, (0, 0, 0), thick)
    cv2.putText(im, text, org, FONT, scale, (0, 255, 255), 1)
    return im


def stamp(t, dec=1, full=True):
    """"seconds  h:mm:ss.s" (full) or the seconds only"""
    return f"{t:.{dec}f}  {reclib.clock(t)}" if full else f"{t:.{dec}f}"


def grid(ims, cols):
    """tiles -> one image, cols per row, the last row padded with black"""
    ims = list(ims)
    h, w = ims[0].shape[:2]
    while len(ims) % cols:
        ims.append(np.zeros((h, w, 3), np.uint8))
    return np.vstack([np.hstack(ims[r:r + cols]) for r in range(0, len(ims), cols)])


def outpath(p, sub="sheets"):
    """bare file name -> <work folder>/<sub>/<name>; anything with a folder is kept. Creates the folder."""
    if not os.path.dirname(p):
        p = os.path.join(reclib.workdir(), sub, p)
    p = os.path.abspath(p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p.replace("\\", "/")


def save(path, im, q=None):
    """cv2.imwrite that also works for non-ASCII paths (q = JPEG quality); False when the write fails"""
    ok, buf = cv2.imencode(os.path.splitext(path)[1], im, [cv2.IMWRITE_JPEG_QUALITY, q] if q else [])
    if ok:
        with open(path, "wb") as f:
            f.write(buf.tobytes())
    return bool(ok)


def _size(s):
    w, h = str(s).lower().split("x")
    return int(w), int(h)


def _raw(cmd, w, h):
    """run one ffmpeg (inside the process cap) and return its bgr24 frames as a list"""
    n = w * h * 3
    with _SLOT:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        ims = []
        try:
            while True:
                raw = p.stdout.read(n)
                if len(raw) < n:
                    break
                ims.append(np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy())
        finally:
            p.stdout.close()
            p.wait()
    return ims


def grab(tag, t, w, h):
    """one frame at t by a seek; black when the decode fails"""
    ims = _raw([projcfg.ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", reclib.video(tag), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], w, h)
    return ims[0] if ims else np.zeros((h, w, 3), np.uint8)


# ---------------------------------------------------------------- keyframe-only decoding (shared with ingest.py)

def gop(keys, fps=None):
    """nominal keyframe spacing (s): the median gap, snapped to a whole number of frames when the frame rate is known"""
    if len(keys) < 2:
        return 1.0
    g = float(np.median(np.diff(keys)))
    return round(g * fps) / fps if fps else g


def cut(keys, s):
    """(index of the first keyframe at or after s, a seek time just before it).
    The seek time sits at most 0.05 s before that keyframe and never closer to the previous one than half the gap,
    so a small container start offset cannot make the decoder start one keyframe early or late."""
    i = int(np.searchsorted(keys, s - 1e-6))
    if i >= len(keys):
        return i, float(keys[-1]) + 0.05
    back = 0.05 if i == 0 else min(0.05, (keys[i] - keys[i - 1]) / 2)
    return i, max(0.0, float(keys[i]) - back)


def keyframes(tag, s, e, size=None, threads=2, keys=None, vf=None):
    """yield (time, bgr frame) for every keyframe of the recording with s <= time < e, decoding keyframes only.
    Times are the real keyframe times of scan/<tag>_keys.txt. size=None keeps the source size (pass it via vf/size otherwise).
    Holds one slot of the ffmpeg process cap while it runs."""
    keys = reclib.keys(tag) if keys is None else keys
    (i0, t0), (i1, t1) = cut(keys, s), cut(keys, e)
    if i1 <= i0:
        return
    w, h = size
    cmd = [projcfg.ffmpeg(), "-v", "error", "-threads", str(threads), "-skip_frame", "nokey", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}",
           "-i", reclib.video(tag), "-vsync", "0"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    n = 0
    with _SLOT:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        try:
            while n < i1 - i0:
                raw = p.stdout.read(w * h * 3)
                if len(raw) < w * h * 3:
                    break
                yield float(keys[i0 + n]), np.frombuffer(raw, np.uint8).reshape(h, w, 3)
                n += 1
        finally:
            p.stdout.close()
            if p.poll() is None:
                p.kill()
            p.wait()
    if n != i1 - i0:
        print(f"  warning: {tag} {s:.1f}-{e:.1f}: decoded {n} keyframes, the keys file lists {i1 - i0}", flush=True)


# ---------------------------------------------------------------- all

def all_sheets(tag, every=1, cols=6, per_sheet=42, size=(400, 225), decoders=4, until=None, force=False, name="all", quiet=False):
    """whole-recording sheets from keyframes only. Returns the list of files written (existing ones are kept unless force)."""
    import probe
    keys = reclib.keys(tag)
    info = probe.probe(reclib.video(tag))
    fr = next((s.get("r_frame_rate") for s in info["streams"] if s["codec_type"] == "video"), None)
    fps = (lambda a, b: float(a) / float(b))(*fr.split("/")) if fr else None
    span = per_sheet * every * gop(keys, fps)
    end = float(keys[-1]) + 1e-3 if until is None else min(float(until), float(keys[-1]) + 1e-3)
    w, h = size
    folder = os.path.join(reclib.workdir(), "sheets")
    os.makedirs(folder, exist_ok=True)

    def sheet(a):
        out = os.path.join(folder, f"{name}_{tag}_{int(a):05d}.jpg").replace("\\", "/")
        if os.path.isfile(out) and not force:
            return None
        # same windows as the old sheetall.py: a - 0.05 keeps a keyframe that sits right on the boundary in its own sheet
        ims = [label(im.copy(), stamp(t)) for n, (t, im) in enumerate(keyframes(tag, max(0, a - 0.05), a - 0.05 + span, size, 2, keys, f"scale={w}:{h}"))
               if n % every == 0]
        if not ims:
            return None
        save(out, grid(ims, cols), 82)
        if not quiet:
            print(tag, int(a), len(ims), flush=True)
        return out, len(ims)

    with ThreadPoolExecutor(max(1, min(MAXPROC, decoders))) as ex:
        res = [r for r in ex.map(sheet, [float(a) for a in np.arange(0, end, span)]) if r]
    return res


# ---------------------------------------------------------------- dense / range / frame / times / strips

def dense(tag, a, b, fps, name, cols=6, per=48, size=(400, 225), full=True):
    w, h = size
    span = per / fps
    folder = os.path.join(reclib.workdir(), "sheets")
    os.makedirs(folder, exist_ok=True)

    def sheet(s):
        e = min(b, s + span)
        ims = _raw([projcfg.ffmpeg(), "-v", "error", "-threads", "3", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", reclib.video(tag),
                    "-vf", f"fps={fps}:start_time=0,scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], w, h)
        if not ims:
            return None
        for n, im in enumerate(ims):
            label(im, stamp(s + n / fps, 1, full), (4, 20), 0.6)
        out = os.path.join(folder, f"{name}_{int(s):05d}.jpg").replace("\\", "/")
        save(out, grid(ims, cols), 80)
        print(name, int(s), len(ims), flush=True)
        return out

    with ThreadPoolExecutor(MAXPROC) as ex:
        return [r for r in ex.map(sheet, [float(x) for x in np.arange(a, b, span)]) if r]


def range_sheet(tag, a, b, step, out, cols=6, w=400):
    h = w * 9 // 16
    ts = [float(t) for t in np.arange(a, b, step)]
    with ThreadPoolExecutor(MAXPROC) as ex:
        ims = list(ex.map(lambda t: label(grab(tag, t, w, h), stamp(t)), ts))
    out = outpath(out)
    save(out, grid(ims, cols), 82)
    print(out, len(ts), "frames")
    return out


def frame(tag, t, out, crop=None):
    out = outpath(out)
    vf = ["-vf", "crop={2}:{3}:{0}:{1}".format(*crop)] if crop else []
    with _SLOT:
        r = subprocess.run([projcfg.ffmpeg(), "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", reclib.video(tag), "-frames:v", "1", *vf, out])
    if r.returncode or not os.path.isfile(out):
        raise SystemExit(f"no frame at {t} s of {tag}")
    print(out)
    return out


def times_sheet(tag, out, ts, offset=0.0, cols=6, size=(400, 225), full=True):
    w, h = size
    with ThreadPoolExecutor(MAXPROC) as ex:
        ims = list(ex.map(lambda t: label(grab(tag, t + offset, w, h), stamp(t, 2, full), (4, 18), 0.55), ts))
    out = outpath(out)
    save(out, grid(ims, cols), 85)
    print(out, len(ts))
    return out


def strips(tag, out, fps, wins, size=(320, 180), cols=12, full=True):
    w, h = size
    rows = []
    for win in wins:
        a, b = (float(x) for x in win.split("-"))
        ims = _raw([projcfg.ffmpeg(), "-v", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", reclib.video(tag),
                    "-vf", f"fps={fps}:start_time=0,scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], w, h)
        if not ims:
            print(f"  no frames for window {win}", flush=True)
            continue
        for n, im in enumerate(ims):
            label(im, stamp(a + n / fps, 2, full), (3, 16), 0.5, 3)
        g = grid(ims, cols)
        rows += [g[r:r + h] for r in range(0, g.shape[0], h)]
    if not rows:
        raise SystemExit("no frames decoded")
    out = outpath(out)
    save(out, np.vstack(rows), 80)
    print(out, len(rows), "rows")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("all")
    p.add_argument("tags", nargs="+")
    p.add_argument("--every", type=int, default=1)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--per-sheet", type=int, default=42)
    p.add_argument("--size", type=_size, default=(400, 225))
    p.add_argument("--decoders", type=int, default=4)
    p.add_argument("--until", type=float)
    p.add_argument("--name", default="all")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("dense")
    p.add_argument("tag"), p.add_argument("start", type=float), p.add_argument("end", type=float), p.add_argument("fps", type=float), p.add_argument("name")
    p.add_argument("--label", choices=("full", "sec"), default="full")
    p = sub.add_parser("range")
    p.add_argument("tag"), p.add_argument("a", type=float), p.add_argument("b", type=float), p.add_argument("step", type=float), p.add_argument("out")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--w", type=int, default=400)
    p = sub.add_parser("frame")
    p.add_argument("tag"), p.add_argument("t", type=float), p.add_argument("out")
    p.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    p = sub.add_parser("times")
    p.add_argument("tag"), p.add_argument("out")
    p.add_argument("--offset", type=float, default=0.0)
    p.add_argument("--label", choices=("full", "sec"), default="full")
    p.add_argument("t", type=float, nargs="+")
    p = sub.add_parser("strips")
    p.add_argument("tag"), p.add_argument("out"), p.add_argument("fps", type=float)
    p.add_argument("--size", type=_size, default=(320, 180))
    p.add_argument("--cols", type=int, default=12)
    p.add_argument("--label", choices=("full", "sec"), default="full")
    p.add_argument("wins", nargs="+", metavar="a-b")
    a = ap.parse_args(argv)

    for tag in (a.tags if a.cmd == "all" else [a.tag]):
        v = reclib.video(tag)
        if tag not in reclib.tags():
            raise SystemExit(f'recording "{tag}" is not in {reclib.rec()["file"] or "recordings.json"} (known: {", ".join(reclib.tags()) or "none"}); add it with ingest.py')
        if not os.path.isfile(v):
            raise SystemExit(f"video of {tag} not found: {v}")
    if a.cmd == "all":
        for tag in a.tags:
            if not os.path.isfile(reclib.rec()["recordings"][tag]["keys"]):
                raise SystemExit(f'no keyframe list for {tag} ({reclib.rec()["recordings"][tag]["keys"]}); run ingest.py {tag} <video> --steps keys')
            t0 = time.time()
            res = all_sheets(tag, a.every, a.cols, a.per_sheet, a.size, a.decoders, a.until, a.force, a.name)
            print(f"{tag}: {len(res)} sheets, {sum(n for _, n in res)} frames, {time.time() - t0:.0f} s")
        print("done")
    elif a.cmd == "dense":
        dense(a.tag, a.start, a.end, a.fps, a.name, full=a.label == "full")
    elif a.cmd == "range":
        range_sheet(a.tag, a.a, a.b, a.step, a.out, a.cols, a.w)
    elif a.cmd == "frame":
        frame(a.tag, a.t, a.out, a.crop)
    elif a.cmd == "times":
        times_sheet(a.tag, a.out, a.t, a.offset, full=a.label == "full")
    elif a.cmd == "strips":
        strips(a.tag, a.out, a.fps, a.wins, a.size, a.cols, a.label == "full")


if __name__ == "__main__":
    main()
