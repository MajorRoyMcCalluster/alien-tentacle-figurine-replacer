"""Generates the Alien Tentacle Figurine: replaces the figurine in common.SLOT (the Atlas Figurine) with an
original bioluminescent alien tentacle on a suction-cup foot.

Mesh roles (the figurine's own mesh names are kept so the game's name-hash links still match; see SLOT["roles"]):
  head    upper tendril, child of Headjnt  -> wobbles (pivot y = 0.135)
  rings   glowing rings on the upper tendril (unlit glow material)
  collar  glowing collar over the wobble seam (unlit glow material)
  lower   foot + lower tendril, static
  the pedestal geometry is the game's own; its glow ring is recoloured green
"""
import numpy as np, re, base64, os, sys, copy, struct
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK, BOB, PREFIX, SLOT, SCENE_LC, mxml_of, mbin

OUT = os.path.join(WORK, "out") + os.sep

PIVOT = 0.135
FOOT_Y = 0.019            # top of the pedestal
SIZE = 1.5                # overall size vs. the first prototype
SCALE = 0.135 * SIZE      # concept units -> metres
CTRL = np.array([(0, 0.05, 0), (0, 0.45, 0), (-0.2, 0.8, 0.05), (0.35, 1.05, -0.05), (0.05, 1.6, 0.0)]) * SCALE
CTRL[:, 1] += FOOT_Y - CTRL[0, 1] + 0.003
R_ROOT, R_TIP = 0.175 * SCALE, 0.033 * SCALE
SEGS = 28

# ---------------------------------------------------------------- curve + frames
def bez(t):
    p = np.repeat(CTRL[:, None, :], len(t), 1); w = t[None, :, None]
    while len(p) > 1: p = p[:-1] * (1 - w) + p[1:] * w
    return p[0]

def frames(t):
    P = bez(t)
    T = np.gradient(P, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.zeros_like(T); N[0] = np.cross(T[0], [0, 0, 1.0]); N[0] /= np.linalg.norm(N[0])
    for i in range(1, len(t)):                       # parallel transport (no twisting)
        v = N[i - 1] - (N[i - 1] @ T[i]) * T[i]; N[i] = v / np.linalg.norm(v)
    B = np.cross(T, N)
    return P, T, N, B

def radius(t):
    return R_TIP + (R_ROOT - R_TIP) * (1 - t) ** 0.85

def t_at_y(y):
    tt = np.linspace(0, 1, 4001); return float(tt[np.argmin(np.abs(bez(tt)[:, 1] - y))])

T_SEAM = t_at_y(PIVOT)

# ---------------------------------------------------------------- mesh builders
class Mesh:
    def __init__(s): s.P = []; s.N = []; s.UV = []; s.I = []
    def add(s, P, N, UV, I):
        base = sum(len(p) for p in s.P)
        s.P.append(P); s.N.append(N); s.UV.append(UV); s.I.append(I + base)
    def done(s):
        return np.concatenate(s.P), np.concatenate(s.N), np.concatenate(s.UV), np.concatenate(s.I)

def grid_indices(rows, cols):
    I = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = r * cols + c; b = a + 1; d = a + cols; e = d + 1
            I += [(a, b, e), (a, e, d)]
    return np.array(I, np.int64)

def tube(t0, t1, nrings, rfun=radius):
    t = np.linspace(t0, t1, nrings)
    P, T, N, B = frames(t)
    r = rfun(t)
    th = np.linspace(0, 2 * np.pi, SEGS + 1)
    ct, st = np.cos(th), np.sin(th)
    nrm = ct[None, :, None] * N[:, None, :] + st[None, :, None] * B[:, None, :]
    pos = P[:, None, :] + r[:, None, None] * nrm
    # surface normal accounts for the taper
    dr = np.gradient(r) / np.maximum(np.linalg.norm(np.gradient(P, axis=0), axis=1), 1e-9)
    n = nrm - dr[:, None, None] * T[:, None, :]; n /= np.linalg.norm(n, axis=2, keepdims=True)
    uv = np.stack(np.meshgrid(th / (2 * np.pi), 1 - t * 0.94 - 0.05)[::-1], -1)   # u around, v along (top of texture = tip)
    uv = np.stack([np.broadcast_to(th / (2 * np.pi), (nrings, SEGS + 1)), np.broadcast_to((1 - (0.05 + 0.94 * t))[:, None], (nrings, SEGS + 1))], -1)
    I = grid_indices(nrings, SEGS + 1)
    # flip so cross(b-a, c-a) points outward
    p = pos.reshape(-1, 3); k = I[0]
    if np.cross(p[k[1]] - p[k[0]], p[k[2]] - p[k[0]]) @ n.reshape(-1, 3)[k[0]] < 0: I = I[:, [0, 2, 1]]
    return pos.reshape(-1, 3), n.reshape(-1, 3), uv.reshape(-1, 2), I

def cap(t, outward_sign, dome=0.0):
    """closing cap at curve parameter t; dome>0 makes a hemisphere-ish tip"""
    P, T, N, B = frames(np.array([max(t - 1e-3, 0), t, min(t + 1e-3, 1)]))
    c, Tc, Nc, Bc = P[1], T[1] * outward_sign, N[1], B[1]
    r = radius(np.array([t]))[0]
    rings = 7 if dome else 2
    pts, nrm, uvs = [], [], []
    for j in range(rings):
        a = (j / (rings - 1)) * (np.pi / 2) if dome else (0 if j == 0 else np.pi / 2)
        rr = r * np.cos(a); h = (r * dome) * np.sin(a)
        for k in range(SEGS + 1):
            th = 2 * np.pi * k / SEGS
            d = np.cos(th) * Nc + np.sin(th) * Bc
            pts.append(c + rr * d + h * Tc)
            nn = (np.cos(a) * d + np.sin(a) * Tc) if dome else Tc
            nrm.append(nn / np.linalg.norm(nn))
            uvs.append((k / SEGS, 1 - (0.05 + 0.94 * t)))
    pts, nrm, uvs = np.array(pts), np.array(nrm), np.array(uvs)
    I = grid_indices(rings, SEGS + 1)
    k = I[I.shape[0] // 2]
    fn = np.cross(pts[k[1]] - pts[k[0]], pts[k[2]] - pts[k[0]])
    if fn @ nrm[k[0]] < 0: I = I[:, [0, 2, 1]]
    return pts, nrm, uvs, I

def torus(t, minor, extra, nmaj=None):
    nmaj = nmaj or SEGS
    P, T, N, B = frames(np.array([max(t - 1e-3, 0), t, min(t + 1e-3, 1)]))
    c, Tc, Nc, Bc = P[1], T[1], N[1], B[1]
    R = radius(np.array([t]))[0] + extra
    nmin = 10
    pts, nrm, uvs = [], [], []
    for i in range(nmaj + 1):
        a = 2 * np.pi * i / nmaj; d = np.cos(a) * Nc + np.sin(a) * Bc
        for j in range(nmin + 1):
            b = 2 * np.pi * j / nmin
            n = np.cos(b) * d + np.sin(b) * Tc
            pts.append(c + R * d + minor * n); nrm.append(n); uvs.append((i / nmaj, j / nmin))
    pts, nrm, uvs = np.array(pts), np.array(nrm), np.array(uvs)
    I = grid_indices(nmaj + 1, nmin + 1)
    k = I[0]
    if np.cross(pts[k[1]] - pts[k[0]], pts[k[2]] - pts[k[0]]) @ nrm[k[0]] < 0: I = I[:, [0, 2, 1]]
    return pts, nrm, uvs, I

def foot():
    """flat suction-cup foot, lathe profile around the vertical axis at the curve root"""
    root = bez(np.array([0.0]))[0]
    # foot stays inside the pedestal's glow ring so the ring still shows
    prof = [(0.0, FOOT_Y), (0.042, FOOT_Y), (0.0445, FOOT_Y + 0.0025), (0.0425, FOOT_Y + 0.006),
            (R_ROOT * 1.15, FOOT_Y + 0.011), (R_ROOT * 1.04, FOOT_Y + 0.018), (R_ROOT * 0.995, FOOT_Y + 0.026)]
    pts, nrm, uvs = [], [], []
    prof = np.array(prof)
    for j, (r, y) in enumerate(prof):
        for k in range(SEGS + 1):
            th = 2 * np.pi * k / SEGS
            pts.append((root[0] + r * np.cos(th), y, root[2] + r * np.sin(th)))
            uvs.append((k / SEGS, 0.985 + 0.012 * j / len(prof)))
    pts = np.array(pts); rows = len(prof)
    I = grid_indices(rows, SEGS + 1)
    # normals from the profile tangent
    for j in range(rows):
        a = prof[max(j - 1, 0)]; b = prof[min(j + 1, rows - 1)]
        dr, dy = b[0] - a[0], b[1] - a[1]
        for k in range(SEGS + 1):
            th = 2 * np.pi * k / SEGS
            n = np.array([dy * np.cos(th), -dr, dy * np.sin(th)])
            if j == 0: n = np.array([0, -1.0, 0])
            nrm.append(n / (np.linalg.norm(n) + 1e-12))
    nrm = np.array(nrm)
    k = I[len(I) // 2]
    if np.cross(pts[k[1]] - pts[k[0]], pts[k[2]] - pts[k[0]]) @ nrm[k[0]] < 0: I = I[:, [0, 2, 1]]
    return pts, nrm, np.array(uvs), I

RING_TS = [0.58, 0.66, 0.74, 0.82, 0.89]

def build_meshes():
    up = Mesh(); up.add(*tube(T_SEAM - 0.03, 0.985, 90)); up.add(*cap(0.985, +1, dome=1.0)); up.add(*cap(T_SEAM - 0.03, -1))
    rings = Mesh()
    for tt in RING_TS:
        rings.add(*torus(tt, minor=radius(np.array([tt]))[0] * 0.10, extra=0.0))
    collar = Mesh(); collar.add(*torus(T_SEAM, minor=0.0042 * SIZE, extra=0.0015 * SIZE))
    low = Mesh(); low.add(*foot()); low.add(*tube(0.0, T_SEAM + 0.01, 45)); low.add(*cap(T_SEAM + 0.01, +1))
    return {"head": up.done(), "rings": rings.done(), "collar": collar.done(), "lower": low.done()}

# ---------------------------------------------------------------- packing
def pack_normal(n):
    n = n / np.linalg.norm(n, axis=1, keepdims=True)
    s = np.abs(n).sum(1, keepdims=True); o = n[:, :2] / s
    neg = n[:, 2] < 0
    ox = np.where(neg, (1 - np.abs(o[:, 1])) * np.sign(o[:, 0] + 1e-12), o[:, 0])
    oy = np.where(neg, (1 - np.abs(o[:, 0])) * np.sign(o[:, 1] + 1e-12), o[:, 1])
    qx = np.clip(np.round((ox + 1) * 511.5), 0, 1023).astype(np.uint32)
    qy = np.clip(np.round((oy + 1) * 511.5), 0, 1023).astype(np.uint32)
    return qx | (qy << 10) | (np.uint32(512) << 20) | (np.uint32(3) << 30)

def unpack_normal(v):
    v = v.astype(np.int64); x = (v & 1023) / 511.5 - 1; y = ((v >> 10) & 1023) / 511.5 - 1
    z = 1 - np.abs(x) - np.abs(y)
    nx = np.where(z < 0, (1 - np.abs(y)) * np.sign(x), x); ny = np.where(z < 0, (1 - np.abs(x)) * np.sign(y), y)
    n = np.stack([nx, ny, z], 1); return n / np.linalg.norm(n, axis=1, keepdims=True)

def streams(P, N, UV, I):
    n = len(P); assert n < 65536
    vcol = np.full((n, 4), 255, np.uint8)
    vd = np.zeros(n, dtype=[("c", "u1", 4), ("n", "<u4")]); vd["c"] = vcol; vd["n"] = pack_normal(N)
    vbytes = vd.tobytes()
    ibytes = I.astype("<u2").tobytes()
    pos = np.zeros((n, 8), np.float32); pos[:, :3] = P; pos[:, 3] = 1; pos[:, 4:6] = UV; pos[:, 7] = 1
    pbytes = pos.astype("<f2").tobytes()
    assert len(vbytes) == 8 * n
    return vbytes, ibytes, pbytes

# ---------------------------------------------------------------- textures
def mip_dds(img, fmt, path):
    import struct
    w, h = img.size; levels = []; cur = img
    while True:
        cw, ch = cur.size
        c4 = cur if (cw >= 4 and ch >= 4) else cur.resize((max(4, cw), max(4, ch)), Image.BOX)
        levels.append(c4.tobytes("bcn", 1 if fmt == "DXT1" else 5))
        if cw == 1 and ch == 1: break
        cur = cur.resize((max(1, cw // 2), max(1, ch // 2)), Image.LANCZOS)
    blk = 8 if fmt == "DXT1" else 16
    hdr = struct.pack("<4s7I", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000, h, w,
                      max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * blk, 0, len(levels)) + b"\0" * 44
    hdr += struct.pack("<2I4s5I", 32, 0x4, fmt.encode(), 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    open(path, "wb").write(hdr + b"".join(levels))

def textures():
    Wt, Ht = 512, 1024
    v = np.linspace(0, 1, Ht)[:, None]; t = np.clip((1 - v - 0.05) / 0.94, 0, 1)
    cob = np.array([0.07, 0.16, 0.62]); ice = np.array([0.55, 0.85, 0.98])
    a = (t ** 1.2)[..., None]
    col = np.broadcast_to(cob * (1 - a) + ice * a, (Ht, Wt, 3)).copy()
    # soft pearly streaks
    rng = np.random.default_rng(7)
    u = np.linspace(0, 1, Wt)[None, :]
    streak = 0.06 * np.sin(2 * np.pi * (u * 3 + t * 5 + 0.3)) + 0.04 * np.sin(2 * np.pi * (u * 7 - t * 11))
    col *= (1 + streak)[..., None]
    # glow spots (painted, bright) - tile horizontally so the seam is clean
    im = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    glow = Image.new("RGB", (Wt, Ht), (0, 0, 0)); dg = ImageDraw.Draw(glow)
    for _ in range(85):
        x = rng.uniform(0, Wt); y = rng.uniform(Ht * 0.08, Ht * 0.92); r = rng.uniform(5, 12)
        for dx in (-Wt, 0, Wt):
            dg.ellipse((x + dx - r * 1.6, y - r, x + dx + r * 1.6, y + r), fill=(110, 255, 235))
    # stripe bands on the lower tendril (the upper one gets real glowing rings)
    for tt in (0.16, 0.24, 0.32, 0.40):
        y = (1 - (0.05 + 0.94 * tt)) * Ht
        dg.rectangle((0, y - 6, Wt, y + 6), fill=(110, 255, 235))
    halo = glow.filter(ImageFilter.GaussianBlur(7))
    out = np.asarray(im).astype(np.float32) / 255
    g = np.asarray(glow).astype(np.float32) / 255; hl = np.asarray(halo).astype(np.float32) / 255
    out = out * (1 - 0.75 * g.max(2, keepdims=True)) + 0.9 * g + 0.35 * hl
    # foot band (bottom of the texture): deep cobalt
    out[int(Ht * 0.975):] = np.array([0.05, 0.10, 0.42])
    diff = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
    diff.save(OUT + "preview_biolum_diffuse.png")
    # masks: the glossy-plastic value the game's own figurines use (red channel full, green/blue zero)
    masks = Image.new("RGB", (Wt, Ht), (255, 0, 0))
    normal = Image.new("RGB", (Wt, Ht), (128, 128, 255))
    os.makedirs(OUT + "tex", exist_ok=True)
    mip_dds(diff, "DXT1", OUT + f"tex/{PREFIX}_BIOLUM.DDS")
    mip_dds(masks, "ATI2", OUT + f"tex/{PREFIX}_BIOLUM.MASKS.DDS")
    mip_dds(normal, "ATI2", OUT + f"tex/{PREFIX}_BIOLUM.NORMAL.DDS")

# ---------------------------------------------------------------- files
SC = SLOT["scene"]
MATP = "MODELS\\PLANETS\\BIOMES\\COMMON\\BUILDINGS\\PROPS\\BOBBLEHEADS\\" + SC + "\\"
MAIN_MAT = MATP + f"{PREFIX}_BIOLUM_MAT.MATERIAL.MBIN"
GLOW_MAT = MATP + f"{PREFIX}_GLOW_MAT.MATERIAL.MBIN"
PEDESTAL_MAT = MATP + f"{PREFIX}_PEDESTAL_MAT.MATERIAL.MBIN"
TEX_PATH = f"TEXTURES/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/ALIENTENTACLE/{PREFIX}_BIOLUM"

def compile_mxml(path):
    mbin(path)

def fix_position_counts(path, ds):
    """MBINCompiler writes each mesh's position-stream list length as the vertex+index stream length.
    The game reads streams by the header offsets so it still renders, but fix it to match the game's own
    files: the count sits at 0x58 + 0x48 * mesh_index."""
    b = bytearray(open(path, "rb").read())
    for k, d in enumerate(ds):
        at = 0x58 + 0x48 * k
        cur = struct.unpack_from("<I", b, at)[0]
        assert cur in (len(d["vb"]) + len(d["ib"]), len(d["pb"])), f"unexpected layout at mesh {k}: {cur}"
        struct.pack_into("<I", b, at, len(d["pb"]))
    open(path, "wb").write(bytes(b))
    return bytes(b)

def main():
    meshes = {SLOT["roles"][r]: m for r, m in build_meshes().items()}
    role_of = {v: k for k, v in SLOT["roles"].items()}
    # original pedestal streams
    os.makedirs(OUT, exist_ok=True)
    GEO_DATA = mxml_of(BOB + SCENE_LC + ".geometry.data.mbin.pc")
    GEO_HDR = mxml_of(BOB + SCENE_LC + ".geometry.mbin.pc")
    od = open(GEO_DATA).read()
    order = SLOT["order"]
    data = {}
    for name in order:
        if name in meshes:
            P, N, UV, I = meshes[name]
            vb, ib, pb = streams(P, N, UV, I)
            data[name] = dict(vb=vb, ib=ib, pb=pb, nv=len(P), ni=I.size, aabb=(P.min(0), P.max(0)), P=P)
        else:
            m = re.search(r'IdString" value="%s".*?VertexDataSize" value="(\d+)".*?IndexDataSize" value="(\d+)".*?MeshDataStream" value="([^"]*)".*?MeshPositionDataStream" value="([^"]*)"' % name, od, re.S)
            vs, isz = int(m.group(1)), int(m.group(2)); b = base64.b64decode(m.group(3)); p = base64.b64decode(m.group(4))
            pos = np.frombuffer(p, "<f2").reshape(-1, 8).astype(np.float32)
            data[name] = dict(vb=b[:vs], ib=b[vs:vs + isz], pb=p, nv=vs // 8, ni=isz // 2, aabb=None, P=pos[:, :3])
    # ---- data file
    dt = ET.parse(GEO_DATA); droot = dt.getroot()
    arr = [e for e in droot if e.get("name") == "StreamDataArray"][0]
    for ent in arr:
        props = {c.get("name"): c for c in ent}
        name = props["IdString"].get("value"); d = data[name]
        props["VertexDataSize"].set("value", str(len(d["vb"])))
        props["VertexPositionDataSize"].set("value", str(len(d["pb"])))
        props["IndexDataSize"].set("value", str(len(d["ib"])))
        props["MeshDataStream"].set("value", base64.b64encode(d["vb"] + d["ib"]).decode())
        props["MeshPositionDataStream"].set("value", base64.b64encode(d["pb"]).decode())
    os.makedirs(OUT + "build", exist_ok=True)
    dpath = OUT + f"build/{SC}.GEOMETRY.DATA.MXML"
    dt.write(dpath, encoding="utf-8", xml_declaration=True)
    compile_mxml(dpath)
    raw = fix_position_counts(OUT + f"build/{SC}.GEOMETRY.DATA.MBIN.PC", [data[n] for n in order])
    # ---- header
    ht = ET.parse(GEO_HDR); hroot = ht.getroot()
    hp = {c.get("name"): c for c in hroot}
    starts, ends, hst, hed, hull = [], [], [], [], []
    # original hull verts for the pedestal
    ohull = [(float(x.find("./Property[@name='X']").get("value")), float(x.find("./Property[@name='Y']").get("value")),
              float(x.find("./Property[@name='Z']").get("value"))) for x in hp["BoundHullVerts"]]
    ohs = [int(x.get("value")) for x in hp["BoundHullVertSt"]]; ohe = [int(x.get("value")) for x in hp["BoundHullVertEd"]]
    v0 = 0; batch_starts = []; bi = 0
    for k, name in enumerate(order):
        d = data[name]
        starts.append(v0); ends.append(v0 + d["nv"] - 1); v0 += d["nv"]
        batch_starts.append(bi); bi += d["ni"]
        if d["aabb"] is None:
            pts = ohull[ohs[k]:ohe[k]]
        else:
            lo, hi = d["aabb"]
            pts = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        hst.append(len(hull)); hull += pts; hed.append(len(hull))
    def set_list(prop, vals):
        for e, v in zip(prop, vals): e.set("value", str(v))
    hp["VertexCount"].set("value", str(v0)); hp["IndexCount"].set("value", str(bi))
    set_list(hp["MeshVertRStart"], starts); set_list(hp["MeshVertREnd"], ends)
    set_list(hp["BoundHullVertSt"], hst); set_list(hp["BoundHullVertEd"], hed)
    # rebuild hull vert list
    tmpl = copy.deepcopy(hp["BoundHullVerts"][0])
    for e in list(hp["BoundHullVerts"]): hp["BoundHullVerts"].remove(e)
    for i, (x, y, z) in enumerate(hull):
        e = copy.deepcopy(tmpl); e.set("_index", str(i))
        for c, v in zip("XYZ", (x, y, z)): e.find("./Property[@name='%s']" % c).set("value", "%.6f" % v)
        e.find("./Property[@name='W']").set("value", "1.000000")
        hp["BoundHullVerts"].append(e)
    aabbs = {}
    for k, (emin, emax) in enumerate(zip(hp["MeshAABBMin"], hp["MeshAABBMax"])):
        name = order[k]; d = data[name]
        if d["aabb"] is not None:
            for c, i in zip("XYZ", range(3)):
                emin.find("./Property[@name='%s']" % c).set("value", "%.6f" % d["aabb"][0][i])
                emax.find("./Property[@name='%s']" % c).set("value", "%.6f" % d["aabb"][1][i])
        aabbs[name] = [float(emin.find("./Property[@name='%s']" % c).get("value")) for c in "XYZ"] + \
                      [float(emax.find("./Property[@name='%s']" % c).get("value")) for c in "XYZ"]
    for ent in hp["StreamMetaDataArray"]:
        props = {c.get("name"): c for c in ent}
        name = props["IdString"].get("value"); d = data[name]
        vio = raw.find(d["vb"] + d["ib"]); po = raw.find(d["pb"])
        assert vio > 0 and po > 0, name
        props["VertexDataSize"].set("value", str(len(d["vb"]))); props["VertexDataOffset"].set("value", str(vio))
        props["VertexPositionDataSize"].set("value", str(len(d["pb"]))); props["VertexPositionDataOffset"].set("value", str(po))
        props["IndexDataSize"].set("value", str(len(d["ib"]))); props["IndexDataOffset"].set("value", str(len(d["vb"])))
    hpath = OUT + f"build/{SC}.GEOMETRY.MXML"
    ht.write(hpath, encoding="utf-8", xml_declaration=True)
    compile_mxml(hpath)
    # ---- scene
    st = ET.parse(mxml_of(BOB + SCENE_LC + ".scene.mbin")); sroot = st.getroot()
    def walk(e):
        props = {c.get("name"): c for c in e if c.tag == "Property"}
        yield e, props
        if "Children" in props:
            for c in props["Children"]: yield from walk(c)
    k_of = {n: i for i, n in enumerate(order)}
    for node, props in walk(sroot):
        if props["Type"].get("value") != "MESH": continue
        name = props["Name"].get("value").upper()
        if name not in k_of: continue
        k = k_of[name]; d = data[name]
        attrs = {}
        for a in props["Attributes"]:
            ap = {c.get("name"): c for c in a}; attrs[ap["Name"].get("value")] = ap["Value"]
        vals = {"BATCHSTARTPHYSI": batch_starts[k], "VERTRSTARTPHYSI": starts[k], "VERTRENDPHYSICS": ends[k],
                "BATCHSTARTGRAPH": 0, "BATCHCOUNT": d["ni"], "VERTRSTARTGRAPH": 0, "VERTRENDGRAPHIC": d["nv"] - 1,
                "BOUNDHULLST": hst[k], "BOUNDHULLED": hed[k]}
        for c, v in zip(["AABBMINX", "AABBMINY", "AABBMINZ", "AABBMAXX", "AABBMAXY", "AABBMAXZ"], aabbs[name]): vals[c] = "%.6f" % v
        role = role_of.get(name)
        if role in ("head", "lower"): vals["MATERIAL"] = MAIN_MAT
        if role in ("rings", "collar"): vals["MATERIAL"] = GLOW_MAT
        if name == SLOT["pedestal_glow"]: vals["MATERIAL"] = PEDESTAL_MAT
        for key, v in vals.items(): attrs[key].set("value", str(v))
        # our meshes are authored in figurine space: head = Headjnt offset only, children/lower = identity
        if role in ("head", "lower"):
            for c in props["Transform"]:
                c.set("value", "1.000000" if c.get("name").startswith("Scale") else "0.000000")
            if role == "head":
                [c for c in props["Transform"] if c.get("name") == "TransY"][0].set("value", "%.6f" % -PIVOT)
    spath = OUT + f"build/{SC}.SCENE.MXML"
    st.write(spath, encoding="utf-8", xml_declaration=True)
    compile_mxml(spath)
    # ---- materials
    # main material: the Astronaut figurine's plain lit material (diffuse/normal/masks), pointed at our textures
    m = open(mxml_of(BOB + "toysmbobblehead/toybackpack_mat.material.mbin")).read()
    m = m.replace("TEXTURES/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/SPACENOMANBACKPACK", TEX_PATH)
    assert TEX_PATH in m, "toybackpack_mat changed in a game update"
    m = re.sub(r'(<Data template="cTkMaterialData">\s*<Property name="Name" value=")[^"]*', r'\1' + PREFIX + '_BIOLUM_MAT', m)
    open(OUT + f"build/{PREFIX}_BIOLUM_MAT.MATERIAL.MXML", "w").write(m); compile_mxml(OUT + f"build/{PREFIX}_BIOLUM_MAT.MATERIAL.MXML")
    # glow material: the pedestal's unlit glow, recoloured cyan
    g = open(mxml_of(BOB + "octobobblehead/bobblebaseglowgreenmat.material.mbin")).read()
    g = re.sub(r'(<Data template="cTkMaterialData">\s*<Property name="Name" value=")[^"]*', r'\1' + PREFIX + '_GLOW_MAT', g)
    g = g.replace('<Property name="X" value="0.100500" />\n\t\t\t\t<Property name="Y" value="0.750000" />\n\t\t\t\t<Property name="Z" value="0.456675" />',
                  '<Property name="X" value="0.300000" />\n\t\t\t\t<Property name="Y" value="1.000000" />\n\t\t\t\t<Property name="Z" value="0.930000" />')
    assert "0.930000" in g, "glow material changed in a game update"
    open(OUT + f"build/{PREFIX}_GLOW_MAT.MATERIAL.MXML", "w").write(g); compile_mxml(OUT + f"build/{PREFIX}_GLOW_MAT.MATERIAL.MXML")
    # pedestal glow ring: the game's green pedestal glow (as on the original release), under our own name
    pg = open(mxml_of(BOB + "octobobblehead/bobblebaseglowgreenmat.material.mbin")).read()
    pg = re.sub(r'(<Data template="cTkMaterialData">\s*<Property name="Name" value=")[^"]*', r'\1' + PREFIX + '_PEDESTAL_MAT', pg)
    open(OUT + f"build/{PREFIX}_PEDESTAL_MAT.MATERIAL.MXML", "w").write(pg); compile_mxml(OUT + f"build/{PREFIX}_PEDESTAL_MAT.MATERIAL.MXML")
    textures()
    np.save(OUT + "meshes.npy", {k: v for k, v in meshes.items()}, allow_pickle=True)
    print("seam t=%.3f  verts=%d  indices=%d" % (T_SEAM, v0, bi))
    for n in order: print(" ", n, data[n]["nv"], "verts", data[n]["ni"] // 3, "tris")

if __name__ == "__main__":
    main()
