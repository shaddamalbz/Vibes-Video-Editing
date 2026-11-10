import subprocess, numpy as np
from kitcfg import VIDEO                      # montage.json in the work folder
def read_window(t0, dur, x, y, w, h, scale=None):
    """Yield (frame_time, bgr ndarray) at 60fps for a crop of the video (frame-accurate seek)."""
    vf = f"crop={w}:{h}:{x}:{y}"
    ow, oh = w, h
    if scale:
        ow, oh = scale; vf += f",scale={ow}:{oh}"
    cmd = ["ffmpeg","-hide_banner","-loglevel","error","-ss",f"{t0}","-t",f"{dur}","-i",VIDEO,"-vf",vf,"-r","60","-f","rawvideo","-pix_fmt","bgr24","-"]
    p = subprocess.run(cmd, capture_output=True)
    buf = np.frombuffer(p.stdout, np.uint8)
    n = len(buf)//(ow*oh*3)
    arr = buf[:n*ow*oh*3].reshape(n, oh, ow, 3)
    return [(t0 + k/60.0, arr[k]) for k in range(n)]
