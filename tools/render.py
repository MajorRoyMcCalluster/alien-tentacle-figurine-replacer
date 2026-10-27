"""Preview renders of the built mod for the Nexus page and README.  Usage: python tools/render.py  (after build.py)"""
import numpy as np, re, os, sys, shutil, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from common import bary_raster, sample

REL = os.path.join(C.WORK, "mod", C.MOD_FOLDER) + "/"
OUT = os.path.join(C.REPO, "nexus", "images") + "/"; os.makedirs(OUT, exist_ok=True)
B = REL + "MODELS/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/BOBBLEHEADS/"
W = os.path.join(C.WORK, "render") + "/"; shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
SC = C.SLOT["scene"]; R_ = C.SLOT["roles"]
HEAD = (R_["head"], R_["rings"], R_["collar"]); GLOW = (R_["rings"], R_["collar"], C.SLOT["pedestal_glow"])
for f in (f"{SC}.GEOMETRY.MBIN.PC", f"{SC}.GEOMETRY.DATA.MBIN.PC"): shutil.copy(B + f, W + f.lower())
C.mbin(W + C.SCENE_LC + ".geometry.mbin.pc")

def font(name, size):
    for d in ("C:/Windows/Fonts/", os.path.expanduser("~/.fonts/"), "/mnt/user-data/uploads/Fonts/"):
        if os.path.isfile(d + name): return ImageFont.truetype(d + name, size)
    for f in ("DejaVuSansCondensed-Bold.ttf", "DejaVuSans.ttf"):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()
hdr = open(W + C.SCENE_LC + ".geometry.MXML").read(); raw = open(W + C.SCENE_LC + ".geometry.data.mbin.pc", "rb").read()
tex = np.asarray(Image.open(REL + f"TEXTURES/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/ALIENTENTACLE/{C.PREFIX}_BIOLUM.DDS").convert("RGB")).astype(np.float32) / 255

def unpack(v):
    v = v.astype(np.int64); x = (v & 1023) / 511.5 - 1; y = ((v >> 10) & 1023) / 511.5 - 1; z = 1 - abs(x) - abs(y)
    nx = np.where(z < 0, (1 - abs(y)) * np.sign(x), x); ny = np.where(z < 0, (1 - abs(x)) * np.sign(y), y)
    N = np.stack([nx, ny, z], 1); return N / np.linalg.norm(N, axis=1, keepdims=True)
meshes = {}
for m in re.finditer(r'IdString" value="([^"]*)" />\s*<Property name="Hash" value="\d+" />\s*<Property name="VertexDataSize" value="(\d+)" />\s*<Property name="VertexDataOffset" value="(\d+)" />\s*<Property name="VertexPositionDataSize" value="(\d+)" />\s*<Property name="VertexPositionDataOffset" value="(\d+)" />\s*<Property name="IndexDataSize" value="(\d+)" />\s*<Property name="IndexDataOffset" value="(\d+)" />', hdr):
    name = m.group(1); vs, vo, ps, po, isz, io = map(int, m.groups()[1:])
    vb = raw[vo:vo + vs]; n = vs // 8
    N = unpack(np.frombuffer(vb, dtype=[("c", "u1", 4), ("n", "<u4")])["n"])
    idx = np.frombuffer(raw[vo + io:vo + io + isz], "<u2").astype(int).reshape(-1, 3)
    pos = np.frombuffer(raw[po:po + ps], "<f2").reshape(-1, 8).astype(np.float64)
    meshes[name] = (pos[:, :3], N, pos[:, 4:6], idx)

def rot(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    return Rx @ Ry

def tilt(ax, az):
    ax, az = math.radians(ax), math.radians(az)
    Rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    Rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    return Rz @ Rx

def render(W_, H_, yaw=25, pitch=-12, wob=(0, 0), ppu=2600, cx=0.5, cy=0.55, focus_y=0.19, bg=None):
    R = rot(yaw, pitch)
    col = np.zeros((H_, W_, 3), np.float32); glow = np.zeros((H_, W_, 3), np.float32)
    zb = np.full((H_, W_), -9.0); cov = np.zeros((H_, W_), bool)
    L1 = np.array([-0.55, 0.65, -0.52]); L1 /= np.linalg.norm(L1)      # key light
    L2 = np.array([0.8, 0.1, 0.4]); L2 /= np.linalg.norm(L2)            # cyan rim from behind-right
    V = np.array([0, 0, -1.0])
    piv = np.array([0, 0.135, 0])
    for name, (P, N, UV, idx) in meshes.items():
        Q = P.copy(); NN = N.copy()
        if name in (C.SLOT["pedestal"], C.SLOT["pedestal_glow"]): Q = Q + np.array(C.SLOT["base_offset"])
        if name in HEAD:
            T = tilt(*wob); Q = (Q - piv) @ T.T + piv; NN = NN @ T.T
        Q = (Q - [0, focus_y, 0]) @ R.T; NN = NN @ R.T
        isglow = name in GLOW
        for f in idx:
            q = Q[f]
            fn = np.cross(q[1] - q[0], q[2] - q[0])
            if fn[2] >= 0: continue
            pts = np.stack([q[:, 0] * ppu + W_ * cx, (-q[:, 1]) * ppu + H_ * cy], -1)
            r = bary_raster(pts, W_, H_)
            if not r: continue
            xs, ys, bc = r; d = -(bc @ q[:, 2])
            k = d > zb[ys, xs]; xs, ys, bc, d = xs[k], ys[k], bc[k], d[k]
            if not len(xs): continue
            n = bc @ NN[f]; n /= np.linalg.norm(n, axis=1, keepdims=True)
            zb[ys, xs] = d; cov[ys, xs] = True
            if isglow:
                c = np.array([0.30, 1.0, 0.93]) if name != "SUB1BASE" else np.array([0.10, 0.80, 0.50])
                shade = 0.85 + 0.15 * np.clip(-(n @ V), 0, 1)
                col[ys, xs] = c * shade[:, None]; glow[ys, xs] = c * 1.0
                continue
            if name == "BASE":
                base = np.array([0.10, 0.11, 0.12])
            else:
                base = sample(tex, bc @ UV[f])
            dif = np.clip(n @ L1, 0, 1)[:, None]
            H = L1 - V; H /= np.linalg.norm(H)
            spec = np.clip(n @ H, 0, 1)[:, None] ** 60
            rim = np.clip(n @ L2, 0, 1)[:, None] ** 2
            fres = (1 - np.clip(-(n @ V), 0, 1))[:, None] ** 3
            c = base * (0.18 + 0.72 * dif) + 0.45 * spec + rim * np.array([0.25, 0.8, 0.9]) * 0.45 + fres * np.array([0.3, 0.7, 1.0]) * 0.35
            if name != "BASE":
                bright = np.clip((base[:, 1] - base[:, 2]) * 8, 0, 1)[:, None]  # painted cyan spots/stripes only (green > blue)
                glow[ys, xs] = base * bright * 0.55
            col[ys, xs] = c
    # background
    if bg is None:
        yy, xx = np.mgrid[0:H_, 0:W_]
        r = np.sqrt(((xx - W_ * cx) / W_) ** 2 + ((yy - H_ * 0.45) / H_) ** 2)
        bgc = np.array([0.02, 0.05, 0.08])[None, None] * (1 - np.clip(r * 1.2, 0, 1))[..., None] + np.array([0.008, 0.01, 0.014])
        rng = np.random.default_rng(4)
        for _ in range(500):
            sx, sy = rng.integers(0, W_), rng.integers(0, H_); bgc[sy, sx] += rng.uniform(0.2, 0.8)
    else:
        bgc = bg
    out = np.where(cov[..., None], col, bgc)
    # bloom from glow buffer
    g = Image.fromarray((np.clip(glow, 0, 1) * 255).astype(np.uint8))
    b1 = np.asarray(g.filter(ImageFilter.GaussianBlur(W_ / 160))).astype(np.float32) / 255
    b2 = np.asarray(g.filter(ImageFilter.GaussianBlur(W_ / 45))).astype(np.float32) / 255
    out = out + 0.9 * b1 + 0.7 * b2
    # soft floor reflection glow under the pedestal
    return Image.fromarray((np.clip(out, 0, 1) ** (1 / 1.05) * 255).astype(np.uint8))

if __name__ == "__main__":
    # 1) hero 1920x1080 with title
    hero = render(1920, 1080, yaw=28, pitch=-10, ppu=2550, cx=0.66, cy=0.53, focus_y=0.19)
    d = ImageDraw.Draw(hero)
    t1 = font("AGENCYB.TTF", 120); t2 = font("AGENCYR.TTF", 44)
    d.text((110, 330), "ALIEN TENTACLE", font=t1, fill=(110, 255, 235))
    d.text((110, 450), "FIGURINE", font=t1, fill=(110, 255, 235))
    d.text((114, 600), "A bioluminescent cockpit companion", font=t2, fill=(190, 225, 235))
    d.text((114, 652), "that wobbles while you fly.", font=t2, fill=(190, 225, 235))
    d.text((114, 760), f"NO MAN'S SKY  ·  FIGURINE REPLACER  ·  v{C.VERSION}", font=font("AGENCYR.TTF", 30), fill=(120, 170, 185))
    hero.save(OUT + "01_hero.jpg", quality=93)
    # 2) clean turntable trio
    trio = Image.new("RGB", (1920, 1080))
    for i, yaw in enumerate((-35, 25, 100)):
        im = render(640, 1080, yaw=yaw, pitch=-8, ppu=2300, cx=0.5, cy=0.52, focus_y=0.19)
        trio.paste(im, (i * 640, 0))
    trio.save(OUT + "02_angles.jpg", quality=93)
    # 3) wobble sequence (still) + animated GIF
    seq = Image.new("RGB", (1920, 1080))
    for i, w in enumerate(((0, -9), (0, 0), (0, 9))):
        seq.paste(render(640, 1080, yaw=0, pitch=-6, wob=w, ppu=2300, cx=0.5, cy=0.52, focus_y=0.19), (i * 640, 0))
    dd = ImageDraw.Draw(seq); f3 = font("AGENCYR.TTF", 40)
    for i, t in enumerate(("WOBBLE", "REST", "WOBBLE")): dd.text((i * 640 + 320 - dd.textlength(t, font=f3) / 2, 1018), t, font=f3, fill=(120, 200, 210))
    seq.save(OUT + "03_wobble.jpg", quality=93)
    frames = []
    for k in range(24):
        a = 9 * math.sin(2 * math.pi * k / 24); b = 4 * math.sin(4 * math.pi * k / 24 + 0.7)
        frames.append(render(480, 640, yaw=20, pitch=-8, wob=(b, a), ppu=1450, cx=0.5, cy=0.55, focus_y=0.19).convert("P", palette=Image.ADAPTIVE))
    frames[0].save(OUT + "04_wobble.gif", save_all=True, append_images=frames[1:], duration=60, loop=0)
    # 4) close-up of the glowing collar and rings
    close = render(1920, 1080, yaw=40, pitch=-5, ppu=6200, cx=0.5, cy=0.5, focus_y=0.20)
    close.save(OUT + "05_closeup.jpg", quality=93)
    print("ok")
