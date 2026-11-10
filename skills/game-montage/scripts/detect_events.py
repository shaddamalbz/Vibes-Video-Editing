"""Kill detection stage C: turn 60fps features into frame-accurate own-kill events.

The player's own killfeed rows carry a yellow outline on the killer/victim block. In the half-res killfeed crop that shows up
as a contiguous band of ~10-17 y-rows with 30-260 yellow pixels. We track those bands through time (a row lives ~5s and shifts UP
as older rows expire), classify by row body colour (teal = we killed, red = we died), and refine the onset:
  row onset  = the frame the row's fill pops in (teal jump in that band), just before the yellow outline
  skull onset = centre-bottom kill icon starts (white blob appears)
kill frame = earliest of the two confirmations.
"""
import json
import numpy as np, soundfile as sf, librosa

FPS = 60.0
d = np.load("scan/feat60.npz")
skull = d["skull"].astype(np.int32)          # white, teal, red
teal_y = d["teal_y"].astype(np.int32)        # (N,120)
red_y = d["red_y"].astype(np.int32)
yel = d["yl_y"].astype(np.int32) + d["yr_y"].astype(np.int32)
N = len(skull)
print("frames", N, f"{N/FPS:.1f}s")

ON = 2          # y-row counts as yellow if >= this many yellow px
MIN_RUN = 9     # contiguous y-rows
SUM_LO, SUM_HI = 30, 300
PITCH = 19.5


WIN = 15
csum = np.concatenate([np.zeros((N, 1), np.int32), np.cumsum(yel, axis=1)], axis=1)      # (N,121)
cnt_on = np.concatenate([np.zeros((N, 1), np.int32), np.cumsum(yel >= 2, axis=1)], axis=1)


def bands(f):
    """Fixed-height windows (WIN rows) over the yellow y-profile; robust to scene-yellow noise touching the band."""
    ssum = csum[f, WIN:] - csum[f, :-WIN]                    # (121-WIN,) sum in window starting at y
    con = cnt_on[f, WIN:] - cnt_on[f, :-WIN]                 # rows with yellow in window
    ok = np.where((ssum >= SUM_LO) & (ssum <= SUM_HI) & (con >= 10))[0]
    out, used = [], -99
    # greedy: take best window in each cluster
    i = 0
    while i < len(ok):
        j = i
        while j + 1 < len(ok) and ok[j + 1] - ok[j] <= 2:
            j += 1
        cl = ok[i:j + 1]
        y0 = int(cl[np.argmax(ssum[cl])])
        out.append((y0, y0 + WIN))
        i = j + 1
    return out


tracks, active = [], []
for f in range(N):
    for (y0, y1) in bands(f):
        hit = None
        for ti in active:
            tr = tracks[ti]
            if f - tr["last"] > 12:
                continue
            ssum = int(yel[f, y0:y1].sum())
            if ssum > 1.6 * tr["sum"] + 25:      # sudden surge = a different, newly appeared row
                continue
            for k in range(0, 6):
                if abs(y0 - (tr["y0"] - k * PITCH)) <= 3.5:
                    hit = ti
                    break
            if hit is not None:
                break
        ssum = int(yel[f, y0:y1].sum())
        if hit is not None:
            tr = tracks[hit]
            tr["last"] = f; tr["y0"] = y0; tr["y1"] = y1; tr["n"] += 1; tr["sum"] = ssum
        else:
            tracks.append({"first": f, "last": f, "y0": y0, "y1": y1, "ystart": y0, "n": 1, "sum": ssum})
            active.append(len(tracks) - 1)
    if f % 50 == 0:
        active = [ti for ti in active if f - tracks[ti]["last"] <= 12]

print("raw band tracks:", len(tracks))
MIN_N = 60  # >= 1.25 s of evidence
good = [t for t in tracks if t["n"] >= MIN_N and (t["last"] - t["first"]) <= 60 * 7.5]
print(f"kept (>= {MIN_N} frames, life <= 7.5s):", len(good))

events = []
for tr in good:
    fs = tr["first"] + 6
    a, b = max(int(tr["ystart"]) - 1, 0), min(int(tr["ystart"]) + 17, 120)
    t = int(teal_y[fs:fs + 30, a:b].sum()); r = int(red_y[fs:fs + 30, a:b].sum())
    ratio = t / (r + 1.0)
    if t + r < 8000:
        continue                       # overlay noise (network stats box etc.), not a killfeed row
    kind = "kill" if ratio >= 0.6 else ("death" if ratio <= 0.5 else "ambiguous")
    series = (teal_y if kind == "kill" else red_y)[:, a:b].sum(1)
    fy = tr["first"]
    lo = max(fy - 15, 12)
    base = np.median(series[lo - 10:lo])
    settled = np.median(series[fy + 4:fy + 14])
    thr = base + 0.5 * max(settled - base, 1)
    onset = fy
    for f in range(fy, lo - 1, -1):
        if series[f] >= thr:
            onset = f
        else:
            break
    events.append({"kind": kind, "yellow_frame": int(fy), "row_onset": int(onset), "y0": int(tr["ystart"]), "n": tr["n"],
                   "life": (tr["last"] - tr["first"] + 1) / FPS, "teal": t, "red": r, "ratio": round(ratio, 2), "jump": int(settled - base)})

# ---- skull onset (white kill-icon blob appearing after >=20 quiet frames) ----
w = skull[:, 0]
run_max = np.maximum.accumulate  # placeholder to keep numpy import used clearly
skull_events = []
for f in range(20, N):
    if w[f] >= 250 and w[f - 20:f].max() < 90:
        if not skull_events or f - skull_events[-1] > 30:
            skull_events.append(f)
print("skull onsets:", len(skull_events))

# ---- audio cue score: 6-11 kHz bump near the kill (informational) ----
y, sr = sf.read("scan/game_audio.wav")
hop = 110
S = np.abs(librosa.stft(y, n_fft=512, hop_length=hop))
fr = librosa.fft_frequencies(sr=sr, n_fft=512)
hi = S[fr >= 6000].sum(0)
t_a = np.arange(len(hi)) * hop / sr


def audio_score(t):
    i0, i1 = np.searchsorted(t_a, [t - 0.06, t + 0.12])
    b0, b1 = np.searchsorted(t_a, [t - 1.5, t - 0.3])
    base = np.median(hi[b0:b1]) + 1e-6
    return float(hi[i0:i1].max() / base)


kills, deaths = [], []
for e in sorted(events, key=lambda e: e["row_onset"]):
    if e["kind"] == "death":
        deaths.append({**e, "death_time": e["row_onset"] / FPS})
        continue
    if e["kind"] == "ambiguous":
        print("  ambiguous row at", round(e["row_onset"] / FPS, 2), "ratio", e["ratio"])
        continue
    fo = e["row_onset"]
    cand = [s for s in skull_events if fo - 8 <= s <= fo + 10]
    e["skull_onset"] = int(min(cand, key=lambda s: abs(s - fo))) if cand else None
    anchor = fo if e["skull_onset"] is None else min(fo, e["skull_onset"])
    e["kill_frame"] = int(anchor); e["kill_time"] = anchor / FPS
    e["audio_ratio"] = audio_score(e["kill_time"])
    conf = 0.55 + (0.30 if e["skull_onset"] is not None else 0) + (0.15 if e["audio_ratio"] > 1.6 else (0.07 if e["audio_ratio"] > 1.25 else 0))
    e["confidence"] = round(conf, 2)
    kills.append(e)

json.dump({"kills": kills, "deaths": deaths, "skull_onsets": skull_events}, open("scan/events60.json", "w"), indent=1)
print(f"\nKILLS ({len(kills)}):")
for k in kills:
    print(f"  t={k['kill_time']:8.3f}s ratio={k['ratio']:4.2f} f={k['kill_frame']:6d} row_onset={k['row_onset']} skull={k['skull_onset']} yellow={k['yellow_frame']} life={k['life']:.1f}s jump={k['jump']:5d} audio x{k['audio_ratio']:5.1f} conf={k['confidence']}")
print(f"\nDEATHS ({len(deaths)}):")
for k in deaths:
    print(f"  t={k['death_time']:8.3f}s life={k['life']:.1f}s")
unmatched = [s for s in skull_events if not any(abs(s - k['kill_frame']) <= 12 for k in kills)]
print(f"\nskull onsets without own-kill row: {len(unmatched)}")
