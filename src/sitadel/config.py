"""Chemins, constantes partagées et lecture locale de la configuration.

Aucune valeur secrète n'est affichée ni écrite : `read_setting` lit l'environnement puis `.env`.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- Arborescence des données (chemins historiques conservés) -------------------------------------
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
PATTERNS = PROCESSED / "patterns"
FINAL = DATA / "final"
REF = DATA / "ref"
CACHE = DATA / "cache"
DOCS = ROOT / "docs"
DOCS_SOURCES = DOCS / "sources"
MANIFEST = DATA / "manifest.json"

PERMIS_PM = PROCESSED / "pc_78_personnes_morales.csv"      # ingest
SIREN_ENRICHI = PROCESSED / "siren_enrichi.csv"           # enrich
DEMANDEURS = PROCESSED / "demandeurs_classes.csv"         # classify
PERMIS_CLASSES = PROCESSED / "pc_78_classes.csv"          # classify
REVUE_LLM = PROCESSED / "revue_llm.csv"                   # review
REVUE_WEB = PROCESSED / "revue_web.csv"                   # review
ECHANTILLON = PROCESSED / "echantillon_controle.csv"      # review (contrôle qualité)
CJ_INSEE = REF / "cj_insee.csv"
NAF_INSEE = REF / "naf_insee.csv"
COMMUNES = REF / "communes_78.csv"
SOURCES_WEB_CONNUES = REF / "sources_web.csv"

CACHE_SIRENE = CACHE / "recherche_entreprises.jsonl"
CACHE_GEMINI = CACHE / "gemini_decisions.jsonl"
CACHE_OLLAMA = CACHE / "ollama_decisions.jsonl"           # historique en lecture seule
CACHE_WEB = CACHE / "web_research.jsonl"

# --- Constantes métier partagées -------------------------------------------------------------------
FAMILLES = ["bailleur_social", "medico_social_sante", "collectivite_public", "association_ess",
            "promoteur_prive", "sci_fonciere", "entreprise_autre", "non_determine"]
CIBLES = ["bailleur_social", "association_ess", "medico_social_sante"]
# Sièges sociaux, holdings, conseil de gestion, soutien aux entreprises : jamais une preuve de secteur.
APE_GENERIQUES = {"70.10Z", "64.20Z", "70.22Z", "82.99Z"}
SIREN_URL = "https://annuaire-entreprises.data.gouv.fr/entreprise/"


def read_setting(name: str, root: Path = ROOT) -> str:
    """Variable d'environnement, sinon ligne `NOM=valeur` du fichier `.env` local ; "" si absente."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = root / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("\"'")
    return ""
