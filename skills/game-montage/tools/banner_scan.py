"""Find the boss attack-name banners (top centre, e.g. "Glacier Strike" with a red underline) over a source range.
Groups consecutive banner frames into events and writes one crop per event to a sheet.
usage: banner_scan.py <start_s> <end_s> [fps]"""
import json, subprocess, sys
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
a, b = float(sys.argv[1]), float(sys.argv[2])
fps = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
X0, Y0, CW, CH = 660, 185, 600, 60                     # banner text y~200-225, red underline y~232
raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", V,
                      "-vf", f"fps={fps:g},crop={CW}:{CH}:{X0}:{Y0}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                     capture_output=True).stdout
n = len(raw) // (CW * CH * 3)
fr = np.frombuffer(raw[:n * CW * CH * 3], np.uint8).reshape(n, CH, CW, 3)
ev, cur = [], None
for i in range(n):
    g = cv2.cvtColor(fr[i], cv2.COLOR_BGR2GRAY).astype(np.int16)
    best = 0.0
    for y in range(38, 54):                                  # thin bright underline: brighter than 4 rows above and below
        ln = g[y:y + 2].max(0) - np.maximum(g[y - 4], g[min(y + 5, CH - 1)])
        best = max(best, float((ln[250:350] > 30).mean()))
    txt = cv2.Canny(g[8:42].astype(np.uint8), 100, 220).mean()
    hit = best > 0.55 and txt > 4
    t = a + i / fps
    if hit:
        if cur and t - cur[1] <= 1.5 / fps + 0.01:
            cur[1] = t
            if txt > cur[3]:
                cur[2], cur[3] = i, txt
        else:
            cur = [t, t, i, txt]
            ev.append(cur)
print(len(ev), "banner events")
rows = []
for s, e, i, _ in ev:
    im = fr[i].copy()
    lab = f"{s:.1f}-{e:.1f}"
    im = cv2.copyMakeBorder(im, 0, 0, 160, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    cv2.putText(im, lab, (4, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    rows.append(im)
    print(f"  {s:8.1f} -> {e:8.1f}")
if rows:
    per = 24
    for k in range(0, len(rows), per):
        chunk = rows[k:k + per]
        half = (len(chunk) + 1) // 2
        left = np.vstack(chunk[:half])
        right = np.vstack(chunk[half:] + [np.zeros_like(chunk[0])] * (half - len(chunk[half:])))
        cv2.imwrite(f"sheets/banners_{k // per}.jpg", np.hstack([left, right]))
