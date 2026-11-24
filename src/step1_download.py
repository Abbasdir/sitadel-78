"""Étape 1 — Téléchargement de l'extraction Sitadel (Yvelines, 78) et filtrage personnes morales.

Source : SDES, « Liste des permis de construire et autres autorisations d'urbanisme »
  https://www.data.gouv.fr/datasets/liste-des-permis-de-construire-et-autres-autorisations-durbanisme
  Catalogue DiDo : https://www.statistiques.developpement-durable.gouv.fr/catalogue?page=dataset&datasetId=6513f0189d7d312c80ec5b5b

Le filtre départemental est appliqué côté serveur (API DiDo, DEP_CODE=eq:78) : on ne télécharge
que ~20k lignes au lieu de ~2M. Le filtre « personne morale » est fait localement pour pouvoir
compter et documenter ce qu'on écarte.

Usage : python src/step1_download.py [--millesime 2026-10] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
DOCS = ROOT / "docs" / "sources"

API = "https://data.statistiques.developpement-durable.gouv.fr/dido/api"
DEP = "78"
UA = {"User-Agent": "sitadel-78-etude/0.1 (analyse open data, usage non commercial)"}
PAUSE_S = 2  # cadence raisonnable entre requêtes

DATAFILES = {
    "logements": "8b35affb-55fc-4c1f-915b-7750f974446a",
    "locaux": "f8f0700f-806c-40a7-83b1-f21cf507e7c4",
}
# Documentation officielle (note de présentation + dictionnaires des variables)
DOC_FILES = {
    "note_presentation_sitadel.pdf": "52ce326b-45b2-42ce-a2e7-4a60554ef559",
    "dictionnaire_logements.xls": "ab799b04-0b03-4f96-949c-eb23c478a8e8",
    "dictionnaire_locaux.xls": "38ca96c1-c8af-42db-bba1-13cd4bc713f3",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=300, **kw)
    r.raise_for_status()
    time.sleep(PAUSE_S)
    return r


def latest_millesime(rid: str) -> str:
    return get(f"{API}/v1/datafiles/{rid}").json()["millesime"]


def download_csv(name: str, rid: str, millesime: str, force: bool) -> dict:
    out = RAW / f"sitadel_{name}_{DEP}_{millesime}.csv"
    url = (f"{API}/v1/datafiles/{rid}/csv?millesime={millesime}"
           f"&withColumnName=true&withColumnDescription=false&DEP_CODE=eq:{DEP}")
    if force or not out.exists():
        print(f"  téléchargement {name} …", flush=True)
        with requests.get(url, headers=UA, timeout=600, stream=True) as r:
            r.raise_for_status()
            with out.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        time.sleep(PAUSE_S)
    else:
        print(f"  {out.name} déjà présent (--force pour retélécharger)")
    return {
        "fichier": out.relative_to(ROOT).as_posix(),
        "url_api": url,
        "page_catalogue": ("https://www.statistiques.developpement-durable.gouv.fr/catalogue?"
                           f"page=datafile&datafileRid={rid}&datafileMillesime={millesime}"),
        "millesime": millesime,
        "sha256": sha256(out),
    }


def load(path: Path, kind: str) -> pd.DataFrame:
    # Le CSV DiDo est séparé par « ; ». Tout en texte pour ne pas abîmer SIREN/SIRET/codes commune.
    df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, na_values=[""])
    df.insert(0, "SOURCE_FICHIER", kind)
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--millesime", help="ex. 2026-10 (défaut : le plus récent)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for d in (RAW, PROC, DOCS):
        d.mkdir(parents=True, exist_ok=True)

    manifest = {"telecharge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "departement": DEP, "fichiers": {}, "documentation": {}}

    for name, rid in DATAFILES.items():
        mil = args.millesime or latest_millesime(rid)
        manifest["fichiers"][name] = download_csv(name, rid, mil, args.force)

    for fname, fid in DOC_FILES.items():
        out = DOCS / fname
        if args.force or not out.exists():
            out.write_bytes(get(f"{API}/files/{fid}").content)
        manifest["documentation"][fname] = f"{API}/files/{fid}"

    # --- Chargement + filtrage ------------------------------------------------
    frames = [load(ROOT / m["fichier"], k) for k, m in manifest["fichiers"].items()]
    df = pd.concat(frames, ignore_index=True, sort=False)
    stats = {"lignes_78_total": len(df),
             "par_fichier": df["SOURCE_FICHIER"].value_counts().to_dict(),
             "par_type_dau": df["TYPE_DAU"].value_counts(dropna=False).to_dict()}

    # Personne morale = demandeur « avéré » en tant que personne morale : SIREN ou catégorie
    # juridique renseignés. (Pour une personne physique ces champs sont vides.)
    is_pm = df["SIREN_DEM"].notna() | df["CJ_DEM"].notna()
    is_pc = df["TYPE_DAU"].eq("PC")
    stats["personnes_morales_toutes_dau"] = int(is_pm.sum())
    stats["pc_personnes_morales"] = int((is_pm & is_pc).sum())
    stats["pm_sans_denomination"] = int((is_pm & df["DENOM_DEM"].isna()).sum())
    stats["pm_sans_siren"] = int((is_pm & df["SIREN_DEM"].isna()).sum())

    pm = df[is_pm & is_pc].copy()
    # Un même permis peut figurer dans les deux fichiers (mixte logements + locaux).
    dup = pm.duplicated("NUM_DAU", keep=False)
    stats["pc_presents_dans_les_deux_fichiers"] = int(pm.loc[dup, "NUM_DAU"].nunique())
    pm["DANS_LOGEMENTS"] = pm["NUM_DAU"].isin(pm.loc[pm.SOURCE_FICHIER == "logements", "NUM_DAU"])
    pm["DANS_LOCAUX"] = pm["NUM_DAU"].isin(pm.loc[pm.SOURCE_FICHIER == "locaux", "NUM_DAU"])

    # Lien source par ligne : page catalogue du fichier + identifiant du permis
    pm["SOURCE_URL"] = pm["SOURCE_FICHIER"].map(
        {k: m["page_catalogue"] for k, m in manifest["fichiers"].items()})
    pm["SIREN_URL"] = "https://annuaire-entreprises.data.gouv.fr/entreprise/" + pm["SIREN_DEM"].fillna("")
    pm.loc[pm["SIREN_DEM"].isna(), "SIREN_URL"] = pd.NA

    out = PROC / "pc_78_personnes_morales.csv"
    pm.to_csv(out, index=False, encoding="utf-8")
    stats["sortie"] = {"fichier": out.relative_to(ROOT).as_posix(), "lignes": len(pm),
                       "permis_distincts": int(pm["NUM_DAU"].nunique()),
                       "siren_distincts": int(pm["SIREN_DEM"].nunique())}
    manifest["stats"] = stats

    (ROOT / "data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
