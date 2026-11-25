"""Recherche simulée, identité SIREN, sélection d'extraits et preuves web : aucun accès réseau."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fixtures import EXCERPT, LEGAL, PAGE, SIREN, HtmlResponse, response, source, tavily_post
from sitadel import agent
from sitadel.clients.tavily import TavilyClient
from sitadel.clients.web_page import assert_public_destination
from sitadel.config import read_setting
from sitadel.errors import WebResearchError, WebServiceError
from sitadel.evidence import (WebResearch, activity_excerpts, check_proposal as parse, contains_siren,
                              legal_page, same_site, usable_activity_url, verified_sources)
from sitadel.prompt import build_input


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.session = Mock()

    def researcher(self, key="test-key", seeds=None):
        client = TavilyClient(key, session=self.session) if key else None
        return WebResearch(client, cache=self.root / "cache.jsonl", seeds=seeds or self.root / "seeds.csv",
                           session=self.session, pause=0, max_pages=3)

    def seed_file(self, url=PAGE, identity=LEGAL):
        path = self.root / "seeds.csv"
        path.write_text(f"SIREN_DEM,url,url_identite\n{SIREN},{url},{identity}\n", encoding="utf-8")
        return path

    def pages(self, identity=SIREN):
        return {PAGE: EXCERPT + f"\n[Informations légales]({LEGAL})\nPrésident PERSONNE_TEST dans la technologie.",
                LEGAL: f"RCS {identity}. Président PERSONNE_TEST."}

    # --- recherche Tavily ---

    def test_search_and_extract_prove_identity_without_saving_people_or_secrets(self):
        self.session.post.side_effect = tavily_post(self.pages())
        client = self.researcher(key="tavily-test-secret")
        record = client.research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["provider"], "tavily")
        self.assertEqual(record["statut"], "sources_trouvees")
        self.assertEqual(record["sources"][0]["url_identite"], LEGAL)
        self.assertEqual(record["sources"][0]["extrait"], EXCERPT)
        for call in self.session.post.call_args_list:
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer tavily-test-secret")
            body = call.kwargs["json"]
            if call.args[0].endswith("/search"):
                self.assertEqual(body["search_depth"], "basic")
                self.assertFalse(body["auto_parameters"])
                self.assertFalse(body["include_answer"])
            else:
                self.assertEqual(body["extract_depth"], "basic")
        text = client.cache.read_text(encoding="utf-8")
        self.assertNotIn("PERSONNE_TEST", text)
        self.assertNotIn("tavily-test-secret", text)
        count = self.session.post.call_count
        client.research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(self.session.post.call_count, count)

    def test_search_fetch_identity_and_cache_from_a_known_url(self):
        self.session.post.side_effect = tavily_post(self.pages())
        client = self.researcher(seeds=self.seed_file())
        record = client.research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["statut"], "sources_trouvees")
        self.assertEqual(record["sources"][0]["url_identite"], LEGAL)
        self.assertEqual(record["sources"][0]["extrait"], EXCERPT)
        searches = [c for c in self.session.post.call_args_list if c.args[0].endswith("/search")]
        self.assertEqual(len(searches), 1)  # une URL connue dispense de la recherche par nom
        calls = self.session.post.call_count
        client.research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(self.session.post.call_count, calls)
        text = client.cache.read_text(encoding="utf-8")
        self.assertNotIn("PERSONNE_TEST", text)
        self.assertNotIn("test-key", text)

    def test_wrong_entity_cannot_supply_classification_evidence(self):
        self.session.post.side_effect = tavily_post(self.pages(identity="987654321"))
        record = self.researcher().research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["sources"], [])
        self.assertEqual(record["statut"], "aucune_source_verifiee")

    def test_quota_during_extraction_stops_without_more_pages_or_empty_cached_success(self):
        search = tavily_post(self.pages())
        def post(url, **kwargs):
            return search(url, **kwargs) if url.endswith("/search") else response(status=432)
        self.session.post.side_effect = post
        client = self.researcher(key="tavily-test-secret")
        with self.assertRaises(WebServiceError) as caught:
            client.research(SIREN, "ENTREPRISE TEST")
        self.assertIn("432", str(caught.exception))
        self.assertNotIn("tavily-test-secret", str(caught.exception))
        self.assertFalse(client.cache.exists())
        self.assertEqual(self.session.post.call_count, 3)  # deux recherches et une extraction

    def test_ollama_key_does_not_replace_a_missing_tavily_key(self):
        settings = {"OLLAMA_API_KEY": "ollama-test-secret"}
        with patch.object(agent, "read_setting", side_effect=lambda name: settings.get(name, "")):
            client = agent.make_researcher("tavily", self.root / "seeds.csv", cache=self.root / "web.jsonl",
                                           session=self.session)
        with self.assertRaisesRegex(WebResearchError, "TAVILY_API_KEY"):
            client.research(SIREN, "ENTREPRISE TEST")
        self.session.post.assert_not_called()
        self.session.get.assert_not_called()

    def test_terms_pages_can_verify_identity_but_never_describe_activity(self):
        terms = "https://entreprise.example/en/terms-and-conditions"
        self.assertTrue(legal_page(terms))
        self.session.post.side_effect = tavily_post({PAGE: EXCERPT + f"\n[Terms]({terms})",
                                                     terms: f"RCS {SIREN}.\n{EXCERPT}"})
        record = self.researcher().research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["sources"][0]["url"], PAGE)
        self.assertEqual(record["sources"][0]["url_identite"], terms)

    def test_missing_key_stops_without_network_call(self):
        with self.assertRaises(WebResearchError):
            self.researcher(key="").research(SIREN, "ENTREPRISE TEST")
        self.session.post.assert_not_called()
        self.session.get.assert_not_called()

    def test_request_budget_is_bounded(self):
        self.session.post.side_effect = tavily_post(
            {url: EXCERPT + f"\n[Mentions]({LEGAL})" for url in (PAGE, PAGE + "2", PAGE + "3")},
            search_results=[PAGE, PAGE + "2", PAGE + "3"])
        record = self.researcher().research(SIREN, "ENTREPRISE TEST")
        fetches = [call for call in self.session.post.call_args_list if call.args[0].endswith("/extract")]
        self.assertLessEqual(len(fetches), 3)
        self.assertLessEqual(len(record["pages_consultees"]), 3)

    # --- lecture directe des URL connues ---

    def test_wrong_siren_does_not_produce_a_source(self):
        self.session.get.side_effect = [HtmlResponse(f'<p>{EXCERPT}</p>'),
                                        HtmlResponse("<p>RCS 987654321</p>")]
        with patch("sitadel.clients.web_page.assert_public_destination"):
            record = self.researcher(key="", seeds=self.seed_file()).research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["sources"], [])
        self.assertEqual(record["statut"], "aucune_source_verifiee")

    def test_known_urls_work_without_api_key(self):
        self.session.get.side_effect = [
            HtmlResponse(f'<html><meta name="description" content="{EXCERPT}"><a href="{LEGAL}">Mentions</a></html>'),
            HtmlResponse(f"<html><p>RCS {SIREN}</p><p>Directeur PERSONNE_TEST</p></html>"),
        ]
        with patch("sitadel.clients.web_page.assert_public_destination"):
            record = self.researcher(key="", seeds=self.seed_file()).research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["provider"], "url_connue")
        self.assertTrue(record["sources"])
        self.session.post.assert_not_called()

    def test_legal_page_is_not_an_activity_description(self):
        path = self.seed_file(url=LEGAL, identity="")
        self.session.get.return_value = HtmlResponse(f"<p>RCS {SIREN}</p><p>{EXCERPT}</p>")
        with patch("sitadel.clients.web_page.assert_public_destination"):
            record = self.researcher(key="", seeds=path).research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["sources"], [])

    def test_personal_page_is_not_fetched_and_its_address_is_not_saved(self):
        url = "https://annuaire.example/dirigeant/PERSONNE_TEST"
        client = self.researcher(key="", seeds=self.seed_file(url=url, identity=""))
        record = client.research(SIREN, "ENTREPRISE TEST")
        self.assertEqual(record["sources"], [])
        self.assertNotIn("PERSONNE_TEST", client.cache.read_text(encoding="utf-8"))
        self.session.get.assert_not_called()
        self.session.post.assert_not_called()

    def test_local_dns_destination_is_refused(self):
        with patch("sitadel.clients.web_page.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            with self.assertRaises(WebResearchError):
                assert_public_destination(PAGE)

    # --- sélection des extraits ---

    def test_actual_thales_and_directory_fragments_are_not_activity_evidence(self):
        rejected = [
            "It presents the various activities of the Thales Group, its products and services, and news about its various entities.",
            "3 Activités de recherche et développement",
            "Actionnaires | État français (26,6 %) Dassault Aviation (26,59 %)",
            "Société d'hébergement et de traitement de données | En savoir +",
            "Grossiste en équipements industriels | En savoir +",
            "Attention, les horaires n'ont pas été mis à jour, les informations ne sont pas garanties.",
            "Les informations sont disponibles sur notre portail.",
            "## Notre entreprise est spécialisée dans la promotion immobilière",
        ]
        self.assertEqual(activity_excerpts("\n".join(rejected)), [])
        self.assertEqual(activity_excerpts(EXCERPT), [EXCERPT])

    def test_statutory_clauses_and_company_names_are_not_activity_evidence(self):
        # Extraits réels laissés passer par la version précédente du filtre (DIVIMAJA, CIIF).
        clause = ("Agrément : les cessions d’actions au profit d’associés ou de tiers sont soumises "
                  "à l’agrément de la collectivité des associés.")
        name = "COMPAGNIE D'INVESTISSEMENTS IMMOBILIERS ET FINANCIERS"
        headquarters = ("Elle est composée d’un établissement principal, siège social de l’entreprise "
                        f"{name}, situé : 75 Rue DE LOURMEL, 75015 PARIS.")
        self.assertEqual(activity_excerpts(clause, "DIVIMAJA"), [])
        self.assertEqual(activity_excerpts(headquarters, name), [])
        weak = source(extrait=headquarters)
        self.assertEqual(verified_sources(SIREN, {SIREN: {"sources": [weak]}}, name), [])
        output = {"famille": "sci_fonciere", "justification": "Société immobilière.", "confiance": "basse",
                  "preuves": [{"champ": "sources_web", "source_id": "web_test", "valeur": headquarters}]}
        entry = {"siren": SIREN, "denomination": name, "sources_web": [weak]}
        self.assertEqual(parse(json.dumps(output), entry)["statut_controle"], "rejetee")
        # Une vraie description d'activité reste retenue, même quand la dénomination y figure.
        thales = ("Thales est un groupe d'électronique français spécialisé dans l'aérospatial, la défense, "
                  "la sécurité et le transport terrestre.")
        self.assertEqual(activity_excerpts(thales, "THALES"), [thales])
        self.assertEqual(activity_excerpts(EXCERPT, "ENTREPRISE TEST"), [EXCERPT])

    def test_excerpts_naming_a_natural_person_are_never_kept(self):
        # Cas réel (Groupe Flo) : nom de fondateur au milieu d'une phrase d'activité. Nom fictif ici.
        named = ("Alors que se développe la restauration rapide, Jean-Paul Exemple mise sur des plats "
                 "traditionnels et un décor emprunté à l'Art Nouveau.")
        self.assertEqual(activity_excerpts(named, "GROUPE FLO"), [])
        self.assertEqual(verified_sources(SIREN, {SIREN: {"sources": [source(extrait=named)]}}, "GROUPE FLO"), [])
        kept = "Le groupe Flo est l'un des principaux groupes de la restauration française."
        self.assertEqual(activity_excerpts(kept, "GROUPE FLO"), [kept])

    def test_a_reference_to_the_target_siren_does_not_validate_a_different_company_page(self):
        wrong = "https://annuaire.example/societe/filiale-987654321"
        self.assertFalse(usable_activity_url(wrong, SIREN))
        self.assertFalse(usable_activity_url("https://bodacc.example/bulletin.pdf", SIREN))
        self.assertTrue(usable_activity_url("https://annuaire.example/societe/12345678900012", SIREN))
        for url in (wrong, "https://bodacc.example/bulletin.pdf"):
            wrong_source = source(id="web_wrong_entity", url=url, url_identite=url)
            self.assertEqual(verified_sources(SIREN, {SIREN: {"sources": [wrong_source]}}), [])

    def test_related_company_paragraph_is_not_attributed_to_the_page_owner(self):
        content = "Notre entreprise est une holding de gestion.\n## Entreprises similaires\n" + EXCERPT
        self.assertEqual(activity_excerpts(content), [])

    def test_old_cached_weak_sources_cannot_be_passed_to_the_model(self):
        for text, url in [
            (EXCERPT, "https://entreprise.example/en/terms-and-conditions"),
            ("Grossiste en équipements industriels | En savoir +", PAGE),
            ("3 Activités de recherche et développement", PAGE),
        ]:
            with self.subTest(url=url, text=text):
                weak = source(id="web_old", url=url, extrait=text)
                self.assertEqual(verified_sources(SIREN, {SIREN: {"sources": [weak]}}), [])

    def test_siren_spacing_and_company_site_boundaries(self):
        self.assertTrue(contains_siren("RCS 123 456 789", SIREN))
        self.assertFalse(contains_siren("01234567890", SIREN))
        self.assertTrue(same_site(PAGE, LEGAL))
        self.assertFalse(same_site(PAGE, "https://entreprise.example.evil.invalid/legal"))

    def test_only_activity_passages_are_kept(self):
        text = EXCERPT + "\nDirecteur PERSONNE_TEST expert des technologies.\nContact: test@example.org"
        self.assertEqual(activity_excerpts(text), [EXCERPT])

    def test_configuration_can_be_read_locally(self):
        (self.root / ".env").write_text("TAVILY_API_KEY='local-test-key'\n", encoding="utf-8")
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            self.assertEqual(read_setting("TAVILY_API_KEY", self.root), "local-test-key")

    # --- contrôle des citations web ---

    def test_citing_industrial_activity_does_not_support_property_development(self):
        entry = {"siren": SIREN, "sources_web": [source()]}
        output = {"famille": "promoteur_prive", "justification": "Cette entreprise est un promoteur.",
                  "confiance": "basse", "preuves": [{"champ": "sources_web", "source_id": "web_test", "valeur": EXCERPT}]}
        self.assertEqual(parse(json.dumps(output), entry)["statut_controle"], "rejetee")
        output["famille"] = "entreprise_autre"
        self.assertEqual(parse(json.dumps(output), entry)["statut_controle"], "a_verifier")

    def test_web_proof_requires_identity_and_exact_excerpt(self):
        entry = {"siren": SIREN, "sources_web": [source()]}
        output = {"famille": "entreprise_autre", "justification": "L'activité décrite relève de l'aéronautique.",
                  "confiance": "basse", "preuves": [{"champ": "sources_web", "source_id": "web_test", "valeur": EXCERPT}]}
        self.assertEqual(parse(json.dumps(output), entry)["statut_controle"], "a_verifier")
        for changed in (source(siren="987654321"), source(identite_verifiee=False),
                        source(extrait="autre texte"), source(url_identite="https://autre.example/legal")):
            with self.subTest(changed=changed):
                self.assertEqual(parse(json.dumps(output), {**entry, "sources_web": [changed]})["statut_controle"], "rejetee")
        self.assertEqual(verified_sources("", {"": {"sources": [source()]}}), [])

    def test_web_input_ignores_access_date_but_tracks_content(self):
        d = {"SIREN_DEM": SIREN, "DENOM": "ENTREPRISE TEST"}
        dated = {"id": "web_test", "extrait": EXCERPT, "consulte_le": "2026-11-24"}
        self.assertEqual(build_input(d, {}, [dated]), build_input(d, {}, [{**dated, "consulte_le": "2026-11-25"}]))
        self.assertNotEqual(build_input(d, {}, [dated]), build_input(d, {}, [{**dated, "extrait": "activité modifiée"}]))

    def test_a_web_url_does_not_make_a_generic_activity_discriminating(self):
        text = "Cette société exerce une activité de holding et de siège social."
        output = {"famille": "promoteur_prive", "justification": "Holding donc promoteur.", "confiance": "basse",
                  "preuves": [{"champ": "sources_web", "source_id": "web_test", "valeur": text}]}
        result = parse(json.dumps(output), {"siren": SIREN, "sources_web": [source(extrait=text)]})
        self.assertEqual(result["statut_controle"], "rejetee")


if __name__ == "__main__":
    unittest.main()
