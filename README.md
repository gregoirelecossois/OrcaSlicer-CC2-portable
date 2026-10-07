# OrcaSlicer portable pour l'Elegoo Centauri Carbon 2 Combo

Ce dépôt fabrique une version **portable** d'[OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) pour Windows, déjà réglée pour l'**Elegoo Centauri Carbon 2 Combo**. Au premier lancement, l'assistant de configuration ne s'affiche pas : l'imprimante, le réglage d'impression et les 4 bobines du CANVAS sont déjà sélectionnés.

Le programme n'est ni recompilé ni modifié. Le workflow télécharge le zip portable officiel, y ajoute un dossier `data_dir` pré-configuré et retire les profils des autres marques d'imprimantes.

## Récupérer la version portable

Dans l'onglet **Releases** du dépôt, téléchargez `OrcaSlicer_<version>_Elegoo_CC2_portable.zip`, décompressez-le et lancez `orca-slicer.exe`.

## Lancer une construction

Une construction démarre :

- **à la demande**, depuis l'onglet **Actions**, workflow « OrcaSlicer portable CC2 », bouton **Run workflow**. On peut y choisir une version précise d'OrcaSlicer (par exemple `v2.4.2`) ; sinon c'est la dernière version stable ;
- **chaque lundi** : si OrcaSlicer a publié une nouvelle version, une nouvelle release `cc2-<version>` est créée ;
- **à chaque modification** de `portable/`, `scripts/` ou du workflow : le zip est construit pour vérification et reste disponible comme artefact pendant 14 jours, mais aucune release n'est publiée.

## Modifier les pré-réglages

Tout se règle dans [`portable/cc2-settings.json`](portable/cc2-settings.json) :

| Clé | Rôle |
| --- | --- |
| `nozzles` | Buses proposées (`0.2`, `0.4`, `0.6`, `0.8`). La première est sélectionnée au démarrage. |
| `print_profile` | Réglage d'impression sélectionné. Vide = celui recommandé par Elegoo pour la buse. |
| `filament_slots` | Un filament et une couleur par emplacement du CANVAS. Un seul emplacement pour la version sans CANVAS. |
| `extra_filaments` | Filaments affichés en plus de ceux recommandés par Elegoo pour le CC2. |
| `profile_vendors` | Marques d'imprimantes gardées dans le zip, en plus de la bibliothèque de filaments et des profils génériques. Liste vide = toutes les marques. |
| `app` | Préférences OrcaSlicer supplémentaires (section `app` de `OrcaSlicer.conf`). |

Les noms doivent correspondre exactement aux profils d'OrcaSlicer (dossier [`resources/profiles/Elegoo`](https://github.com/OrcaSlicer/OrcaSlicer/tree/main/resources/profiles/Elegoo)). Le script vérifie chaque nom dans les profils de la version téléchargée. Un nom inconnu, ou un profil incompatible avec la buse choisie, fait échouer la construction avec un message explicite.

Pour tester en local, avec un dossier OrcaSlicer décompressé :

```sh
python3 scripts/make_portable_conf.py \
  --resources chemin/vers/OrcaSlicer/resources \
  --settings portable/cc2-settings.json \
  --version 2.4.2 \
  --out chemin/vers/OrcaSlicer/data_dir
```

## Fonctionnement

- Au démarrage, OrcaSlicer utilise le dossier `data_dir` s'il existe à côté de `orca-slicer.exe`, au lieu de `%APPDATA%\OrcaSlicer` (`GUI_App::init_app_config`).
- Le script `scripts/make_portable_conf.py` écrit dans ce dossier un `OrcaSlicer.conf` qui :
  - marque l'assistant de premier lancement comme terminé (`firstguide.finish`) ;
  - active le modèle Elegoo Centauri Carbon 2 (`models`). Au démarrage, OrcaSlicer installe alors les profils Elegoo depuis ses ressources ;
  - sélectionne l'imprimante, le réglage d'impression, les filaments et leurs couleurs (`presets` et `orca_presets`) ;
  - rend visibles les filaments recommandés par Elegoo pour le CC2 (`filaments`).

### Pourquoi retirer les autres marques ?

Dans OrcaSlicer 2.4.x, la fenêtre « Ajouter / supprimer des filaments » relit les profils de toutes les marques livrées (environ 8 000 fichiers) à chaque ouverture, ce qui peut prendre plusieurs minutes sous Windows. Le script `scripts/trim_profiles.py` ne garde que les marques de `profile_vendors`, plus `OrcaFilamentLibrary` et `Custom` qu'OrcaSlicer installe toujours. La fenêtre lit alors environ 830 fichiers et propose les mêmes filaments pour le CC2, puisque les filaments des autres marques ne visent que leurs propres imprimantes. En contrepartie, on ne peut plus ajouter d'imprimante d'une autre marque.

## Limites

- **Windows x64 uniquement.** Sous Linux, l'AppImage ne détecte pas de `data_dir` à côté d'elle ; il faudrait la lancer avec `--datadir`. Sous macOS, Gatekeeper complique la distribution.
- Si une future version d'OrcaSlicer ne fournit plus ses profils au format JSON, les noms ne peuvent plus être vérifiés. Le workflow affiche alors un avertissement.

## Licence

OrcaSlicer est distribué sous licence AGPL-3.0. Les zips publiés contiennent le programme officiel non modifié ; seuls des fichiers de profils sont ajoutés ou retirés. Chaque release renvoie vers la version et le code source d'origine.
