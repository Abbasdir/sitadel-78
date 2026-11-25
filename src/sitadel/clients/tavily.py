"""Client Tavily (offre Researcher gratuite) : recherche et extraction, requêtes `basic` uniquement."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import requests

from ..errors import WebResearchError, WebServiceError

API = "https://api.tavily.com"


class TavilyClient:
    def __init__(self, api_key: str, *, session=None, exclude_domains: list[str] | None = None):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.exclude_domains = exclude_domains or []

    def search(self, query: str, max_results: int = 3) -> list:
        body = {"query": query, "max_results": max_results,
                "search_depth": "basic", "auto_parameters": False,
                "exclude_domains": self.exclude_domains,
                "include_answer": False, "include_raw_content": False, "include_images": False}
        results = self._post("search", body).get("results", [])
        return results if isinstance(results, list) else []

    def extract(self, url: str) -> dict:
        """Texte markdown d'une page et liens qu'elle propose ; WebResearchError si la page n'est pas lue."""
        body = {"urls": [url], "extract_depth": "basic", "format": "markdown", "include_images": False}
        results = self._post("extract", body).get("results", [])
        page = next((page for page in results if isinstance(page, dict)
                     and page.get("url") == url), None) if isinstance(results, list) else None
        if page is None or not isinstance(page.get("raw_content"), str):
            raise WebResearchError("Page non extraite par Tavily.")
        text = page["raw_content"]
        # Les liens de mentions légales sont proposés par la page extraite, jamais inventés par le LLM.
        links = [urljoin(url, link) for link in re.findall(r"\]\(([^\s)]+)\)", text)]
        return {"content": text, "links": links}

    def _post(self, endpoint: str, body: dict) -> dict:
        try:
            response = self.session.post(f"{API}/{endpoint}", json=body,
                                         headers={"Authorization": f"Bearer {self.api_key}"},
                                         timeout=45, allow_redirects=False)
            _raise_for_status(response.status_code)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Objet JSON attendu")
            return data
        except requests.Timeout as exc:
            raise WebServiceError("Délai de réponse Tavily dépassé.") from exc
        except requests.RequestException as exc:
            raise WebServiceError("Connexion à Tavily impossible.") from exc
        except ValueError as exc:
            raise WebServiceError("Réponse Tavily illisible : format JSON attendu.") from exc


def _raise_for_status(status: int) -> None:
    if status in {401, 403}:
        raise WebServiceError(f"Clé Tavily refusée (HTTP {status}) : vérifier TAVILY_API_KEY dans .env.")
    if status in {402, 429, 432, 433}:
        raise WebServiceError(
            f"Quota gratuit Tavily atteint ou accès limité (HTTP {status}). "
            "Arrêt sans relance ni activation de pay-as-you-go."
        )
    if status != 200:
        raise WebServiceError(f"Service Tavily indisponible (HTTP {status}).")
