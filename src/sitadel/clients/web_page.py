"""Lecture directe d'une page HTML publique connue (mode sans clé de recherche)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from ..errors import WebResearchError

USER_AGENT = "sitadel-78-etude/0.2"
MAX_BYTES = 2_000_000


def assert_public_destination(url: str) -> None:
    """Ne jamais lire une adresse du réseau local."""
    host = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(host, None)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise WebResearchError("La page ne pointe pas vers une adresse Internet publique.")
    except (socket.gaierror, ValueError) as exc:
        raise WebResearchError("Adresse publique non résolue.") from exc


class HtmlPageReader:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def read(self, url: str) -> dict:
        """{"content": paragraphes, "identity_text": texte complet, "links": liens absolus}."""
        try:
            response = self.session.get(url, headers={"User-Agent": USER_AGENT},
                                        timeout=30, allow_redirects=False, stream=True)
            with response:
                # Pas de suivi automatique des redirections vers un autre site.
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise WebResearchError("URL redirigée : fournir l'adresse publique finale.")
                if "html" not in response.headers.get("Content-Type", ""):
                    raise WebResearchError("Le mode direct accepte uniquement les pages HTML.")
                html = _read_limited(response)
        except requests.RequestException as exc:
            raise WebResearchError("Page publique inaccessible.") from exc
        return _parse_html(url, html)


def _read_limited(response) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_content(65536):
        size += len(chunk)
        if size > MAX_BYTES:
            raise WebResearchError("Page trop volumineuse.")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_html(url: str, html: bytes) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    links = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)]
    identity_text = soup.get_text(" ", strip=True)
    for tag in soup(["script", "style", "noscript", "form", "nav", "footer", "aside", "header"]):
        tag.decompose()
    descriptions = [tag.get("content", "") for tag in soup.find_all("meta")
                    if tag.get("name", "").lower() == "description"
                    or tag.get("property", "").lower() == "og:description"]
    blocks = descriptions + [tag.get_text(" ", strip=True) for tag in soup.select("p, li")]
    content = "\n".join(blocks) if blocks else soup.get_text("\n", strip=True)
    return {"content": content, "identity_text": identity_text, "links": links}
