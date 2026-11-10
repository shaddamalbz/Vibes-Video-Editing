"""Meme caption in the style of emote-reaction Shorts (user 5 Nov 2026, ref youtube.com/shorts/Fsx6xs58UP4): lowercase bold rounded text, white (or green) fill,
thick black outline, plus a small funny sticker (Reuseable Assets/Stickers, white sticker edge) next to it. Small in a long (16:9), a bit bigger in a Short.
Draws onto a frame (preview) or writes a transparent RGBA overlay of the full canvas for the render.

usage:
  py -3.14 meme_caption.py <frame.png|WxH> <out.png> "<text>" --at X Y [--sticker name] [--side right|left|below|above] [--size 46] [--sticker-h 120] [--fill white|green]
  X Y = centre of the text block in canvas pixels (e.g. just above a character's head). <frame> = WxH (e.g. 1920x1080) writes a transparent overlay.
"""
import argparse, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__))), "scripts"))
import projcfg

STICKERS = projcfg.path("reusable_dir", "Stickers")
FONT = projcfg.FontMap({"meme_caption": ("bold", r"C:\Windows\Fonts\ARLRDBD.TTF")})["meme_caption"]
FILLS = {"white": (255, 255, 255), "green": (118, 255, 92), "yellow": (255, 226, 70)}


def sticker_frames(name):
    """[(RGBA frame, duration ms)] of an (animated) sticker"""
    p = next(f"{STICKERS}/{name}{e}" for e in (".png", ".webp", ".gif") if os.path.exists(f"{STICKERS}/{name}{e}"))
    im = Image.open(p)
    out = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        out.append((im.convert("RGBA"), im.info.get("duration", 100) or 100))
    return out


def sticker(name, h, edge, frame=0):
    im = sticker_frames(name)[frame][0] if isinstance(name, str) else name
    im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    pad = edge + 2
    big = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    big.alpha_composite(im, (pad, pad))
    a = big.getchannel("A").filter(ImageFilter.MaxFilter(2 * edge + 1))
    out = Image.new("RGBA", big.size, (255, 255, 255, 0))
    out.putalpha(a)
    out.alpha_composite(big)
    return out


def caption(text, size, fill):
    f = ImageFont.truetype(FONT, size)
    sw = max(3, round(size * 0.16))
    l, t, r, b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f, stroke_width=sw)
    im = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((4 - l, 4 - t), text, font=f, fill=FILLS.get(fill, fill), stroke_width=sw, stroke_fill=(0, 0, 0))
    return im


def block(text, stick=None, side="right", size=46, sh=120, fill="white", gap=10, frame=0):
    """caption text + sticker as one RGBA image (frame = sticker animation frame)"""
    cap = caption(text, size, fill) if text else None
    st = sticker(stick, sh, max(3, sh // 22), frame) if stick else None
    if cap is None:
        return st
    if st is None:
        return cap
    if side in ("right", "left"):
        w, h = cap.width + gap + st.width, max(cap.height, st.height)
        b = Image.new("RGBA", (w, h))
        b.alpha_composite(cap, (0 if side == "right" else st.width + gap, (h - cap.height) // 2))
        b.alpha_composite(st, (cap.width + gap if side == "right" else 0, (h - st.height) // 2))
    else:
        w, h = max(cap.width, st.width), cap.height + gap + st.height
        b = Image.new("RGBA", (w, h))
        top, bot = (cap, st) if side == "below" else (st, cap)
        b.alpha_composite(top, ((w - top.width) // 2, 0))
        b.alpha_composite(bot, ((w - bot.width) // 2, top.height + gap))
    return b


def write_sprite(outdir, text, stick=None, side="right", size=46, sh=120, fill="white"):
    """frames of the caption block (one per sticker animation frame) + meta.json, for render.py's overlay layer (overlay.py).
    Returns (w, h) of the block in pixels at the 1080p size it was drawn for."""
    import json
    os.makedirs(outdir, exist_ok=True)
    fr = sticker_frames(stick) if stick else [(None, 100)]
    for i in range(len(fr)):
        block(text, stick, side, size, sh, fill, frame=i).save(f"{outdir}/{i:06d}.png")
    w, h = Image.open(f"{outdir}/000000.png").size
    ms = sum(d for _, d in fr) / len(fr)
    json.dump({"frames": len(fr), "fps": round(1000 / ms, 3), "body_cx": 0.5, "w": w, "h": h}, open(f"{outdir}/meta.json", "w"))
    return w, h


def build(canvas, text, at, stick=None, side="right", size=46, sh=120, fill="white", gap=10):
    cap = caption(text, size, fill)
    st = sticker(stick, sh, max(3, sh // 22)) if stick else None
    if st is None:
        w, h = cap.size
        block = Image.new("RGBA", (w, h))
        block.alpha_composite(cap)
    elif side in ("right", "left"):
        w, h = cap.width + gap + st.width, max(cap.height, st.height)
        block = Image.new("RGBA", (w, h))
        cx = 0 if side == "right" else st.width + gap
        block.alpha_composite(cap, (cx, (h - cap.height) // 2))
        block.alpha_composite(st, (cap.width + gap if side == "right" else 0, (h - st.height) // 2))
    else:
        w, h = max(cap.width, st.width), cap.height + gap + st.height
        block = Image.new("RGBA", (w, h))
        top, bot = (cap, st) if side == "below" else (st, cap)
        block.alpha_composite(top, ((w - top.width) // 2, 0))
        block.alpha_composite(bot, ((w - bot.width) // 2, top.height + gap))
    x, y = round(at[0] - w / 2), round(at[1] - h / 2)
    canvas.alpha_composite(block, (max(0, min(x, canvas.width - w)), max(0, min(y, canvas.height - h))))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame")
    ap.add_argument("out")
    ap.add_argument("text")
    ap.add_argument("--at", nargs=2, type=float, required=True)
    ap.add_argument("--sticker", default=None)
    ap.add_argument("--side", default="right", choices=["right", "left", "below", "above"])
    ap.add_argument("--size", type=int, default=46)
    ap.add_argument("--sticker-h", type=int, default=120)
    ap.add_argument("--fill", default="white")
    a = ap.parse_args()
    if "x" in a.frame and not os.path.exists(a.frame):
        W, H = map(int, a.frame.split("x"))
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    else:
        canvas = Image.open(a.frame).convert("RGBA")
    build(canvas, a.text, a.at, a.sticker, a.side, a.size, a.sticker_h, a.fill)
    canvas.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
