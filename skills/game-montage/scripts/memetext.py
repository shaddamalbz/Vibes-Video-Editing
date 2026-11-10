"""Meme / funny-video text looks (NOT the brand guideline look; the brand look stays for thumbnails and montage text).
Requested by the user on the first funny video (7 Oct 2026): the brand caption panel looked bad on a meme edit.

styles (used from textfx.make_sprite):
  "meme"   : big bold word, white (or "color") fill with a thick black outline and a hard shadow (DEATH 5, FINALLY.)
  "tiktok" : the classic TikTok caption: black bold text on a white rounded box, wraps to 2 lines
  "chat"   : a dark chat-app card (assistant parody): the user's prompt being typed in the input box ("typed" chars),
             then sent as a bubble with the reply streaming in ("reply_words"). Every state is one sprite; make_edl emits one
             text item per state ("anim": "static").
"""
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

import projcfg

F = projcfg.FontMap({                                              # name: (fallback role, preferred file); override in video-project.json "fonts"
    "black": ("black", r"C:\Windows\Fonts\seguibl.ttf"),
    "bold": ("bold", r"C:\Windows\Fonts\segoeuib.ttf"),
    "semi": ("semibold", r"C:\Windows\Fonts\seguisb.ttf"),
    "reg": ("regular", r"C:\Windows\Fonts\segoeui.ttf"),
})


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _out(img):
    """PIL RGBA -> (bgr uint8, alpha uint8)"""
    a = np.asarray(img)
    return np.ascontiguousarray(a[..., 2::-1]), np.ascontiguousarray(a[..., 3])


def meme(item, W):
    text = item["text"]
    if "size" in item:
        size = int(item["size"] * W)
    else:                                                      # fit the word to a fraction of the width
        f100 = ImageFont.truetype(F["black"], 100)
        b = f100.getbbox(text)
        size = int(100 * item.get("width", 0.7) * W / max(b[2] - b[0], 1))
    f = ImageFont.truetype(F["black"], max(size, 12))
    sw = max(2, int(size * 0.11))
    b = f.getbbox(text, stroke_width=sw)
    pad = int(size * 0.12)
    sh = max(2, int(size * 0.06))
    cw, ch = b[2] - b[0] + 2 * pad + sh, b[3] - b[1] + 2 * pad + sh
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    o = (pad - b[0], pad - b[1])
    d.text((o[0] + sh, o[1] + sh), text, font=f, fill=(0, 0, 0, 170), stroke_width=sw, stroke_fill=(0, 0, 0, 170))   # hard shadow
    d.text(o, text, font=f, fill=_hex(item.get("color", "#FFFFFF")) + (255,), stroke_width=sw, stroke_fill=(0, 0, 0, 255))
    return _out(img)


def _wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def tiktok(item, W):
    size = int(item.get("size", 0.052) * W)
    f = ImageFont.truetype(F["bold"], size)
    lines = _wrap(item["text"], f, W * item.get("wrap", 0.80))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.02)
    px, py = int(size * 0.42), int(size * 0.20)
    widths = [f.getlength(l) for l in lines]
    rad = int(size * 0.32)
    cw = int(max(widths)) + 2 * px + 4
    ch = lh * len(lines) + 2 * py + 4
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = _hex(item.get("bg", "#FFFFFF")) + (255,)
    for i, (l, w) in enumerate(zip(lines, widths)):          # one rounded box per line, like TikTok (centred, overlapping)
        x0 = (cw - w) / 2 - px
        y0 = py + i * lh - py * (0.6 if i else 1)
        d.rounded_rectangle([x0, y0, x0 + w + 2 * px, py + (i + 1) * lh + py * 0.4], radius=rad, fill=bg)
    for i, (l, w) in enumerate(zip(lines, widths)):
        d.text(((cw - w) / 2, py + i * lh + (lh - (asc + desc)) / 2), l, font=f, fill=_hex(item.get("ink", "#000000")) + (255,))
    return _out(img)


def chat(item, W):
    """dark chat card. item: user (full prompt), typed (chars typed so far, or None when sent), reply, reply_words, name"""
    s = item.get("_short", W) / 1080.0                       # 16:9 canvases scale the card by the short side
    cw = int(item.get("card_w", 0.90) * W)
    fs = int(46 * s)
    f, fb, fh = ImageFont.truetype(F["reg"], fs), ImageFont.truetype(F["semi"], fs), ImageFont.truetype(F["semi"], int(38 * s))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.12)
    user, reply = item["user"], item.get("reply", "")
    pad = int(34 * s)
    bub_max = int(cw * 0.72)
    ulines = _wrap(user, f, bub_max - 2 * int(26 * s))
    rlines = _wrap(reply, f, cw - 2 * pad) if reply else []
    head_h = int(84 * s)
    body_h = int(len(ulines) * lh + 2 * 22 * s) + int(28 * s) + len(rlines) * lh + int(24 * s)
    inp_h = int(96 * s)
    ch = head_h + body_h + inp_h + pad
    img = Image.new("RGBA", (cw + 8, ch + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, cw + 6, ch + 6], radius=int(34 * s), fill=(0, 0, 0, 120))                  # shadow
    d.rounded_rectangle([0, 0, cw, ch], radius=int(34 * s), fill=(33, 33, 33, 255), outline=(66, 66, 66, 255), width=max(1, int(2 * s)))
    d.text((pad, int(26 * s)), item.get("name", "ChatGPT"), font=fh, fill=(236, 236, 236, 255))
    nw = fh.getlength(item.get("name", "ChatGPT"))
    d.text((pad + nw + int(10 * s), int(26 * s)), "v", font=ImageFont.truetype(F["reg"], int(26 * s)), fill=(150, 150, 150, 255))
    d.line([0, head_h, cw, head_h], fill=(52, 52, 52, 255), width=max(1, int(2 * s)))
    y = head_h + int(24 * s)
    typed = item.get("typed")
    if typed is None:                                            # sent: the user's bubble (right) + the streaming reply (left)
        bw = int(max(f.getlength(l) for l in ulines)) + 2 * int(26 * s)
        bh = len(ulines) * lh + 2 * int(18 * s)
        bx = cw - pad - bw
        d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=int(28 * s), fill=(48, 48, 48, 255))
        for i, l in enumerate(ulines):
            d.text((bx + int(26 * s), y + int(18 * s) + i * lh), l, font=f, fill=(236, 236, 236, 255))
        y += bh + int(28 * s)
        n = item.get("reply_words", 0)
        if n > 0:
            shown = " ".join(reply.split()[:n])
            for i, l in enumerate(_wrap(shown, f, cw - 2 * pad)):
                d.text((pad, y + i * lh), l, font=f, fill=(236, 236, 236, 255))
    iy = ch - inp_h - int(10 * s)
    d.rounded_rectangle([pad - int(10 * s), iy, cw - pad + int(10 * s), iy + inp_h - int(14 * s)], radius=int(40 * s), fill=(48, 48, 48, 255))
    ty = iy + (inp_h - int(14 * s) - (asc + desc)) // 2
    if typed is None or typed == 0:
        d.text((pad + int(18 * s), ty), "Message " + item.get("name", "ChatGPT"), font=f, fill=(142, 142, 142, 255))
    else:
        t = user[:typed]
        maxw = cw - 2 * pad - int(110 * s)
        while f.getlength(t) > maxw:                              # long prompt: the input box scrolls, show the end
            t = t[1:]
        d.text((pad + int(18 * s), ty), t, font=f, fill=(236, 236, 236, 255))
        cx = pad + int(18 * s) + f.getlength(t) + int(4 * s)
        d.line([cx, ty + int(6 * s), cx, ty + asc + int(4 * s)], fill=(236, 236, 236, 255), width=max(2, int(3 * s)))   # caret
    r = int(30 * s)                                              # send button
    bx, by = cw - pad - int(14 * s) - r, iy + (inp_h - int(14 * s)) // 2
    on = typed not in (None, 0)
    d.ellipse([bx - r, by - r, bx + r, by + r], fill=(236, 236, 236, 255) if on else (90, 90, 90, 255))
    d.polygon([(bx, by - int(14 * s)), (bx - int(12 * s), by + int(2 * s)), (bx + int(12 * s), by + int(2 * s))], fill=(33, 33, 33, 255))
    d.line([bx, by, bx, by + int(14 * s)], fill=(33, 33, 33, 255), width=max(2, int(5 * s)))
    return _out(img)


# ---- modern looks (Wukong "first time playing", 13 Oct 2026: the user asked for meme edits that are "more advanced, not tacky / dated")
F.update({"serif": ("regular", r"C:\Windows\Fonts\GARA.TTF"), "serif_b": ("bold", r"C:\Windows\Fonts\GARABD.TTF"),
          "cond": ("bold", r"C:\Windows\Fonts\bahnschrift.ttf"), "sym": ("regular", r"C:\Windows\Fonts\seguisym.ttf")})


def _soft_shadow(img, radius, alpha, offset=(0, 0)):
    """img RGBA -> img over a blurred black copy of its alpha (a soft glow / drop shadow, no hard outline)"""
    a = np.asarray(img)[..., 3].astype(np.float32)
    k = max(3, int(radius) * 2 + 1)
    sh = cv2.GaussianBlur(a, (k, k), radius / 2.0) * alpha
    sh = np.roll(np.roll(sh, offset[1], 0), offset[0], 1)
    base = np.zeros(a.shape + (4,), np.uint8)
    base[..., 3] = np.clip(sh, 0, 255).astype(np.uint8)
    return Image.alpha_composite(Image.fromarray(base, "RGBA"), img)


def cine(item, W):
    """trailer title: Garamond caps with wide letter spacing, white, soft dark glow (no outline, no box)"""
    s = item.get("_short", W) / 1080.0
    size = int(item.get("size", 0.070) * W)
    f = ImageFont.truetype(F["serif_b" if item.get("bold") else "serif"], size)
    text = item["text"].upper() if item.get("caps", True) else item["text"]
    tr = item.get("track", 0.16) * size

    def span(t):
        return sum(f.getlength(c) for c in t) + tr * max(len(t) - 1, 0)

    lines = []                                                     # "\n" breaks lines; "wrap" (fraction of W) wraps long ones
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            nxt = (cur + " " + word).strip()
            if cur and item.get("wrap") and span(nxt) > item["wrap"] * W:
                lines.append(cur)
                cur = word
            else:
                cur = nxt
        lines.append(cur)
    tw = int(max(span(t) for t in lines))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * item.get("leading", 1.05))
    th = lh * (len(lines) - 1) + asc + desc
    pad = int(size * 0.6)
    img = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = _hex(item.get("color", "#F4EFE6")) + (255,)
    for k, t in enumerate(lines):
        x = pad + (tw - span(t)) / 2
        for c in t:
            d.text((x, pad + k * lh), c, font=f, fill=col)
            x += f.getlength(c) + tr
    if item.get("rule"):                                           # thin gold rule under the title
        y = pad + th + int(size * 0.05)
        img2 = Image.new("RGBA", (img.width, img.height + int(size * 0.3)), (0, 0, 0, 0))
        img2.paste(img, (0, 0))
        ImageDraw.Draw(img2).line([pad + tw * 0.3, y, pad + tw * 0.7, y], fill=_hex("#C9A45C") + (230,), width=max(2, int(3 * s)))
        img = img2
    for _ in range(int(item.get("shadow", 1))):                   # 2-3 = darker glow for bright backgrounds
        img = _soft_shadow(img, size * 0.35, 0.75)
    return _out(img)


def hud(item, W):
    """death counter as a clean game-HUD pill: [red bar] skull  DEATHS  n"""
    s = item.get("_short", W) / 1080.0
    h = int(item.get("size", 0.075) * item.get("_short", W))
    fl = ImageFont.truetype(F["cond"], int(h * 0.36))
    fn = ImageFont.truetype(F["cond"], int(h * 0.62))
    fs = ImageFont.truetype(F["sym"], int(h * 0.50))
    if item.get("minimal"):                                       # just the skull + the number, soft shadow, no pill / label / bar
        fn2, fs2 = ImageFont.truetype(F["cond"], int(h * 0.70)), ImageFont.truetype(F["sym"], int(h * 0.58))
        sw2, nw2, gap2 = fs2.getlength("☠"), fn2.getlength(item["text"]), int(h * 0.18)
        img = Image.new("RGBA", (int(sw2 + gap2 + nw2 + h * 0.4), h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((h * 0.2, h * 0.5), "☠", font=fs2, fill=(240, 236, 228, 230), anchor="lm")
        d.text((h * 0.2 + sw2 + gap2, h * 0.52), item["text"], font=fn2, fill=_hex(item.get("color", "#FFFFFF")) + (255,), anchor="lm")
        return _out(_soft_shadow(img, h * 0.18, 0.85, (0, int(h * 0.04))))
    label, num = item.get("label", "DEATHS"), item["text"]
    gap = int(h * 0.22)
    lw, nw, sw = fl.getlength(label), fn.getlength(num), fs.getlength("\u2620")
    bar = max(3, int(h * 0.07))
    cw = int(bar + gap + sw + gap * 0.8 + lw + gap * 0.7 + nw + gap * 1.2)
    img = Image.new("RGBA", (cw, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, cw - 1, h - 1], radius=int(h * 0.22), fill=(12, 12, 14, 175), outline=(255, 255, 255, 38), width=max(1, int(2 * s)))
    d.rectangle([0, int(h * 0.18), bar, int(h * 0.82)], fill=_hex(item.get("accent", "#E5484D")) + (255,))
    x = bar + gap
    d.text((x, h * 0.5), "\u2620", font=fs, fill=(240, 236, 228, 235), anchor="lm")
    x += sw + gap * 0.8
    d.text((x, h * 0.53), label, font=fl, fill=(240, 236, 228, 170), anchor="lm")
    x += lw + gap * 0.7
    d.text((x, h * 0.52), num, font=fn, fill=_hex(item.get("color", "#FFFFFF")) + (255,), anchor="lm")
    return _out(_soft_shadow(img, h * 0.15, 0.5, (0, int(h * 0.05))))


def plain(item, W):
    """modern caption: white semibold text, soft shadow, no box; wraps; lowercase is up to the writer"""
    s = item.get("_short", W) / 1080.0
    size = int(item.get("size", 0.050) * W)
    f = ImageFont.truetype(F[item.get("font", "semi")], size)
    lines = _wrap(item["text"], f, W * item.get("wrap", 0.82))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.05)
    pad = int(size * 0.5)
    widths = [f.getlength(l) for l in lines]
    cw, ch = int(max(widths)) + 2 * pad, lh * len(lines) + 2 * pad
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    hl = item.get("highlight")                                     # one word in the accent colour
    for i, (l, w) in enumerate(zip(lines, widths)):
        x = (cw - w) / 2 if item.get("align") != "left" else pad
        y = pad + i * lh
        if hl and hl in l.split():
            for word in l.split(" "):
                c = _hex(item.get("accent", "#FFD43B")) if word.strip(".,!?") == hl else _hex(item.get("color", "#FFFFFF"))
                d.text((x, y), word, font=f, fill=c + (255,))
                x += f.getlength(word + " ")
        else:
            d.text((x, y), l, font=f, fill=_hex(item.get("color", "#FFFFFF")) + (255,))
    return _out(_soft_shadow(img, size * 0.28, 0.9, (0, int(size * 0.04))))


def sub(item, W):
    """translated dialogue subtitle: white semibold on a dark rounded box that covers the game's own burned-in line underneath
    ("min_w" = the box is at least this fraction of W wide, "min_h" fraction of W tall, so the original subtitle is hidden)"""
    size = int(item.get("size", 0.024) * W)
    f = ImageFont.truetype(F[item.get("font", "semi")], size)
    lines = _wrap(item["text"], f, W * item.get("wrap", 0.62))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.08)
    padx, pady = int(size * 0.9), int(size * 0.35)
    widths = [f.getlength(l) for l in lines]
    cw = max(int(max(widths)) + 2 * padx, int(item.get("min_w", 0) * W))
    ch = max(lh * len(lines) + 2 * pady, int(item.get("min_h", 0) * W))
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=int(size * 0.45), fill=(8, 8, 10, int(item.get("box_alpha", 0.86) * 255)))
    y0 = (ch - lh * len(lines)) / 2
    for i, (l, w) in enumerate(zip(lines, widths)):
        d.text(((cw - w) / 2, y0 + i * lh), l, font=f, fill=_hex(item.get("color", "#FFFFFF")) + (255,))
    return _out(img)


def make(item, W):
    return {"meme": meme, "tiktok": tiktok, "chat": chat, "cine": cine, "hud": hud, "plain": plain, "sub": sub}[item["style"]](item, W)
