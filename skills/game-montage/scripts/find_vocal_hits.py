"""Find sung moments (e.g. every "bang") in the song window, so kills can land ON the syllable.

What worked on IVE "Bang Bang" (after two wrong tries with plain DSP):
  1. Demucs (htdemucs) splits the song into vocals / instrumental.     <- centre-channel tricks pick up bass + kick, do NOT use them
  2. On the clean vocal: onset strength peaks = syllable starts; level + pitch per syllable.
  3. Whisper (small) on short chunks finds the word only when it is sung plainly; processed hooks are missed.
     So the final call comes from the syllable list + the song's structure (hooks repeat every 8 beats) + what the user hears.
  4. Instrumental silent gaps (a cappella stops) are listed too: hooks often sit right before the music slams back.

Usage (from the work folder; times are VIDEO seconds = song seconds - window start):
  py -3.14 find_vocal_hits.py song.wav <window_start_s> <window_len_s> [--word bang] [--strips]
Writes vocal_hits.json; with --strips also scan/vocal_<a>-<b>.png spectrogram strips (green ticks = syllable starts).
Needs: pip install demucs openai-whisper (and CPU torch). Both download model weights on first use: ask the user first.
"""
import argparse, json, os, re, subprocess, sys
import numpy as np, librosa, scipy.signal as sps

ap = argparse.ArgumentParser()
ap.add_argument("song"); ap.add_argument("start", type=float); ap.add_argument("length", type=float)
ap.add_argument("--word", default=None, help="word to look for with Whisper (regex), e.g. bang or \"beam|ビーム\"")
ap.add_argument("--lang", default="en", help="Whisper language of the vocal, e.g. ja for a Japanese song")
ap.add_argument("--strips", action="store_true")
a = ap.parse_args()

os.makedirs("scan", exist_ok=True)
PAD = 1.0                                             # cut 1 s earlier so the first syllable has context
win = os.path.join("scan", "song_win.wav")
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(a.start - PAD, 0):.3f}", "-t", f"{a.length + PAD + 1:.3f}",
                "-i", a.song, "-ar", "44100", "-ac", "2", win], check=True)
off = min(PAD, a.start)
voc = os.path.join("scan", "sep", "htdemucs", "song_win", "vocals.wav")
if not os.path.exists(voc):
    subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "--two-stems", "vocals", "-o", os.path.join("scan", "sep"), win], check=True)
inst = voc.replace("vocals.wav", "no_vocals.wav")

P = None
if os.path.exists("beats.json"):
    P = json.load(open("beats.json"))["beat_period"]

sr, hop = 22050, 128
y, _ = librosa.load(voc, sr=sr, mono=True); y = y[int(off * sr):]
yi, _ = librosa.load(inst, sr=sr, mono=True); yi = yi[int(off * sr):]
rms = 20 * np.log10(librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0] + 1e-6)
rms_i = 20 * np.log10(librosa.feature.rms(y=yi, frame_length=2048, hop_length=hop)[0] + 1e-6)
on = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, aggregate=np.median, n_mels=64, fmax=6000)
f0, vf, _ = librosa.pyin(y, fmin=120, fmax=900, sr=sr, frame_length=2048, hop_length=hop)
t = np.arange(len(on)) * hop / sr
pk, _ = sps.find_peaks(on, height=np.percentile(on, 80), distance=int(0.07 * sr / hop))

hits = []
for p in pk:
    if t[p] > a.length:
        continue
    j = slice(p, p + int(0.12 * sr / hop))
    ff = f0[j][vf[j]] if vf[j].any() else []
    hits.append({"t": round(float(t[p]), 3), "beat": round(float(t[p] / P), 3) if P else None, "onset": round(float(on[p]), 2),
                 "level_db": round(float(rms[p:p + 12].max()), 1), "pitch": librosa.hz_to_note(np.median(ff)) if len(ff) else None})

# instrumental silent gaps (music stops, vocals only)
quiet = rms_i < (np.median(rms_i) - 25)
gaps, s0 = [], None
for i, q in enumerate(quiet):
    if q and s0 is None:
        s0 = i
    if (not q or i == len(quiet) - 1) and s0 is not None:
        if (i - s0) * hop / sr >= 0.25:
            gaps.append([round(s0 * hop / sr, 2), round(i * hop / sr, 2)])
        s0 = None

words = []
if a.word:
    import whisper
    m = whisper.load_model("small")
    y16, _ = librosa.load(voc, sr=16000, mono=True); y16 = y16[int(off * 16000):]
    loud = np.percentile(rms, 75) - 15                     # Whisper invents words on near-silent stems (intro): keep hits only where someone sings
    for c0 in np.arange(0, a.length, 2.0):                # short overlapping chunks: long ones make Whisper loop, overlap catches words on a boundary
        seg = y16[int(c0 * 16000):int((c0 + 4.0) * 16000)].astype(np.float32)
        pad = np.zeros(8000, np.float32)
        r = m.transcribe(np.concatenate([pad, seg, pad]), language=a.lang, word_timestamps=True, temperature=0.0, condition_on_previous_text=False)
        for s in r["segments"]:
            for w in s.get("words", []):
                t0 = float(c0 + w["start"] - 0.5)
                i0 = max(int(t0 * sr / hop), 0)
                if re.search(a.word, w["word"], re.I) and w["end"] - w["start"] > 0.03 and t0 >= 0 and rms[i0:i0 + int(0.3 * sr / hop)].max() > loud:
                    words.append({"t": round(t0, 2), "end": round(float(c0 + w["end"] - 0.5), 2), "prob": round(float(w["probability"]), 2)})
    words.sort(key=lambda w: w["t"])
    words = [w for i, w in enumerate(words) if i == 0 or w["t"] - words[i - 1]["t"] > 0.25]

json.dump({"window_start": a.start, "syllables": hits, "instrumental_gaps": gaps, "word": a.word, "word_hits": words},
          open("vocal_hits.json", "w"), indent=1)
print(f"{len(hits)} syllable starts, instrumental gaps {gaps}")
if a.word:
    print(f"Whisper '{a.word}' (HINTS ONLY: it invents words on wordless vocals; on Bang Bang it 'heard' 12 bangs in the intro and missed the hook):",
          [(w["t"], w["prob"]) for w in words])
print("strongest syllables (t, beat, onset, level, pitch):")
for h in sorted(hits, key=lambda h: -h["onset"])[:25]:
    print(f"  {h['t']:7.3f}s  beat {h['beat']}  onset {h['onset']:5.2f}  {h['level_db']:6.1f} dB  {h['pitch']}")

if a.strips:
    import cv2
    M = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)), ref=np.max)
    M = M[librosa.fft_frequencies(sr=sr, n_fft=2048) <= 4000]
    for s0_ in np.arange(0, a.length, 6.0):
        s1_ = min(s0_ + 6.0, a.length)
        i0, i1 = int(s0_ * sr / hop), int(s1_ * sr / hop)
        img = cv2.applyColorMap((cv2.resize(np.clip((M[::-1, i0:i1] + 65) / 65, 0, 1), (int((s1_ - s0_) * 300), 380)) * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)
        can = np.zeros((420, img.shape[1], 3), np.uint8); can[:380] = img
        for h in hits:
            if s0_ <= h["t"] < s1_:
                x = int((h["t"] - s0_) * 300); cv2.line(can, (x, 0), (x, 10), (80, 255, 80), 2)
        for s in np.arange(np.ceil(s0_ * 2) / 2, s1_, 0.5):
            x = int((s - s0_) * 300); cv2.putText(can, f"{s:.1f}", (x - 12, 410), 0, 0.42, (230, 230, 230), 1)
        cv2.imwrite(os.path.join("scan", f"vocal_{s0_:.0f}-{s1_:.0f}.png"), can)
    print("strips -> scan/vocal_*.png")
