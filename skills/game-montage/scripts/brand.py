"""Channel brand layers for the renderer: an optional warm->cool tint ramp and the closing end card (logo + wordmark).
Assets are the channel's own raster masters, named in the profile's brand.json: never stretched or recoloured. The wordmark can be cut
from a banner image and keyed from its dark background. Entrance uses a pixel-dissolve to stay on the pixel-art theme.
"""
import math, os
import numpy as np, cv2
from textfx import BGR, blit
from edl_lib import HERE                     # relative logo / wordmark paths resolve against the work folder

import projcfg

# Channel brand = the private profile's brand.json (never copied into the skill, never edited):
#   "logo": square logo image, "wordmark": RGBA png or {"from": banner png, "box": [x0, y0, x1, y1], "key": [lo, range]}
#   (keyed off a dark background, alpha from brightness), "endcard_bg_bgr": [b, g, r].
# An edit's own "endcard": {"logo", "wordmark", "bg_bgr"} wins over the profile.
_B = projcfg.brand()
BRAND_LOGO = _B.get("logo") or None
BRAND_WORDMARK = _B.get("wordmark") or None
BRAND_BG = tuple(_B.get("endcard_bg_bgr", (0, 0, 0)))


def load_wordmark(spec):
    """spec = path to an RGBA png, or {"from": banner png, "box": [x0, y0, x1, y1], "key": [lo, range]} -> BGRA"""
    if isinstance(spec, str):
        return cv2.imread(os.path.join(HERE, spec), cv2.IMREAD_UNCHANGED)
    x0, y0, x1, y1 = spec["box"]
    crop = cv2.imread(os.path.join(HERE, spec["from"]))[y0:y1, x0:x1]
    lo, rng = spec.get("key", [80, 70])
    alpha = np.clip((crop.max(2).astype(np.float32) - lo) / rng, 0, 1)
    return np.dstack([crop, (alpha * 255).astype(np.uint8)])


def ss(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Tint:
    """work side = warm sunset, gamer side = cool navy/cyan. Per-channel gains (RGB in the EDL) ramped around the drop."""
    def __init__(self, cfg, P, fps):
        self.cfg = cfg
        if cfg:
            self.t1 = cfg["at_beat"] * P
            self.t0 = self.t1 - cfg["ramp_beats"] * P
            self.warm, self.cool = np.array(cfg["warm"][::-1], np.float32), np.array(cfg["cool"][::-1], np.float32)   # -> BGR
        self.fps = fps

    def apply(self, frame, n):
        if not self.cfg:
            return frame
        r = ss((n / self.fps - self.t0) / (self.t1 - self.t0))
        g = self.warm * (1 - r) + self.cool * r
        return cv2.multiply(frame, (float(g[0]), float(g[1]), float(g[2]), 1.0))


def pixelate(img, block):
    if block <= 1:
        return img
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(w // block, 1), max(h // block, 1)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


class EndCard:
    def __init__(self, cfg, P, fps, W, H):
        self.cfg, self.fps, self.W, self.H = cfg, fps, W, H
        if not cfg:
            return
        self.res = W / 1080.0
        self.n0 = int(round(cfg["start_beat"] * P * fps))
        self.fade = max(int(round(cfg["fade_beats"] * P * fps)), 1)
        # optional end (mid-video logo sting): the whole card fades back out to the footage over fade_out_beats
        self.n1 = int(round(cfg["end_beat"] * P * fps)) if "end_beat" in cfg else None
        self.fade_out = max(int(round(cfg.get("fade_out_beats", cfg["fade_beats"]) * P * fps)), 1)
        self.bg = np.array(cfg.get("bg_bgr", BRAND_BG), np.float32)              # card background
        lw = int(cfg["logo_width"] * W)
        if not cfg.get("logo", BRAND_LOGO):
            raise SystemExit('endcard needs a logo: set "logo" in the channel profile brand.json, or "endcard": {"logo": ...} in the edit')
        logo = cv2.imread(os.path.join(HERE, cfg.get("logo", BRAND_LOGO)))
        self.logo = cv2.resize(logo, (lw, lw), interpolation=cv2.INTER_AREA if lw < logo.shape[1] else cv2.INTER_CUBIC)
        self.wm = None                                                          # the wordmark is optional
        if cfg.get("wordmark", BRAND_WORDMARK):
            wm = load_wordmark(cfg.get("wordmark", BRAND_WORDMARK))
            ww = int(cfg["wordmark_width"] * W)
            wh = int(round(ww * wm.shape[0] / wm.shape[1]))
            self.wm = cv2.resize(wm, (ww, wh), interpolation=cv2.INTER_AREA if ww < wm.shape[1] else cv2.INTER_CUBIC)
        self.pix = cfg.get("pixel_in", 0.55)

    def _enter(self, t):
        """t: seconds since this element started -> (alpha, pixel block, scale)"""
        if t <= 0:
            return 0.0, 1, 1.0
        u = min(t / self.pix, 1.0)
        block = max(1, int(round(26 * self.res * (1 - u) ** 2)))
        scale = 0.92 + 0.08 * (1 - (1 - u) ** 3) + 0.03 * math.sin(math.pi * u) * (1 - u)
        return min(1.0, t / 0.22), block, scale

    def draw(self, frame, n):
        if not self.cfg or n < self.n0 or (self.n1 is not None and n >= self.n1):
            return frame
        if self.n1 is not None and n >= self.n1 - self.fade_out:
            under = frame.copy()
            out = ss((self.n1 - n) / self.fade_out)
            self._draw(frame, n)
            frame[:] = cv2.addWeighted(under, 1 - out, frame, out, 0)
            return frame
        return self._draw(frame, n)

    def _draw(self, frame, n):
        W, H = self.W, self.H
        a = ss((n - self.n0) / self.fade)
        frame[:] = cv2.addWeighted(frame, 1 - a, np.full_like(frame, self.bg.astype(np.uint8)), a, 0)
        t_card = (n - self.n0 - 0.55 * self.fade) / self.fps               # logo starts once the card is mostly opaque
        c = self.cfg
        al, block, sc = self._enter(t_card)
        if al > 0.01:
            img = pixelate(self.logo, block)
            if abs(sc - 1) > 1e-3:
                img = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST if block > 1 else cv2.INTER_LINEAR)
            h, w = img.shape[:2]
            x0, y0 = int(W / 2 - w / 2), int(c["logo_y"] * H - h / 2)
            self._lighten(frame, img, x0, y0, al)
        al2, block2, sc2 = self._enter(t_card - 0.30)                      # wordmark follows the logo
        if al2 > 0.01 and self.wm is not None:
            bgr = pixelate(self.wm[..., :3], block2)
            amask = pixelate(self.wm[..., 3], block2)
            h, w = amask.shape
            x0, y0 = int(W / 2 - w / 2), int(c["wordmark_y"] * H - h / 2 + (1 - al2) * 14 * self.res)
            blit(frame, bgr, amask, x0, y0, al2)
        return frame

    @staticmethod
    def _lighten(frame, img, x0, y0, opacity):
        """lighten blend: the logo's dark square never shows as a rectangle, only the mark does"""
        h, w = img.shape[:2]
        H, W = frame.shape[:2]
        fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
        if fx1 <= fx0 or fy1 <= fy0:
            return
        roi = frame[fy0:fy1, fx0:fx1]
        src = img[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
        mx = np.maximum(roi, src)
        frame[fy0:fy1, fx0:fx1] = cv2.addWeighted(roi, 1 - opacity, mx, opacity, 0)
