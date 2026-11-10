"""Check that this machine can run the skill. Installs nothing: prints what is missing and the command that adds it.

    python doctor.py          run it inside the project folder (or any work folder under it)

Exit code 0 = the core pipeline (scan -> edit list -> preview/final render -> verify) can run.
"""
import importlib, os, platform, shutil, subprocess, sys

import projcfg

CORE = [("numpy", "numpy"), ("cv2", "opencv-python"), ("soundfile", "soundfile"), ("scipy", "scipy"), ("PIL", "Pillow"),
        ("librosa", "librosa")]
OPTIONAL = [("demucs", "demucs", "separate vocals / game music from effects"),
            ("torch", "torch", "needed by demucs and whisper"),
            ("whisper", "openai-whisper", "find sung words, check voice-over"),
            ("yt_dlp", "yt-dlp", "download a song or reference clip (ask the owner first)")]
OK, BAD, WARN = "[ok]  ", "[MISS]", "[warn]"


def has(mod):
    try:
        importlib.import_module(mod)
        return True
    except Exception as e:                      # a blocked DLL counts as missing too
        return False


def install_hint(tool):
    s = platform.system()
    if tool == "ffmpeg":
        return {"Windows": "winget install Gyan.FFmpeg", "Darwin": "brew install ffmpeg"}.get(s, "sudo apt install ffmpeg")
    return ""


def main():
    c = projcfg.cfg()
    fail = False
    print("project :", c["root"] or f"no {projcfg.NAME} found above {os.getcwd()} (run setup_project.py)")
    print("skill   :", projcfg.SKILL_DIR.replace("\\", "/"))
    print("python  :", sys.version.split()[0], sys.executable)
    if sys.version_info < (3, 10):
        print(BAD, "Python 3.10 or newer is needed")
        fail = True

    ff = shutil.which(projcfg.ffmpeg())
    if not ff:
        print(BAD, "ffmpeg not found ->", install_hint("ffmpeg"), f'(or set "ffmpeg" in {projcfg.NAME})')
        fail = True
    else:
        ver = subprocess.run([ff, "-version"], capture_output=True, text=True, errors="replace").stdout.splitlines()[0]
        print(OK, ver[:70], "|", ff)
        enc = projcfg.encoder()
        have = f" {enc} " in projcfg._encoders()
        print(OK if have else BAD, "H.264 encoder:", enc, "" if have else '-> not in this ffmpeg build; set "encoder" in ' + projcfg.NAME)
        fail |= not have
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, errors="replace").stdout
        for flt in ("loudnorm", "ebur128"):
            ok = f" {flt} " in filters
            print(OK if ok else BAD, "ffmpeg filter", flt)
            fail |= not ok
        if not shutil.which("ffprobe"):
            print(WARN, "no ffprobe: fine, tools/probe.py reads `ffmpeg -i` instead")

    for d in c["extra_pythonpath"]:
        if d not in sys.path:
            sys.path.insert(0, d)
    missing = [pip for mod, pip in CORE if not has(mod)]
    for mod, pip in CORE:
        print(BAD if pip in missing else OK, "python package", pip)
    if missing:
        print("       ->", os.path.basename(sys.executable), "-m pip install", " ".join(missing))
        fail = True
    for mod, pip, why in OPTIONAL:
        print(OK if has(mod) else WARN, f"optional {pip}: {why}")

    for k in projcfg.DIR_KEYS:
        print(OK if os.path.isdir(c[k]) else WARN, f"{k}: {c[k]}")
    try:
        for role in ("black", "bold", "regular"):
            projcfg.font(role)
        print(OK, "fonts")
    except SystemExit as e:
        print(BAD, e)
        fail = True
    b = projcfg.brand()
    print(OK if b.get("logo") else WARN, "channel profile brand.json:", "logo set" if b.get("logo") else "no logo (edits end without a logo card)")
    print("\nRESULT:", "core pipeline cannot run yet, fix the [MISS] lines" if fail else "ready")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
