"""Text sprites for compose916.py (the looks of the 9:16 Shorts): pixel header, big game-line captions, small notes,
skull counter, white "text post" box, and the plain cap / box labels of the shot-list timeline.
Everything is drawn for a 1080x1920 canvas with Pillow and returned as RGBA images; premul() turns one into the
(BGR * alpha, alpha) float pair that paste() blends onto a frame.

Fonts go through projcfg.FontMap: the names below can be set in video-project.json "fonts" (by name, e.g. "c916_black", or by
role, e.g. "black"), or per spec with "fonts": {"black": "<file>"} (short names: black, note, box, round, emoji, symbol).
Colours: midnight / coral / cream / yellow, overridable by the "palette" of profile/brand.json or of the spec ("#RRGGBB").
"""
import os
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

import projcfg

W, H = 1080, 1920
PALETTE = {"midnight": (7, 21, 46), "coral": (255, 102, 94), "cream": (247, 242, 227), "yellow": (255, 214, 64)}
# short name: (role, files to try first; the first one is what the look was designed with)
FONT_PREFS = {
    "black": ("black", ["C:/Windows/Fonts/ariblk.ttf"]),
    "note": ("semibold", ["C:/Windows/Fonts/seguisb.ttf"]),
    "box": ("bold", ["C:/Windows/Fonts/arialbd.ttf"]),
    "round": ("bold", ["C:/Windows/Fonts/ARLRDBD.TTF", "C:/Windows/Fonts/arialbd.ttf"]),
    "emoji": ("emoji", ["C:/Windows/Fonts/seguiemj.ttf", "/System/Library/Fonts/Apple Color Emoji.ttc",
                        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]),
    "symbol": ("symbol", ["C:/Windows/Fonts/seguisym.ttf", "/System/Library/Fonts/Apple Symbols.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]),
}
NO_FALLBACK = ("emoji", "symbol")          # roles projcfg has no candidates for: a bold text font would draw empty boxes


class SpriteError(Exception):
    pass


def hex_rgb(v):
    if isinstance(v, str):
        v = v.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(x) for x in v)


def premul(im, crop=False):
    """RGBA image -> (BGR * alpha, alpha, dx, dy) float32; crop=True trims to the visible part (dx, dy = its offset)"""
    dx = dy = 0
    if crop:
        bb = im.getbbox()
        if bb:
            im, dx, dy = im.crop(bb), bb[0], bb[1]
    a = np.asarray(im).astype(np.float32)
    return a[..., 2::-1] * (a[..., 3:4] / 255.0), a[..., 3:4] / 255.0, dx, dy


def paste(frame, sprite, x, y, alpha=1.0):
    """blend a premul() sprite with its top-left corner at (x, y), clipped to the frame"""
    rgb, a = sprite[0], sprite[1]
    h, w = a.shape[:2]
    x, y = int(x) + sprite[2], int(y) + sprite[3]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    rgb, a = rgb[y0 - y:y1 - y, x0 - x:x1 - x], a[y0 - y:y1 - y, x0 - x:x1 - x]
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a * alpha) + rgb * alpha).astype(np.uint8)


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF


class Sprites:
    def __init__(self, fonts=None, palette=None):
        self.over = dict(fonts or {})
        self.col = dict(PALETTE)
        for src in (projcfg.brand().get("palette") or {}, palette or {}):
            for k, v in src.items():
                try:
                    self.col[k] = hex_rgb(v)
                except (ValueError, TypeError):
                    raise SpriteError(f'palette colour "{k}": {v!r} is not "#RRGGBB" or [r, g, b]')
        self.map = projcfg.FontMap({"c916_" + k: (role, next((f for f in files if os.path.isfile(f)), files[0]))
                                    for k, (role, files) in FONT_PREFS.items()})
        self._ttf = {}

    def colour(self, name):
        if name not in self.col:
            raise SpriteError(f'unknown colour "{name}" (have: {", ".join(sorted(self.col))}); add it to "palette"')
        return self.col[name]

    def font_file(self, name):
        if name in self.over:
            if not os.path.isfile(str(self.over[name])):
                raise SpriteError(f'font "{name}": file not found: {self.over[name]}')
            return self.over[name]
        role, prefer = self.map.spec["c916_" + name]
        fonts = projcfg.cfg()["fonts"]
        if role in NO_FALLBACK and not any(f and os.path.isfile(f) for f in (fonts.get("c916_" + name), prefer, fonts.get(role))):
            raise SpriteError(f'no font found for "{role}": set "fonts": {{"{role}": "<path to a font file>"}} in {projcfg.NAME} '
                              f'or "fonts": {{"{name}": "<file>"}} in the spec')
        try:
            return self.map["c916_" + name]
        except SystemExit as e:                                  # projcfg.font found nothing at all
            raise SpriteError(str(e))

    def font(self, name, size):
        if (name, size) not in self._ttf:
            f = self.font_file(name)
            try:
                self._ttf[name, size] = ImageFont.truetype(f, size)
            except OSError as e:
                raise SpriteError(f'font "{name}": cannot load {f} ({e})')
        return self._ttf[name, size]

    # ---- pixel header -------------------------------------------------------------------------------------------------
    def pixel_text(self, text, cap_px, block, color, track=2):
        f = self.font("black", int(cap_px * 1.38))
        tw = sum(f.getbbox(ch)[2] for ch in text) + track * len(text) + 4
        im = Image.new("L", (tw, int(cap_px * 2)), 0)
        d = ImageDraw.Draw(im)
        x = 2
        for ch in text:
            d.text((x, 0), ch, font=f, fill=255)
            x += f.getbbox(ch)[2] + track
        a = np.array(im) > 110
        ys, xs = np.where(a)
        if not len(ys):
            raise SpriteError(f"header line {text!r} draws nothing")
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        a = np.kron(a, np.ones((block, block), bool))
        pad = 8
        big = np.pad(a, pad)
        ring = cv2.dilate(big.astype(np.uint8), np.ones((2 * pad - 3, 2 * pad - 3), np.uint8)) > 0
        rgba = np.zeros(big.shape + (4,), np.uint8)
        rgba[ring] = self.col["midnight"] + (255,)
        rgba[big] = color + (255,)
        return Image.fromarray(rgba)

    def header(self, lines, emoji=None, y0=330, block_max=12):
        """lines [[text, colour name]] stacked from y0, each as big as fits 980 px; emoji after the last line.
        Returns (full-canvas image, y of the header's bottom edge)."""
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        y = y0
        for k, (text, col) in enumerate(lines):
            last = k == len(lines) - 1
            maxw = 980 - (130 if last and emoji else 0)
            p = None
            for blk in range(min(12, block_max), 3, -1):
                p = self.pixel_text(text, 9, blk, self.colour(col))
                if p.width <= maxw:
                    break
            if last and emoji:
                em = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
                ImageDraw.Draw(em).text((100, 100), emoji, font=self.font("emoji", 109), embedded_color=True)
                em = em.crop(em.getbbox())
                em = em.resize((round(em.width * 120 / em.height), 120), Image.LANCZOS)
                x = (W - (p.width + 18 + em.width)) // 2
                im.alpha_composite(p, (x, y))
                im.alpha_composite(em, (x + p.width + 18, y + (p.height - em.height) // 2))
            else:
                im.alpha_composite(p, ((W - p.width) // 2, y))
            y += p.height + 14
        return im, y - 14

    # ---- captions under the band / over the picture ---------------------------------------------------------------------
    def caption(self, text, kind="game"):
        """word-wrapped caps: game lines cream with *marked* words yellow + bigger; "react" all yellow; "note" small cream, as typed"""
        midnight, cream, yellow = self.col["midnight"], self.col["cream"], self.col["yellow"]
        im = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if kind == "note":
            d.multiline_text((W / 2, 40), text, font=self.font("note", 38), fill=cream + (235,), anchor="ma", align="center",
                             stroke_width=4, stroke_fill=midnight + (255,))
            return im
        if kind not in ("game", "react"):
            raise SpriteError(f'caption kind "{kind}": use "game", "react" or "note"')
        f, fh = self.font("black", 68), self.font("black", 84)
        words = [(w.replace("*", "").upper(), "*" in w or kind == "react") for w in text.split()]
        lines, cur, cw = [], [], 0
        for w, hi in words:
            ww = d.textlength(w + " ", font=fh if hi else f)
            if cur and cw + ww > W - 120:
                lines.append(cur)
                cur, cw = [], 0
            cur.append((w, hi))
            cw += ww
        lines.append(cur)
        y = 10
        for ln in lines:
            tw = sum(d.textlength(w + " ", font=fh if hi else f) for w, hi in ln) - d.textlength(" ", font=f)
            x = (W - tw) / 2
            for w, hi in ln:
                ft = fh if hi else f
                d.text((x, y + (0 if hi else 10)), w, font=ft, fill=(yellow if hi else cream) + (255,), stroke_width=9,
                       stroke_fill=midnight + (255,))
                x += d.textlength(w + " ", font=ft)
            y += 104
        return im

    def counter(self, n):
        midnight, cream = self.col["midnight"], self.col["cream"]
        im = Image.new("RGBA", (300, 90), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((10, 45), "\u2620", font=self.font("symbol", 54), fill=cream + (255,), anchor="lm", stroke_width=5,
               stroke_fill=midnight + (255,))
        d.text((78, 47), str(n), font=self.font("black", 50), fill=cream + (255,), anchor="lm", stroke_width=6,
               stroke_fill=midnight + (255,))
        return im.crop(im.getbbox())

    def memebox(self, text, room, fixed=None):
        """white rounded "text post" box, black bold sans, centred, 1-2 lines (the font shrinks until it fits `room` px of height);
        returns (image, font size); fixed = force one size (all boxes of a video share the smallest fitted size)"""
        bw = int(W * 0.9)
        for size in ((fixed,) if fixed else (66, 62, 58, 54, 50, 46, 42, 38)):
            f = self.font("box", size)
            fe = self.font("emoji", int(size * 0.9)) if any(is_emoji(c) for c in text) else f
            tl = lambda s: sum((fe if is_emoji(c) else f).getlength(c) for c in s)     # noqa: E731
            lines, cur = [], ""
            for w in text.split():
                nxt = (cur + " " + w).strip()
                if cur and tl(nxt) > bw - 56:
                    lines.append(cur)
                    cur = w
                else:
                    cur = nxt
            lines.append(cur)
            lh = int(size * 1.18)
            bh = len(lines) * lh + 2 * 18
            if len(lines) <= 2 and bh <= room:
                break
        im = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x0 = (W - bw) // 2
        d.rounded_rectangle((x0, 0, x0 + bw - 1, bh - 1), radius=26, fill=(255, 255, 255, 255))
        y = 18
        for ln in lines:
            x = (W - tl(ln)) / 2
            for c in ln:
                if is_emoji(c):
                    d.text((x, y + size * 0.02), c, font=fe, embedded_color=True)
                else:
                    d.text((x, y), c, font=f, fill=(12, 12, 12, 255))
                x += (fe if is_emoji(c) else f).getlength(c)
            y += lh
        return im, size

    # ---- labels of the shot-list timeline -------------------------------------------------------------------------------
    def label(self, text, size, style="cap"):
        """"cap" = white bold + thick black outline, "box" = black rounded-sans text on a white rounded box; \\n = new line"""
        if style not in ("cap", "box"):
            raise SpriteError(f'text style "{style}": use "cap" or "box"')
        f = self.font("round" if style == "box" else "box", size)
        lines = text.split("\n")
        d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        bbs = [d0.textbbox((0, 0), ln, font=f) for ln in lines]
        lw = max(b[2] - b[0] for b in bbs)
        lh = int(size * 1.18)
        pad = int(size * 0.45) if style == "box" else int(size * 0.18)
        im = Image.new("RGBA", (lw + 2 * pad, lh * len(lines) + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if style == "box":
            d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(size * 0.35), fill=(255, 255, 255, 255))
        for i, (ln, bb) in enumerate(zip(lines, bbs)):
            x = pad + (lw - (bb[2] - bb[0])) // 2 - bb[0]
            y = pad + i * lh - bb[1] + int(size * 0.05)
            if style == "box":
                d.text((x, y), ln, font=f, fill=(0, 0, 0, 255))
            else:
                d.text((x, y), ln, font=f, fill=(255, 255, 255, 255), stroke_width=max(4, size // 9), stroke_fill=(0, 0, 0, 255))
        return im
