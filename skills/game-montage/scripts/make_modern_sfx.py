"""Synthesize "modern edit" sounds (no downloads) into Reuseable Assets/SFX (13 Oct 2026, Wukong first-time edits: the user wanted meme
edits that are more advanced, not tacky / dated -> sound design instead of vine booms):
  sub_drop.wav  : deep 808-style drop (75 -> 38 Hz, 0.9 s) with a soft click on top: the "death" weight under a freeze
  hud_tick.wav  : short clean UI tick (counter step)
  riser.wav     : 1.6 s filtered-noise riser + rising tone, ends on a hard stop (before a payoff)
  whoosh.wav    : 0.45 s air whoosh (cut accent)
tape_stop(y, sr, dur) is importable: slows a snippet to a stop (turntable / tape power-down).
"""
import numpy as np, soundfile as sf

SR = 48000
import projcfg
OUT = projcfg.path("reusable_dir", "SFX") + "/"
rng = np.random.default_rng(7)


def norm(x, pk=-1.0):
    return (x / (np.abs(x).max() + 1e-9) * 10 ** (pk / 20)).astype(np.float32)


def lp(x, a):                                   # one-pole low-pass, a in (0,1): smaller = darker
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def sub_drop():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 38 + 37 * np.exp(-t / 0.12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.42) * np.minimum(1, t / 0.004)
    body = np.tanh(1.6 * body)
    click = lp(rng.standard_normal(n), 0.35) * np.exp(-t / 0.006) * 0.5
    return norm(body + click, -1.0)


def hud_tick():
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 2350 * t) * np.exp(-t / 0.012) + 0.5 * np.sin(2 * np.pi * 4700 * t) * np.exp(-t / 0.006)
    click = rng.standard_normal(n) * np.exp(-t / 0.0015) * 0.4
    return norm(tone + click, -3.0)


def riser():
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    u = t / t[-1]
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # sweep a resonant-ish band upward by mixing progressively brighter low-passed noise
    for k, a in enumerate(np.linspace(0.02, 0.6, 12)):
        w = np.clip(u * 12 - k, 0, 1) * np.clip(k + 2 - u * 12, 0, 1)
        out += lp(noise, a) * w
    tone = np.sin(2 * np.pi * np.cumsum(180 + 900 * u ** 2) / SR) * 0.25
    env = u ** 2.2
    return norm((out + tone) * env, -2.0)


def whoosh():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    u = t / t[-1]
    env = np.sin(np.pi * u) ** 2
    x = lp(rng.standard_normal(n), 0.08) * env + lp(rng.standard_normal(n), 0.3) * env * 0.3
    return norm(x, -3.0)


def gong():
    """temple gong (user, 13 Oct 2026: the tape stop + sub drop on deaths sounded bad -> something satisfying that fits Wukong):
    inharmonic partials with a soft strike, a slow bloom of the mid partials, slight beating pairs and a long low tail"""
    n = int(3.2 * SR)
    t = np.arange(n) / SR
    f0 = 92.0
    ratios = [1.0, 1.52, 2.08, 2.63, 3.17, 3.81, 4.49, 5.36, 6.12, 7.03]
    out = np.zeros(n)
    for k, r in enumerate(ratios):
        amp = 1.0 / (1 + 0.55 * k)
        tau = 2.6 / (1 + 0.45 * k)
        bloom = 1 - np.exp(-t / (0.004 + 0.035 * min(k, 4)))          # higher partials swell in a little later
        for det in (-0.35, 0.35):                                      # beating pair
            f = f0 * r * (1 - 0.012 * np.exp(-t / 0.4)) + det          # tiny pitch sag right after the strike
            out += amp * bloom * np.exp(-t / tau) * np.sin(2 * np.pi * np.cumsum(f) / SR + rng.uniform(0, 6.28))
    strike = lp(rng.standard_normal(n), 0.25) * np.exp(-t / 0.012) * 0.8
    body = lp(out, 0.5)
    return norm(np.tanh(0.9 * (body + strike)), -1.0)


def woodblock():
    """muyu temple woodblock 'tok': short, bright, satisfying; for fast repeated deaths and counter steps"""
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * 820 * t) * np.exp(-t / 0.045) + 0.45 * np.sin(2 * np.pi * 1690 * t) * np.exp(-t / 0.018)
            + 0.25 * np.sin(2 * np.pi * 410 * t) * np.exp(-t / 0.06))
    click = lp(rng.standard_normal(n), 0.5) * np.exp(-t / 0.0025) * 0.7
    return norm(tone + click, -2.0)


def tape_stop(y, sr=SR, dur=0.5):
    """y (n, ch): play from the start with the rate falling 1 -> 0 over dur (quadratic), like a turntable power-down"""
    m = int(dur * sr)
    rate = (1 - np.arange(m) / m) ** 1.6
    pos = np.cumsum(rate)
    pos = pos[pos < len(y) - 1]
    out = np.stack([np.interp(pos, np.arange(len(y)), y[:, c]) for c in range(y.shape[1])], 1)
    out *= np.linspace(1, 0.2, len(out))[:, None]
    return out.astype(np.float32)


if __name__ == "__main__":
    for name, fn in (("sub_drop", sub_drop), ("hud_tick", hud_tick), ("riser", riser), ("whoosh", whoosh), ("gong", gong),
                     ("woodblock", woodblock)):
        y = fn()
        sf.write(OUT + name + ".wav", np.stack([y, y], 1), SR)
        print(OUT + name + ".wav", f"{len(y) / SR:.2f} s")
