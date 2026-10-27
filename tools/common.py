"""Shared settings and helpers for the Alien Tentacle Figurine build."""
import os, shutil, subprocess, sys
import numpy as np

VERSION = "1.1.0"
AUTHOR = "MajorRoyMcCalluster"
MOD_NAME = "Alien Tentacle Figurine"            # display name
MOD_FOLDER = "AlienTentacleFigurine"            # folder inside GAMEDATA/MODS
RELEASE_NAME = "Alien Tentacle Figurine Replacer"
PREFIX = "ATF"                                  # file prefix for our materials / textures

# ---- which figurine this mod replaces
# The Atlas Figurine: sold in the Quicksilver shop (tier 1) on the Space Anomaly, so anyone can get it early.
# Its scene has the same joints and pedestal as the other figurines; every mesh links to its stream by name.
SLOT = dict(
    label="Atlas Figurine",
    scene="ATLASBOBBLEHEAD",                       # file stem; game files are stored lower case
    order=["ATLASMODEL", "SUB1ATLASMODEL", "SUB2ATLASMODEL", "BASE", "SUB1BASE", "BASEGLOW"],  # stream order in the geometry file
    roles={"head": "ATLASMODEL",                   # upper tendril, child of Headjnt -> wobbles
           "rings": "SUB1ATLASMODEL",              # glowing rings (child of head)
           "collar": "SUB2ATLASMODEL",             # glowing collar over the wobble seam (child of head)
           "lower": "BASEGLOW"},                   # foot + lower tendril, static
    pedestal="BASE", pedestal_glow="SUB1BASE",     # original pedestal geometry, kept
    base_offset=(0.0, 0.009608, -0.011222),        # pedestal node transform (used by the preview renders)
    text_keys=("UI_BOBBLE_ATLAS_NAME", "UI_BOBBLE_ATLAS_NAME_L", "UI_BOBBLE_ATLAS_DESC"),
    loc="NMS_LOC6",
)
SCENE_LC = SLOT["scene"].lower()

# in-game text (replaces the figurine's name and description)
ITEM_NAME = "ALIEN TENTACLE FIGURINE"
ITEM_NAME_L = "Alien Tentacle Figurine"
ITEM_DESC = ("A bioluminescent synthetic companion for your starship's cockpit, cast in the likeness of an alien tentacle. "
             "It wobbles.\n\nInstall to an <TECHNOLOGY>Inventory Slot<> to decorate your ship's interior.")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REPO, "work")              # extracted + decompiled game files, build output (git-ignored)
DIST = os.path.join(REPO, "dist")              # release zips (git-ignored)

BOB = "models/planets/biomes/common/buildings/props/bobbleheads/"
# game files the build reads (all lower case, as stored in the game's .pak files)
GAME_FILES = {
    BOB + SCENE_LC + ".scene.mbin": "NMSARC.EntitySceneMBIN.pak",
    BOB + SCENE_LC + ".geometry.mbin.pc": "NMSARC.MeshPlanetBIOMES.pak",
    BOB + SCENE_LC + ".geometry.data.mbin.pc": "NMSARC.MeshPlanetBIOMES.pak",
    BOB + SCENE_LC + "/tilingtexture_mat.material.mbin": "NMSARC.MetadataEtc.pak",          # pedestal (kept)
    BOB + "octobobblehead/bobblebaseglowgreenmat.material.mbin": "NMSARC.MetadataEtc.pak",  # template for the glow materials
    BOB + "toysmbobblehead/toybackpack_mat.material.mbin": "NMSARC.MetadataEtc.pak",       # template for the main material
}

def game_path(rel):
    return os.path.join(WORK, "game", rel)

def mxml_of(rel):
    """decompiled MXML path for a game file"""
    p = game_path(rel)
    for ext in (".mbin.pc", ".mbin"):
        if p.endswith(ext): return p[: -len(ext)] + ".MXML"
    raise ValueError(rel)

def find_mbincompiler():
    cand = [os.environ.get("MBINCOMPILER", "")]
    here = os.path.join(REPO, "tools", "bin")
    cand += [os.path.join(here, n) for n in ("MBINCompiler.exe", "MBINCompiler-linux", "MBINCompiler")]
    cand += [shutil.which(n) or "" for n in ("MBINCompiler", "MBINCompiler.exe", "MBINCompiler-linux")]
    for c in cand:
        if c and os.path.isfile(c): return c
    sys.exit("MBINCompiler not found. Put MBINCompiler.exe in tools/bin/ or set the MBINCOMPILER environment variable.")

def mbin(path, quiet=True):
    """compile an MXML or decompile an MBIN (MBINCompiler decides from the extension)"""
    r = subprocess.run([find_mbincompiler(), "-y"] + (["-q"] if quiet else []) + [path], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr); sys.exit("MBINCompiler failed on " + path)

# ---- small software rasteriser used by the checks and the preview renders
def bary_raster(pts, W, H):
    x0, y0 = np.floor(pts.min(0)).astype(int); x1, y1 = np.ceil(pts.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W - 1), min(y1, H - 1)
    if x1 < x0 or y1 < y0: return None
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1)); xs, ys = xs.ravel(), ys.ravel()
    px, py = xs + 0.5, ys + 0.5
    (ax, ay), (bx, by), (cx, cy) = pts
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(den) < 1e-12: return None
    l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
    l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
    l3 = 1 - l1 - l2
    m = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
    return xs[m], ys[m], np.stack([l1[m], l2[m], l3[m]], 1)

def sample(img, uv):
    h, w = img.shape[:2]
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1.001); y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int); fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
