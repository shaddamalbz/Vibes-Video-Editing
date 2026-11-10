"""Anime / manga looks for the montage renderer (first used on the FF XVI Pandemonium short, Oct 2026).

impact_frame(img, style, ...)   2-4 frame "impact frame": the shot redrawn in 3 flat tones (white / red / black), inverted like an anime
                                hit frame, with ink edges and radial speed lines. Styles: "red" (white paper, red mid tones, black
                                highlights), "dark" (black paper, red mid tones, white highlights), "bw" (white paper, black ink only).
speed_lines(img, ...)           radial anime speed lines (tapered wedges from the screen edge towards a centre), redrawn every 2 frames.
PanelLayer                      manga page: 2-4 panels (polygons on a paper background) pop in one by one on beats, each playing its own
                                piece of a recording, then the page "shatters" (panels fly apart) and reveals the timeline underneath.

EDL usage (all times are output seconds x beat_period, like every other beat value):
  clip effects:  {"preset": "impact_2"}  /  {"preset": "speedlines_in"}          (presets in fx_catalog.py)
  top level:     "panels": [{"start": 12.0, "end": 16.7, "bg": [245, 242, 236], "exit": {"type": "shatter", "dur": 0.22},
                             "items": [{"in": 12.0, "poly": [[0.03,0.02],[0.97,0.02],[0.97,0.30],[0.03,0.36]], "src": 205.3,
                                        "speed": 0.6, "crop": {"cx": 1000, "cy": 520, "w": 1100}, "style": "color"}, ...]}]
  poly = panel corners in screen fractions; crop = source window centre + width in 1920x1080 pixels (height follows the panel shape);
  style "color" | "impact" (whole panel drawn as an impact frame) ; optional "video" (another recording), "impact_at" (panel seconds).
"""
import math, subprocess
import numpy as np, cv2

INK = (14, 10, 12)              # BGR near-black ink
PAPER = (246, 243, 238)         # warm white paper
CRIMSON = (48, 30, 214)         # BGR deep red (Pandemonium / brand-coral family)


def _tones(img):
    """work at 1/3 size with a median blur, so the flat shapes come out big and clean (like an inked frame), not as noise"""
    H, W = img.shape[:2]
    g = cv2.cvtColor(cv2.resize(img, (W // 3, H // 3), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(2.5, (6, 6)).apply(g)
    g = cv2.medianBlur(g, 5)
    g = cv2.bilateralFilter(g, 7, 50, 7)
    e = cv2.Canny(g, 70, 160)
    return g, e


def _up(mask, W, H, k=3):
    """upscale a small binary mask with smooth edges, drop specks"""
    m = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
    return m > 127


def speed_lines(img, center=(0.5, 0.5), count=150, color=INK, inner=0.34, seed=0, alpha=1.0):
    """tapered radial wedges from outside the frame towards (inner x diagonal) of the centre"""
    H, W = img.shape[:2]
    rng = np.random.default_rng(seed)
    cx, cy = center[0] * W, center[1] * H
    R = math.hypot(W, H)
    layer = np.zeros((H, W), np.uint8)
    for _ in range(int(count)):
        a = rng.uniform(0, 2 * math.pi)
        r0 = R * rng.uniform(inner, inner + 0.22)
        half = rng.uniform(0.002, 0.009)                    # wedge half-angle at the outer edge
        p0 = (cx + math.cos(a) * r0, cy + math.sin(a) * r0)
        p1 = (cx + math.cos(a - half) * R, cy + math.sin(a - half) * R)
        p2 = (cx + math.cos(a + half) * R, cy + math.sin(a + half) * R)
        cv2.fillPoly(layer, [np.array([p0, p1, p2], np.int32)], 255, cv2.LINE_AA)
    m = (layer.astype(np.float32) / 255.0 * alpha)[..., None]
    return (img.astype(np.float32) * (1 - m) + np.array(color, np.float32) * m).astype(np.uint8)


def impact_frame(img, style="red", center=(0.5, 0.5), lines=150, seed=0, accent=CRIMSON):
    H, W = img.shape[:2]
    g, e = _tones(img)
    hi, mid = np.percentile(g, 88), np.percentile(g, 60)
    if hi - mid < 10:                                       # flat frame: spread the tones so the redraw never comes out blank
        mid, hi = np.percentile(g, 45), np.percentile(g, 75)
    m_mid, m_hi = _up(g > mid, W, H), _up(g > hi, W, H)
    m_edge = cv2.resize(cv2.dilate(e, np.ones((2, 2), np.uint8)), (W, H), interpolation=cv2.INTER_LINEAR) > 90
    if style == "dark":
        out = np.zeros((H, W, 3), np.uint8); out[:] = INK
        out[m_mid] = accent
        out[m_hi] = PAPER
        out[m_edge] = PAPER
        line_col = PAPER
    else:
        out = np.zeros((H, W, 3), np.uint8); out[:] = PAPER
        if style == "red":
            out[m_mid] = accent
        out[m_hi] = INK
        out[m_edge] = INK
        line_col = INK
    if lines:
        out = speed_lines(out, center, lines, line_col, 0.36, seed)
    return out


# ---------------------------------------------------------------------------------------------- manga panels
def _ease_out(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


class PanelLayer:
    def __init__(self, groups, P, fps, W, H, video, src_fps=60.0):
        self.groups, self.P, self.fps, self.W, self.H, self.video, self.src_fps = groups or [], P, fps, W, H, video, src_fps
        self.res = W / 1080.0
        for gi, g in enumerate(self.groups):
            g["_n0"] = int(round(g["start"] * P * fps))
            g["_n1"] = int(round(g["end"] * P * fps))
            ex = g.get("exit", {"type": "shatter", "dur": 0.22})
            g["_nx"] = max(1, int(round(ex.get("dur", 0.22) * fps)))
            g["_exit"] = ex.get("type", "shatter")
            for k, it in enumerate(g["items"]):
                it["_n_in"] = int(round(it["in"] * P * fps))
                poly = np.array(it["poly"], np.float64) * [W, H]
                it["_poly"] = poly
                x0, y0 = poly.min(0); x1, y1 = poly.max(0)
                it["_box"] = (int(math.floor(x0)), int(math.floor(y0)), int(math.ceil(x1)), int(math.ceil(y1)))
                it["_frames"] = None
                it["_seed"] = 31 * gi + k

    def _load(self, it, g):
        if it["_frames"] is not None:
            return
        bx0, by0, bx1, by1 = it["_box"]
        bw, bh = bx1 - bx0, by1 - by0
        cr = it.get("crop", {})
        cw = int(cr.get("w", 1920 * 0.6))
        ch = int(round(cw * bh / bw))
        if ch > 1080:
            ch = 1080; cw = int(round(ch * bw / bh))
        cx, cy = cr.get("cx", 960), cr.get("cy", 540)
        x0 = int(min(max(cx - cw / 2, 0), 1920 - cw)); y0 = int(min(max(cy - ch / 2, 0), 1080 - ch))
        dur = (g["end"] - it["in"]) * self.P + g["_nx"] / self.fps + 0.1
        span = dur * it.get("speed", 1.0) + 0.1
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{it['src']:.4f}", "-i", it.get("video", self.video), "-t", f"{span:.3f}",
               "-vf", f"crop={cw}:{ch}:{x0}:{y0},scale={bw}:{bh}:flags=bicubic", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        buf = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.uint8)
        k = len(buf) // (bw * bh * 3)
        it["_frames"] = buf[:k * bw * bh * 3].reshape(k, bh, bw, 3)

    def _content(self, it, g, t_rel):
        fr = it["_frames"]
        pos = t_rel * it.get("speed", 1.0) * self.src_fps
        i0 = int(math.floor(pos)); a = pos - i0
        last = len(fr) - 1
        f0, f1 = fr[min(max(i0, 0), last)], fr[min(max(i0 + 1, 0), last)]
        img = f0 if a < 0.03 or i0 + 1 > last else cv2.addWeighted(f0, 1 - a, f1, a, 0)
        imp = it.get("impact_at")
        if it.get("style") == "impact" or (imp is not None and imp <= t_rel < imp + 0.1):
            img = impact_frame(img, it.get("impact_style", "red"), (0.5, 0.5), int(70 * self.res) + 40, it["_seed"] + int(t_rel * 15))
        return img

    def draw(self, frame, n):
        W, H, fps = self.W, self.H, self.fps
        for g in self.groups:
            if not (g["_n0"] <= n < g["_n1"] + g["_nx"]):
                if n >= g["_n1"] + g["_nx"]:
                    for it in g["items"]:
                        it["_frames"] = None
                continue
            u_exit = max(0.0, (n - g["_n1"]) / g["_nx"]) if n >= g["_n1"] else 0.0
            bg = np.array(g.get("bg", PAPER), np.float32)
            page = np.empty_like(frame); page[:] = bg.astype(np.uint8)
            page_a = 1.0 - _ease_out(u_exit)                 # the paper fades while the panels fly apart
            out = frame.astype(np.float32) * (1 - page_a) + page.astype(np.float32) * page_a
            border = max(2, int(round(g.get("border", 10) * self.res)))
            for it in g["items"]:
                if n < it["_n_in"]:
                    continue
                self._load(it, g)
                t_rel = (n - it["_n_in"]) / fps
                img = self._content(it, g, t_rel)
                bx0, by0, bx1, by1 = it["_box"]
                poly = it["_poly"].copy()
                # entrance: slam in (scale 1.10 -> 1 around the panel centre) + white flash on the panel
                ue = _ease_out(t_rel / 0.14)
                sc = 1.10 - 0.10 * ue
                flash = max(0.0, 1 - t_rel / 0.10) * 0.8
                cen = poly.mean(0)
                M = np.array([[sc, 0, (1 - sc) * cen[0]], [0, sc, (1 - sc) * cen[1]]])
                if u_exit > 0:                                # shatter: fly away from the screen centre and tilt
                    d = cen - [W / 2, H / 2]
                    d = d / (np.linalg.norm(d) + 1e-6) if np.linalg.norm(d) > 1 else np.array([0.0, -1.0])
                    off = d * (u_exit ** 2) * 0.9 * H
                    ang = math.radians((12 if it["_seed"] % 2 else -12) * u_exit)
                    R = cv2.getRotationMatrix2D((float(cen[0]), float(cen[1])), math.degrees(ang), 1.0)
                    M = np.vstack([R, [0, 0, 1]]) @ np.vstack([M, [0, 0, 1]])
                    M = M[:2]; M[:, 2] += off
                layer = np.zeros_like(frame)
                layer[by0:by1, bx0:bx1] = img[:by1 - by0, :bx1 - bx0]
                if flash > 0:
                    layer[by0:by1, bx0:bx1] = cv2.addWeighted(layer[by0:by1, bx0:bx1], 1 - flash, np.full_like(layer[by0:by1, bx0:bx1], 255), flash, 0)
                mask = np.zeros(frame.shape[:2], np.uint8)
                cv2.fillPoly(mask, [poly.astype(np.int32)], 255, cv2.LINE_AA)
                cv2.polylines(layer, [poly.astype(np.int32)], True, INK, border, cv2.LINE_AA)
                cv2.polylines(mask, [poly.astype(np.int32)], True, 255, border, cv2.LINE_AA)
                layer = cv2.warpAffine(layer, M, (W, H), flags=cv2.INTER_LINEAR)
                mask = cv2.warpAffine(mask, M, (W, H), flags=cv2.INTER_LINEAR)
                a = (mask.astype(np.float32) / 255.0 * (1 - _ease_out(u_exit) * 0.6))[..., None]
                out = out * (1 - a) + layer.astype(np.float32) * a
            frame = np.clip(out, 0, 255).astype(np.uint8)
        return frame
