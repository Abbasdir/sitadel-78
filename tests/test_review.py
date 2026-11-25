"""Régressions : preuves inventées, activités génériques et validation humaine périmée."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401  (chemin src)
from sitadel.agent import cache_matches
from sitadel.evidence import check_proposal as parse, public_url
from sitadel.prompt import PROMPT_SHA256, VERSION_PROMPT
from sitadel.review import decision_id, review_decision, write_reviews
from sitadel.storage import load_history


class LLMReviewTests(unittest.TestCase):
    def setUp(self):
        self.entree = {"denomination": "SOCIETE TEST", "categorie_juridique": "5710 SAS",
                       "code_ape_au_permis": "41.10A Promotion immobilière de logements",
                       "activite_principale_siege": "41.10A Promotion immobilière de logements"}
        self.output = {"famille": "promoteur_prive", "justification": "L'activité fournie est la promotion de logements.",
                       "confiance": "moyenne", "preuves": [
                           {"champ": "code_ape_au_permis", "valeur": self.entree["code_ape_au_permis"]}]}

    def record(self, output=None, entree=None):
        return {"siren": "123456789", "modele": "modele-test:3b", "entree": entree or self.entree,
                "sortie_brute": json.dumps(self.output if output is None else output),
                "version_prompt": VERSION_PROMPT, "prompt_sha256": PROMPT_SHA256,
                "horodatage": "2026-11-24T12:00:00+00:00"}

    def test_valid_citation_is_only_a_proposal(self):
        result = review_decision(self.record())
        self.assertEqual(result["statut_controle"], "a_verifier")
        self.assertNotEqual(result["statut_controle"], "validee")

    def test_missing_or_fabricated_proof_is_rejected(self):
        for preuves in (None, [], [{"champ": "code_ape_au_permis", "valeur": "41.10B"}],
                        [{"champ": "site_web_invente", "valeur": "promotion"}]):
            with self.subTest(preuves=preuves):
                output = {**self.output, "preuves": preuves}
                self.assertEqual(review_decision(self.record(output))["statut_controle"], "rejetee")

    def test_holding_or_headquarters_does_not_prove_promotion(self):
        for code in ("70.10Z Activités des sièges sociaux", "64.20Z Activités des sociétés holding"):
            with self.subTest(code=code):
                entree = {**self.entree, "code_ape_au_permis": code, "activite_principale_siege": code}
                output = {**self.output, "preuves": [
                    {"champ": "denomination", "valeur": entree["denomination"]},
                    {"champ": "categorie_juridique", "valeur": entree["categorie_juridique"]},
                    {"champ": "code_ape_au_permis", "valeur": code}]}
                self.assertEqual(review_decision(self.record(output, entree))["statut_controle"], "rejetee")

    def test_abstention_is_a_valid_result(self):
        output = {**self.output, "famille": "non_determine", "preuves": []}
        self.assertEqual(review_decision(self.record(output))["statut_controle"], "abstention")

    def test_malformed_output_never_crashes_or_passes(self):
        for raw in ("pas du json", "[]", "null", "42", '{"famille": "inventee"}',
                    json.dumps({**self.output, "confiance": []})):
            with self.subTest(raw=raw):
                self.assertEqual(parse(raw, self.entree)["statut_controle"], "rejetee")

    def test_approval_requires_source_and_exact_decision(self):
        record = self.record()
        manuel = {"decision_id": decision_id(record), "verdict_manuel": "valide"}
        self.assertEqual(review_decision(record, manuel)["statut_controle"], "validation_incomplete")
        manuel["source_validation"] = "https://annuaire-entreprises.data.gouv.fr/entreprise/123456789"
        self.assertEqual(review_decision(record, manuel)["statut_controle"], "validee")
        manuel["decision_id"] = "une-autre-reponse"
        self.assertEqual(review_decision(record, manuel)["statut_controle"], "validation_incomplete")

    def test_rejected_evidence_cannot_be_approved(self):
        record = self.record({**self.output, "preuves": []})
        manuel = {"decision_id": decision_id(record), "verdict_manuel": "valide",
                  "source_validation": "https://example.org/source"}
        self.assertEqual(review_decision(record, manuel)["statut_controle"], "validation_incomplete")

    def test_local_or_non_http_address_is_not_a_public_source(self):
        for source in ("", None, "file:///tmp/source", "javascript:alert(1)", "http://localhost:8501",
                       "http://127.0.0.1/source", "http://192.168.1.1/source", "https://intranet.local/source"):
            with self.subTest(source=source):
                self.assertFalse(public_url(source))

    def test_approval_cannot_contradict_the_expected_family(self):
        record = self.record()
        manuel = {"decision_id": decision_id(record), "verdict_manuel": "valide",
                  "source_validation": "https://example.org/source", "famille_attendue": "association_ess"}
        self.assertEqual(review_decision(record, manuel)["statut_controle"], "validation_incomplete")

    def test_changed_input_invalidates_approval(self):
        record = self.record()
        manuel = {"decision_id": decision_id(record), "verdict_manuel": "valide",
                  "source_validation": "https://example.org/source"}
        changed = {**self.entree, "code_ape_au_permis": "64.20Z Activités des sociétés holding"}
        self.assertNotEqual(review_decision(record, manuel, changed)["statut_controle"], "validee")

    def test_legacy_cache_cannot_modify_the_classification(self):
        record = self.record()
        del record["prompt_sha256"]
        self.assertEqual(review_decision(record)["statut_controle"], "ancienne_version")
        self.assertFalse(cache_matches(record, self.entree, "modele-test:3b"))

    def test_cache_accounts_for_input_prompt_and_model(self):
        record = self.record()
        self.assertTrue(cache_matches(record, self.entree, "modele-test:3b"))
        self.assertFalse(cache_matches(record, self.entree, "modele-test:7b"))
        self.assertFalse(cache_matches(record, {**self.entree, "denomination": "AUTRE"}, "modele-test:3b"))

    def test_manual_verdicts_survive_a_new_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "revue.csv"
            records = [self.record()]
            rows = write_reviews(records, path)
            rows[0].update(verdict_manuel="valide", source_validation="https://example.org/source",
                           commentaire_manuel="Activité vérifiée.")
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            refreshed = write_reviews(records, path)
            self.assertEqual(refreshed[0]["verdict_manuel"], "valide")
            self.assertEqual(refreshed[0]["commentaire_manuel"], "Activité vérifiée.")
            self.assertEqual(refreshed[0]["statut_controle"], "validee")

    def test_history_keeps_old_trials_and_skips_broken_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.jsonl"
            path.write_text(json.dumps(self.record()) + "\ninvalid\n" + json.dumps(self.record()) + "\n",
                            encoding="utf-8")
            with self.assertWarns(UserWarning):
                self.assertEqual(len(load_history(path)), 2)

    def test_review_export_reports_changed_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "revue.csv"
            current = {**self.entree, "denomination": "AUTRE SOCIETE"}
            rows = write_reviews([self.record()], path, {"123456789": current})
            self.assertEqual(rows[0]["statut_controle"], "donnees_modifiees")


if __name__ == "__main__":
    unittest.main()
