import json, sys, numpy as np, soundfile as sf
from edl_lib import load_edl, timeline
fps=float(sys.argv[1]) if len(sys.argv)>1 else 30
y,sr=sf.read(f"scan/mix_{int(fps)}.wav"); y=y.mean(1) if y.ndim>1 else y
tl,_=timeline(load_edl(),fps)
def rms(a,b): s=y[int(a*sr):int(b*sr)]; return 20*np.log10(np.sqrt((s**2).mean())+1e-9)
def pk(a,b): s=y[int(a*sr):int(b*sr)]; return 20*np.log10(np.abs(s).max()+1e-9)
print("final mix, dBFS: song-only 0.8s before | hit 0-0.4s (rms / peak) | tail 0.4-0.9s  -> hit vs before")
d=[]
for c in tl:
    if c.get("calm"): continue
    t=c["n_k"]/fps; b=rms(t-1.0,t-0.35); h=rms(t,t+0.4); d.append(h-b)
    print(f"  {c['id']} kill#{str(c['kill_id']):>3s}  before {b:6.1f}  hit {h:6.1f} / {pk(t,t+0.4):5.1f}  tail {rms(t+0.4,t+0.9):6.1f}  -> {h-b:+5.1f} dB")
print(f"median hit vs before: {np.median(d):+.1f} dB (min {min(d):+.1f})")
