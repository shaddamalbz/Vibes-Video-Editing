"""Montage renderer: edl.json -> preview_vN.mp4 / final.mp4   (run from the work folder)
FFmpeg does: decode+crop, audio mix + loudnorm, colour grade, sharpen, vignette, fades, NVENC encode.
Python/OpenCV does only what FFmpeg filters can't: speed-ramp time maps with optical-flow slow-mo, beat-locked decaying effects,
and clip transitions (whip pan / zoom / spin / glitch / flash / luma dissolve / ice shatter).
Effects and transitions can be named presets (fx_catalog.py); load_edl() expands them.
Usage: py -3.14 <skill>/scripts/render.py --mode preview --out preview_v1.mp4      (540x960 @30)
       py -3.14 <skill>/scripts/render.py --mode final   --out final.mp4           (1080x1920 @60)
Top-level "canvas": "16:9" renders landscape (960x540 @30 preview, 1920x1080 @60 final) for long YouTube videos: every clip shows the
whole frame, frames are streamed from FFmpeg instead of held in memory (clips may be minutes long), and the view zooms just enough
that shake / roll never show the frame edge.
"""
import argparse, json, math, os, subprocess, sys, time
import numpy as np, cv2
from edl_lib import load_edl, timeline, HERE
from mix_audio import build_mix

SRC_FPS = 60.0
CROP_W, SRC_H = 900, 1080          # decoded window (visible 9:16 slice is 607.5 wide, the rest is margin for shake / whip)
cv2.setNumThreads(max(2, (os.cpu_count() or 4) // 2))


from timemap import TimeMap, smoothstep
from textfx import TextLayer
from overlay import OverlayLayer
from brand import Tint, EndCard
from anime import impact_frame, speed_lines, PanelLayer
import frost
import projcfg

_FILTERS = {}


def has_filter(name):
    """does the ffmpeg on PATH have this filter? (some builds ship without GPL filters such as eq)"""
    if name not in _FILTERS:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-h", f"filter={name}"], capture_output=True, text=True)
        _FILTERS[name] = "Unknown filter" not in (r.stdout + r.stderr) and r.returncode == 0
    return _FILTERS[name]


# ------------------------------------------------------------------ pixel effects ----------
def motion_blur(img, L, angle):
    L = int(max(3, round(L))) | 1
    if abs(angle) < 1:
        return cv2.blur(img, (L, 1))
    if abs(angle - 90) < 1:
        return cv2.blur(img, (1, L))
    h, w = img.shape[:2]
    c = (w / 2, h / 2)
    R = cv2.getRotationMatrix2D(c, -angle, 1.0)
    Ri = cv2.getRotationMatrix2D(c, angle, 1.0)
    t = cv2.warpAffine(img, R, (w, h), borderMode=cv2.BORDER_REFLECT_101)
    t = cv2.blur(t, (L, 1))
    return cv2.warpAffine(t, Ri, (w, h), borderMode=cv2.BORDER_REFLECT_101)


def zoom_blur(img, amount, k=6):
    """radial blur: average of k copies scaled up around the centre (burst look)"""
    h, w = img.shape[:2]
    acc = img.astype(np.float32)
    for i in range(1, k):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, 1 + amount * i / (k - 1))
        acc += cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return (acc / k).astype(np.uint8)


def rgb_split(img, px):
    h, w = img.shape[:2]
    b, g, r = cv2.split(img)
    Mr = np.float32([[1, 0, px], [0, 1, 0.25 * px]])
    Mb = np.float32([[1, 0, -px], [0, 1, -0.25 * px]])
    r = cv2.warpAffine(r, Mr, (w, h), borderMode=cv2.BORDER_REPLICATE)
    b = cv2.warpAffine(b, Mb, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return cv2.merge([b, g, r])


def glitch(img, amount, rng):
    h, w = img.shape[:2]
    a = min(amount, 1.3)
    out = img.copy()
    for _ in range(int(4 + 10 * a)):
        sh = max(2, int(rng.uniform(0.010, 0.07) * h * (0.6 + 0.6 * a)))
        y = int(rng.uniform(0, h - sh))
        dx = int(rng.uniform(-1, 1) * 0.14 * w * a)
        out[y:y + sh] = np.roll(out[y:y + sh], dx, axis=1)
        if rng.random() < 0.35:
            ch = int(rng.integers(0, 3))
            out[y:y + sh, :, ch] = np.roll(out[y:y + sh, :, ch], dx // 2 + int(8 * a), axis=1)
    if rng.random() < 0.5 * a:                      # thin bright scan bar
        y = int(rng.uniform(0, h - 4))
        out[y:y + 3] = cv2.convertScaleAbs(out[y:y + 3], alpha=1.0, beta=70)
    return out


# ------------------------------------------------------------------ transitions ----------
def new_state():
    return dict(z=1.0, tx=0.0, ty=0.0, rot=0.0, mblur=None, gauss=0.0, glitch=0.0, rgb=0.0, white=0.0, border=cv2.BORDER_REFLECT_101,
                zblur=0.0, invert=0.0, desat=0.0, bars=0.0, impact=None, lines=None, zt=None, black=0.0, frost=None)


def key_value(spec, x, default=0.0):
    """a number, or {"keys": [[x_rel_kill_s, value], ...]} smoothstepped between keys (x = output s relative to the kill)"""
    if spec is None:
        return default
    if not isinstance(spec, dict):
        return float(spec)
    ks = sorted(spec["keys"], key=lambda k: k[0])
    if x <= ks[0][0]:
        return float(ks[0][1])
    for (x0, v0), (x1, v1) in zip(ks, ks[1:]):
        if x <= x1:
            return float(v0 + (v1 - v0) * smoothstep(x0, x1, x))
    return float(ks[-1][1])


def cover_zoom(st, W, H):
    """landscape: the zoom at which the frame, shifted by (tx, ty) and rolled by rot, still covers the whole canvas"""
    a, b = W / 2, H / 2
    ax, by = a + abs(st["tx"]), b + abs(st["ty"])
    c, s = abs(math.cos(st["rot"])), abs(math.sin(st["rot"]))
    return max((ax * c + by * s) / a, (ax * s + by * c) / b)


class FrameStream:
    """frames of one clip read from an FFmpeg pipe on demand (landscape clips can be minutes long).
    Access must move forward; a short backlog stays available (slow-mo pairs, impact-frame look-back)."""
    KEEP = 96

    def __init__(self, cmd, n, shape):
        self.n, self.shape, self.size = n, shape, shape[0] * shape[1] * 3
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.size * 2)
        self.next, self.buf = 0, {}

    def __len__(self):
        return self.n

    def __getitem__(self, j):
        j = min(max(int(j), 0), self.n - 1)
        while self.next <= j:
            data = self.p.stdout.read(self.size)
            if len(data) < self.size:                    # source ended early: hold the last frame
                self.n = max(self.next, 1)
                break
            self.buf[self.next] = np.frombuffer(data, np.uint8).reshape(self.shape)
            self.buf.pop(self.next - self.KEEP, None)
            self.next += 1
        j = min(j, self.next - 1)
        while j not in self.buf and j < self.next - 1:  # older than the backlog: nearest kept frame
            j += 1
        return self.buf[j]

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.stdout.close()


def merge_blur(st, L, angle):
    if st["mblur"] is None or L > st["mblur"][0]:
        st["mblur"] = (L, angle)


def apply_transition(st, kind, p, side, d, W, H, res):
    """p: 0..1 strength (1 = at the cut). side: +1 outgoing clip, -1 incoming clip. d: direction sign."""
    if kind == "whip_pan":
        st["border"] = cv2.BORDER_REPLICATE
        st["tx"] += -side * d * W * 1.15 * p ** 2
        merge_blur(st, 0.11 * W * p, 0)
    elif kind == "zoom_in":
        st["z"] *= 1 + 1.6 * p ** 2
        st["gauss"] = max(st["gauss"], 9 * res * p)
        st["white"] = max(st["white"], 0.18 * p)
    elif kind == "zoom_out":
        st["z"] *= 1 - 0.40 * p ** 2
        st["gauss"] = max(st["gauss"], 8 * res * p)
    elif kind == "spin":
        st["rot"] += side * d * (math.pi / 2) * p ** 2
        st["z"] *= 1 + 0.55 * p ** 2
        st["gauss"] = max(st["gauss"], 6 * res * p)
        merge_blur(st, 0.05 * W * p, 0)
    elif kind == "glitch_cut":
        st["glitch"] = max(st["glitch"], 1.1 * p)
        st["rgb"] = max(st["rgb"], 22 * res * p)
    elif kind == "flash_cut":
        st["white"] = max(st["white"], p ** (1.6 if side > 0 else 1.2))
    elif kind == "dip_black":                        # fade out to black, cut, fade in (chapter breaks in long-form)
        st["black"] = max(st["black"], float(smoothstep(0.0, 1.0, p)))


# ------------------------------------------------------------------ renderer ----------
class Renderer:
    def __init__(self, edl, mode, out):
        self.edl, self.mode, self.out = edl, mode, out
        self.land = edl.get("canvas") == "16:9"           # landscape long-form (whole frame, streamed decode)
        if mode == "preview":
            self.W, self.H, self.fps = (960, 540, 30) if self.land else (540, 960, 30)
            self.interp = cv2.INTER_LINEAR
        else:
            self.W, self.H, self.fps = (1920, 1080, 60) if self.land else (1080, 1920, 60)
            self.interp = cv2.INTER_LANCZOS4
        self.res = min(self.W, self.H) / 1080.0
        self.S = self.H / SRC_H                      # source -> output scale
        self.tl, self.total = timeline(edl, self.fps)
        self.video = edl["project"]["video"]
        self.prep_clips()
        rc = edl.get("render", {})
        self.slowmo = rc.get("slowmo_interp", "flow")
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self._flow_key, self._flow, self._grid = None, None, None
        for c in self.tl:                                # per-clip exposure match (gamma LUT, values from exposure.py)
            g = c.get("exposure_gamma", 1.0)
            c["_lut"] = None if abs(g - 1.0) < 0.01 else np.clip(((np.arange(256) / 255.0) ** g) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        self.text = TextLayer(edl.get("texts", []), edl["song"]["beat_period"], self.fps, self.W, self.H)
        self.tint = Tint(edl.get("tint"), edl["song"]["beat_period"], self.fps)
        self.endcard = EndCard(edl.get("endcard"), edl["song"]["beat_period"], self.fps, self.W, self.H)
        self.stings = [EndCard(s, edl["song"]["beat_period"], self.fps, self.W, self.H) for s in edl.get("stings", [])]   # mid-video logo cards
        self.panels = PanelLayer(edl.get("panels"), edl["song"]["beat_period"], self.fps, self.W, self.H, self.video)   # manga pages (anime.py)
        self.overlays = OverlayLayer(edl.get("overlays"), edl["song"]["beat_period"], self.fps, self.W, self.H, HERE)   # keyed characters (overlay.py)

    def prep_clips(self):
        fps = self.fps
        tl = self.tl
        for i, c in enumerate(tl):
            c["idx"] = i
            c["trans_out"] = c.get("transition_out") if i < len(tl) - 1 else None
            c["trans_in"] = tl[i - 1].get("transition_out") if i > 0 else None
            c["tm"] = TimeMap(c["speed"], (c["n_k"] - c["n_s"]) / fps, (c["n_e"] - c["n_k"]) / fps, self.edl["song"]["beat_period"])
            c["t_src_k"] = c["src_kill_frame"] / SRC_FPS
            rng = np.random.default_rng(1234 + i)
            c["_phase"] = rng.uniform(0, 2 * math.pi, 5)
            c["rs"], c["re"] = c["n_s"], c["n_e"]
        # luma dissolve = overlap of the two neighbouring clips around the cut
        self.luma = {}
        for i in range(len(tl) - 1):
            t = tl[i].get("transition_out")
            if t and t["type"] == "luma_fade":
                h = max(1, int(round(t["dur"] * fps / 2)))
                tl[i]["re"] += h
                tl[i + 1]["rs"] -= h
                self.luma[i] = (tl[i + 1]["n_s"], h)
        self.shatter = {}                                # ice shatter: the outgoing frame breaks into shards over the next clip, after the cut
        for i in range(len(tl) - 1):
            t = tl[i].get("transition_out")
            if t and t["type"] == "ice_shatter":
                nd = max(2, int(round(t["dur"] * fps)))
                tl[i]["re"] += nd
                self.shatter[i] = (tl[i + 1]["n_s"], nd, t.get("center"))
        for c in tl:
            lo = c["tm"].offset((c["rs"] - c["n_k"]) / fps)
            hi = c["tm"].offset((c["re"] - c["n_k"]) / fps)
            c["fa"] = int(math.floor((c["t_src_k"] + min(lo, hi)) * SRC_FPS)) - 2
            c["fb"] = int(math.ceil((c["t_src_k"] + max(lo, hi)) * SRC_FPS)) + 3
            c["frames"] = None

    # -------------- source decoding (FFmpeg: seek + crop) --------------
    def full_frame(self, c):
        """clips with "wide" (full 16:9 frame inside the 9:16 canvas) or a "decode_w" are decoded uncropped, scaled to decode_w"""
        return self.land or c.get("wide") is not None or c.get("decode_w") is not None

    def dec_geom(self, c):
        """(decoded width, height, source->decoded scale, decoded x of source x=0)"""
        if self.full_frame(c):
            dw = int(c.get("decode_w", self.W if self.land else (1280 if self.mode == "final" else 960)))
            dh = int(round(dw * 9 / 16 / 2) * 2)
            return dw, dh, dw / 1920.0, 0.0
        x0 = int(min(max(c.get("crop_x", 960) - CROP_W // 2, 0), 1920 - CROP_W))
        return CROP_W, SRC_H, 1.0, -float(x0)

    def load(self, c):
        if c["frames"] is not None:
            return
        n = c["fb"] - c["fa"] + 1
        dw, dh, _, dx = self.dec_geom(c)
        if self.land:                                    # streamed; fps=60 also evens out variable-rate recordings
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(c['fa'] / SRC_FPS - 0.004, 0):.4f}", "-i", c.get("video", self.video),
                   "-frames:v", str(n), "-vf", f"fps={SRC_FPS:g},scale={dw}:{dh}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
            c["frames"] = FrameStream(cmd, n, (dh, dw, 3))
            return
        vf = f"scale={dw}:{dh}:flags=area" if self.full_frame(c) else f"crop={CROP_W}:{SRC_H}:{int(-dx)}:0"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(c['fa'] / SRC_FPS - 0.004, 0):.4f}", "-i", c.get("video", self.video),   # multi-recording: a clip may carry its own source video
               "-frames:v", str(n), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        p = subprocess.run(cmd, capture_output=True)
        buf = np.frombuffer(p.stdout, np.uint8)
        k = len(buf) // (dw * dh * 3)
        c["frames"] = buf[:k * dw * dh * 3].reshape(k, dh, dw, 3)
        if k < n:
            print(f"  warn: {c['id']} decoded {k}/{n} frames")

    def src_frame(self, c, x):
        pos = (c["t_src_k"] + c["tm"].offset(x)) * SRC_FPS - c["fa"]
        fr = c["frames"]
        last = len(fr) - 1
        spd = c["tm"].speed_at(x)
        i0 = int(math.floor(pos))
        a = pos - i0
        if spd < 0.05:                                   # a freeze: hold one real frame (blending two frames ghosts the moving HUD)
            return fr[min(max(int(round(pos)), 0), last)]
        if spd < 0.9 and 0.03 < a < 0.97:               # slow-mo: synthesize the in-between frame instead of duplicating
            j0, j1 = min(max(i0, 0), last), min(max(i0 + 1, 0), last)
            f0, f1 = fr[j0], fr[j1]
            if self.slowmo == "flow" and j1 != j0:
                return self.flow_interp(c, j0, f0, f1, a)
            return cv2.addWeighted(f0, 1 - a, f1, a, 0)
        return fr[min(max(int(round(pos)), 0), last)]

    def flow_interp(self, c, j0, f0, f1, a):
        """bidirectional optical-flow interpolation (DIS, computed at half resolution, cached per source frame pair)"""
        h, w = f0.shape[:2]
        key = (c["idx"], j0)
        if self._flow_key != key:
            g0 = cv2.cvtColor(cv2.resize(f0, (w // 2, h // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            g1 = cv2.cvtColor(cv2.resize(f1, (w // 2, h // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            F01 = cv2.resize(self.dis.calc(g0, g1, None), (w, h)) * 2.0
            F10 = cv2.resize(self.dis.calc(g1, g0, None), (w, h)) * 2.0
            self._flow_key, self._flow = key, (F01, F10)
        F01, F10 = self._flow
        if self._grid is None or self._grid[0].shape != (h, w):
            gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            self._grid = (gx, gy)
        gx, gy = self._grid
        w0 = cv2.remap(f0, gx - a * F01[..., 0], gy - a * F01[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        w1 = cv2.remap(f1, gx - (1 - a) * F10[..., 0], gy - (1 - a) * F10[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        return cv2.addWeighted(w0, 1 - a, w1, a, 0)

    # -------------- per clip frame --------------
    def kill_effects(self, c, x, st):
        W, res = min(self.W, self.H), self.res           # shake etc. scale with the short side (same look in 9:16 and 16:9)
        it = c["intensity"]
        ph = c["_phase"]
        push = c.get("push_in", 0.0)
        if push:
            if x < 0:
                st["z"] *= 1 + push * float(smoothstep(-(c["tm"].pre_len), 0.0, x))
            else:
                st["z"] *= 1 + push * (1 - float(smoothstep(0.0, 0.25, x)))
        x_clip = x
        for fx in c["effects"]:
            t = fx["type"]
            x = x_clip - fx.get("at", 0.0)                   # "at": the effect starts that many output seconds after the anchor (a 2nd hit in one clip)
            if t == "zoom_punch" and 0 <= x < fx["dur"]:
                u = x / fx["dur"]
                st["z"] *= 1 + fx["amp"] * it * (1 - u) ** 3
            elif t == "shake" and 0 <= x < max(0.7, 5 * fx["decay"]):
                d = math.exp(-x / fx["decay"])
                A = fx["amp"] * it * W * d
                f = fx["freq"]
                st["tx"] += A * (math.sin(2 * math.pi * f * x + ph[0]) + 0.5 * math.sin(2 * math.pi * 1.9 * f * x + ph[1])) / 1.5
                st["ty"] += 0.8 * A * (math.sin(2 * math.pi * 1.1 * f * x + ph[2]) + 0.5 * math.sin(2 * math.pi * 2.1 * f * x + ph[3])) / 1.5
                st["rot"] += math.radians(fx["roll_deg"]) * it * d * math.sin(2 * math.pi * 0.8 * f * x + ph[4])
            elif t == "rgb_split" and x >= 0:
                st["rgb"] = max(st["rgb"], fx["px"] * it * res * math.exp(-x / fx["decay"]))
            elif t == "flash" and x >= 0:
                st["white"] = max(st["white"], min(fx.get("cap", 0.65), fx["alpha"] * it * math.exp(-x / fx["decay"])))
            elif t == "zoom_blur" and 0 <= x < fx["dur"]:
                st["zblur"] = max(st["zblur"], fx["amount"] * it * (1 - x / fx["dur"]) ** 2)
            elif t == "invert" and 0 <= x < fx["dur"]:
                st["invert"] = max(st["invert"], fx["alpha"] * (1 - x / fx["dur"]) ** 0.5)
            elif t == "strobe" and 0 <= x < fx["dur"]:
                if int(x * fx["rate"] * 2) % 2 == 0:
                    st["white"] = max(st["white"], fx["alpha"] * (1 - 0.5 * x / fx["dur"]))
            elif t == "desat":
                if fx.get("mode", "after") == "after" and 0 <= x < fx["dur"]:
                    st["desat"] = max(st["desat"], 1 - smoothstep(0.0, fx["dur"], x))
                elif fx.get("mode") == "hold" and 0 <= x < fx["dur"]:          # drains to grey over `ramp` s and stays (death freeze)
                    st["desat"] = max(st["desat"], fx.get("amount", 0.85) * smoothstep(0.0, fx.get("ramp", 0.12), x))
                elif fx.get("mode") == "before" and -fx["pre"] <= x < 0:
                    st["desat"] = max(st["desat"], smoothstep(-fx["pre"], -fx["pre"] + 0.12, x))
            elif t == "letterbox" and 0 <= x < fx["dur"] + 0.15:
                u = min(1.0, x / 0.06) if x < fx["dur"] else 1 - (x - fx["dur"]) / 0.15
                st["bars"] = max(st["bars"], fx["size"] * u)
            elif t == "glitch" and 0 <= x < fx["dur"]:
                st["glitch"] = max(st["glitch"], min(1.3, it * (1 - x / fx["dur"]) ** 1.3))
            elif t == "impact":                             # anime impact frames: flat 3-tone redraw on a few frames around the hit
                for i, (a0, a1) in enumerate(fx["frames"]):
                    if a0 <= x < a1:
                        sty = fx.get("styles", ["red"])
                        st["impact"] = {"style": sty[i % len(sty)], "center": fx.get("center", [0.5, 0.5]), "lines": fx.get("lines", 150), "seed": c["idx"] * 7 + i}
            elif t == "speedlines" and fx["from"] <= x < fx["to"]:
                u = (x - fx["from"]) / max(fx["to"] - fx["from"], 1e-6)
                a = fx.get("alpha", 0.8) * (min(1.0, u / 0.15) if fx.get("fade_in", True) else 1.0) * (min(1.0, (1 - u) / 0.15) if fx.get("fade_out", True) else 1.0)
                if st["lines"] is None or a > st["lines"]["alpha"]:
                    st["lines"] = {"alpha": a, "count": fx.get("count", 110), "color": fx.get("color", [246, 243, 238]), "center": fx.get("center", [0.5, 0.5]),
                                   "inner": fx.get("inner", 0.30), "seed": c["idx"] * 1000 + int(x * 30)}
            elif t == "motion_blur" and x >= 0:
                L = fx["len"] * it * res * math.exp(-x / fx["decay"])
                if L >= 3:
                    merge_blur(st, L, fx.get("angle", 0))
            elif t == "frost" and x >= fx.get("from", 0.0):      # ice look (frost.py): frost creeps in from the edges, optional cracks
                fr_ = {"u": float(smoothstep(fx.get("from", 0.0), fx.get("from", 0.0) + fx.get("ramp", 0.5), x)),
                       "crack": float(smoothstep(fx["crack"], fx["crack"] + fx.get("crack_dur", 0.14), x)) if fx.get("crack") is not None else 0.0,
                       "focus": fx.get("focus", [0.5, 0.5]), "center": fx.get("center", fx.get("focus", [0.5, 0.5])), "grade": fx.get("grade", 1.0)}
                if st["frost"] is None or fr_["u"] >= st["frost"]["u"]:
                    st["frost"] = fr_
            elif t == "zoom_to" and x >= fx["from"]:             # glide the view onto a point of the source (e.g. the boss HP bar) and zoom in
                u = float(smoothstep(fx["from"], fx["to"], x))
                if "back_from" in fx:                            # optional glide back out ("back_from" / "back_to", s rel. anchor)
                    u *= 1.0 - float(smoothstep(fx["back_from"], fx["back_to"], x))
                if st["zt"] is None or u > st["zt"][0]:
                    st["zt"] = (u, fx["x"], fx["y"], fx["z"])

    def clip_frame(self, c, n, with_transition=True):
        fps, W, H = self.fps, self.W, self.H
        x = (n - c["n_k"]) / fps
        st = new_state()
        self.kill_effects(c, x, st)
        if self.land:                                    # no frame edge may show: zoom just enough for the shake / roll
            st["z"] = max(st["z"], cover_zoom(st, W, H))
        if with_transition:
            to, ti = c["trans_out"], c["trans_in"]
            if to and to["type"] not in ("luma_fade", "ice_shatter"):
                nd = max(1, int(round(to["dur"] * fps)))
                if n >= c["n_e"] - nd:
                    p = (n - (c["n_e"] - nd) + 1) / nd
                    apply_transition(st, to["type"], p, +1, to.get("dir", 1), W, H, self.res)
            if ti and ti["type"] not in ("luma_fade", "ice_shatter"):
                nd = max(1, int(round(ti["dur"] * fps)))
                k = n - c["n_s"]
                if 0 <= k < nd:
                    p = 1 - k / nd
                    apply_transition(st, ti["type"], p, -1, ti.get("dir", 1), W, H, self.res)
        src = self.src_frame(c, x)
        z = st["z"] * c.get("base_zoom", 1.0)            # static zoom + vertical view centre (hide game subtitles at the bottom)
        dw, dh, k, dx = self.dec_geom(c)
        cs = np.array([c.get("crop_x", 960) * k + dx, c.get("view_y", SRC_H / 2) * k])
        scale = self.S / k                                # output px per decoded px for the 9:16 crop look
        wide = key_value(c.get("wide"), x, 0.0) if self.full_frame(c) else 0.0
        if wide > 0.0:                                    # wide: shrink toward the whole 16:9 frame (fits the width), centred
            scale = scale ** (1 - wide) * (W / dw) ** wide
            cs = cs * (1 - wide) + np.array([dw / 2, dh / 2]) * wide
        if st["zt"] is not None:
            u, zx, zy, Z = st["zt"]
            cs = cs * (1 - u) + np.array([zx * k + dx, zy * k]) * u
            z *= Z ** u
        if self.land and wide == 0.0:                    # keep the zoomed view inside the frame (e.g. a zoom onto a HUD corner)
            hw, hh = W / (2 * scale * z), H / (2 * scale * z)
            cs = np.array([min(max(cs[0], hw), dw - hw) if hw < dw / 2 else dw / 2, min(max(cs[1], hh), dh - hh) if hh < dh / 2 else dh / 2])
        cd = np.array([W / 2, H / 2])
        c_, s_ = math.cos(st["rot"]), math.sin(st["rot"])
        Rinv = np.array([[c_, s_], [-s_, c_]])           # R(-rot)
        A = Rinv / (scale * z)
        b = cs - A @ (cd + np.array([st["tx"], st["ty"]]))
        M = np.hstack([A, b[:, None]]).astype(np.float64)
        if wide > 0.002:                                  # the frame no longer fills the canvas: blurred, darkened copy behind it
            out = self.wide_bg(src)
            fg = cv2.warpAffine(src, M, (W, H), flags=self.interp | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT)
            m = cv2.warpAffine(np.full(src.shape[:2], 255, np.uint8), M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT)
            cv2.copyTo(fg, (m > 127).astype(np.uint8), out)
        elif src.shape[1] == W and src.shape[0] == H and np.abs(M - np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])).max() < 1e-9:
            out = src.copy()                              # identity view (most 16:9 frames): same pixels as the warp, ~20x cheaper
        else:
            out = cv2.warpAffine(src, M, (W, H), flags=self.interp | cv2.WARP_INVERSE_MAP, borderMode=st["border"])
        if c.get("_lut") is not None:
            out = cv2.LUT(out, c["_lut"])
        if st["gauss"] > 0.5:
            out = cv2.GaussianBlur(out, (0, 0), st["gauss"])
        if st["mblur"]:
            out = motion_blur(out, *st["mblur"])
        if st["zblur"] > 0.004:
            out = zoom_blur(out, st["zblur"])
        if st["desat"] > 0.01:
            g = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            out = cv2.addWeighted(out, 1 - min(st["desat"], 1.0), g, min(st["desat"], 1.0), 0)
        if st["rgb"] > 0.5:
            out = rgb_split(out, st["rgb"])
        if st["glitch"] > 0.03:
            out = glitch(out, st["glitch"], np.random.default_rng(1000003 * c["idx"] + n))
        if st["invert"] > 0.01:
            a = min(st["invert"], 1.0)
            out = cv2.addWeighted(out, 1 - a, 255 - out, a, 0)
        if st["frost"]:
            out = frost.apply(out, st["frost"], self.res, seed=7 + c["idx"])
        if st["white"] > 0.01:
            w = min(st["white"], 1.0)
            out = cv2.convertScaleAbs(out, alpha=1 - w, beta=255 * w)
        if st["black"] > 0.005:
            out = cv2.convertScaleAbs(out, alpha=1 - min(st["black"], 1.0), beta=0)
        if st["impact"]:
            im = st["impact"]
            base = out
            if cv2.resize(out, (18, 32), interpolation=cv2.INTER_AREA).mean() > 150:     # blown-out flash: redraw the shot from just before it
                base = cv2.warpAffine(self.src_frame(c, x - im.get("back", 0.15)), M, (W, H), flags=self.interp | cv2.WARP_INVERSE_MAP, borderMode=st["border"])
                if c.get("_lut") is not None:
                    base = cv2.LUT(base, c["_lut"])
            out = impact_frame(base, im["style"], im["center"], int(im["lines"]), im["seed"])
        if st["lines"]:
            L_ = st["lines"]
            out = speed_lines(out, L_["center"], int(L_["count"]), tuple(L_["color"]), L_["inner"], L_["seed"], L_["alpha"])
        if st["bars"] > 0.002:
            hb = int(round(st["bars"] * H))
            out[:hb] = 0
            out[H - hb:] = 0
        return out

    def wide_bg(self, src):
        """background for the wide layout: the same frame, cover-scaled, heavily blurred and darkened"""
        W, H = self.W, self.H
        cfg = self.edl.get("wide_bg", {})
        sm = cv2.resize(src, (64, 36), interpolation=cv2.INTER_AREA)
        cw = 36 * W / H                                   # cover crop of the 16:9 thumbnail at the canvas aspect
        x0 = int(round((64 - cw) / 2))
        sm = cv2.GaussianBlur(sm[:, x0:x0 + max(int(round(cw)), 2)], (0, 0), cfg.get("blur", 1.6))
        bg = cv2.resize(sm, (W, H), interpolation=cv2.INTER_CUBIC)
        return cv2.convertScaleAbs(bg, alpha=cfg.get("dim", 0.42), beta=0)

    def luma_mix(self, A, B, p):
        lb = cv2.cvtColor(B, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        m = np.clip((p * 1.5 - (1 - lb) * 0.5) / 0.5, 0, 1)[..., None]
        return (A.astype(np.float32) * (1 - m) + B.astype(np.float32) * m).astype(np.uint8)

    def frame(self, n):
        act = [c for c in self.tl if c["rs"] <= n < c["re"]]
        for c in act:
            self.load(c)
        if len(act) == 1:
            fr = self.clip_frame(act[0], n)
        elif act[0]["idx"] in self.shatter:
            A, B = act[0], act[1]
            nb, nd, cen = self.shatter[A["idx"]]
            fa = self.clip_frame(A, n, False)
            if cen is None:                              # break from the crack centre of the clip's frost effect
                cen = next((fx.get("center", fx.get("focus")) for fx in A["effects"] if fx["type"] == "frost"), None) or [0.5, 0.5]
            fr = frost.shatter(fa, self.clip_frame(B, n, True), (n - nb + 0.5) / nd, self.res, cen, seed=7 + A["idx"])
        else:
            A, B = act[0], act[1]
            nb, h = self.luma[A["idx"]]
            p = (n - (nb - h) + 0.5) / (2 * h)
            fr = self.luma_mix(self.clip_frame(A, n, False), self.clip_frame(B, n, False), p)
        fr = self.tint.apply(fr, n)
        fb = self.edl.get("film_bars", 0.0)              # thin black cinema bars over the whole edit (top-level "film_bars": fraction of the height)
        if fb > 0:
            hb = int(round(fb * self.H))
            fr[:hb] = 0
            fr[self.H - hb:] = 0
        fr = self.overlays.draw(fr, n)
        fr = self.panels.draw(fr, n)
        fr = self.text.draw(fr, n)
        for s in self.stings:
            fr = s.draw(fr, n)
        return self.endcard.draw(fr, n)

    # -------------- encode --------------
    def vf_chain(self):
        g = self.edl["grade"]
        L = self.total / self.fps
        f = self.edl["fades"]
        ramp = self.edl.get("grade_ramp")
        if ramp:
            P = self.edl["song"]["beat_period"]
            t1 = ramp["at_beat"] * P
            t0 = t1 - ramp["ramp_beats"] * P
            rr = f"clip((t-{t0:.4f})/{t1 - t0:.4f},0,1)"
            fr_ = ramp["from"]
            def mix(k, hi):
                lo = fr_.get(k, hi)
                return f"'{lo}+({hi}-{lo})*{rr}'"
            eq = (f"eq=contrast={mix('contrast', g['contrast'])}:brightness={mix('brightness', g.get('brightness', 0))}:"
                  f"saturation={mix('saturation', g['saturation'])}:gamma={mix('gamma', g['gamma'])}:eval=frame,")
        elif has_filter("eq"):
            eq = f"eq=contrast={g['contrast']}:brightness={g.get('brightness', 0)}:saturation={g['saturation']}:gamma={g['gamma']},"
        else:                                            # ffmpeg build without the GPL eq filter (a non-GPL build): same grade via lutyuv
            c, b, s, gm = g["contrast"], g.get("brightness", 0), g["saturation"], g["gamma"]
            eq = (f"lutyuv=y='clip(255*pow(clip(((val-128)*{c}+128+{b}*255)/255,0,1),1/{gm}),0,255)'"
                  f":u='clip((val-128)*{s}+128,0,255)':v='clip((val-128)*{s}+128,0,255)',")
        return (f"scale=out_color_matrix=bt709:out_range=tv:flags=bicubic,format=yuv420p,"
                f"{eq}"
                f"unsharp=5:5:{g.get('sharpen_final', g['sharpen']) if self.mode == 'final' else g['sharpen']}:5:5:0,vignette={g['vignette_angle']}"
                + "".join((                       # ffmpeg fade with d=0 falls back to 25 frames, so skip a zero fade
                    f",fade=t=in:st=0:d={f['video_in']}" if f["video_in"] > 0 else "",
                    f",fade=t=out:st={L - f['video_out']:.3f}:d={f['video_out']}" if f["video_out"] > 0 else "")))

    def run(self, debug=None, rng=None):
        t0 = time.time()
        wav = os.path.join(HERE, "scan", f"mix_{self.fps}.wav")
        _, lufs, tp = build_mix(self.edl, self.fps, wav)
        if debug:
            os.makedirs(os.path.join(HERE, "probe", "dbg"), exist_ok=True)
            for n in debug:
                cv2.imwrite(os.path.join(HERE, "probe", "dbg", f"{self.mode}_{n:05d}.png"), self.frame(n))
            return
        if self.mode == "preview":
            venc = ["-c:v", "h264_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "26", "-b:v", "5M", "-maxrate", "8M", "-bufsize", "12M", "-g", "60"]
        elif self.land:
            # 16:9 long finals: 16 Mbps since 10 Nov 2026 (user compared 1 min at 49 vs 16 Mbps and picked 16; 72 min = ~8.5 GB, was 26 GB).
            # edl "final_bitrate": "40M" restores a higher target for one video.
            br = int(str(self.edl.get("final_bitrate", "16M")).rstrip("Mm"))
            venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-profile:v", "high", "-rc", "vbr", "-b:v", f"{br}M",
                    "-maxrate", f"{br * 3 // 2}M", "-bufsize", f"{br * 2}M", "-spatial_aq", "1", "-g", "120", "-bf", "2"]
        else:
            venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-profile:v", "high", "-rc", "vbr", "-cq", "17", "-b:v", "40M",
                    "-maxrate", "60M", "-bufsize", "100M", "-spatial_aq", "1", "-g", "120", "-bf", "2"]
        enc_name = projcfg.encoder()
        if enc_name != "h264_nvenc":              # no NVIDIA encoder: same targets with another H.264 encoder (not tuned per vendor)
            br = int(str(self.edl.get("final_bitrate", "16M")).rstrip("Mm"))
            if enc_name == "libx264":
                venc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-maxrate", "8M", "-bufsize", "12M", "-g", "60"] if self.mode == "preview"
                        else ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-b:v", f"{br}M", "-maxrate", f"{br * 3 // 2}M", "-bufsize", f"{br * 2}M", "-g", "120", "-bf", "2"] if self.land
                        else ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-crf", "17", "-maxrate", "60M", "-bufsize", "100M", "-g", "120", "-bf", "2"])
            else:
                rate = "5M" if self.mode == "preview" else f"{br}M" if self.land else "40M"
                venc = ["-c:v", enc_name, "-b:v", rate, "-g", "60" if self.mode == "preview" else "120"]
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{self.W}x{self.H}", "-r", str(self.fps),
               "-i", "-", "-i", wav, "-vf", self.vf_chain(), *venc, "-r", str(self.fps), "-pix_fmt", "yuv420p",
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
               "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", self.out]
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        N = self.total
        for n in range(N):
            enc.stdin.write(self.frame(n).tobytes())
            if n % 60 == 0:
                print(f"  frame {n}/{N}  {time.time()-t0:5.0f}s", flush=True)
            for c in self.tl:                              # free decoded frames of finished clips
                if c["frames"] is not None and n >= c["re"]:
                    if isinstance(c["frames"], FrameStream):
                        c["frames"].close()
                    c["frames"] = None
        enc.stdin.close()
        enc.wait()
        print(f"rendered {N} frames -> {self.out}  ({time.time()-t0:.0f}s)")
        rep = {"mode": self.mode, "size": [self.W, self.H], "fps": self.fps, "frames": N, "audio_lufs": lufs, "audio_true_peak": tp,
               "clips": [{"id": c["id"], "calm": bool(c.get("calm")), "kill_id": c.get("kill_id"), "kill_out_frame": c["n_k"], "kill_out_time": c["n_k"] / self.fps,
                          "beat_time": c["t_k"], "kill_vs_beat_frames": c["kill_err_frames"], "start_frame": c["n_s"], "end_frame": c["n_e"],
                          "transition_out": (c.get("transition_out") or {}).get("type")} for c in self.tl]}
        json.dump(rep, open(os.path.join(HERE, f"render_report_{self.mode}.json"), "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preview", "final"], default="preview")
    ap.add_argument("--out", default=None)
    ap.add_argument("--edl", default=None)
    ap.add_argument("--debug-frames", default=None, help="comma list of output frame numbers to dump as PNG (no encode)")
    a = ap.parse_args()
    edl = load_edl(a.edl)
    out = a.out or ("preview_v1.mp4" if a.mode == "preview" else "final.mp4")
    r = Renderer(edl, a.mode, os.path.join(HERE, out))
    r.run(debug=[int(x) for x in a.debug_frames.split(",")] if a.debug_frames else None)
