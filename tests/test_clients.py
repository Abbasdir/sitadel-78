"""Clients HTTP Gemini et Tavily : contrats d'API, quotas, erreurs sans fuite de clé ; configuration locale."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from fixtures import SIREN, answer, response
from sitadel.agent import cache_matches
from sitadel.clients.gemini import DEFAULT_MODEL, GeminiClient
from sitadel.clients.tavily import TavilyClient
from sitadel.config import read_setting
from sitadel.errors import GeminiIndisponible, WebResearchError, WebServiceError
from sitadel.evidence import WebResearch, check_proposal as parse
from sitadel.prompt import PROMPT_SHA256, SCHEMA, SYSTEM
from sitadel.storage import load_all_history


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.session = Mock()

    def client(self, **kwargs):
        return GeminiClient(api_key="gemini-test-secret", session=self.session, pause=0,
                            system=SYSTEM, schema=SCHEMA, **kwargs)

    def test_missing_key_and_paid_model_never_call_the_service(self):
        with self.assertRaisesRegex(GeminiIndisponible, "GEMINI_API_KEY"):
            GeminiClient(api_key="", session=self.session, system=SYSTEM, schema=SCHEMA)
        with self.assertRaisesRegex(GeminiIndisponible, "Modèle refusé"):
            self.client(model="gemini-4-carbon")
        self.session.post.assert_not_called()

    def test_wire_contract_uses_json_and_never_calls_paid_search(self):
        raw = json.dumps({"famille": "non_determine", "justification": "Preuves insuffisantes.",
                          "confiance": "basse", "preuves": []})
        self.session.post.return_value = response(answer(raw))
        client = self.client()
        entry = {"siren": SIREN, "denomination": "ENTREPRISE TEST"}
        result = client.ask(entry)
        call = self.session.post.call_args
        self.assertEqual(call.args, (f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent",))
        self.assertEqual(call.kwargs["headers"]["x-goog-api-key"], "gemini-test-secret")
        self.assertFalse(call.kwargs["allow_redirects"])
        payload = call.kwargs["json"]
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["generationConfig"]["responseJsonSchema"], SCHEMA)
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], SYSTEM)
        self.assertNotIn("gemini-test-secret", json.dumps(payload))
        self.assertEqual(result["message"]["content"], raw)
        self.assertEqual(parse(raw, entry)["statut_controle"], "abstention")
        self.assertEqual(result["usage"]["promptTokenCount"], 100)

    def test_errors_stop_without_retry_or_disclosing_key(self):
        for status in (400, 401, 403, 404, 429, 503):
            with self.subTest(status=status):
                self.session.reset_mock()
                self.session.post.return_value = response({"error": "gemini-test-secret"}, status)
                with self.assertRaises(GeminiIndisponible) as caught:
                    self.client().ask({"siren": SIREN})
                self.assertIn(str(status), str(caught.exception))
                self.assertNotIn("gemini-test-secret", str(caught.exception))
                self.session.post.assert_called_once()

    def test_network_errors_do_not_become_classifications(self):
        for error in (requests.Timeout("gemini-test-secret"), requests.ConnectionError("gemini-test-secret")):
            with self.subTest(error=type(error).__name__):
                self.session.post.side_effect = error
                with self.assertRaises(GeminiIndisponible) as caught:
                    self.client().ask({"siren": SIREN})
                self.assertNotIn("gemini-test-secret", str(caught.exception))

    def test_truncated_blocked_or_empty_answers_are_not_saved_as_abstentions(self):
        invalid = [{}, [], {"candidates": [{"finishReason": "MAX_TOKENS"}]},
                   {"candidates": [{"finishReason": "SAFETY"}]},
                   answer(""), {"candidates": [None]},
                   {"candidates": [{"finishReason": "STOP", "content": {"parts": None}}]}]
        for data in invalid:
            with self.subTest(data=data):
                self.session.post.return_value = response(data)
                with self.assertRaises(GeminiIndisponible):
                    self.client().ask({"siren": SIREN})

    def test_cache_changes_when_provider_parameters_change(self):
        client = self.client()
        entry = {"siren": SIREN}
        record = {"modele": client.model, "entree": entry, "prompt_sha256": PROMPT_SHA256,
                  "config_sha256": client.config_sha256}
        self.assertTrue(cache_matches(record, entry, client.model, config_sha256=client.config_sha256))
        self.assertFalse(cache_matches(record, entry, client.model, config_sha256="different"))
        self.assertFalse(cache_matches(record, entry, "qwen2.5:3b"))

    def test_local_configuration_and_environment_do_not_mix_providers(self):
        (self.root / ".env").write_text('GEMINI_API_KEY="gemini-test-secret"\nTAVILY_API_KEY=tavily-test-secret\n', encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read_setting("GEMINI_API_KEY", self.root), "gemini-test-secret")
            self.assertEqual(read_setting("TAVILY_API_KEY", self.root), "tavily-test-secret")
            self.assertEqual(read_setting("OLLAMA_API_KEY", self.root), "")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "environment-key"}):
            self.assertEqual(read_setting("GEMINI_API_KEY", self.root), "environment-key")

    def test_history_merges_by_date_without_deleting_old_answers(self):
        records = [{"siren": SIREN, "horodatage": "2026-11-24T12:00:00+00:00", "modele": "qwen2.5:3b"},
                   {"siren": SIREN, "horodatage": "2026-11-25T12:00:00+00:00", "modele": DEFAULT_MODEL}]
        for name, record in zip(("ollama_decisions.jsonl", "gemini_decisions.jsonl"), records):
            (self.root / name).write_text(json.dumps(record) + "\n", encoding="utf-8")
        self.assertEqual(load_all_history(self.root), records)


class TavilyErrorTests(unittest.TestCase):
    """Erreurs du service de recherche : arrêt sans relance, sans fuite de clé ni résultat en cache."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.session = Mock()

    def researcher(self):
        return WebResearch(TavilyClient("test-key", session=self.session), cache=self.root / "cache.jsonl",
                           seeds=self.root / "seeds.csv", session=self.session, pause=0, max_pages=3)

    def test_authentication_error_does_not_expose_the_key(self):
        self.session.post.return_value = response(status=401)
        with self.assertRaises(WebResearchError) as caught:
            self.researcher().research(SIREN, "ENTREPRISE TEST")
        self.assertNotIn("test-key", str(caught.exception))

    def test_payment_required_is_explicit_without_retry_or_saved_result(self):
        self.session.post.return_value = response(status=402)
        client = self.researcher()
        with self.assertRaises(WebServiceError) as caught:
            client.research(SIREN, "ENTREPRISE TEST")
        message = str(caught.exception)
        self.assertIn("HTTP 402", message)
        self.assertIn("pay-as-you-go", message)
        self.assertNotIn("test-key", message)
        self.assertEqual(self.session.post.call_count, 1)
        self.assertFalse(client.cache.exists())

    def test_network_failure_does_not_expose_request_details(self):
        for error in (requests.Timeout("test-key"), requests.ConnectionError("test-key")):
            with self.subTest(error=type(error).__name__):
                self.session.post.side_effect = error
                with self.assertRaises(WebResearchError) as caught:
                    self.researcher().research(SIREN, "ENTREPRISE TEST")
                self.assertNotIn("test-key", str(caught.exception))
                self.assertNotIn("JSON", str(caught.exception))

    def test_server_failure_and_invalid_json_are_distinguished(self):
        self.session.post.return_value = response(status=503)
        with self.assertRaisesRegex(WebResearchError, "HTTP 503"):
            self.researcher().research(SIREN, "ENTREPRISE TEST")
        invalid = Mock(status_code=200)
        invalid.json.side_effect = ValueError("test-key")
        self.session.post.side_effect = None
        self.session.post.return_value = invalid
        with self.assertRaises(WebResearchError) as caught:
            self.researcher().research(SIREN, "ENTREPRISE TEST")
        self.assertIn("JSON", str(caught.exception))
        self.assertNotIn("test-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
