"""Données et doubles de test partagés : aucun accès réseau."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SIREN = "123456789"
PAGE = "https://entreprise.example/activites"
LEGAL = "https://entreprise.example/mentions-legales"
EXCERPT = "Notre entreprise fabrique des équipements industriels pour l'aviation et l'aéronautique."


def source(siren: str = SIREN, **changes) -> dict:
    return {"id": "web_test", "siren": siren, "url": PAGE, "url_identite": LEGAL,
            "identite_verifiee": True, "extrait": EXCERPT, **changes}


def response(data=None, status=200):
    """Réponse JSON simulée (Gemini, Tavily)."""
    return Mock(status_code=status, json=Mock(return_value=data))


def answer(raw: str) -> dict:
    """Réponse Gemini complète contenant `raw`."""
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": raw}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 40}}


def tavily_post(pages: dict[str, str], search_results: list[str] | None = None, status: int = 200):
    """Simule /search et /extract : `pages` associe une URL à son texte markdown."""
    def post(url, *, json, **kwargs):
        if status != 200:
            return response(status=status)
        if url.endswith("/search"):
            return response({"results": [{"url": u} for u in (search_results or [PAGE])]})
        target = json["urls"][0]
        return response({"results": [{"url": target, "raw_content": pages.get(target, "")}]})
    return post


class HtmlResponse:
    """Réponse HTML simulée pour la lecture directe des URL connues."""

    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("Erreur HTTP simulée")

    def iter_content(self, size):
        yield self.text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
