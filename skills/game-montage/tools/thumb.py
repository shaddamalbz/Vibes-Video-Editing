"""Thumbnails and covers from one photo: Shorts cover (1080x1920) + TikTok cover (1080x1440), long thumbnail (1920x1080),
text-free covers, an in-game frame polished into a 9:16 photo, and a frame with its subtitle inpainted.

Style: the full picture with no panels or gradients over it; a small game title line, then a two-line hook, both with an
outline and a soft shadow only around the letters. One hook line can take the accent colour.

    thumb.py short <photo> <out_shorts.png> <out_tiktok.png> <line1> <line2> <accent 0|1|2> [--arrow fx0,fy0,fx1,fy1] [--title "..."]
    thumb.py long  <photo> <out.png> <line1> <line2> <accent 0|1|2> [--crop-top 0-1] [--title "..."]
    thumb.py cover <photo> <out_shorts.png> <out_tiktok.png> [--focus-y 0.42]
    thumb.py photo <frame> <out.png> [--x0 N] [--gamma 1.3] [--sat 1.12] [--sharpen 0.7] [--erase x0,y0,x1,y1 ...]
    thumb.py clean <frame.png | video | recording tag> <out.png> [--band x0,y0,x1,y1] [--t seconds]

accent = which hook line gets the accent colour (1 or 2; 0 = none). --arrow is in fractions of the PHOTO, tail then tip,
so it lands on the same spot in both crops. --erase boxes are OUTPUT pixels (1080x1920) and are inpainted (HUD bits).
--band is in pixels of a 1920x1080 frame.

Everything about the look comes from the game profile section "thumb" (<profile_dir>/games/<game>.json, found through
recordings.json in the work folder, see reclib.py); every key is optional:

    "thumb": {"title": "MY GAME",                 default: the profile's "game" name in capitals; --title wins; none = no title line
              "title_font": "<.ttf>", "hook_font": "<.ttf>",     default: font roles "bold" / "black" of video-project.json
              "text": [247, 242, 227], "accent": [232, 58, 48], "ink": [8, 8, 12],      RGB list or "#RRGGBB"
              "shadow": {"blur": 14, "opacity": 0.75},
              "short": {"title_size": 56, "title_track": 7, "hook_size": 128, "hook_min": 40, "margin": 110,
                        "y_shorts": 1225, "y_tiktok": 1000, "title_gap": 84, "line_gap": 1.14, "arrow_width": 26},
              "long": {"title_size": 58, "hook_size": 118, "xy": [70, 700], "title_gap": 80, "line_step": 130},
              "cover_focus_y": 0.42,
              "photo": {"gamma": 1.3, "sat": 1.12, "contrast": 1.08, "sharpen": 0.7},
              "sub_band": [430, 865, 1490, 980]}

"text" falls back to the channel palette colour "cream" of profile/brand.json. Needs numpy, opencv-python, Pillow.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import reclib
import projcfg

SHORTS, TIKTOK, LONG = (1080, 1920), (1080, 1440), (1920, 1080)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
D_SHORT = {"title_size": 56, "title_track": 7, "hook_size": 128, "hook_min": 40, "margin": 110, "y_shorts": 1225, "y_tiktok": 1000,
           "title_gap": 84, "line_gap": 1.14, "arrow_width": 26}
D_LONG = {"title_size": 58, "hook_size": 118, "xy": [70, 700], "title_gap": 80, "line_step": 130}
D_SHADOW = {"blur": 14, "opacity": 0.75}
D_PHOTO = {"gamma": 1.3, "sat": 1.12, "contrast": 1.08, "sharpen": 0.7}
D_BAND = [430, 865, 1490, 980]

# font name -> (role, preferred file); a "fonts" entry in video-project.json or the profile keys title_font / hook_font win
FONTS = projcfg.FontMap({"thumb_title": ("bold", "C:/Windows/Fonts/georgiab.ttf"), "thumb_hook": ("black", "C:/Windows/Fonts/ariblk.ttf")})


def _sec(key, defaults):
    """a sub-dict of the profile's "thumb" section over its built-in defaults"""
    return {**defaults, **(reclib.val("thumb", key, None) or {})}


def _rgb(v):
    if isinstance(v, str):
        v = v.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(x) for x in v)


def colours():
    """(text, accent, ink) as RGB tuples"""
    text = reclib.val("thumb", "text", None) or projcfg.brand().get("palette", {}).get("cream") or (247, 242, 227)
    return _rgb(text), _rgb(reclib.val("thumb", "accent", (232, 58, 48))), _rgb(reclib.val("thumb", "ink", (8, 8, 12)))


def title_text(title=None):
    """--title, else the profile's thumb title, else the game name in capitals, else None (no title line)"""
    t = title if title is not None else reclib.val("thumb", "title", None) or (reclib.game().get("game") or "").upper()
    return t or None


def _font(name, size):
    f = reclib.val("thumb", name.replace("thumb_", "") + "_font", None)
    return ImageFont.truetype(f if f and os.path.isfile(f) else FONTS[name], size)


def _open(photo):
    if not os.path.isfile(photo):
        raise SystemExit(f"thumb.py: photo not found: {photo}")
    try:
        return Image.open(photo).convert("RGB")
    except OSError as e:
        raise SystemExit(f"thumb.py: cannot read {photo} as an image ({e})")


def _save(im, out):
    d = os.path.dirname(os.path.abspath(out))
    if not os.path.isdir(d):
        raise SystemExit(f"thumb.py: output folder does not exist: {d}")
    im.save(out)


def _fill(im, W, H, y_of=None):
    """scale to cover WxH and crop (centre in x; y from y_of(scaled height) or centre).
    Returns the crop and a mapper from photo fractions to crop pixels."""
    k = max(W / im.width, H / im.height)
    r = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    x = (r.width - W) // 2
    y = y_of(r.height) if y_of else (r.height - H) // 2
    return r.crop((x, y, x + W, y + H)), (lambda fx, fy: (fx * r.width - x, fy * r.height - y))


def _shadowed(base, sh, ink):
    """darken the picture softly where the shadow mask is, nothing else"""
    s = _sec("shadow", D_SHADOW)
    sh = sh.filter(ImageFilter.GaussianBlur(s["blur"])).point(lambda v: int(v * s["opacity"]))
    return Image.composite(Image.new("RGB", base.size, ink), base, sh)


def _arrow(base, p0, p1, w, fill, ink):
    """hand-made meme arrow: shaft + triangular head, drawn as a fat outline copy first"""
    d = ImageDraw.Draw(base)
    v = np.subtract(p1, p0).astype(float)
    L = np.hypot(*v)
    u, n = v / L, np.array([-v[1], v[0]]) / L
    head = 3.2 * w
    s1 = np.array(p1) - u * head * 0.9
    tri = [tuple(p1), tuple(s1 + n * head * 0.62), tuple(s1 - n * head * 0.62)]
    for col, grow in ((ink, 12), (fill, 0)):
        d.line([tuple(p0), tuple(s1)], fill=col, width=w + grow)
        t = np.array(tri)
        c = t.mean(0)
        d.polygon([tuple(c + (q - c) * (1 + grow / head)) for q in t], fill=col)


def _spaced(d, xy, text, font, fill, track, stroke, sf):
    """letter-spaced text centred on xy[0]"""
    w = sum(d.textlength(c, font=font) for c in text) + track * (len(text) - 1)
    x = xy[0] - w / 2
    for c in text:
        d.text((x, xy[1]), c, font=font, fill=fill, stroke_width=stroke, stroke_fill=sf)
        x += d.textlength(c, font=font) + track


def _fit(text, maxw, start, smallest):
    s = start
    while s > smallest:
        f = _font("thumb_hook", s)
        if f.getlength(text) <= maxw:
            return f
        s -= 2
    return _font("thumb_hook", smallest)


def short_image(photo, size, y0, line1, line2, accent, arrow=None, title=None):
    """one vertical cover as a PIL image: size = (W, H), y0 = top of the title line"""
    W, H = size
    o = _sec("short", D_SHORT)
    text, acc, ink = colours()
    title = title_text(title)
    base, to_px = _fill(photo if isinstance(photo, Image.Image) else _open(photo), W, H)
    if arrow:
        _arrow(base, to_px(*arrow[:2]), to_px(*arrow[2:]), o["arrow_width"], acc, ink)
    # each hook line as big as it fits, so a long line never shrinks the short one
    rows = [(t, acc if str(accent) == str(i) else text, _fit(t, W - o["margin"], o["hook_size"], o["hook_min"]))
            for i, t in ((1, line1), (2, line2))]
    tfont = _font("thumb_title", o["title_size"])
    sh = Image.new("L", (W, H), 0)
    ds = ImageDraw.Draw(sh)
    if title:
        _spaced(ds, (W / 2, y0), title, tfont, 200, o["title_track"], 8, 200)
    y = y0 + o["title_gap"]
    for t, _, f in rows:
        ds.text((W / 2, y), t, font=f, fill=255, anchor="ma", stroke_width=16, stroke_fill=255)
        y += int(f.size * o["line_gap"])
    base = _shadowed(base, sh, ink)
    d = ImageDraw.Draw(base)
    if title:
        _spaced(d, (W / 2, y0), title, tfont, text, o["title_track"], 4, ink)
    y = y0 + o["title_gap"]
    for t, col, f in rows:
        d.text((W / 2, y), t, font=f, fill=col, anchor="ma", stroke_width=7, stroke_fill=ink)
        y += int(f.size * o["line_gap"])
    print(W, H, "hook sizes", [r[2].size for r in rows], "text bottom", y)
    return base


def short(photo, out_shorts, out_tiktok, line1, line2, accent, arrow=None, title=None):
    """Shorts cover + TikTok cover with the title line and the two-line hook"""
    im, o = _open(photo), _sec("short", D_SHORT)
    _save(short_image(im, SHORTS, o["y_shorts"], line1, line2, accent, arrow, title), out_shorts)
    _save(short_image(im, TIKTOK, o["y_tiktok"], line1, line2, accent, arrow, title), out_tiktok)


def long(photo, out, line1, line2, accent, crop_top=0.5, title=None):
    """16:9 thumbnail, text block on the lower left (away from the duration badge). crop_top 0 = keep the top, 1 = the bottom"""
    W, H = LONG
    o = _sec("long", D_LONG)
    text, acc, ink = colours()
    title = title_text(title)
    tfont, hfont = _font("thumb_title", o["title_size"]), _font("thumb_hook", o["hook_size"])
    X, Y = o["xy"]
    base, _ = _fill(_open(photo), W, H, lambda h: round((h - H) * crop_top))
    rows = [(line1, acc if str(accent) == "1" else text), (line2, acc if str(accent) == "2" else text)]

    def draw(d, title_fill, stroke_t, stroke_h, sf):
        if title:
            d.text((X, Y), title, font=tfont, fill=title_fill, stroke_width=stroke_t, stroke_fill=sf)
        y = Y + o["title_gap"]
        for t, col in rows:
            d.text((X, y), t, font=hfont, fill=col if sf == ink else 255, stroke_width=stroke_h, stroke_fill=sf)
            y += o["line_step"]

    sh = Image.new("L", (W, H), 0)
    draw(ImageDraw.Draw(sh), 200, 8, 16, 255)
    base = _shadowed(base, sh, ink)
    draw(ImageDraw.Draw(base), text, 4, 7, ink)
    _save(base, out)
    wide = [round(hfont.getlength(t)) for t in (line1, line2)]
    print(out, "width", *wide)
    if X + max(wide) > W:
        print(f"  WARNING: the hook is wider than the picture ({X + max(wide)} > {W}), shorten it")


def cover(photo, out_shorts, out_tiktok, focus_y=None):
    """text-free Shorts + TikTok covers: the photo only, centred in x, focus_y (0-1) kept in the middle of the crop"""
    fy = reclib.val("thumb", "cover_focus_y", 0.42) if focus_y is None else focus_y
    im = _open(photo)
    for out, (W, H) in ((out_shorts, SHORTS), (out_tiktok, TIKTOK)):
        c, _ = _fill(im, W, H, lambda h: min(max(0, round(fy * h - H / 2)), h - H))
        _save(c, out)
        print(out, W, H)


def photo(frame, out, x0=None, gamma=None, sat=None, sharpen=None, erase=()):
    """9:16 window of an in-game frame from source x0 (default: centre), scaled to 1080x1920, shadows lifted,
    a little contrast / saturation / sharpening; erase boxes (x0, y0, x1, y1 in output pixels) are inpainted"""
    o = _sec("photo", D_PHOTO)
    gamma, sat, sharpen = (o[k] if v is None else v for k, v in (("gamma", gamma), ("sat", sat), ("sharpen", sharpen)))
    im = _open(frame)
    w = round(im.height * 9 / 16)
    if x0 is None:
        x0 = (im.width - w) // 2
    im = im.crop((x0, 0, x0 + w, im.height)).resize(SHORTS, Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255
    a = a ** (1 / gamma)                                         # lift the dark game frame
    a = np.clip((a - 0.5) * o["contrast"] + 0.5, 0, 1)           # a touch of contrast back
    im = Image.fromarray((a * 255).astype(np.uint8))
    im = ImageEnhance.Color(im).enhance(sat)
    if sharpen > 0:
        im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=round(sharpen * 100), threshold=2))
    if erase:
        import cv2
        b = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
        m = np.zeros(b.shape[:2], np.uint8)
        for ex0, ey0, ex1, ey1 in erase:
            m[int(ey0):int(ey1), int(ex0):int(ex1)] = 255
        im = Image.fromarray(cv2.cvtColor(cv2.inpaint(b, m, 9, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB))
    _save(im, out)
    print(out, im.size)


def clean(frame, out, band=None, t=0.0):
    """inpaint the game subtitle of a frame: thin bright strokes inside the band only (a bright face stays).
    frame = an image, or a video / recording tag (then the frame at t seconds, scaled to 1920x1080)"""
    import cv2
    if frame.lower().endswith(IMAGE_EXT):
        _open(frame)
        im = cv2.imdecode(np.fromfile(frame, np.uint8), cv2.IMREAD_COLOR)
    else:
        src = reclib.video(frame)
        if not os.path.isfile(src):
            raise SystemExit(f"thumb.py: frame / video not found: {frame}")
        im = reclib.still(src, t, size=LONG, gray=False)
        if im is None:
            raise SystemExit(f"thumb.py: could not decode a frame of {src} at {t} s")
        im = im.copy()
    h, w = im.shape[:2]
    x0, y0, x1, y1 = band or reclib.val("thumb", "sub_band", D_BAND)
    x0, x1 = (round(v * w / LONG[0]) for v in (x0, x1))
    y0, y1 = (round(v * h / LONG[1]) for v in (y0, y1))
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    inside = np.zeros_like(g)
    inside[y0:y1, x0:x1] = 1
    th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, np.ones((15, 15), np.uint8))
    m = cv2.dilate(((th > 40) & (inside > 0)).astype(np.uint8) * 255, np.ones((9, 9), np.uint8))
    res = cv2.inpaint(im, m, 6, cv2.INPAINT_TELEA)
    _save(Image.fromarray(cv2.cvtColor(res, cv2.COLOR_BGR2RGB)), out)
    print(out, (w, h), "inpainted px", int((m > 0).sum()))


def _nums(n, cast=float):
    def parse(s):
        v = [cast(x) for x in s.split(",")]
        if len(v) != n:
            raise argparse.ArgumentTypeError(f"needs {n} comma-separated numbers, got {s!r}")
        return tuple(v)
    return parse


def main(argv=None):
    ap = argparse.ArgumentParser(description="thumbnails and covers from one photo (look from the game profile section \"thumb\")")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("short", help="Shorts cover 1080x1920 + TikTok cover 1080x1440 with title and hook")
    p.add_argument("photo"), p.add_argument("out_shorts"), p.add_argument("out_tiktok"), p.add_argument("line1"), p.add_argument("line2")
    p.add_argument("accent", choices=["0", "1", "2"], help="hook line in the accent colour (0 = none)")
    p.add_argument("--arrow", type=_nums(4), metavar="fx0,fy0,fx1,fy1", help="arrow tail and tip in fractions of the photo")
    p.add_argument("--title", help="title line (default: profile thumb title, else the game name in capitals)")
    p = sub.add_parser("long", help="long thumbnail 1920x1080, text on the lower left")
    p.add_argument("photo"), p.add_argument("out"), p.add_argument("line1"), p.add_argument("line2")
    p.add_argument("accent", choices=["0", "1", "2"])
    p.add_argument("--crop-top", type=float, default=0.5, help="vertical crop 0-1 (0.5 = centre)")
    p.add_argument("--title")
    p = sub.add_parser("cover", help="text-free Shorts + TikTok covers")
    p.add_argument("photo"), p.add_argument("out_shorts"), p.add_argument("out_tiktok")
    p.add_argument("--focus-y", type=float, help="photo height fraction kept in the middle (default 0.42)")
    p = sub.add_parser("photo", help="in-game frame -> polished 1080x1920 photo")
    p.add_argument("frame"), p.add_argument("out")
    p.add_argument("--x0", type=int, help="left edge of the 9:16 window in source pixels (default: centre)")
    p.add_argument("--gamma", type=float), p.add_argument("--sat", type=float)
    p.add_argument("--sharpen", type=float, help="unsharp amount, 0 = off (default 0.7)")
    p.add_argument("--erase", type=_nums(4, int), nargs="+", action="extend", default=[], metavar="x0,y0,x1,y1", help="output-pixel boxes to inpaint")
    p = sub.add_parser("clean", help="inpaint the subtitle band of a frame")
    p.add_argument("frame", help="image, video or recording tag"), p.add_argument("out")
    p.add_argument("--band", type=_nums(4, int), metavar="x0,y0,x1,y1", help="subtitle band in 1920x1080 pixels")
    p.add_argument("--t", type=float, default=0.0, help="time in seconds when the input is a video")
    a = ap.parse_args(argv)
    if a.cmd == "short":
        short(a.photo, a.out_shorts, a.out_tiktok, a.line1, a.line2, a.accent, a.arrow, a.title)
    elif a.cmd == "long":
        long(a.photo, a.out, a.line1, a.line2, a.accent, a.crop_top, a.title)
    elif a.cmd == "cover":
        cover(a.photo, a.out_shorts, a.out_tiktok, a.focus_y)
    elif a.cmd == "photo":
        photo(a.frame, a.out, a.x0, a.gamma, a.sat, a.sharpen, a.erase)
    else:
        clean(a.frame, a.out, a.band, a.t)


if __name__ == "__main__":
    main()
