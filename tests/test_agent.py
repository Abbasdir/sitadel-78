"""Agent et CLI : budget de recherche, reprise du cache, aucune devinette, pas d'export après un échec."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from fixtures import EXCERPT, SIREN, answer, response, source
from sitadel import cli
from sitadel.agent import AgentOptions, AgentPaths, run_agent
from sitadel.clients.gemini import GeminiClient
from sitadel.errors import WebResearchError
from sitadel.prompt import PROMPT_SHA256, SCHEMA, SYSTEM, build_input

HOLDING = {"APE": "64.20Z", "APE_LIBELLE": "Activités des sociétés holding"}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.rows = [{"SIREN_DEM": siren, "DENOM": "ENTREPRISE TEST", "famille": "non_determine",
                      "regle_initiale": "AMBIGU", "CJ": "5710", "CJ_LIBELLE": "SAS", "APE": "64.20Z",
                      "APE_LIBELLE": "Activités des sociétés holding", "activite_principale": "64.20Z"}
                     for siren in (SIREN, "987654321")]
        pd.DataFrame(self.rows).to_csv(self.root / "demandeurs_classes.csv", index=False)
        pd.DataFrame([HOLDING]).to_csv(self.root / "naf.csv", index=False)
        self.paths = AgentPaths(demandeurs=self.root / "demandeurs_classes.csv", naf=self.root / "naf.csv",
                                cache=self.root / "llm.jsonl")

    def researcher(self, *, fail=False, with_source=True, cached_no_source=False):
        researcher = Mock()
        researcher.latest = {}
        researcher.cached_current.return_value = False
        if cached_no_source:
            researcher.latest[SIREN] = {"statut": "aucune_source_verifiee", "sources": []}
            researcher.cached_current.side_effect = lambda siren, name: siren == SIREN
        if fail:
            researcher.research.side_effect = WebResearchError("Clé absente")
        else:
            def research(siren, name, **kwargs):
                sources = [source(siren)] if with_source else []
                researcher.latest[siren] = {"sources": sources}
                return {"statut": "sources_trouvees" if sources else "aucune_source_verifiee"}
            researcher.research.side_effect = research
        return researcher

    def fake_classifier(self):
        raw = json.dumps({"famille": "non_determine", "justification": "Information insuffisante.",
                          "confiance": "basse", "preuves": []})
        return Mock(model="test:3b", config_sha256="cfg", config={},
                    ask=Mock(return_value={"message": {"content": raw}}))

    def run_once(self, researcher, classifier=None, **options):
        classifier = classifier or self.fake_classifier()
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_agent(AgentOptions(**{"web": True, "limit": 1, **options}), classifier=classifier,
                               researcher=researcher, paths=self.paths)
        return result, classifier.ask

    def test_default_gemini_limits_web_calls_and_preserves_cache(self):
        session = Mock()
        raw = json.dumps({"famille": "entreprise_autre", "justification": "Activité industrielle décrite par la source.",
                          "confiance": "moyenne", "preuves": [{"champ": "sources_web", "source_id": "web_test", "valeur": EXCERPT}]})
        session.post.return_value = response(answer(raw))
        client = GeminiClient(api_key="gemini-test-secret", session=session, pause=0, system=SYSTEM, schema=SCHEMA)
        researcher = self.researcher()
        self.assertEqual(self.run_once(researcher, client)[0], 0)
        self.assertEqual(researcher.research.call_count, 1)
        cache = self.paths.cache
        record = json.loads(cache.read_text(encoding="utf-8"))
        self.assertEqual(record["famille"], "entreprise_autre")
        self.assertEqual(record["statut_controle"], "a_verifier")
        self.assertEqual(record["provider"], "gemini")
        self.assertEqual(record["entree"]["sources_web"][0]["extrait"], EXCERPT)
        self.assertNotIn("gemini-test-secret", cache.read_text(encoding="utf-8"))
        history = cache.read_bytes()
        researcher.cached_current.return_value = True
        self.assertEqual(self.run_once(researcher, client, sirens=[SIREN], limit=3)[0], 0)
        self.assertEqual(cache.read_bytes(), history)
        self.assertEqual(researcher.research.call_count, 1)
        session.post.assert_called_once()

    def test_limit_is_applied_before_web_research(self):
        researcher = self.researcher()
        result, ask = self.run_once(researcher)
        self.assertEqual(result, 0)
        self.assertEqual(researcher.research.call_count, 1)
        self.assertEqual(ask.call_count, 1)

    def test_missing_search_key_does_not_create_a_model_response(self):
        result, ask = self.run_once(self.researcher(fail=True))
        self.assertEqual(result, 1)
        ask.assert_not_called()
        self.assertFalse(self.paths.cache.exists())

    def test_existing_model_answer_does_not_prevent_a_first_web_search(self):
        self.paths.cache.write_text(json.dumps({
            "siren": SIREN, "modele": "test:3b", "prompt_sha256": PROMPT_SHA256, "config_sha256": "cfg",
            "entree": build_input(self.rows[0], {"64.20Z": "Activités des sociétés holding"})}) + "\n",
            encoding="utf-8")
        researcher = self.researcher()
        self.run_once(researcher)
        self.assertEqual(researcher.research.call_count, 1)

    def test_no_verified_web_source_does_not_trigger_guessing(self):
        result, ask = self.run_once(self.researcher(with_source=False))
        self.assertEqual(result, 0)
        ask.assert_not_called()
        self.assertFalse(self.paths.cache.exists())

    def test_next_limited_batch_skips_previous_searches_without_sources(self):
        researcher = self.researcher(cached_no_source=True)
        result, ask = self.run_once(researcher)
        self.assertEqual(result, 0)
        self.assertEqual(researcher.research.call_count, 1)
        self.assertEqual(researcher.research.call_args.args[0], "987654321")
        ask.assert_called_once()


class CliTests(unittest.TestCase):
    def test_quiet_refresh_runs_all_exports_without_printing_tables(self):
        def refresh_step():
            print("TABLEAU DE RESULTATS")
            return "TABLEAU DE RESULTATS"

        output = io.StringIO()
        with (patch.object(cli, "run_classify", side_effect=refresh_step) as classify,
              patch.object(cli.analyze, "run", side_effect=refresh_step) as patterns,
              patch.object(cli.export, "run", side_effect=refresh_step) as export,
              contextlib.redirect_stdout(output)):
            result = cli.refresh(quiet=True)
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")
        for step in (classify, patterns, export):
            step.assert_called_once_with()

    def test_agent_failure_does_not_refresh_analyses_or_exports(self):
        for code, refreshed in ((1, False), (0, True)):
            with self.subTest(code=code):
                with (patch.object(cli, "run_agent", return_value=code),
                      patch.object(cli, "refresh", return_value=0) as refresh,
                      contextlib.redirect_stdout(io.StringIO())):
                    self.assertEqual(cli.main(["agent", "--limit", "1"]), code)
                self.assertEqual(refresh.called, refreshed)

    def test_limit_must_be_positive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["agent", "--limit", "0"])


if __name__ == "__main__":
    unittest.main()
