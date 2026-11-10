"""Music-free game sound for games whose recording carries their own soundtrack (FF XVI battle music clashes with the song).

usage (from the work folder):  game_sfx.py <start_s> <end_s>
Separates that source range with Demucs (htdemucs) and keeps only the hits: drums + 0.9 x percussive(other) + 0.5 x percussive(vocals)
(HPSS margin 2 strips the sustained music). Writes scan/game_sfx_st48.wav on the full recording timeline (silence outside the range);
use it with "audio": {"game_file": "scan/game_sfx_st48.wav", "bed": {"on": true, "rel_db": -5}}.
Demucs on CPU takes a few minutes for ~3 minutes of fight.
"""
import os, subprocess, sys
import numpy as np, soundfile as sf, librosa
from kitcfg import VIDEO, HERE

t0, t1 = float(sys.argv[1]), float(sys.argv[2])
scan, sep = os.path.join(HERE, "scan"), os.path.join(HERE, "sep")
os.makedirs(scan, exist_ok=True)
name = f"fight_{int(t0)}"
seg = os.path.join(scan, name + ".wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", VIDEO, "-vn", "-ac", "2", "-ar", "44100", seg], check=True)
stems = os.path.join(sep, "htdemucs", name)
if not os.path.exists(os.path.join(stems, "drums.wav")):
    subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "-o", sep, seg], check=True)


def perc(x, sr):
    return np.stack([librosa.istft(librosa.decompose.hpss(librosa.stft(x[:, ch]), margin=2.0)[1], length=len(x)) for ch in range(x.shape[1])], 1)


d, sr = sf.read(os.path.join(stems, "drums.wav"), dtype="float32", always_2d=True)
o, _ = sf.read(os.path.join(stems, "other.wav"), dtype="float32", always_2d=True)
v, _ = sf.read(os.path.join(stems, "vocals.wav"), dtype="float32", always_2d=True)
sfx = d + 0.9 * perc(o, sr) + 0.5 * perc(v, sr)
sfx48 = np.stack([librosa.resample(sfx[:, ch], orig_sr=sr, target_sr=48000) for ch in range(2)], 1)
full = np.zeros((int(round(t0 * 48000)) + len(sfx48), 2), np.float32)
full[int(round(t0 * 48000)):] = sfx48
out = os.path.join(scan, "game_sfx_st48.wav")
sf.write(out, full, 48000, subtype="FLOAT")
print(f"wrote {out}: {t0:.1f}-{t1:.1f}s of music-free game sound")
