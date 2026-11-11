"""Timeline builder for edits made of source spans laid end to end (long-form cuts, story Shorts): the layer under longlib.py and shortlib.py.

A sequence is a list of items laid end to end (output seconds, beat_period 1.0):
  Run(cid, src, s0, s1, fx=[(src_t, preset|dict)], accents=[(src_t, speed)], note, gain_db, **clip_extras)
      real-speed source span, split at slow-mo accents (speed = slow(...) etc.); game sound = the source, crossfaded at every cut
  Hold(cid, src, t, dur, note, fx=[(rel_s, preset|dict)], ring=0.0, gain_db, **clip_extras)
      freeze frame of source t for dur s (ring > 0: the source sound keeps playing into the freeze for `ring` s, then fades)
  Gap(dur)  leaves time with no clip (e.g. a title over black; the previous clip is extended over it)
Build(seq, video, t0=0.0) -> object with
  .clips            edl.json clips (reference/edl.md), .end = output length, .marks[cid] = (out start, out end), .runs = the audio spans
  .at(src, t)       output time of source time t of recording src
  .clip(cid)        the clip dict of an item
  .game_track(audio, path, end, xf=0.12, fade_last=0.0)   writes the game sound of the whole timeline (48 kHz PCM_24), returns its peak in dB
`src` is a recording tag. `video` / `audio` are tag -> file mappings: pass VIDEO / AUDIO from this module (they read the work folder's
recordings.json through tools/reclib.py, nothing is resolved until a tag is looked up), or plain dicts.

Recording helpers (all read recordings.json, found by walking up from the current directory):
  VIDEO[tag], AUDIO[tag]     the recording's video file / its 48 kHz game audio (scan/<tag>_audio.flac from ingest.py)
  pick(tag=None)             the tag itself, or the only recording when there is exactly one; a clear message otherwise
  read(src, a, b)            float32 stereo game audio of recording src from a to b seconds
  quiet(src, t, win=0.5)     the quietest 40 ms within t +- win (cut between words, not inside one)

    import sys; sys.path.insert(0, "<skill>/scripts")
    from seqlib import Run, Hold, Build, VIDEO, AUDIO, slow
    b = Build([Run("a", "W", 100.0, 108.0), Run("b", "W", 300.0, 306.0, accents=[(303.2, slow())], fx=[(303.2, "shake_3")])], VIDEO)
    peak = b.game_track(AUDIO, "game_track.wav", b.end)     # then put b.clips into an edl.json
"""
import numpy as np, soundfile as sf

import projcfg
from timemap import TimeMap

SR = 48000
REAL = {"keys": [[-900, 1.0], [900, 1.0]]}


def slow(f=0.45, pre=0.25, hold=0.8, ramp=0.3):
    """real speed -> slow-mo f from `pre` s before the impact to `hold` s after it -> real speed (output seconds)"""
    return {"keys": [[-900, 1.0], [-(pre + ramp), 1.0], [-pre, f], [hold, f], [hold + ramp, 1.0], [900, 1.0]]}


def freeze_at(t):
    return {"keys": [[-900, 1.0], [t, 1.0], [t + 0.01, 0.02], [900, 0.02]]}


SLOW = slow()
SLOW_BIG = slow(0.35, 0.3, 1.2, 0.35)


# ---------------------------------------------------------------- recordings (recordings.json through tools/reclib.py)
def _reclib():
    projcfg.use_tools()
    import reclib
    return reclib


class _RecMap:
    """tag -> file of that recording, read from recordings.json when a tag is looked up"""
    def __init__(self, kind):
        self.kind = kind

    def __getitem__(self, tag):
        return getattr(_reclib(), self.kind)(pick(tag))

    def __contains__(self, tag):
        return tag in _reclib().tags()

    def __iter__(self):
        return iter(_reclib().tags())

    def keys(self):
        return _reclib().tags()

    def __repr__(self):
        return f"<{self.kind} of the recordings in recordings.json>"


VIDEO = _RecMap("video")
AUDIO = _RecMap("audio")


def pick(tag=None):
    """the recording tag to use: `tag` when given (it must be in recordings.json), else the only recording of the work folder"""
    rl = _reclib()
    tags = rl.tags()
    where = rl.rec()["file"]
    if not tags:
        raise SystemExit(f"no recordings: {'no recordings.json at or above ' + rl.rec()['dir'] if not where else where + ' lists none'}. "
                         'Run tools/ingest.py on the recording, or write recordings.json: {"recordings": {"A": {"video": "<file>"}}}')
    if tag is None:
        if len(tags) > 1:
            raise SystemExit(f"{where} has {len(tags)} recordings ({', '.join(tags)}): say which one, e.g. Long(\"{tags[0]}\")")
        return tags[0]
    if tag not in tags:
        raise SystemExit(f'recording "{tag}" is not in {where} (known: {", ".join(tags)}); add it with tools/ingest.py')
    return tag


def read(src, a, b, f=None):
    """game audio of recording src from a to b seconds (float32, 2-D); f = another audio file to read instead"""
    y, _ = sf.read(f or AUDIO[src], start=max(0, int(a * SR)), frames=max(1, int((b - a) * SR)), dtype="float32", always_2d=True)
    return y


def quiet(src, t, win=0.5):
    """the quietest 40 ms of game audio within t +- win (cut between words, not inside one)"""
    y = read(src, t - win, t + win).mean(1)
    hop = int(0.02 * SR)
    n = len(y) // hop
    e = np.convolve(np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1)), np.ones(2) / 2, "same")
    return round(t - win + (int(np.argmin(e)) + 0.5) * hop / SR, 3)


# ---------------------------------------------------------------- timeline
class Run:
    def __init__(self, cid, src, s0, s1, fx=(), accents=(), note="", gain_db=0.0, **extra):
        self.cid, self.src, self.s0, self.s1, self.fx, self.accents, self.note, self.gain_db, self.extra = \
            cid, src, s0, s1, list(fx), list(accents), note, gain_db, extra


class Hold:
    def __init__(self, cid, src, t, dur, note="", fx=(), ring=0.0, gain_db=0.0, **extra):
        self.cid, self.src, self.t, self.dur, self.note, self.fx, self.ring, self.gain_db, self.extra = \
            cid, src, t, dur, note, list(fx), ring, gain_db, extra


class Gap:
    def __init__(self, dur, cid="gap"):
        self.dur, self.cid = dur, cid


class Build:
    def __init__(self, seq, video, t0=0.0):
        self.clips, self.runs, self.marks = [], [], {}
        o = t0
        for it in seq:
            if isinstance(it, Gap):
                self.marks[it.cid] = (o, o + it.dur)
                if self.clips:
                    self.clips[-1]["beats"]["end"] = round(o + it.dur, 4)
                o += it.dur
                continue
            if isinstance(it, Hold):
                tq = round(it.t * 60) / 60.0
                c = {"id": it.cid, "note": it.note, "kill_id": len(self.clips), "src_kill_frame": round(tq * 60), "section": "hold",
                     "video": video[it.src], "beats": {"start": round(o, 4), "kill": round(o, 4), "end": round(o + it.dur, 4)},
                     "speed": freeze_at(0.0), "push_in": 0.0, "intensity": 1.0,
                     "effects": [({**p, "at": round(r, 3)} if isinstance(p, dict) else {"preset": p, "at": round(r, 3)}) for r, p in it.fx],
                     "hit": False, "bed_gain": 0.0, "transition_out": {"preset": "cut"}, **it.extra}
                self.clips.append(c)
                self.marks[it.cid] = (o, o + it.dur)
                if it.ring > 0:
                    tm = TimeMap(REAL, 2.0, it.ring + 2, 1.0, dx=0.001)
                    self.runs.append(dict(src=it.src, lo=tq, hi=tq + it.ring, o0=o, ok=o, tq=tq, tm=tm, gain=it.gain_db, cid=it.cid,
                                          fade_out=True))
                o += it.dur
                continue
            pts = sorted(it.accents) or [(it.s0, REAL)]
            bounds = [it.s0] + [(a[0] + b[0]) / 2 for a, b in zip(pts, pts[1:])] + [it.s1]
            first = o
            for k, ((t, sp), lo, hi) in enumerate(zip(pts, bounds, bounds[1:])):
                tq = round(t * 60) / 60.0
                tm = TimeMap(sp, 60.0 if it.accents else 0.0, (hi - lo) + 2 if not it.accents else 60.0, 1.0, dx=0.001)
                o_k = o - tm.inverse(lo - tq)
                o_e = o_k + tm.inverse(hi - tq)
                c = {"id": it.cid if len(pts) == 1 else f"{it.cid}{k + 1}", "note": it.note, "kill_id": len(self.clips),
                     "src_kill_frame": round(tq * 60), "section": "run", "video": video[it.src],
                     "beats": {"start": round(o, 4), "kill": round(o_k, 4), "end": round(o_e, 4)}, "speed": sp, "push_in": 0.0,
                     "intensity": 1.0,
                     "effects": [({**p, "at": round(tm.inverse(ft - tq), 3)} if isinstance(p, dict) else
                                  {"preset": p, "at": round(tm.inverse(ft - tq), 3)}) for ft, p in it.fx if lo - 1e-6 <= ft < hi],
                     "hit": False, "bed_gain": 0.0, "transition_out": {"preset": "cut"}, **it.extra}
                self.clips.append(c)
                self.runs.append(dict(src=it.src, lo=lo, hi=hi, o0=o, ok=o_k, tq=tq, tm=tm, gain=it.gain_db, cid=it.cid))
                o = o_e
            self.marks[it.cid] = (first, o)
        self.end = o

    def at(self, src, t):
        """output time of source time t of recording src (inside one of the runs)"""
        for r in self.runs:
            if r["src"] == src and r["lo"] - 1e-6 <= t <= r["hi"] + 1e-6:
                return r["ok"] + r["tm"].inverse(t - r["tq"])
        raise ValueError(f"source {src} {t} is not in the edit")

    def clip(self, cid):
        return next(c for c in self.clips if c["id"] == cid)

    def game_track(self, audio, path, end, xf=0.12, fade_last=0.0, fin_first=True):
        """the game sound of every run, time-mapped through its speed curve, equal-power crossfades of xf (each side) at the cuts"""
        N = int(round((end + 1) * SR))
        game = np.zeros((N, 2), np.float32)
        for idx, r in enumerate(self.runs):
            os_ = r["o0"]
            nxt = self.runs[idx + 1]["o0"] if idx + 1 < len(self.runs) else end
            oe_ = min(r["ok"] + r["tm"].inverse(r["hi"] - r["tq"]), nxt) if not r.get("fade_out") else r["o0"] + (r["hi"] - r["lo"])
            t_out = np.arange(int(round((os_ - xf) * SR)), int(round((oe_ + xf) * SR))) / SR
            srct = r["tq"] + np.interp(t_out - r["ok"], r["tm"].xs, r["tm"].cum)
            a, b = srct.min() - 0.05, srct.max() + 0.05
            raw, _ = sf.read(audio[r["src"]], start=max(0, int(round(a * SR))), frames=int(round((b - a) * SR)) + 2, dtype="float32",
                             always_2d=True)
            pos = (srct - a) * SR
            y = np.stack([np.interp(pos, np.arange(len(raw)), raw[:, ch]) for ch in range(2)], 1).astype(np.float32)
            spd = np.gradient(srct) * SR
            y *= np.clip((spd - 0.06) / 0.24, 0.0, 1.0)[:, None].astype(np.float32)      # silent on freezes
            y *= 10 ** (r["gain"] / 20)
            n = len(y)
            f = min(int(2 * xf * SR), n // 2)
            w = np.ones(n, np.float32)
            w[:f] = np.sin(np.linspace(0, np.pi / 2, f)) ** 2
            w[-f:] = np.cos(np.linspace(0, np.pi / 2, f)) ** 2
            if r.get("fade_out"):
                k = min(n, int(0.35 * SR))
                w[-k:] *= np.linspace(1, 0, k)
            if idx == len(self.runs) - 1 and fade_last:
                k = min(n, int(fade_last * SR))
                w[-k:] *= np.linspace(1, 0, k)
            i = int(round((os_ - xf) * SR))
            i0 = max(i, 0)
            seg = y[i0 - i:] * w[i0 - i:, None]
            game[i0:i0 + len(seg)] += seg[:N - i0]
        sf.write(path, game, SR, subtype="PCM_24")
        return round(float(20 * np.log10(np.abs(game).max() + 1e-9)), 2)
