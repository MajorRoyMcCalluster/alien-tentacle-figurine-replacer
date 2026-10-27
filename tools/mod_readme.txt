{name} v{version}  by {author}
============================================================
A figurine replacer for No Man's Sky. Replaces the {slot} cockpit adornment
with a glowing alien tentacle on a suction-cup foot. The top half wobbles with your ship,
glowing rings run up its length, and the item is renamed "{item}" in game.

INSTALL
  1. Extract the "{folder}" folder into:  No Man's Sky\GAMEDATA\MODS\
     (create the MODS folder if it doesn't exist)
  2. Install the {slot} in your starship's inventory and look at your dashboard.

GETTING THE {slot_uc}
  It's the easiest figurine to get, early in any save:
  - Buy it with Quicksilver from the Quicksilver Synthesis Companion on the Space Anomaly
    (call in the Anomaly from your starship's quick menu).
  - Some reward starships come with it already installed.

UNINSTALL
  Delete the "{folder}" folder. Nothing is saved to your game, so it's safe to remove any time.

COMPATIBILITY
  - Visual only. Your save is never changed, and the figurine keeps its normal in-game bonus.
  - Multiplayer safe: other players see the normal {slot}.
  - Conflicts only with other mods that replace the {slot} ({scene}) model.
  - Works alongside other figurine mods for different figurines.
  - The new name is in English and US English; other languages show the original name.
  - A future game update that changes the {slot} may need a mod update.

FILES
  MODELS\...\BOBBLEHEADS\{scene}.*         new model (geometry + scene)
  MODELS\...\BOBBLEHEADS\{scene}\ATF_*     materials
  TEXTURES\...\PROPS\ALIENTENTACLE\ATF_*          textures
  LANGUAGE\{loc}_*.EXML                        item name and description

CREDITS
  Built with MBINCompiler (monkeyman192 and the NMS modding community) and HGPAKtool.
