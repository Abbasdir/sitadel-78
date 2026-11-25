"""Preuves : identité par SIREN, sélection d'extraits d'activité et contrôle des citations du modèle.

Aucune page complète ni aucun nom de dirigeant n'est conservé : seuls de courts passages d'activité,
rattachés au SIREN par une page d'identité du même site, peuvent être transmis au modèle.
"""
from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .clients import web_page
from .config import APE_GENERIQUES, CACHE_WEB, FAMILLES, SOURCES_WEB_CONNUES
from .errors import WebResearchError, WebServiceError
from .prompt import CHAMPS_PREUVE
from .storage import append_jsonl, load_web_latest

VERSION = "web-v3"
PERSONAL = re.compile(r"pr[eé]sident|direct(?:eur|rice)|fondateur|dirigeant|biograph|\bCEO\b|\bPDG\b|"
                      r"\b(?:Mme|Monsieur|Madame|Mr|Mrs)\b|vie priv[eé]e|donn[eé]es personnelles|"
                      r"privacy|cookies|@|r[eé]daction|publication|h[eé]bergeur|contact", re.I)
DISALLOWED_HOSTS = {"pappers.fr", "societe.com", "linkedin.com", "facebook.com", "instagram.com",
                    "verif.com", "infogreffe.fr", "origami-entreprises.fr", "tavily.com"}
LEGAL_URL = re.compile(r"mention|legal|impressum|privacy|privacynotice|donnees.?personnelles|cookies|"
                       r"terms(?:[-_/]|$)|conditions[-_](?:generales|utilisation)|(?:^|/)cg[uv](?:[./]|$)", re.I)
SECTOR = re.compile(r"\b(?:a[eé]ronaut|aviation|aerospace|industri|d[eé]fense|cyber|logiciel|informatique|"
                    r"restaura|aliment|agric|transport|m[eé]dic|sant[eé]|h[oô]pit|cr[eè]che|handicap|"
                    r"promotion immobili|logement|immobilier|association|coop[eé]rativ|collectivit|"
                    r"banque|assurance|courtier|cr[eé]dit|enseignement|formation|[eé]nergie|"
                    r"construction|bailleur|HLM|fondation|mutuelle|coop[eé]rativ|action sociale|"
                    r"commune|municipal|[eé]tablissement public|[eé]lectronique|electronics)", re.I)
ACTIVITY_STATEMENT = re.compile(
    r"\b(?:est|sont|sommes|exerce\w*|sp[eé]cialis\w*|fabriqu\w*|con[çc]oi\w*|con[çc]ev\w*|"
    r"d[eé]velopp\w*|construi\w*|commercialis\w*|exploit\w*|g[eè]re\w*|g[eé]r(?:ons|ant)|"
    r"propos\w*|offr\w*|assur\w*|r[eé]alis\w*|accompagn\w*|intervien\w*|op[eè]r\w*|"
    r"is|are|designs?|manufactures?|develops?|operates?|provides?|speciali[sz]\w*|builds?|manages?|offers?)\b", re.I)
BOILERPLATE = re.compile(
    r"en savoir|read more|learn more|voir (?:aussi|plus)|actionnaires?|shareholders?|"
    r"(?:ce|notre) (?:site|portail)\b|this (?:website|site)\b|plan du site|horaires?|"
    r"conform[eé]ment [aà] l.article|droit d.acc[eè]s|opening hours|last updated", re.I)
# Clauses de statuts, de capital ou de gouvernance : elles décrivent la société, pas son activité.
# Suite « Prénom Nom » (deux mots à majuscule) hors début de phrase : nom probable d'une personne
# physique. Volontairement large : mieux vaut perdre un extrait que publier un nom.
PERSON_NAME = re.compile(r"[A-ZÀ-Ý][a-zà-ÿ]+(?:-[A-ZÀ-Ý][a-zà-ÿ]+)?\s+[A-ZÀ-Ý][a-zà-ÿ]{2,}")
STATUTORY = re.compile(
    r"cessions? d.actions|agr[eé]ment|collectivit[eé] des associ[eé]s|\bassoci[eé]s?\b|"
    r"assembl[eé]e g[eé]n[eé]rale|capital social|\bstatuts\b|droit de vote", re.I)
RELATED_SECTION = re.compile(
    r"^(?:#{1,6}\s*)?(?:voir aussi|entreprises similaires|autres entreprises|autres professionnels|"
    r"[aà] proximit[eé]|vous aimerez|sur le m[eê]me sujet|related companies|you may also like)\b", re.I)
FAMILY_SIGNALS = {
    "bailleur_social": r"HLM|bailleur social|logements? sociaux|habitat social",
    "medico_social_sante": r"m[eé]dico.social|sant[eé]|soins|h[oô]pit|hospital|EHPAD|handicap|action sociale|cr[eè]che",
    "collectivite_public": r"collectivit|commune|municipal|d[eé]partement|[eé]tablissement public|soci[eé]t[eé] publique|[eÉ]tat\b",
    "association_ess": r"association|fondation|mutuelle|coop[eé]rativ|[eé]conomie sociale|solidaire",
    "promoteur_prive": r"promot(?:ion|eur) immobili|marchand de biens|SCCV|constructeur.{0,15}maisons|construction.{0,15}logements",
    "sci_fonciere": r"immobili|fonci[eè]r|location.{0,15}(?:biens|logements|locaux)",
    "entreprise_autre": r"a[eé]ronaut|aviation|aerospace|industri|d[eé]fense|cyber|logiciel|informatique|"
                        r"restaura|aliment|agric|transport|banque|assurance|courtier|cr[eé]dit|"
                        r"enseignement|formation|[eé]nergie|commerce",
}


# --- URL et identité -------------------------------------------------------------------------------

def public_url(value: str) -> bool:
    """Adresse http(s) d'un hôte public ; refuse localhost, réseaux privés et identifiants intégrés."""
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value.strip())
        host = url.hostname or ""
        if (url.scheme not in {"https", "http"} or not host or url.username
                or host == "localhost" or host.endswith((".localhost", ".local"))):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host
    except ValueError:
        return False


def same_site(left: str, right: str) -> bool:
    a = (urlsplit(left).hostname or "").removeprefix("www.")
    b = (urlsplit(right).hostname or "").removeprefix("www.")
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


def contains_siren(text: str, siren: str) -> bool:
    pattern = r"(?<!\d)" + r"[\s. -]*".join(re.escape(x) for x in siren) + r"(?!\d)"
    return bool(re.search(pattern, text))


def legal_page(url: str) -> bool:
    return bool(LEGAL_URL.search(urlsplit(url).path))


def personal_page(url: str) -> bool:
    return bool(re.search(r"(?:^|/)(?:dirigeants?|personnes?|persons?|people|officers?|leadership|"
                          r"biograph(?:y|ie)|founders?|team|(?:l[-_])?equipe)(?:/|$)",
                          unquote(urlsplit(url).path), re.I))


def usable_activity_url(url: str, siren: str) -> bool:
    """Écarter les bulletins multi-sociétés et les fiches d'un autre SIREN/SIRET."""
    path = unquote(urlsplit(url).path)
    if path.lower().endswith(".pdf") or personal_page(url):
        return False
    identifiers = {number[:9] for number in re.findall(r"(?<!\d)(\d{14}|\d{9})(?!\d)", path)}
    return not identifiers or identifiers == {siren}


def disallowed_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in DISALLOWED_HOSTS)


# --- Extraits d'activité ---------------------------------------------------------------------------

def without_name(text: str, denomination: str | None) -> str:
    """Retire les mots de la dénomination : « IMMOBILIERS » dans un nom ne décrit pas une activité."""
    for word in re.findall(r"[^\W\d_]{4,}", denomination if isinstance(denomination, str) else ""):
        text = re.sub(r"\b" + re.escape(word) + r"\b", " ", text, flags=re.I)
    return text


def mentions_person(text: str) -> bool:
    """Vrai si le passage contient un probable « Prénom Nom » ailleurs qu'en début de phrase."""
    for match in PERSON_NAME.finditer(text):
        before = text[:match.start()].rstrip(" *_\"«(")
        if before and before[-1] not in ".!?":
            return True
    return False


def informative_excerpt(text: str, denomination: str | None = None) -> bool:
    """Un passage doit décrire une activité précise ; un mot-clé, un titre, une clause de statuts ou
    le seul nom de la société ne suffisent pas."""
    return (isinstance(text, str) and 30 <= len(text) <= 350
            and "|" not in text and not BOILERPLATE.search(text) and not PERSONAL.search(text)
            and not STATUTORY.search(text) and not mentions_person(without_name(text, denomination))
            and bool(SECTOR.search(without_name(text, denomination))) and bool(ACTIVITY_STATEMENT.search(text)))


def family_supported_by_excerpt(family: str, text: str) -> bool:
    """Filtre de cohérence minimal ; ce contrôle ne remplace pas une revue métier."""
    pattern = FAMILY_SIGNALS.get(family)
    return bool(pattern and re.search(r"\b(?:" + pattern + ")", text, re.I))


def activity_excerpts(content: str, denomination: str | None = None) -> list[str]:
    """Courts passages d'activité seulement ; ni page complète, ni mentions de dirigeants."""
    passages = []
    for block in re.split(r"\n+|(?<=[.!?])\s+", content):
        if RELATED_SECTION.search(block.strip()):
            break
        if re.match(r"\s*(?:#{1,6}\s|\d+[.)]?\s)", block):
            continue
        block = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", block)
        block = re.sub(r"\s+", " ", block).strip(" #*-|")
        if informative_excerpt(block, denomination) and block not in passages:
            passages.append(block)
        if len(passages) == 2:
            break
    return passages


def read_seeds(path: Path = SOURCES_WEB_CONNUES) -> dict[str, list[dict]]:
    """URL connues par SIREN (`SIREN_DEM,url,url_identite`), utilisables sans clé de recherche."""
    if not path.exists():
        return {}
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            siren = row.get("SIREN_DEM", "").strip()
            url, identity_url = row.get("url", "").strip(), row.get("url_identite", "").strip()
            if (re.fullmatch(r"\d{9}", siren) and public_url(url)
                    and (not identity_url or (public_url(identity_url) and same_site(url, identity_url)))):
                result.setdefault(siren, []).append({"url": url, "url_identite": identity_url})
    return result


def verified_sources(siren: str, records: dict[str, dict] | None = None,
                     denomination: str | None = None) -> list[dict]:
    """Sources en cache encore recevables : même SIREN, identité vérifiée, extrait informatif."""
    if not re.fullmatch(r"\d{9}", str(siren)):
        return []
    record = (load_web_latest() if records is None else records).get(siren, {})
    result = []
    sources = record.get("sources", [])
    for source in sources if isinstance(sources, list) else []:
        if (isinstance(source, dict) and isinstance(source.get("id"), str) and source["id"]
                and source.get("siren") == siren and source.get("identite_verifiee") is True
                and public_url(source.get("url", "")) and public_url(source.get("url_identite", ""))
                and same_site(source["url"], source["url_identite"])
                and not personal_page(source["url_identite"])
                and not legal_page(source["url"]) and usable_activity_url(source["url"], siren)
                and informative_excerpt(source.get("extrait"), denomination)):
            result.append(source)
    return result


# --- Contrôle des citations du modèle --------------------------------------------------------------

def check_proposal(raw: str, entree: dict) -> dict:
    """Vérifie le format et les citations, sans prétendre prouver la vérité du classement."""
    result = {"famille": "non_determine", "justification": "", "preuves": [],
              "confiance": "basse", "statut_controle": "rejetee", "motif_controle": ""}

    def reject(reason):
        return {**result, "motif_controle": reason}
    try:
        out = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return reject("Réponse non JSON.")
    if not isinstance(out, dict):
        return reject("La réponse doit être un objet JSON.")
    if out.get("famille") not in FAMILLES:
        return reject("Famille absente ou hors de la liste autorisée.")
    result["famille"] = out["famille"]
    justification = out.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        return reject("Justification absente ou invalide.")
    result["justification"] = justification.strip()[:400]
    if not isinstance(out.get("confiance"), str) or out["confiance"] not in {"basse", "moyenne"}:
        return reject("Confiance absente ou invalide.")
    result["confiance"] = out["confiance"]
    preuves = out.get("preuves")
    if not isinstance(preuves, list):
        return reject("Liste de preuves absente ou invalide.")
    web_cited = False
    for preuve in preuves:
        if not isinstance(preuve, dict) or preuve.get("champ") not in CHAMPS_PREUVE:
            return reject("Champ de preuve non autorisé.")
        value = preuve.get("valeur")
        if preuve["champ"] == "sources_web":
            sources = verified_sources(entree.get("siren", ""),
                                       {entree.get("siren", ""): {"sources": entree.get("sources_web", [])}},
                                       entree.get("denomination"))
            source = next((s for s in sources if s.get("id") == preuve.get("source_id")), None)
            if source is None or not isinstance(value, str) or value != source["extrait"]:
                return reject("Preuve web invalide : source non vérifiée, autre SIREN ou extrait modifié.")
            if result["famille"] != "non_determine" and not family_supported_by_excerpt(result["famille"], value):
                return reject("L'extrait web cité ne justifie pas la famille proposée.")
            web_cited = True
            continue
        if not isinstance(value, str) or not value.strip() or value != entree.get(preuve["champ"]):
            return reject("Une preuve ne recopie pas exactement une valeur fournie.")
    result["preuves"] = preuves
    if result["famille"] == "non_determine":
        return {**result, "statut_controle": "abstention", "motif_controle": "Le modèle s'abstient."}
    if not (web_cited or _discriminating_citation(preuves)):
        return reject("Preuves insuffisantes : nom, forme commerciale ou activité générique seulement.")
    return {**result, "statut_controle": "a_verifier",
            "motif_controle": "Citations contrôlées ; classement métier à vérifier manuellement."}


def _discriminating_citation(preuves: list[dict]) -> bool:
    discriminant = False
    for preuve in preuves:
        value, champ = preuve["valeur"], preuve["champ"]
        if champ in {"code_ape_au_permis", "activite_principale_siege"}:
            code = re.match(r"\d{2}\.\d{2}[A-Z]\b", value)
            discriminant |= bool(code and code.group() not in APE_GENERIQUES)
        elif champ == "categorie_juridique":
            code = value.split()[0]
            # Ces statuts peuvent être discriminants ; une forme commerciale générique ne l'est pas.
            discriminant |= code.startswith(("4", "7", "9")) or code in {
                "5546", "5646", "5547", "5647", "6541", "6540", "6539", "8210"}
    return discriminant


# --- Recherche de sources --------------------------------------------------------------------------

class WebResearch:
    """Recherche d'extraits d'activité dont l'identité est prouvée par le SIREN.

    Avec un client de recherche (Tavily) : découverte puis extraction des pages par ce client.
    Sans client : lecture HTML directe des seules URL connues (`data/ref/sources_web.csv`).
    """

    def __init__(self, search_client=None, *, key_name: str = "TAVILY_API_KEY", cache: Path = CACHE_WEB,
                 seeds: Path = SOURCES_WEB_CONNUES, pause: float = 2, max_pages: int = 3, session=None):
        self.client = search_client
        self.key_name = key_name
        self.cache = cache
        self.seeds = read_seeds(seeds)
        self.pause = pause
        self.max_pages = max_pages
        self.reader = web_page.HtmlPageReader(session)
        self.latest = load_web_latest(cache)
        self.pages = {}
        self.last_request = 0.0

    @property
    def provider(self) -> str:
        return "tavily" if self.client else "url_connue"

    def signature(self, siren: str, denomination: str) -> str:
        return hashlib.sha256(json.dumps([VERSION, self.provider, denomination, self.seeds.get(siren, [])],
                                         sort_keys=True).encode()).hexdigest()

    def cached_current(self, siren: str, denomination: str) -> bool:
        return self.latest.get(siren, {}).get("signature") == self.signature(siren, denomination)

    def research(self, siren: str, denomination: str, *, force: bool = False) -> dict:
        started = time.monotonic()
        if not re.fullmatch(r"\d{9}", siren):
            raise WebResearchError("SIREN invalide.")
        signature = self.signature(siren, denomination)
        cached = self.latest.get(siren)
        if not force and cached and cached.get("signature") == signature:
            return cached
        seeds = self.seeds.get(siren, [])
        if not seeds and not self.client:
            raise WebResearchError(f"{self.key_name} absente et aucune URL connue pour ce SIREN. "
                                   "Renseigner .env ou data/ref/sources_web.csv.")
        candidates = list(seeds) + self._discover(siren, denomination, bool(seeds))
        sources, visited, observations = self._collect(siren, denomination, candidates)
        record = {"siren": siren, "signature": signature, "version_recherche": VERSION,
                  "statut": "sources_trouvees" if sources else "aucune_source_verifiee",
                  "sources": sources, "pages_consultees": visited,
                  "observations": observations,
                  "provider": self.provider,
                  "duree_s": round(time.monotonic() - started, 2),
                  "horodatage": _now()}
        append_jsonl(self.cache, record)
        self.latest[siren] = record
        return record

    # -- étapes de la recherche --

    def _discover(self, siren: str, denomination: str, has_seeds: bool) -> list[dict]:
        """Pages candidates proposées par le moteur ; l'identité sera contrôlée ensuite."""
        if not self.client:
            return []
        name = denomination if "masqu" not in denomination.lower() else ""
        results = self._search(f'"{siren}" {name} activite site officiel')
        if name and not has_seeds:
            # Les pages d'activité citent rarement le SIREN ; l'identité sera contrôlée après découverte.
            results += self._search(f'"{name}" entreprise activites site officiel')
        results = sorted(results, key=lambda result: legal_page(result.get("url", ""))
                         if isinstance(result, dict) else True)
        return [{"url": result.get("url", ""), "url_identite": ""} for result in results
                if isinstance(result, dict) and public_url(result.get("url", ""))
                and usable_activity_url(result.get("url", ""), siren) and not disallowed_host(result.get("url", ""))]

    def _collect(self, siren: str, denomination: str, candidates: list[dict]) -> tuple[list, list, list]:
        sources, visited, observations = [], [], []
        for candidate in candidates:
            if len(visited) >= self.max_pages:
                break
            url = candidate["url"]
            if personal_page(url):
                observations.append({"url": "", "resultat": "Page de personne physique exclue du périmètre."})
                continue
            if not usable_activity_url(url, siren):
                observations.append({"url": url, "resultat": "Document collectif ou fiche d'un autre SIREN/SIRET : activité non attribuable."})
                continue
            if url in visited:
                continue
            visited.append(url)
            try:
                page = self._fetch(url)
                identity_url = self._identity_url(siren, url, page, candidate["url_identite"], visited)
                if not identity_url:
                    observations.append({"url": url, "resultat": "SIREN non retrouvé sur le site."})
                    continue
                # Une politique de confidentialité peut prouver le SIREN, pas le secteur d'activité.
                excerpts = [] if legal_page(url) else activity_excerpts(page["content"], denomination)
                sources += [_source(siren, url, identity_url, excerpt) for excerpt in excerpts]
                observations.append({"url": url, "resultat": "Activité extraite." if excerpts else
                                     "SIREN retrouvé, mais aucune description précise d'activité retenue (titres, rubriques et mentions légales exclus)."})
            except WebServiceError:
                raise
            except WebResearchError as exc:
                observations.append({"url": url, "resultat": str(exc)})
        return sources, visited, observations

    def _identity_url(self, siren: str, url: str, page: dict, known_identity: str, visited: list) -> str:
        """La page elle-même, ou une page légale du même site, doit contenir le SIREN."""
        if contains_siren(page["identity_text"], siren):
            return url
        legal_urls = [known_identity] if known_identity else []
        legal_urls += [link for link in page.get("links", []) if isinstance(link, str)
                       and public_url(link) and same_site(url, link) and legal_page(link)]
        for legal_url in dict.fromkeys(legal_urls):
            if len(visited) >= self.max_pages:
                break
            if legal_url not in visited:
                visited.append(legal_url)
            if contains_siren(self._fetch(legal_url)["identity_text"], siren):
                return legal_url
        return ""

    # -- accès réseau, espacés d'au moins `pause` secondes --

    def _wait(self) -> None:
        wait = self.pause - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()

    def _search(self, query: str) -> list:
        self._wait()
        return self.client.search(query, max_results=3)

    def _fetch(self, url: str) -> dict:
        if not public_url(url):
            raise WebResearchError("URL publique invalide.")
        if url in self.pages:
            return self.pages[url]
        if self.client:
            self._wait()
            data = self.client.extract(url)
            page = {"url": url, "content": str(data.get("content", "")),
                    "identity_text": str(data.get("content", "")), "links": data.get("links", [])}
        else:
            web_page.assert_public_destination(url)
            self._wait()
            page = {"url": url, **self.reader.read(url)}
        self.pages[url] = page
        return page


def _source(siren: str, url: str, identity_url: str, excerpt: str) -> dict:
    source_id = "web_" + hashlib.sha256((url + "\n" + excerpt).encode()).hexdigest()[:12]
    return {"id": source_id, "siren": siren, "url": url, "url_identite": identity_url,
            "identite_verifiee": True, "extrait": excerpt, "consulte_le": _now()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
