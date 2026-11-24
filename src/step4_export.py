"""Étape 4a — CSV final : 1 ligne par permis, famille du demandeur, indicateurs, liens vers les sources.

Sortie : data/final/sitadel_78_pc_personnes_morales.csv (+ dictionnaire des colonnes en .md)

Liens par ligne :
  SOURCE_PERMIS_URL       l'enregistrement Sitadel exact (API DiDo filtrée sur NUM_DAU, CSV public)
  SOURCE_PERMIS_URL_2     idem dans le 2e fichier pour les permis mixtes logements + locaux
  SOURCE_JEU_DE_DONNEES   page du jeu de données SDES (millésime)
  SIREN_URL               fiche publique du demandeur (annuaire-entreprises.data.gouv.fr)

Usage : python src/step4_export.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from step3_patterns import CIBLES, load, medsoc_signaux  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data" / "final"
API = "https://data.statistiques.developpement-durable.gouv.fr/dido/api/v1/datafiles"

COLONNES = {
    "NUM_DAU": "numéro du permis de construire",
    "COMM": "code INSEE de la commune", "COMMUNE": "nom de la commune (geo.api.gouv.fr)",
    "ADRESSE_TERRAIN": "adresse du terrain (Sitadel)",
    "FICHIER": "fichier(s) Sitadel où figure le permis : logements, locaux, logements+locaux",
    "ETAT": "autorisé / commencé / terminé / annulé (ETAT_DAU)",
    "DATE_AUTORISATION": "date réelle d'autorisation", "DATE_OUVERTURE_CHANTIER": "date réelle de DOC (si déclarée)",
    "DATE_ACHEVEMENT": "date réelle de DAACT (si déclarée)",
    "DELAI_AUT_DOC_JOURS": "jours entre autorisation et ouverture de chantier",
    "SIREN_DEM": "SIREN du demandeur", "DENOMINATION": "dénomination (masquée si risque de nom de personne)",
    "CJ": "catégorie juridique au permis", "APE": "code APE au permis",
    "FAMILLE": "famille du demandeur", "SOUS_FAMILLE": "précision", "CONFIANCE": "haute / moyenne / basse",
    "REGLE_APPLIQUEE": "règle de classement déclenchée (ou « llm »)", "SIGNAL": "signal public qui fonde la décision",
    "FAMILLE_CIBLE": "bailleur social, association/ESS ou médico-social",
    "NATURE_PROJET": "nouvelle construction / travaux sur existant", "EXTENSION": "indicateur d'extension",
    "NB_LOGEMENTS_CREES": "logements créés", "DONT_LOCATIFS_SOCIAUX": "dont financés par prêt locatif social",
    "SURF_HAB_CREEE_M2": "surface d'habitation créée", "SURF_LOCAUX_CREEE_M2": "surface de locaux créée",
    "NB_CHAMBRES": "chambres (hébergement)", "SERVICE_PUBLIC": "type de service public ou d'intérêt collectif",
    "RESIDENCE": "type de résidence déclaré", "SIGNAUX_MEDICO_SOCIAUX": "signaux projet médico-social (étape 3)",
    "SOURCE_PERMIS_URL": "enregistrement Sitadel du permis (CSV public, API DiDo)",
    "SOURCE_PERMIS_URL_2": "idem dans le 2e fichier (permis mixtes)",
    "SOURCE_JEU_DE_DONNEES": "page catalogue SDES du fichier", "SIREN_URL": "fiche publique du demandeur",
}


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    man = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    pc = load()
    sig = medsoc_signaux(pc)
    pc["SIGNAUX_MEDICO_SOCIAUX"] = sig.apply(lambda r: " ; ".join(r.index[r]), axis=1)

    def rec_url(kind: str, num: str) -> str:
        url = man["fichiers"][kind]["url_api"].split("&DEP_CODE")[0]
        return f"{url}&NUM_DAU=eq:{num}"

    first = pc["SOURCE_FICHIER"].str.split("+").str[0]
    pc["SOURCE_PERMIS_URL"] = [rec_url(k, n) for k, n in zip(first, pc["NUM_DAU"])]
    pc["SOURCE_PERMIS_URL_2"] = [rec_url("locaux", n) if f == "logements+locaux" else None
                                 for f, n in zip(pc["SOURCE_FICHIER"], pc["NUM_DAU"])]
    adr = pc[["ADR_NUM_TER", "ADR_LIBVOIE_TER", "ADR_LIEUDIT_TER"]].fillna("").agg(" ".join, axis=1)
    pc["ADRESSE_TERRAIN"] = adr.str.split().str.join(" ").replace("", None)

    out = pc.rename(columns={
        "SOURCE_FICHIER": "FICHIER", "DATE_REELLE_AUTORISATION": "DATE_AUTORISATION",
        "DATE_REELLE_DOC": "DATE_OUVERTURE_CHANTIER", "DATE_REELLE_DAACT": "DATE_ACHEVEMENT",
        "DELAI_DOC_J": "DELAI_AUT_DOC_JOURS", "DENOM_DEM": "DENOMINATION", "CJ_DEM": "CJ", "APE_DEM": "APE",
        "famille": "FAMILLE", "sous_famille": "SOUS_FAMILLE", "confiance": "CONFIANCE",
        "regle_appliquee": "REGLE_APPLIQUEE", "signal": "SIGNAL", "NB_LGT_TOT_CREES": "NB_LOGEMENTS_CREES",
        "NB_LGT_PRET_LOC_SOCIAL": "DONT_LOCATIFS_SOCIAUX", "SURF_HAB_CREEE": "SURF_HAB_CREEE_M2",
        "SURF_LOC_CREEE": "SURF_LOCAUX_CREEE_M2", "RESIDENCE": "RESIDENCE_CODE", "RESIDENCE_LIB": "RESIDENCE",
        "SOURCE_URL": "SOURCE_JEU_DE_DONNEES"})
    out["FAMILLE_CIBLE"] = out["FAMILLE"].isin(CIBLES)
    out["NATURE_PROJET"] = out["NATURE_PROJET_DECLAREE"].map({"1": "nouvelle construction",
                                                              "2": "travaux sur existant"})
    for c in ("DATE_AUTORISATION", "DATE_OUVERTURE_CHANTIER", "DATE_ACHEVEMENT"):
        out[c] = out[c].dt.date
    for c in ("NB_LOGEMENTS_CREES", "DONT_LOCATIFS_SOCIAUX", "SURF_HAB_CREEE_M2", "SURF_LOCAUX_CREEE_M2", "NB_CHAMBRES"):
        out[c] = out[c].astype(int)
    out["DELAI_AUT_DOC_JOURS"] = out["DELAI_AUT_DOC_JOURS"].astype("Int64")
    out = out[list(COLONNES)].sort_values(["DATE_AUTORISATION", "NUM_DAU"], ascending=[False, True])
    path = FINAL / "sitadel_78_pc_personnes_morales.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")  # BOM : ouverture correcte dans Excel

    doc = ["# Dictionnaire — sitadel_78_pc_personnes_morales.csv\n",
           f"Source : SDES Sitadel, millésime {man['fichiers']['logements']['millesime']}, Yvelines, "
           "permis de construire déposés par des personnes morales. 1 ligne par permis.\n",
           "| colonne | description |", "|---|---|"] + [f"| `{k}` | {v} |" for k, v in COLONNES.items()]
    (FINAL / "dictionnaire_colonnes.md").write_text("\n".join(doc) + "\n", encoding="utf-8")
    print(f"{len(out)} permis -> {path.relative_to(ROOT).as_posix()}")
    print("liens permis manquants :", int(out["SOURCE_PERMIS_URL"].isna().sum()),
          "| SIREN_URL manquants :", int(out["SIREN_URL"].isna().sum()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
