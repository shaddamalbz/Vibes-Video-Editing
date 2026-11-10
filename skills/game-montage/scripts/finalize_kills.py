"""Kill detection stage D: frame-accurate onset for the visually verified own kills -> kills.json

Approximate kill times come from the detector union (killfeed-row tracker + 5fps scan + skull flash), each one
verified by eye against full-res crops (see probe/verify_*.png). Here every kill is re-localised on the 60fps features:
  1. yellow-outline surge in a 15-row window (own row appears)      -> f_y
  2. back-trace the row fill pop (teal jump) from f_y                -> row_onset  (= kill frame)
  3. confirmations: centre kill icon (white/flash), game-audio 6-11 kHz bump
"""
import json
from kitcfg import VIDEO, PLAYER
import numpy as np, soundfile as sf, librosa

FPS = 60.0
d = np.load("scan/feat60.npz")
skull = d["skull"].astype(np.int32)
teal_y = d["teal_y"].astype(np.int32); red_y = d["red_y"].astype(np.int32)
yel = d["yl_y"].astype(np.int32) + d["yr_y"].astype(np.int32)
N = len(skull)
WIN = 15
csum = np.concatenate([np.zeros((N, 1), np.int32), np.cumsum(yel, axis=1)], axis=1)
W = csum[:, WIN:] - csum[:, :-WIN]                        # (N,106) yellow px in 15-row window starting at y

# (approx time, note): the candidates Claude checked by eye on the make_sheets.py contact sheets and the user confirmed.
# verified.json in the work folder: [{"t": 245.37, "note": ""}, ...]
VERIFIED = [(v["t"], v.get("note", "")) for v in json.load(open("verified.json", encoding="utf-8"))]

y_a, sr = sf.read("scan/game_audio.wav")
hop = 110
S = np.abs(librosa.stft(y_a, n_fft=512, hop_length=hop))
fr = librosa.fft_frequencies(sr=sr, n_fft=512)
hi = S[fr >= 6000].sum(0)
t_a = np.arange(len(hi)) * hop / sr


def audio_ratio(t):
    i0, i1 = np.searchsorted(t_a, [t - 0.06, t + 0.12])
    b0, b1 = np.searchsorted(t_a, [t - 1.5, t - 0.3])
    return float(hi[i0:i1].max() / (np.median(hi[b0:b1]) + 1e-6))


def localise(tc):
    f0 = int(round(tc * FPS))
    lo, hi_ = max(f0 - 100, 20), min(f0 + 40, N - 30)
    best = None
    for f in range(lo, hi_):
        prev = W[f - 8:f].mean(0)
        ok = np.where((W[f] >= 50) & (prev < 20) & (W[f + 1:f + 9].max(0) >= 50))[0]   # outline can flicker for a few frames
        for y in ok:
            score = abs(f - (f0 + 4))
            if best is None or score < best[0]:
                best = (score, f, int(y))
    if best is None:
        return None
    _, fy, y = best
    a, b = max(y - 2, 0), min(y + 18, 120)
    series = teal_y[:, a:b].sum(1)
    base = np.median(series[fy - 25:fy - 10]); settled = np.median(series[fy + 3:fy + 14])
    thr = base + 0.5 * max(settled - base, 1)
    onset = fy
    for f in range(fy, fy - 16, -1):
        if series[f] >= thr:
            onset = f
        else:
            break
    teal = int(teal_y[fy + 3:fy + 30, a:b].sum()); red = int(red_y[fy + 3:fy + 30, a:b].sum())
    icon_white = next((f for f in range(onset - 4, onset + 9) if skull[f, 0] >= 250), None)
    icon_flash = next((f for f in range(onset, onset + 31) if skull[f, 2] >= 1200), None)
    return {"row_onset": int(onset), "yellow_frame": int(fy), "row_y": int(y), "band_teal": teal, "band_red": red,
            "yellow_sum": int(W[fy + 3, y]), "icon_white": icon_white, "icon_flash": icon_flash}


kills = []
for tc, note in VERIFIED:
    r = localise(tc)
    if r is None:
        print("!! could not localise", tc); continue
    kf = r["row_onset"]
    # earliest visual confirmation of the kill event: killfeed row pop or centre kill-icon start (icon only counts if it belongs to this row)
    if r["icon_white"] is not None and abs(r["icon_white"] - kf) <= 8:
        kf = min(kf, r["icon_white"])
    ar = audio_ratio(kf / FPS)
    icon = (r["icon_white"] is not None) or (r["icon_flash"] is not None)
    conf = 0.6 + 0.15 * icon + (0.10 if ar > 1.6 else (0.05 if ar > 1.25 else 0)) + 0.15   # +0.15: verified by eye on full-res crops
    kills.append({"kill_frame": kf, "kill_time": round(kf / FPS, 4), "approx_input": tc, "note": note,
                  "confidence": round(min(conf, 1.0), 2),
                  "signals": {"own_row_yellow_outline": True, "row_onset_frame": r["row_onset"], "yellow_outline_frame": r["yellow_frame"],
                              "center_icon_onset_frame": r["icon_white"], "center_icon_flash_frame": r["icon_flash"],
                              "audio_hi_band_ratio": round(ar, 2), "yellow_px_in_row": r["yellow_sum"], "verified_visually": True}})
    print(f"{tc:8.2f} -> frame {kf:6d}  t={kf/FPS:9.3f}s  (yellow +{r['yellow_frame']-kf}f)  icon white={r['icon_white']} flash={r['icon_flash']}  audio x{ar:5.1f}  y={r['row_y']}  ysum={r['yellow_sum']}")

kills.sort(key=lambda k: k["kill_frame"])

# ---- sequences (same round bursts): gap <= 30s; rounds are >= ~40s apart ----
SEQ_GAP = 30.0
seqs, cur = [], []
for k in kills:
    if cur and k["kill_time"] - cur[-1]["kill_time"] > SEQ_GAP:
        seqs.append(cur); cur = []
    cur.append(k)
seqs.append(cur)
LABEL = {1: "single", 2: "double", 3: "triple", 4: "quadra", 5: "ACE"}
for si, s in enumerate(seqs, 1):
    for i, k in enumerate(s, 1):
        k["sequence"] = si; k["index_in_sequence"] = i; k["sequence_size"] = len(s); k["sequence_label"] = LABEL.get(len(s), f"{len(s)}K")
        k["gap_from_prev_kill_s"] = round(k["kill_time"] - s[i - 2]["kill_time"], 2) if i > 1 else None
for i, k in enumerate(kills, 1):
    k["id"] = i

data = {"video": VIDEO, "fps": 60, "cfr": True, "frame_count": N, "player": PLAYER,
        "detection": ("own killfeed row (yellow outline on the player's block + teal fill, tracked at 60fps) confirmed by the centre-bottom kill icon, "
                      "game-audio hi-band bump, and visual verification on full-res crops. Assists (yellow on small icons) and other players' kills excluded."),
        "total_kills": len(kills), "kills": kills,
        "sequences": [{"sequence": i + 1, "kills": len(s), "label": LABEL.get(len(s), f"{len(s)}K"), "start": s[0]["kill_time"], "end": s[-1]["kill_time"],
                       "span_s": round(s[-1]["kill_time"] - s[0]["kill_time"], 2), "kill_ids": [k["id"] for k in s]} for i, s in enumerate(seqs)]}
json.dump(data, open("kills.json", "w"), indent=1)
print(f"\n{len(kills)} kills, {len(seqs)} sequences -> kills.json")
for s in data["sequences"]:
    print(f"  seq {s['sequence']:2d} {s['label']:7s} {s['start']:8.2f}s -> {s['end']:8.2f}s  (span {s['span_s']}s)  ids {s['kill_ids']}")
