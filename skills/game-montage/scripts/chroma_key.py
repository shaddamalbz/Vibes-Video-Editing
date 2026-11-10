"""Key a green/blue-screen clip (e.g. an anime dancer) into RGBA PNG frames for the "overlays" layer of render.py.
The key colour is sampled from the frame corners; alpha is a soft ramp on "how much the pixel is the key colour"
(key channel minus the larger other channel), then green spill on the edges is pulled back (G <= max(R, B)).
Every frame is cropped to the union bounding box of the subject, so the layer only moves the character.

  py chroma_key.py <video> <out_dir> [--start s] [--end s] [--soft 30] [--hard 90] [--max_h 1080]
Writes out_dir/000000.png ... and out_dir/meta.json {fps, w, h, frames, src, start, end, key}."""
import argparse, json, os, subprocess, sys
import numpy as np, cv2

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("out")
ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--end", type=float, default=None)
ap.add_argument("--soft", type=float, default=30, help="key strength where alpha starts to drop (0-255 scale)")
ap.add_argument("--hard", type=float, default=90, help="key strength where alpha is 0")
ap.add_argument("--max_h", type=int, default=1080)
a = ap.parse_args()

import projcfg
projcfg.use_tools()
from probe import probe   # ffprobe stand-in (works with ffmpeg builds that ship no ffprobe)
info = probe(a.video)
info["streams"] = [s for s in info["streams"] if s["codec_type"] == "video"]
W, H = info["streams"][0]["width"], info["streams"][0]["height"]
num, den = map(int, info["streams"][0]["r_frame_rate"].split("/"))
fps = num / den
end = a.end if a.end is not None else float(info["format"]["duration"])
s = min(1.0, a.max_h / H)
w, h = int(round(W * s / 2) * 2), int(round(H * s / 2) * 2)
p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{a.start:.3f}", "-to", f"{end:.3f}", "-i", a.video,
                    "-vf", f"scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w, 3)

# key colour: median of the four corner patches over a few frames
k = max(4, h // 40)
patch = np.concatenate([f[:k, :k].reshape(-1, 3) for f in fr[::max(1, len(fr) // 8)]] +
                       [f[:k, -k:].reshape(-1, 3) for f in fr[::max(1, len(fr) // 8)]])
key = np.median(patch, 0)                               # BGR
kc = int(np.argmax(key))                                # 1 = green, 0 = blue
others = [c for c in range(3) if c != kc]
print(f"{len(fr)} frames {w}x{h} @ {fps:.2f} fps, key BGR {key.astype(int).tolist()} ({'green' if kc == 1 else 'blue' if kc == 0 else 'red'})")


def rgba(f):
    f32 = f.astype(np.float32)
    strength = f32[..., kc] - np.maximum(f32[..., others[0]], f32[..., others[1]])
    alpha = np.clip(1.0 - (strength - a.soft) / (a.hard - a.soft), 0.0, 1.0)
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    out = f32.copy()
    cap = np.maximum(f32[..., others[0]], f32[..., others[1]])
    out[..., kc] = np.minimum(f32[..., kc], cap)       # spill suppression
    return np.dstack([out, alpha * 255.0]).clip(0, 255).astype(np.uint8)


frames = [rgba(f) for f in fr]
mask = np.zeros((h, w), bool)
for f in frames:
    mask |= f[..., 3] > 24
# thin border lines of the source (full-height columns / full-width rows that are never the key colour) are not the subject
bad_c = mask.sum(0) > 0.98 * h
bad_r = mask.sum(1) > 0.98 * w
if bad_c.any() or bad_r.any():
    for f in frames:
        f[:, bad_c, 3] = 0
        f[bad_r, :, 3] = 0
    mask[:, bad_c] = False
    mask[bad_r, :] = False
    print(f"cleared {int(bad_c.sum())} border columns, {int(bad_r.sum())} border rows")
ys, xs = np.where(mask)
pad = 4
y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
os.makedirs(a.out, exist_ok=True)
for i, f in enumerate(frames):
    cv2.imwrite(os.path.join(a.out, f"{i:06d}.png"), f[y0:y1, x0:x1])
cxs = []
for f in frames[::10]:                                   # where the body is inside the box (arms reaching out widen the box)
    al = f[y0:y1, x0:x1, 3].astype(np.float32)
    cxs.append((al.sum(0) * np.arange(al.shape[1])).sum() / max(al.sum(), 1) / al.shape[1])
meta = {"fps": fps, "w": int(x1 - x0), "h": int(y1 - y0), "frames": len(frames), "src": a.video, "start": a.start, "end": end,
        "body_cx": round(float(np.median(cxs)), 3),
        "key_bgr": key.astype(int).tolist(), "touches_bottom": bool(y1 >= h - 1), "crop": [int(x0), int(y0), int(x1), int(y1)]}
json.dump(meta, open(os.path.join(a.out, "meta.json"), "w"), indent=1)
print(f"-> {a.out}: {len(frames)} RGBA frames {x1 - x0}x{y1 - y0} (subject box), touches bottom: {meta['touches_bottom']}")
