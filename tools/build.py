"""Build the Alien Tentacle Figurine mod from your own No Man's Sky install.

    python tools/build.py --game "C:\\Program Files (x86)\\Steam\\steamapps\\common\\No Man's Sky"

Steps: extract the few game files it needs (HGPAKtool) -> decompile them (MBINCompiler) -> generate the model,
materials, textures and text -> run the release checks -> zip into dist/.
Options: --extracted DIR  use already-extracted game files instead of reading the .pak files
         --install        also copy the finished mod into the game's GAMEDATA/MODS folder
         --no-check       skip the release checks (not recommended)
"""
import argparse, html, os, shutil, subprocess, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

def extract(game, extracted=None):
    dst = os.path.join(C.WORK, "game")
    shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
    if extracted:
        for rel in C.GAME_FILES:
            src = os.path.join(extracted, rel)
            if not os.path.isfile(src): sys.exit(f"missing in --extracted folder: {rel}")
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True); shutil.copy(src, os.path.join(dst, rel))
    else:
        banks = os.path.join(game, "GAMEDATA", "PCBANKS")
        if not os.path.isdir(banks): sys.exit(f"can't find {banks} - pass your No Man's Sky folder with --game")
        try:
            import hgpaktool  # noqa: F401
        except ImportError:
            sys.exit("HGPAKtool is missing: pip install hgpaktool")
        paks = sorted({os.path.join(banks, p) for p in C.GAME_FILES.values()})
        filters = [f"-f=*{rel}" for rel in C.GAME_FILES]   # wildcard form: a pak without the file is not an error
        r = subprocess.run([sys.executable, "-c", "from hgpaktool.cli import run; run()", "-U", *filters, "-O", dst, *paks],
                           capture_output=True, text=True)
        missing = [rel for rel in C.GAME_FILES if not os.path.isfile(os.path.join(dst, rel))]
        if r.returncode != 0 or missing:
            # files moved between paks in a game update: search every pak
            r = subprocess.run([sys.executable, "-c", "from hgpaktool.cli import run; run()", "-U", *filters, "-O", dst, banks],
                               capture_output=True, text=True)
            missing = [rel for rel in C.GAME_FILES if not os.path.isfile(os.path.join(dst, rel))]
            if missing: print(r.stdout, r.stderr); sys.exit("couldn't extract: " + ", ".join(missing))
    for rel in C.GAME_FILES:
        C.mbin(C.game_path(rel))
        if not os.path.isfile(C.mxml_of(rel)): sys.exit("decompile failed: " + rel)
    print(f"extracted and decompiled {len(C.GAME_FILES)} game files")

def esc(s): return html.escape(s, quote=True).replace("&#x27;", "'").replace("\n", "&#xA;")

def assemble():
    out = os.path.join(C.WORK, "out")
    m = os.path.join(C.WORK, "mod", C.MOD_FOLDER); shutil.rmtree(os.path.dirname(m), ignore_errors=True)
    G = os.path.join(m, "MODELS/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/BOBBLEHEADS")
    T = os.path.join(m, "TEXTURES/PLANETS/BIOMES/COMMON/BUILDINGS/PROPS/ALIENTENTACLE")
    SC = C.SLOT["scene"]
    for d in (G + "/" + SC, T, m + "/LANGUAGE"): os.makedirs(d)
    for f in (f"{SC}.SCENE.MBIN", f"{SC}.GEOMETRY.MBIN.PC", f"{SC}.GEOMETRY.DATA.MBIN.PC"):
        shutil.copy(os.path.join(out, "build", f), G)
    for f in (f"{C.PREFIX}_BIOLUM_MAT.MATERIAL.MBIN", f"{C.PREFIX}_GLOW_MAT.MATERIAL.MBIN", f"{C.PREFIX}_PEDESTAL_MAT.MATERIAL.MBIN"):
        shutil.copy(os.path.join(out, "build", f), G + "/" + SC)
    for f in os.listdir(os.path.join(out, "tex")): shutil.copy(os.path.join(out, "tex", f), T)
    entries = dict(zip(C.SLOT["text_keys"], (C.ITEM_NAME, C.ITEM_NAME_L, C.ITEM_DESC)))
    for fn, col in ((C.SLOT["loc"] + "_ENGLISH.EXML", "English"), (C.SLOT["loc"] + "_USENGLISH.EXML", "USEnglish")):
        o = ['<?xml version="1.0" encoding="utf-8"?>', f'<!-- {C.MOD_NAME} v{C.VERSION}: renames the {C.SLOT["label"]} -->',
             '<Data template="cTkLocalisationTable">', '\t<Property name="Table">']
        for k, v in entries.items():
            o += [f'\t\t<Property name="Table" value="TkLocalisationEntry" _id="{k}">', f'\t\t\t<Property name="Id" value="{k}" />',
                  f'\t\t\t<Property name="{col}" value="{esc(v)}" />', '\t\t</Property>']
        o += ['\t</Property>', '</Data>', '']
        open(os.path.join(m, "LANGUAGE", fn), "w", encoding="utf-8", newline="\r\n").write("\n".join(o))
    readme = open(os.path.join(C.REPO, "tools", "mod_readme.txt"), encoding="utf-8").read()
    readme = readme.format(name=C.MOD_NAME, version=C.VERSION, author=C.AUTHOR, folder=C.MOD_FOLDER, item=C.ITEM_NAME_L,
                           slot=C.SLOT["label"], slot_uc=C.SLOT["label"].upper(), scene=C.SLOT["scene"], loc=C.SLOT["loc"])
    open(os.path.join(m, "README.txt"), "w", encoding="utf-8", newline="\r\n").write(readme)
    return m

def package(m):
    os.makedirs(C.DIST, exist_ok=True)
    z = os.path.join(C.DIST, f"{C.RELEASE_NAME}-{C.VERSION}.zip")
    if os.path.exists(z): os.remove(z)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(m):
            for f in sorted(files):
                p = os.path.join(root, f); zf.write(p, os.path.relpath(p, os.path.dirname(m)))
    return z

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="your No Man's Sky folder")
    ap.add_argument("--extracted", help="folder of already-extracted game files (lower-case game paths)")
    ap.add_argument("--install", action="store_true", help="copy the built mod into GAMEDATA/MODS")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()
    if not (a.game or a.extracted): ap.error("pass --game (or --extracted)")
    extract(a.game, a.extracted)
    import model; model.main()
    m = assemble()
    if not a.no_check:
        import check
        if not check.run(m): sys.exit("release checks failed - nothing was packaged")
    z = package(m)
    print("built:", z)
    if a.install:
        if not a.game: sys.exit("--install needs --game")
        dst = os.path.join(a.game, "GAMEDATA", "MODS", C.MOD_FOLDER)
        shutil.rmtree(dst, ignore_errors=True); shutil.copytree(m, dst)
        print("installed:", dst)

if __name__ == "__main__":
    main()
