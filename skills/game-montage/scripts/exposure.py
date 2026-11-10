"""Exposure match between clips: measure each clip's average brightness over the source range it actually shows,
then write a gentle per-clip gamma (`exposure_gamma`) into edl.json so dark rounds and bright rounds sit closer together.
Run after make_edl.py (make_edl.py rewrites edl.json without these values)."""
import json, math, subprocess
import numpy as np, cv2
from edl_lib import load_edl, timeline
from timemap import TimeMap

edl = load_edl()
fps = 60
P = edl["song"]["beat_period"]
tl, _ = timeline(edl, fps)
V = edl["project"]["video"]


def sample(t, crop_x, V=V, full=False):
    x0 = int(min(max(crop_x - 304, 0), 1920 - 608))
    vf = "scale=152:270" if full else f"crop=608:1080:{x0}:0,scale=152:270"   # wide clips: the whole frame (squashed; only the mean matters)
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", V, "-frames:v", "1",
                        "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    g = np.frombuffer(p.stdout, np.uint8)
    if g.size < 152 * 270:
        return None
    g = g[:152 * 270].reshape(270, 152)
    return g[int(270 * 0.06):int(270 * 0.86)].mean() / 255.0     # ignore the HUD strips at the top and bottom


means = {}
for c in tl:
    tm = TimeMap(c["speed"], (c["n_k"] - c["n_s"]) / fps, (c["n_e"] - c["n_k"]) / fps, P)
    tk = c["src_kill_frame"] / 60.0
    lo, hi = tk + tm.offset(-(c["n_k"] - c["n_s"]) / fps), tk + tm.offset((c["n_e"] - c["n_k"]) / fps)
    vals = [v for v in (sample(t, c.get("crop_x", 960), c.get("video", V), c.get("wide") is not None) for t in np.linspace(lo, hi, 5)) if v is not None]
    means[c["id"]] = float(np.mean(vals))

target = float(np.median([means[c["id"]] for c in tl if not c.get("calm")]))
print(f"target mean luma {target:.3f}")
for c in edl["clips"]:
    m = means[c["id"]]
    g = math.log(target) / math.log(max(m, 1e-3))
    g = min(max(g, 0.80), 1.25)
    strength = 0.4 if c.get("calm") else (0.7 if g < 1 else 0.35)       # brighten dark rounds more than we darken bright ones (white smoke must stay white)
    g = 1 + strength * (g - 1)
    c["exposure_mean"] = round(m, 3)
    c["exposure_gamma"] = round(g, 3)
    print(f"  {c['id']} {'calm ' if c.get('calm') else 'kill#%-3s' % c['kill_id']}  mean {m:.3f}  -> gamma {g:.3f}")
json.dump(edl, open("edl.json", "w"), indent=1)
print("exposure_gamma written to edl.json")
