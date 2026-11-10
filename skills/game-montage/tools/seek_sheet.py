"""Overview contact sheets of a long recording by seeking (one ffmpeg per frame, in parallel).
usage: seek_sheet.py <step_s> [start] [end] [tag]
"""
import subprocess, sys, json, os
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
step = float(sys.argv[1])
a = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
b = float(sys.argv[3]) if len(sys.argv) > 3 else 11132.0
tag = sys.argv[4] if len(sys.argv) > 4 else "ov"
W, H, COLS, ROWS = 320, 180, 8, 8
os.makedirs("sheets", exist_ok=True)


def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", V, "-frames:v", "1",
                          "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    if len(raw) < W * H * 3:
        return np.zeros((H, W, 3), np.uint8)
    return np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3).copy()


ts = list(np.arange(a, b, step))
with ThreadPoolExecutor(12) as ex:
    frames = list(ex.map(grab, ts))
per = COLS * ROWS
for s in range(0, len(ts), per):
    grid = np.zeros((ROWS * H, COLS * W, 3), np.uint8)
    for i, (t, im) in enumerate(zip(ts[s:s + per], frames[s:s + per])):
        h, m = divmod(int(t), 3600)
        cv2.putText(im, f"{h}:{m // 60:02d}:{m % 60:02d}", (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(im, f"{h}:{m // 60:02d}:{m % 60:02d}", (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        r, c = divmod(i, COLS)
        grid[r * H:(r + 1) * H, c * W:(c + 1) * W] = im
    out = f"sheets/{tag}_{a:.0f}_{s // per:02d}.jpg"
    cv2.imwrite(out, grid, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(out)
