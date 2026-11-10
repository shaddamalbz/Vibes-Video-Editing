"""EXAMPLE EDL generator = the one behind a finished shooter kill montage (23 kills on a pop song with a sung "bang bang" hook).
Copy it into a new work folder as make_edl.py and change the song-specific parts: START_BEAT / WINDOW_BEATS, BANGS (vocal hits),
PLAN (which kill on which beat), SATCHEL_PRE (special lead-in), texts. Effects can also be named presets from fx_catalog.py.

v6: ALL 23 kills in 120 beats; the satchel chase IS the relaxed opening; a kill on every sung "bang" of the four "bang bang" lines
(found on the Demucs vocal stem); brand tint + logo end card from the channel profile.
Revisions are made by editing edl.json (beats / speed keys / effects / transitions / texts / audio) and re-rendering, not by touching the pipeline.
Re-running this script overwrites edl.json (use it only to start over), then run exposure.py.
"""
import json
from timemap import TimeMap
from kitcfg import VIDEO

B = json.load(open("beats.json"))
K = {k["id"]: k for k in json.load(open("kills.json"))["kills"]}

SONG_FILE = B["song"]
START_BEAT = 88                        # bar 22 downbeat = 34.94 s (low-energy, relaxed part). Drop #1 = window beat 24, drop #2 = beat 88
WINDOW_BEATS = 120                     # 30 bars = 47.4 s (ends in the 1-bar dip at bar 51 -> calm outro)
P = B["beat_period"]
S0 = B["beats"][START_BEAT]
E = B["beat_energy"][START_BEAT:START_BEAT + WINDOW_BEATS + 1]

# no calm clips any more: the satchel chase is the relaxed opening (the user's call)
CALM = []

# (kill id, start beat, kill beat, end beat, intensity ramp, section, arc)
# Song map (window beats): guitar intro 0-20, the sung lead-in 20-24, chorus 1 = 24-54 (sung "...with a bang" on 24 and 40),
# the lead-in line again 50-55 with an a cappella stop at 54.1-55.85 (instrumental silent), then the "bang bang" hook four times,
# every 8 beats, the two "bang"s one beat apart (vocal onsets from the Demucs vocal stem, video s): 22.08/22.48, 25.22/25.68,
# 28.37/28.84, 31.53/31.94. Break 84-88, drop 2 = 88 (dense verse vocals), outro dip from 116.
# pair_a / pair_b = the kill on the 1st / 2nd "bang" of a line (kill beats = measured vocal onsets, a few ms off the grid on purpose).
# rapid = 2-beat clip (1 beat in, 1 out) for kills that read in a flash (death-cam / enemy not visible / ability).
# satchel = Blast Pack chase before kill #14 as the opening: wall hug 1627.8 (1.0x), throw ~1630.7-1631.3, flight 1631.3-1632.8 (slow-mo),
# landing + aim 1632.8-1633.7, enemy in the smoke 1633.7-1634.62 (deep slow-mo), kill ON the first sung "bang" (drop 1).
BANGS = [(55.924, 56.938), (63.879, 65.055), (71.871, 73.062), (79.878, 80.908)]
PLAN = [
    (14, 0, 24, 26, 1.90, "hero", "satchel"),                            # opening: satchel chase -> kill ON drop #1 (first sung "bang")
    (9, 26, 28, 30, 1.35, "drop", "std"),                                # B Upper, Vandal headshot mid-jump
    (10, 30, 32, 34, 1.35, "drop", "std"),                               # A Site, long-range Vandal headshot
    (2, 34, 36, 38, 1.40, "drop", "std"),                                # B Site, Sheriff through a wall
    (15, 38, 40, 42, 1.45, "drop", "std"),                               # open-field Phantom headshot on the 2nd "...with a bang" (15.76 s)
    (8, 42, 44, 46, 1.40, "drop", "std"),                                # defender spawn doorway, long-range headshot
    (1, 46, 48, 50, 1.30, "drop", "std"),                                # Sheriff, enemy clear in the centre
    # "bang bang" line 1: slow-mo approach through the a cappella stop, kill as the music slams back in
    (20, 50, BANGS[0][0], 56.45, 1.60, "pair", "pair_a_long"), (21, 56.45, BANGS[0][1], 59, 1.45, "pair", "pair_b"),
    (13, 59, 60, 61, 1.20, "rapid", "rapid"),                            # ability kill after death (death-cam)
    (11, 61, BANGS[1][0], 64.45, 1.40, "pair", "pair_a"), (12, 64.45, BANGS[1][1], 67, 1.45, "pair", "pair_b"),     # line 2 (#12 = spike carrier through smoke)
    (7, 67, 68, 69, 1.25, "rapid", "rapid"),
    (22, 69, BANGS[2][0], 72.45, 1.45, "pair", "pair_a"), (23, 72.45, BANGS[2][1], 75, 1.50, "pair", "pair_b"),     # line 3 (same round, A Tree)
    (16, 75, BANGS[3][0], 80.40, 1.55, "pair", "pair_a_long"), (17, 80.40, BANGS[3][1], 84, 1.55, "pair", "pair_b"),  # line 4 (same round), slow tail into the break
    (18, 84, 88, 90, 1.80, "hero", "hero"),                              # long corridor Phantom headshot ON drop #2 (lead-in over the 84-88 break)
    (5, 90, 92, 94, 1.50, "finale", "std"),                              # SMG duel, enemy shooting
    (4, 94, 96, 98, 1.50, "finale", "std"),                              # A Main, Vandal headshot in the muzzle flash
    (3, 98, 100, 101, 1.50, "rapid", "rapid"),                           # ability kill
    (6, 101, 104, 108, 1.60, "finale", "std"),                           # heavy, headshot, big visuals
    (19, 108, 112, 120, 1.65, "finale", "std"),                          # round-winning kill (WON) closes in the quiet bar
]
assert sorted(p[0] for p in PLAN) == sorted(K), "every kill exactly once"
assert all(PLAN[i][3] == PLAN[i + 1][1] for i in range(len(PLAN) - 1)), "clips must butt together"

COMBOS = [["zoom_punch", "rgb_split"], ["shake", "flash"], ["glitch", "zoom_punch"], ["motion_blur", "shake"],
          ["rgb_split", "flash", "zoom_punch"], ["shake", "glitch", "rgb_split"]]
FX_DEFAULT = {
    "zoom_punch": {"amp": 0.16, "dur": 0.34},
    "shake": {"amp": 0.024, "freq": 22, "decay": 0.14, "roll_deg": 1.0},
    "rgb_split": {"px": 16, "decay": 0.13},
    "flash": {"alpha": 0.70, "decay": 0.07},
    "glitch": {"dur": 0.24, "slices": 10, "shift": 0.10},
    "motion_blur": {"len": 36, "angle": 0, "decay": 0.09},
}
# rapid clips: one or two light effects (the next cut comes 0.4 s after the kill), rotating, never the same twice in a row
RAPID_COMBOS = [["zoom_punch"], ["rgb_split", "shake"], ["glitch"], ["shake", "zoom_punch"], ["flash"]]
FX_RAPID = {
    "zoom_punch": {"amp": 0.12, "dur": 0.22},
    "shake": {"amp": 0.018, "freq": 24, "decay": 0.10, "roll_deg": 0.8},
    "rgb_split": {"px": 12, "decay": 0.10},
    "flash": {"alpha": 0.50, "decay": 0.05},
    "glitch": {"dur": 0.16, "slices": 8, "shift": 0.08},
}
TRANS = ["whip_pan", "zoom_in", "glitch_cut", "flash_cut", "spin", "zoom_out"]
RAPID_TRANS = ["glitch_cut", "zoom_in", "flash_cut", "whip_pan"]
TRANS_DUR = {"calm": 0.50, "hero": 0.20, "drop": 0.12, "mid": 0.15, "finale": 0.13, "pair": 0.15, "rapid": 0.08}

# speed arcs: (fraction of the pre-kill span, speed) / (fraction of the post-kill span, speed)
ARC = {
    "std":    {"pre": [(0.0, 1.8), (0.45, 1.0), (0.78, 0.40), (1.0, 0.28)], "post": [(0.0, 1.35), (0.25, 0.65), (0.55, 0.50), (0.80, 1.0), (1.0, 2.0)]},
    "hero":   {"pre": [(0.0, 1.0), (0.50, 0.65), (0.80, 0.38), (1.0, 0.26)], "post": [(0.0, 1.50), (0.20, 0.70), (0.50, 0.50), (0.80, 0.90), (1.0, 1.6)]},
    "pair_a": {"pre": [(0.0, 1.8), (0.45, 1.0), (0.78, 0.45), (1.0, 0.32)], "post": [(0.0, 1.35), (1.0, 1.0)]},                 # snap, then cut to the second kill
    "pair_a_long": {"pre": [(0.0, 1.0), (0.50, 0.65), (0.80, 0.38), (1.0, 0.28)], "post": [(0.0, 1.35), (1.0, 1.0)]},          # long slow-mo approach
    "pair_b": {"pre": [(0.0, 1.0), (1.0, 1.0)], "post": [(0.0, 1.35), (0.25, 0.65), (0.55, 0.50), (0.80, 1.0), (1.0, 2.0)]},
    "rapid":  {"pre": [(0.0, 1.5), (0.6, 0.8), (1.0, 0.45)], "post": [(0.0, 1.2), (0.5, 0.75), (1.0, 1.4)]},           # 1 beat in, 1 beat out
}
# satchel opening: absolute keys (beats relative to the kill), 24-beat lead-in. Source at the keys: b-24 1627.8 (wall hug, 1.0x),
# b-15.6 1631.1 (throw), b-14.8 1631.3 -> b-9 1632.6 flight in slow-mo, b-8.3 1632.8 landing, b-6.4 1633.5 aiming, b-5.6 1633.7 -> kill: enemy in the smoke.
SATCHEL_PRE = [(-24.0, 1.0), (-15.6, 1.0), (-14.8, 0.55), (-9.0, 0.55), (-8.3, 0.95), (-6.4, 0.95), (-5.6, 0.55), (-0.001, 0.28)]


def speed_keys(pre_b, post_b, arc):
    a = ARC["hero" if arc == "satchel" else arc]
    if arc == "satchel":
        keys = [[x, s] for x, s in SATCHEL_PRE]
    else:
        keys = [[round(-pre_b * (1 - u), 4), s] for u, s in a["pre"]]
        keys[-1][0] = -0.001
    keys += [[round(post_b * u, 4), s] for u, s in a["post"]]
    return {"keys": keys}


clips = []
for i, (frame, bs, be, note) in enumerate(CALM):
    clips.append({"id": f"c{len(clips)+1:02d}", "calm": True, "note": note, "src_kill_frame": frame, "section": "calm",
                  "beats": {"start": bs, "kill": bs, "end": be}, "crop_x": 960,
                  "speed": {"keys": [[-100, 1.0], [100, 1.0]]}, "push_in": 0.0, "intensity": 0.0, "effects": []})
# "bang bang" lines: a different look per line; line 1 (music slams back after the a cappella stop) gets the flash.
# The 2nd tap stays readable: no flash / glitch on pair_b.
PAIR_A_COMBOS = [["flash", "zoom_punch", "shake"], ["zoom_punch", "rgb_split"], ["glitch", "zoom_punch"], ["shake", "zoom_punch", "rgb_split"]]
PAIR_B_COMBOS = [["rgb_split", "zoom_punch"], ["shake", "rgb_split"], ["zoom_punch", "shake"], ["rgb_split", "motion_blur"]]
k_i, r_i, l_i, prev_combo = 0, 0, -1, None
for (kid, bs, bk, be, ramp, section, arc) in PLAN:
    k_i += 1
    if section == "hero":
        combo = ["flash", "zoom_punch", "shake"] if k_i == 1 else ["flash", "glitch", "zoom_punch"]
    elif section == "pair":
        if arc.startswith("pair_a"):
            l_i += 1
        combo = (PAIR_A_COMBOS if arc.startswith("pair_a") else PAIR_B_COMBOS)[l_i % 4]
    elif section == "rapid":
        combo = RAPID_COMBOS[r_i % len(RAPID_COMBOS)]; r_i += 1
    else:
        combo = COMBOS[k_i % len(COMBOS)]
        if combo == prev_combo:
            combo = COMBOS[(k_i + 1) % len(COMBOS)]
    prev_combo = combo
    fx = []
    for name in combo:
        p = dict((FX_RAPID if section == "rapid" else FX_DEFAULT)[name]); p["type"] = name
        if name == "motion_blur":
            p["angle"] = [0, 90, 35][k_i % 3]
        fx.append(p)
    e_kill = E[int(bk)]
    c = {
        "id": f"c{len(clips)+1:02d}", "kill_id": kid, "src_kill_frame": K[kid]["kill_frame"], "section": section, "arc": arc,
        "beats": {"start": bs, "kill": bk, "end": be}, "crop_x": 960,
        "speed": speed_keys(bk - bs, be - bk, arc),
        "push_in": 0.09 if section == "hero" else (0.0 if section in ("pair", "rapid") else 0.05),
        "intensity": round(ramp * (0.75 + 0.5 * e_kill), 3),
        "beat_energy_at_kill": round(e_kill, 2), "effects": fx,
    }
    if arc == "pair_b":
        c["audio_kill_hit"] = {"lead": 0.0, "decay_tau": 0.28}          # no crescendo before the 2nd tap, it lands one beat after the 1st
    if arc == "rapid":
        c["audio_kill_hit"] = {"lead": 0.20, "decay_tau": 0.30, "post": 0.70}   # tighter tail: the next hit comes 0.79 s later
        c["audio_duck_db"] = 6.0                                       # lighter duck so a run of hits does not pump the song
    clips.append(c)

for i in range(len(clips) - 1):
    cur, nxt = clips[i], clips[i + 1]
    if cur.get("arc", "").startswith("pair_a"):
        cur["transition_out"] = {"type": "glitch_cut", "dur": 0.08, "dir": 1}          # kill, cut, kill
        continue
    rapid = "rapid" in (cur["section"], nxt["section"])
    pool = RAPID_TRANS if rapid else TRANS
    if cur["section"] == "calm" or nxt["section"] == "hero":
        t = "luma_fade"                                    # soft dissolves: calm -> calm, into the drops
    elif cur["section"] == "hero":
        t = "whip_pan"
    else:
        t = pool[i % len(pool)]
    prev = clips[i - 1]["transition_out"]["type"] if i > 0 else None
    if t == prev and t != "luma_fade":
        t = pool[(i + 1) % len(pool)]
    dur = TRANS_DUR["rapid"] if rapid and t != "luma_fade" else TRANS_DUR[cur["section"]]
    cur["transition_out"] = {"type": t, "dur": dur, "dir": 1 if i % 2 == 0 else -1}

# where does the satchel go off in the output? (source ~1631.4 = 3.22 s before the kill)
sat = next(c for c in clips if c.get("arc") == "satchel")
tm = TimeMap(sat["speed"], (sat["beats"]["kill"] - sat["beats"]["start"]) * P, (sat["beats"]["end"] - sat["beats"]["kill"]) * P, P)
boom_beat = round(sat["beats"]["kill"] + tm.inverse(-3.2) / P, 2)
src_start = tm.offset(-(sat["beats"]["kill"] - sat["beats"]["start"]) * P)

# on-screen text (beats from the window start). Only words that are actually sung (user-typed lyric words + BANG) and the kill counters.
texts = [
    {"text": "BANG", "beat": 24.0, "dur": 2.8, "style": "chrome", "anim": "pop", "pos": [0.5, 0.38], "width": 0.78},
    {"text": "BANG", "beat": 40.0, "dur": 1.9, "style": "chrome", "anim": "pop", "pos": [0.5, 0.40], "width": 0.66},      # 2nd "...with a bang"
]
# each "bang bang" line: "BANG" on the kill of the 1st bang, "BANG BANG" on the kill of the 2nd
for li, (b1, b2) in enumerate(BANGS):
    nxt_clip_end = next(p[3] for p in PLAN if abs(p[2] - b2) < 1e-6)
    texts.append({"text": "BANG", "beat": b1, "dur": round(b2 - b1, 3), "style": "chrome", "anim": "pop", "pos": [0.5, 0.40], "width": 0.60})
    texts.append({"text": "BANG BANG", "beat": b2, "dur": round(min(3.0, nxt_clip_end - b2), 3), "style": "chrome", "anim": "pop", "pos": [0.5, 0.40], "width": 0.82})
# lyric words (kinetic, one at a time on the vocal hits of the bar before the first bang); the words come from lyrics.txt (user-typed)
LYRIC_SLOTS = [20.5, 21.0, 21.8, 22.3, 23.0, 23.5]
LYRIC_END = 23.95                                                  # the first bang lands on beat 24
words = []
for line in open("lyrics.txt", encoding="utf-8").read().splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        w, _, at = line.partition("@")
        words.append((w.strip().upper(), float(at) if at.strip() else None))
if words:
    free = [b for b in LYRIC_SLOTS]
    placed = []
    for w, at in words:
        if at is None:
            at = free.pop(0) if free else (placed[-1][1] + 0.5 if placed else LYRIC_SLOTS[0])
        else:
            free = [b for b in free if b > at]
        placed.append((w, at))
    size = min(0.21, 0.80 / (0.76 * max(len(w) for w, _ in placed)))
    for i, (w, at) in enumerate(placed):
        nxt = placed[i + 1][1] if i + 1 < len(placed) else LYRIC_END
        texts.append({"text": w, "beat": at, "dur": max(min(nxt - at, 3.0), 0.5), "style": "chrome", "anim": "pop", "pos": [0.5, 0.36],
                      "size": round(size, 3), "opacity": 0.95})
for n, (kid, bs, bk, be, ramp, section, arc) in enumerate(PLAN, 1):
    y = 0.31 if kid == 19 else (0.27 if arc == "pair_b" else 0.20)                  # #19: the game shows a WON banner at the top; 2nd tap stacks under the 1st
    nxt_k = PLAN[n][2] if n < len(PLAN) else 999
    dur = min(3.0, PLAN[n][3] - bk) if arc.startswith("pair_a") else min(3.0, nxt_k - bk - 0.04)   # pair_a stacks with its 2nd tap; others hand over to the next counter
    texts.append({"text": f"x{n}", "beat": bk, "dur": dur, "style": "counter", "anim": "pop", "accent": "cyan" if n % 2 else "coral", "pos": [0.5, y]})

edl = {
    "version": 6,
    "project": {"title": "Kill montage example", "video": VIDEO, "layout": "crop (9:16 centre crop, crosshair-centred)",
                "notes": "Edit this file and re-run render.py. beats are relative to the window start; 1 beat = song.beat_period s. "
                         "speed.keys = [beats relative to the kill, speed]; a snap is two keys a hair apart. calm clips have no kill (ambient game sound only). "
                         "texts are timed in beats. pair_a/pair_b clips are the double tap on the sung 'bang, bang' hooks."},
    "song": {"file": SONG_FILE, "window_start": S0, "start_beat_index": START_BEAT, "window_beats": WINDOW_BEATS,
             "bpm": B["bpm"], "beat_period": P, "audio_offset_ms": 0.0},
    "grade": {"contrast": 1.06, "brightness": 0.025, "saturation": 1.20, "gamma": 1.04, "sharpen": 0.6, "sharpen_final": 0.8, "vignette_angle": "PI/8"},
    "render": {"slowmo_interp": "flow"},
    "grade_ramp": {"at_beat": 24, "ramp_beats": 3.0, "from": {"saturation": 0.80, "contrast": 1.0, "brightness": 0.055, "gamma": 1.08}},
    "fades": {"video_in": 0.8, "video_out": 0.35},
    "tint": {"warm": [1.07, 1.00, 0.88], "cool": [0.95, 1.00, 1.08], "at_beat": 24, "ramp_beats": 3.0},
    "endcard": {"start_beat": 113.0, "fade_beats": 1.2, "bg_bgr": [38, 13, 2], "logo_width": 0.62, "logo_y": 0.365,
                "wordmark_width": 0.88, "wordmark_y": 0.650, "pixel_in": 0.55},      # logo + wordmark come from the channel profile (brand.py)
    "brand": {"midnight": "#07152E", "night": "#102448", "cyan": "#19CFE0", "coral": "#FF665E", "cream": "#F7F2E3",
              "sunset": "#FFC27A", "muted": "#AAB9CC",
              "note": "title-only wordmark in the end card"},
    "audio": {
        "kill_hit": {"pre": 0.02, "post": 0.90, "rms_db": -5.0, "attack": 0.002, "decay_tau": 0.38, "fade_out": 0.35, "bass_db": 7.0, "lead": 0.30, "lead_db": -10.0},
        "shots": {"max": 2, "peak_db": -6.0, "min_sep": 0.08, "len": 0.22, "post_events": 1, "post_db_offset": -4.0},
        "duck": {"kill_db": 8.0, "shot_db": 1.5, "lead_db": 3.0, "hold": 0.08, "release": 0.26}, "duck_split_hz": 220,
        "ambient_rms_db": -26.0, "song_gain_db": -7.5, "bus_comp_thr": 0.5,
        "bus_hp_hz": 30, "song_fade_in": 0.40, "song_fade_out": 1.00, "target_lufs": -14.0,
    },
    "clips": clips, "texts": texts,
}
json.dump(edl, open("edl.json", "w"), indent=1)
print(f"edl.json v6: {len(clips)} clips, {WINDOW_BEATS} beats = {WINDOW_BEATS*P:.2f}s, window {S0:.3f}s -> {S0+WINDOW_BEATS*P:.3f}s, beat {P:.4f}s ({60/P:.1f} BPM)")
for c in clips:
    b = c["beats"]
    print(f"  {c['id']} {'calm   ' if c.get('calm') else 'kill#%-2d' % c['kill_id']} beats {b['start']:6}->{b['kill']:5}->{b['end']:6} ({(b['end']-b['start'])*P:4.2f}s) {c['section']:6s} {c.get('arc',''):7s} int {c['intensity']:.2f} "
          f"fx {'+'.join(f['type'] for f in c['effects']):26s} out {c.get('transition_out',{}).get('type','-')}")
print(f"satchel clip: source starts {1634.62 + src_start:.2f}s (target ~1627.8), satchel detonation at beat {boom_beat}; {len(texts)} texts")
