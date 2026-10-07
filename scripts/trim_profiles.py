#!/usr/bin/env python3
"""Remove the printer vendor profiles a portable build does not need.

OrcaSlicer 2.4.x reads every vendor profile shipped in resources/profiles each
time the filament selection dialog opens (about 8,000 files), which can take
minutes on Windows. Keeping only the vendors listed in "profile_vendors" (plus
the filament library and the generic profiles OrcaSlicer always installs)
makes the dialog open about ten times faster. The filaments offered for the
printer are unchanged: other vendors' filaments only target their own printers.
"""

import argparse
import json
import os
import shutil
import sys

# Always installed by OrcaSlicer: PresetBundle::ORCA_FILAMENT_LIBRARY and ORCA_DEFAULT_BUNDLE.
ALWAYS_KEPT = ["OrcaFilamentLibrary", "Custom"]


def fail(message):
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def vendor_names(profiles_dir):
    # A vendor is a <name>.json index next to a <name>/ folder; other files
    # (blacklist.json, hotend.stl...) are not vendors and are left alone.
    return sorted(
        name[:-5] for name in os.listdir(profiles_dir)
        if name.endswith(".json") and os.path.isdir(os.path.join(profiles_dir, name[:-5]))
    )


def preset_names(profiles_dir, vendor):
    index = load_json(os.path.join(profiles_dir, vendor + ".json"))
    return {
        entry["name"]: os.path.join(profiles_dir, vendor, entry["sub_path"])
        for key in ("machine_model_list", "machine_list", "process_list", "filament_list")
        for entry in index.get(key, [])
    }


def check_inheritance(profiles_dir, kept):
    # Presets inherit within their vendor or from the filament library; make
    # sure removing the other vendors broke no "inherits" link.
    library = set(preset_names(profiles_dir, "OrcaFilamentLibrary"))
    for vendor in kept:
        presets = preset_names(profiles_dir, vendor)
        for name, path in presets.items():
            if not os.path.isfile(path):
                continue
            parent = load_json(path).get("inherits", "")
            if parent and parent not in presets and parent not in library:
                fail(f'Le profil "{name}" ({vendor}) hérite de "{parent}", absent des profils conservés.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profiles", required=True, help="dossier resources/profiles de la version OrcaSlicer téléchargée")
    parser.add_argument("--settings", required=True, help="fichier de pré-réglages (portable/cc2-settings.json)")
    args = parser.parse_args()

    settings = load_json(args.settings)
    wanted = settings.get("profile_vendors", [])
    if not wanted:
        print("profile_vendors vide : tous les profils sont conservés.")
        return
    if settings["vendor"] not in wanted:
        fail(f'"{settings["vendor"]}" doit figurer dans "profile_vendors".')

    available = vendor_names(args.profiles)
    kept = list(dict.fromkeys(ALWAYS_KEPT + wanted))
    missing = [v for v in kept if v not in available]
    if missing:
        fail(f"Profils introuvables dans cette version d'OrcaSlicer : {', '.join(missing)}.")

    check_inheritance(args.profiles, kept)

    removed = [v for v in available if v not in kept]
    for vendor in removed:
        os.remove(os.path.join(args.profiles, vendor + ".json"))
        shutil.rmtree(os.path.join(args.profiles, vendor))

    print(f"Profils conservés : {', '.join(kept)}")
    print(f"{len(removed)} marques retirées")


if __name__ == "__main__":
    main()
