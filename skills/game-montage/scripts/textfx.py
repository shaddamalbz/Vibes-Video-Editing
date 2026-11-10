"""On-screen text for the montage, skinned with a small palette (default below; a channel profile's brand.json "palette" replaces it):
  colour tokens  : Midnight #07152E, Night blue #102448, Cyan #19CFE0, Coral #FF665E, Warm cream #F7F2E3, Sunset #FFC27A
  big words      : cream with a cyan ghost on the left and a coral ghost on the right (the same split as the S logo outline)
  lower-third    : compact Night blue panel (~86% opacity), cream text, 3px cyan / coral / sunset border, pixel-notched corners
  badge          : Coral panel with MIDNIGHT text (guideline rule for small labels)
Display font: Pixelify Sans is not installed, so the guideline fallback (bold monospace) is used and pixelated for the blocky look.
Text events live in edl.json under "texts", timed in beats:
  {"text": "BANG", "beat": 24, "dur": 3.4, "style": "chrome", "anim": "pop", "pos": [0.5, 0.40], "width": 0.80}
Styles: chrome | counter | badge | caption     Anims: pop (slam in, overshoot, quick fade out) | fade (soft in/out + slow drift) | static
Funny-video styles (memetext.py, not the brand look): meme (white word, thick black outline) | tiktok (black on a white box) | chat (chat-app card)
Optional per item: accent ("cyan" | "coral" | "sunset"), opacity.
"""
import math
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import memetext
import projcfg

HEX = {"midnight": "#07152E", "night": "#102448", "cyan": "#19CFE0", "coral": "#FF665E", "cream": "#F7F2E3", "sunset": "#FFC27A", "muted": "#AAB9CC"}


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


HEX.update(projcfg.brand().get("palette", {}))                    # a channel profile may rename / recolour the palette
BRAND = {k: _rgb(v) for k, v in HEX.items()}                       # RGB tuples
BGR = {k: (v[2], v[1], v[0]) for k, v in BRAND.items()}

FONTS = projcfg.FontMap({                                         # name: (fallback role, preferred file); override in video-project.json "fonts"
    "black": ("black", r"C:\Windows\Fonts\ariblk.ttf"),
    "mono": ("mono", r"C:\Windows\Fonts\consolab.ttf"),
    "semibold": ("semibold", r"C:\Windows\Fonts\seguisb.ttf"),
    "jp": ("bold", r"C:\Windows\Fonts\YuGothB.ttc"),          # Japanese manga SFX (ゴゴゴ, ドン): needs a font with kana
})
STYLES = {
    "chrome":  {"font": "black", "width": 0.80, "pixel": 2, "split": True},
    "counter": {"font": "mono", "size": 0.062, "pixel": 3, "panel": "night", "text": "cream", "padx": 0.55, "pady": 0.34},
    "badge":   {"font": "mono", "size": 0.050, "pixel": 3, "panel": "coral", "text": "midnight", "padx": 0.60, "pady": 0.34},
    "caption": {"font": "semibold", "size": 0.050, "pixel": 1, "panel": "night", "text": "cream", "padx": 0.70, "pady": 0.45},
    "manga":   {"font": "jp", "size": 0.12, "pixel": 1, "manga": True},     # manga SFX lettering: dark ink fill, thick paper outline
}


def _over(base_rgb, base_a, top_rgb, top_a):
    out_a = top_a + base_a * (1 - top_a)
    num = top_rgb * top_a[..., None] + base_rgb * (base_a * (1 - top_a))[..., None]
    out_rgb = num / np.maximum(out_a, 1e-6)[..., None]
    return out_rgb, out_a


def _pixelate(rgb, a, block):
    if block <= 1:
        return rgb, a
    h, w = a.shape
    pm = rgb * a[..., None]
    sm_p = cv2.resize(pm, (max(w // block, 1), max(h // block, 1)), interpolation=cv2.INTER_AREA)
    sm_a = cv2.resize(a, (max(w // block, 1), max(h // block, 1)), interpolation=cv2.INTER_AREA)
    big_p = cv2.resize(sm_p, (w, h), interpolation=cv2.INTER_NEAREST)
    big_a = cv2.resize(sm_a, (w, h), interpolation=cv2.INTER_NEAREST)
    return big_p / np.maximum(big_a, 1e-6)[..., None], big_a


def make_sprite(item, W):
    """returns (bgr uint8 (h,w,3), alpha uint8 (h,w))"""
    text, style = item["text"], item.get("style", "chrome")
    if style in ("meme", "tiktok", "chat", "cine", "hud", "plain", "sub"):
        return memetext.make(item, W)
    st = dict(STYLES[style])
    res = W / 1080.0
    if style == "chrome" and "width" in item:
        st["width"] = item["width"]
    path = FONTS[st["font"]]
    f100 = ImageFont.truetype(path, 100)
    b = f100.getbbox(text)
    size = int(100 * st["width"] * W / max(b[2] - b[0], 1)) if "width" in st else int(st["size"] * W)
    if "size" in item and style != "manga":                          # fixed font size (lyric words share one size; small 16:9 captions)
        size = int(item["size"] * W)
    f = ImageFont.truetype(path, max(size, 12))
    b = f.getbbox(text)
    tw, th = b[2] - b[0], b[3] - b[1]
    block = max(1, int(round(st["pixel"] * res)))

    if st.get("manga"):                                              # ---- manga SFX: ink fill (purple-black), thick white outline, hard shadow
        size = int(item.get("size", st["size"]) * W)
        f = ImageFont.truetype(path, max(size, 12))
        sw = max(2, int(size * 0.10))
        b = f.getbbox(text, stroke_width=sw)
        tw, th = b[2] - b[0], b[3] - b[1]
        pad = int(size * 0.25)
        cw, ch = tw + 2 * pad, th + 2 * pad
        outer = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(outer).text((pad - b[0], pad - b[1]), text, font=f, fill=255, stroke_width=sw, stroke_fill=255)
        inner = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(inner).text((pad - b[0], pad - b[1]), text, font=f, fill=255)
        mo, mi = np.asarray(outer, np.float32) / 255.0, np.asarray(inner, np.float32) / 255.0
        rgb = np.zeros((ch, cw, 3), np.float32); a = np.zeros((ch, cw), np.float32)
        sh = np.roll(np.roll(mo, int(size * 0.06), 0), int(size * 0.05), 1)
        rgb, a = _over(rgb, a, np.zeros((ch, cw, 3), np.float32), sh * 0.6)
        rgb, a = _over(rgb, a, np.broadcast_to(np.array((250, 248, 244), np.float32), (ch, cw, 3)), mo)
        ink = np.array(_rgb(item.get("ink", "#2B0F45")), np.float32)
        rgb, a = _over(rgb, a, np.broadcast_to(ink, (ch, cw, 3)), mi)
        return np.clip(rgb[..., ::-1], 0, 255).astype(np.uint8), np.clip(a * 255, 0, 255).astype(np.uint8)
    if "panel" not in st:                                            # ---- big word: cream gradient + glow + hard shadow
        pad = int(size * 0.45)
        cw, ch = tw + 2 * pad, th + 2 * pad
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).text((pad - b[0], pad - b[1]), text, font=f, fill=255)
        m = np.asarray(mask, np.float32) / 255.0
        top, bot = np.array((255, 252, 242), np.float32), np.array((236, 226, 204), np.float32)
        grad = (top[None, :] * (1 - np.linspace(0, 1, ch))[:, None] + bot[None, :] * np.linspace(0, 1, ch)[:, None])
        fill = np.repeat(grad[:, None, :], cw, axis=1)
        rgb = np.zeros((ch, cw, 3), np.float32); a = np.zeros((ch, cw), np.float32)
        sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(size * 0.03)), np.float32) / 255.0
        sh = np.roll(np.roll(sh, int(size * 0.045), axis=0), int(size * 0.03), axis=1)
        rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND["midnight"], np.float32), (ch, cw, 3)), sh * 0.55)
        gl = np.asarray(mask.filter(ImageFilter.GaussianBlur(size * 0.09)), np.float32) / 255.0
        rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND["cream"], np.float32), (ch, cw, 3)), np.clip(gl * 0.55, 0, 1))
        rgb, a = _over(rgb, a, fill, m)
    else:                                                            # ---- panel (counter / badge / caption lower third)
        px, py = int(size * st["padx"]), int(size * st["pady"])
        bw = max(int(round(3 * res)), 2) if st["panel"] == "night" else 0
        cw, ch = tw + 2 * px + 2 * bw, th + 2 * py + 2 * bw
        pad = int(6 * res) + block * 2
        W2, H2 = cw + 2 * pad, ch + 2 * pad
        rgb = np.zeros((H2, W2, 3), np.float32); a = np.zeros((H2, W2), np.float32)
        notch = max(2, block * 2)
        panel = np.zeros((H2, W2), np.float32); panel[pad:pad + ch, pad:pad + cw] = 1
        for (y, x) in ((pad, pad), (pad, pad + cw - notch), (pad + ch - notch, pad), (pad + ch - notch, pad + cw - notch)):
            panel[y:y + notch, x:x + notch] = 0                      # pixel-notched corners
        sh_off = max(block * 2, int(4 * res))
        shadow = np.roll(np.roll(panel, sh_off, 0), sh_off, 1)
        rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND["midnight"], np.float32), (H2, W2, 3)), shadow * 0.8)
        accent = BRAND[item.get("accent", "cyan")]
        if bw:
            inner = cv2.erode(panel, np.ones((2 * bw + 1, 2 * bw + 1), np.uint8))
            rgb, a = _over(rgb, a, np.broadcast_to(np.array(accent, np.float32), (H2, W2, 3)), panel)
            rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND["night"], np.float32), (H2, W2, 3)), inner * 0.90)
        else:
            rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND[st["panel"]], np.float32), (H2, W2, 3)), panel)
        tm = Image.new("L", (W2, H2), 0)
        ImageDraw.Draw(tm).text((pad + bw + px - b[0], pad + bw + py - b[1]), text, font=f, fill=255)
        tmask = np.asarray(tm, np.float32) / 255.0
        rgb, a = _over(rgb, a, np.broadcast_to(np.array(BRAND[st["text"]], np.float32), (H2, W2, 3)), tmask)
    rgb, a = _pixelate(rgb, a, block if "panel" in st or st.get("pixel", 1) > 1 else 1)
    return np.clip(rgb[..., ::-1], 0, 255).astype(np.uint8), np.clip(a * 255, 0, 255).astype(np.uint8)


def blit(frame, src, a, x0, y0, opacity):
    """alpha-blend src (bgr image or colour tuple) with alpha a (uint8 h,w) at (x0,y0)"""
    h, w = a.shape
    H, W = frame.shape[:2]
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    af = (a[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0].astype(np.float32) / 255.0 * opacity)[..., None]
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    col = (src[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0].astype(np.float32) if isinstance(src, np.ndarray) else np.array(src, np.float32))
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - af) + col * af).astype(np.uint8)


class TextLayer:
    def __init__(self, texts, P, fps, W, H):
        self.fps, self.W, self.H, self.res = fps, W, H, W / 1080.0
        self.items = []
        cache = {}
        for i, t in enumerate(texts):
            key = repr(sorted((k, repr(v)) for k, v in t.items() if k not in ("beat", "dur", "anim", "pos", "opacity", "fade_in", "fade_out")))
            if key not in cache:
                cache[key] = make_sprite({**t, "_short": min(W, H)}, W)
            n0 = int(round(t["beat"] * P * fps))
            n1 = int(round((t["beat"] + t["dur"]) * P * fps))
            self.items.append({**t, "sprite": cache[key], "n0": n0, "n1": max(n1, n0 + 2), "seed": i})

    def draw(self, frame, n):
        for it in self.items:
            if it["n0"] <= n < it["n1"]:
                self._blit(frame, it, n)
        return frame

    def _blit(self, frame, it, n):
        fps, W, H, res = self.fps, self.W, self.H, self.res
        x = (n - it["n0"]) / fps
        r = (it["n1"] - n) / fps
        px, py = it.get("pos", [0.5, 0.4])
        style = it.get("style", "chrome")
        sc, alpha, split, jx, jy = 1.0, 1.0, 0.0, 0.0, 0.0
        if it.get("anim", "pop") == "pop":
            sc = 1 + (0.50 if style in ("chrome", "meme") else 0.28) * math.exp(-x / 0.07)
            fo = min(0.20, 0.40 * (x + r))                      # short words (a sung eighth note = 0.2 s) get a proportionally short fade-out
            alpha = min(1.0, x / 0.04 + 0.2) * min(1.0, max(r / fo, 0.0))
            sc *= 1 + 0.10 * (1 - min(1.0, max(r / fo, 0.0)))
            split = 15 * res * math.exp(-x / 0.10)
            amp = (9 if style in ("chrome", "meme") else 4) * res * math.exp(-x / 0.12)
            ph = it["seed"] * 1.7
            jx = amp * math.sin(2 * math.pi * 23 * x + ph)
            jy = amp * 0.7 * math.sin(2 * math.pi * 29 * x + ph + 1.3)
        elif it.get("anim") == "static":                         # one state of a sequence (chat card typing): no fade, no motion
            alpha = 1.0
        elif it.get("anim") == "menace":                         # JoJo-style menacing letters: quick fade in, trembling, slow rise
            alpha = min(1.0, x / 0.12) * min(1.0, max(r / 0.25, 0.0))
            ph = it["seed"] * 2.3
            amp = 5 * res
            jx = amp * math.sin(2 * math.pi * 11 * x + ph)
            jy = amp * 0.8 * math.sin(2 * math.pi * 13 * x + ph + 0.9) - 22 * res * (x / max(x + r, 1e-3))
            sc = 1 + 0.04 * math.sin(2 * math.pi * 1.5 * x + ph)
        elif it.get("anim") == "drift":                          # trailer title: slow fade in/out, slow push (scale 1.00 -> 1.05)
            fi, fo = it.get("fade_in", 0.6), it.get("fade_out", 0.5)
            alpha = min(1.0, x / fi) * min(1.0, max(r / fo, 0.0))
            sc = 1.0 + 0.05 * (x / max(x + r, 1e-3))
        elif it.get("anim") == "tick":                           # HUD counter step: quick bump, no jitter, hard in, short fade out
            sc = 1 + 0.16 * math.exp(-x / 0.06)
            alpha = min(1.0, x / 0.03 + 0.3) * min(1.0, max(r / 0.12, 0.0))
        elif it.get("anim") == "sub":                            # translated subtitle: quick fade, no motion
            alpha = min(1.0, x / 0.08) * min(1.0, max(r / 0.08, 0.0))
        elif it.get("anim") == "rise":                           # modern caption: fade + 10 px rise in, fade out
            alpha = min(1.0, x / 0.12) * min(1.0, max(r / 0.15, 0.0))
            jy = 10 * res * math.exp(-x / 0.06)
        else:
            alpha = min(1.0, x / 0.30) * min(1.0, max(r / 0.35, 0.0))
            jy = -14 * res * (x / max(x + r, 1e-3))
        alpha *= it.get("opacity", 1.0)
        if alpha <= 0.01:
            return
        bgr, a = it["sprite"]
        sc = min(sc, max(1.0, 0.97 * W / a.shape[1]))     # the slam-in overshoot never pushes a long word out of frame
        if abs(sc - 1.0) > 1e-3:
            bgr = cv2.resize(bgr, None, fx=sc, fy=sc, interpolation=cv2.INTER_LINEAR)
            a = cv2.resize(a, None, fx=sc, fy=sc, interpolation=cv2.INTER_LINEAR)
        h, w = a.shape
        x0, y0 = int(round(px * W + jx - w / 2)), int(round(py * H + jy - h / 2))
        if it.get("align") == "left":                                # "pos" x = left edge (lower-third notes in 16:9)
            x0 = int(round(px * W + jx))
        if style == "chrome" and split > 0.5:                        # brand split: cyan ghost left, coral ghost right (like the S mark)
            k = int(round(split))
            blit(frame, BGR["cyan"], a, x0 - k, y0, alpha * 0.85)
            blit(frame, BGR["coral"], a, x0 + k, y0, alpha * 0.85)
        blit(frame, bgr, a, x0, y0, alpha)
