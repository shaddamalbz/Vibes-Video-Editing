"""Overlay layer: keyed character clips (RGBA PNG frames from chroma_key.py, e.g. an anime dancer) drawn over the footage,
under the texts and the end card. Top-level edl key "overlays", a list of:
  {"dir": "dancers/rem",          folder with 000000.png ... + meta.json (relative to the work folder or absolute)
   "start": 36, "end": 76,        window beats (on screen from start to end)
   "x": 0.24,                     where the BODY centre sits (fraction of the canvas width; meta body_cx)
   "bottom": 0.97,                where the bottom of the subject box sits (fraction of the canvas height; 1.0 = canvas bottom)
   "height": 0.42,                height of the subject box (fraction of the canvas height)
   "rate": 1.04,                  source seconds per output second (match the dance to the song tempo)
   "src_start": 0.0,              source second shown at "start" (pick a dance accent for the first beat)
   "loop": true, "flip": false,   mirror horizontally with flip
   "fade": 0.12, "pop": 0.18,     seconds of alpha fade at both ends / scale-in with a small overshoot at the start
   "opacity": 1.0}
Frames are read lazily and cached at the drawn size."""
import json, math, os
from collections import OrderedDict
import numpy as np, cv2


class OverlayLayer:
    def __init__(self, items, beat_period, fps, W, H, base):
        self.P, self.fps, self.W, self.H = beat_period, fps, W, H
        self.items = []
        for it in items or []:
            d = it["dir"] if os.path.isabs(it["dir"]) else os.path.join(base, it["dir"])
            meta = json.load(open(os.path.join(d, "meta.json")))
            self.items.append({**it, "_d": d, "_m": meta, "_cache": OrderedDict()})

    def _frame(self, it, idx, h):
        key = (idx, h, it.get("flip", False))
        c = it["_cache"]
        if key in c:
            c.move_to_end(key)
            return c[key]
        a = cv2.imread(os.path.join(it["_d"], f"{idx:06d}.png"), cv2.IMREAD_UNCHANGED)
        w = max(1, int(round(a.shape[1] * h / a.shape[0])))
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA if h < a.shape[0] else cv2.INTER_CUBIC)
        if it.get("flip"):
            a = a[:, ::-1]
        a = a.astype(np.float32)
        c[key] = a
        if len(c) > 400:
            c.popitem(last=False)
        return a

    def draw(self, fr, n):
        t = n / self.fps
        for it in self.items:
            t0, t1 = it["start"] * self.P, it["end"] * self.P
            if not (t0 <= t < t1):
                continue
            m = it["_m"]
            dt = t - t0
            src = it.get("src_start", 0.0) + dt * it.get("rate", 1.0)
            idx = int(src * m["fps"])
            idx = idx % m["frames"] if it.get("loop", True) else min(idx, m["frames"] - 1)
            scale = 1.0
            pop = it.get("pop", 0.0)
            if pop > 0 and dt < pop:                         # scale in with a small overshoot
                u = dt / pop
                scale = 0.55 + 0.45 * (1 - (1 - u) ** 3) + 0.08 * math.sin(math.pi * u)
            h = max(2, int(round(it.get("height", 0.4) * self.H * scale)))
            a = self._frame(it, idx, h)
            fade = it.get("fade", 0.0)
            op = it.get("opacity", 1.0)
            if fade > 0:
                op *= min(1.0, dt / fade, (t1 - t) / fade)
            cx = it.get("body_cx", m.get("body_cx", 0.5))
            if it.get("flip"):
                cx = 1 - cx
            x0 = int(round(it.get("x", 0.5) * self.W - cx * a.shape[1]))
            y1 = int(round(it.get("bottom", 1.0) * self.H))
            y0 = y1 - a.shape[0]
            ax0, ay0 = max(0, -x0), max(0, -y0)
            fx0, fy0 = max(0, x0), max(0, y0)
            fx1, fy1 = min(self.W, x0 + a.shape[1]), min(self.H, y1)
            if fx1 <= fx0 or fy1 <= fy0:
                continue
            sub = a[ay0:ay0 + (fy1 - fy0), ax0:ax0 + (fx1 - fx0)]
            al = sub[..., 3:4] / 255.0 * op
            roi = fr[fy0:fy1, fx0:fx1].astype(np.float32)
            fr[fy0:fy1, fx0:fx1] = (sub[..., :3] * al + roi * (1 - al)).astype(np.uint8)
        return fr
