"""Release checks for the built mod folder. Usage: python tools/check.py <mod folder>  (exit 1 on any failure)"""
import os, re, sys, struct, shutil, subprocess, base64, glob
import numpy as np
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

def run(MOD):
    W = os.path.join(C.WORK, "check") + os.sep; shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
    fails, notes = [], []
    def ok(cond, msg):
        (notes if cond else fails).append(("PASS " if cond else "FAIL ") + msg)

    B = MOD + "/MODELS/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/BOBBLEHEADS/"
    files = {"scene": B + "OCTOBOBBLEHEAD.SCENE.MBIN", "geo": B + "OCTOBOBBLEHEAD.GEOMETRY.MBIN.PC",
             "data": B + "OCTOBOBBLEHEAD.GEOMETRY.DATA.MBIN.PC",
             "mat": B + f"OCTOBOBBLEHEAD/{C.PREFIX}_BIOLUM_MAT.MATERIAL.MBIN", "glow": B + f"OCTOBOBBLEHEAD/{C.PREFIX}_GLOW_MAT.MATERIAL.MBIN"}
    for k, f in files.items(): ok(os.path.exists(f), f"file present: {os.path.relpath(f, MOD)}")

    # 1) every MBIN decompiles, and recompiling the MXML reproduces the same bytes
    mx = {}
    for k, f in files.items():
        dst = W + os.path.basename(f).lower(); shutil.copy(f, dst)
        r = subprocess.run([C.find_mbincompiler(), "-y", "-q", dst], capture_output=True, text=True)
        xml = [p for p in glob.glob(W + "*.MXML") if os.path.basename(p).lower().startswith(os.path.basename(f).lower().split(".")[0]) and
               os.path.basename(p).lower().replace(".mxml", "") == os.path.basename(dst).replace(".mbin.pc", "").replace(".mbin", "")]
        ok(r.returncode == 0 and xml, f"{k}: decompiles")
        if not xml: continue
        mx[k] = xml[0]
        rt = W + "rt_" + os.path.basename(xml[0]); shutil.copy(xml[0], rt)
        subprocess.run([C.find_mbincompiler(), "-y", "-q", rt], capture_output=True)
        out = [p for p in glob.glob(W + "rt_*") if not p.endswith(".MXML") and os.path.basename(p).lower().startswith(os.path.basename(rt).lower().replace(".mxml", ""))]
        if k == "data":
            # MBINCompiler mis-writes position-stream lengths on every compile (even the game's own file),
            # so check instead that our patched file decompiles to exactly the streams the header points at
            pass
        else:
            same = out and open(out[0], "rb").read() == open(f, "rb").read()
            ok(bool(same), f"{k}: recompiles byte-identical")
        for p in out: os.remove(p)

    # 2) geometry streams
    hdr = open(mx["geo"]).read(); raw = open(files["data"], "rb").read()
    meshes = {}
    for m in re.finditer(r'IdString" value="([^"]*)" />\s*<Property name="Hash" value="(\d+)" />\s*<Property name="VertexDataSize" value="(\d+)" />\s*<Property name="VertexDataOffset" value="(\d+)" />\s*<Property name="VertexPositionDataSize" value="(\d+)" />\s*<Property name="VertexPositionDataOffset" value="(\d+)" />\s*<Property name="IndexDataSize" value="(\d+)" />\s*<Property name="IndexDataOffset" value="(\d+)" />', hdr):
        name, h = m.group(1), int(m.group(2)); vs, vo, ps, po, isz, io = map(int, m.groups()[2:])
        ok(vo + vs + isz <= len(raw) and po + ps <= len(raw), f"{name}: stream offsets inside data file")
        vb = raw[vo:vo + vs]; ib = raw[vo + io:vo + io + isz]; pb = raw[po:po + ps]
        n = vs // 8
        idx = np.frombuffer(ib, "<u2").astype(int).reshape(-1, 3); pos = np.frombuffer(pb, "<f2").reshape(-1, 8).astype(np.float64)
        ok(len(pos) == n and idx.max() < n and idx.min() >= 0, f"{name}: {n} verts, {len(idx)} tris, indices in range")
        ok(np.isfinite(pos).all(), f"{name}: no NaN/inf in positions/UVs")
        meshes[name] = (pos, idx, vb, h)
    dx = open(mx["data"]).read()
    for m in re.finditer(r'IdString" value="([^"]*)".*?MeshDataStream" value="([^"]*)".*?MeshPositionDataStream" value="([^"]*)"', dx, re.S):
        pos, idx, vb, h = meshes[m.group(1)]
        ok(base64.b64decode(m.group(3)) == pos.astype("<f2").tobytes() and base64.b64decode(m.group(2))[:len(vb)] == vb,
           f"{m.group(1)}: data file's own stream lists match the header offsets")
    hp = lambda tag: [int(x) for x in re.findall(r'<Property name="%s" value="(\d+)" _index' % tag, hdr)]
    starts, ends = hp("MeshVertRStart"), hp("MeshVertREnd")
    order = ["OCTOLOW", "SUB1OCTOLOW", "SUB2OCTOLOW", "SPLASHLOW", "BASE", "SUB1BASE"]
    ok(list(meshes) == order, "mesh order matches original")
    v0 = 0
    for k, nm in enumerate(order):
        n = len(meshes[nm][0]); ok(starts[k] == v0 and ends[k] == v0 + n - 1, f"{nm}: vertex range in header"); v0 += n
    ok(int(re.search(r'VertexCount" value="(\d+)"', hdr).group(1)) == v0, "total vertex count")
    ok(int(re.search(r'IndexCount" value="(\d+)"', hdr).group(1)) == sum(m[1].size for m in meshes.values()), "total index count")

    def unpack(v):
        v = v.astype(np.int64); x = (v & 1023) / 511.5 - 1; y = ((v >> 10) & 1023) / 511.5 - 1; z = 1 - abs(x) - abs(y)
        nx = np.where(z < 0, (1 - abs(y)) * np.sign(x), x); ny = np.where(z < 0, (1 - abs(x)) * np.sign(y), y)
        N = np.stack([nx, ny, z], 1); return N / np.linalg.norm(N, axis=1, keepdims=True)
    for nm in order[:4]:
        pos, idx, vb, h = meshes[nm]
        N = unpack(np.frombuffer(vb, dtype=[("c", "u1", 4), ("n", "<u4")])["n"])
        P = pos[:, :3]
        fn = np.cross(P[idx[:, 1]] - P[idx[:, 0]], P[idx[:, 2]] - P[idx[:, 0]]); area = np.linalg.norm(fn, axis=1)
        good = area > 1e-12
        agree = ((fn[good] * N[idx[good]].mean(1)).sum(1) > 0).mean()
        ok(agree > 0.995, f"{nm}: faces wound outward ({agree:.1%})")
        ok((pos[:, 4:6] >= -0.001).all() and (pos[:, 4:6] <= 1.001).all(), f"{nm}: UVs within 0-1")

    # 3) scene: links, counts, AABBs match the real data, materials exist
    sc = open(mx["scene"]).read()
    for m in re.finditer(r'<Property name="Name" value="(\w+)" />\s*<Property name="NameHash" value="(\d+)" />\s*<Property name="Type" value="MESH"', sc):
        seg = sc[m.end():m.end() + 9000]
        a = dict(re.findall(r'<Property name="Name" value="([A-Z0-9]+)" />\s*<Property name="Value" value="([^"]*)"', seg)[:22])
        nm = m.group(1).upper(); pos, idx, vb, h = meshes[nm]
        ok(int(a["HASH"]) == h == int(m.group(2)), f"scene {m.group(1)}: hash links to its stream")
        ok(int(a["BATCHCOUNT"]) == idx.size and int(a["VERTRENDGRAPHIC"]) == len(pos) - 1, f"scene {m.group(1)}: counts match")
        if nm in order[:4]:
            lo, hi = pos[:, :3].min(0), pos[:, :3].max(0)
            sa = np.array([float(a[k]) for k in ("AABBMINX", "AABBMINY", "AABBMINZ", "AABBMAXX", "AABBMAXY", "AABBMAXZ")])
            ok(np.abs(sa - np.r_[lo, hi]).max() < 2e-3, f"scene {m.group(1)}: bounding box matches mesh")
        mat = a["MATERIAL"].replace("\\", "/").split("/")[-1]
        in_mod = os.path.exists(B + "OCTOBOBBLEHEAD/" + mat)
        in_game = os.path.exists(C.game_path(C.BOB + "octobobblehead/" + mat.lower()))
        ok(in_mod or in_game, f"scene {m.group(1)}: material {mat} exists ({'mod' if in_mod else 'game'})")

    # 4) materials point at textures that ship with the mod; DDS files are complete
    for k in ("mat",):
        for t in re.findall(r'Map" value="([^"]+)"', open(mx[k]).read()):
            ok(os.path.exists(MOD + "/" + t), f"material texture present: {t}")
    def dds_ok(p):
        d = open(p, "rb").read()
        h, w, lin, mips = struct.unpack("<II I", d[12:24])[0], struct.unpack("<I", d[16:20])[0], 0, struct.unpack("<I", d[28:32])[0]
        four = d[84:88]; blk = 8 if four == b"DXT1" else 16
        size, cw, ch = 0, w, h
        for _ in range(mips):
            size += max(1, (cw + 3) // 4) * max(1, (ch + 3) // 4) * blk; cw, ch = max(1, cw // 2), max(1, ch // 2)
        full = 1 + int(np.log2(max(w, h)))
        return d[:4] == b"DDS " and len(d) == 128 + size and mips == full, f"{w}x{h} {four.decode()} {mips} mips"
    for p in sorted(glob.glob(MOD + "/TEXTURES/**/*.DDS", recursive=True)):
        good, info = dds_ok(p); ok(good, f"DDS complete: {os.path.basename(p)} ({info})")

    # 5) language patches are valid XML in the game's localisation format
    for p in sorted(glob.glob(MOD + "/LANGUAGE/*.EXML")):
        try:
            root = ET.parse(p).getroot()
            col = "USEnglish" if "USENGLISH" in p else "English"
            ents = root.findall("./Property[@name='Table']/Property")
            good = root.get("template") == "cTkLocalisationTable" and len(ents) == 3 and all(
                e.find("./Property[@name='Id']") is not None and e.find(f"./Property[@name='{col}']") is not None for e in ents)
            ok(good, f"language patch valid: {os.path.basename(p)}")
        except Exception as e:
            ok(False, f"language patch parses: {os.path.basename(p)} ({e})")

    # 6) nothing extra in the folder
    allowed = {".MBIN", ".PC", ".DDS", ".EXML", ".TXT"}
    extra = [p for p in glob.glob(MOD + "/**/*", recursive=True) if os.path.isfile(p) and os.path.splitext(p)[1].upper() not in allowed]
    ok(not extra, "no stray files in the mod folder")
    ok(not any(w in open(p, "rb").read().decode("latin1").upper() for w in ("MIA_", "MIAKEEPSAKE", "ATD_")
                 for p in glob.glob(MOD + "/**/*.*", recursive=True) if not p.endswith(".DDS")), "no leftover old names in any file")
    ok(not any(w in os.path.relpath(p, MOD).upper() for w in ("ATD_", "MIA") for p in glob.glob(MOD + "/**/*", recursive=True)), "no old names in file paths")
    for n in notes: print(n)
    for f in fails: print(f)
    print(f"\n{len(notes)} passed, {len(fails)} failed")
    return not fails

if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1]) else 1)
