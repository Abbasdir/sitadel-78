"""Client Gemini (generateContent) sur une offre Free Tier, sans outil Google Search payant.

La clé doit appartenir à un projet Free Tier : le protocole generateContent ne
permet pas de déduire si la facturation a été activée sur le compte de l'utilisateur.
"""
from __future__ import annotations

import hashlib
import json
import time

import requests

from ..config import read_setting
from ..errors import GeminiIndisponible

DEFAULT_MODEL = "gemini-3.5-flash-lite"
FREE_MODELS = {DEFAULT_MODEL, "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"}
API = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    """Un appel = une réponse JSON conforme au schéma fourni, ou GeminiIndisponible."""

    def __init__(self, model: str = DEFAULT_MODEL, *, system: str, schema: dict,
                 api_key: str | None = None, session=None, pause: float = 6):
        if model not in FREE_MODELS:
            raise GeminiIndisponible("Modèle refusé : choisir un modèle Flash-Lite avec offre gratuite.")
        self.api_key = read_setting("GEMINI_API_KEY") if api_key is None else api_key
        if not self.api_key or self.api_key.lower() in {"cle", "ta_cle", "votre_cle"}:
            raise GeminiIndisponible(
                "GEMINI_API_KEY absente : ajouter une clé d'un projet Free Tier dans .env "
                "(https://aistudio.google.com/api-keys), sans activer la facturation."
            )
        if not self.api_key.isascii() or any(char.isspace() for char in self.api_key):
            raise GeminiIndisponible("Format de GEMINI_API_KEY invalide : vérifier la valeur dans .env.")
        self.model = model
        self.system = system
        self.session = session or requests.Session()
        self.pause = pause
        self.last_request = 0.0
        self.config = {"temperature": 0, "maxOutputTokens": 2048,
                       "responseMimeType": "application/json", "responseJsonSchema": schema}
        self.config_sha256 = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()

    def _wait(self) -> None:
        wait = self.pause - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()

    def ask(self, entree: dict) -> dict:
        """Renvoie {"message": {"content": texte JSON}, "usage": compteurs de tokens}."""
        self._wait()
        # Les sources sont lues par Python ; Gemini ne reçoit que les champs masqués et les courts
        # extraits vérifiés. Aucun tools/google_search.
        payload = {"systemInstruction": {"parts": [{"text": self.system}]},
                   "contents": [{"role": "user", "parts": [{"text": json.dumps(entree, ensure_ascii=False)}]}],
                   "generationConfig": self.config}
        data = self._post(payload)
        return {"message": {"content": _answer_text(data)}, "usage": _usage(data)}

    def _post(self, payload: dict) -> dict:
        try:
            response = self.session.post(f"{API}/{self.model}:generateContent", json=payload,
                                         headers={"x-goog-api-key": self.api_key}, timeout=90,
                                         allow_redirects=False)
            _raise_for_status(response.status_code)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Objet JSON attendu")
            return data
        except requests.Timeout as exc:
            raise GeminiIndisponible("Délai de réponse Gemini dépassé, aucune relance automatique.") from exc
        except requests.RequestException as exc:
            raise GeminiIndisponible("Connexion à Gemini impossible.") from exc
        except ValueError as exc:
            raise GeminiIndisponible("Réponse Gemini illisible.") from exc


def _raise_for_status(status: int) -> None:
    if status in {400, 401, 403}:
        raise GeminiIndisponible(
            f"Gemini refuse la requête (HTTP {status}) : vérifier la clé, l'accès au modèle "
            "et le projet Free Tier. Aucun basculement vers une offre payante."
        )
    if status == 404:
        raise GeminiIndisponible("Modèle Gemini inaccessible (HTTP 404), aucun modèle de remplacement appelé.")
    if status == 429:
        raise GeminiIndisponible(
            "Quota Gemini gratuit atteint ou indisponible (HTTP 429). "
            "Réessayer après son renouvellement ; aucune relance automatique ni offre payante."
        )
    if status != 200:
        raise GeminiIndisponible(f"Service Gemini indisponible (HTTP {status}).")


def _answer_text(data: dict) -> str:
    """Texte de la réponse complète ; une réponse tronquée, bloquée ou vide n'est jamais une abstention."""
    candidates = data.get("candidates", [])
    candidate = candidates[0] if isinstance(candidates, list) and candidates else None
    if not isinstance(candidate, dict) or candidate.get("finishReason") != "STOP":
        raise GeminiIndisponible("Gemini n'a pas fourni de réponse complète ; aucun résultat de classement enregistré.")
    content = candidate.get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    parts = parts if isinstance(parts, list) else []
    raw = "".join(part["text"] for part in parts if isinstance(part, dict)
                  and isinstance(part.get("text"), str) and not part.get("thought"))
    if not raw.strip():
        raise GeminiIndisponible("Réponse Gemini vide ; aucun résultat de classement enregistré.")
    return raw


def _usage(data: dict) -> dict:
    usage = data.get("usageMetadata", {})
    return {key: value for key, value in usage.items() if isinstance(value, int)} if isinstance(usage, dict) else {}
