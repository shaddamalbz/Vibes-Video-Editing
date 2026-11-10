"""Verification contact sheets: union of all candidate sources, one tile per candidate (killfeed crop + centre skull crop)."""
import json, os, subprocess, sys
import numpy as np, cv2

from kitcfg import VIDEO                      # montage.json in the work folder
ev = json.load(open("scan/events60.json"))
coarse = json.load(open("scan/coarse_events.json"))
d = np.load("scan/feat60.npz")
rd = d["skull"][:, 2].astype(int); wh = d["skull"][:, 0].astype(int)

cands = []   # (time, source)
for k in ev["kills"]:
    cands.append((k["kill_time"], "row"))
# skull red-flash groups (short flash, decent magnitude)
fl = np.where(rd >= 1200)[0]
groups = []
for f in fl:
    if not groups or f - groups[-1][-1] > 30:
        groups.append([f])
    else:
        groups[-1].append(f)
for g in groups:
    if len(g) <= 12 and 1300 <= rd[g].max() <= 3800:
        cands.append((g[0] / 60.0 - 0.15, "flash"))
for k in coarse["kills"]:
    cands.append((k["t"] - 0.1, "coarse"))
cands.sort()
merged = []
for t, s in cands:
    if merged and t - merged[-1]["t"] < 1.6:
        merged[-1]["src"].add(s)
        continue
    merged.append({"t": t, "src": {s}})
print(len(merged), "merged candidates")
json.dump([{"t": m["t"], "src": sorted(m["src"])} for m in merged], open("scan/candidates.json", "w"), indent=1)


def grab(t, crop, out):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", VIDEO, "-frames:v", "1",
                    "-vf", crop, out], check=True)


tiles = []
for i, m in enumerate(merged):
    t = max(m["t"], 0)
    grab(t + 0.45, "crop=560:250:1360:80", "probe/_kf.png")
    grab(t + 0.10, "crop=300:250:810:720", "probe/_sk.png")
    a = cv2.imread("probe/_kf.png"); b = cv2.imread("probe/_sk.png")
    tile = np.hstack([a, b])
    lab = f"#{i+1}  {t:8.2f}s  {'+'.join(sorted(m['src']))}"
    cv2.rectangle(tile, (0, 0), (560, 22), (0, 0, 0), -1)
    cv2.putText(tile, lab, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    tiles.append(tile)

PER = 12
for si in range(0, len(tiles), PER):
    chunk = tiles[si:si + PER]
    while len(chunk) % 2:
        chunk.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(chunk[r:r + 2]) for r in range(0, len(chunk), 2)]
    os.makedirs("probe", exist_ok=True)
    cv2.imwrite(f"probe/verify_{si // PER + 1}.png", np.vstack(rows))
print("sheets:", (len(tiles) + PER - 1) // PER)
