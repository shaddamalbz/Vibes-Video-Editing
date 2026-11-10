"""Step 1: song analysis -> beats.json
Constant-tempo grid fit around a BPM guess (get candidates from analyze_song2.py; librosa's own tracker often lands on double-time),
downbeat phase from section-change alignment, beat-synchronous energy, drop candidates.
"""
import json

import librosa
import numpy as np
import scipy.ndimage as ndi
import scipy.signal as sps

import sys
SONG = sys.argv[1]                                  # usage: analyze_song.py song.wav <bpm guess> beats.json
BPM0 = float(sys.argv[2])
OUT = sys.argv[3] if len(sys.argv) > 3 else "beats.json"
SR, HOP = 44100, 256
y, sr = librosa.load(SONG, sr=SR, mono=True)
dur = len(y) / sr
fps_env = sr / HOP

S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
low = S[freqs < 120].sum(axis=0)
rms = librosa.feature.rms(S=S, frame_length=2048, hop_length=HOP)[0]
n = min(len(oenv), len(low), len(rms))
oenv, low, rms = oenv[:n], low[:n], rms[:n]
t_env = np.arange(n) / fps_env

# low-band *onsets* (kick attacks), not level
low_on = np.maximum(np.diff(ndi.gaussian_filter1d(low, 1), prepend=0), 0)
env = ndi.gaussian_filter1d(oenv / oenv.max() + 0.7 * low_on / low_on.max(), 1.5)


def grid_score(P, off):
    ts = np.arange(off, t_env[-1], P)
    idx = np.clip(np.round(ts * fps_env).astype(int), 0, n - 1)
    return env[idx].mean()


# coarse -> fine constant-grid fit around BPM0
P0 = 60 / BPM0
best = (0, P0, 0)
for P in np.linspace(P0 * 0.99, P0 * 1.01, 201):
    for off in np.arange(0, P, 0.003):
        s = grid_score(P, off)
        if s > best[0]:
            best = (s, P, off)
_, P, off = best
for P2 in np.linspace(P - 0.0004, P + 0.0004, 81):
    for off2 in np.arange(off - 0.006, off + 0.006, 0.0005):
        s = grid_score(P2, off2)
        if s > best[0]:
            best = (s, P2, off2)
_, P, off = best
bpm = 60 / P
print(f"constant grid: {bpm:.4f} BPM  period {P:.5f}s  offset {off:.4f}s  score {best[0]:.4f}")

# beats over the whole song (beat 0 at the first grid point >= 0)
nb = int((dur - off) / P) + 1
beats = off + P * np.arange(nb)
# realized onset lag: median distance between each beat and the local onset peak (informational)
lags = []
for b in beats:
    lo, hi = np.searchsorted(t_env, [b - 0.05, b + 0.05])
    if hi > lo + 2:
        lags.append(t_env[lo + int(np.argmax(env[lo:hi]))] - b)
print(f"median onset-vs-grid lag {np.median(lags)*1000:.1f} ms (std {np.std(lags)*1000:.1f} ms)")

# ---- beat-synchronous energy ----
def seg(a, b, arr):
    i, j = np.searchsorted(t_env, [a, b])
    return arr[i:max(j, i + 1)]

beat_rms = np.array([seg(b, b + P, rms).mean() for b in beats])
beat_low = np.array([seg(b, b + P, low).mean() for b in beats])
beat_flux = np.array([seg(b, b + P, oenv).mean() for b in beats])
nrm = lambda v: (v - v.min()) / (v.max() - v.min() + 1e-9)
beat_energy = 0.4 * nrm(beat_rms) + 0.4 * nrm(beat_low) + 0.2 * nrm(beat_flux)

# ---- downbeat phase: section changes should land on bar starts (4/4). Vote by big beat-to-beat-block energy jumps ----
blk = 4
jumps = []
for i in range(blk, len(beats) - blk):
    d = beat_energy[i:i + blk].mean() - beat_energy[i - blk:i].mean()
    jumps.append((i, d))
big = [i for i, d in sorted(jumps, key=lambda x: -abs(x[1]))[:30]]
votes = np.bincount([i % 4 for i in big], minlength=4)
# tie-break with kick strength on the beat
kick = np.array([seg(b - 0.02, b + 0.08, low_on).max() for b in beats])
phase_kick = np.array([kick[p::4].mean() for p in range(4)])
phase = int(np.argmax(votes * 10 + phase_kick / phase_kick.max()))
print("downbeat votes by phase", votes.tolist(), "kick strength by phase", np.round(phase_kick / phase_kick.max(), 2).tolist(), "-> phase", phase)
downbeats = beats[phase::4]
bar_len = 4 * P

# ---- bars & drop detection (4-beat bars) ----
bars = []
for bi, st in enumerate(downbeats):
    en = st + bar_len
    if en > dur:
        break
    first_beat = int(round((st - off) / P))
    bars.append({
        "bar": bi, "start": float(st), "end": float(en), "first_beat": first_beat,
        "energy": float(beat_energy[first_beat:first_beat + 4].mean()),
        "low": float(beat_low[first_beat:first_beat + 4].mean()),
    })
E = np.array([b["energy"] for b in bars])
L = nrm(np.array([b["low"] for b in bars]))
cands = []
for i in range(1, len(bars) - 1):
    before = E[max(0, i - 2):i].mean()
    after = E[i:i + 2].mean()
    jump = E[i] - E[i - 1]
    sustain = after - before
    lowj = L[i] - L[max(0, i - 2):i].mean()
    score = 0.4 * jump + 0.4 * sustain + 0.2 * lowj
    cands.append({"bar": i, "t": bars[i]["start"], "beat": bars[i]["first_beat"], "score": float(score),
                  "jump": float(jump), "sustain": float(sustain), "low_jump": float(lowj),
                  "energy_before": float(before), "energy_after": float(after)})
cands.sort(key=lambda c: -c["score"])
top = []
for c in cands:
    if all(abs(c["t"] - o["t"]) > 8 for o in top):
        top.append(c)
    if len(top) == 5:
        break

# ---- strong onsets ----
pk, _ = sps.find_peaks(oenv, height=np.percentile(oenv, 92), distance=int(0.06 * fps_env))
onsets = [{"t": float(t_env[i]), "strength": float(oenv[i])} for i in pk]

print("\nbars (4 beats = %.3fs):" % bar_len)
for b in bars:
    print(f"  bar {b['bar']:3d}  {b['start']:7.2f}s  beat {b['first_beat']:4d}  {b['energy']:.2f} " + "#" * int(b["energy"] * 40))
print("\ndrop candidates:")
for c in top:
    print(f"  bar {c['bar']:3d} @ {c['t']:7.2f}s (beat {c['beat']})  score {c['score']:.3f}  before {c['energy_before']:.2f} -> after {c['energy_after']:.2f}  lowjump {c['low_jump']:.2f}")

out = {
    "song": SONG, "duration": float(dur),
    "bpm": float(bpm), "constant_tempo": True, "beat_period": float(P), "grid_offset": float(off),
    "onset_vs_grid_lag_ms": {"median": float(np.median(lags) * 1000), "std": float(np.std(lags) * 1000)},
    "note": f"constant-tempo grid fitted around {BPM0} BPM on the onset + kick envelope",
    "beats": [float(x) for x in beats],
    "eighths": [float(off + P / 2 * k) for k in range(int((dur - off) / (P / 2)) + 1)],
    "downbeat_phase": phase, "downbeats": [float(x) for x in downbeats],
    "beat_energy": [float(x) for x in beat_energy],
    "onsets": onsets, "bars": bars, "drop_candidates": top,
}
with open(OUT, "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote beats.json")
