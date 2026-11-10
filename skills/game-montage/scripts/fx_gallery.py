"""Render one short silent demo clip per preset in fx_catalog.py, so presets can be picked by eye (catalog page).
    py -3.14 fx_gallery.py --video <recording> --kill <frame> --kill2 <frame> --out <folder> [--only shake_1,whip_2]
Effects + speed styles play on kill --kill; transitions cut from --kill to --kill2; text styles sit on --kill2.
Writes <out>/fx/<preset>.mp4 (360x640, 30 fps) and <out>/catalog.json (name, group, Indonesian description, settings).
Run it from any scratch folder; it needs no audio and no edl.json.
"""
import argparse, copy, json, os, subprocess, sys, time
import numpy as np

import fx_catalog as C
from render import Renderer

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--kill", type=int, required=True, help="source frame (60 fps) of the kill used for effect / speed demos")
ap.add_argument("--kill2", type=int, required=True, help="source frame of a second kill (transition target, text demos)")
ap.add_argument("--out", required=True)
ap.add_argument("--only", default="")
ap.add_argument("--bpm", type=float, default=152.0)
a = ap.parse_args()
P = 60.0 / a.bpm
only = set(x for x in a.only.split(",") if x)
os.makedirs(os.path.join(a.out, "fx"), exist_ok=True)

BASE = {
    "project": {"video": a.video},
    "song": {"beat_period": P, "window_beats": 5},
    "grade": {"contrast": 1.06, "brightness": 0.025, "saturation": 1.20, "gamma": 1.04, "sharpen": 0.6, "vignette_angle": "PI/8"},
    "render": {"slowmo_interp": "flow"}, "fades": {"video_in": 0.0, "video_out": 0.0}, "texts": [],
}


def clip(frame, bs, bk, be, speed="std", effects=(), trans=None, intensity=1.5, push=0.05):
    c = {"id": "g", "kill_id": 0, "src_kill_frame": frame, "beats": {"start": bs, "kill": bk, "end": be}, "crop_x": 960,
         "speed": {"preset": speed}, "push_in": push, "intensity": intensity, "effects": [{"preset": e} for e in effects]}
    if trans:
        c["transition_out"] = {"preset": trans}
    return c


def render(name, edl):
    edl = C.expand(copy.deepcopy(edl))
    for i, c in enumerate(edl["clips"]):
        c["id"] = f"c{i + 1:02d}"
    out = os.path.join(a.out, "fx", f"{name}.mp4")
    r = Renderer(edl, "preview", out)
    enc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{r.W}x{r.H}", "-r", "30",
                            "-i", "-", "-vf", f"eq=contrast={BASE['grade']['contrast']}:saturation={BASE['grade']['saturation']}:gamma={BASE['grade']['gamma']},"
                            "scale=360:640:flags=bicubic,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-an",
                            "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for n in range(r.total):
        enc.stdin.write(r.frame(n).tobytes())
    enc.stdin.close(); enc.wait()
    return out


jobs = []
for name in C.EFFECTS:
    e = dict(BASE, song={"beat_period": P, "window_beats": 5}, clips=[clip(a.kill, 0, 2, 5, effects=[name])])
    jobs.append((name, "efek", C.EFFECT_INFO.get(name, ""), C.EFFECTS[name], e))
for name in C.TRANSITIONS:
    e = dict(BASE, song={"beat_period": P, "window_beats": 6},
             clips=[clip(a.kill, 0, 1.5, 3, effects=["zoom_1"], trans=name), clip(a.kill2, 3, 4.5, 6, effects=["zoom_1"])])
    jobs.append((name, "transisi", C.TRANSITION_INFO.get(name, ""), C.TRANSITIONS[name], e))
for name in C.SPEED:
    e = dict(BASE, song={"beat_period": P, "window_beats": 7}, clips=[clip(a.kill, 0, 4, 7, speed=name, effects=["zoom_1"])])
    jobs.append((name, "speed", C.SPEED_INFO.get(name, ""), C.SPEED[name], e))
SAMPLE = {"word_pop": "BANG", "word_float": "BANG", "counter": "x7", "badge": "HEADSHOT", "caption": "contoh caption"}
for name in C.TEXTS:
    e = dict(BASE, song={"beat_period": P, "window_beats": 5}, clips=[clip(a.kill2, 0, 1, 5, speed="real")],
             texts=[{"preset": name, "text": SAMPLE.get(name, "TEKS"), "beat": 1.0, "dur": 3.2}])
    jobs.append((name, "teks", C.TEXT_INFO.get(name, ""), C.TEXTS[name], e))

cat_path = os.path.join(a.out, "catalog.json")
catalog = {j["name"]: j for j in json.load(open(cat_path, encoding="utf-8"))} if os.path.exists(cat_path) else {}
t0 = time.time()
for i, (name, group, info, settings, e) in enumerate(jobs, 1):
    if only and name not in only:
        continue
    render(name, e)
    catalog[name] = {"name": name, "group": group, "info": info, "settings": settings, "file": f"fx/{name}.mp4"}
    print(f"[{i}/{len(jobs)}] {group:8s} {name:14s} {time.time() - t0:6.0f}s", flush=True)
order = [j[0] for j in jobs]
json.dump([catalog[n] for n in order if n in catalog], open(cat_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("catalog ->", cat_path)
