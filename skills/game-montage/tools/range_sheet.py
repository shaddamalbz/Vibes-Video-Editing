"""Compact sheet of several labelled source ranges: one row block per range, frames every <step> s.
usage: range_sheet.py out.jpg step name=a-b name=a-b ..."""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
out, step = sys.argv[1], float(sys.argv[2])
W, H, COLS = 256, 144, 10
blocks = []
for a in sys.argv[3:]:
    name, r = a.split("=")
    lo, hi = map(float, r.split("-"))
    blocks.append((name, list(np.arange(lo, hi + 1e-6, step))))


def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", V, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3).copy()


allts = [t for _, ts in blocks for t in ts]
with ThreadPoolExecutor(12) as ex:
    frames = dict(zip(allts, ex.map(grab, allts)))
rows = []
for name, ts in blocks:
    cells = []
    for t in ts:
        im = frames[t].copy()
        cv2.putText(im, f"{name} {t:.1f}", (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
        cv2.putText(im, f"{name} {t:.1f}", (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
        cells.append(im)
    while len(cells) % COLS:
        cells.append(np.zeros((H, W, 3), np.uint8))
    for k in range(0, len(cells), COLS):
        rows.append(np.hstack(cells[k:k + COLS]))
    rows.append(np.full((6, W * COLS, 3), 255, np.uint8))
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
print(out, len(rows))
