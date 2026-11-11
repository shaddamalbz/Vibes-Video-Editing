"""Builder of a 16:9 long-form edit: spans of a recording joined end to end (seqlib Runs), game sound only, real speed, a logo end card.
Run the caller (make_edl.py) from its own work folder, at or below the folder that holds recordings.json (tools/reclib.py): it writes
edl.json (reference/edl.md), game_track.wav, a silent song.wav, runs.json (source span -> output time of every run), chapters.txt and,
with add-ons, caps/<name>/ sprites and sfx/*.wav.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from longlib import Long, quiet

    L = Long("W")                                   # recording tag from recordings.json; Long() when there is only one
    L.scene("intro", "W", 12.0, 31.5)               # cutscene / conversation, both ends snapped to a pause in the audio
    L.run("fight", "W", 40.0, 95.0)                 # gameplay; speed=2 plays it fast, gain_db=-6 lowers its sound
    L.caption("oops", "W", 61.2, 3.0, "salah pencet", (780, 330), "monkaHmm_a")
    L.sfx("W", 61.2, "bonk.wav", -8.0)
    L.sfx_fill("fight", "walk.mp3", -11.0)
    L.build("Game - part 1", "lanjut part 2.", dips=["intro"], chapters=[("Intro", "intro"), ("First fight", "fight")])

API
  Long(rec=None, outro=15.0, endcard=None, notes=NOTES)
      rec      recording tag written as the edit's default video / game audio (project.video, audio.game_file); default = the only
               recording of the work folder. Every scene / run still names its own recording, so one edit can mix several.
      outro    seconds of logo end card after the last clip (the last clip is held under it, its sound fades over outro - 2 s); 0 = none
      endcard  sizes / positions of the card, merged over ENDCARD; the logo, the wordmark and the default background come from the
               channel profile's brand.json inside the renderer (brand.py)
      notes    free text for project.notes
  .scene(cid, src, s0, s1, snap=True, **kw)        span played as is; snap moves both ends to the nearest pause (quiet())
  .run(cid, src, s0, s1, speed=None, **kw)         gameplay span; speed > 1 = constant fast rate. kw = seqlib.Run extras (gain_db, fx ...)
  .caption(name, src, t, dur, text, at, sticker=None, side="right", size=46, sh=120, pop=0.18, fade=0.15)
      meme caption (tools/meme_caption.py) from source time t for dur output seconds, block centre at = (x, y) in 1080p pixels
  .sfx(src, t, file, peak_db=-8.0, offset=0.0)     a sound from <reusable_dir>/SFX at source time t (offset in output seconds)
  .sfx_fill(cid, file, peak_db=-10.0)              a sound looped over the whole output length of run cid
  .build(title, note, dips, chapters, fade_in=0.3)
      note = small text over the last 4.2 s before the end card, dips = clip ids that end with a dip to black,
      chapters = [(name, clip id)] -> chapters.txt with YouTube timestamps
  quiet(src, t, win=0.5)                           the quietest 40 ms of game audio within t +- win
"""
import json, os, subprocess

import numpy as np, soundfile as sf

import projcfg
from seqlib import Run, Build, SR, VIDEO, AUDIO, pick, read, quiet  # noqa: F401  (re-exported for the callers)

OUTRO = 15.0
ENDCARD = {"logo_width": 0.12, "logo_y": 0.43, "wordmark_width": 0.26, "wordmark_y": 0.60, "pixel_in": 0.55}   # a small card for 16:9
NOTES = "timeline in seconds; game sound only"


class Long:
    def __init__(self, rec=None, outro=OUTRO, endcard=None, notes=NOTES):
        self.rec, self.outro, self.endcard, self.notes = pick(rec), float(outro), endcard, notes
        self.seq, self.caps, self.fx, self.fills = [], [], [], []

    def scene(self, cid, src, s0, s1, snap=True, **kw):
        """a cutscene / conversation span, played as is; both ends moved to the nearest pause in the audio"""
        if snap:
            s0, s1 = quiet(src, s0), quiet(src, s1)
        self.seq.append(Run(cid, src, s0, s1, note="scene", **kw))

    def run(self, cid, src, s0, s1, speed=None, **kw):
        """gameplay span; speed > 1 plays it fast at a constant rate (game sound comes along time-squeezed, so lower it with gain_db)"""
        if speed:
            kw["accents"] = [(s0, {"keys": [[-200, speed], [200, speed]]})]
        self.seq.append(Run(cid, src, s0, s1, note="run", **kw))

    def caption(self, name, src, t, dur, text, at, sticker=None, side="right", size=46, sh=120, pop=0.18, fade=0.15):
        """meme caption (+ sticker, tools/meme_caption.py look) from source time t of recording src, dur output seconds,
        block centre at = (x, y) in 1080p pixels. Sprites in caps/<name>/."""
        self.caps.append(dict(name=name, src=src, t=t, dur=dur, text=text, at=at, sticker=sticker, side=side, size=size, sh=sh, pop=pop, fade=fade))

    def sfx(self, src, t, file, peak_db=-8.0, offset=0.0):
        """a sound effect from <reusable_dir>/SFX at source time t of recording src (offset = output seconds, e.g. negative to land the hit)"""
        self.fx.append(dict(src=src, t=t, file=file, peak_db=peak_db, offset=offset))

    def sfx_fill(self, cid, file, peak_db=-10.0):
        """a sound effect looped over the whole output length of run cid (fades at both ends), e.g. cartoon footsteps over a fast walk"""
        self.fills.append(dict(cid=cid, file=file, peak_db=peak_db))

    def _endcard(self):
        bg = projcfg.brand().get("endcard_bg_bgr")
        return {**({"bg_bgr": bg} if bg is not None else {}), **ENDCARD, **(self.endcard or {})}

    def build(self, title, note, dips, chapters, fade_in=0.3):
        outro = self.outro
        b = Build(self.seq, VIDEO)
        END = b.end + outro
        b.clips[-1]["beats"]["end"] = round(END, 4)
        T = b.marks
        for cid in dips:
            next(c for c in b.clips if c["id"] == cid)["transition_out"] = {"preset": "dip_black_1"}
        t1 = b.end
        texts = [{"style": "plain", "anim": "rise", "text": note, "beat": round(t1 - 4.2, 3), "dur": 4.2, "pos": [0.5, 0.84], "size": 0.030, "wrap": 0.7}]
        gpk = b.game_track(AUDIO, "game_track.wav", END, xf=0.12, fade_last=max(outro - 2.0, 0.0))
        sfx = [{"file": "game_track.wav", "t": 0.0, "peak_db": gpk, "duck_db": 0}]
        overlays = self._addons(b, sfx)
        sf.write("song.wav", np.zeros((int((END + 1) * SR), 2), np.float32), SR)
        edl = {
            "version": 1,
            "project": {"title": title, "video": VIDEO[self.rec], "layout": "16:9 long-form", "notes": self.notes},
            "canvas": "16:9",
            "song": {"file": "song.wav", "window_start": 0.0, "window_beats": round(END, 4), "beat_period": 1.0, "audio_offset_ms": 0.0},
            "grade": {"contrast": 1.04, "brightness": 0.0, "saturation": 1.04, "gamma": 1.0, "sharpen": 0.3, "sharpen_final": 0.45, "vignette_angle": "PI/10"},
            "fades": {"video_in": fade_in, "video_out": 0.6},
            "render": {"slowmo_interp": "flow"},
            **({"endcard": {"start_beat": round(END - outro, 3), "fade_beats": 0.6, **self._endcard()}} if outro > 0 else {}),
            "audio": {"kill_hit": {"pre": 0.02, "post": 0.9, "rms_db": -12.0, "attack": 0.002, "decay_tau": 0.38, "fade_out": 0.35, "bass_db": 2.0, "lead": 0.0, "lead_db": -10.0},
                      "shots": {"max": 0, "peak_db": -12.0, "min_sep": 0.08, "len": 0.22, "post_events": 0, "post_db_offset": -4.0},
                      "duck": {"kill_db": 0.0, "shot_db": 0.0, "lead_db": 0.0, "hold": 0.08, "release": 0.26},
                      "game_file": AUDIO[self.rec], "bed": {"on": False, "rel_db": 0.0, "edge": 0.008},
                      "song_gain_db": -4.0, "bus_comp_thr": 0.5, "bus_hp_hz": 30, "song_fade_in": 0.0, "song_fade_out": 0.05, "target_lufs": -14.0,
                      "sfx": sfx},
            "texts": texts,
            "overlays": overlays,
            "clips": b.clips,
        }
        json.dump(edl, open("edl.json", "w"), indent=1)
        json.dump([{"cid": r["cid"], "src": r["src"], "lo": round(r["lo"], 3), "hi": round(r["hi"], 3), "out": round(r["o0"], 3)} for r in b.runs], open("runs.json", "w"), indent=0)
        with open("chapters.txt", "w") as f:
            for name, cid in chapters:
                t = T[cid][0]
                f.write(f"{int(t // 60)}:{int(t % 60):02d} {name}\n")
        m, s = divmod(END, 60)
        print(open("chapters.txt").read())
        print(f"edl.json: {len(b.clips)} clips, END {END:.1f} s = {int(m)}:{s:04.1f}")

    def _addons(self, b, sfx):
        """caption sprites -> render overlays, SFX -> audio.sfx entries (wav copies in sfx/), loops cut to their run's length"""
        os.makedirs("sfx", exist_ok=True)
        sfx_dir = projcfg.path("reusable_dir", "SFX")

        def wav(file):
            out = "sfx/" + os.path.splitext(os.path.basename(file))[0] + ".wav"
            if not os.path.exists(out):
                subprocess.run([projcfg.ffmpeg(), "-v", "error", "-y", "-i", f"{sfx_dir}/{file}", "-ar", str(SR), "-ac", "2", out], check=True)
            return out

        ov = []
        if self.caps:
            projcfg.use_tools()
            import meme_caption
        for c in self.caps:
            w, h = meme_caption.write_sprite(f"caps/{c['name']}", c["text"], c["sticker"], c["side"], c["size"], c["sh"])
            t0 = b.at(c["src"], c["t"])
            ov.append({"dir": f"caps/{c['name']}", "start": round(t0, 3), "end": round(t0 + c["dur"], 3), "x": c["at"][0] / 1920,
                       "bottom": (c["at"][1] + h / 2) / 1080, "height": h / 1080, "rate": 1.0, "loop": True, "pop": c["pop"], "fade": c["fade"]})
            print(f"caption {c['name']:8s} out {t0:8.2f}  {c['text']!r} + {c['sticker']}")
        for f in self.fx:
            t0 = b.at(f["src"], f["t"])
            sfx.append({"file": wav(f["file"]), "t": round(t0, 3), "offset": f["offset"], "peak_db": f["peak_db"], "duck_db": 0})
            print(f"sfx {f['file']} out {t0 + f['offset']:8.2f}")
        for f in self.fills:
            a, z = b.marks[f["cid"]]
            y, _ = sf.read(wav(f["file"]), dtype="float32", always_2d=True)
            n = int((z - a) * SR)
            y = np.tile(y, (n // len(y) + 1, 1))[:n].copy()
            k = int(0.25 * SR)
            y[:k] *= np.linspace(0, 1, k)[:, None]
            y[-k:] *= np.linspace(1, 0, k)[:, None]
            out = f"sfx/fill_{f['cid']}.wav"
            sf.write(out, y, SR)
            sfx.append({"file": out, "t": round(a, 3), "peak_db": f["peak_db"], "duck_db": 0})
            print(f"sfx fill {f['file']} over {f['cid']} {a:.2f}-{z:.2f}")
        return ov
