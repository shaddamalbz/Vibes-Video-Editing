"""Shared EDL helpers: beat -> seconds -> output frame for a given fps.
HERE = the montage work folder (the current directory, or MONTAGE_DIR): edl.json, scan/, brand/ and the outputs live there,
the scripts themselves live in the skill folder."""
import json
import os

from fx_catalog import expand

HERE = os.path.abspath(os.environ.get("MONTAGE_DIR", os.getcwd()))


def load_edl(path=None):
    """load edl.json and resolve named presets (fx_catalog.py)"""
    return expand(json.load(open(path or os.path.join(HERE, "edl.json"), encoding="utf-8")))


def timeline(edl, fps):
    """Resolve every clip to output-frame boundaries. Cuts and the kill frame are rounded to the nearest output frame,
    so the kill-vs-beat error is at most half an output frame."""
    P = edl["song"]["beat_period"]
    out = []
    for c in edl["clips"]:
        b = c["beats"]
        ts, tk, te = b["start"] * P, b["kill"] * P, b["end"] * P
        n_s, n_k, n_e = round(ts * fps), round(tk * fps), round(te * fps)
        out.append(dict(c, t_s=ts, t_k=tk, t_e=te, n_s=n_s, n_k=n_k, n_e=n_e,
                        kill_err_frames=(n_k / fps - tk) * fps))
    total = round(edl["song"]["window_beats"] * P * fps)
    return out, total
