"""Contrôle qualité du classement : 15 demandeurs tirés au hasard par famille (graine fixe).

Sortie : data/processed/echantillon_controle.csv, avec une colonne vide « verdict_manuel » à remplir
à la main (ok / faux:<famille attendue> / ?) en ouvrant SIREN_URL (fiche publique annuaire-entreprises).

Usage : python src/qc_echantillon.py [--n 15] [--seed 42]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    dem = pd.read_csv(P / "demandeurs_classes.csv", dtype=str)
    ech = pd.concat(g.sample(n=min(args.n, len(g)), random_state=args.seed)
                    for _, g in dem.groupby("famille"))
    ech = ech.rename(columns={"SOURCE_SIREN_URL": "SIREN_URL"})
    ech["verdict_manuel"] = ""
    cols = ["famille", "sous_famille", "confiance", "regle_appliquee", "signal", "SIREN_DEM", "DENOM",
            "CJ", "CJ_LIBELLE", "APE", "APE_LIBELLE", "activite_principale", "n_pc", "SIREN_URL",
            "verdict_manuel"]
    ech[cols].to_csv(P / "echantillon_controle.csv", index=False, encoding="utf-8")
    print(f"{len(ech)} lignes -> data/processed/echantillon_controle.csv (graine {args.seed})")
    print(ech["famille"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
