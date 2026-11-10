"""Self-check of a rendered montage: ffprobe, kill-vs-beat (frames), brightness/duplicate-frame sanity, audio loudness."""
import json, subprocess, sys, os
import numpy as np, cv2

mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
vid = sys.argv[2] if len(sys.argv) > 2 else ("preview_v1.mp4" if mode == "preview" else "final.mp4")
rep = json.load(open(f"render_report_{mode}.json"))
import projcfg
projcfg.use_tools()
from probe import probe   # ffprobe stand-in (works with ffmpeg builds that ship no ffprobe)
p = probe(vid, frames=True)
v = next(s for s in p["streams"] if s["codec_type"] == "video"); a = next(s for s in p["streams"] if s["codec_type"] == "audio")
print(f"{vid}: {v['width']}x{v['height']} {v['r_frame_rate']} fps, {v['nb_frames']} frames, {float(p['format']['duration']):.3f}s, video {v['codec_name']} audio {a['codec_name']}")
errs = [c["kill_vs_beat_frames"] for c in rep["clips"] if not c.get("calm")]
print(f"kill vs beat: max |diff| {max(abs(e) for e in errs):.3f} frame, mean |diff| {np.mean(np.abs(errs)):.3f} frame over {len(errs)} kills  -> {'OK' if max(abs(e) for e in errs) < 1 else 'FAIL'}")
print(f"audio: {rep['audio_lufs']} LUFS, true peak {rep['audio_true_peak']} dBFS")
cap = cv2.VideoCapture(vid); prev = None; lum = []; diffs = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    g = cv2.cvtColor(cv2.resize(f, (135, 240)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    lum.append(g.mean())
    if prev is not None:
        diffs.append(np.abs(g - prev).mean())
    prev = g
lum = np.array(lum); diffs = np.array(diffs)
fade = 8
mid = lum[fade:-fade]
print(f"brightness: mean {lum.mean():.1f}, min inside (excl. fades) {mid.min():.1f}, max {lum.max():.1f}")
dups = np.where(diffs < 0.05)[0]
print(f"near-identical consecutive frames: {len(dups)} {list(dups[:12])}")
print(f"decoded frames {len(lum)} (expected {rep['frames']})")
