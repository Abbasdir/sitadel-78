"""Étape 2b-LLM — Arbitrage des demandeurs « non déterminé » par un LLM local (Ollama, qwen2.5).

- Ne traite QUE les demandeurs que les règles laissent en non_determine.
- Entrée envoyée au modèle : dénomination (déjà masquée si à risque), catégorie juridique, APE au permis,
  activité principale actuelle (Sirène). Rien d'autre, aucun appel web.
- Sortie demandée : JSON {famille, justification, confiance}. Quelle que soit la confiance annoncée
  par le modèle, la décision est enregistrée avec regle_appliquee="llm" et confiance="basse".
- Cache : data/cache/ollama_decisions.jsonl (entrée + sortie brute, pour audit et reprise).
- Si Ollama ne répond pas : arrêt propre, les cas restent non_determine.

Usage : python src/step2b_llm.py [--model qwen2.5] [--limit N] [--host http://localhost:11434]
Puis la réinjection est automatique (relance de step2b_classify).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache" / "ollama_decisions.jsonl"
NAF = ROOT / "data" / "ref" / "naf_insee.csv"

FAMILLES = ["bailleur_social", "medico_social_sante", "collectivite_public", "association_ess",
            "promoteur_prive", "sci_fonciere", "entreprise_autre", "non_determine"]

SYSTEM = """Tu classes des personnes morales qui ont déposé un permis de construire dans les Yvelines.
Familles (choisis exactement une valeur) :
- bailleur_social : organisme HLM (ESH, OPH, coopérative HLM), SEM de logement social, foncière solidaire.
- medico_social_sante : gestionnaire d'EHPAD, IME, ESAT, foyers, crèches, cliniques, hôpitaux.
- collectivite_public : État, collectivités, établissements publics, SEM/SPL d'aménagement.
- association_ess : association, fondation, coopérative ou entreprise de l'ESS (hors cas ci-dessus).
- promoteur_prive : promoteur immobilier, société de programme, marchand de biens, constructeur.
- sci_fonciere : société qui détient ou loue de l'immobilier (SCI, foncière, investisseur).
- entreprise_autre : entreprise qui construit pour sa propre activité (commerce, industrie, services).
- non_determine : les informations ne suffisent pas.
Règles : n'utilise que les champs fournis ; n'invente rien ; si deux familles restent plausibles,
réponds non_determine. Ne cite jamais de nom de personne physique.
Réponds en JSON : {"famille": ..., "justification": "1 phrase en français", "confiance": "moyenne"|"basse"}."""

SCHEMA = {
    "type": "object",
    "properties": {
        "famille": {"type": "string", "enum": FAMILLES},
        "justification": {"type": "string"},
        "confiance": {"type": "string", "enum": ["moyenne", "basse"]},
    },
    "required": ["famille", "justification", "confiance"],
}


class OllamaIndisponible(Exception):
    pass


def resolve_model(host: str, wanted: str) -> str:
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaIndisponible(f"Ollama ne répond pas sur {host} ({type(e).__name__})") from e
    names = [m["name"] for m in r.json().get("models", [])]
    for n in names:
        if n == wanted or n.split(":")[0] == wanted:
            return n
    raise OllamaIndisponible(f"modèle « {wanted} » absent (disponibles : {', '.join(names) or 'aucun'}) "
                             f"— faire `ollama pull {wanted}`")


def ask(host: str, model: str, entree: dict) -> dict:
    payload = {
        "model": model,
        "stream": False,
        "format": SCHEMA,  # sortie structurée (Ollama >= 0.5) ; JSON validé ci-dessous de toute façon
        "options": {"temperature": 0, "seed": 42},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": json.dumps(entree, ensure_ascii=False)}],
    }
    try:
        r = requests.post(f"{host}/api/chat", json=payload, timeout=180)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaIndisponible(f"appel Ollama échoué ({type(e).__name__})") from e
    return r.json()


def parse(raw: str) -> dict:
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return {"famille": "non_determine", "justification": "sortie LLM non JSON", "confiance": "basse"}
    fam = out.get("famille")
    if fam not in FAMILLES:
        return {"famille": "non_determine", "justification": f"famille hors liste : {fam!r}",
                "confiance": "basse"}
    return {"famille": fam, "justification": str(out.get("justification", ""))[:400],
            "confiance": out.get("confiance")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen2.5")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    dem = pd.read_csv(P / "demandeurs_classes.csv", dtype=str)
    naf = pd.read_csv(NAF, dtype=str).set_index("APE")["APE_LIBELLE"]
    # Après une 1re réinjection, les cas tranchés par le LLM ne sont plus non_determine :
    # on repart de la décision des règles (regle_initiale) pour garder le même périmètre.
    regle0 = dem["regle_initiale"] if "regle_initiale" in dem else dem["regle_appliquee"]
    todo = dem[dem["famille"].eq("non_determine") | regle0.isin(["AMBIGU", "AUCUN"])]

    done = set()
    if CACHE.exists():
        done = {json.loads(line)["siren"] for line in CACHE.read_text(encoding="utf-8").splitlines()}
    todo = todo[~todo["SIREN_DEM"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"{len(todo)} demandeurs non déterminés à soumettre ({len(done)} déjà en cache)")
    if todo.empty:
        return 0

    try:
        model = resolve_model(args.host, args.model)
    except OllamaIndisponible as e:
        print(f"Arrêt : {e}. Les cas restent « non déterminé ».")
        return 0

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with CACHE.open("a", encoding="utf-8") as f:
        for _, d in todo.iterrows():
            d = d.where(d.notna(), None)
            act = d["activite_principale"]
            entree = {
                "denomination": d["DENOM"],  # déjà masquée si elle peut contenir un nom de personne
                "categorie_juridique": f'{d["CJ"]} {d["CJ_LIBELLE"] or ""}'.strip(),
                "code_ape_au_permis": f'{d["APE"]} {d["APE_LIBELLE"] or ""}'.strip(),
                "activite_principale_siege": f'{act} {naf.get(act, "")}'.strip() if act else None,
            }
            try:
                t0 = time.time()
                resp = ask(args.host, model, entree)
            except OllamaIndisponible as e:
                print(f"Arrêt : {e}. {n} réponses enregistrées, le reste reste « non déterminé ».")
                break
            raw = resp.get("message", {}).get("content", "")
            out = parse(raw)
            rec = {"siren": d["SIREN_DEM"], "modele": model, "entree": entree, "sortie_brute": raw,
                   "famille": out["famille"], "justification": out["justification"],
                   "confiance_annoncee": out["confiance"], "confiance": "basse", "regle_appliquee": "llm",
                   "duree_s": round(time.time() - t0, 1),
                   "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            print(f"  {n}/{len(todo)} {str(d['DENOM'])[:40]:40s} -> {out['famille']}")

    if n:
        sys.path.insert(0, str(Path(__file__).parent))
        import step2b_classify  # réinjection dans demandeurs_classes.csv / pc_78_classes.csv
        return step2b_classify.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
