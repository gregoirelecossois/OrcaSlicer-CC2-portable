#!/usr/bin/env python3
"""Generate a pre-configured OrcaSlicer data_dir for a portable build.

OrcaSlicer uses a folder named "data_dir" next to its executable when it
exists. This script writes the OrcaSlicer.conf it reads at startup so that:
  * the first-run setup wizard is skipped,
  * the vendor (e.g. Elegoo) profiles are installed from the bundled resources,
  * the chosen printer, print profile and filament slots are selected.

Preset names are checked against the profiles shipped in the downloaded
release (its "resources" folder), so a renamed profile fails the build instead
of producing a portable build that silently falls back to defaults.
"""

import argparse
import hashlib
import json
import os
import sys


def fail(message):
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def warn(message):
    print(f"::warning::{message}", file=sys.stderr)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class VendorProfiles:
    """Names and files of the presets declared in resources/profiles/<vendor>.json."""

    def __init__(self, profiles_dir, vendor):
        self.profiles_dir = profiles_dir
        self.vendor = vendor
        self.index = load_json(os.path.join(profiles_dir, vendor + ".json"))

    def _entries(self, key):
        return {e["name"]: e["sub_path"] for e in self.index.get(key, [])}

    def preset(self, list_key, name):
        sub_path = self._entries(list_key).get(name)
        if sub_path is None:
            return None
        return load_json(os.path.join(self.profiles_dir, self.vendor, sub_path))

    def require(self, list_key, name, what):
        preset = self.preset(list_key, name)
        if preset is None:
            fail(f'{what} "{name}" introuvable dans les profils {self.vendor} de cette version d\'OrcaSlicer.')
        return preset


def check_compatible(preset, machine, what):
    compatible = preset.get("compatible_printers") or []
    if compatible and machine not in compatible:
        fail(f'{what} "{preset.get("name")}" n\'est pas compatible avec "{machine}".')


def config_text(conf):
    # Same layout as AppConfig::save(): tab-indented JSON, then (read on
    # Windows) an MD5 line computed over the JSON text.
    body = json.dumps(conf, indent="\t", ensure_ascii=False)
    md5 = hashlib.md5(body.encode("utf-8")).hexdigest().upper()
    return f"{body}\n# MD5 checksum {md5}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resources", required=True, help="dossier resources de la version OrcaSlicer téléchargée")
    parser.add_argument("--settings", required=True, help="fichier de pré-réglages (portable/cc2-settings.json)")
    parser.add_argument("--version", required=True, help="version d'OrcaSlicer, ex. 2.4.2")
    parser.add_argument("--out", required=True, help="dossier data_dir à créer")
    args = parser.parse_args()

    settings = load_json(args.settings)
    vendor = settings["vendor"]
    model = settings["printer_model"]
    nozzles = settings["nozzles"]
    slots = settings["filament_slots"]
    if not nozzles:
        fail("Il faut au moins une buse dans \"nozzles\".")
    if not slots:
        fail("Il faut au moins un emplacement dans \"filament_slots\".")

    machine = f"{model} {nozzles[0]} nozzle"
    print_profile = settings.get("print_profile", "")
    visible_filaments = [s["preset"] for s in slots] + list(settings.get("extra_filaments", []))

    profiles_dir = os.path.join(args.resources, "profiles")
    if os.path.isfile(os.path.join(profiles_dir, vendor + ".json")):
        profiles = VendorProfiles(profiles_dir, vendor)
        model_preset = profiles.require("machine_model_list", model, "Modèle d'imprimante")
        for nozzle in nozzles:
            profiles.require("machine_list", f"{model} {nozzle} nozzle", "Imprimante")
        machine_preset = profiles.require("machine_list", machine, "Imprimante")

        if not print_profile:
            print_profile = machine_preset.get("default_print_profile", "")
        if print_profile:
            check_compatible(profiles.require("process_list", print_profile, "Réglage d'impression"),
                             machine, "Le réglage d'impression")

        for slot in slots:
            check_compatible(profiles.require("filament_list", slot["preset"], "Filament"),
                             machine, "Le filament")
        for name in settings.get("extra_filaments", []):
            profiles.require("filament_list", name, "Filament")

        # Show every filament Elegoo recommends for this printer, as the setup wizard does.
        defaults = [m for m in model_preset.get("default_materials", "").split(";") if m]
        visible_filaments = defaults + visible_filaments
    else:
        # Newer builds may ship vendor profiles as caches only; the names
        # cannot be checked then, OrcaSlicer falls back to defaults if wrong.
        warn(f"{vendor}.json absent de {profiles_dir} : noms de profils non vérifiés.")

    # De-duplicate while keeping order.
    visible_filaments = list(dict.fromkeys(visible_filaments))

    printer_settings = {
        "machine": machine,
        "process": print_profile,
        "filament": slots[0]["preset"],
        "filament_colors": ",".join(s["color"] for s in slots),
    }
    for i, slot in enumerate(slots[1:], start=1):
        printer_settings[f"filament_{i:02d}"] = slot["preset"]
    if not print_profile:
        del printer_settings["process"]

    app = {"version": args.version}
    for key, value in settings.get("app", {}).items():
        if not isinstance(value, (str, bool)):
            fail(f'La préférence "{key}" doit être un texte ou un booléen.')
        app[key] = value

    conf = {
        "header": f"OrcaSlicer {args.version}",
        "app": app,
        # Marks the setup wizard as done, see GuideFrame::SaveProfile().
        "firstguide": {"finish": True},
        "filaments": visible_filaments,
        "presets": {
            "machine": machine,
            "process": print_profile,
            "filaments": [s["preset"] for s in slots],
        },
        "orca_presets": [printer_settings],
        # Vendors listed here get their profiles installed from resources at startup.
        "models": [{"vendor": vendor, "model": model, "nozzle_diameter": ";".join(nozzles)}],
    }

    # Shipped empty so a server install can keep data_dir read-only and grant
    # write access to the log folder only: every launch writes its log there.
    os.makedirs(os.path.join(args.out, "log"), exist_ok=True)
    conf_path = os.path.join(args.out, "OrcaSlicer.conf")
    with open(conf_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(config_text(conf))

    print(f"{conf_path} écrit :")
    print(f"  imprimante : {machine}")
    print(f"  réglage    : {print_profile or '(défaut)'}")
    for i, slot in enumerate(slots, start=1):
        print(f"  bobine {i}   : {slot['preset']} {slot['color']}")
    print(f"  {len(visible_filaments)} filaments visibles")


if __name__ == "__main__":
    main()
