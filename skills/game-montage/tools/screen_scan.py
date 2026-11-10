"""Find full-screen states over a source range: GAME OVER (text template), the death bubbles screen (dark teal, no HUD) and the
Eikon-feather loading screen (dark with a bright orange centre). Groups consecutive hits into events.
usage: screen_scan.py <start_s> <end_s> [fps]"""
import json, subprocess, sys
import numpy as np, cv2

V = json.load(open("montage.json"))["video"]
a, b = float(sys.argv[1]), float(sys.argv[2])
fps = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
W, H = 480, 270
ref = cv2.resize(cv2.imread("frames/gameover_8276.png", cv2.IMREAD_GRAYSCALE), (W, H), interpolation=cv2.INTER_AREA)
tpl = ref[110:130, 165:315]                                  # the "GAME OVER" letters

raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", V, "-vf", f"fps={fps:g},scale={W}:{H}",
                      "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
n = len(raw) // (W * H * 3)
fr = np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3)
states = []
for i in range(n):
    im = fr[i]
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    go = cv2.minMaxLoc(cv2.matchTemplate(g[95:145, 140:340], tpl, cv2.TM_CCOEFF_NORMED))[1]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    mean = im.reshape(-1, 3).mean(0)
    centre = im[95:175, 200:280].reshape(-1, 3).mean(0)
    orange = centre[2] > 150 and centre[2] > centre[0] + 60 and mean.mean() < 70
    if go > 0.6:
        s = "GAMEOVER"
    elif orange:
        s = "LOADING"
    elif mean.mean() < 45 and mean[1] > mean[2] + 8:
        s = "TEAL"
    else:
        s = "-"
    states.append(s)
ev = []
for i, s in enumerate(states):
    t = a + i / fps
    if s == "-":
        continue
    if ev and ev[-1][0] == s and t - ev[-1][2] <= 2.0 / fps + 0.01:
        ev[-1][2] = t
    else:
        ev.append([s, t, t])
for s, t0, t1 in ev:
    if t1 - t0 >= 0.4 or s == "GAMEOVER":
        h0, m0 = divmod(int(t0), 3600)
        print(f"{s:9s} {t0:8.1f} -> {t1:8.1f}  ({h0}:{m0 // 60:02d}:{m0 % 60:02d})  {t1 - t0:5.1f}s")
