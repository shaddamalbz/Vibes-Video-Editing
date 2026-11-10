"""Audio for the montage.

The game sounds are treated as part of the music:
  * bed        : (optional, audio.bed.on) continuous game sound under every clip, retimed through its speed ramp. For games whose
                 recording carries its own soundtrack (FF XVI), point audio.game_file at a music-free SFX track (Demucs, see reference/games.md)
  * sfx        : (optional, audio.sfx) extra samples such as a meme "bonk", placed on a beat
  * kill hit   : the game's own audio at the kill (impact + bass thump + shot tail), triggered ON the kill frame = on the beat,
                 level-normalised so every kill hits equally hard (it behaves like a drum sample)
  * shots      : the game's gunshots before the kill are re-timed through the clip's speed ramp, so each shot still lands on its
                 muzzle flash even in slow-mo (played at 1x, not stretched)
  * audio_lag  : per clip (s): the game audio trails the picture by this much (OBS sync); the hit is read that much later
                 and the onset auto-trim is skipped (the measured lag already puts the gunshot on the beat)
  * duck       : the song is pumped down (sidechain-style envelope) on every hit, so hits cut through and the groove locks to the kills
Python only places the samples / builds the duck envelope (sample-accurate bookkeeping); FFmpeg does the DSP:
song fades, amultiply (duck), highpass + compression of the hit bus, limiter and two-pass loudnorm to -14 LUFS.
"""
import json, os, re, subprocess, sys
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt
from edl_lib import load_edl, timeline, HERE
from timemap import TimeMap

SR = 48000
GAME = os.path.join(HERE, "scan", "game_audio_st48.wav")
GAME_OFF = 0.0                                         # source time of sample 0 in GAME (a compact track that starts mid-recording)
DEFAULTS = {
    "kill_hit": {"pre": 0.02, "post": 0.90, "rms_db": -4.0, "attack": 0.002, "decay_tau": 0.38, "fade_out": 0.35, "bass_db": 7.0, "lead": 0.30, "lead_db": -10.0},
    "shots": {"max": 2, "peak_db": -6.0, "min_sep": 0.08, "len": 0.22, "post_events": 1, "post_db_offset": -4.0},
    "duck": {"kill_db": 8.0, "shot_db": 1.5, "lead_db": 3.0, "hold": 0.08, "release": 0.26},
    "duck_split_hz": 220,
    "ambient_rms_db": -26.0,
    "game_file": "scan/game_audio_st48.wav",          # which game track to use (FFXVI: BGM-free SFX track)
    "bed": {"on": False, "rel_db": -6.0, "edge": 0.008},   # continuous game sound under every clip, retimed through the speed ramp (varispeed)
    "song_gain_db": -6.0,
    "bus_comp_thr": 0.45,
    "bus_hp_hz": 30, "song_fade_in": 0.10, "song_fade_out": 1.20, "target_lufs": -14.0,
}


def cfg(edl):
    a = edl.get("audio", {})
    out = {}
    for k, v in DEFAULTS.items():
        out[k] = {**v, **a.get(k, {})} if isinstance(v, dict) else a.get(k, v)
    return out


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def use_game(c, A):
    """point read_game at the clip's own game track (multi-recording edits / a music-free track: clip["game_audio"]), else audio.game_file.
    clip["game_audio_offset"] (or audio.game_file_offset): source time of the track's first sample (compact tracks, e.g. FLAC of a range)"""
    global GAME, GAME_OFF
    GAME = os.path.join(HERE, c.get("game_audio", A["game_file"]))
    GAME_OFF = float(c.get("game_audio_offset", A.get("game_file_offset", 0.0) if "game_audio" not in c else 0.0))


def read_game(t0, dur):
    i0 = max(int(round((t0 - GAME_OFF) * SR)), 0)
    y, _ = sf.read(GAME, start=i0, frames=int(round(dur * SR)), dtype="float32", always_2d=True)
    return y


def detect_shots(t_lo, t_hi):
    """gunshot-like onsets in the game audio: sharp rise of high-passed short-time energy. returns [(t_onset, peak_db)]"""
    if t_hi - t_lo < 0.05:                            # empty range (e.g. a clip shorter than the hit): sf.read with frames < 0 reads the whole file
        return []
    y = read_game(t_lo, t_hi - t_lo).mean(1)
    if len(y) < 2048:
        return []
    sos = butter(4, 250, "hp", fs=SR, output="sos")
    hp = sosfilt(sos, y)
    w = int(0.004 * SR)
    E = np.convolve(hp ** 2, np.ones(w) / w, mode="same")
    db = 10 * np.log10(E + 1e-12)
    k = int(0.012 * SR)
    rise = db - np.concatenate([np.full(k, db[0]), db[:-k]])
    cand = np.where((rise > 14) & (db > -50))[0]
    ons, last = [], -10 ** 9
    for i in cand:
        if i - last > int(0.05 * SR):                 # first sample of a new rise
            j = i + int(np.argmax(rise[i:i + int(0.02 * SR)]))
            ons.append(j)
            last = j
    out = []
    for j in ons:
        t = t_lo + j / SR
        seg = y[j:j + int(0.06 * SR)]
        out.append((t, 20 * np.log10(np.abs(seg).max() + 1e-9)))
    return out


def fade(x, fin, fout):
    n = len(x)
    a, b = min(int(fin * SR), n), min(int(fout * SR), n)     # a short hit (small "post") may be shorter than the fade
    if a:
        x[:a] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a)))[:, None]
    if b:
        x[n - b:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, b)))[:, None]
    return x


def place(bus, snip, t, peak_db, gain_db_extra=0.0):
    pk = 20 * np.log10(np.abs(snip).max() + 1e-9)
    g = 10 ** (min(peak_db + gain_db_extra - pk, 24.0) / 20)
    i0 = int(round(t * SR))
    i1 = min(i0 + len(snip), len(bus))
    if i0 < 0 or i1 <= i0:
        return
    bus[i0:i1] += snip[:i1 - i0] * g


def duck_envelope(triggers, N, hold, release):
    env_db = np.zeros(N, dtype=np.float32)
    att = 0.006
    for t0, depth in triggers:
        i0 = max(int((t0 - att) * SR), 0)
        i1 = min(int((t0 + hold + 7 * release) * SR), N)
        if i1 <= i0:
            continue
        tt = np.arange(i0, i1) / SR
        d = np.where(tt < t0, (tt - (t0 - att)) / att, np.where(tt < t0 + hold, 1.0, np.exp(-(tt - (t0 + hold)) / release)))
        env_db[i0:i1] = np.minimum(env_db[i0:i1], -depth * d.astype(np.float32))
    return (10 ** (env_db / 20)).astype(np.float32)


def bed_bus(edl, tl, fps, N, A, P):
    """continuous game sound: every clip's source audio played through its time map (slow-mo = slower + lower, like tape)"""
    bed = np.zeros((N, 2), dtype=np.float32)
    for c in tl:
        use_game(c, A)
        n0, n1 = int(round(c["n_s"] / fps * SR)), min(int(round(c["n_e"] / fps * SR)), N)
        if n1 <= n0:
            continue
        t_out = np.arange(n0, n1) / SR
        tk_out, t_k = c["n_k"] / fps, c["src_kill_frame"] / 60.0 + c.get("audio_lag", 0.0)
        if c.get("calm"):
            src = t_k + (t_out - t_out[0])
        else:
            tm = TimeMap(c["speed"], (c["n_k"] - c["n_s"]) / fps, (c["n_e"] - c["n_k"]) / fps, P)
            src = t_k + np.interp(t_out - tk_out, tm.xs, tm.cum)
        lo, hi = max(src.min() - 0.05, 0.0), src.max() + 0.05
        y = read_game(lo, hi - lo)
        pos = (src - lo) * SR
        seg = np.stack([np.interp(pos, np.arange(len(y)), y[:, ch]) for ch in range(2)], 1).astype(np.float32)
        spd = np.gradient(src) * SR                          # a freeze frame (speed < 0.05) plays the source at a crawl = a low drone:
        g = np.clip((spd - 0.06) / 0.24, 0.0, 1.0)            # mute the bed there instead (fades in/out over ~0.1 s)
        if g.min() < 0.999:
            k = max(1, int(0.05 * SR))
            g = np.convolve(g, np.ones(k) / k, mode="same")
            seg *= g[:, None].astype(np.float32)
        e = int(A["bed"]["edge"] * SR)
        ei, eo = c.get("bed_edge_in", A["bed"]["edge"]), c.get("bed_edge_out", A["bed"]["edge"])   # 0 where the next clip continues the same source
        seg = fade(seg, ei, eo) if len(seg) > 2 * e else seg
        bed[n0:n1] += seg * c.get("bed_gain", 1.0)
    return bed


def build_bus(edl, fps, verbose=True):
    tl, total = timeline(edl, fps)
    P = edl["song"]["beat_period"]
    A = cfg(edl)
    L = total / fps
    N = int(round(L * SR))
    bus = np.zeros((N, 2), dtype=np.float32)
    triggers = []
    log = []
    for c in tl:
        use_game(c, A)
        if c.get("hit") is False:                           # long-form real-time stretches: only the bed (the game sound as it is)
            log.append((c["id"] + "-", 0, 0))
            continue
        if c.get("calm"):                                   # relaxed opening: just the game's ambience (footsteps etc.) under the music
            t_a = c["src_kill_frame"] / 60.0 + c.get("audio_lag", 0.0)
            sn = fade(read_game(t_a, (c["n_e"] - c["n_s"]) / fps).copy(), 0.10, 0.20)
            rms = np.sqrt((sn ** 2).mean() + 1e-12)
            g = 10 ** ((A["ambient_rms_db"] - 20 * np.log10(rms)) / 20)
            i0 = int(round(c["n_s"] / fps * SR)); i1 = min(i0 + len(sn), len(bus))
            if i1 > i0:
                bus[i0:i1] += sn[:i1 - i0] * g
            log.append((c["id"] + "~", 0, 0))
            continue
        tk_out = c["n_k"] / fps
        t_k = c["src_kill_frame"] / 60.0 + c.get("audio_lag", 0.0)     # audio_lag: the recording's sound trails its picture (OBS)
        tm = TimeMap(c["speed"], (c["n_k"] - c["n_s"]) / fps, (c["n_e"] - c["n_k"]) / fps, P)
        src_lo = t_k + tm.offset(-(c["n_k"] - c["n_s"]) / fps)
        src_hi = t_k + tm.offset((c["n_e"] - c["n_k"]) / fps)
        kh = {**A["kill_hit"], **c.get("audio_kill_hit", {})}          # per-clip override (e.g. the 2nd tap of a double)
        # --- kill hit on the kill frame (onset-aligned: if the game's loud burst comes later than the kill frame, trim the quiet lead so the burst lands ON the beat)
        MAXT = 0.35
        full = read_game(t_k - kh["pre"], kh["pre"] + kh["post"] + MAXT).copy()
        e5 = np.convolve(np.abs(full).mean(1), np.ones(int(0.005 * SR)) / int(0.005 * SR), mode="same")
        ref = e5[:int((kh["pre"] + 0.5) * SR)].max() + 1e-9
        i_on = int(np.argmax(e5 >= 0.20 * ref))
        pre_eff, shift = kh["pre"], 0.0
        if i_on > int(kh["pre"] * SR) + int(0.02 * SR) and c.get("audio_lag") is None:   # a measured lag already puts the shot on the beat
            i_on = min(i_on, int((kh["pre"] + MAXT) * SR))
            start = max(i_on - int(0.005 * SR), 0)
            shift = start / SR - kh["pre"]
            full = full[start:]
            pre_eff = 0.005
        snip = full[:int((pre_eff + kh["post"]) * SR)]
        tt = np.arange(len(snip)) / SR - pre_eff
        envh = np.where(tt >= 0, np.minimum(tt / kh["attack"], 1.0) * np.exp(-tt / kh["decay_tau"]), 0.0)   # silent before the kill frame: the hit starts ON the beat
        snip = fade(snip * envh[:, None].astype(np.float32), 0.0, kh["fade_out"])
        a0, a1 = int(pre_eff * SR), int((pre_eff + min(0.30, kh["post"])) * SR)     # short hits: level over what is played
        rms = np.sqrt((snip[a0:a1] ** 2).mean() + 1e-12)
        g = 10 ** (min(kh["rms_db"] - 20 * np.log10(rms), 36.0) / 20)
        i0 = int(round((tk_out - pre_eff) * SR)); i1 = min(i0 + len(snip), len(bus))
        if i0 >= 0 and i1 > i0:
            bus[i0:i1] += snip[:i1 - i0] * g
        if shift > 0.01:
            print(f"  {c['id']} kill#{c['kill_id']}: hit onset trimmed by {shift*1000:.0f} ms so the burst lands on the beat")
        triggers.append((tk_out, c.get("audio_duck_db", A["duck"]["kill_db"])))        # per-clip override (lighter for rapid runs)
        if kh.get("lead", 0) > 0:
            ld = read_game(t_k - kh["pre"] - kh["lead"], kh["lead"]).copy()
            ld = fade(ld, kh["lead"] * 0.9, 0.0)                                 # crescendo into the beat
            rms = np.sqrt((ld[int(len(ld) * 0.5):] ** 2).mean() + 1e-12)
            g = 10 ** (min(kh["rms_db"] + kh["lead_db"] - 20 * np.log10(rms), 36.0) / 20)
            i0 = int(round((tk_out - kh["pre"] - kh["lead"]) * SR)); i1 = min(i0 + len(ld), len(bus))
            if i0 >= 0 and i1 > i0:
                bus[i0:i1] += ld[:i1 - i0] * g
            triggers.append((tk_out - kh["lead"] * 0.8, A["duck"]["lead_db"]))
        # --- gunshots before the kill, retimed through the speed ramp
        sh = A["shots"]
        ev = [(t, p) for t, p in detect_shots(max(src_lo - 0.1, 0), t_k - kh["pre"] - 0.01) if src_lo - 0.02 <= t < t_k - kh["pre"] - 0.03]
        ev.sort(key=lambda e: -e[1])
        chosen = []
        for t, p in ev:
            if len(chosen) >= sh["max"]:                     # checked first, so "max": 0 really means no shots
                break
            if all(abs(t - u) >= sh["min_sep"] for u, _ in chosen):
                chosen.append((t, p))
        post = [(t, p) for t, p in detect_shots(t_k + kh["post"] + 0.02, min(src_hi, t_k + 2.0)) if t < src_hi - 0.05]
        post.sort(key=lambda e: -e[1])
        post = post[:sh["post_events"]]
        for t, p in chosen + post:
            is_post = t > t_k
            tau = tk_out + tm.inverse(t - t_k) - 0.010
            if tau < 0 or tau > L - 0.05:
                continue
            s = fade(read_game(t - 0.010, sh["len"]).copy(), 0.003, 0.07)
            place(bus, s, tau, sh["peak_db"], sh["post_db_offset"] if is_post else 0.0)
            triggers.append((tau + 0.010, A["duck"]["shot_db"]))
        log.append((c["id"], len(chosen), len(post)))
    for fx in edl.get("audio", {}).get("sfx", []):          # extra sound effects (e.g. a meme "bonk"): {"file", "beat" (window beats) or "t" (s), "peak_db", "duck_db"}
        y, sr = sf.read(os.path.join(HERE, fx["file"]), dtype="float32", always_2d=True)
        if y.shape[1] == 1:
            y = np.repeat(y, 2, 1)
        if sr != SR:
            pos = np.arange(int(len(y) * SR / sr)) * sr / SR
            y = np.stack([np.interp(pos, np.arange(len(y)), y[:, ch]) for ch in range(2)], 1).astype(np.float32)
        t = fx["t"] if "t" in fx else fx["beat"] * P
        place(bus, y[:, :2], t + fx.get("offset", 0.0), fx.get("peak_db", -6.0))
        if fx.get("duck_db", 0) > 0:
            triggers.append((t, fx["duck_db"]))
    if A["bed"]["on"]:                                       # level the bed against the song window (song after its gain)
        bed = bed_bus(edl, tl, fps, N, A, P)
        if "gain_db" in A["bed"]:                            # fixed gain (long-form: the game sound leads, music only in parts)
            g = 10 ** (A["bed"]["gain_db"] / 20)
        else:
            song = edl["song"]
            ssr = sf.info(os.path.join(HERE, song["file"])).samplerate
            s, _ = sf.read(os.path.join(HERE, song["file"]), start=int(song["window_start"] * ssr), frames=int(L * ssr), always_2d=True)
            r_song = np.sqrt((s ** 2).mean()) * 10 ** (A["song_gain_db"] / 20)
            r_bed = np.sqrt((bed ** 2).mean()) + 1e-9
            g = r_song / r_bed * 10 ** (A["bed"]["rel_db"] / 20)
        bus += bed * g
        if verbose:
            print(f"  game bed: {20*np.log10(g):+.1f} dB gain, {A['bed']['rel_db']:+.1f} dB vs song")
    env = duck_envelope(triggers, N, A["duck"]["hold"], A["duck"]["release"])
    if verbose:
        print("  shots retimed per clip (pre/post):", ", ".join(f"{i}:{a}/{b}" for i, a, b in log))
    return bus, env, tl, total, L


def build_mix(edl, fps, out_wav):
    A = cfg(edl)
    bus, env, tl, total, L = build_bus(edl, fps)
    scan = os.path.join(HERE, "scan")
    bus_wav, env_wav = os.path.join(scan, "bus.wav"), os.path.join(scan, "duck_env.wav")
    sf.write(bus_wav, bus, SR, subtype="FLOAT")
    sf.write(env_wav, np.stack([env, env], 1), SR, subtype="FLOAT")
    song = edl["song"]
    S0 = song["window_start"] + song.get("audio_offset_ms", 0.0) / 1000.0
    fmt = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    fc = (f"[0:a]atrim=start={S0:.6f}:duration={L:.6f},asetpts=PTS-STARTPTS,aresample=48000,{fmt},volume={A['song_gain_db']}dB,"
          f"afade=t=in:st=0:d={A['song_fade_in']},afade=t=out:st={L-A['song_fade_out']:.4f}:d={A['song_fade_out']}[s0];"
          f"[s0]acrossover=split={A['duck_split_hz']}:order=4th[slo][shi];"                       # duck only the mids/highs, keep kick + bass intact
          f"[2:a]{fmt}[e];[shi][e]amultiply[shd];[slo][shd]amix=inputs=2:normalize=0:duration=longest[s1];"
          f"[1:a]{fmt},highpass=f={A['bus_hp_hz']},equalizer=f=70:t=q:w=1.2:g={A['kill_hit']['bass_db']},acompressor=threshold={A['bus_comp_thr']}:ratio=3:attack=3:release=60:makeup=1[b];"
          f"[s1][b]amix=inputs=2:normalize=0:duration=longest,atrim=duration={L:.6f},asetpts=PTS-STARTPTS,alimiter=limit=0.95:level=disabled[mix]")
    script = os.path.join(scan, "mix_graph.txt")
    open(script, "w", encoding="utf-8").write(fc)
    raw = os.path.join(scan, "mix_raw.wav")
    r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", os.path.join(HERE, song["file"]), "-i", bus_wav, "-i", env_wav,
             "-filter_complex_script", script, "-map", "[mix]", "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", raw])
    if r.returncode:
        raise RuntimeError(r.stderr)
    I = A["target_lufs"]
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", raw, "-af", f"loudnorm=I={I}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S).group(0))
    af = (f"loudnorm=I={I}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=summary")
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", raw, "-af", af, "-ar", "48000", "-c:a", "pcm_s16le", out_wav])
    if r.returncode:
        raise RuntimeError(r.stderr)
    chk = run(["ffmpeg", "-hide_banner", "-nostats", "-i", out_wav, "-af", "ebur128=peak=true", "-f", "null", "-"])
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", chk.stderr)[-1]
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", chk.stderr)[-1]
    # how much louder is the game hit than the (ducked) song in the first 150 ms of each moment?
    ssr = sf.info(os.path.join(HERE, song["file"])).samplerate
    s, _ = sf.read(os.path.join(HERE, song["file"]), start=int(S0 * ssr), frames=int(L * ssr), always_2d=True)
    s48 = np.stack([np.interp(np.arange(int(L * SR)) / SR, np.arange(len(s)) / ssr, s[:, ch]) for ch in range(2)], 1) * env[:int(L * SR), None]
    d1, d2 = [], []
    for c in tl:
        if c.get("calm") or c.get("hit") is False:
            continue
        a0 = int(c["n_k"] / fps * SR)
        for (x0, x1, dl) in ((0.0, 0.15, d1), (0.15, 0.40, d2)):
            b0, b1 = a0 + int(x0 * SR), a0 + int(x1 * SR)
            rb = np.sqrt((bus[b0:b1] ** 2).mean() + 1e-12); rs = np.sqrt((s48[b0:b1] ** 2).mean() + 1e-12)
            dl.append(20 * np.log10(rb / rs))
    print(f"audio mix: {L:.3f}s, pre-norm {m['input_i']} LUFS -> {lufs} LUFS (true peak {tp} dBFS)")
    if d1:
        print(f"  game hit vs ducked song: 0-150 ms median {np.median(d1):+.1f} dB (min {min(d1):+.1f}, max {max(d1):+.1f}); 150-400 ms median {np.median(d2):+.1f} dB")
    return out_wav, float(lufs), float(tp)


if __name__ == "__main__":
    fps = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    build_mix(load_edl(), fps, os.path.join(HERE, "scan", f"mix_{int(fps)}.wav"))
