"""Étape 2a — Enrichissement des SIREN demandeurs via l'API publique Recherche d'entreprises.

API : https://recherche-entreprises.api.gouv.fr (DINUM, données Sirène/INSEE + RNE + labels publics)
Limite publique : 7 req/s. On reste à ~4 req/s, avec cache local (reprise possible).

Données personnelles : la réponse contient des noms de dirigeants personnes physiques.
On ne conserve QUE des champs décrivant la personne morale (liste blanche KEEP ci-dessous) :
aucun nom de personne physique n'est écrit sur disque.

Usage : python src/step2a_enrich_siren.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "processed" / "pc_78_personnes_morales.csv"
CACHE = ROOT / "data" / "cache" / "recherche_entreprises.jsonl"
OUT = ROOT / "data" / "processed" / "siren_enrichi.csv"
API = "https://recherche-entreprises.api.gouv.fr/search"
UA = {"User-Agent": "sitadel-78-etude/0.1 (analyse open data)"}
DELAY = 0.25

KEEP = ["siren", "nom_complet", "nom_raison_sociale", "sigle", "activite_principale",
        "nature_juridique", "categorie_entreprise", "tranche_effectif_salarie", "date_creation",
        "etat_administratif", "nombre_etablissements_ouverts"]
KEEP_COMPL = ["collectivite_territoriale", "liste_idcc", "liste_finess_juridique", "est_association",
              "est_ess", "est_finess", "est_siae", "type_siae", "est_service_public",
              "est_administration", "est_entrepreneur_individuel", "est_societe_mission",
              "identifiant_association"]


def fetch(siren: str) -> dict:
    for attempt in range(4):
        r = requests.get(API, params={"q": siren, "page": 1, "per_page": 1}, headers=UA, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        res = [x for x in r.json().get("results", []) if x.get("siren") == siren]
        if not res:
            return {"siren": siren, "trouve": False}
        x = res[0]
        rec = {k: x.get(k) for k in KEEP}
        c = x.get("complements") or {}
        rec.update({k: c.get(k) for k in KEEP_COMPL})
        if isinstance(rec.get("collectivite_territoriale"), dict):  # garder code + niveau seulement
            ct = rec["collectivite_territoriale"]
            rec["collectivite_territoriale"] = {k: ct.get(k) for k in ("code", "niveau", "code_insee")}
        rec["trouve"] = True
        return rec
    raise RuntimeError(f"429 persistant pour {siren}")


def main() -> int:
    sirens = sorted(pd.read_csv(IN, dtype=str)["SIREN_DEM"].dropna().unique())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            done[rec["siren"]] = rec
    todo = [s for s in sirens if s not in done]
    print(f"{len(sirens)} SIREN, {len(done)} en cache, {len(todo)} à interroger", flush=True)
    with CACHE.open("a", encoding="utf-8") as f:
        for i, s in enumerate(todo, 1):
            try:
                rec = fetch(s)
            except Exception as e:  # on note l'échec, on continue
                rec = {"siren": s, "trouve": None, "erreur": str(e)[:200]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            done[s] = rec
            if i % 250 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
            time.sleep(DELAY)

    df = pd.DataFrame([done[s] for s in sirens])
    for col in ("liste_idcc", "liste_finess_juridique", "collectivite_territoriale"):
        if col in df:
            df[col] = df[col].apply(lambda v: json.dumps(v, ensure_ascii=False) if v not in (None, [], {}) and v == v else None)
    df["SOURCE_SIREN_URL"] = "https://annuaire-entreprises.data.gouv.fr/entreprise/" + df["siren"]
    df.to_csv(OUT, index=False, encoding="utf-8")
    print("trouvés:", df["trouve"].value_counts(dropna=False).to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
