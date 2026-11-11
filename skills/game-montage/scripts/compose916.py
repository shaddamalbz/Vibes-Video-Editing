"""One 9:16 compositor for Shorts: turns a pre-rendered 16:9 video, or a list of shots cut straight from recordings, into a
1080x1920 Short with header, captions, stickers and the channel outro.

    python compose916.py <spec.json> <out.mp4> [--final] [--source r16.mp4]
    from compose916 import render;  render(spec_dict, "out.mp4", final=False)

Preview = 540x960 @ 30 fps, --final = 1080x1920 @ 60 fps. Everything is composed on a 1080x1920 canvas, so all positions
below are 1080x1920 pixels; positions inside the game picture are 1920x1080 pixels whatever the source size.
Frames are streamed (one source frame in memory at a time); see "memory" at the end.

SPEC (json or dict). Give EITHER "source" OR "shots":

  "source": "r16.mp4"      one pre-rendered 16:9 video; its audio is passed through. Times in the spec = seconds of it.
                           (--source / render(source=...) overrides; relative paths resolve against the spec's folder)
  "shots": [...]           a timeline of shots from one or more files, see SHOTS. Times of the overlay keys = output seconds.
  "layout": "band"|"full"  band = blurred dark copy of the picture as background + the game as a band in the middle;
                           full = a 9:16 window of the game fills the screen. Default: "full" when the spec has "views",
                           "view" or "shots", else "band".

 band layout (source mode)
  "band_crop": [240, 50, 1440, 810]   x, y, w, h of the game picture that becomes the band (the default hides a subtitle row
                                      at the bottom of one game: set it per game)
  "band_y": 650, "band_h": 608        top edge and height of the band
  "gamma": 1.12                       brightening of the band (>1 brightens)

 full layout (source mode)
  "view": {"cx": 960, "cy": 540, "z": 1.0}     window centre in the game picture and zoom (1 = 608x1080 window)
  "views": [{"t0", "t1", "cx", "cy", "z", "cx1", "cy1", "z1"}]   window per time range; *1 = value at t1 (eased); a missing
                                      value = the one of "view"; times without a view use "view"
  "gamma": 1.0

 overlays (both layouts, both modes), drawn in this order
  "header": [["LINE 1", "cream"], ["LINE 2", "coral"]]   pixel header from y 330 (312 with a memebox); [] or absent = none
  "header_y", "header_block_max": 12 (cap the pixel size), "emoji": "x" (after the last line),
  "header_t1": s                      header shown until then (fades out over 0.25 s); default: the whole video
  "caps": [{"t0", "t1", "text", "kind": "game"|"react"|"note", "y"}]   game = cream caps, *marked* words yellow and bigger;
                                      react = all yellow; note = small cream text as typed. y default: "cap_y", notes "note_y"
  "cap_y": 1300 (band) / 1330 (full), "note_y": band_y - 96
  "memebox": [{"t0", "t1", "text"}]   white rounded text-post box directly above the band, hard on/off
  "counter": [[t, n], ...], "counter_end": s   skull counter at the band's top-right corner, value n from t on
  "stickers": [{"t0", "t1", "name", "x", "y", "h": 240}]   animated sticker (reusable_dir/Stickers), centred at x, y
  "insets": [{"t0", "t1", "src": [x, y, w, h], "w": out width, "cx", "cy", "border": 6}]   live magnifier box of a part of
                                      the game picture; zooms out of the bottom-left corner and back into it
  "memes": [{"t0", "t1", "text", "stick", "side": "below", "size": 70, "sh": 240, "fill": "white", "x", "y", "shake": 0}]
                                      meme_caption block (caption + sticker) centred at x, y; shake = jitter px

 ending and sound
  "fade_out": 0.35         source mode: fade to black at the end.  Shots mode: fade-out of the SONG (default 0.6)
  "video_fade": s          fade to black at the end in either mode (default: fade_out in source mode, 0 in shots mode)
  "outro": true|false      append profile/brand.json "outro_9x16" (silent, fades in). Default true in source mode, false in
                           shots mode; skipped with a note when the brand has no outro clip
  "loudnorm": true|false   normalise the sound; default true in source mode, false in shots mode
  "loudness": {"I": -14, "TP": -1.5, "LRA": 11}
  "fps", "size": [w, h]    override the preview / final defaults;  "cq": n = constant-quality encode instead of the bitrate one
  "fonts": {"black"|"note"|"box"|"round"|"emoji"|"symbol": "<file>"}, "palette": {"coral": "#FF665E", ...}
  "max_buffer_mb": 1024    see memory

SHOTS (each: {"src", "a", "b", ...}; a, b = seconds in src)
  "rate": 1.0 (speed), "rev": false (play backwards)
  "cx", "cy", "z"          window centre in decode pixels and zoom (1 = full height); "cx1", "cy1", "z1" = at the shot's end (eased)
  "punch": [t, ...]        1.12x zoom punches at these shot-relative times;  "shake": px, "shake_t": until then
  "flash": t               white flash at t (shot-relative);  "bw": true;  "gamma": g
  "band": true  (or "layout": "band")   whole-scene band: full-width band of aspect "band_ar" (16/9) centred at height
                           "band_y" (960; note: the centre, unlike the spec-level band_y) over a blurred dark copy
  "text": [[t0, t1, text, y, size, style], ...]   shot-relative labels centred at height y; style "cap" (white, black
                           outline) or "box" (black on a white rounded box); also as {"t0", "t1", "text", "y", "size", "style"}
  "game_audio": true, "game_db": 0   mix this shot's own sound in (needs "game_gain_db")
  "decode_size": [1920, 1080]
 spec level: "overlays": [[t0, t1, text, y, size, style]] in output time; "song": file, "song_t0": start in the song,
  "song_gain_db": 0, "game_gain_db": null (level of the shots' own sound; null = off). No song and no game sound = silent.

memory: a forward shot is counted first (one decode pass without output) and then streamed, one frame in RAM. A reversed
shot keeps only the frames it will show: in RAM up to "max_buffer_mb", above that in a temporary raw file next to the
output that is read back through a memory map.
"""
import json, math, os, re, struct, subprocess, sys

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:      # importable from anywhere: projcfg and sprites916 sit next to this file
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np, cv2

import projcfg
import sprites916
from sprites916 import SpriteError, paste, premul

W, H = 1080, 1920
LAYOUTS = ("band", "full")


class ComposeError(Exception):
    pass


# ---- small helpers ------------------------------------------------------------------------------------------------------
def _mp4_duration(path):
    """container duration from the mvhd box (what ffprobe reports as format duration), or None"""
    try:
        with open(path, "rb") as f:
            end = os.path.getsize(path)

            def find(name, stop):
                while f.tell() + 8 <= stop:
                    pos = f.tell()
                    size, typ = struct.unpack(">I4s", f.read(8))
                    if size == 1:
                        size = struct.unpack(">Q", f.read(8))[0]
                    elif size == 0:
                        size = stop - pos
                    if typ == name:
                        return pos + size
                    if size < 8:
                        return None
                    f.seek(pos + size)
                return None

            moov_end = find(b"moov", end)
            if not moov_end or not find(b"mvhd", moov_end):
                return None
            ver = f.read(4)[0]
            if ver == 1:
                f.read(16)
                scale, dur = struct.unpack(">IQ", f.read(12))
            else:
                f.read(8)
                scale, dur = struct.unpack(">II", f.read(8))
            return dur / scale if scale else None
    except (OSError, struct.error, IndexError):
        return None


def _probe(path):
    projcfg.use_tools()
    import probe
    p = probe.probe(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video" and "width" in s), None)
    if v is None:
        raise ComposeError(f"no video stream found in {path}")
    dur = (_mp4_duration(path) if path.lower().endswith((".mp4", ".mov", ".m4v")) else None) or float(p["format"].get("duration") or 0)
    return v["width"], v["height"], dur, any(s["codec_type"] == "audio" for s in p["streams"])


def _enc_args(final, cq):
    e = projcfg.encoder()
    if e == "h264_nvenc":
        if cq is not None:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
        return (["-c:v", "h264_nvenc", "-preset", "p6", "-b:v", "16M", "-maxrate", "24M", "-bufsize", "32M"] if final
                else ["-c:v", "h264_nvenc", "-preset", "p5", "-b:v", "4M"])
    if e == "libx264":
        if cq is not None:
            return ["-c:v", "libx264", "-preset", "medium", "-crf", str(cq)]
        return (["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-maxrate", "24M", "-bufsize", "32M"] if final
                else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
    return ["-c:v", e] + (["-b:v", "16M", "-maxrate", "24M", "-bufsize", "32M"] if final else ["-b:v", "4M"])


def _ff(cmd, what):
    if subprocess.run(cmd).returncode:
        raise ComposeError(f"ffmpeg failed while {what}")


def _write(wr, frame):
    try:
        wr.stdin.write(frame.tobytes())
    except (BrokenPipeError, OSError):
        raise ComposeError("the video encoder stopped (see the ffmpeg message above)")


def _lut(gamma):
    return np.clip(255.0 * (np.arange(256) / 255.0) ** (1 / gamma), 0, 255)


def _stickers():
    projcfg.use_tools()
    try:
        import meme_caption
    except SystemExit as e:
        raise ComposeError(str(e))
    return meme_caption


def _sticker_frames(mc, name):
    try:
        return mc.sticker_frames(name)
    except StopIteration:
        raise ComposeError(f'sticker "{name}" not found in {mc.STICKERS} (.png / .webp / .gif)')


# ---- overlays shared by both modes ----------------------------------------------------------------------------------------
class _Overlays:
    def __init__(self, spec, layout, sp, gamma):
        self.band_y = spec.get("band_y", 650)
        self.lut = None if gamma == 1.0 else _lut(gamma).astype(np.uint8)
        boxes = spec.get("memebox") or []
        lines = spec.get("header") or []
        hy = spec.get("header_y", 312 if boxes else 330)
        self.head, bottom = None, hy - 14
        if lines:
            im, bottom = sp.header(lines, spec.get("emoji"), hy, spec.get("header_block_max", 12))
            self.head = premul(im, crop=True)
        self.head_t1 = spec.get("header_t1", 1e9)
        cap_y = spec.get("cap_y", 1300 if layout == "band" else 1330)
        note_y = spec.get("note_y", self.band_y - 96)
        self.caps = [(c["t0"], c["t1"], premul(sp.caption(c["text"], c.get("kind", "game")), crop=True),
                      c.get("y", note_y if c.get("kind") == "note" else cap_y)) for c in spec.get("caps") or []]
        room = self.band_y - 14 - (bottom + 16)                   # free height between header and band
        size = min([sp.memebox(b["text"], room)[1] for b in boxes] or [0])
        self.boxes = [(b["t0"], b["t1"], premul(sp.memebox(b["text"], room, size)[0])) for b in boxes]
        self.cnt = spec.get("counter") or []
        self.cnt_img = {n: premul(sp.counter(n)) for _, n in self.cnt}
        self.cnt_end = spec.get("counter_end", 1e9)
        self.stk, self.memes = [], []
        if spec.get("stickers") or spec.get("memes"):
            mc = _stickers()
            for s in spec.get("stickers") or []:
                fr = _sticker_frames(mc, s["name"])
                h = s.get("h", 240)
                self.stk.append((s["t0"], s["t1"], [premul(mc.sticker(im, h, max(3, h // 22))) for im, _ in fr],
                                 sum(d for _, d in fr) / len(fr) / 1000.0, s["x"], s["y"]))
            for m in spec.get("memes") or []:
                fr = _sticker_frames(mc, m["stick"]) if m.get("stick") else [(None, 100)]
                sps = [premul(mc.block(m.get("text", ""), m.get("stick"), m.get("side", "below"), m.get("size", 70), m.get("sh", 240),
                                       m.get("fill", "white"), frame=i)) for i in range(len(fr))]
                self.memes.append((m["t0"], m["t1"], sps, sum(d for _, d in fr) / len(fr) / 1000.0, m["x"], m["y"], m.get("shake", 0)))
        self.insets = spec.get("insets") or []
        self.rng = np.random.default_rng(7)

    @staticmethod
    def _pop(sp, t, t0):
        pop = min(1.0, (t - t0) / 0.12)
        if pop < 1.0:                                            # small pop-in: scale up from 60 %
            s = 0.6 + 0.4 * pop
            sp = (cv2.resize(sp[0], None, fx=s, fy=s), cv2.resize(sp[1], None, fx=s, fy=s)[..., None], 0, 0)
        return sp

    def draw(self, frame, t, f, k):
        """frame = 1080x1920 canvas, f = the source frame behind it (for insets), k = its width / 1920"""
        if self.head is not None and t < self.head_t1:
            paste(frame, self.head, 0, 0, min(1.0, (self.head_t1 - t) / 0.25))
        for t0, t1, sp, y in self.caps:
            if t0 <= t < t1:
                paste(frame, sp, 0, y, min(1.0, (t - t0) / 0.08, (t1 - t) / 0.08))
        for t0, t1, sp in self.boxes:
            if t0 <= t < t1:
                paste(frame, sp, 0, self.band_y - 14 - sp[1].shape[0])
        cur = None
        for tt, cn in self.cnt:
            if tt <= t < self.cnt_end:
                cur = cn
        if cur is not None:
            sp = self.cnt_img[cur]
            if self.boxes:                                       # inside the band's top-right corner (the box sits above it)
                paste(frame, sp, W - sp[1].shape[1] - 24, self.band_y + 16)
            else:
                paste(frame, sp, W - sp[1].shape[1] - 28, self.band_y - sp[1].shape[0] - 14)
        for t0, t1, sps, fdur, x, y in self.stk:
            if t0 <= t < t1:
                sp = self._pop(sps[int((t - t0) / fdur) % len(sps)], t, t0)
                h_, w_ = sp[1].shape[:2]
                paste(frame, sp, x - w_ / 2, y - h_ / 2)
        for ins in self.insets:
            t0, t1 = ins["t0"], ins["t1"]
            if t0 <= t < t1:
                u = min(1.0, (t - t0) / 0.25, (t1 - t) / 0.2)
                u = u * u * (3 - 2 * u)
                sx, sy, sw_, sh_ = ins["src"]
                crop = f[int(sy * k):int((sy + sh_) * k), int(sx * k):int((sx + sw_) * k)]
                bw = max(8, int(ins["w"] * (0.25 + 0.75 * u)))
                bh = max(4, int(bw * sh_ / sw_))
                box = cv2.resize(crop, (bw, bh), interpolation=cv2.INTER_CUBIC)
                if self.lut is not None:
                    box = cv2.LUT(box, self.lut)
                bd = ins.get("border", 6)
                box = cv2.copyMakeBorder(box, bd, bd, bd, bd, cv2.BORDER_CONSTANT, value=(255, 255, 255))
                cx_ = 140 + (ins["cx"] - 140) * u
                cy_ = 1800 + (ins["cy"] - 1800) * u
                x0_, y0_ = int(cx_ - box.shape[1] / 2), int(cy_ - box.shape[0] / 2)
                x0c, y0c = max(0, x0_), max(0, y0_)
                x1c, y1c = min(W, x0_ + box.shape[1]), min(H, y0_ + box.shape[0])
                if x1c > x0c and y1c > y0c:
                    frame[y0c:y1c, x0c:x1c] = box[y0c - y0_:y1c - y0_, x0c - x0_:x1c - x0_]
        for t0, t1, sps, fdur, x, y, shk in self.memes:
            if t0 <= t < t1:
                sp = self._pop(sps[int((t - t0) / fdur) % len(sps)], t, t0)
                h_, w_ = sp[1].shape[:2]
                jx, jy = self.rng.uniform(-shk, shk, 2) if shk else (0, 0)
                paste(frame, sp, x - w_ / 2 + jx, y - h_ / 2 + jy, min(1.0, (t1 - t) / 0.08))


# ---- source mode: the two layouts --------------------------------------------------------------------------------------
def _band_layout(spec, sw, sh, final, gamma):
    k = sw / 1920.0
    cx, cy, cw, ch = [int(round(v * k)) for v in spec.get("band_crop", (240, 50, 1440, 810))]
    by, bh = spec.get("band_y", 650), spec.get("band_h", 608)
    lut = None if gamma == 1.0 else _lut(gamma).astype(np.float32).astype(np.uint8)
    interp = cv2.INTER_LANCZOS4 if final else cv2.INTER_LINEAR

    def make(f, t):
        bgsrc = cv2.resize(f, (int(H * sw / sh) // 6, H // 6), interpolation=cv2.INTER_AREA)
        x0 = (bgsrc.shape[1] - W // 6) // 2
        bg = cv2.GaussianBlur(bgsrc[:, x0:x0 + W // 6], (0, 0), 4.5)
        bg = cv2.resize(bg, (W, H), interpolation=cv2.INTER_LINEAR)
        hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] *= 0.8
        frame = (cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) * 0.62).astype(np.uint8)
        band = cv2.resize(f[cy:cy + ch, cx:cx + cw], (W, bh), interpolation=interp)
        frame[by:by + bh] = band if lut is None else cv2.LUT(band, lut)
        return frame
    return make


def _full_layout(spec, sw, sh, final, gamma):
    k = sw / 1920.0
    base = {"cx": 960, "cy": 540, "z": 1.0, **(spec.get("view") or {})}
    views = spec.get("views") or []
    lut = None if gamma == 1.0 else _lut(gamma).astype(np.uint8)
    interp = cv2.INTER_LANCZOS4 if final else cv2.INTER_LINEAR

    def view(t):
        for v in views:
            if v["t0"] <= t < v["t1"]:
                u = (t - v["t0"]) / max(1e-6, v["t1"] - v["t0"])
                u = u * u * (3 - 2 * u)
                g = lambda n: v.get(n, base[n]) + (v.get(n + "1", v.get(n, base[n])) - v.get(n, base[n])) * u   # noqa: E731
                return g("cx"), g("cy"), g("z")
        return base["cx"], base["cy"], base["z"]

    def make(f, t):
        cx, cy, z = view(t)
        ww, hh = 608 / z * k, 1080 / z * k
        x0 = min(max(0.0, cx * k - ww / 2), sw - ww)
        y0 = min(max(0.0, cy * k - hh / 2), sh - hh)
        M = np.float32([[W / ww, 0, -x0 * W / ww], [0, H / hh, -y0 * H / hh]])          # sub-pixel window, smooth pushes
        frame = cv2.warpAffine(f, M, (W, H), flags=interp)
        return frame if lut is None else cv2.LUT(frame, lut)
    return make


# ---- shots mode ---------------------------------------------------------------------------------------------------------
def _ease(u):
    return 0.5 - 0.5 * np.cos(np.pi * min(1, max(0, u)))


def _window(img, cx, cy, z):
    sh, sw = img.shape[:2]
    hh = sh / z
    ww = hh * 9 / 16
    cx = min(max(cx, ww / 2), sw - ww / 2)
    cy = min(max(cy, hh / 2), sh - hh / 2)
    M = np.float32([[W / ww, 0, -(cx - ww / 2) * W / ww], [0, H / hh, -(cy - hh / 2) * H / hh]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _scene_band(img, cx, cy, z, ar, yc):
    """a full-width band of aspect ar centred at height yc over a blurred, darkened, zoomed copy of the same frame"""
    sh, sw = img.shape[:2]
    ch = sh / z
    cw = min(sw, ch * ar)
    ch = cw / ar
    cx = min(max(cx, cw / 2), sw - cw / 2)
    cy = min(max(cy, ch / 2), sh - ch / 2)
    bh = int(round(W / ar))
    M = np.float32([[W / cw, 0, -(cx - cw / 2) * W / cw], [0, bh / ch, -(cy - ch / 2) * bh / ch]])
    fg = cv2.warpAffine(img, M, (W, bh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    bg = cv2.resize(_window(cv2.resize(img, (sw // 4, sh // 4)), cx / 4, cy / 4, 1.0), (W // 8, H // 8))
    bg = cv2.GaussianBlur(bg, (0, 0), 6)
    bg = (cv2.resize(bg, (W, H)) * 0.42).astype(np.uint8)
    y0 = int(yc - bh / 2)
    bg[y0:y0 + bh] = fg
    return bg


def _count(ff, src, a, b, fps):
    r = subprocess.run([ff, "-v", "error", "-nostats", "-progress", "pipe:1", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src,
                        "-an", "-vf", f"fps={fps}", "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    n = re.findall(r"^frame=\s*(\d+)", r.stdout, re.M)
    if r.returncode or not n or not int(n[-1]):
        raise ComposeError(f"no frames in {src} between {a} and {b} s")
    return int(n[-1])


def _shot_frames(ff, s, fps, n, idxs, cap_bytes, spool):
    """yield the source frame of every output frame (idxs = index into the shot as played, so already reversed for "rev")"""
    sw, sh = s.get("decode_size", (1920, 1080))
    size = sw * sh * 3
    p = subprocess.Popen([ff, "-v", "error", "-ss", f"{s['a']:.3f}", "-t", f"{s['b'] - s['a']:.3f}", "-i", s["src"], "-vf",
                          f"fps={fps},scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)

    def read():
        raw = p.stdout.read(size)
        return np.frombuffer(raw, np.uint8).reshape(sh, sw, 3) if len(raw) == size else None
    try:
        if not s.get("rev"):
            cur, img = -1, None
            for want in idxs:
                while cur < want:
                    nxt = read()
                    if nxt is None:
                        break
                    cur, img = cur + 1, nxt
                if img is None:
                    raise ComposeError(f"could not decode {s['src']} at {s['a']} s")
                yield img
        else:
            orig = [n - 1 - j for j in idxs]
            need = sorted(set(orig))
            pos = {v: i for i, v in enumerate(need)}
            on_disk = len(need) * size > cap_bytes
            store = (np.memmap(spool, np.uint8, "w+", shape=(len(need), sh, sw, 3)) if on_disk
                     else np.empty((len(need), sh, sw, 3), np.uint8))
            try:
                for i in range(need[-1] + 1):
                    img = read()
                    if img is None:
                        break
                    if i in pos:
                        store[pos[i]] = img
                for o in orig:
                    yield np.array(store[pos[o]]) if on_disk else store[pos[o]]     # a copy, so the map can be closed
            finally:
                mm = getattr(store, "_mmap", None)
                del store
                if mm is not None:
                    mm.close()
                if on_disk and os.path.exists(spool):
                    os.remove(spool)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def _labels(sp, items):
    out = []
    for it in items or []:
        t0, t1, tx, y, sz, st = ([it[k] for k in ("t0", "t1", "text", "y", "size")] + [it.get("style", "cap")]) if isinstance(it, dict) else it
        im = sp.label(tx, sz, st)
        out.append((t0, t1, premul(im), y))
    return out


# ---- render --------------------------------------------------------------------------------------------------------------
def render(spec, out, final=False, source=None, base=None):
    """compose `spec` (dict, see the module docstring) into `out`; source = the 16:9 video (overrides spec["source"]);
    base = folder that relative paths in the spec resolve against. Raises ComposeError with a plain message."""
    try:
        return _render(dict(spec), out, final, source, base)
    except SpriteError as e:
        raise ComposeError(str(e))
    except KeyError as e:
        raise ComposeError(f"the spec is missing the key {e}")


def _render(spec, out, final, source, base):
    def rp(p):
        if p and not os.path.isabs(p) and not os.path.exists(p) and base and os.path.exists(os.path.join(base, p)):
            return os.path.join(base, p).replace("\\", "/")
        return p

    def need(p, what):
        if not p or not os.path.isfile(p):
            raise ComposeError(f"{what} not found: {p}")
        return p

    shots = spec.get("shots")
    src = rp(source or spec.get("source"))
    if shots and src:
        raise ComposeError('give either "source" or "shots", not both')
    if not shots and not src:
        raise ComposeError('the spec needs "source" (a 16:9 video; or --source) or "shots"')
    layout = spec.get("layout") or ("full" if shots or "views" in spec or "view" in spec else "band")
    if layout not in LAYOUTS:
        raise ComposeError(f'unknown layout "{layout}": use "band" or "full"')
    if src:
        need(src, "source video")
    else:
        for s in shots:
            s["src"] = need(rp(s["src"]), "shot source")
            if s.get("layout", layout) not in LAYOUTS:
                raise ComposeError(f'unknown shot layout "{s["layout"]}": use "band" or "full"')
    song = rp(spec.get("song")) if shots else None
    if song:
        need(song, "song")
    if not out.lower().endswith(".mp4"):
        raise ComposeError(f"the output must be an .mp4 file: {out}")

    ff = projcfg.ffmpeg()
    fps = int(spec.get("fps") or (60 if final else 30))
    OW, OH = spec.get("size") or ((W, H) if final else (540, 960))
    enc = _enc_args(final, spec.get("cq"))
    if spec.get("cq") is not None and enc[1] not in ("h264_nvenc", "libx264"):
        print(f'note: "cq" is ignored with the {enc[1]} encoder')
    want_outro = spec.get("outro", not shots)
    outro = projcfg.brand().get("outro_9x16") if want_outro else None
    if want_outro and not (outro and os.path.isfile(outro)):
        print('note: no outro appended (profile/brand.json has no "outro_9x16" clip)')
        outro = None
    L = {"I": -14, "TP": -1.5, "LRA": 11, **(spec.get("loudness") or {})}
    loud = f"loudnorm=I={L['I']:g}:TP={L['TP']:g}:LRA={L['LRA']:g}" if spec.get("loudnorm", not shots) else ""
    gamma = spec.get("gamma", 1.12 if layout == "band" and not shots else 1.0)
    sp = sprites916.Sprites(spec.get("fonts"), spec.get("palette"))
    ov = _Overlays(spec, layout, sp, gamma)
    vfade = spec.get("video_fade", 0.0 if shots else spec.get("fade_out", 0.35))
    main = out[:-4] + "_main.mp4" if outro else out
    small = (OW, OH) != (W, H)

    def finish(frame, t, dur):
        if vfade > 0 and t > dur - vfade:
            frame = (frame * max(0.0, (dur - t) / vfade)).astype(np.uint8)
        return cv2.resize(frame, (OW, OH), interpolation=cv2.INTER_AREA) if small else frame

    raw_in = ["-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}", "-r", str(fps), "-i", "-"]
    if src:
        sw, sh, dur, has_audio = _probe(src)
        make = (_band_layout if layout == "band" else _full_layout)(spec, sw, sh, final, gamma)
        k = sw / 1920.0
        rd = subprocess.Popen([ff, "-v", "error", "-i", src, "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                              stdout=subprocess.PIPE)
        aud = ["-af", f"{loud},aresample=48000"] if loud and not outro else []
        wr = subprocess.Popen([ff, *raw_in, *(["-i", src, "-map", "0:v", "-map", "1:a"] if has_audio else []), *enc, "-pix_fmt", "yuv420p",
                               *(aud + ["-c:a", "aac", "-b:a", "192k", "-shortest"] if has_audio else []),
                               *(["-movflags", "+faststart"] if main == out else []), main], stdin=subprocess.PIPE)
        n = 0
        try:
            while True:
                raw = rd.stdout.read(sw * sh * 3)
                if len(raw) < sw * sh * 3:
                    break
                t = n / fps
                f = np.frombuffer(raw, np.uint8).reshape(sh, sw, 3)
                frame = make(f, t)
                ov.draw(frame, t, f, k)
                _write(wr, finish(frame, t, dur))
                n += 1
        finally:
            rd.stdout.close()
            rd.kill()
            rd.wait()
            try:
                wr.stdin.close()
            except OSError:
                pass
            if wr.wait():
                raise ComposeError("ffmpeg failed while encoding the video")
        if not n:
            raise ComposeError(f"no frames decoded from {src}")
    else:
        n, has_audio = _render_shots(spec, shots, song, layout, ov, sp, ff, fps, enc, raw_in, finish, main, out,
                                     "" if outro else loud)
    if outro:
        pad = max(6, int(math.ceil(_probe(outro)[2])) + 1)
        fc = (f"[1:v]fps={fps},scale={OW}:{OH},fade=t=in:st=0:d=0.3,format=yuv420p,setsar=1[o];[0:v]format=yuv420p,setsar=1[m];"
              f"[m][o]concat=n=2:v=1:a=0[v]")
        if has_audio:
            fc += f";[0:a]{loud + ',' if loud else ''}aresample=48000,apad=pad_dur={pad}[a]"
        _ff([ff, "-v", "error", "-y", "-i", main, "-i", outro, "-filter_complex", fc, "-map", "[v]", *(["-map", "[a]"] if has_audio else []),
             *enc, "-r", str(fps), *(["-c:a", "aac", "-b:a", "192k", "-shortest"] if has_audio else []), "-movflags", "+faststart", out],
            "appending the outro")
        os.remove(main)
    print(out, n, "frames", "+ outro" if outro else "(no outro)")
    return out


def _render_shots(spec, shots, song, layout, ov, sp, ff, fps, enc, raw_in, finish, main, out, loud):
    counts, plan, total = {}, [], 0
    for s in shots:
        key = (s["src"], s["a"], s["b"])
        if key not in counts:
            counts[key] = _count(ff, s["src"], s["a"], s["b"], fps)
        n = counts[key]
        n_out = int(round(n / s.get("rate", 1.0)))
        plan.append((s, n, n_out, total))
        total += n_out
    dur = total / fps
    tmp = out + ".video.mp4"
    cap = int(spec.get("max_buffer_mb", 1024)) * 2 ** 20
    wr = subprocess.Popen([ff, *raw_in, *enc, "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    ovs = _labels(sp, spec.get("overlays"))
    rng = np.random.default_rng(3)
    try:
        for s, n, n_out, f0 in plan:
            texts = _labels(sp, s.get("text"))
            rate = s.get("rate", 1.0)
            Ls = n_out / fps
            band = s["band"] if "band" in s else s.get("layout", layout) == "band"
            lut = _lut(s["gamma"]).astype(np.uint8) if s.get("gamma") else None
            idxs = [min(n - 1, int(i * rate)) for i in range(n_out)]
            for i, img in enumerate(_shot_frames(ff, s, fps, n, idxs, cap, out + ".rev.raw")):
                t = i / fps
                u = _ease(t / max(Ls, 1e-6))
                cx = s.get("cx", 960) + (s.get("cx1", s.get("cx", 960)) - s.get("cx", 960)) * u
                cy = s.get("cy", 540) + (s.get("cy1", s.get("cy", 540)) - s.get("cy", 540)) * u
                z = s.get("z", 1.0) + (s.get("z1", s.get("z", 1.0)) - s.get("z", 1.0)) * u
                for pt in s.get("punch", []):                    # quick zoom punch: up in 0.05 s, back in 0.25 s
                    d = t - pt
                    if 0 <= d < 0.3:
                        z *= 1 + 0.12 * (d / 0.05 if d < 0.05 else 1 - (d - 0.05) / 0.25)
                if s.get("shake") and t < s.get("shake_t", 1e9):
                    cx += rng.uniform(-1, 1) * s["shake"]
                    cy += rng.uniform(-1, 1) * s["shake"]
                fr = _scene_band(img, cx, cy, z, s.get("band_ar", 16 / 9), s.get("band_y", 960)) if band else _window(img, cx, cy, z)
                if lut is not None:
                    fr = cv2.LUT(fr, lut)
                if s.get("flash") is not None and 0 <= t - s["flash"] < 0.18:
                    kf = 1 - (t - s["flash"]) / 0.18
                    fr = (fr * (1 - 0.85 * kf) + 255 * 0.85 * kf).astype(np.uint8)
                if s.get("bw"):
                    fr = cv2.cvtColor(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                for t0, t1, spr, y in texts:
                    if t0 <= t < t1:
                        paste(fr, spr, W / 2 - spr[1].shape[1] / 2, y - spr[1].shape[0] / 2)
                T = (f0 + i) / fps
                for t0, t1, spr, y in ovs:
                    if t0 <= T < t1:
                        paste(fr, spr, W / 2 - spr[1].shape[1] / 2, y - spr[1].shape[0] / 2)
                ov.draw(fr, T, img, img.shape[1] / 1920.0)
                _write(wr, finish(fr, T, dur))
    finally:
        try:
            wr.stdin.close()
        except OSError:
            pass
        if wr.wait():
            raise ComposeError("ffmpeg failed while encoding the video")
    # sound: the song and / or the shots' own sound
    inputs, filt, amix, k = ["-i", tmp], [], [], 1
    if song:
        inputs += ["-ss", f"{spec.get('song_t0', 0):.3f}", "-t", f"{dur:.3f}", "-i", song]
        fo = spec.get("fade_out", 0.6)
        filt.append(f"[1:a]volume={spec.get('song_gain_db', 0)}dB,afade=t=out:st={max(0, dur - fo):.3f}:d={fo},aresample=48000[s]")
        amix.append("[s]")
        k = 2
    if spec.get("game_gain_db") is not None:
        for s, n, n_out, f0 in plan:
            if not s.get("game_audio"):
                continue
            inputs += ["-ss", f"{s['a']:.3f}", "-t", f"{s['b'] - s['a']:.3f}", "-i", s["src"]]
            rate = s.get("rate", 1.0)
            tempo = f",atempo={rate}" if rate != 1.0 else ""
            ms = int(f0 / fps * 1000)
            filt.append(f"[{k}:a]aresample=48000{tempo},volume={spec['game_gain_db'] + s.get('game_db', 0)}dB,adelay={ms}|{ms}[g{k}]")
            amix.append(f"[g{k}]")
            k += 1
    fast = []
    if amix:
        filt.append("".join(amix) + f"amix=inputs={len(amix)}:normalize=0,alimiter=limit=0.95" + (f",{loud},aresample=48000" if loud else "") + "[a]")
        cmd = [ff, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", *fast, main]
    else:
        cmd = [ff, "-v", "error", "-y", "-i", tmp, "-c", "copy", *fast, main]
    _ff(cmd, "adding the sound")
    os.remove(tmp)
    return total, bool(amix)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="compose a 9:16 Short from a spec (see the module docstring for the format)")
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--final", action="store_true", help="1080x1920 @ 60 fps instead of the 540x960 @ 30 fps preview")
    ap.add_argument("--source", help="the pre-rendered 16:9 video (overrides the spec's \"source\")")
    a = ap.parse_args(argv)
    try:
        if not os.path.isfile(a.spec):
            raise ComposeError(f"spec not found: {a.spec}")
        try:
            spec = json.load(open(a.spec, encoding="utf-8"))
        except ValueError as e:
            raise ComposeError(f"{a.spec} is not valid json: {e}")
        render(spec, a.out, a.final, a.source, os.path.dirname(os.path.abspath(a.spec)))
    except ComposeError as e:
        sys.exit(f"compose916: {e}")


if __name__ == "__main__":
    main()
