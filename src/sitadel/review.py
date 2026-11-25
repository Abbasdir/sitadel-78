"""Revue humaine : statut de chaque proposition, verdicts manuels et application des seules validations.

Une proposition du modèle reste séparée du classement des règles. Elle ne s'applique qu'à un demandeur
encore « non déterminé », après validation manuelle attachée à la réponse exacte (decision_id) et
appuyée par une source publique.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from .config import ECHANTILLON, REVUE_LLM, REVUE_WEB, SIREN_URL
from .evidence import check_proposal, public_url, verified_sources
from .prompt import PROMPT_SHA256, build_input
from .storage import load_all_history, load_web_latest, read_csv_rows, write_csv_atomic

MANUEL = ["verdict_manuel", "famille_attendue", "source_validation", "commentaire_manuel"]
COLONNES_REVUE = ["decision_id", "SIREN_DEM", "DENOM", "famille_proposee", "statut_controle",
                  "justification", "preuves", "sources_web", "motif_controle", "modele", "version_prompt",
                  "horodatage", "duree_s", "SIREN_URL"] + MANUEL
COLONNES_LLM = ["famille_proposee_llm", "statut_llm", "justification_llm", "controle_llm",
                "preuves_llm", "modele_llm", "decision_llm_id", "source_validation_llm",
                "sources_web_llm", "source_activite_llm"]
COLONNES_REVUE_WEB = ["SIREN_DEM", "statut_recherche", "provider", "sources", "pages_consultees",
                      "observations", "horodatage", "duree_s"]


def decision_id(record: dict) -> str:
    """Empreinte du contenu exact d'une réponse : un verdict manuel ne vaut que pour elle."""
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def review_decision(record: dict, manuel: dict | None = None, entree_actuelle: dict | None = None) -> dict:
    """Statut d'une réponse : contrôle des citations, version du prompt, données, puis verdict manuel."""
    manuel = manuel or {}
    entree = record.get("entree") or {}
    controle = check_proposal(record.get("sortie_brute", ""), entree)
    if record.get("prompt_sha256") != PROMPT_SHA256:
        controle.update(statut_controle="ancienne_version", motif_controle="Ancien prompt : réponse à réévaluer.")
    elif entree_actuelle is not None and entree != entree_actuelle:
        controle.update(statut_controle="donnees_modifiees", motif_controle="Les données du demandeur ont changé.")
    verdict = manuel.get("verdict_manuel", "").strip().lower()
    if verdict == "rejete":
        controle.update(statut_controle="refusee", motif_controle="Proposition rejetée lors du contrôle manuel.")
    elif verdict == "valide":
        if _validation_applicable(record, manuel, controle):
            controle.update(statut_controle="validee", motif_controle="Validation manuelle avec source publique.")
        else:
            controle.update(statut_controle="validation_incomplete",
                            motif_controle="Validation inapplicable : vérifier la version, les preuves et le lien source.")
    elif verdict:
        controle.update(statut_controle="validation_incomplete", motif_controle="Verdict attendu : valide ou rejete.")
    return controle


def _validation_applicable(record: dict, manuel: dict, controle: dict) -> bool:
    return (manuel.get("decision_id") == decision_id(record)
            and controle["statut_controle"] in {"a_verifier", "abstention"}
            and manuel.get("famille_attendue", "") in {"", controle["famille"]}
            and public_url(manuel.get("source_validation", "")))


def write_reviews(records: list[dict], path=REVUE_LLM, entrees_actuelles: dict | None = None) -> list[dict]:
    """Exporte tout l'historique et conserve les verdicts manuels attachés à la même réponse."""
    previous = {row["decision_id"]: row for row in read_csv_rows(path)}
    rows = []
    for record in records:
        ident = decision_id(record)
        manuel = previous.get(ident, {})
        entree = record.get("entree") or {}
        entree_actuelle = entrees_actuelles.get(record["siren"]) if entrees_actuelles is not None else None
        controle = review_decision(record, manuel, entree_actuelle)
        row = {"decision_id": ident, "SIREN_DEM": record["siren"],
               "DENOM": entree.get("denomination"),
               "famille_proposee": controle["famille"], "statut_controle": controle["statut_controle"],
               "justification": controle["justification"],
               "preuves": json.dumps(controle["preuves"], ensure_ascii=False),
               "sources_web": json.dumps(publishable_sources(record["siren"], entree.get("sources_web", []),
                                                             entree.get("denomination")), ensure_ascii=False),
               "motif_controle": controle["motif_controle"], "modele": record.get("modele"),
               "version_prompt": record.get("version_prompt", "v1"),
               "horodatage": record.get("horodatage"), "duree_s": record.get("duree_s"),
               "SIREN_URL": SIREN_URL + record["siren"]}
        row.update({key: manuel.get(key, "") for key in MANUEL})
        rows.append(row)
    write_csv_atomic(path, COLONNES_REVUE, rows)
    return rows


def publishable_sources(siren: str, sources: list, denomination: str | None) -> list[dict]:
    """Seuls les extraits encore recevables (identité, activité, aucun nom de personne) sont publiés.
    Les caches bruts, eux, restent locaux et ne sont jamais réécrits."""
    return verified_sources(siren, {siren: {"sources": sources}}, denomination)


def write_web_review(records: dict[str, dict], path=REVUE_WEB, denominations: dict | None = None) -> None:
    rows = [{"SIREN_DEM": siren, "statut_recherche": record.get("statut"),
             "provider": record.get("provider"), "horodatage": record.get("horodatage"),
             "duree_s": record.get("duree_s", ""),
             "sources": json.dumps(publishable_sources(siren, record.get("sources", []),
                                                       (denominations or {}).get(siren)), ensure_ascii=False),
             **{key: json.dumps(record.get(key, []), ensure_ascii=False)
                for key in ("pages_consultees", "observations")}}
            for siren, record in records.items()]
    write_csv_atomic(path, COLONNES_REVUE_WEB, rows)


def apply_reviews(d: pd.DataFrame, naf: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes LLM aux demandeurs et n'applique que les validations manuelles recevables.

    Écrit aussi revue_web.csv et revue_llm.csv (verdicts existants conservés).
    """
    history = load_all_history()
    latest = {record["siren"]: record for record in history}
    web_profiles = load_web_latest()
    write_web_review(web_profiles, REVUE_WEB, dict(zip(d["SIREN_DEM"], d["DENOM"])))
    naf_labels = dict(zip(naf["APE"], naf["APE_LIBELLE"]))
    entrees_actuelles = {row["SIREN_DEM"]: build_input(row, naf_labels, verified_sources(row["SIREN_DEM"], web_profiles, row["DENOM"]))
                        for _, row in d.iterrows() if row["SIREN_DEM"] in latest}
    reviews = write_reviews(history, REVUE_LLM, entrees_actuelles)
    by_id = {row["decision_id"]: row for row in reviews}
    for column in COLONNES_LLM:
        d[column] = "non_soumis" if column == "statut_llm" else ""
    for i, demandeur in d.iterrows():
        record = latest.get(demandeur["SIREN_DEM"])
        if record is None:
            continue
        ident = decision_id(record)
        manuel = by_id[ident]
        controle = review_decision(record, manuel, entrees_actuelles[demandeur["SIREN_DEM"]])
        sources = (record.get("entree") or {}).get("sources_web", [])
        cited = {preuve.get("source_id") for preuve in controle["preuves"] if preuve.get("champ") == "sources_web"}
        source_url = next((source["url"] for source in sources if source.get("id") in cited), "")
        d.loc[i, COLONNES_LLM] = [
            controle["famille"], controle["statut_controle"], controle["justification"],
            controle["motif_controle"], json.dumps(controle["preuves"], ensure_ascii=False),
            record.get("modele", ""), ident, manuel.get("source_validation", ""),
            json.dumps(publishable_sources(record["siren"], sources, demandeur["DENOM"]), ensure_ascii=False),
            source_url]
        if (demandeur["famille"] == "non_determine" and controle["statut_controle"] == "validee"
                and controle["famille"] != "non_determine"):
            d.loc[i, ["famille", "sous_famille", "confiance", "regle_appliquee", "signal"]] = [
                controle["famille"], f"LLM validé manuellement ({record['modele']})", "basse", "llm_valide",
                f"{controle['justification']} [validation : {manuel['source_validation']}]"]
    return d


def write_control_sample(demandeurs: pd.DataFrame, n: int = 15, seed: int = 42, path=ECHANTILLON) -> pd.DataFrame:
    """Contrôle qualité des règles : n demandeurs tirés au hasard par famille, colonne verdict à remplir."""
    ech = pd.concat(g.sample(n=min(n, len(g)), random_state=seed)
                    for _, g in demandeurs.groupby("famille"))
    ech = ech.rename(columns={"SOURCE_SIREN_URL": "SIREN_URL"})
    ech["verdict_manuel"] = ""
    cols = ["famille", "sous_famille", "confiance", "regle_appliquee", "signal", "SIREN_DEM", "DENOM",
            "CJ", "CJ_LIBELLE", "APE", "APE_LIBELLE", "activite_principale", "n_pc", "SIREN_URL",
            "verdict_manuel"]
    ech[cols].to_csv(path, index=False, encoding="utf-8")
    return ech
