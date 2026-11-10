"""Times when a game subtitle is on screen (bright low-saturation pixels in the bottom band).
usage: sub_scan.py a b   -> prints runs [start, end] and saves scan/subs.json"""
import json, subprocess, sys
import numpy as np
V = json.load(open("montage.json"))["video"]
a, b = float(sys.argv[1]), float(sys.argv[2])
FPS, W, H = 10, 800, 110
p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(a), "-t", str(b - a), "-i", V,
                      "-vf", f"fps={FPS},crop=800:110:560:935", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
vals = []
while True:
    raw = p.stdout.read(W * H * 3)
    if len(raw) < W * H * 3: break
    im = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(int)
    white = (im.min(axis=2) > 200) & (im.max(axis=2) - im.min(axis=2) < 30)
    vals.append(int(white.sum()))
vals = np.array(vals); on = vals > 150
runs, s = [], None
for i, o in enumerate(on):
    t = a + i / FPS
    if o and s is None: s = t
    if not o and s is not None:
        if t - s >= 0.5: runs.append([round(s, 1), round(t, 1)])
        s = None
if s is not None: runs.append([round(s, 1), round(b, 1)])
for r in runs: print(r)
json.dump(runs, open(f"scan/subs_{a:.0f}.json", "w"))
