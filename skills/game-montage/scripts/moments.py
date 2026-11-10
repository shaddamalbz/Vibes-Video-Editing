"""Find impact moments in games without a killfeed (FF XVI etc.): brightness jumps + loud game-audio onsets.

usage (from the work folder):
  moments.py scan <start_s> <end_s>          tiny 64x36 luma track of that source range (scan/luma_<start>.raw) + game audio (scan/game_audio_st48.wav)
  moments.py peaks [--top 40] [--gap 1.0]     strongest impact candidates in the scanned range, sorted by time
  moments.py find <t1> <t2> ...               exact impact frame near rough times (biggest flash / loudest onset within +-1 s)
Then check every candidate on a contact sheet: anchor_sheet.py sheets/x.jpg t1 t2 ...
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf
from kitcfg import VIDEO, HERE

SCAN = os.path.join(HERE, "scan")
META = os.path.join(SCAN, "moments.json")
GAME = os.path.join(SCAN, "game_audio_st48.wav")
FPS, LW, LH = 60.0, 64, 36


def ensure_game_audio():
    if not os.path.exists(GAME):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", VIDEO, "-vn", "-ac", "2", "-ar", "48000", GAME], check=True)


def scan(t0, t1):
    os.makedirs(SCAN, exist_ok=True)
    ensure_game_audio()
    out = os.path.join(SCAN, f"luma_{int(t0)}.raw")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", VIDEO, "-vf", f"fps={FPS:g},scale={LW}:{LH},format=gray",
                    "-f", "rawvideo", out], check=True)
    json.dump({"t0": t0, "t1": t1, "luma": out}, open(META, "w"))
    print(f"scanned {t0:.1f}-{t1:.1f}s -> {out}")


def tracks():
    m = json.load(open(META))
    T0 = m["t0"]
    lum = np.fromfile(m["luma"], np.uint8).reshape(-1, LH, LW).astype(np.float32).mean((1, 2))
    rise = np.concatenate([[0, 0], lum[2:] - lum[:-2]])
    y, sr = sf.read(GAME, dtype="float32", always_2d=True)
    y = y.mean(1)
    hop = sr // 100                                   # 10 ms
    n = len(y) // hop
    db = 20 * np.log10(np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12))
    on = np.concatenate([[0] * 3, db[3:] - db[:-3]])  # 30 ms rise
    return T0, m["t1"], lum, rise, db, on


def find(times):
    T0, _, lum, rise, db, on = tracks()
    for m in times:
        lo, hi = max(int((m - 1.0 - T0) * FPS), 0), int((m + 1.0 - T0) * FPS)
        i = lo + int(np.argmax(rise[lo:hi]))
        a0, a1 = int((m - 1.0) * 100), int((m + 1.0) * 100)
        loud = np.where(db[a0:a1] > db[a0:a1].max() - 6, on[a0:a1], -99)
        j = a0 + int(np.argmax(loud))
        print(f"{m:7.2f}: flash {T0 + i / FPS:7.3f}s (+{rise[i]:5.1f} luma, level {lum[i]:5.1f})   audio onset {j / 100:7.2f}s (+{on[j]:4.1f} dB, {db[j]:5.1f} dBFS)")


def peaks(top, gap):
    T0, T1, lum, rise, db, on = tracks()
    t_v = T0 + np.arange(len(rise)) / FPS
    a = np.interp(t_v, np.arange(len(on)) / 100, np.maximum(on, 0)) * np.interp(t_v, np.arange(len(db)) / 100, (db > np.percentile(db, 60)).astype(float))
    score = np.maximum(rise, 0) / (rise.std() + 1e-6) + a / (a.std() + 1e-6)
    picked = []
    for i in np.argsort(-score):
        if all(abs(t_v[i] - t_v[j]) >= gap for j in picked):
            picked.append(i)
        if len(picked) >= top:
            break
    for i in sorted(picked):
        print(f"{t_v[i]:7.2f}s  score {score[i]:5.1f}  flash +{rise[i]:5.1f}  level {lum[i]:5.1f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scan":
        scan(float(sys.argv[2]), float(sys.argv[3]))
    elif cmd == "find":
        find([float(a) for a in sys.argv[2:]])
    elif cmd == "peaks":
        args = sys.argv[2:]
        top = int(args[args.index("--top") + 1]) if "--top" in args else 40
        gap = float(args[args.index("--gap") + 1]) if "--gap" in args else 1.0
        peaks(top, gap)
    else:
        print(__doc__)
