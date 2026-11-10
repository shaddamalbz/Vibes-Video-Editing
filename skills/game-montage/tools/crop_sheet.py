"""One frame per anchor with source-x grid lines (every 240 px) to pick crop_x.  usage: crop_sheet.py out.jpg t1 t2 ...  (t may be 'id=t')"""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
W, H, COLS = 480, 270, 4
out, args = sys.argv[1], sys.argv[2:]
items = [(a.split("=")[0], float(a.split("=")[1])) if "=" in a else (a, float(a)) for a in args]


def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", V, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3).copy()


with ThreadPoolExecutor(12) as ex:
    frames = list(ex.map(grab, [t for _, t in items]))
rows = (len(items) + COLS - 1) // COLS
grid = np.zeros((rows * H, COLS * W, 3), np.uint8)
for i, ((name, t), im) in enumerate(zip(items, frames)):
    for sx in range(240, 1920, 240):
        x = sx * W // 1920
        cv2.line(im, (x, 0), (x, H), (0, 255, 255) if sx % 480 == 0 else (0, 160, 160), 1)
        if sx % 480 == 0:
            cv2.putText(im, str(sx), (x + 2, H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    cv2.putText(im, f"{name} {t:.2f}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
    cv2.putText(im, f"{name} {t:.2f}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    r, c = divmod(i, COLS)
    grid[r * H:(r + 1) * H, c * W:(c + 1) * W] = im
cv2.imwrite(out, grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
print(out)
