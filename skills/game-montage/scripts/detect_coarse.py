"""Kill detection stage A: coarse (5fps) scan of the killfeed crop for the player's yellow row marker.
Yellow diamond at LEFT end of a teal row  = the player killed someone (kill)
Yellow diamond at RIGHT end of a red row  = the player was killed     (death)
Markers are tracked across frames (a real row lives ~5s); flickering yellow scenery is rejected by
(1) row-body colour next to the blob, (2) minimum track lifetime.
"""
import json
import numpy as np, cv2

FPS = 5
kf = np.memmap("scan/kf.raw", dtype=np.uint8, mode="r").reshape(-1, 120, 160, 3)
N = len(kf)
PITCH = 13  # row pitch at 1/3 scale (~39 px @1080p)
MIN_TRACK_FRAMES = 6


def candidates(frame):
    f = np.ascontiguousarray(frame[:80])
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = ((H >= 15) & (H <= 35) & (S > 110) & (V > 150)).astype(np.uint8)
    if m.sum() > 700:
        return []
    teal = ((H >= 70) & (H <= 105) & (S > 50) & (V > 80))
    red = (((H <= 10) | (H >= 170)) & (S > 90) & (V > 110))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for k in range(1, n):
        x, y, w, h, a = st[k]
        if not (20 <= a <= 110 and 5 <= w <= 20 and 6 <= h <= 13):
            continue
        cx, cy = int(round(cen[k][0])), int(round(cen[k][1]))
        y0, y1 = max(cy - 2, 0), cy + 9
        # kill: yellow at killer end (left), teal body to its right; death: yellow at victim end (right), red body to its left
        tr_ = teal[y0:y1, min(cx + 10, 159):min(cx + 90, 160)]
        rr_ = red[y0:y1, min(cx + 10, 159):min(cx + 90, 160)]
        tl_ = teal[y0:y1, max(cx - 90, 0):max(cx - 10, 0)]
        rl_ = red[y0:y1, max(cx - 90, 0):max(cx - 10, 0)]
        tf = tr_.mean() if tr_.size else 0
        rf_right = rr_.mean() if rr_.size else 0
        rf = rl_.mean() if rl_.size else 0
        tf_left = tl_.mean() if tl_.size else 0
        if cx < 125 and tf > 0.18 and tf > rf_right:
            out.append(("kill", cx, cy, int(a)))
        elif cx > 125 and rf > 0.18 and rf > tf_left:
            out.append(("death", cx, cy, int(a)))
    return out


tracks = []  # dicts: side,x,y,first,last,n
for i in range(N):
    for side, cx, cy, a in candidates(kf[i]):
        best = None
        for tr in tracks:
            if tr["side"] != side or i - tr["last"] > 2 or abs(cx - tr["x"]) > 3:
                continue
            for k in range(0, 6):
                if abs(cy - (tr["y"] - k * PITCH)) <= 3:
                    best = tr
                    break
            if best:
                break
        if best:
            best["last"] = i
            best["n"] += 1
            best["y"] = cy
            best["x"] = cx
        else:
            tracks.append({"side": side, "x": cx, "y": cy, "y0": cy, "first": i, "last": i, "n": 1})

good = [t for t in tracks if t["n"] >= MIN_TRACK_FRAMES]
kills = sorted([t for t in good if t["side"] == "kill"], key=lambda t: t["first"])
deaths = sorted([t for t in good if t["side"] == "death"], key=lambda t: t["first"])
print(f"tracks {len(tracks)} kept {len(good)}  kills {len(kills)}  deaths {len(deaths)}")
ev = lambda ts: [{"t": t["first"] / FPS, "frame5": t["first"], "dur": (t["last"] - t["first"] + 1) / FPS, "x": t["x"], "y0": t["y0"]} for t in ts]
json.dump({"kills": ev(kills), "deaths": ev(deaths)}, open("scan/coarse_events.json", "w"), indent=1)
print("kills :", [round(t["first"] / FPS, 1) for t in kills])
print("deaths:", [round(t["first"] / FPS, 1) for t in deaths])

print("\nALL tracks (side t_first n_frames x y0):")
for t in sorted(tracks, key=lambda t: t["first"]):
    print(f"  {t['side']:5s} {t['first']/FPS:7.1f}s n={t['n']:3d} last={t['last']/FPS:7.1f}s x={t['x']:3d} y0={t['y0']:3d} {'KEPT' if t['n']>=MIN_TRACK_FRAMES else ''}")
