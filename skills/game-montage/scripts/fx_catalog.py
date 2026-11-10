"""Named presets for the montage renderer: kill effects, transitions, speed styles and text styles.

In edl.json a clip can refer to presets by name instead of raw numbers:
    "effects": [{"preset": "shake_3"}, {"preset": "flash_2"}]
    "transition_out": {"preset": "whip_1"}
    "speed": {"preset": "hero"}
    texts: {"preset": "word_pop", "text": "BANG", "beat": 24, "dur": 2.8}
Any extra key next to "preset" overrides that one value, e.g. {"preset": "shake_2", "decay": 0.3}.
load_edl() (edl_lib.py) expands presets, so render.py, mix_audio.py and exposure.py only ever see plain values.

Effect amplitudes are multiplied by the clip's "intensity" (about 1.2 calm .. 2.0 hero).
Add a new look = add an entry here (and, for a brand-new effect type, a branch in render.py kill_effects/clip_frame),
then run fx_gallery.py so the catalog page shows it.
"""

# ---------------------------------------------------------------- kill effects (start ON the kill frame unless noted)
EFFECTS = {
    # zoom punch: quick push-in on the kill that settles back
    "zoom_1": {"type": "zoom_punch", "amp": 0.10, "dur": 0.25},
    "zoom_2": {"type": "zoom_punch", "amp": 0.16, "dur": 0.34},
    "zoom_3": {"type": "zoom_punch", "amp": 0.28, "dur": 0.45},
    # camera shake
    "shake_1": {"type": "shake", "amp": 0.012, "freq": 18, "decay": 0.12, "roll_deg": 0.4},
    "shake_2": {"type": "shake", "amp": 0.024, "freq": 22, "decay": 0.14, "roll_deg": 1.0},
    "shake_3": {"type": "shake", "amp": 0.045, "freq": 16, "decay": 0.22, "roll_deg": 2.5},
    "shake_4": {"type": "shake", "amp": 0.020, "freq": 8, "decay": 0.40, "roll_deg": 0.6},
    # RGB split (colour channels pull apart)
    "rgb_1": {"type": "rgb_split", "px": 8, "decay": 0.10},
    "rgb_2": {"type": "rgb_split", "px": 16, "decay": 0.13},
    "rgb_3": {"type": "rgb_split", "px": 30, "decay": 0.24},
    # white flash
    "flash_1": {"type": "flash", "alpha": 0.35, "decay": 0.05},
    "flash_2": {"type": "flash", "alpha": 0.70, "decay": 0.07},
    "flash_3": {"type": "flash", "alpha": 1.00, "decay": 0.16, "cap": 0.90},
    # digital glitch (sliced rows shifted sideways)
    "glitch_1": {"type": "glitch", "dur": 0.14, "slices": 8, "shift": 0.08},
    "glitch_2": {"type": "glitch", "dur": 0.24, "slices": 10, "shift": 0.10},
    "glitch_3": {"type": "glitch", "dur": 0.45, "slices": 14, "shift": 0.14},
    # motion blur smear
    "blur_h": {"type": "motion_blur", "len": 36, "angle": 0, "decay": 0.09},
    "blur_v": {"type": "motion_blur", "len": 36, "angle": 90, "decay": 0.09},
    "blur_diag": {"type": "motion_blur", "len": 44, "angle": 35, "decay": 0.12},
    # radial zoom blur burst from the centre
    "zoomblur_1": {"type": "zoom_blur", "amount": 0.06, "dur": 0.25},
    "zoomblur_2": {"type": "zoom_blur", "amount": 0.14, "dur": 0.40},
    # negative / inverted colours
    "invert_1": {"type": "invert", "alpha": 1.0, "dur": 0.10},
    "invert_2": {"type": "invert", "alpha": 0.6, "dur": 0.28},
    # strobe (white flicker)
    "strobe_1": {"type": "strobe", "rate": 12, "dur": 0.30, "alpha": 0.55},
    "strobe_2": {"type": "strobe", "rate": 8, "dur": 0.50, "alpha": 0.80},
    # black & white tricks
    "bw_pop": {"type": "desat", "mode": "after", "dur": 0.60},
    "color_burst": {"type": "desat", "mode": "before", "pre": 0.80},
    # cinematic bars slam in on the kill
    "letterbox_1": {"type": "letterbox", "size": 0.10, "dur": 0.80},
    # anime impact frames (anime.py): the shot redrawn in flat white / red / black on a few frames, with radial speed lines
    "impact_1": {"type": "impact", "frames": [[0.0, 0.05]], "styles": ["red"], "lines": 150},
    "impact_2": {"type": "impact", "frames": [[0.0, 0.034], [0.05, 0.084], [0.1, 0.134]], "styles": ["red", "dark", "red"], "lines": 160},
    "impact_3": {"type": "impact", "frames": [[-0.05, 0.0], [0.0, 0.067], [0.1, 0.15], [0.2, 0.25]], "styles": ["dark", "red", "dark", "bw"], "lines": 180},
    "impact_bw": {"type": "impact", "frames": [[0.0, 0.067]], "styles": ["bw"], "lines": 120},
    # anime speed lines (white wedges rushing to the centre)
    "speedlines_in": {"type": "speedlines", "from": -0.6, "to": 0.0, "alpha": 0.85, "count": 110, "fade_out": False},
    "speedlines_out": {"type": "speedlines", "from": 0.0, "to": 0.5, "alpha": 0.8, "count": 110, "fade_in": False},
    "speedlines_hold": {"type": "speedlines", "from": -1.5, "to": 1.5, "alpha": 0.55, "count": 80, "color": [20, 10, 12]},
    # ice (frost.py): the shot turns icy and frost creeps in from the edges; freeze_2 adds ice cracks from "center" after "crack" s.
    # "from" / "crack" are s after the anchor (or after "at"); "focus" [x, y] = the spot that stays clear longest (0..1 of the frame).
    # Pair with a freeze frame (speed key < 0.05) and the ice_shatter_1 transition on the cut.
    "freeze_1": {"type": "frost", "from": 0.0, "ramp": 0.6, "focus": [0.5, 0.5]},
    "freeze_2": {"type": "frost", "from": 0.0, "ramp": 0.55, "crack": 0.6, "crack_dur": 0.14, "focus": [0.5, 0.5], "center": [0.5, 0.5]},
}

EFFECT_INFO = {   # Indonesian one-liners for the catalog page
    "zoom_1": "Zoom kecil ke arah kill", "zoom_2": "Zoom standar (dipakai di Bang Bang)", "zoom_3": "Zoom besar, terasa menghantam",
    "shake_1": "Getar halus", "shake_2": "Getar standar", "shake_3": "Getar keras + miring", "shake_4": "Goyang pelan dan panjang",
    "rgb_1": "Warna sedikit pecah", "rgb_2": "Warna pecah standar", "rgb_3": "Warna pecah lebar, lama hilang",
    "flash_1": "Kilat putih tipis", "flash_2": "Kilat putih standar", "flash_3": "Layar hampir putih penuh",
    "glitch_1": "Glitch singkat", "glitch_2": "Glitch standar", "glitch_3": "Glitch panjang dan kasar",
    "blur_h": "Gambar tersapu ke samping", "blur_v": "Gambar tersapu ke atas-bawah", "blur_diag": "Gambar tersapu miring",
    "zoomblur_1": "Ledakan blur dari tengah, kecil", "zoomblur_2": "Ledakan blur dari tengah, besar",
    "invert_1": "Warna negatif sekejap", "invert_2": "Warna negatif tipis, lebih lama",
    "strobe_1": "Kedip putih cepat", "strobe_2": "Kedip putih lebih lambat dan terang",
    "bw_pop": "Jadi hitam-putih saat kill, warna kembali pelan", "color_burst": "Hitam-putih sebelum kill, warna meledak saat kill",
    "letterbox_1": "Bar hitam ala film muncul saat kill",
    "impact_1": "Impact frame anime: 1 kedip putih-merah-hitam", "impact_2": "Impact frame berkedip 3x (merah / gelap / merah)",
    "impact_3": "Impact frame besar: mulai sebelum pukulan, 4 kedip", "impact_bw": "Impact frame hitam-putih ala manga",
    "speedlines_in": "Garis kecepatan anime menuju pukulan", "speedlines_out": "Garis kecepatan setelah pukulan",
    "speedlines_hold": "Garis kecepatan gelap tipis, lama (momen tegang)",
    "freeze_1": "Gambar membeku: warna jadi biru es, embun beku merambat dari pinggir layar",
    "freeze_2": "Membeku + retakan es menyebar dari satu titik (pasangkan dengan transisi ice_shatter_1)",
}

# ---------------------------------------------------------------- transitions (on the cut to the next clip)
TRANSITIONS = {
    "cut": {"type": "cut", "dur": 0.0},
    "whip_1": {"type": "whip_pan", "dur": 0.12},
    "whip_2": {"type": "whip_pan", "dur": 0.22},
    "zoom_in_1": {"type": "zoom_in", "dur": 0.15},
    "zoom_out_1": {"type": "zoom_out", "dur": 0.15},
    "spin_1": {"type": "spin", "dur": 0.18},
    "glitch_cut_1": {"type": "glitch_cut", "dur": 0.08},
    "glitch_cut_2": {"type": "glitch_cut", "dur": 0.16},
    "flash_cut_1": {"type": "flash_cut", "dur": 0.12},
    "dissolve_1": {"type": "luma_fade", "dur": 0.50},
    "dip_black_1": {"type": "dip_black", "dur": 0.45},
    "ice_shatter_1": {"type": "ice_shatter", "dur": 0.42},
}
TRANSITION_INFO = {
    "cut": "Potong langsung, tanpa efek", "whip_1": "Sapuan kamera cepat", "whip_2": "Sapuan kamera lebih panjang",
    "zoom_in_1": "Masuk lewat zoom", "zoom_out_1": "Keluar lewat zoom mundur", "spin_1": "Putar 90 derajat",
    "glitch_cut_1": "Potong dengan glitch singkat", "glitch_cut_2": "Potong dengan glitch lebih lama",
    "flash_cut_1": "Potong lewat kilat putih", "dissolve_1": "Larut pelan (cocok untuk bagian santai)",
    "dip_black_1": "Gelap sebentar lalu terang lagi (ganti chapter / ganti bos di video panjang)",
    "ice_shatter_1": "Layar yang membeku pecah jadi serpihan kaca, klip berikutnya muncul di baliknya",
}

# ---------------------------------------------------------------- speed styles: (fraction of the span, speed)
# pre = from clip start to the kill, post = from the kill to clip end. Speeds < 0.9 use optical-flow slow-mo.
SPEED = {
    "std":    {"pre": [(0.0, 1.8), (0.45, 1.0), (0.78, 0.40), (1.0, 0.28)], "post": [(0.0, 1.35), (0.25, 0.65), (0.55, 0.50), (0.80, 1.0), (1.0, 2.0)]},
    "hero":   {"pre": [(0.0, 1.0), (0.50, 0.65), (0.80, 0.38), (1.0, 0.26)], "post": [(0.0, 1.50), (0.20, 0.70), (0.50, 0.50), (0.80, 0.90), (1.0, 1.6)]},
    "rapid":  {"pre": [(0.0, 1.5), (0.6, 0.8), (1.0, 0.45)], "post": [(0.0, 1.2), (0.5, 0.75), (1.0, 1.4)]},
    "pair_a": {"pre": [(0.0, 1.8), (0.45, 1.0), (0.78, 0.45), (1.0, 0.32)], "post": [(0.0, 1.35), (1.0, 1.0)]},
    "pair_a_long": {"pre": [(0.0, 1.0), (0.50, 0.65), (0.80, 0.38), (1.0, 0.28)], "post": [(0.0, 1.35), (1.0, 1.0)]},
    "pair_b": {"pre": [(0.0, 1.0), (1.0, 1.0)], "post": [(0.0, 1.35), (0.25, 0.65), (0.55, 0.50), (0.80, 1.0), (1.0, 2.0)]},
    "freeze": {"pre": [(0.0, 1.8), (0.45, 1.0), (0.78, 0.40), (1.0, 0.28)], "post": [(0.0, 0.05), (0.30, 0.05), (0.55, 1.0), (1.0, 1.6)]},
    "ramp_fast": {"pre": [(0.0, 2.2), (0.7, 1.4), (1.0, 0.5)], "post": [(0.0, 1.0), (1.0, 2.2)]},
    "real":   {"pre": [(0.0, 1.0), (1.0, 1.0)], "post": [(0.0, 1.0), (1.0, 1.0)]},
    "heavy":  {"pre": [(0.0, 1.0), (0.75, 1.0), (1.0, 0.6)], "post": [(0.0, 0.5), (0.3, 0.6), (0.65, 1.0), (1.0, 1.0)]},
}
SPEED_INFO = {
    "std": "Cepat masuk, slow-mo pas kill, cepat keluar", "hero": "Slow-mo panjang menuju kill (untuk drop)",
    "rapid": "Singkat, untuk rentetan kill cepat", "pair_a": "Kill pertama dari dua kill beruntun",
    "pair_a_long": "Seperti pair_a tapi pendekatan slow-mo panjang", "pair_b": "Kill kedua dari dua kill beruntun",
    "freeze": "Gambar hampir berhenti sesaat setelah kill", "ramp_fast": "Ngebut ke kill, lalu ngebut lagi", "real": "Kecepatan asli, tanpa slow-mo",
    "heavy": "Kecepatan asli, slow-mo sebentar pas pukulan (kesan berat, bos gede)",
}

# ---------------------------------------------------------------- text styles
TEXTS = {
    "word_pop": {"style": "chrome", "anim": "pop", "pos": [0.5, 0.40], "width": 0.78},
    "word_float": {"style": "chrome", "anim": "float", "pos": [0.5, 0.40], "width": 0.70},
    "counter": {"style": "counter", "anim": "pop", "pos": [0.5, 0.20], "accent": "cyan"},
    "badge": {"style": "badge", "anim": "pop", "pos": [0.5, 0.26]},
    "caption": {"style": "caption", "anim": "float", "pos": [0.5, 0.80]},
    "menace": {"style": "manga", "anim": "menace", "pos": [0.82, 0.30], "size": 0.10},      # ゴゴゴ (SFX letters, JoJo style)
    "manga_pop": {"style": "manga", "anim": "pop", "pos": [0.5, 0.30], "size": 0.16},       # ドン!! etc.
    # funny videos (memetext.py, not the brand look): meme word, TikTok caption box, chat-app card (one item per typing state)
    "meme_word": {"style": "meme", "anim": "pop", "pos": [0.5, 0.30], "width": 0.70},
    "tiktok_caption": {"style": "tiktok", "anim": "pop", "pos": [0.5, 0.70], "size": 0.052},
    "chat_card": {"style": "chat", "anim": "static", "pos": [0.5, 0.45]},
}
TEXT_INFO = {
    "word_pop": "Kata besar menghantam (seperti BANG)", "word_float": "Kata besar muncul pelan",
    "counter": "Label hitungan kill (x1, x2, ...)", "badge": "Label kecil warna coral", "caption": "Teks kecil di panel gelap",
    "menace": "Huruf efek suara manga bergetar (ゴゴゴ)", "manga_pop": "Huruf efek suara manga menghantam (ドン!!)",
    "meme_word": "Kata besar gaya meme: putih, garis hitam tebal (video lucu)", "tiktok_caption": "Caption gaya TikTok: huruf hitam di kotak putih",
    "chat_card": "Kartu chat ala ChatGPT yang mengetik (satu item per tahap ketik)",
}


def speed_keys(pre_b, post_b, name):
    """speed preset -> TimeMap keys in beats relative to the kill"""
    a = SPEED[name]
    keys = [[round(-pre_b * (1 - u), 4), s] for u, s in a["pre"]]
    keys[-1][0] = -0.001                                  # a snap at the kill = two keys a hair apart
    keys += [[round(post_b * u, 4), s] for u, s in a["post"]]
    return keys


def _merge(table, item, what):
    if not isinstance(item, dict) or "preset" not in item:
        return item
    name = item["preset"]
    if name not in table:
        raise ValueError(f"unknown {what} preset '{name}'. Known: {', '.join(table)}")
    return {**table[name], **item}


def expand(edl):
    """resolve every preset reference in an EDL (in place); idempotent"""
    for c in edl.get("clips", []):
        c["effects"] = [_merge(EFFECTS, fx, "effect") for fx in c.get("effects", [])]
        if c.get("transition_out"):
            c["transition_out"] = _merge(TRANSITIONS, c["transition_out"], "transition")
        sp = c.get("speed")
        if isinstance(sp, dict) and "preset" in sp:
            if sp["preset"] not in SPEED:
                raise ValueError(f"unknown speed preset '{sp['preset']}'. Known: {', '.join(SPEED)}")
            b = c["beats"]
            c["speed"] = {"preset": sp["preset"], "keys": speed_keys(b["kill"] - b["start"], b["end"] - b["kill"], sp["preset"])}
    edl["texts"] = [_merge(TEXTS, t, "text") for t in edl.get("texts", [])]
    return edl
