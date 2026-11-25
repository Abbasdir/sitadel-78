"""Mesure de la qualité à partir des verdicts humains, sans appel réseau.

Deux mesures indépendantes :
  - agent : réponses actuelles de `revue_llm.csv` (dernière réponse par SIREN, prompt en vigueur) ;
    une proposition revue est correcte ou erronée, une abstention revue est justifiée ou manquée ;
  - règles : `echantillon_controle.csv` (15 demandeurs tirés au hasard par famille).

Le nombre de cas classés ne mesure pas la précision : une abstention peut être la bonne réponse.
Avec quelques dizaines de verdicts, les taux restent indicatifs (intervalle de Wilson à 95 % affiché).

Conventions de saisie
  revue_llm.csv          verdict_manuel = valide | rejete ; famille_attendue si connue
                         (pour une abstention : valide = abstention justifiée,
                          rejete ou famille_attendue renseignée = une famille était déterminable)
  echantillon_controle   verdict_manuel = ok | faux:<famille attendue> | ?
"""
from __future__ import annotations

import math

import pandas as pd

from .config import DOCS, ECHANTILLON, FAMILLES, REVUE_LLM

RAPPORT = DOCS / "evaluation.md"
STATUTS_PERIMES = {"ancienne_version", "donnees_modifiees"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance d'une proportion, utilisable pour de petits effectifs."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - marge), min(1.0, centre + marge))


def rate(k: int, n: int) -> str:
    if n == 0:
        return "— (aucun verdict)"
    low, high = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} (IC95 {low:.0%}–{high:.0%})"


def agent_outcomes(revue: pd.DataFrame) -> pd.DataFrame:
    """Dernière réponse par SIREN, avec sa nature (proposition / abstention / rejet) et le verdict humain."""
    latest = revue.sort_values("horodatage").drop_duplicates("SIREN_DEM", keep="last").copy()
    verdict = latest["verdict_manuel"].astype(str).str.strip().str.lower()
    attendue = latest["famille_attendue"].astype(str).str.strip()
    latest["nature"] = "proposition"
    latest.loc[latest["famille_proposee"].eq("non_determine"), "nature"] = "abstention"
    latest.loc[latest["statut_controle"].eq("rejetee"), "nature"] = "rejet du contrôle"
    latest.loc[latest["statut_controle"].isin(STATUTS_PERIMES), "nature"] = "périmée (à relancer)"
    latest["resultat"] = "non revue"
    latest.loc[latest["nature"].eq("rejet du contrôle"), "resultat"] = "écartée par le contrôle"
    latest.loc[latest["nature"].eq("périmée (à relancer)"), "resultat"] = "à relancer"
    proposition, abstention = latest["nature"].eq("proposition"), latest["nature"].eq("abstention")
    latest.loc[proposition & verdict.eq("valide"), "resultat"] = "correcte"
    latest.loc[proposition & verdict.eq("rejete"), "resultat"] = "erronée"
    latest.loc[abstention & verdict.eq("valide") & attendue.isin(["", "non_determine"]), "resultat"] = "abstention justifiée"
    missed = verdict.eq("rejete") | (attendue.isin(FAMILLES) & ~attendue.eq("non_determine"))
    latest.loc[abstention & missed, "resultat"] = "abstention manquée"
    return latest


def rules_outcomes(sample: pd.DataFrame) -> pd.DataFrame:
    sample = sample.copy()
    verdict = sample["verdict_manuel"].str.strip().str.lower()
    sample["resultat"] = "non revu"
    sample.loc[verdict.eq("ok"), "resultat"] = "correct"
    sample.loc[verdict.str.startswith("faux"), "resultat"] = "erreur"
    sample.loc[verdict.eq("?"), "resultat"] = "indécidable"
    sample["famille_attendue"] = verdict.str.extract(r"faux\s*:\s*(\w+)", expand=False)
    return sample


def report(revue: pd.DataFrame, sample: pd.DataFrame) -> str:
    agent = agent_outcomes(revue)
    rules = rules_outcomes(sample)
    count = agent["resultat"].value_counts()
    props = int(count.get("correcte", 0) + count.get("erronée", 0))
    abst = int(count.get("abstention justifiée", 0) + count.get("abstention manquée", 0))
    lines = ["# Évaluation (verdicts humains)", "",
             "Généré par `sitadel evaluate` à partir des colonnes `verdict_manuel`. "
             "Les taux sur quelques dizaines de cas restent indicatifs.", "",
             "## Agent (dernière réponse par demandeur)", "",
             "| nature | réponses |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in agent["nature"].value_counts().items()]
    lines += ["", f"- Propositions correctes : {rate(int(count.get('correcte', 0)), props)}",
              f"- Abstentions justifiées : {rate(int(count.get('abstention justifiée', 0)), abst)}",
              f"- Réponses actuelles non encore revues : {int(count.get('non revue', 0))}",
              "", "## Règles (échantillon de contrôle)", "",
              "| famille | revus | corrects | précision |", "|---|---|---|---|"]
    for famille, g in rules.groupby("famille"):
        ok, err = int(g["resultat"].eq("correct").sum()), int(g["resultat"].eq("erreur").sum())
        lines.append(f"| {famille} | {ok + err} / {len(g)} | {ok} | {rate(ok, ok + err)} |")
    ok, err = int(rules["resultat"].eq("correct").sum()), int(rules["resultat"].eq("erreur").sum())
    lines += ["", f"- Ensemble : {rate(ok, ok + err)} ; indécidables : {int(rules['resultat'].eq('indécidable').sum())}"]
    errors = rules[rules["resultat"].eq("erreur")]
    if not errors.empty:
        lines += ["", "Erreurs relevées :", ""] + [
            f"- {r.SIREN_DEM} {r.DENOM} : {r.famille} → {r.famille_attendue} (règle {r.regle_appliquee})"
            for r in errors.itertuples()]
    return "\n".join(lines) + "\n"


def run() -> str:
    revue = pd.read_csv(REVUE_LLM, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    sample = pd.read_csv(ECHANTILLON, dtype=str, keep_default_na=False)
    text = report(revue, sample)
    RAPPORT.write_text(text, encoding="utf-8")
    return text
