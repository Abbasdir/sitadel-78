"""Agent unique : proposition sourcée ou abstention pour les demandeurs laissés ambigus par les règles.

Déroulé pour chaque demandeur sélectionné :
  1. (option --web) recherche de sources dont l'identité est vérifiée par le SIREN ;
  2. sans source vérifiable en mode --web : pas d'appel au modèle (aucune devinette) ;
  3. appel Gemini avec l'entrée masquée + extraits vérifiés, contrôle des citations, ajout au cache.

L'agent n'écrit que dans ses caches (ajout seul). Il ne modifie ni le classement, ni les analyses, ni
les exports : la CLI les actualise ensuite, et seulement si l'exécution s'est bien terminée.
Aucune proposition n'est appliquée sans validation manuelle (voir review.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .clients.gemini import DEFAULT_MODEL, GeminiClient
from .clients.tavily import TavilyClient
from .config import CACHE_GEMINI, DEMANDEURS, NAF_INSEE, SOURCES_WEB_CONNUES, read_setting
from .errors import GeminiIndisponible, WebResearchError
from .evidence import DISALLOWED_HOSTS, WebResearch, check_proposal, verified_sources
from .prompt import PROMPT_SHA256, SCHEMA, SYSTEM, VERSION_PROMPT, build_input
from .storage import append_jsonl, load_history, load_web_latest

PROVIDER = "gemini"
REGLES_AMBIGUES = ["AMBIGU", "AUCUN"]


@dataclass
class AgentOptions:
    limit: int = 3                      # demandeurs maximum par exécution, appliqué avant toute recherche
    sirens: list[str] = field(default_factory=list)
    force: bool = False                 # refaire l'essai en conservant l'historique
    web: bool = False                   # rechercher des sources avant de proposer
    refresh_web: bool = False           # refaire les recherches déjà en cache
    web_provider: str = "tavily"        # "tavily" ou "urls" (URL connues seulement, sans clé)
    web_sources: Path = SOURCES_WEB_CONNUES
    model: str | None = None


@dataclass
class AgentPaths:
    demandeurs: Path = DEMANDEURS
    naf: Path = NAF_INSEE
    cache: Path = CACHE_GEMINI


def make_classifier(model: str | None = None) -> GeminiClient:
    return GeminiClient(model or read_setting("GEMINI_MODEL") or DEFAULT_MODEL, system=SYSTEM, schema=SCHEMA)


def make_researcher(web_provider: str = "tavily", seeds: Path = SOURCES_WEB_CONNUES, **kwargs) -> WebResearch:
    """Tavily si une clé est configurée ; sinon (ou en mode "urls") lecture directe des URL connues."""
    key = read_setting("TAVILY_API_KEY") if web_provider == "tavily" else ""
    client = TavilyClient(key, exclude_domains=sorted(DISALLOWED_HOSTS)) if key else None
    return WebResearch(client, seeds=seeds, **kwargs)


def cache_matches(record: dict, entree: dict, model: str, *, config_sha256: str | None = None) -> bool:
    """Une réponse en cache est réutilisable si prompt, modèle, paramètres et entrée sont identiques."""
    return (record.get("prompt_sha256") == PROMPT_SHA256
            and record.get("modele") == model and record.get("entree") == entree
            and (config_sha256 is None or record.get("config_sha256") == config_sha256))


def select_ambiguous(demandeurs: pd.DataFrame, sirens: list[str] | None = None) -> pd.DataFrame:
    """Toujours repartir des cas laissés ambigus par les règles (même après une validation)."""
    regle0 = demandeurs["regle_initiale"] if "regle_initiale" in demandeurs else demandeurs["regle_appliquee"]
    todo = demandeurs[demandeurs["famille"].eq("non_determine") | regle0.isin(REGLES_AMBIGUES)]
    return todo[todo["SIREN_DEM"].isin(sirens)] if sirens else todo


def run_agent(options: AgentOptions, *, classifier=None, researcher=None,
              paths: AgentPaths | None = None) -> int:
    """Renvoie 0 si l'exécution s'est terminée normalement, 1 en cas d'arrêt (clé, quota, service)."""
    paths = paths or AgentPaths()
    dem = pd.read_csv(paths.demandeurs, dtype=str)
    naf = pd.read_csv(paths.naf, dtype=str).set_index("APE")["APE_LIBELLE"]
    todo = select_ambiguous(dem, options.sirens)
    if todo.empty:
        print("Aucun demandeur ambigu à traiter.")
        return 0

    try:
        classifier = classifier or make_classifier(options.model)
    except GeminiIndisponible as e:
        print(f"Arrêt : {str(e).rstrip('.')}. Les cas restent « non déterminé ».")
        return 1
    if researcher is None and (options.web or options.refresh_web):
        researcher = make_researcher(options.web_provider, options.web_sources)

    history = _history_by_siren(paths.cache)
    web_profiles = researcher.latest if researcher else load_web_latest()
    entries = {d["SIREN_DEM"]: build_input(d, naf, verified_sources(d["SIREN_DEM"], web_profiles, d["DENOM"]))
               for _, d in todo.iterrows()}
    if not options.force and not options.refresh_web:
        todo = _skip_up_to_date(todo, entries, history, classifier, researcher, web_profiles)
    todo = todo.head(options.limit)

    if researcher and not todo.empty:
        try:
            todo = _research_sources(todo, entries, naf, researcher, options.refresh_web)
        except WebResearchError as exc:
            print(f"Arrêt recherche : {str(exc).rstrip('.')}. Aucune nouvelle réponse LLM générée.")
            return 1
        if not options.force:
            todo = todo[~todo["SIREN_DEM"].map(lambda s: _cached(history, s, entries[s], classifier))]

    print(f"{len(todo)} demandeurs à soumettre à {classifier.model} ({VERSION_PROMPT})", flush=True)
    if todo.empty:
        return 0
    saved, failed = _ask_model(todo, entries, classifier, paths.cache)
    print(f"{saved} réponse(s) enregistrée(s). Revue : data/processed/revue_llm.csv ; "
          "aucune proposition appliquée automatiquement.")
    return 1 if failed else 0


# --- étapes ----------------------------------------------------------------------------------------

def _history_by_siren(cache: Path) -> dict[str, list[dict]]:
    by_siren: dict[str, list[dict]] = {}
    for record in load_history(cache):
        by_siren.setdefault(record["siren"], []).append(record)
    return by_siren


def _cached(history: dict, siren: str, entree: dict, classifier) -> bool:
    return bool(history.get(siren)) and cache_matches(
        history[siren][-1], entree, classifier.model, config_sha256=classifier.config_sha256)


def _skip_up_to_date(todo, entries, history, classifier, researcher, web_profiles) -> pd.DataFrame:
    """Écarte les réponses à jour et les recherches déjà faites sans source exploitable."""
    names = dict(zip(todo["SIREN_DEM"], todo["DENOM"]))
    done, negative_cached = set(), 0
    for siren, entree in entries.items():
        web_current = researcher is not None and researcher.cached_current(siren, str(names[siren]))
        no_source = (web_current and not entree["sources_web"]
                     and web_profiles.get(siren, {}).get("statut") == "aucune_source_verifiee")
        model_current = _cached(history, siren, entree, classifier)
        if no_source or (model_current and (researcher is None or web_current)):
            done.add(siren)
            negative_cached += int(bool(no_source))
    if negative_cached:
        print(f"{negative_cached} demandeur(s) déjà recherchés sans source exploitable : "
              "ignorés pour avancer dans le lot (--refresh-web pour les retenter).", flush=True)
    return todo[~todo["SIREN_DEM"].isin(done)]


def _research_sources(todo, entries, naf, researcher, refresh_web: bool) -> pd.DataFrame:
    """Met à jour les entrées avec les sources vérifiées ; retire les demandeurs sans source."""
    no_sources = set()
    for _, d in todo.iterrows():
        siren = d["SIREN_DEM"]
        cached = not refresh_web and researcher.cached_current(siren, str(d["DENOM"]))
        print(f"  recherche web pour {siren} ({'cache' if cached else 'nouvelle recherche'}) ...", flush=True)
        web_record = researcher.research(siren, str(d["DENOM"]), force=refresh_web)
        sources = verified_sources(siren, researcher.latest, d["DENOM"])
        entries[siren] = build_input(d, naf, sources)
        print(f"  {web_record['statut']} : {len(sources)} extrait(s) d'activité retenu(s)", flush=True)
        if not sources:
            no_sources.add(siren)
    if no_sources:
        print(f"{len(no_sources)} demandeur(s) sans source vérifiable : aucune nouvelle proposition demandée.")
    return todo[~todo["SIREN_DEM"].isin(no_sources)]


def _ask_model(todo, entries, classifier, cache: Path) -> tuple[int, bool]:
    """Un appel par demandeur ; arrêt au premier échec du service (aucune réponse inventée)."""
    saved = 0
    for _, d in todo.iterrows():
        entree = entries[d["SIREN_DEM"]]
        try:
            t0 = time.time()
            resp = classifier.ask(entree)
        except GeminiIndisponible as e:
            print(f"Arrêt : {str(e).rstrip('.')}. {saved} réponses enregistrées, le reste reste « non déterminé ».")
            return saved, True
        raw = resp.get("message", {}).get("content", "")
        out = check_proposal(raw, entree)
        append_jsonl(cache, _record(d["SIREN_DEM"], classifier, entree, raw, out, resp, time.time() - t0))
        saved += 1
        print(f"  {saved}/{len(todo)} {str(d['DENOM'])[:40]:40s} -> {out['famille']} "
              f"[{out['statut_controle']}]", flush=True)
    return saved, False


def _record(siren: str, classifier, entree: dict, raw: str, out: dict, resp: dict, duration: float) -> dict:
    """Champs historiques conservés : l'identifiant de décision est l'empreinte de ce contenu."""
    return {"siren": siren, "modele": classifier.model, "entree": entree, "sortie_brute": raw,
            "famille": out["famille"], "justification": out["justification"], "preuves": out["preuves"],
            "statut_controle": out["statut_controle"], "motif_controle": out["motif_controle"],
            "version_prompt": VERSION_PROMPT, "prompt_sha256": PROMPT_SHA256,
            "confiance_annoncee": out["confiance"], "confiance": "basse",
            "regle_appliquee": "llm_proposition",
            "duree_s": round(duration, 1),
            "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": PROVIDER, "config_sha256": classifier.config_sha256,
            "parametres_modele": classifier.config, "usage_tokens": resp.get("usage", {})}
