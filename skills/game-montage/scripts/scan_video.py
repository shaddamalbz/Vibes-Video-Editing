"""Kill detection stage 0: one pass over the recording with FFmpeg (GPU decode).
  scan/kf.raw, scan/cb.raw   5 fps crops: killfeed (top right) and centre-bottom kill icon, for detect_coarse.py
  scan/game_audio.wav        mono 22.05 kHz game audio, for detect_events.py / finalize_kills.py (audio confirmation)
  scan/game_audio_st48.wav   stereo 48 kHz game audio, for mix_audio.py (kill hits, gunshots)
Crops assume a 1920x1080 recording with the default Valorant HUD.
"""
import os, subprocess
from kitcfg import VIDEO, HERE
import projcfg

scan = os.path.join(HERE, "scan")
os.makedirs(scan, exist_ok=True)
v = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
print("audio ...")
subprocess.run(v + ["-i", VIDEO, "-vn", "-ac", "1", "-ar", "22050", os.path.join(scan, "game_audio.wav")], check=True)
subprocess.run(v + ["-i", VIDEO, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", os.path.join(scan, "game_audio_st48.wav")], check=True)
print("5 fps HUD crops ...")
subprocess.run(v + [*projcfg.hwaccel(), "-i", VIDEO, "-filter_complex",
                    "[0:v]fps=5,split=2[a][b];[a]crop=480:360:1440:60,scale=160:120[kf];[b]crop=600:300:660:640,scale=200:100[cb]",
                    "-map", "[kf]", "-f", "rawvideo", "-pix_fmt", "bgr24", os.path.join(scan, "kf.raw"),
                    "-map", "[cb]", "-f", "rawvideo", "-pix_fmt", "bgr24", os.path.join(scan, "cb.raw")], check=True)
print("scan done ->", scan)
