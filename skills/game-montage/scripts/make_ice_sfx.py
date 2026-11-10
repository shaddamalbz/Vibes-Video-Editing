"""Synthesize the ice sound effects for the freeze look (no downloads): ice_freeze.wav (crystalline swell as the frame freezes),
ice_crack.wav (sharp crack), ice_shatter.wav (glass breaking + tinkling shards). 48 kHz stereo, peaks at -1 dBFS.
usage: make_ice_sfx.py [out_dir]   (default: the project's reusable assets folder, SFX/)
"""
import os, sys
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
import projcfg
OUT = sys.argv[1] if len(sys.argv) > 1 else projcfg.path("reusable_dir", "SFX")
rng = np.random.default_rng(1601)


def bp(x, lo, hi):
    return sosfilt(butter(4, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def hp(x, f):
    return sosfilt(butter(4, f, "highpass", fs=SR, output="sos"), x)


def lp(x, f):
    return sosfilt(butter(4, f, "lowpass", fs=SR, output="sos"), x)


def ping(dur, f0, decay, n_part=3):
    """a small glassy 'tink': a few inharmonic partials with fast decay"""
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    for k in range(n_part):
        f = f0 * (1, 2.32, 3.87, 5.4)[k] * rng.uniform(0.98, 1.02)
        y += (0.7 ** k) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / (decay / (1 + 0.6 * k)))
    return y * np.minimum(t / 0.0015, 1)


def add(buf, y, t0, gain, pan):
    i = int(t0 * SR)
    j = min(i + len(y), len(buf))
    if j <= i:
        return
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:j, 0] += y[:j - i] * gain * l
    buf[i:j, 1] += y[:j - i] * gain * r


def norm(buf, peak_db=-1.0):
    buf = buf - buf.mean(0)
    return (buf / (np.abs(buf).max() + 1e-9) * 10 ** (peak_db / 20)).astype(np.float32)


def freeze():
    L = 1.1
    buf = np.zeros((int(L * SR), 2))
    t = np.arange(len(buf)) / SR
    hiss = bp(rng.normal(0, 1, len(buf)), 3500, 11000)                 # icy hiss swelling in, then cut short
    env = np.clip(t / 0.62, 0, 1) ** 2.2 * np.exp(-np.clip(t - 0.62, 0, None) / 0.12)
    for ch in range(2):
        buf[:, ch] += 0.35 * hiss * env * rng.uniform(0.9, 1.1)
    sweep = np.sin(2 * np.pi * np.cumsum(900 + 2600 * np.clip(t / 0.62, 0, 1) ** 2) / SR)      # rising shimmer
    buf += (0.08 * sweep * env)[:, None]
    for _ in range(70):                                                # crystals forming: pings get denser toward the freeze
        t0 = 0.62 * (1 - rng.random() ** 2.2)
        add(buf, ping(0.25, rng.uniform(2400, 7800), rng.uniform(0.03, 0.08)), t0, rng.uniform(0.05, 0.16) * (0.3 + t0), rng.uniform(-0.8, 0.8))
    lock = hp(rng.normal(0, 1, int(0.05 * SR)), 1500) * np.exp(-np.arange(int(0.05 * SR)) / SR / 0.008)   # the 'lock' click
    add(buf, lock, 0.62, 0.9, 0.0)
    thump = np.sin(2 * np.pi * 70 * np.arange(int(0.4 * SR)) / SR) * np.exp(-np.arange(int(0.4 * SR)) / SR / 0.09)
    add(buf, thump, 0.62, 0.7, 0.0)
    return norm(buf)


def crack():
    L = 0.6
    buf = np.zeros((int(L * SR), 2))
    for k in range(5):                                                 # a fast series of cracks
        t0 = 0.004 * k + rng.uniform(0, 0.012) * k
        n = int(0.09 * SR)
        y = hp(rng.normal(0, 1, n), 1200) * np.exp(-np.arange(n) / SR / rng.uniform(0.006, 0.02))
        add(buf, y, t0, 1.0 / (1 + 0.4 * k), rng.uniform(-0.5, 0.5))
    n = int(0.35 * SR)
    body = bp(rng.normal(0, 1, n), 300, 3000) * np.exp(-np.arange(n) / SR / 0.05)
    add(buf, body, 0.0, 0.6, 0.0)
    thump = np.sin(2 * np.pi * 110 * np.arange(n) / SR) * np.exp(-np.arange(n) / SR / 0.06)
    add(buf, thump, 0.0, 0.8, 0.0)
    for _ in range(14):
        add(buf, ping(0.2, rng.uniform(3000, 9000), 0.04), rng.uniform(0.01, 0.25), rng.uniform(0.04, 0.12), rng.uniform(-0.8, 0.8))
    return norm(buf)


def shatter():
    L = 1.8
    buf = np.zeros((int(L * SR), 2))
    n = int(0.12 * SR)                                                 # the break: broadband smash
    smash = lp(rng.normal(0, 1, n), 9000) * np.exp(-np.arange(n) / SR / 0.03)
    add(buf, smash, 0.0, 1.0, -0.15)
    add(buf, lp(rng.normal(0, 1, n), 9000) * np.exp(-np.arange(n) / SR / 0.03), 0.003, 1.0, 0.15)
    m = int(0.5 * SR)
    thump = np.sin(2 * np.pi * 62 * np.arange(m) / SR) * np.exp(-np.arange(m) / SR / 0.11)
    add(buf, thump, 0.0, 0.9, 0.0)
    for _ in range(220):                                               # shards tinkling and landing
        t0 = rng.exponential(0.28)
        if t0 > L - 0.3:
            continue
        g = rng.uniform(0.05, 0.3) * np.exp(-t0 / 0.6)
        add(buf, ping(0.3, rng.uniform(2000, 10500), rng.uniform(0.015, 0.07), int(rng.integers(2, 5))), t0, g, rng.uniform(-0.95, 0.95))
    k = int(1.2 * SR)                                                  # debris hiss
    deb = bp(rng.normal(0, 1, k), 2500, 12000) * np.exp(-np.arange(k) / SR / 0.25)
    add(buf, deb, 0.02, 0.18, -0.4)
    add(buf, bp(rng.normal(0, 1, k), 2500, 12000) * np.exp(-np.arange(k) / SR / 0.25), 0.02, 0.18, 0.4)
    return norm(buf)


os.makedirs(OUT, exist_ok=True)
for name, fn in (("ice_freeze.wav", freeze), ("ice_crack.wav", crack), ("ice_shatter.wav", shatter)):
    y = fn()
    sf.write(os.path.join(OUT, name), y, SR, subtype="PCM_16")
    print(f"{name}: {len(y) / SR:.2f} s")
