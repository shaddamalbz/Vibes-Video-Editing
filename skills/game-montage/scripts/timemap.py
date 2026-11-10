"""Speed-ramp time map shared by the renderer (video) and the mixer (audio events are retimed through it).

x = output seconds relative to the kill frame (negative = before the kill)
offset(x) = source seconds relative to the kill frame
Speed spec (in edl.json clip["speed"]):
  {"keys": [[beats_rel_kill, speed], ...], "ramp_pow": ...}   keyframes, smooth (log-speed, smoothstep) between keys.
      A jump (snap) is two keys a hair apart, e.g. [-0.001, 0.3], [0.0, 1.4].
  {"ramp": [s0, s1], ...} / {"pre":..,"slow":..,"slow_dur":..,"ease":..,"post_boost":..,"post_decay":..}  legacy formats
"""
import math
import numpy as np


def smoothstep(a, b, x):
    if b == a:                                       # zero-length ramp (a clip that starts on its anchor): a step
        return np.where(np.asarray(x) >= b, 1.0, 0.0)
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class TimeMap:
    def __init__(self, sp, pre_len, post_len, beat_period=None, dx=0.0005):
        self.sp, self.pre_len = sp, pre_len
        if "keys" in sp:
            ks = sorted(sp["keys"], key=lambda k: k[0])
            self.kx = np.array([k[0] * beat_period for k in ks], dtype=float)
            self.kl = np.log(np.array([k[1] for k in ks], dtype=float))
        xs = np.arange(-(pre_len + 1.2), post_len + 1.6, dx)
        s = np.array([self.speed(x) for x in xs])
        cum = np.concatenate([[0.0], np.cumsum((s[1:] + s[:-1]) * 0.5 * dx)])
        cum -= np.interp(0.0, xs, cum)
        self.xs, self.cum, self.s = xs, cum, s

    def speed(self, x):
        sp = self.sp
        if "keys" in sp:
            kx, kl = self.kx, self.kl
            if x <= kx[0]:
                return math.exp(kl[0])
            if x >= kx[-1]:
                return math.exp(kl[-1])
            i = int(np.searchsorted(kx, x))
            u = (x - kx[i - 1]) / (kx[i] - kx[i - 1])
            w = u * u * (3 - 2 * u)
            return math.exp(kl[i - 1] + (kl[i] - kl[i - 1]) * w)
        if x >= 0:
            return 1.0 + (sp.get("post_boost", 1.0) - 1.0) * math.exp(-x / sp.get("post_decay", 0.2))
        if "ramp" in sp:
            s0, s1 = sp["ramp"]
            u = min(max((x + self.pre_len) / self.pre_len, 0.0), 1.0) ** sp.get("ramp_pow", 1.0)
            return s0 + (s1 - s0) * u
        sd, e = sp["slow_dur"], sp["ease"]
        if x > -sd:
            return sp["slow"]
        if x > -(sd + e):
            w = float(smoothstep(-(sd + e), -sd, x))
            return sp["pre"] + (sp["slow"] - sp["pre"]) * w
        return sp["pre"]

    def offset(self, x):
        return float(np.interp(x, self.xs, self.cum))

    def inverse(self, dt):
        """output seconds (relative to the kill) at which the source time t_k + dt is shown"""
        return float(np.interp(dt, self.cum, self.xs))

    def speed_at(self, x):
        return float(np.interp(x, self.xs, self.s))
