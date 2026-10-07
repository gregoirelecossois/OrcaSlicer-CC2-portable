#!/usr/bin/env python3
"""Remove the profiles a single-printer portable build does not need.

OrcaSlicer 2.4.x parses every preset of the installed vendors at startup, and
re-reads every vendor shipped in resources/profiles each time the filament
selection dialog opens. Fewer profiles make both faster. Driven by
portable/cc2-settings.json:

  profile_vendors          printer vendors kept; the others are removed
                           ("OrcaFilamentLibrary" and "Custom" are always kept,
                           OrcaSlicer installs them whatever the printer).
  printer_presets_only     keep only the vendor presets of "printer_model"
                           (all its nozzles): its printers, the print profiles
                           and filaments compatible with them.
  filament_library_brands  filament brands kept in OrcaFilamentLibrary
                           (filament_vendor value, e.g. "Generic"); empty = all.

The presets the kept ones inherit from are always kept.
"""

import argparse
import json
import os
import shutil
import sys

LIBRARY = "OrcaFilamentLibrary"
# Always installed by OrcaSlicer: PresetBundle::ORCA_FILAMENT_LIBRARY and ORCA_DEFAULT_BUNDLE.
ALWAYS_KEPT = [LIBRARY, "Custom"]
# Fallback filament when a selection is invalid: PresetBundle::ORCA_DEFAULT_FILAMENT.
DEFAULT_FILAMENT = "Generic PLA @System"
LISTS = ("machine_model_list", "machine_list", "process_list", "filament_list")


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


class Vendor:
    def __init__(self, profiles_dir, name):
        self.name = name
        self.dir = os.path.join(profiles_dir, name)
        self.index_path = os.path.join(profiles_dir, name + ".json")
        self.index = load_json(self.index_path)
        # preset name -> (list key, sub_path)
        self.entries = {e["name"]: (key, e["sub_path"]) for key in LISTS for e in self.index.get(key, [])}
        self._cache = {}

    def preset(self, name):
        if name not in self._cache:
            path = os.path.join(self.dir, self.entries[name][1])
            self._cache[name] = load_json(path) if os.path.isfile(path) else {}
        return self._cache[name]

    def names(self, key):
        return [n for n, (k, _) in self.entries.items() if k == key]

    def instantiable(self, key):
        return [n for n in self.names(key) if self.preset(n).get("instantiation") == "true"]

    def keep_only(self, kept):
        removed = [n for n in self.entries if n not in kept]
        if not removed:
            return 0
        for key in LISTS:
            if key in self.index:
                self.index[key] = [e for e in self.index[key] if e["name"] in kept]
        with open(self.index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.index, f, indent=4, ensure_ascii=False)
            f.write("\n")
        kept_files = {os.path.normpath(self.entries[n][1]) for n in kept if n in self.entries}
        for root, _, files in os.walk(self.dir):
            for file in files:
                rel = os.path.normpath(os.path.relpath(os.path.join(root, file), self.dir))
                if file.endswith(".json") and rel not in kept_files:
                    os.remove(os.path.join(root, file))
        return len(removed)


class Profiles:
    def __init__(self, profiles_dir, vendors):
        self.vendors = {v: Vendor(profiles_dir, v) for v in vendors}
        self.library = self.vendors[LIBRARY]

    def owner(self, vendor, name):
        # Presets inherit within their vendor, or from the filament library.
        for v in (vendor, self.library):
            if name in v.entries:
                return v
        return None

    def effective(self, vendor, name, key):
        """Value of key for a preset, following its "inherits" chain."""
        v = vendor
        while name:
            v = self.owner(v, name)
            if v is None:
                return None
            preset = v.preset(name)
            if key in preset:
                return preset[key]
            name = preset.get("inherits", "")
        return None

    def closure(self, roots):
        """roots: (vendor, name) pairs -> {vendor name: set of preset names}, ancestors included."""
        kept = {v: set() for v in self.vendors}
        todo = list(roots)
        while todo:
            vendor, name = todo.pop()
            owner = self.owner(vendor, name)
            if owner is None:
                fail(f'Le profil "{name}" ({vendor.name}) est introuvable dans les profils conservés.')
            if name in kept[owner.name]:
                continue
            kept[owner.name].add(name)
            parent = owner.preset(name).get("inherits", "")
            if parent:
                todo.append((owner, parent))
        return kept


def printer_roots(profiles, vendor, model):
    """The vendor presets used by printer "model": its printers, compatible print profiles and filaments."""
    if model not in vendor.entries:
        fail(f'Modèle "{model}" introuvable dans les profils {vendor.name}.')
    machines = {n for n in vendor.instantiable("machine_list")
                if profiles.effective(vendor, n, "printer_model") == model}
    if not machines:
        fail(f'Aucune imprimante "{model}" dans les profils {vendor.name}.')
    roots = [model] + sorted(machines)
    for key in ("process_list", "filament_list"):
        for name in vendor.instantiable(key):
            printers = profiles.effective(vendor, name, "compatible_printers") or []
            condition = profiles.effective(vendor, name, "compatible_printers_condition") or ""
            # No list and no condition: compatible with every printer.
            if set(printers) & machines or (not printers and not condition):
                roots.append(name)
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profiles", required=True, help="dossier resources/profiles de la version OrcaSlicer téléchargée")
    parser.add_argument("--settings", required=True, help="fichier de pré-réglages (portable/cc2-settings.json)")
    args = parser.parse_args()

    settings = load_json(args.settings)
    wanted = settings.get("profile_vendors", [])
    brands = settings.get("filament_library_brands", [])
    printer_only = settings.get("printer_presets_only", False)

    available = vendor_names(args.profiles)
    kept_vendors = list(dict.fromkeys(ALWAYS_KEPT + wanted)) if wanted else available
    if settings["vendor"] not in kept_vendors:
        fail(f'"{settings["vendor"]}" doit figurer dans "profile_vendors".')
    missing = [v for v in kept_vendors if v not in available]
    if missing:
        fail(f"Profils introuvables dans cette version d'OrcaSlicer : {', '.join(missing)}.")

    removed_vendors = [v for v in available if v not in kept_vendors]
    for vendor in removed_vendors:
        os.remove(os.path.join(args.profiles, vendor + ".json"))
        shutil.rmtree(os.path.join(args.profiles, vendor))

    profiles = Profiles(args.profiles, kept_vendors)
    library = profiles.library
    roots = [(library, DEFAULT_FILAMENT)]
    for vendor in profiles.vendors.values():
        if vendor is library:
            if not brands:
                roots += [(library, n) for n in library.entries]
            for name in library.instantiable("filament_list") if brands else []:
                brand = profiles.effective(library, name, "filament_vendor")
                brand = brand[0] if isinstance(brand, list) and brand else brand
                if brand in brands:
                    roots.append((library, name))
        elif printer_only and vendor.name == settings["vendor"]:
            roots += [(vendor, n) for n in printer_roots(profiles, vendor, settings["printer_model"])]
        else:
            roots += [(vendor, n) for n in vendor.entries]

    kept = profiles.closure(roots)
    selected = [f'{settings["printer_model"]} {n} nozzle' for n in settings["nozzles"]] + \
               [s["preset"] for s in settings["filament_slots"]] + \
               settings.get("extra_filaments", []) + [settings.get("print_profile", "")]
    for name in filter(None, selected):
        if not any(name in names for names in kept.values()):
            fail(f'Le profil "{name}" serait retiré : vérifiez les réglages d\'allègement.')

    print(f"{len(removed_vendors)} marques retirées, conservées : {', '.join(kept_vendors)}")
    for vendor in profiles.vendors.values():
        before = len(vendor.entries)
        removed = vendor.keep_only(kept[vendor.name])
        print(f"  {vendor.name} : {before - removed} profils sur {before}")


if __name__ == "__main__":
    main()
