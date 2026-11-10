"""Contact sheet: one row per anchor time, frames at offsets around it.  usage: anchor_sheet.py out.jpg t1 t2 ..."""
import subprocess, sys, json
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
OFFS = [-0.5, -0.25, 0.0, 0.25, 0.5]
W, H = 320, 180
out, ts = sys.argv[1], [float(a) for a in sys.argv[2:]]
rows = []
for t in ts:
    cells = []
    for o in OFFS:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + o:.3f}", "-i", V, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
        im = np.frombuffer(p.stdout, np.uint8)[:W * H * 3].reshape(H, W, 3).copy()
        cv2.putText(im, f"{t + o:.2f}" + (" *" if o == 0 else ""), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cells.append(im)
    rows.append(np.hstack(cells))
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
