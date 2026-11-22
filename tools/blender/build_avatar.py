"""
EntrenAR · Generador del avatar base para Blender (y GLB directo).

Arma el modelo descrito en docs/MODELO_ARTISTA.md:
  - `body`: una sola malla continua (sin piezas pegadas), con 13 shape keys y el atributo _ZONE
  - prendas separadas con los mismos shape keys: top_tank, top_tee, top_sports,
    bottom_shorts, bottom_leggings, bottom_joggers, shoes
  - peinados: hair_short, hair_shaved, hair_curly, hair_long, hair_ponytail, hair_bun
  - `face`: ojos, cejas, nariz, boca y orejas
  - materiales: skin, top, bottom, shoe, sole, hair, eye, brow, lips

Cómo usarlo
-----------
A) Dentro de Blender (4.x): Scripting → Abrir este archivo → Ejecutar.
   Crea la colección «EntrenAR Avatar» lista para retocar. Para exportar: Archivo → Exportar → glTF
   (o ejecutar con --export).
B) Blender por consola:
      blender --background --python build_avatar.py -- --export avatar_base.glb
C) Sin Blender (solo Python 3 + numpy):
      python build_avatar.py --glb avatar_base.glb

El cuerpo se define como un campo de distancia (formas unidas con «smooth min») y se convierte en malla con
«surface nets» (caras de 4 lados). Cada shape key se obtiene llevando los vértices a la superficie del cuerpo
modificado y suavizando el desplazamiento, igual que el motor de la app (frontend/src/body3d/morph).
Coordenadas internas: metros, Y arriba, la persona mira hacia +Z, su lado derecho en x negativo.
"""
import json
import math
import struct
import sys
import time

import numpy as np

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

# =====================================================================================================
# Proporciones (las mismas que frontend/src/body3d/avatarSpec.js)
# =====================================================================================================
TORSO = {
    "M": [
        (0.79, 0.105, 0.08, 0, "hip"), (0.83, 0.150, 0.105, -0.004, "hip"), (0.885, 0.168, 0.118, -0.012, "hip"),
        (0.945, 0.165, 0.117, -0.012, "hip"), (1.0, 0.153, 0.106, 0.0, "abdomen"), (1.05, 0.146, 0.101, 0.006, "abdomen"),
        (1.10, 0.143, 0.097, 0.003, "waist"), (1.17, 0.152, 0.102, 0.004, "waist"), (1.24, 0.167, 0.111, 0.009, "chest"),
        (1.31, 0.177, 0.116, 0.012, "chest"), (1.37, 0.181, 0.108, 0.004, "shoulders"), (1.415, 0.168, 0.094, -0.006, "shoulders"),
        (1.455, 0.112, 0.071, -0.012, "neck"), (1.485, 0.064, 0.058, -0.006, "neck"),
    ],
    "F": [
        (0.79, 0.108, 0.085, 0, "hip"), (0.83, 0.158, 0.11, -0.008, "hip"), (0.895, 0.181, 0.126, -0.018, "hip"),
        (0.955, 0.172, 0.121, -0.016, "hip"), (1.01, 0.148, 0.101, -0.002, "abdomen"), (1.055, 0.133, 0.093, 0.004, "abdomen"),
        (1.10, 0.124, 0.088, 0.002, "waist"), (1.16, 0.132, 0.092, 0.003, "waist"), (1.23, 0.149, 0.1, 0.008, "chest"),
        (1.30, 0.157, 0.104, 0.01, "chest"), (1.355, 0.162, 0.099, 0.004, "shoulders"), (1.405, 0.153, 0.087, -0.004, "shoulders"),
        (1.445, 0.103, 0.066, -0.01, "neck"), (1.472, 0.056, 0.051, -0.005, "neck"),
    ],
}
REGIONS = ["neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm", "forearm", "thigh", "calf"]
REGION_STEP = 0.4
BASE = dict(sex="M", muscle=0.5, fat=0.3)
# k: el target se muestrea a mitad de camino y se multiplica (aproximación lineal más fiel)
TARGETS = [("sex_female", dict(sex="F"), {}, 1), ("muscle", dict(muscle=0.75), {}, 2), ("fat", dict(fat=0.65), {}, 2)] + [
    (f"girth_{r}", {}, {r: 1 + REGION_STEP / 2}, 2) for r in REGIONS]
ZONE_IDS = [None, "torso", "neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm_right", "arm_left",
            "forearm_right", "forearm_left", "wrist", "thigh_right", "thigh_left", "calf_right", "calf_left"]
COLORS = {"skin": "#ebc2a2", "top": "#ff5a1f", "bottom": "#111827", "shoe": "#f5f5f4", "sole": "#e7e5e4",
          "hair": "#3f2a1d", "eye": "#1c1917", "brow": "#3f2a1d", "lips": "#b4685a"}

# componentes del cuerpo (par = lado derecho, impar = izquierdo)
C_TORSO, C_NECK, C_HEAD, C_DELT, C_UPPER, C_FORE, C_HAND, C_THIGH, C_CALF, C_FOOT = 1, 2, 3, 4, 6, 8, 10, 12, 14, 16


def catmull(rows, steps):
    rows = np.asarray(rows, float)
    out = []
    n = len(rows)
    for i in range(n - 1):
        p0, p1, p2, p3 = rows[max(0, i - 1)], rows[i], rows[i + 1], rows[min(n - 1, i + 2)]
        for s in range(steps):
            t = s / steps
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(rows[-1])
    return np.array(out)


def profile(radii, n=24):
    r = catmull(np.array(radii)[:, None], math.ceil(n / (len(radii) - 1)))[:, 0]
    return np.maximum(0.004, r)


def limb(a, b, radii, flat=1.0):
    a, b = np.array(a, float), np.array(b, float)
    v = b - a
    return dict(a=a, b=b, v=v, len2=float(v @ v), prof=profile(radii), flat=flat)


def ell(c, r):
    return dict(c=np.array(c, float), r=np.array(r, float))


def body_model(sex="M", muscle=0.5, fat=0.3, factors=None):
    F = sex == "F"
    g = {r: 1.0 for r in REGIONS}
    g.update(factors or {})
    mus = 1 + (muscle - 0.5) * 0.28
    fat = fat - 0.3
    src = TORSO["F" if F else "M"]
    mul = []
    for *_, region in src:
        fw = fd = 1.0
        zz = 0.0
        if region == "hip":
            fw, fd = g["hip"] * (1 + fat * 0.18), g["hip"] * (1 + fat * 0.2)
        elif region == "abdomen":
            fw, fd, zz = g["abdomen"] * (1 + fat * 0.3), g["abdomen"] * (1 + fat * 0.5), max(0, fat) * 0.035 * g["abdomen"]
        elif region == "waist":
            fw, fd = g["waist"] * (1 + fat * 0.28), g["waist"] * (1 + fat * 0.35)
        elif region == "chest":
            fw, fd = g["chest"] * (1 + (mus - 1) * 0.6 + fat * 0.1), g["chest"] * (1 + (mus - 1) * 0.5 + fat * 0.12)
        elif region == "shoulders":
            fw, fd = g["shoulders"] * (1 + (mus - 1) * 0.7), 1 + (mus - 1) * 0.3
        elif region == "neck":
            fw, fd = g["neck"] * (1 + (mus - 1) * 0.6), g["neck"]
        mul.append([fw, fd, zz])
    mul = np.array(mul)
    for _ in range(2):  # suaviza entre regiones vecinas (sin tocar el cuello)
        prev = mul.copy()
        for i in range(1, len(mul) - 1):
            if "neck" in (src[i][4], src[i - 1][4], src[i + 1][4]):
                continue
            mul[i] = prev[i - 1] * 0.25 + prev[i] * 0.5 + prev[i + 1] * 0.25
    rows = np.array([[y, w * mul[i, 0], d * mul[i, 1], dz + mul[i, 2]] for i, (y, w, d, dz, _) in enumerate(src)])
    sm = catmull(rows, 5)
    y0, y1, step = sm[0, 0], sm[-1, 0], 0.002
    ys = np.arange(y0, y1 + step, step)
    torso = dict(y0=y0, y1=y1, step=step, n=len(ys), w=np.interp(ys, sm[:, 0], sm[:, 1]),
                 d=np.interp(ys, sm[:, 0], sm[:, 2]), dz=np.interp(ys, sm[:, 0], sm[:, 3]))
    ells = []
    if F:
        bust = g["chest"] * (1 + fat * 0.25)
        for s in (-1, 1):
            ells.append(ell([s * 0.066, 1.272, 0.072 * g["chest"]], [0.066 * bust, 0.062 * bust, 0.058 * bust]))
    else:
        for s in (-1, 1):
            ells.append(ell([s * 0.072, 1.305, 0.068 * g["chest"]], [0.08 * mus, 0.058 * mus, 0.048 * mus]))
    for s in (-1, 1):
        gl = g["hip"] * (1 + fat * 0.15) * (1.08 if F else 1)
        ells.append(ell([s * 0.072, 0.9, -0.064 * gl], [0.088 * gl, 0.1 * gl, 0.072 * gl]))
    neck_r = (0.05 if F else 0.058) * g["neck"] * (1 + (mus - 1) * 0.5)
    neck = limb([0, 1.44, -0.01], [0, 1.6, 0.0], [neck_r * 1.18, neck_r, neck_r * 0.96, neck_r * 0.92])
    head_r = np.array([0.082, 0.106, 0.096] if F else [0.088, 0.112, 0.1]) * (1 + max(0, fat) * 0.04)
    head = ell([0, 1.668, 0.006], head_r)
    jaw = ell([0, 1.6, 0.04], [head_r[0] * 0.78, 0.05, head_r[2] * 0.7])
    sw = (0.183 if F else 0.2) * (1 + (g["shoulders"] - 1) * 0.8) * (1 + (mus - 1) * 0.35)
    arm_f = g["arm"] * (1 + (mus - 1) * 0.9 + fat * 0.22) * (0.86 if F else 1)
    fore_f = g["forearm"] * (1 + (mus - 1) * 0.6 + fat * 0.1) * (0.86 if F else 1)
    th_f = g["thigh"] * (1 + (mus - 1) * 0.7 + fat * 0.25) * (1.04 if F else 1)
    ca_f = g["calf"] * (1 + (mus - 1) * 0.6 + fat * 0.12)
    arms, legs = [], []
    for s in (-1, 1):
        J, E = [s * sw, 1.405, -0.004], [s * (sw + 0.085), 1.135, -0.02]
        W, H = [s * (sw + 0.13), 0.88, 0.01], [s * (sw + 0.145), 0.775, 0.022]
        delt = (0.052 if F else 0.062) * mus * g["shoulders"]
        arms.append(dict(s=s, J=np.array(J), E=np.array(E), W=np.array(W), H=np.array(H),
                         delt=ell([s * (sw + 0.004), 1.392, 0], [delt, delt * 1.18, delt * 1.08]),
                         upper=limb(J, E, np.array([0.054, 0.058, 0.06, 0.054, 0.046, 0.04]) * arm_f),
                         elbow=ell(E, [0.04 * fore_f, 0.042 * fore_f, 0.04 * fore_f]),
                         fore=limb(E, W, np.array([0.041, 0.047, 0.045, 0.038, 0.031, 0.027]) * fore_f),
                         hand=limb(W, H, np.array([0.026, 0.034, 0.035, 0.028, 0.016]) * (0.9 if F else 1), 0.55)))
        Hj, K, A = [s * (0.094 if F else 0.09), 0.885, -0.004], [s * 0.1, 0.49, 0.008], [s * 0.098, 0.085, -0.012]
        legs.append(dict(s=s, Hj=np.array(Hj), K=np.array(K), A=np.array(A),
                         thigh=limb(Hj, K, np.array([0.094, 0.092, 0.084, 0.072, 0.06, 0.052]) * th_f),
                         knee=ell(K, [0.052 * ca_f, 0.058, 0.055 * ca_f]),
                         calf=limb(K, A, np.array([0.05, 0.058, 0.062, 0.052, 0.04, 0.032, 0.029]) * ca_f),
                         shoe=ell([s * 0.098, 0.05, 0.03], [0.047, 0.047, 0.112]),
                         sole=ell([s * 0.098, 0.018, 0.03], [0.05, 0.02, 0.118])))
    return dict(F=F, torso=torso, ells=ells, neck=neck, head=head, jaw=jaw, arms=arms, legs=legs)


# =====================================================================================================
# Campo de distancia (vectorizado: P es un arreglo (N, 3))
# =====================================================================================================
def s_ell(P, e):
    p = (P - e["c"]) / e["r"]
    k0 = np.linalg.norm(p, axis=1)
    k1 = np.linalg.norm(p / e["r"], axis=1)
    return np.where(k1 < 1e-9, -e["r"].min(), k0 * (k0 - 1) / np.maximum(k1, 1e-9))


def s_limb(P, L):
    d = P - L["a"]
    t = np.clip(d @ L["v"] / L["len2"], 0, 1)
    perp = d - t[:, None] * L["v"]
    if L["flat"] != 1:
        perp = perp * np.array([1, 1, 1 / L["flat"]])
    prof = L["prof"]
    f = t * (len(prof) - 1)
    i = np.minimum(len(prof) - 2, f.astype(int))
    u = f - i
    return np.linalg.norm(perp, axis=1) - (prof[i] + (prof[i + 1] - prof[i]) * u)


def s_torso(P, T):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    f = (np.clip(y, T["y0"], T["y1"]) - T["y0"]) / T["step"]
    i = np.minimum(T["n"] - 2, f.astype(int))
    u = f - i
    lerp = lambda a: a[i] + (a[i + 1] - a[i]) * u  # noqa: E731
    w, d, dz = lerp(T["w"]), lerp(T["d"]), lerp(T["dz"])
    ex, ez = x / w, (z - dz) / d
    k0 = np.hypot(ex, ez)
    k1 = np.hypot(ex / w, ez / d)
    de = np.where(k1 < 1e-9, -np.minimum(w, d), k0 * (k0 - 1) / np.maximum(k1, 1e-9))
    return np.maximum(de, np.maximum(T["y0"] - y, y - T["y1"]))


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def body_sdf(m, P, comp=False):
    best = s_torso(P, m["torso"])
    cmp = np.full(len(P), C_TORSO, np.uint8)
    T = best
    for e in m["ells"]:
        T = smin(T, s_ell(P, e), 0.03)
    dn = s_limb(P, m["neck"])
    cmp[dn < best] = C_NECK
    best = np.minimum(best, dn)
    T = smin(T, dn, 0.035)
    dh = smin(s_ell(P, m["head"]), s_ell(P, m["jaw"]), 0.03)
    cmp[dh < best] = C_HEAD
    best = np.minimum(best, dh)
    T = smin(T, dh, 0.025)
    D = T.copy()
    for i in range(2):
        A, L = m["arms"][i], m["legs"][i]
        d1, d2, d3, d4, d5 = s_ell(P, A["delt"]), s_limb(P, A["upper"]), s_ell(P, A["elbow"]), s_limb(P, A["fore"]), s_limb(P, A["hand"])
        arm = smin(smin(smin(smin(d1, d2, 0.04), d3, 0.03), d4, 0.03), d5, 0.025)
        D = np.minimum(D, smin(T, arm, 0.03))
        for dv, c in ((d1, C_DELT), (d2, C_UPPER), (d3, C_FORE), (d4, C_FORE), (d5, C_HAND)):
            cmp[dv < best] = c + i
            best = np.minimum(best, dv)
        e1, e2, e3 = s_limb(P, L["thigh"]), s_ell(P, L["knee"]), s_limb(P, L["calf"])
        e4 = smin(s_ell(P, L["shoe"]), s_ell(P, L["sole"]), 0.02)
        leg = smin(smin(smin(e1, e2, 0.04), e3, 0.04), e4, 0.02)
        D = np.minimum(D, smin(T, leg, 0.045))
        for dv, c in ((e1, C_THIGH), (e2, C_CALF), (e3, C_CALF), (e4, C_FOOT)):
            cmp[dv < best] = c + i
            best = np.minimum(best, dv)
    D = np.maximum(D, -P[:, 1])
    return (D, cmp) if comp else D


def chunked(fn, P, n=250_000):
    return np.concatenate([fn(P[i:i + n]) for i in range(0, len(P), n)]) if len(P) else np.zeros(0)


def gradient(fn, P, e=7e-4):
    g = np.zeros_like(P)
    for k in range(3):
        d = np.zeros(3)
        d[k] = e
        g[:, k] = fn(P + d) - fn(P - d)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)


def project(fn, P, iters=4):
    P = P.copy()
    for _ in range(iters):
        d = fn(P)
        if np.abs(d).max() < 1e-5:
            break
        P -= gradient(fn, P) * d[:, None]
    return P


# =====================================================================================================
# Surface nets: campo de distancia → malla de quads
# =====================================================================================================
def surface_nets(fn, lo, hi, h):
    lo, hi = np.array(lo, float), np.array(hi, float)
    n = (np.ceil((hi - lo) / h) + 1).astype(int)
    gx, gy, gz = [lo[k] + np.arange(n[k]) * h for k in range(3)]
    G = np.stack(np.meshgrid(gx, gy, gz, indexing="ij"), -1).reshape(-1, 3)
    f = chunked(fn, G).reshape(n)
    neg = f < 0
    cells = n - 1
    S = np.zeros((*cells, 3))
    C = np.zeros(cells)

    def edges(axis):
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[axis], sl1[axis] = slice(0, -1), slice(1, None)
        f0, f1 = f[tuple(sl0)], f[tuple(sl1)]
        cross = (f0 < 0) != (f1 < 0)
        I = np.array(np.nonzero(cross))
        t = f0[cross] / (f0[cross] - f1[cross])
        pts = I.T.astype(float)
        pts[:, axis] += t
        return I, pts

    for axis in range(3):
        I, pts = edges(axis)
        others = [k for k in range(3) if k != axis]
        for da in (0, 1):
            for db in (0, 1):
                c = I.copy()
                c[others[0]] -= da
                c[others[1]] -= db
                ok = np.all((c >= 0) & (c < cells[:, None]), axis=0)
                idx = tuple(c[:, ok])
                np.add.at(S, idx, pts[ok])
                np.add.at(C, idx, 1)
    active = C > 0
    vid = np.full(cells, -1, np.int64)
    vid[active] = np.arange(active.sum())
    V = lo + (S[active] / C[active][:, None]) * h

    quads = []
    # (offsets de las 4 celdas alrededor de una arista, igual que el motor de la app)
    spec = {0: [(0, -1, -1), (0, 0, -1), (0, 0, 0), (0, -1, 0)],
            1: [(-1, 0, -1), (-1, 0, 0), (0, 0, 0), (0, 0, -1)],
            2: [(-1, -1, 0), (0, -1, 0), (0, 0, 0), (-1, 0, 0)]}
    for axis in range(3):
        sl0, sl1 = [slice(None)] * 3, [slice(None)] * 3
        sl0[axis], sl1[axis] = slice(0, -1), slice(1, None)
        cross = np.zeros_like(neg)
        cross[tuple(sl0)] = neg[tuple(sl0)] != neg[tuple(sl1)]
        I = np.array(np.nonzero(cross))
        others = [k for k in range(3) if k != axis]
        ok = np.all([(I[k] >= 1) & (I[k] <= n[k] - 2) for k in others], axis=0) & (I[axis] <= n[axis] - 2)
        I = I[:, ok]
        q = []
        for off in spec[axis]:
            c = I + np.array(off)[:, None]
            q.append(vid[tuple(c)])
        q = np.stack(q, 1)
        flip = ~neg[tuple(I)]
        q[flip] = q[flip][:, [0, 3, 2, 1]]
        quads.append(q[np.all(q >= 0, axis=1)])
    return V, np.concatenate(quads)


def quads_to_tris(Q):
    return np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])


def vertex_normals(V, tris):
    fn = np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, tris[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def edge_list(Q):
    e = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    return np.concatenate([e, e[:, ::-1]])


def smooth_field(F, E, V, iters):
    deg = np.bincount(E[:, 0], minlength=V).astype(float)
    deg[deg == 0] = 1
    for _ in range(iters):
        avg = np.stack([np.bincount(E[:, 0], weights=F[E[:, 1], k], minlength=V) for k in range(3)], 1) / deg[:, None]
        F = F * 0.5 + avg * 0.5
    return F


# =====================================================================================================
# Shape keys del cuerpo
# =====================================================================================================
def bone_offset(mA, mB, comp, P):
    off = np.zeros_like(P)
    head = comp == C_HEAD
    off[head] = mB["head"]["c"] - mA["head"]["c"]

    def seg(mask, a0, b0, a1, b1):
        if not mask.any():
            return
        v = b0 - a0
        t = np.clip((P[mask] - a0) @ v / (v @ v), 0, 1)[:, None]
        da, db = a1 - a0, b1 - b0
        off[mask] = da + (db - da) * t

    for i in range(2):
        A, B, LA, LB = mA["arms"][i], mB["arms"][i], mA["legs"][i], mB["legs"][i]
        off[comp == C_DELT + i] = B["delt"]["c"] - A["delt"]["c"]
        seg(comp == C_UPPER + i, A["J"], A["E"], B["J"], B["E"])
        seg(comp == C_FORE + i, A["E"], A["W"], B["E"], B["W"])
        seg(comp == C_HAND + i, A["W"], A["H"], B["W"], B["H"])
        seg(comp == C_THIGH + i, LA["Hj"], LA["K"], LB["Hj"], LB["K"])
        seg(comp == C_CALF + i, LA["K"], LA["A"], LB["K"], LB["A"])
        off[comp == C_FOOT + i] = LB["shoe"]["c"] - LA["shoe"]["c"]
    return off


def project_to(P, N, comp, mA, mB):
    fn = lambda X: body_sdf(mB, X)  # noqa: E731
    P0 = P + bone_offset(mA, mB, comp, P)
    t0 = np.zeros(len(P))
    f0 = fn(P0)
    t1 = -f0
    f1 = fn(P0 + N * t1[:, None])
    for _ in range(6):
        den = f1 - f0
        ok = np.abs(den) > 1e-9
        t2 = np.where(ok, np.clip(t1 - f1 * (t1 - t0) / np.where(ok, den, 1), -0.12, 0.12), t1)
        t0, f0, t1 = t1, f1, t2
        f1 = fn(P0 + N * t1[:, None])
    R = P0 + N * t1[:, None]
    g = gradient(fn, R)
    bad = (np.abs(f1) > 1e-3) | (np.einsum("ij,ij->i", g, N) < 0.2)
    if bad.any():  # cayó en otra superficie: punto más cercano
        R[bad] = project(fn, P0[bad], 6)
    return R


def zone_of(comp, y):
    torso = np.select([y > 1.44, y > 1.36, y > 1.2, y > 1.07, y > 0.98], ["neck", "shoulders", "chest", "waist", "abdomen"], "hip")
    names = []
    for c, t in zip(comp, torso, strict=True):
        side = "right" if c % 2 == 0 else "left"
        base = c - (c % 2) if c >= C_DELT else c
        names.append({C_TORSO: t, C_NECK: "neck", C_DELT: "shoulders", C_UPPER: f"arm_{side}", C_FORE: f"forearm_{side}",
                      C_HAND: "wrist", C_THIGH: f"thigh_{side}", C_CALF: f"calf_{side}"}.get(base))
    return np.array([ZONE_IDS.index(z) if z in ZONE_IDS else 0 for z in names], np.float32)


def build_body(h=0.01, log=print):
    t = time.time()
    mBase = body_model(**BASE)
    fn = lambda X: body_sdf(mBase, X)  # noqa: E731
    V, Q = surface_nets(fn, [-0.47, -0.012, -0.2], [0.47, 1.8, 0.22], h)
    V = project(fn, V, 3)
    N = gradient(fn, V)
    _, comp = body_sdf(mBase, V, comp=True)
    log(f"cuerpo: {len(V)} vértices, {len(Q)} quads ({time.time() - t:.1f} s)")
    E = edge_list(Q)
    keys, heads = {}, {}
    for name, av, fac, k in TARGETS:
        t = time.time()
        mT = body_model(**{**BASE, **av}, factors=fac)
        D = (project_to(V, N, comp, mBase, mT) - V) * k
        D = smooth_field(D, E, len(V), 10)
        D[np.linalg.norm(D, axis=1) < 2.5e-4] = 0  # < 0,25 mm: ruido del suavizado (así el archivo queda liviano)
        keys[name] = D
        heads[name] = (mT["head"], k)
        log(f"  shape key {name} ({time.time() - t:.1f} s)")
    return dict(model=mBase, V=V, Q=Q, N=N, comp=comp, zone=zone_of(comp, V[:, 1]), keys=keys, heads=heads)


# =====================================================================================================
# Prendas (superficies separadas, apenas por fuera del cuerpo)
# =====================================================================================================
def garment_masks(body):
    V, comp, m = body["V"], body["comp"], body["model"]
    x, y, z = V.T
    ax = np.abs(x)
    base = np.where(comp >= C_DELT, comp - comp % 2, comp)
    torso, thigh, calf = base == C_TORSO, base == C_THIGH, base == C_CALF
    A = m["arms"]
    side = (comp % 2).astype(int)
    J = np.array([A[s]["J"] for s in side])
    Ev = np.array([A[s]["E"] - A[s]["J"] for s in side])
    t_arm = np.einsum("ij,ij->i", V - J, Ev) / np.einsum("ij,ij->i", Ev, Ev)
    front = z > 0.02
    wb = 0.985
    tank_neck = 1.425 - np.where(front, 0.05 * np.maximum(0, 1 - (ax / 0.085) ** 2), 0.01)
    tee_neck = 1.45 - np.where(front, 0.025 * np.maximum(0, 1 - (ax / 0.07) ** 2), 0)
    return {
        # nombre: (máscara de vértices, grosor, material)
        "bottom_shorts": ((torso & (y < wb)) | (thigh & (y > 0.70)), 0.009, "bottom"),
        "bottom_leggings": ((torso & (y < 1.0)) | thigh | (calf & (y > 0.15)), 0.003, "bottom"),
        "bottom_joggers": ((torso & (y < wb)) | thigh | (calf & (y > 0.115)), 0.012, "bottom"),
        "top_tank": (torso & (y >= wb + 0.004) & (y < tank_neck) & ~((ax > 0.128) & (y > 1.27)), 0.005, "top"),
        "top_tee": ((torso & (y >= 0.95) & (y < tee_neck)) | (base == C_DELT) | ((base == C_UPPER) & (t_arm < 0.42)), 0.015, "top"),
        "top_sports": (torso & (((y >= 1.20) & (y < 1.385)) | ((y >= 1.38) & (y < 1.47) & (ax > 0.045) & (ax < 0.085))), 0.004, "top"),
        "shoes": (base == C_FOOT, 0.002, "shoe"),
    }


def extract_garment(body, mask, thick):
    V, Q, keys = body["V"], body["Q"], body["keys"]
    fn = lambda X: body_sdf(body["model"], X)  # noqa: E731
    sel = mask[Q].sum(1) >= 3
    Qg = Q[sel]
    src = np.unique(Qg)
    remap = np.full(len(V), -1)
    remap[src] = np.arange(len(src))
    Qg = remap[Qg]
    P = V[src].copy()
    # bordes (aristas usadas por una sola cara) suavizados: dobladillos prolijos en vez de escalones
    e = np.concatenate([Qg[:, [0, 1]], Qg[:, [1, 2]], Qg[:, [2, 3]], Qg[:, [3, 0]]])
    key = np.sort(e, 1)
    uniq, cnt = np.unique(key, axis=0, return_counts=True)
    border = uniq[cnt == 1]
    if len(border):
        bE = np.concatenate([border, border[:, ::-1]])
        bv = np.unique(border)
        for _ in range(12):
            deg = np.bincount(bE[:, 0], minlength=len(P)).astype(float)
            avg = np.stack([np.bincount(bE[:, 0], weights=P[bE[:, 1], k], minlength=len(P)) for k in range(3)], 1)
            P[bv] = P[bv] * 0.5 + (avg[bv] / np.maximum(deg[bv], 1)[:, None]) * 0.5
        P[bv] = project(fn, P[bv], 4)
    N = gradient(fn, P)
    P = P + N * thick
    return P, Qg, {k: d[src] for k, d in keys.items()}


# =====================================================================================================
# Pelo y cara
# =====================================================================================================
def hair_sdf(style, m):
    hc, hr = m["head"]["c"], m["head"]["r"]

    def fn(P):
        y, z = P[:, 1], P[:, 2]
        zn = np.clip((z - hc[2]) / hr[2], -1, 1)
        cut = (hc[1] - 0.02 + 0.07 * zn) - y        # línea del pelo: alta en la frente, baja en la nuca

        def cap(s):  # sólido que se superpone con la cabeza: una sola superficie limpia hacia afuera
            return smax(s_ell(P, ell(hc, hr * s)), cut, 0.012)

        if style == "shaved":
            d = cap(1.035)
        elif style == "short":
            d = cap(1.06)
        elif style == "curly":
            d = cap(1.08)
            gold = math.pi * (3 - math.sqrt(5))
            for i in range(26):  # rulos repartidos sobre la parte de arriba
                u = 1 - (i + 0.5) / 26 * 0.85
                r = math.sqrt(1 - u * u)
                c = hc + np.array([math.cos(i * gold) * r * hr[0] * 1.06, u * hr[1] * 1.04 - 0.01, math.sin(i * gold) * r * hr[2] * 1.06])
                b = s_ell(P, ell(c, [0.026, 0.026, 0.026]))
                d = smin(d, smax(b, cut - 0.01, 0.01), 0.012)
        elif style == "long":
            d = cap(1.06)
            back = s_ell(P, ell(hc + [0, -0.13, -0.06], [hr[0] * 1.02, 0.17, 0.05]))
            back = smax(back, z - (hc[2] - 0.005), 0.01)
            d = smin(d, back, 0.03)
            for s in (-1, 1):
                d = smin(d, s_ell(P, ell(hc + [s * hr[0] * 0.95, -0.06, -0.015], [0.022, 0.1, 0.042])), 0.02)
        elif style == "ponytail":
            d = cap(1.055)
            d = smin(d, s_ell(P, ell(hc + [0, 0.047, -0.1], [0.03, 0.03, 0.03])), 0.015)
            d = smin(d, s_limb(P, limb(hc + [0, 0.04, -0.115], hc + [0, -0.17, -0.135], [0.03, 0.036, 0.03, 0.016])), 0.015)
        elif style == "bun":
            d = cap(1.055)
            d = smin(d, s_ell(P, ell(hc + [0, 0.087, -0.065], [0.046, 0.042, 0.046])), 0.02)
        else:
            raise ValueError(style)
        return d

    return fn


HAIR_STYLES = ["short", "shaved", "curly", "long", "ponytail", "bun"]


def build_hair(style, m, h=0.0058):
    hc = m["head"]["c"]
    fn = hair_sdf(style, m)
    V, Q = surface_nets(fn, hc + [-0.16, -0.32, -0.2], hc + [0.16, 0.16, 0.18], h)
    return project(fn, V, 3), Q


def ellipsoid_mesh(c, r, rot_z=0.0, seg=16, rings=10):
    """Elipsoide en quads (los polos como triángulos degenerados)."""
    pts = []
    for i in range(rings + 1):
        th = math.pi * i / rings
        for j in range(seg):
            ph = 2 * math.pi * j / seg
            pts.append([math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)])
    P = np.array(pts) * r
    if rot_z:
        cz, sz = math.cos(rot_z), math.sin(rot_z)
        P = P @ np.array([[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]])
    P += c
    Q = []
    for i in range(rings):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            Q.append([a, b, b + seg, a + seg])
    return P, np.array(Q)


def build_face(m):
    fn = lambda X: body_sdf(m, X)  # noqa: E731
    hc, hr = m["head"]["c"], m["head"]["r"]

    def surf_z(x, y):  # z de la superficie de la cara en (x, y)
        z = hc[2] + 0.2
        for _ in range(80):
            d = fn(np.array([[x, y, z]]))[0]
            if d < 1e-4:
                break
            z -= max(d, 0.0005)
        return z

    parts = []
    for s in (-1, 1):
        parts.append(("eye", [s * 0.032, 1.676, surf_z(s * 0.032, 1.676) - 0.004], [0.012, 0.0095, 0.007], 0))
        parts.append(("brow", [s * 0.033, 1.699, surf_z(s * 0.033, 1.699) - 0.002], [0.02, 0.0045, 0.005], s * -0.12))
        parts.append(("skin", [s * hr[0] * 0.98, 1.662, hc[2] - 0.004], [0.012, 0.026, 0.019], 0))  # orejas
    parts.append(("skin", [0, 1.652, surf_z(0, 1.652) - 0.006], [0.011, 0.02, 0.015], 0))  # nariz
    parts.append(("lips", [0, 1.618, surf_z(0, 1.618) - 0.003], [0.02, 0.006, 0.006], 0))
    Vs, Qs, mats = [], [], []
    off = 0
    for mat, c, r, rz in parts:
        P, Q = ellipsoid_mesh(np.array(c), np.array(r), rz)
        Vs.append(P)
        Qs.append(Q + off)
        mats += [mat] * len(Q)
        off += len(P)
    return np.concatenate(Vs), np.concatenate(Qs), mats


def head_keys(P, body):
    """Shape keys de pelo y cara: siguen a la cabeza (centro y tamaño) de cada target."""
    base = body["model"]["head"]
    out = {}
    for name, (head, k) in body["heads"].items():
        D = ((head["c"] + (P - base["c"]) * (head["r"] / base["r"])) - P) * k
        D[np.linalg.norm(D, axis=1) < 2.5e-4] = 0
        out[name] = D
    return out


def garment_keys_from_body(P, body):
    """Para prendas que no salieron del cuerpo: cada vértice copia el desplazamiento del vértice del cuerpo más cercano."""
    V = body["V"]
    idx = np.empty(len(P), int)
    for i in range(0, len(P), 2000):
        d = ((P[i:i + 2000, None, :] - V[None, :, :]) ** 2).sum(-1)
        idx[i:i + 2000] = d.argmin(1)
    return {k: d[idx] for k, d in body["keys"].items()}


# =====================================================================================================
# Armado completo
# =====================================================================================================
def build_all(log=print):
    body = build_body(log=log)
    objs = [dict(name="body", V=body["V"], Q=body["Q"], mats=["skin"] * len(body["Q"]), keys=body["keys"], zone=body["zone"])]
    for name, (mask, thick, mat) in garment_masks(body).items():
        P, Q, keys = extract_garment(body, mask, thick)
        mats = [mat] * len(Q)
        if name == "shoes":
            mats = ["sole" if P[q, 1].mean() < 0.026 else "shoe" for q in Q]
        objs.append(dict(name=name, V=P, Q=Q, mats=mats, keys=keys))
        log(f"{name}: {len(P)} vértices")
    for style in HAIR_STYLES:
        P, Q = build_hair(style, body["model"])
        objs.append(dict(name=f"hair_{style}", V=P, Q=Q, mats=["hair"] * len(Q), keys=head_keys(P, body)))
        log(f"hair_{style}: {len(P)} vértices")
    P, Q, mats = build_face(body["model"])
    objs.append(dict(name="face", V=P, Q=Q, mats=mats, keys=head_keys(P, body)))
    return objs


# =====================================================================================================
# Salida A: GLB directo (sin Blender)
# =====================================================================================================
def srgb_to_linear(hexcol):
    c = [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


Q_SCALE = 16000.0  # posiciones y desplazamientos en enteros de 16 bits: 1 unidad = 1/16000 m (±2 m, 0,06 mm)


def write_glb(objs, path):
    """GLB cuantizado (KHR_mesh_quantization): ~60% más liviano; Three.js lo lee sin decodificadores extra."""
    blob = bytearray()
    views, accessors = [], []

    def view(data, stride=None, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data),
                      **({"byteStride": stride} if stride else {}), **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    def padded(arr, stride):  # elementos de vértice alineados a 4 bytes
        raw = np.ascontiguousarray(arr).view(np.uint8).reshape(len(arr), -1)
        out = np.zeros((len(arr), stride), np.uint8)
        out[:, :raw.shape[1]] = raw
        return out.tobytes()

    def acc(**kw):
        accessors.append(kw)
        return len(accessors) - 1

    def q16(D):
        return np.clip(np.round(D * Q_SCALE), -32767, 32767).astype(np.int16)

    def add_delta(D):
        Q = q16(D)
        nz = np.nonzero(np.abs(Q).max(1) > 0)[0]
        base = dict(componentType=5122, count=int(len(Q)), type="VEC3",
                    min=(Q.min(0) if len(Q) else [0, 0, 0]).tolist(), max=(Q.max(0) if len(Q) else [0, 0, 0]).tolist())
        if len(nz) < len(Q) * 0.55:  # disperso: solo los vértices que se mueven
            if not len(nz):
                return acc(**base)
            iv = view(nz.astype(np.uint32).tobytes())
            vv = view(np.ascontiguousarray(Q[nz]).tobytes())
            return acc(**base, sparse={"count": int(len(nz)), "indices": {"bufferView": iv, "componentType": 5125},
                                       "values": {"bufferView": vv}})
        return acc(**base, bufferView=view(padded(Q, 8), 8, 34962))

    mat_names = list(COLORS)
    materials = [{"name": n, "pbrMetallicRoughness": {"baseColorFactor": srgb_to_linear(COLORS[n]) + [1], "metallicFactor": 0,
                                                       "roughnessFactor": 0.6}, "doubleSided": n in ("top", "bottom")}
                 for n in mat_names]
    names = [t[0] for t in TARGETS]
    meshes, nodes = [], []
    for o in objs:
        V = o["V"]
        tris_all = o["T"] if "T" in o else quads_to_tris(o["Q"])
        mats_all = np.array(o["mats"]) if "T" in o else np.concatenate([o["mats"], o["mats"]])
        Pq = q16(V)
        Nq = np.clip(np.round(vertex_normals(V, tris_all) * 127), -127, 127).astype(np.int8)
        attrs = {
            "POSITION": acc(bufferView=view(padded(Pq, 8), 8, 34962), componentType=5122, count=len(V), type="VEC3",
                            min=Pq.min(0).tolist(), max=Pq.max(0).tolist()),
            "NORMAL": acc(bufferView=view(padded(Nq, 4), 4, 34962), componentType=5120, normalized=True, count=len(V), type="VEC3"),
        }
        if "zone" in o:
            attrs["_ZONE"] = acc(bufferView=view(o["zone"].astype(np.float32).tobytes(), None, 34962), componentType=5126,
                                 count=len(V), type="SCALAR")
        targets = [{"POSITION": add_delta(o["keys"][n])} for n in names]
        prims = []
        itype, idt = (5123, np.uint16) if len(V) < 65535 else (5125, np.uint32)
        for mname in sorted(set(o["mats"])):
            tris = tris_all[mats_all == mname].astype(idt).ravel()
            prims.append({"attributes": attrs, "indices": acc(bufferView=view(tris.tobytes(), None, 34963), componentType=itype,
                                                              count=int(len(tris)), type="SCALAR"),
                          "material": mat_names.index(mname), "targets": targets})
        meshes.append({"name": o["name"], "primitives": prims, "weights": [0.0] * len(names),
                       "extras": {"targetNames": names, **o.get("extras", {})}})
        nodes.append({"name": o["name"], "mesh": len(meshes) - 1, "scale": [1 / Q_SCALE] * 3})
    gltf = {"asset": {"version": "2.0", "generator": "EntrenAR build_avatar.py"}, "scene": 0,
            "extensionsUsed": ["KHR_mesh_quantization"], "extensionsRequired": ["KHR_mesh_quantization"],
            "scenes": [{"name": "Scene", "nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
            "materials": materials, "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": 0}]}
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<I4s", len(js), b"JSON") + js)
        fh.write(struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob))


# =====================================================================================================
# Salida B: escena de Blender
# =====================================================================================================
def to_blender(P):
    """(x, y arriba, z adelante) → Blender (x, −y adelante, z arriba)."""
    return np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)


def build_in_blender(objs, export_path=None):
    import bpy

    coll = bpy.data.collections.get("EntrenAR Avatar") or bpy.data.collections.new("EntrenAR Avatar")
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    mats = {}
    for name, hexcol in COLORS.items():
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(hexcol), 1)
            bsdf.inputs["Roughness"].default_value = 0.6
        mats[name] = mat
    names = [t[0] for t in TARGETS]
    for o in objs:
        V = to_blender(o["V"])
        mesh = bpy.data.meshes.new(o["name"] + "_mesh")
        mesh.from_pydata(V.tolist(), [], o["Q"].tolist())
        used = sorted(set(o["mats"]))
        for mname in used:
            mesh.materials.append(mats[mname])
        mesh.polygons.foreach_set("material_index", [used.index(m) for m in o["mats"]])
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        if "zone" in o:
            attr = mesh.attributes.new("_ZONE", "FLOAT", "POINT")
            attr.data.foreach_set("value", o["zone"].tolist())
        mesh.update()
        ob = bpy.data.objects.new(o["name"], mesh)
        coll.objects.link(ob)
        ob.shape_key_add(name="Basis", from_mix=False)
        for n in names:
            sk = ob.shape_key_add(name=n, from_mix=False)
            sk.slider_min, sk.slider_max = -2.0, 2.0
            sk.data.foreach_set("co", (V + to_blender(o["keys"][n])).ravel().tolist())
        if o["name"].startswith(("top_tee", "top_sports", "bottom_leggings", "bottom_joggers")) or (
                o["name"].startswith("hair_") and o["name"] != "hair_short"):
            ob.hide_set(True)  # en la escena se ve un conjunto por vez (todos se exportan)
    print("EntrenAR: avatar armado en la colección «EntrenAR Avatar».")
    if export_path:
        for ob in coll.objects:
            ob.hide_set(False)
        props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
        wanted = dict(filepath=export_path, export_format="GLB", export_yup=True, export_apply=False, export_morph=True,
                      export_morph_normal=False, export_attributes=True, export_animations=False, export_skins=False,
                      export_texcoords=False, export_normals=True, export_cameras=False, export_lights=False,
                      use_selection=False, use_visible=False)
        bpy.ops.export_scene.gltf(**{k: v for k, v in wanted.items() if k in props})
        print("EntrenAR: exportado", export_path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    t = time.time()
    objs = build_all()
    if IN_BLENDER:
        export = argv[argv.index("--export") + 1] if "--export" in argv else None
        build_in_blender(objs, export)
    else:
        out = argv[argv.index("--glb") + 1] if "--glb" in argv else "avatar_base.glb"
        write_glb(objs, out)
        print("GLB escrito en", out)
    print(f"listo en {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
