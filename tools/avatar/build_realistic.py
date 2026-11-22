"""
EntrenAR · Adapta un cuerpo modelado (GLB) como avatar de la app.

Entrada: un GLB con UNA malla de cuerpo humano (puede ser la mitad, sin aplicar el espejo), en pose T o A,
sin shape keys. Salida: frontend/public/models/avatar_body.glb con
  - el cuerpo completo, 1,75 m, Y arriba, mirando a +Z, en pose A
  - los 13 shape keys de la app (sex_female, muscle, fat, girth_*)
  - el atributo _ZONE (zonas tocables) y los anillos de medición precalculados (extras.rings)
  - la forma base calibrada a los perímetros de referencia de la app

Los shape keys se transfieren del cuerpo procedural de la app (tools/blender/build_avatar.py): cada vértice se
asocia a la misma parte del cuerpo (mismo hueso, misma posición a lo largo, mismo ángulo alrededor) y toma su
desplazamiento, girado a la dirección de su hueso y escalado a su grosor.

Uso:  python build_realistic.py modelo.glb [salida.glb]     (Python 3 + numpy)
"""
import json
import math
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
import build_avatar as BA  # noqa: E402
from prep_mesh import adjacency_edges, pose_a, prepare, section  # noqa: E402

REF = {"neck": 38, "shoulders": 116, "chest": 100, "waist": 84, "abdomen": 88, "hip": 98, "arm": 33, "forearm": 28,
       "thigh": 56, "calf": 37}
ZONE_IDS = BA.ZONE_IDS


# ------------------------------------------------------------------------------------------- lectura GLB
def read_glb(path):
    b = open(path, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    bin_ = b[20 + jl + 8:]
    CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8, 5122: np.int16, 5120: np.int8}
    NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = j["accessors"][i]
        n, dt = NC[a["type"]], CT[a["componentType"]]
        bv = j["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        st = bv.get("byteStride") or np.dtype(dt).itemsize * n
        raw = np.frombuffer(bin_, np.uint8, st * (a["count"] - 1) + np.dtype(dt).itemsize * n, off)
        out = np.stack([np.frombuffer(raw[k * st:k * st + np.dtype(dt).itemsize * n].tobytes(), dt) for k in range(a["count"])]) \
            if st != np.dtype(dt).itemsize * n else np.frombuffer(raw.tobytes(), dt).reshape(a["count"], n)
        return out.astype(np.float64)

    Ps, Fs, off = [], [], 0
    for node in j["nodes"]:
        if "mesh" not in node:
            continue
        t = np.array(node.get("translation", [0, 0, 0]), float)
        s = np.array(node.get("scale", [1, 1, 1]), float)
        if node.get("rotation") and np.abs(np.array(node["rotation"]) - [0, 0, 0, 1]).max() > 1e-6:
            raise SystemExit("El objeto tiene una rotación sin aplicar: en Blender, Objeto → Aplicar → Rotación y escala.")
        for p in j["meshes"][node["mesh"]]["primitives"]:
            P = acc(p["attributes"]["POSITION"]) * s + t
            F = acc(p["indices"]).astype(int).reshape(-1, 3)
            Ps.append(P)
            Fs.append(F + off)
            off += len(P)
    return np.concatenate(Ps), np.concatenate(Fs)


# ------------------------------------------------------------------------------------------- esqueleto
def skeleton(P, F, info):
    """Articulaciones del cuerpo adaptado (medidas sobre la malla en pose A). Lado: índice 0 = derecho (x<0)."""
    J0 = np.array([info["xj"], info["yj"]])
    arm = P[info["w"] > 0.95]
    arm = arm[arm[:, 0] > 0]
    d = arm[:, :2] - J0
    tip = arm[np.argmax(np.linalg.norm(d, axis=1))]
    L = np.linalg.norm(tip[:2] - J0)
    u = (tip[:2] - J0) / L
    zc = float(np.median(arm[:, 2]))
    # entrepierna: primer corte horizontal (de abajo hacia arriba) que vuelve a cruzar x=0
    crotch = next(y for y in np.arange(0.6, 1.1, 0.005) if (np.abs(section(P, F, 1, y)[:, 0]) < 0.006).any())

    def leg_center(y):
        s = section(P, F, 1, y)
        s = s[(s[:, 0] > 0.02) & (s[:, 0] < 0.45)]
        return np.array([(s[:, 0].min() + s[:, 0].max()) / 2, y, (s[:, 2].min() + s[:, 2].max()) / 2])

    K, A = leg_center(0.49), leg_center(0.10)
    A[1] = 0.085
    Hj = leg_center(crotch - 0.04)
    Hj = Hj + (Hj - K) / np.linalg.norm(Hj - K) * 0.05
    neck_lo, neck_hi = 1.49, 1.565
    head = P[P[:, 1] > neck_hi]
    hc = np.array([0, (head[:, 1].min() + head[:, 1].max()) / 2, (head[:, 2].min() + head[:, 2].max()) / 2])
    hr = np.array([np.abs(head[:, 0]).max(), (head[:, 1].max() - head[:, 1].min()) / 2, np.ptp(head[:, 2]) / 2])
    sk = dict(crotch=crotch, neck=(neck_lo, neck_hi), head=(hc, hr), arms=[], legs=[])
    for s in (-1, 1):
        J = np.array([s * J0[0], J0[1], zc])
        dirv = np.array([s * u[0], u[1], 0.0])
        sk["arms"].append(dict(J=J, E=J + dirv * L * 0.42, W=J + dirv * L * 0.755, T=J + dirv * L))
        m = np.array([s, 1, 1])
        sk["legs"].append(dict(Hj=Hj * m, K=K * m, A=A * m))
    return sk


# ------------------------------------------------------------------------------------------- referencias del tronco
PROC_MARKS = {"crotch": 0.80, "hip": 0.905, "abdomen": 1.03, "waist": 1.10, "chest": 1.30, "armpit": 1.36, "neck": 1.475}


def torso_marks(P, F, sk, armpit):
    def half(y):
        s = section(P, F, 1, y)
        s = s[np.abs(s[:, 0]) < 0.25]
        return np.ptp(s[:, 0]) / 2

    def front(y):
        s = section(P, F, 1, y)
        s = s[np.abs(np.abs(s[:, 0]) - 0.08) < 0.03]
        return s[:, 2].max()

    ys = np.arange(sk["crotch"] + 0.02, armpit - 0.02, 0.005)
    hw = np.array([half(y) for y in ys])
    hip = ys[np.argmax(np.where(ys < sk["crotch"] + 0.15, hw, -1))]
    waist = ys[np.argmin(np.where((ys > hip + 0.1) & (ys < armpit - 0.08), hw, 9))]
    yc = np.arange(waist + 0.05, armpit + 0.06, 0.005)
    chest = min(yc[np.argmax([front(y) for y in yc])] - 0.02, armpit - 0.035)
    return {"crotch": sk["crotch"], "hip": hip, "abdomen": (hip + waist) / 2 + 0.02, "waist": waist, "chest": chest,
            "armpit": armpit, "neck": sk["neck"][0]}


def to_proc_y(y, marks):
    k = list(PROC_MARKS)
    return np.interp(y, [marks[m] for m in k], [PROC_MARKS[m] for m in k])


# ------------------------------------------------------------------------------------------- partes
# categorías de transferencia: (nombre, comps del procedural, cómo se arma el marco)
def classify(P, info, sk):
    """Parte de cada vértice: torso, neck, head, delt, upper, fore, hand, thigh, calf, foot (+ lado)."""
    n = len(P)
    part = np.full(n, "torso", dtype=object)
    side = (P[:, 0] > 0).astype(int)           # 0 derecho (x<0), 1 izquierdo
    y = P[:, 1]
    w = info["w"]
    lo, hi = sk["neck"]
    part[(y > lo) & (y <= hi) & (np.abs(P[:, 0]) < 0.1)] = "neck"
    part[y > hi] = "head"
    for i in (0, 1):
        A = sk["arms"][i]
        m = (side == i) & (w > 0.12)
        v = A["T"] - A["J"]
        t = ((P - A["J"]) @ v) / (v @ v)
        part[m & (w < 0.75)] = "delt"
        part[m & (w >= 0.75) & (t < 0.42)] = "upper"
        part[m & (w >= 0.75) & (t >= 0.42) & (t < 0.755)] = "fore"
        part[m & (w >= 0.75) & (t >= 0.755)] = "hand"
        L = sk["legs"][i]
        legm = (side == i) & (y < sk["crotch"]) & (w < 0.05)
        part[legm & (y >= L["K"][1])] = "thigh"
        part[legm & (y < L["K"][1]) & (y >= L["A"][1])] = "calf"
        part[legm & (y < L["A"][1])] = "foot"
    return part, side


PROC_COMPS = {"torso": [BA.C_TORSO], "neck": [BA.C_NECK], "head": [BA.C_HEAD], "delt": [BA.C_DELT, BA.C_UPPER],
              "upper": [BA.C_UPPER], "fore": [BA.C_FORE], "hand": [BA.C_HAND], "thigh": [BA.C_THIGH], "calf": [BA.C_CALF],
              "foot": [BA.C_FOOT]}


def bone_of(part, i, sk=None, m=None):
    """Hueso (a, b) de una parte: del esqueleto adaptado (sk) o del modelo procedural (m)."""
    if sk is not None:
        A, L = sk["arms"][i], sk["legs"][i]
        J, E, W, T = A["J"], A["E"], A["W"], A["T"]
        Hj, K, An = L["Hj"], L["K"], L["A"]
        lo, hi = sk["neck"]
        neck = (np.array([0, lo, 0.0]), np.array([0, hi, 0.03]))
    else:
        A, L = m["arms"][i], m["legs"][i]
        J, E, W, T = A["J"], A["E"], A["W"], A["H"] + (A["H"] - A["W"]) * 0.6
        Hj, K, An = L["Hj"], L["K"], L["A"]
        neck = (m["neck"]["a"], m["neck"]["b"])
    return {"delt": (J, E), "upper": (J, E), "fore": (E, W), "hand": (W, T), "thigh": (Hj, K), "calf": (K, An),
            "neck": neck}.get(part)


def frame(a, b):
    ax = (b - a) / np.linalg.norm(b - a)
    fr = np.array([0, 0, 1.0]) - ax * ax[2]
    if np.linalg.norm(fr) < 1e-6:
        fr = np.array([0, 1.0, 0]) - ax * ax[1]
    fr /= np.linalg.norm(fr)
    lat = np.cross(ax, fr)
    return np.stack([ax, lat, fr])          # filas: eje, lateral, frente


def coords_limb(X, a, b):
    R = frame(a, b)
    v = b - a
    t = ((X - a) @ v) / (v @ v)
    off = X - (a + np.outer(t, v))
    lat, fr = off @ R[1], off @ R[2]
    return t, np.arctan2(lat, fr), np.hypot(lat, fr), R


def transfer(P, part, side, sk, proc, log=print):
    """Desplazamientos de los 13 shape keys para cada vértice del cuerpo adaptado."""
    V, comp, keys, m = proc["V"], proc["comp"], proc["keys"], proc["model"]
    names = list(keys)
    D = {k: np.zeros_like(P) for k in names}
    pside = (comp % 2).astype(int)
    pbase = np.where(comp >= BA.C_DELT, comp - comp % 2, comp)
    for pname, pcomps in PROC_COMPS.items():
        for i in (0, 1) if pname not in ("torso", "neck", "head") else (None,):
            sel = (part == pname) & ((side == i) if i is not None else True)
            psel = np.isin(pbase, pcomps) & ((pside == i) if i is not None else True)
            if not sel.any() or not psel.any():
                continue
            X, Y = P[sel], V[psel]
            if pname in ("torso",):
                zc_r = np.median(P[part == "torso"][:, 2])
                zc_p = np.median(V[pbase == BA.C_TORSO][:, 2])
                qa = np.stack([to_proc_y(X[:, 1], sk["marks"]), np.arctan2(X[:, 0], X[:, 2] - zc_r) * 0.13], 1)
                qb = np.stack([Y[:, 1], np.arctan2(Y[:, 0], Y[:, 2] - zc_p) * 0.13], 1)
                ra = np.hypot(X[:, 0], X[:, 2] - zc_r)
                rb = np.hypot(Y[:, 0], Y[:, 2] - zc_p)
                Ra = Rb = np.eye(3)
                wrap = 0.13
            elif pname in ("head", "foot"):
                if pname == "head":
                    ca, rra = sk["head"]
                    cb, rrb = m["head"]["c"], m["head"]["r"]
                else:
                    ca, rra = sk["legs"][i]["A"] * [1, 0, 1] + [0, 0.04, 0.04], np.array([0.05, 0.05, 0.12])
                    shoe = m["legs"][i]["shoe"]
                    cb, rrb = shoe["c"], shoe["r"]
                na, nb = (X - ca) / rra, (Y - cb) / rrb
                qa = na / np.linalg.norm(na, axis=1, keepdims=True) * 0.1
                qb = nb / np.linalg.norm(nb, axis=1, keepdims=True) * 0.1
                ra, rb = np.linalg.norm(X - ca, axis=1), np.linalg.norm(Y - cb, axis=1)
                Ra = Rb = np.eye(3)
                wrap = None
            else:
                ii = i if i is not None else 0
                a_r, b_r = bone_of(pname, ii, sk=sk)
                a_p, b_p = bone_of(pname, ii, m=m)
                ta, fa, ra, Ra = coords_limb(X, a_r, b_r)
                tb, fb, rb, Rb = coords_limb(Y, a_p, b_p)
                Lr = np.linalg.norm(b_r - a_r)
                qa = np.stack([ta * Lr, fa * 0.05], 1)
                qb = np.stack([tb * Lr, fb * 0.05], 1)
                wrap = 0.05
            # k vecinos más cercanos (en bloques)
            k = 4
            idx = np.empty((len(qa), k), int)
            dist = np.empty((len(qa), k))
            for s0 in range(0, len(qa), 1500):
                dq = qa[s0:s0 + 1500, None, :] - qb[None, :, :]
                if wrap:  # el ángulo da la vuelta
                    per = 2 * math.pi * wrap
                    dq[..., 1] = (dq[..., 1] + per / 2) % per - per / 2
                d2 = (dq ** 2).sum(-1)
                nn = np.argpartition(d2, k, axis=1)[:, :k]
                idx[s0:s0 + 1500] = nn
                dist[s0:s0 + 1500] = np.sqrt(np.take_along_axis(d2, nn, 1))
            wts = 1 / (dist + 1e-4)
            wts /= wts.sum(1, keepdims=True)
            scale = np.clip(ra / np.maximum((rb[idx] * wts).sum(1), 1e-3), 0.6, 1.8)[:, None]
            for name in names:
                dp = keys[name][psel][idx]                       # (n, k, 3) en el mundo del procedural
                loc = np.einsum("nkj,ij->nki", dp, Rb)           # al marco del hueso procedural
                loc = (loc * wts[..., None]).sum(1)
                D[name][sel] = (loc @ Ra) * scale                # al marco del hueso adaptado
        log(f"  {pname}: {int((part == pname).sum())} vértices")
    return D


# ------------------------------------------------------------------------------------------- calibración
def perimeter_at(P, F, y, half_limit=0.25):
    s = trunk_cut(section(P, F, 1, y), half_limit)
    a, b = np.ptp(s[:, 0]) / 2, np.ptp(s[:, 2]) / 2
    return ellipse_perimeter(a, b) * 100, (s[:, 2].max() + s[:, 2].min()) / 2


def limb_perimeter(P, part, side, i, name, a0, b0, t):
    c = a0 + (b0 - a0) * t
    ax = (b0 - a0) / np.linalg.norm(b0 - a0)
    Q = P[(part == name) & (side == i)] - c
    Q = Q[np.abs(Q @ ax) < 0.015]
    Q = Q - np.outer(Q @ ax, ax)
    return 2 * math.pi * float(np.linalg.norm(Q, axis=1).mean()) * 100


def calibrate(P, F, part, side, sk, log=print):
    """Ensancha (o afina) cada parte alrededor de su propio eje para llegar a los perímetros de referencia.
    Factores suaves por altura: no deforma la anatomía como lo haría un shape key extrapolado."""
    E = adjacency_edges(F)
    for it in range(3):
        mk = sk["marks"]
        ctrl = {"hip": mk["hip"], "abdomen": mk["abdomen"], "waist": mk["waist"], "chest": mk["chest"]}
        fac, zc = {}, {}
        for r, y in ctrl.items():
            per, zc[r] = perimeter_at(P, F, y)
            fac[r] = float(np.clip(REF[r] / per, 0.88, 1.18))  # suave: el resto lo resuelven las referencias propias
        ys = [mk["crotch"] - 0.1, mk["hip"], mk["abdomen"], mk["waist"], mk["chest"], mk["armpit"] + 0.06, mk["neck"]]
        fs = [fac["hip"], fac["hip"], fac["abdomen"], fac["waist"], fac["chest"], 1.0, 1.0]
        zs = [zc["hip"], zc["hip"], zc["abdomen"], zc["waist"], zc["chest"], zc["chest"], zc["chest"]]
        D = np.zeros_like(P)
        tor = np.isin(part, ["torso"])
        f = np.interp(P[:, 1], ys, fs)
        z0 = np.interp(P[:, 1], ys, zs)
        D[tor, 0] = P[tor, 0] * (f[tor] - 1)
        D[tor, 2] = (P[tor, 2] - z0[tor]) * (f[tor] - 1)
        lf = {}
        for i in (0, 1):
            A, L = sk["arms"][i], sk["legs"][i]
            for name, region, (a0, b0), t in (("upper", "arm", (A["J"], A["E"]), 0.55), ("fore", "forearm", (A["E"], A["W"]), 0.25),
                                              ("thigh", "thigh", (L["Hj"], L["K"]), 0.4), ("calf", "calf", (L["K"], L["A"]), 0.3)):
                k = float(np.clip(REF[region] / limb_perimeter(P, part, side, i, name, a0, b0, t), 0.88, 1.18))
                lf[(name, i)] = k
                m = (part == name) & (side == i)
                ax = (b0 - a0) / np.linalg.norm(b0 - a0)
                off = P[m] - a0
                off = off - np.outer(off @ ax, ax)
                D[m] = off * (k - 1)
        if it == 0:
            log("factores de calibración: " + ", ".join(f"{r} {v:.2f}" for r, v in fac.items()) + " · " +
                ", ".join(f"{n} {v:.2f}" for (n, i), v in lf.items() if i == 1))
        fixed = np.isin(part, ["head", "hand", "foot"])
        D[fixed] = 0
        D = BA.smooth_field(D, E, len(P), 12)
        D[np.isin(part, ["head", "foot"])] = 0
        P = P + D
        if max(abs(v - 1) for v in fac.values()) < 0.02 or it == 1:
            break
    return P


def female_features(P, F, part, marks):
    """Busto para el shape key sex_female (el cuerpo procedural lo resolvía con la ropa; acá el cuerpo se ve)."""
    N = BA.vertex_normals(P, F)
    D = np.zeros_like(P)
    tor = part == "torso"
    front = tor & (N[:, 2] > 0.15) & (P[:, 2] > 0)
    soft = np.where(tor, np.clip((N[:, 2] + 0.1) / 0.6, 0, 1) ** 2, 0)   # se apaga gradualmente hacia los costados
    # altura y separación tomadas del pecho del propio modelo
    chest = P[front & (np.abs(P[:, 1] - marks["chest"]) < 0.05)]
    half = np.abs(chest[:, 0]).max()
    for s in (-1, 1):
        cx, cy = s * half * 0.55, marks["chest"] - 0.025
        dx = (P[:, 0] - cx) / 0.06
        dy = P[:, 1] - cy
        dy = np.where(dy > 0, dy / 0.095, dy / 0.072)  # arriba cae suave, abajo redondeado
        h = 0.04 * np.exp(-(dx ** 2 + dy ** 2)) * soft
        push = N * h[:, None]
        push[:, 1] -= h * 0.25                        # leve caída natural
        D += push
    return BA.smooth_field(D, adjacency_edges(F), len(P), 2)


# ------------------------------------------------------------------------------------------- Loop
def loop_operator(F, n):
    """Subdivisión de Loop como operador lineal: se aplica igual a posiciones y a desplazamientos."""
    te = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    opp = np.concatenate([F[:, 2], F[:, 0], F[:, 1]])
    key = np.sort(te, 1)
    E, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    ne = len(E)
    rows, cols, wts = [], [], []
    # vértices originales
    nb = adjacency_edges(F)
    val = np.bincount(nb[:, 0], minlength=n)
    beta = (1 / val) * (5 / 8 - (3 / 8 + 0.25 * np.cos(2 * np.pi / val)) ** 2)
    rows += [np.arange(n), nb[:, 0]]
    cols += [np.arange(n), nb[:, 1]]
    wts += [1 - val * beta, beta[nb[:, 0]]]
    # vértices nuevos en las aristas
    rows += [n + np.arange(ne)] * 2
    cols += [E[:, 0], E[:, 1]]
    wts += [np.full(ne, 3 / 8)] * 2
    rows += [n + inv]
    cols += [opp]
    wts += [np.full(len(opp), 1 / 8)]
    R, C, W = np.concatenate(rows), np.concatenate(cols), np.concatenate(wts)
    e = n + inv.reshape(3, -1).T          # aristas (ab, bc, ca) de cada triángulo
    a, b, c = F.T
    ab, bc, ca = e[:, 0], e[:, 1], e[:, 2]
    F2 = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
    edge_src = E                             # para heredar datos discretos (zonas)

    def apply(X):
        X = np.asarray(X, float)
        out = np.zeros((n + ne,) + X.shape[1:])
        if X.ndim == 1:
            np.add.at(out, R, W * X[C])
        else:
            np.add.at(out, R, W[:, None] * X[C])
        return out
    return apply, F2, n + ne, edge_src


# ------------------------------------------------------------------------------------------- anillos
def ellipse_perimeter(a, b):
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def trunk_cut(s, limit):
    """Del corte horizontal, solo el bloque continuo alrededor de x=0 (los brazos empiezan después del primer hueco)."""
    s = s[np.abs(s[:, 0]) < limit]
    ax = np.sort(np.abs(s[:, 0]))
    gaps = np.nonzero(np.diff(ax) > 0.035)[0]
    if len(gaps):
        s = s[np.abs(s[:, 0]) <= ax[gaps[0]] + 1e-9]
    return s


def rings_for(P, F, zone, sk, heights):
    """{zona: [x, y, z, r, flat, tilt, perímetro_cm]} medidos sobre la malla (secciones planas)."""
    out = {}
    zid = {z: i for i, z in enumerate(ZONE_IDS)}
    for z, y in heights.items():
        s = trunk_cut(section(P, F, 1, y), 0.32 if z == "shoulders" else 0.25)
        if z == "neck":
            s = s[np.abs(s[:, 0]) < 0.09]
        a = (s[:, 0].max() - s[:, 0].min()) / 2
        b = (s[:, 2].max() - s[:, 2].min()) / 2
        cz = (s[:, 2].max() + s[:, 2].min()) / 2
        out[z] = [0.0, y, cz, a * 1.06, b / a, 0.0, ellipse_perimeter(a, b) * 100]
    for i, sd in enumerate(("right", "left")):
        A, L = sk["arms"][i], sk["legs"][i]
        for z, (a0, b0, t) in {f"arm_{sd}": (A["J"], A["E"], 0.55), f"forearm_{sd}": (A["E"], A["W"], 0.25),
                               f"thigh_{sd}": (L["Hj"], L["K"], 0.4), f"calf_{sd}": (L["K"], L["A"], 0.3)}.items():
            c = a0 + (b0 - a0) * t
            ax = (b0 - a0) / np.linalg.norm(b0 - a0)
            # sección perpendicular al hueso, solo con vértices de esa zona
            m = zone == zid[z]
            Q = P[m]
            near = np.abs((Q - c) @ ax) < 0.012
            pts = Q[near] - c
            pts -= np.outer(pts @ ax, ax)
            r = np.linalg.norm(pts, axis=1)
            rr = float(np.mean(r)) if len(r) else 0.04
            out[z] = [*c.tolist(), rr * 1.12, 1.0, float(math.atan2(ax[0], -ax[1])), 2 * math.pi * rr * 100]
        if sd == "right":
            c = A["E"] + (A["W"] - A["E"]) * 0.97
            ax = (A["W"] - A["E"]) / np.linalg.norm(A["W"] - A["E"])
            out["wrist"] = [*c.tolist(), 0.03, 1.0, float(math.atan2(ax[0], -ax[1])), 17.0]
    return out


# ------------------------------------------------------------------------------------------- todo
def build(src, dst, log=print):
    t0 = time.time()
    P, F = read_glb(src)
    P, F = prepare(P, F, log=log)
    P, info = pose_a(P, F, log=log)
    sk = skeleton(P, F, info)
    sk["marks"] = torso_marks(P, F, sk, info["armpit"])
    log("referencias: " + ", ".join(f"{k} {v:.3f}" for k, v in sk["marks"].items()))
    log(f"esqueleto: entrepierna {sk['crotch']:.3f} · rodilla {sk['legs'][1]['K'].round(3)} · cabeza {sk['head'][0].round(3)}")
    part, side = classify(P, info, sk)
    P = calibrate(P, F, part, side, sk, log=log)
    marks = sk["marks"]
    sk = skeleton(P, F, info)
    sk["marks"] = marks
    log("perímetros: " + ", ".join(f"{r} {perimeter_at(P, F, y)[0]:.0f}" for r, y in (("hip", 0.92), ("waist", 1.12), ("chest", 1.30))))
    log("cuerpo procedural de referencia…")
    proc = BA.build_body(log=lambda *_: None)
    log("transfiriendo shape keys…")
    D = transfer(P, part, side, sk, proc, log=log)
    E = adjacency_edges(F)
    for k in D:
        D[k] = BA.smooth_field(D[k], E, len(P), 3)
    D["sex_female"] = D["sex_female"] + female_features(P, F, part, sk["marks"])
    # zonas (en la malla original)
    zone = np.zeros(len(P))
    zmap = {"neck": "neck", "delt": "shoulders", "hand": "wrist"}
    for v in range(len(P)):
        p, sd = part[v], ("right", "left")[side[v]]
        if p == "torso":
            y = to_proc_y(P[v, 1], marks)   # mismos cortes que la app, en alturas equivalentes
            z = "neck" if y > 1.44 else "shoulders" if y > 1.36 else "chest" if y > 1.2 else "waist" if y > 1.07 else \
                "abdomen" if y > 0.98 else "hip"
        elif p in ("upper", "fore", "thigh", "calf"):
            z = {"upper": "arm", "fore": "forearm"}.get(p, p) + "_" + sd
        else:
            z = zmap.get(p)
        zone[v] = ZONE_IDS.index(z) if z in ZONE_IDS else 0
    # subdivisión (posiciones, desplazamientos y zonas)
    apply, F2, n2, edges = loop_operator(F, len(P))
    P2 = apply(P)
    D2 = {k: apply(d) for k, d in D.items()}
    zone2 = np.concatenate([zone, zone[edges[:, 0]]])
    log(f"subdividido: {n2} vértices, {len(F2)} triángulos")
    heights = {"neck": (marks["neck"] + sk["neck"][1]) / 2, "shoulders": marks["armpit"] + 0.035, "chest": marks["chest"],
               "waist": marks["waist"], "abdomen": marks["abdomen"], "hip": marks["hip"]}
    rings = rings_for(P2, F2, zone2, sk, heights)
    log("perímetros finales (cm): " + ", ".join(f"{k} {rings[k][6]:.0f}" for k in ("neck", "chest", "waist", "abdomen", "hip", "arm_left", "thigh_left")))
    # perímetros propios del modelo (hombre y mujer): la app calcula los pesos de las medidas contra estos
    def refs(PP):
        r = rings_for(PP, F2, zone2, sk, heights)
        avg = lambda a, b: round((r[a][6] + r[b][6]) / 2, 1)  # noqa: E731
        return {"neck": round(r["neck"][6], 1), "shoulders": round(r["shoulders"][6], 1), "chest": round(r["chest"][6], 1),
                "waist": round(r["waist"][6], 1), "abdomen": round(r["abdomen"][6], 1), "hip": round(r["hip"][6], 1),
                "arm": avg("arm_right", "arm_left"), "forearm": avg("forearm_right", "forearm_left"),
                "thigh": avg("thigh_right", "thigh_left"), "calf": avg("calf_right", "calf_left"), "wrist": 17.0 if True else 0}
    reference = {"M": refs(P2), "F": refs(P2 + D2["sex_female"])}
    reference["F"]["wrist"] = 15.0
    log("referencia M: " + str(reference["M"]))
    log("referencia F: " + str(reference["F"]))
    # anillos por target (el motor los combina con los mismos pesos que los shape keys)
    ring_data = {"base": {z: v[:6] for z, v in rings.items()}, "delta": {}}
    for name, d in D2.items():
        rt = rings_for(P2 + d * 0.5, F2, zone2, sk, heights)
        ring_data["delta"][name] = {z: [(rt[z][q] - rings[z][q]) * 2 for q in range(6)] for z in rings}
    for k in D2:
        D2[k][np.linalg.norm(D2[k], axis=1) < 2.5e-4] = 0
    obj = dict(name="body", V=P2, T=F2, mats=["skin"] * len(F2), keys=D2, zone=zone2.astype(np.float32),
               extras={"rings": ring_data, "reference_cm": reference, "pose": "A", "source": os.path.basename(src)})
    BA.write_glb([obj], dst)
    log(f"listo: {dst} ({os.path.getsize(dst) / 1e6:.1f} MB) en {time.time() - t0:.0f} s")
    return P2, F2, D2, zone2, rings


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "..", "frontend", "public", "models", "avatar_body.glb")
    build(src, dst)
