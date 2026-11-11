"""Builder of a story / lore / death-counter Short: a seqlib timeline (16:9 render.py edit, game sound + optional song) plus spec.json
(header, big captions, death counter) for the 9:16 compositor. Times in the timeline are output seconds (beat_period 1.0).
Run the caller from its own work folder, at or below the folder that holds recordings.json (tools/reclib.py), with its OWN scan/ folder
(render.py writes scan/mix_<fps>.wav there, a shared one breaks parallel renders). It writes edl.json, game_track.wav, song.wav, spec.json.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from shortlib import Short

    s = Short("V")                                           # recording tag from recordings.json; Short() when there is only one
    s.scene("hook", "V", 1559.6, 1564.4)
    s.cap("V", 1560.0, 1564.0, "nowhere's *Wei* found by my eye.")
    s.run("fight", "V", 1638.6, 1642.4)
    s.death("d1", "V", 1700.25)
    s.react("fight", 0.5, 2.0, "lah kok gitu")
    b, marks, END = s.build([["LINE ONE", "cream"], ["LINE TWO", "coral"]], tail=0.6)

API
  Short(rec=None, title=None)
      rec    recording tag written as the edit's default video / game audio; default = the only recording of the work folder
      title  project.title of the edl; default "<game name from the game profile> Short"
  .quiet(src, t, win=0.5)                                  the quietest 40 ms of game audio within t +- win
  .scene(cid, src, s0, s1, snap=False, **kw)               span played as is (snap=True moves both ends to a pause in the audio)
  .run(cid, src, s0, s1, fx=(), acc=(), **kw)              gameplay span; fx = [(src_t, preset|dict)], acc = [(src_t, speed curve)]
  .death(cid, src, hit, pre=2.2, hold=0.8, slowmo=True, taunt=None, sfx="gong", sfx_db=-6.0)
      the last `pre` s before the killing hit + a grey freeze (+ the boss's line after it up to source time `taunt`);
      sfx = a wav name in <reusable_dir>/SFX; every death adds 1 to the counter
  .blink(cid, src, hit)                                    a death in under a second
  .cap(src, on, off, text)                                 a game line, big (source times; *word* = highlight)
  .react(cid, off, dur, text) / .note(cid, off, dur, text) the player's reaction / a small side note, relative to the start of clip cid
  .build(header, emoji=None, song=None, song_start=0.0, song_db=-4.0, game_db=0.0, counter_base=0, tail=0.6, layout="band", source="r16.mp4")
      -> (seqlib Build, marks {cid: (out start, out end)}, END).  spec.json = {"header", "emoji", "caps", "counter", "counter_end",
      "layout", "source"}; source = the 16:9 render the compositor reads.
  load_song(path)                                          any audio file -> float32 stereo at 48 kHz
Also re-exported for callers that build their own timeline: Run, Hold, Build, slow, SR, VIDEO, AUDIO, read.
"""
import json, subprocess

import numpy as np, soundfile as sf

import projcfg
from seqlib import Run, Hold, Build, slow, SR, VIDEO, AUDIO, pick, read, quiet, _reclib  # noqa: F401  (re-exported for the callers)

DSLOW = slow(0.32, 0.18, 0.25, 0.22)
FA = 0.12
LAYOUT_NOTE = "16:9 band for compose916.py"


def load_song(path):
    """any audio file -> float32 stereo at SR (ffmpeg, so no librosa / numba is needed)"""
    raw = subprocess.run([projcfg.ffmpeg(), "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


class Short:
    def __init__(self, rec=None, title=None):
        self.rec = pick(rec)
        if title is None:
            rl = _reclib()
            title = f'{rl.game().get("game") or rl.rec()["game"] or "Gameplay"} Short'
        self.title = title
        self.seq, self.deaths, self.caps, self.reacts = [], [], [], []

    # ---------------------------------------------------------------- timeline
    def quiet(self, src, t, win=0.5):
        return quiet(src, t, win)

    def scene(self, cid, src, s0, s1, snap=False, **kw):
        if snap:
            s0, s1 = self.quiet(src, s0), self.quiet(src, s1)
        self.seq.append(Run(cid, src, s0, s1, note="scene", **kw))

    def run(self, cid, src, s0, s1, fx=(), acc=(), **kw):
        self.seq.append(Run(cid, src, s0, s1, fx=list(fx), accents=list(acc), note="run", **kw))

    def death(self, cid, src, hit, pre=2.2, hold=0.8, slowmo=True, taunt=None, sfx="gong", sfx_db=-6.0):
        """last seconds before the killing hit + grey freeze (+ the boss's kill line after it: taunt = source end time)"""
        self.seq.append(Run(cid, src, hit - pre, hit + FA, accents=[(hit, DSLOW)] if slowmo else [],
                            fx=[(hit, "shake_3"), (hit, "flash_1")], note="death run"))
        self.seq.append(Hold(cid + "_h", src, hit + FA, hold, note="death freeze",
                             fx=[(0.0, {"type": "desat", "mode": "hold", "dur": hold + 0.05, "amount": 0.88, "ramp": 0.08}),
                                 (0.0, {"type": "zoom_to", "x": 960, "y": 560, "z": 1.06, "from": 0.0, "to": hold}), (0.0, "shake_2")]))
        self.deaths.append((cid, sfx, sfx_db))
        if taunt:
            self.seq.append(Run(cid + "_t", src, hit + FA + 0.02, taunt, note="kill line"))

    def blink(self, cid, src, hit):
        """a death in under a second: 0.55 s before the hit + a 0.2 s freeze (the counter races)"""
        self.death(cid, src, hit, pre=0.55, hold=0.2, slowmo=False, sfx="woodblock", sfx_db=-14.0)

    # ---------------------------------------------------------------- text (resolved after build)
    def cap(self, src, on, off, text):
        """a game line, big under the band (source times; *word* = highlight)"""
        self.caps.append((src, on, off, text))

    def react(self, cid, off, dur, text):
        """the player's own reaction, relative to the start of clip cid"""
        self.reacts.append((cid, off, dur, text))

    def note(self, cid, off, dur, text):
        """a small side note in the player's voice (e.g. footage missing), small text, not a reaction"""
        self.reacts.append((cid, off, dur, text, "note"))

    # ---------------------------------------------------------------- build
    def build(self, header, emoji=None, song=None, song_start=0.0, song_db=-4.0, game_db=0.0, counter_base=0, tail=0.6,
              layout="band", source="r16.mp4"):
        b = Build(self.seq, VIDEO)
        END = b.end + tail
        b.clips[-1]["beats"]["end"] = round(END, 4)
        T = b.marks
        gpk = b.game_track(AUDIO, "game_track.wav", END, xf=0.06, fade_last=0.5)
        sfx = [{"file": "game_track.wav", "t": 0.0, "peak_db": gpk + game_db, "duck_db": 0}]
        sfx_dir = projcfg.path("reusable_dir", "SFX")
        for cid, kind, db in self.deaths:
            sfx.append({"file": f"{sfx_dir}/{kind}.wav", "t": round(T[cid + "_h"][0], 3), "peak_db": db, "duck_db": 0})
        if song:
            y = load_song(song)
            y = y[int(song_start * SR):int((song_start + END + 1) * SR)]
            k = int(0.8 * SR)
            y[-k:] *= np.linspace(1, 0, k)[:, None]
            sf.write("song.wav", y, SR)
        else:
            sf.write("song.wav", np.zeros((int((END + 1) * SR), 2), np.float32), SR)

        def out_t(src, t):
            for r in b.runs:
                if r["src"] == src and r["lo"] - 1e-6 <= t <= r["hi"] + 1e-6 and not r.get("fade_out"):
                    return r["ok"] + r["tm"].inverse(t - r["tq"])
            return None

        caps = []
        for src, on, off, text in self.caps:
            a, z = out_t(src, on), out_t(src, off)
            if a is None or z is None:
                raise ValueError(f"caption outside the edit: {src} {on}-{off} {text}")
            caps.append({"t0": round(a, 3), "t1": round(z, 3), "text": text, "kind": "game"})
        for cid, off, dur, text, *kind in self.reacts:
            t0 = T[cid][0] + off
            caps.append({"t0": round(t0, 3), "t1": round(t0 + dur, 3), "text": text, "kind": kind[0] if kind else "react"})
        caps.sort(key=lambda c: c["t0"])
        counter = [[round(T[cid + "_h"][0], 3), counter_base + k + 1] for k, (cid, _, _) in enumerate(self.deaths)]
        spec = {"header": header, "emoji": emoji, "caps": caps, "counter": counter, "counter_end": round(END, 3),
                "layout": layout, "source": source}
        json.dump(spec, open("spec.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        edl = {
            "version": 1, "project": {"title": self.title, "video": VIDEO[self.rec], "layout": LAYOUT_NOTE},
            "canvas": "16:9",
            "song": {"file": "song.wav", "window_start": 0.0, "window_beats": round(END, 4), "beat_period": 1.0, "audio_offset_ms": 0.0},
            "grade": {"contrast": 1.05, "brightness": 0.0, "saturation": 1.06, "gamma": 1.0, "sharpen": 0.3, "sharpen_final": 0.45,
                      "vignette_angle": "PI/12"},
            "fades": {"video_in": 0.2, "video_out": 0.3},
            "render": {"slowmo_interp": "flow"},
            "audio": {"kill_hit": {"pre": 0.02, "post": 0.9, "rms_db": -12.0, "attack": 0.002, "decay_tau": 0.38, "fade_out": 0.35,
                                   "bass_db": 2.0, "lead": 0.0, "lead_db": -10.0},
                      "shots": {"max": 0, "peak_db": -12.0, "min_sep": 0.08, "len": 0.22, "post_events": 0, "post_db_offset": -4.0},
                      "duck": {"kill_db": 0.0, "shot_db": 0.0, "lead_db": 0.0, "hold": 0.08, "release": 0.26},
                      "game_file": AUDIO[self.rec], "bed": {"on": False, "rel_db": 0.0, "edge": 0.008},
                      "song_gain_db": song_db if song else -40.0, "bus_comp_thr": 0.5, "bus_hp_hz": 30, "song_fade_in": 0.0,
                      "song_fade_out": 0.05, "target_lufs": -14.0, "sfx": sfx},
            "texts": [],
            "clips": b.clips,
        }
        json.dump(edl, open("edl.json", "w"), indent=1)
        print(f"{len(b.clips)} clips, {len(self.deaths)} deaths, {len(caps)} captions, END {END:.1f} s")
        return b, T, END
