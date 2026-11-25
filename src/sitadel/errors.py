"""Erreurs partagées entre les clients HTTP et le pipeline. Les messages ne contiennent jamais de clé."""
from __future__ import annotations


class WebResearchError(Exception):
    """Une page ou une recherche n'a rien donné d'exploitable : noter l'observation et continuer."""


class WebServiceError(WebResearchError):
    """Erreur globale (clé, quota, service) : arrêter, sans essayer d'autres pages."""


class GeminiIndisponible(Exception):
    """Le classement ne peut pas être demandé ; aucun résultat n'est enregistré."""
