"""Split the game sound of the used source ranges into "no music" (sound effects + voices) and "music" with Demucs (htdemucs).
The FF XVI recording carries its battle score; under the meme song the two musics clashed and every cut made the score jump.

usage (from the work folder): split_music.py a1-b1 a2-b2 ...      (source seconds)
writes
  scan/nomusic.flac : vocals + drums + percussive(other) + percussive(bass) on a compact timeline (sample 0 = source OFF0 s),
                      silence outside the ranges; clips use it with "game_audio": "scan/nomusic.flac", "game_audio_offset": OFF0
  scan/music.flac   : harmonic(other) + harmonic(bass) + harmonic(vocals) (the score without hits), same timeline, for continuous beds
All ranges go through Demucs in ONE run (concatenated with 1 s gaps). CPU: about 2 x real time.
"""
import os, subprocess, sys
import numpy as np, soundfile as sf, librosa

OFF0 = 6900.0
SR = 48000
GAME = "scan/game_audio_st48.wav"
ranges = sorted(tuple(map(float, a.split("-"))) for a in sys.argv[1:])
merged = []
for a, b in ranges:                                     # merge overlaps
    if merged and a <= merged[-1][1] + 0.5:
        merged[-1][1] = max(merged[-1][1], b)
    else:
        merged.append([a, b])
gap = np.zeros((SR, 2), np.float32)
parts, index, pos = [], [], 0
for a, b in merged:
    y, _ = sf.read(GAME, start=int(a * SR), frames=int((b - a) * SR), dtype="float32", always_2d=True)
    parts += [y, gap]
    index.append((a, b, pos))
    pos += len(y) + len(gap)
os.makedirs("sep", exist_ok=True)
cat = np.concatenate(parts)
sf.write("sep/ranges.wav", cat, SR, subtype="FLOAT")
print(f"{len(merged)} ranges, {len(cat) / SR:.1f} s of audio -> demucs")
stems = os.path.join("sep", "htdemucs", "ranges")
subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "-o", "sep", "sep/ranges.wav"], check=True)


def load(name):
    y, sr = sf.read(os.path.join(stems, name + ".wav"), dtype="float32", always_2d=True)
    if sr != SR:
        y = np.stack([librosa.resample(y[:, c], orig_sr=sr, target_sr=SR) for c in range(2)], 1)
    n = len(cat)
    return y[:n] if len(y) >= n else np.vstack([y, np.zeros((n - len(y), 2), np.float32)])


def hp(x, margin=2.0):
    out_h, out_p = [], []
    for c in range(2):
        S = librosa.stft(x[:, c])
        H, P = librosa.decompose.hpss(S, margin=margin)
        out_h.append(librosa.istft(H, length=len(x)))
        out_p.append(librosa.istft(P, length=len(x)))
    return np.stack(out_h, 1), np.stack(out_p, 1)


d, b, o, v = load("drums"), load("bass"), load("other"), load("vocals")
oh, op = hp(o)
bh, bp = hp(b)
vh, vp = hp(v, 1.0)
nomusic = v + d + 0.9 * op + 0.7 * bp
music = oh + bh + 0.6 * vh
end = max(b_ for _, b_, _ in index) + 2
for name, sig in (("nomusic", nomusic), ("music", music)):
    full = np.zeros((int((end - OFF0) * SR), 2), np.float32)
    for a, b_, p in index:
        n = int((b_ - a) * SR)
        i = int((a - OFF0) * SR)
        seg = sig[p:p + n].copy()
        f = int(0.02 * SR)
        seg[:f] *= np.linspace(0, 1, f)[:, None]
        seg[-f:] *= np.linspace(1, 0, f)[:, None]
        full[i:i + n] = seg
    sf.write(f"scan/{name}.flac", np.clip(full, -1, 1), SR, subtype="PCM_16")
    print(f"wrote scan/{name}.flac (offset {OFF0} s)")
