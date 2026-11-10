"""Ice looks for render.py (FF XVI Timekeeper "Frozen in Time", Oct 2026).

effect "frost" (presets freeze_1 / freeze_2): the frame turns icy (cooler, paler), frost creeps in from the edges toward a focus point
with ragged crystal fronds, and (freeze_2) ice cracks spread from a point. Pair it with a speed key below 0.05 (freeze frame).
transition "ice_shatter" (preset ice_shatter_1): the outgoing (frozen) frame breaks into glass shards that fly off and reveal the next clip.

All textures are procedural (numpy / OpenCV) and cached per frame size + seed, so preview and final look the same.
"""
import math
import numpy as np, cv2

_CACHE = {}
ICE = np.array([255, 246, 228], np.float32)          # BGR: cyan-white frost
GLOW = np.array([255, 225, 150], np.float32)         # BGR: icy blue glow around cracks


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _noise(W, H, seed):
    rng = np.random.default_rng(seed)
    n = np.zeros((H, W), np.float32)
    for cells, w in ((5, 0.5), (13, 0.3), (36, 0.2)):
        g = rng.random((int(cells * H / W) + 2, cells + 2)).astype(np.float32)
        n += w * cv2.resize(g, (W, H), interpolation=cv2.INTER_CUBIC)
    return (n - n.min()) / (n.max() - n.min() + 1e-6)


def _frond(img, x, y, a, L, depth, rng, lw):
    x2, y2 = x + math.cos(a) * L, y + math.sin(a) * L
    cv2.line(img, (int(x), int(y)), (int(x2), int(y2)), float(rng.uniform(0.45, 1.0)), lw, cv2.LINE_AA)
    if depth > 0:
        for _ in range(int(rng.integers(2, 4))):
            f = rng.uniform(0.15, 0.85)
            bx, by = x + (x2 - x) * f, y + (y2 - y) * f
            for sgn in (-1, 1):
                _frond(img, bx, by, a + sgn * math.radians(rng.uniform(50, 70)), L * rng.uniform(0.22, 0.42), depth - 1, rng, lw)


def _textures(W, H, seed):
    key = ("tex", W, H, seed)
    if key not in _CACHE:
        s = min(W, H) / 1080.0
        rng = np.random.default_rng(seed + 11)
        cry = np.zeros((H, W), np.float32)
        lw = max(1, int(round(1.3 * s)))
        for _ in range(int(1100 * (W * H) / (1080 * 1920)) + 60):
            _frond(cry, rng.random() * W, rng.random() * H, rng.uniform(0, math.pi), rng.uniform(30, 120) * s, 2, rng, lw)
        cry = np.clip(cv2.GaussianBlur(cry, (0, 0), 0.6 * s + 0.4), 0, 1)
        fine = _noise(W, H, seed + 5)
        fine = cv2.resize(cv2.resize(fine, (W // 3, H // 3)), (W, H))
        _CACHE[key] = (_noise(W, H, seed), cry, fine)
    return _CACHE[key]


def _field(W, H, focus):
    """0 at the frame edge .. 1 at the focus point (rounded-rectangle distance, so frost fills the corners first)"""
    key = ("field", W, H, tuple(focus))
    if key not in _CACHE:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        fx, fy = focus[0] * W, focus[1] * H
        nx = np.where(xx < fx, (fx - xx) / max(fx, 1), (xx - fx) / max(W - fx, 1))
        ny = np.where(yy < fy, (fy - yy) / max(fy, 1), (yy - fy) / max(H - fy, 1))
        _CACHE[key] = (1.0 - (nx ** 4 + ny ** 4) ** 0.25).astype(np.float32)
    return _CACHE[key]


def _cracks(W, H, center, seed):
    """branching crack polylines from the centre: list of (start fraction 0..1, p0, p1, width scale)"""
    key = ("crack", W, H, tuple(center), seed)
    if key not in _CACHE:
        rng = np.random.default_rng(seed + 23)
        s = min(W, H) / 1080.0
        cx, cy = center[0] * W, center[1] * H
        segs = []

        def walk(x, y, a, length, f0, f1, wsc, depth):
            n = max(4, int(length / (34 * s)))
            for i in range(n):
                a += rng.normal(0, 0.16)
                step = length / n
                x2, y2 = x + math.cos(a) * step, y + math.sin(a) * step
                fa = f0 + (f1 - f0) * i / n
                segs.append((fa, (x, y), (x2, y2), wsc * (1 - 0.6 * i / n)))
                if depth > 0 and rng.random() < 0.10:
                    walk(x2, y2, a + rng.choice([-1, 1]) * rng.uniform(0.5, 1.1), length * rng.uniform(0.25, 0.45),
                         fa, fa + (f1 - fa) * 0.8, wsc * 0.6, depth - 1)
                x, y = x2, y2

        R = math.hypot(W, H) * 0.75
        for k in range(7):
            a = 2 * math.pi * k / 7 + rng.uniform(-0.3, 0.3)
            walk(cx, cy, a, R * rng.uniform(0.55, 1.0), 0.0, 1.0, 1.0, 1)
        # a small star of short cracks right at the impact point
        for k in range(6):
            a = rng.uniform(0, 2 * math.pi)
            walk(cx, cy, a, 60 * s * rng.uniform(0.6, 1.3), 0.0, 0.2, 0.9, 0)
        _CACHE[key] = segs
    return _CACHE[key]


def apply(img, st, res, seed=7):
    """st: {"u": frost growth 0..1, "crack": crack growth 0..1, "focus": [x, y], "center": [x, y], "grade": strength}"""
    H, W = img.shape[:2]
    u, cr = float(st.get("u", 0.0)), float(st.get("crack", 0.0))
    if u <= 0.001 and cr <= 0.001:
        return img
    f = img.astype(np.float32)
    g = u * st.get("grade", 1.0)
    if g > 0:                                            # icy grade: cooler, paler, a bit lifted
        gray = f.mean(2, keepdims=True)
        f = f * (1 - 0.35 * g) + gray * (0.35 * g)
        f = f * (1 + g * np.array([0.12, 0.03, -0.14], np.float32)) + g * np.array([20, 9, -6], np.float32)
        f = f * (1 - 0.04 * g) + 255 * 0.02 * g
    if u > 0.001:                                        # frost creeping from the edges toward the focus point
        noise, cry, fine = _textures(W, H, seed)
        d = _field(W, H, st.get("focus", [0.5, 0.5]))
        thr = 0.50 * _smooth(0.0, 1.0, u) ** 0.8
        front = (thr - d + (noise - 0.5) * 0.30) / 0.12
        m = np.clip(front, 0, 1)
        if m.max() > 0:
            deep = np.clip(front / 4.0, 0, 1)            # thicker frost further behind the front
            blur = cv2.GaussianBlur(f, (0, 0), 7 * res + 0.5)
            mb = (m * (0.25 + 0.45 * deep))[..., None]
            f = f * (1 - mb) + blur * mb                 # frosted glass
            a = m * np.clip(0.08 + 0.72 * cry + 0.12 * fine + 0.32 * deep, 0, 0.92)
            rim = np.clip(1 - np.abs(front - 0.5) / 0.6, 0, 1) * (m > 0)      # bright rim along the advancing front
            a = np.maximum(a, rim * 0.55 * (0.4 + 0.6 * cry))
            f = f * (1 - a[..., None]) + ICE * a[..., None]
    if cr > 0.001:                                       # ice cracks spreading from the impact point
        layer = np.zeros((H, W), np.float32)
        shadow = np.zeros((H, W), np.float32)
        base_w = max(1.0, 4.0 * res)
        sh = max(1, int(round(2 * res)))
        for fa, p0, p1, wsc in _cracks(W, H, st.get("center", [0.5, 0.5]), seed):
            if fa <= cr:
                w_ = max(1, int(round(base_w * wsc)))
                a0, a1 = (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1]))
                cv2.line(shadow, (a0[0] + sh, a0[1] + sh), (a1[0] + sh, a1[1] + sh), 1.0, w_, cv2.LINE_AA)
                cv2.line(layer, a0, a1, 1.0, w_, cv2.LINE_AA)
        glow = cv2.GaussianBlur(layer, (0, 0), 3 * res + 1)
        f = f * (1 - 0.45 * shadow[..., None])                      # the dark side of the split
        f = f + glow[..., None] * GLOW * 0.35 * min(1.0, cr * 3)
        f = f * (1 - layer[..., None]) + np.array([255, 252, 245], np.float32) * layer[..., None]
    return np.clip(f, 0, 255).astype(np.uint8)


def _shards(W, H, center, seed, n=46):
    key = ("shards", W, H, tuple(center), seed)
    if key not in _CACHE:
        rng = np.random.default_rng(seed + 31)
        cx, cy = center[0] * W, center[1] * H
        R = math.hypot(W, H)
        pts = []
        while len(pts) < n:                              # denser near the impact point (small shards there, big ones outside)
            r = (rng.random() ** 1.7) * R * 0.75
            a = rng.uniform(0, 2 * math.pi)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            if 1 <= x < W - 1 and 1 <= y < H - 1:
                pts.append((float(x), float(y)))
        sub = cv2.Subdiv2D((0, 0, W, H))
        for p in pts:
            sub.insert(p)
        facets, cents = sub.getVoronoiFacetList([])
        frame = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], np.float32)
        out = []
        for poly, c in zip(facets, cents):
            ok, clip = cv2.intersectConvexConvex(np.array(poly, np.float32), frame)
            if ok <= 0 or clip is None or len(clip) < 3:
                continue
            poly = clip.reshape(-1, 2)
            cen = poly.mean(0)
            dv = cen - np.array([cx, cy])
            dist = np.linalg.norm(dv)
            dv = dv / dist if dist > 1 else np.array([0.0, -1.0])
            out.append(dict(poly=poly, cen=cen, dir=dv, dist=dist / R, spd=rng.uniform(0.6, 1.25),
                            spin=rng.uniform(-50, 50), lag=rng.uniform(0.0, 0.18), lift=rng.uniform(-0.2, 0.15)))
        _CACHE[key] = out
    return _CACHE[key]


def shatter(A, B, p, res, center=(0.5, 0.5), seed=7):
    """the frozen frame A breaks into shards flying outward (toward the camera, then falling), revealing B. p: 0..1 over the transition"""
    H, W = A.shape[:2]
    out = B.astype(np.float32)
    out = out + (255 - out) * (0.55 * max(0.0, 1 - p / 0.35) ** 2)            # flash of the break on the revealed clip
    edge = A.copy()
    for s in _shards(W, H, center, seed):                                      # glinting shard edges
        cv2.polylines(edge, [s["poly"].astype(np.int32)], True, (255, 250, 238), max(1, int(round(2 * res))), cv2.LINE_AA)
    for s in sorted(_shards(W, H, center, seed), key=lambda s: -s["dist"]):  # far shards first, the ones near the impact on top
        q = max(0.0, (p - s["lag"] * (1 - s["dist"])) / (1 - s["lag"] * (1 - s["dist"]) + 1e-6))
        if q <= 0:
            q = 0.0
        e = q ** 1.5
        off = s["dir"] * (0.25 + 0.75 * s["spd"]) * H * 0.75 * e + np.array([0.0, (s["lift"] * e + 0.55 * q * q) * H])
        sc = 1.0 + 0.35 * e * (1.2 - s["dist"])                                # shards come toward the camera a little
        ang = s["spin"] * e
        alpha = 1.0 - _smooth(0.55, 1.0, q)
        if alpha <= 0.01:
            continue
        cx, cy = s["cen"]
        M = cv2.getRotationMatrix2D((float(cx), float(cy)), float(ang), float(sc))
        M[:, 2] += off
        x0, y0 = s["poly"].min(0).astype(int)
        x1, y1 = s["poly"].max(0).astype(int) + 1
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], np.float64) @ M.T
        bx0, by0 = np.floor(corners.min(0)).astype(int) - 2
        bx1, by1 = np.ceil(corners.max(0)).astype(int) + 2
        bx0, by0, bx1, by1 = max(bx0, 0), max(by0, 0), min(bx1, W), min(by1, H)
        if bx1 <= bx0 or by1 <= by0:
            continue
        Ml = M.copy()
        Ml[:, 2] -= [bx0, by0]
        mask = np.zeros((H, W), np.uint8)
        cv2.fillConvexPoly(mask, s["poly"].astype(np.int32), 255, cv2.LINE_AA)
        piece = cv2.warpAffine(edge, Ml, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        mk = cv2.warpAffine(mask, Ml, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        a = (mk.astype(np.float32) / 255.0 * alpha)[..., None]
        shade = 1.0 + 0.25 * math.sin(math.radians(ang) * 2 + s["spd"] * 3)    # shards catch the light as they turn
        reg = out[by0:by1, bx0:bx1]
        out[by0:by1, bx0:bx1] = reg * (1 - a) + np.clip(piece.astype(np.float32) * shade, 0, 255) * a
    return np.clip(out, 0, 255).astype(np.uint8)
