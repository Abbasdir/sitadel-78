"""Commandes du pipeline Sitadel 78.

  ingest    téléchargement Sitadel (78) et filtrage des PC de personnes morales
  enrich    enrichissement des SIREN (API Recherche d'entreprises, cache + reprise)
  classify  règles métier + application des seules validations manuelles de l'agent
  analyze   indicateurs (data/processed/patterns, docs/step3_resume.md)
  export    CSV final et dictionnaire des colonnes
  refresh   classify + analyze + export, sans appel réseau
  agent     propositions sourcées sur les cas ambigus, puis refresh si tout s'est bien passé
  sample    échantillon de contrôle qualité des règles (15 par famille)
  evaluate  taux d'erreur et d'abstention d'après les verdicts humains (docs/evaluation.md)
  pipeline  ingest + enrich + refresh (sans agent)
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

from . import analyze, classify, enrich, evaluate, export, ingest, review
from .agent import AgentOptions, run_agent
from .config import DEMANDEURS, ECHANTILLON, SOURCES_WEB_CONNUES
from .storage import read_csv_rows


def run_classify() -> str:
    pc, enr, cj, naf = classify.load_inputs()
    demandeurs = classify.classify_demandeurs(pc, enr, cj, naf)
    demandeurs = review.apply_reviews(demandeurs, naf)
    permits = classify.merge_permits(pc, demandeurs)
    classify.write_outputs(demandeurs, permits)
    return classify.summary(demandeurs, permits)


def refresh(*, quiet: bool = False) -> int:
    """Classement, analyses et exports à partir des fichiers locaux (aucun appel réseau)."""
    with contextlib.redirect_stdout(io.StringIO()) if quiet else contextlib.nullcontext():
        summary = run_classify()
        analyze.run()  # résumé détaillé dans docs/step3_resume.md : terminal gardé lisible
        report = export.run()
    if not quiet:
        print(summary)
        print(report)
    return 0


def cmd_agent(args) -> int:
    options = AgentOptions(limit=args.limit, sirens=args.siren or [], force=args.force, web=args.web,
                           refresh_web=args.refresh_web, web_provider=args.web_provider,
                           web_sources=args.web_sources, model=args.model)
    code = run_agent(options)
    if code != 0:
        print("Classement, analyses et exports non actualisés. "
              "Après correction, relancer l'agent ou `sitadel refresh`.")
        return code
    refresh(quiet=True)
    print("Revue, classement, analyses et CSV final actualisés.")
    return 0


def cmd_sample(args) -> int:
    filled = [row for row in read_csv_rows(ECHANTILLON) if row.get("verdict_manuel", "").strip()]
    if filled and not args.force:
        print(f"{ECHANTILLON.name} contient déjà {len(filled)} verdict(s) manuel(s) : fichier conservé "
              "(--force pour le régénérer).")
        return 1
    ech = review.write_control_sample(pd.read_csv(DEMANDEURS, dtype=str), n=args.n, seed=args.seed)
    print(f"{len(ech)} lignes -> data/processed/{ECHANTILLON.name} (graine {args.seed})")
    print(ech["famille"].value_counts().to_string())
    return 0


def cmd_pipeline(args) -> int:
    print(json.dumps(ingest.run(), ensure_ascii=False, indent=2))
    print("SIREN trouvés :", enrich.run())
    return refresh()


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("doit être strictement positif")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sitadel", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="télécharger et filtrer Sitadel")
    p.add_argument("--millesime", help="ex. 2026-10 (défaut : le plus récent)")
    p.add_argument("--force", action="store_true", help="retélécharger les fichiers présents")
    p.set_defaults(func=lambda a: print(json.dumps(ingest.run(a.millesime, a.force), ensure_ascii=False, indent=2)))

    p = sub.add_parser("enrich", help="enrichir les SIREN (cache + reprise)")
    p.set_defaults(func=lambda a: print("SIREN trouvés :", enrich.run()))

    p = sub.add_parser("classify", help="règles métier + validations manuelles")
    p.set_defaults(func=lambda a: print(run_classify()))

    p = sub.add_parser("analyze", help="indicateurs et résumé Markdown")
    p.set_defaults(func=lambda a: print(analyze.run()))

    p = sub.add_parser("export", help="CSV final et dictionnaire")
    p.set_defaults(func=lambda a: print(export.run()))

    p = sub.add_parser("refresh", help="classify + analyze + export, sans réseau")
    p.set_defaults(func=lambda a: refresh())

    p = sub.add_parser("agent", help="propositions sourcées sur les demandeurs ambigus (Gemini, Tavily)")
    p.add_argument("--limit", type=positive_int, default=3, help="demandeurs maximum par exécution (défaut : 3)")
    p.add_argument("--siren", action="append", help="SIREN à traiter (option répétable)")
    p.add_argument("--force", action="store_true", help="refaire l'essai en conservant l'historique")
    p.add_argument("--web", action="store_true", help="rechercher des sources avant de proposer une famille")
    p.add_argument("--refresh-web", action="store_true", help="refaire les recherches web en conservant le cache")
    p.add_argument("--web-provider", choices=["tavily", "urls"], default="tavily",
                   help="tavily (défaut) ou urls : seulement les URL connues, sans clé de recherche")
    p.add_argument("--web-sources", type=Path, default=SOURCES_WEB_CONNUES,
                   help="CSV des URL connues par SIREN (SIREN_DEM,url,url_identite)")
    p.add_argument("--model", help="modèle Gemini Flash-Lite (défaut : GEMINI_MODEL ou gemini-3.5-flash-lite)")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("sample", help="échantillon de contrôle qualité des règles")
    p.add_argument("--n", type=positive_int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true", help="écraser un échantillon déjà annoté")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("evaluate", help="taux d'erreur et d'abstention d'après les verdicts humains")
    p.set_defaults(func=lambda a: print(evaluate.run()))

    p = sub.add_parser("pipeline", help="ingest + enrich + refresh (sans agent)")
    p.set_defaults(func=cmd_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
