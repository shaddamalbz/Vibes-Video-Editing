"""Sheet of the right-side HUD action log (source x 1380-1920, y 400-700) shortly after each time, to read which ability was used.
usage: hud_log.py out.jpg [delay] t1 t2 ...   (delay in s after each time, default 0.6)"""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
out = sys.argv[1]
args = sys.argv[2:]
delay = 0.6
if args and args[0].startswith("d="):
    delay = float(args[0][2:]); args = args[1:]
ts = [float(a) for a in args]
X0, Y0, CW, CH = 1380, 400, 540, 300
COLS = 4


def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + delay:.3f}", "-i", V, "-frames:v", "1", "-vf", f"crop={CW}:{CH}:{X0}:{Y0}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:CW * CH * 3], np.uint8).reshape(CH, CW, 3).copy()


with ThreadPoolExecutor(12) as ex:
    frames = list(ex.map(grab, ts))
rows = (len(ts) + COLS - 1) // COLS
grid = np.zeros((rows * CH, COLS * CW, 3), np.uint8)
for i, (t, im) in enumerate(zip(ts, frames)):
    cv2.putText(im, f"{t:.2f}", (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(im, f"{t:.2f}", (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    r, c = divmod(i, COLS)
    grid[r * CH:(r + 1) * CH, c * CW:(c + 1) * CW] = im
cv2.imwrite(out, grid, [cv2.IMWRITE_JPEG_QUALITY, 90])
print(out)
