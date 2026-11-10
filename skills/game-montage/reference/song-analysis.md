# Song analysis

## Getting the song (needs the user's yes)
`yt-dlp --js-runtimes node -x --audio-format wav -o song.%(ext)s "<url>"` (without `--js-runtimes node` YouTube returns HTTP 403).
The user uses songs for experiments only; still ask before every download.

## Beat grid
1. `analyze_song2.py song.wav`: tempo candidates (librosa often reports double-time, e.g. 169 for an 85 BPM song).
2. `analyze_song.py song.wav <bpm> beats.json`: constant-tempo grid (K-pop masters are constant), beat energy, bars, drop candidates.
3. Choose a window (`START_BEAT`, `WINDOW_BEATS`) that starts calm and contains one or two drops. 120 beats at 152 BPM = 47.4 s.

## Sung moments (hook words like "bang")
`find_vocal_hits.py song.wav <window start s> <window length s> --word bang --strips`
- Demucs splits vocals from the music; syllable starts, pitch and level come from the clean vocal.
- Whisper is a hint at best: it found the first plainly sung "bang", missed the processed hook, and invented a dozen "bang"s on the wordless intro vocals. Never place kills from Whisper alone.
- Tested on Bang Bang: the script lists the a cappella stop (21.34-22.04 s) and the hook syllables at 22.08, 25.23, 28.38, 31.54 s among the strongest onsets.
- `instrumental_gaps` lists a cappella stops; hooks often land right when the music comes back.
- Hooks repeat on a fixed bar pattern (in "Bang Bang": four "bang bang" lines every 8 beats, the two words one beat apart).

What went wrong first, so it is not repeated:
- Centre-channel extraction + pitch tracking on the full mix "found" B3 notes that were bass/kick. The kills ended up 1-2 s before the real hook.
- Placing pairs on loud transients of the mix: those were drum fills, not the vocal.
If the result is still uncertain, ask the user which second they hear the word; they were right both times.

## Placing kills
- Kill frame on the beat (or on the measured vocal onset for hook words, a few ms off the grid on purpose). Verify kill-vs-target < 1 output frame.
- Song structure from the first montage (window beats): intro 0-20 (relaxed), lead-in vocal 20-24, drop 24, chorus, a cappella stop, hook lines, break before drop 2, drop 2, outro dip with the end card.
