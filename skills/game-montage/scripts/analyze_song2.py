"""Tempo candidates for a new song (prints half/double-time aware fits; then run analyze_song.py with the best BPM).
Generic song analysis: tempo candidates (half/double aware), constant-grid fit, downbeat phase, bar energy, drop candidates -> beats.json"""
import json, sys
import librosa, numpy as np, scipy.ndimage as ndi, scipy.signal as sps

SONG = sys.argv[1] if len(sys.argv) > 1 else "bang_bang.wav"
OUT = sys.argv[2] if len(sys.argv) > 2 else "beats_new.json"
SR, HOP = 44100, 256
y, sr = librosa.load(SONG, sr=SR, mono=True)
dur = len(y) / sr
fps_env = sr / HOP
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
low = S[freqs < 120].sum(0); rms = librosa.feature.rms(S=S, frame_length=2048, hop_length=HOP)[0]
n = min(len(oenv), len(low), len(rms)); oenv, low, rms = oenv[:n], low[:n], rms[:n]
t_env = np.arange(n) / fps_env
low_on = np.maximum(np.diff(ndi.gaussian_filter1d(low, 1), prepend=0), 0)
env = ndi.gaussian_filter1d(oenv / oenv.max() + 0.7 * low_on / low_on.max(), 1.5)

# 1) tempo candidates from onset autocorrelation + librosa estimate
ac = librosa.autocorrelate(oenv - oenv.mean(), max_size=int(3 * fps_env)); ac /= ac[0]
lags = np.arange(len(ac)) / fps_env
pk, _ = sps.find_peaks(ac, height=0.05, distance=int(0.04 * fps_env))
cands = sorted([(ac[i], 60 / lags[i]) for i in pk if 60 <= 60 / lags[i] <= 220], reverse=True)[:8]
print("autocorr tempo candidates (strength, BPM):", [(round(float(a), 2), round(float(b), 1)) for a, b in cands])
t0 = float(np.atleast_1d(librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=HOP)[0])[0])
print("librosa tempo:", round(t0, 2))

def grid_score(P, off):
    ts = np.arange(off, t_env[-1], P); idx = np.clip(np.round(ts * fps_env).astype(int), 0, n - 1); return env[idx].mean()

def fit(bpm0):
    P0 = 60 / bpm0; best = (0, P0, 0)
    for P in np.linspace(P0 * 0.985, P0 * 1.015, 151):
        for off in np.arange(0, P, 0.004):
            s = grid_score(P, off)
            if s > best[0]: best = (s, P, off)
    _, P, off = best
    for P2 in np.linspace(P - 0.0004, P + 0.0004, 61):
        for off2 in np.arange(off - 0.006, off + 0.006, 0.0005):
            s = grid_score(P2, off2)
            if s > best[0]: best = (s, P2, off2)
    return best

res = {}
for b in sorted({round(c[1]) for c in cands[:4]} | {round(t0), round(t0 / 2), round(t0 * 2)}):
    if 60 <= b <= 200:
        s, P, off = fit(b); res[b] = (s, P, off); print(f"  fit {b:3d} BPM -> {60/P:8.3f} BPM offset {off:.3f} score {s:.4f}")
json.dump({str(k): list(map(float, v)) for k, v in res.items()}, open("scan/tempo_fits.json", "w"))
