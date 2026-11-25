"""Mesure à partir des verdicts humains : propositions, abstentions, réponses périmées, échantillon des règles."""
from __future__ import annotations

import unittest

import pandas as pd

import fixtures  # noqa: F401  (chemin src)
from sitadel.evaluate import agent_outcomes, report, rules_outcomes, wilson


def revue(rows):
    base = {"famille_attendue": "", "verdict_manuel": "", "horodatage": "2026-11-25T10:00:00+00:00"}
    return pd.DataFrame([{**base, **row} for row in rows])


class EvaluateTests(unittest.TestCase):
    def test_agent_outcomes_distinguish_errors_missed_and_stale_answers(self):
        data = revue([
            {"SIREN_DEM": "1", "famille_proposee": "entreprise_autre", "statut_controle": "a_verifier", "verdict_manuel": "valide"},
            {"SIREN_DEM": "2", "famille_proposee": "promoteur_prive", "statut_controle": "a_verifier", "verdict_manuel": "rejete"},
            {"SIREN_DEM": "3", "famille_proposee": "non_determine", "statut_controle": "abstention", "verdict_manuel": "valide"},
            {"SIREN_DEM": "4", "famille_proposee": "non_determine", "statut_controle": "abstention",
             "famille_attendue": "sci_fonciere"},
            {"SIREN_DEM": "5", "famille_proposee": "non_determine", "statut_controle": "donnees_modifiees", "verdict_manuel": "valide"},
            {"SIREN_DEM": "6", "famille_proposee": "non_determine", "statut_controle": "rejetee"},
            {"SIREN_DEM": "7", "famille_proposee": "entreprise_autre", "statut_controle": "a_verifier"},
        ])
        result = dict(zip(*agent_outcomes(data)[["SIREN_DEM", "resultat"]].T.values))
        self.assertEqual(result, {"1": "correcte", "2": "erronée", "3": "abstention justifiée",
                                  "4": "abstention manquée", "5": "à relancer",
                                  "6": "écartée par le contrôle", "7": "non revue"})

    def test_only_the_latest_answer_per_company_is_measured(self):
        data = revue([
            {"SIREN_DEM": "1", "famille_proposee": "promoteur_prive", "statut_controle": "a_verifier",
             "verdict_manuel": "rejete", "horodatage": "2026-11-24T10:00:00+00:00"},
            {"SIREN_DEM": "1", "famille_proposee": "entreprise_autre", "statut_controle": "a_verifier",
             "verdict_manuel": "valide", "horodatage": "2026-11-25T10:00:00+00:00"},
        ])
        self.assertEqual(agent_outcomes(data)["resultat"].tolist(), ["correcte"])

    def test_rules_sample_reads_ok_wrong_and_undecidable(self):
        sample = pd.DataFrame({"famille": ["sci_fonciere"] * 4, "verdict_manuel": ["ok", "faux:promoteur_prive", "?", ""],
                               "SIREN_DEM": list("abcd"), "DENOM": list("abcd"), "regle_appliquee": ["CJ_SCI"] * 4})
        result = rules_outcomes(sample)
        self.assertEqual(result["resultat"].tolist(), ["correct", "erreur", "indécidable", "non revu"])
        self.assertEqual(result["famille_attendue"].iloc[1], "promoteur_prive")
        text = report(revue([]).reindex(columns=["SIREN_DEM", "famille_proposee", "statut_controle",
                                                 "verdict_manuel", "famille_attendue", "horodatage"]), sample)
        self.assertIn("1/2 = 50%", text)
        self.assertIn("sci_fonciere → promoteur_prive", text.replace("a a : ", "").replace("b b : ", ""))

    def test_wilson_interval_is_wide_on_small_samples(self):
        low, high = wilson(3, 3)
        self.assertLess(low, 0.5)
        self.assertEqual(high, 1.0)
        self.assertEqual(wilson(0, 0), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
