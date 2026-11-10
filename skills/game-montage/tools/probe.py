"""ffprobe stand-in (for ffmpeg builds that ship no ffprobe).
Parses `ffmpeg -i <file>` and returns an ffprobe-like dict:
  {"format": {"duration": "123.456"}, "streams": [{"codec_type", "codec_name", "width", "height", "r_frame_rate", "nb_frames", "sample_rate"}]}
nb_frames comes from OpenCV's frame count (estimate for mkv).
CLI: python probe.py <file>            -> json
     python probe.py <file> duration   -> seconds only
"""
import json, re, subprocess, sys


def probe(path, frames=False):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    out = {"format": {}, "streams": []}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        out["format"]["duration"] = f"{int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]):.6f}"
    for line in err.splitlines():
        s = re.search(r"Stream #\d+:\d+.*?: (Video|Audio): (\w+)", line)
        if not s:
            continue
        st = {"codec_type": s[1].lower(), "codec_name": s[2]}
        if st["codec_type"] == "video":
            wh = re.search(r", (\d{2,5})x(\d{2,5})", line)
            if wh:
                st["width"], st["height"] = int(wh[1]), int(wh[2])
            fr = re.search(r"([\d.]+) fps", line) or re.search(r"([\d.]+) tbr", line)
            if fr:
                f = float(fr[1])
                st["r_frame_rate"] = f"{round(f * 1000)}/1000" if f != int(f) else f"{int(f)}/1"
            if frames:
                import cv2
                c = cv2.VideoCapture(path)
                st["nb_frames"] = str(int(c.get(cv2.CAP_PROP_FRAME_COUNT)))
                c.release()
        else:
            sr = re.search(r"(\d+) Hz", line)
            if sr:
                st["sample_rate"] = sr[1]
        out["streams"].append(st)
    return out


def duration(path):
    d = probe(path)["format"].get("duration")
    return float(d) if d else None


if __name__ == "__main__":
    p = probe(sys.argv[1], frames=True)
    print(p["format"].get("duration") if sys.argv[2:] == ["duration"] else json.dumps(p, indent=1))
