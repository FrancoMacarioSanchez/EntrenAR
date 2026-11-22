"""Paso 1: soldar, espejar, escalar a 1,75 m y ubicar el cuerpo (Y arriba, mirando a +Z, pies en y=0)."""
import numpy as np


def weld(P, F, tol):
    q = np.round(P / tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    F2 = inv[F]
    F2 = F2[(F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])]
    return P[first], F2


def border_edges(F):
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    u, c = np.unique(e, axis=0, return_counts=True)
    return u[c == 1]


def prepare(P, F, height=1.75, log=print):
    span = np.ptp(P, 0).max()
    P, F = weld(P, F, span * 2e-5)
    log(f"soldado: {len(P)} vértices, {len(F)} triángulos, bordes abiertos {len(border_edges(F))}")
    # plano del espejo: la x mínima (la mitad modelada está en x ≥ plano)
    x0 = P[:, 0].min()
    P = P - [x0, 0, 0]
    tol = span * 1e-4
    on_plane = np.abs(P[:, 0]) < tol
    P[on_plane, 0] = 0
    M = P * [-1, 1, 1]
    n = len(P)
    # los vértices del plano se comparten; el resto se duplica
    idx = np.arange(n)
    mirror_idx = np.where(on_plane, idx, n + np.cumsum(~on_plane) - 1)
    Pm = np.concatenate([P, M[~on_plane]])
    Fm = mirror_idx[F][:, ::-1]  # invertir orden para mantener las normales hacia afuera
    P, F = Pm, np.concatenate([F, Fm])
    log(f"espejado: {len(P)} vértices, {len(F)} triángulos, bordes abiertos {len(border_edges(F))}")
    # escala y ubicación
    s = height / np.ptp(P[:, 1])
    P = (P - [0, P[:, 1].min(), 0]) * s
    y = P[:, 1]
    torso = P[(y > 0.9) & (y < 1.2) & (np.abs(P[:, 0]) < 0.2)]
    P[:, 2] -= (torso[:, 2].min() + torso[:, 2].max()) / 2
    return P, F


def adjacency_edges(F):
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    return np.concatenate([e, e[:, ::-1]])


def smooth_scalar(w, E, n, iters, keep=None):
    deg = np.maximum(np.bincount(E[:, 0], minlength=n), 1)
    for _ in range(iters):
        avg = np.bincount(E[:, 0], weights=w[E[:, 1]], minlength=n) / deg
        w2 = 0.5 * w + 0.5 * avg
        if keep is not None:
            w2[keep] = w[keep]
        w = w2
    return w


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def pose_a(P, F, arm_deg_from_vertical=38.0, log=print):
    """Baja los brazos desde la pose T: rotación alrededor del hombro, con pesos suaves hacia el tronco."""
    # axila: donde el corte horizontal del tronco se ensancha de golpe (empieza el brazo)
    ys = np.arange(1.2, 1.5, 0.005)
    half = np.array([np.abs(section(P, F, 1, y)[:, 0]).max() for y in ys])
    jump = np.argmax(np.diff(half) > 0.05)
    armpit, side = ys[jump], half[jump]
    xj = side + 0.015
    arm = section(P, F, 0, xj + 0.1)
    arm = arm[arm[:, 1] > armpit - 0.05]
    yj = (arm[:, 1].min() + arm[:, 1].max()) / 2
    tip = P[P[:, 0] > P[:, 0].max() - 0.05]
    cur = np.degrees(np.arctan2(yj - tip[:, 1].mean(), tip[:, 0].mean() - xj))  # caída actual del brazo
    down = (90 - arm_deg_from_vertical) - cur
    log(f"axila y={armpit:.3f} · costado {side:.3f} · hombro ({xj:.3f}, {yj:.3f}) · brazo cae {cur:.1f}° → bajar {down:.1f}°")
    E = adjacency_edges(F)
    out = P.copy()
    wall = np.zeros(len(P))
    for sgn in (1, -1):
        x = P[:, 0] * sgn
        wx = smoothstep(xj - 0.045, xj + 0.06, x)
        wy = smoothstep(armpit - 0.05, armpit + 0.03, P[:, 1])
        w = np.where(x > xj + 0.06, 1.0, wx * wy)
        w[(x < 0.03) | (P[:, 1] < armpit - 0.1)] = 0   # el tronco y las piernas no se mueven
        fixed = (x > xj + 0.14) | (x < 0.04) | (P[:, 1] < armpit - 0.12)
        w = smooth_scalar(w, E, len(P), 30, keep=fixed)
        wall = np.maximum(wall, w)
        th = -np.radians(down) * w * sgn
        dx, dy = P[:, 0] - sgn * xj, P[:, 1] - yj
        c, si = np.cos(th), np.sin(th)
        out[:, 0] = np.where(w > 1e-4, sgn * xj + dx * c - dy * si, out[:, 0])
        out[:, 1] = np.where(w > 1e-4, yj + dx * si + dy * c, out[:, 1])
    return out, dict(armpit=armpit, xj=xj, yj=yj, w=wall)


def section(P, F, axis, value):
    """Puntos donde las aristas cortan el plano coordenada[axis] = value."""
    e = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1), axis=0)
    a, b = P[e[:, 0]], P[e[:, 1]]
    da, db = a[:, axis] - value, b[:, axis] - value
    m = (da * db) < 0
    t = (da[m] / (da[m] - db[m]))[:, None]
    return a[m] + (b[m] - a[m]) * t
