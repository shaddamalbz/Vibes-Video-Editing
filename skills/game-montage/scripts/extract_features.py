"""Kill detection stage B: full 60fps pass. Per frame we keep tiny feature vectors (not the pixels):
  skull region (80x100 @ 920,800 full-res, centre-bottom kill icon): white / teal / red pixel counts
  killfeed region (520x240 @ 1400,80 -> half-res 260x120): per-y-row counts of teal, red, yellow-left, yellow-right
Output: scan/feat60.npz
"""
import subprocess, sys, time
import numpy as np, cv2

from kitcfg import VIDEO                      # montage.json in the work folder
import projcfg
W, H = 260, 220
FRAME = W * H * 3
CHUNK = 300

vf = ("[0:v]split=2[a][b];"
      "[a]crop=520:240:1400:80,scale=260:120:flags=area[kf];"
      "[b]crop=80:100:920:800,pad=260:100:0:0:black[sk];"
      "[kf][sk]vstack=inputs=2[o]")
cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *projcfg.hwaccel(), "-i", VIDEO,
       "-filter_complex", vf, "-map", "[o]", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1 << 27)

skull = []   # (white, teal, red)
teal_y, red_y, yl_y, yr_y = [], [], [], []
n = 0
t0 = time.time()
while True:
    buf = proc.stdout.read(FRAME * CHUNK)
    if not buf:
        break
    k = len(buf) // FRAME
    arr = np.frombuffer(buf[:k * FRAME], np.uint8).reshape(k, H, W, 3)
    for j in range(k):
        f = arr[j]
        kf, sk = f[:120], f[120:, :80]
        hs = cv2.cvtColor(sk, cv2.COLOR_BGR2HSV)
        h_, s_, v_ = hs[..., 0], hs[..., 1], hs[..., 2]
        skull.append((int(((s_ < 45) & (v_ > 215)).sum()),
                      int(((h_ >= 75) & (h_ <= 100) & (s_ > 80) & (v_ > 120)).sum()),
                      int((((h_ <= 8) | (h_ >= 172)) & (s_ > 150) & (v_ > 150)).sum())))
        hk = cv2.cvtColor(kf, cv2.COLOR_BGR2HSV)
        H2, S2, V2 = hk[..., 0], hk[..., 1], hk[..., 2]
        teal = (H2 >= 75) & (H2 <= 100) & (S2 > 80) & (V2 > 120)
        red = ((H2 <= 8) | (H2 >= 172)) & (S2 > 110) & (V2 > 120)
        yel = (H2 >= 15) & (H2 <= 35) & (S2 > 110) & (V2 > 150)
        teal_y.append(teal.sum(1).astype(np.uint16))
        red_y.append(red.sum(1).astype(np.uint16))
        yl_y.append(yel[:, :100].sum(1).astype(np.uint16))
        yr_y.append(yel[:, 100:].sum(1).astype(np.uint16))
    n += k
    if (n // CHUNK) % 40 == 0:
        print(f"{n} frames  {n/60:7.1f}s of video  {time.time()-t0:5.0f}s elapsed", flush=True)
proc.wait()
np.savez_compressed("scan/feat60.npz", skull=np.array(skull, np.uint16), teal_y=np.array(teal_y), red_y=np.array(red_y),
                    yl_y=np.array(yl_y), yr_y=np.array(yr_y))
print("done", n, "frames", f"{time.time()-t0:.0f}s")
