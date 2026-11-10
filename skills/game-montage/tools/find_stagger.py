"""Find the "Stagger Damage" label in a source range (multi-scale edge template from the Timekeeper frame 5850.5).
usage: find_stagger.py <start_s> <end_s> [fps]
"""
import json, subprocess, sys
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
a, b = float(sys.argv[1]), float(sys.argv[2])
fps = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
X0, Y0, CW, CH = 640, 170, 640, 150
ref = cv2.imread("frames/f_5850.5.png", cv2.IMREAD_GRAYSCALE)
base = ref[238:266, 845:1078]
tpls = [cv2.Canny(cv2.resize(base, None, fx=s, fy=s), 80, 200) for s in (0.9, 1.0, 1.15, 1.3)]

raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", V,
                      "-vf", f"fps={fps:g},crop={CW}:{CH}:{X0}:{Y0},format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
n = len(raw) // (CW * CH)
fr = np.frombuffer(raw[:n * CW * CH], np.uint8).reshape(n, CH, CW)
for i in range(n):
    e = cv2.Canny(fr[i], 80, 200)
    mx, loc = max((cv2.minMaxLoc(cv2.matchTemplate(e, t, cv2.TM_CCOEFF_NORMED))[1::2] for t in tpls), key=lambda r: r[0])
    t = a + i / fps
    if mx > 0.1:
        print(f"{t:8.2f}s  {int(t)//3600}:{int(t)%3600//60:02d}:{t%60:05.2f}  match {mx:.2f}  at x={loc[0]+X0} y={loc[1]+Y0}")
print("frames", n)
