"""Étape 3 — Patterns sur les permis de construire des personnes morales (Yvelines).

Entrées : data/processed/pc_78_classes.csv (1 ligne par permis, famille du demandeur)
          data/ref/communes_78.csv (code INSEE -> nom, geo.api.gouv.fr, 1 requête)
Sorties : data/processed/patterns/*.csv  +  docs/step3_resume.md

  1. medico_social_projets.csv        projets à caractère médico-social × famille du porteur
  2. portefeuille_sans_doc.csv        PC autorisés 2024-2026 sans ouverture de chantier, familles cibles
  3. constructeurs_recurrents.csv     demandeurs ≥ 3 PC : années actives, logements, m² créés
  4. extensions_asso_medsoc.csv       extensions portées par associations / acteurs médico-sociaux
  5. cas_fondation_mallet.csv         tous les permis de la Fondation Mallet

Chaque ligne garde NUM_DAU + SOURCE_URL (fichier Sitadel) + SIREN_URL (fiche entreprise publique).
Usage : python src/step3_patterns.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
OUT = P / "patterns"
MD = ROOT / "docs" / "step3_resume.md"

CIBLES = ["bailleur_social", "association_ess", "medico_social_sante"]
NUMS = ["NB_LGT_TOT_CREES", "NB_LGT_PRET_LOC_SOCIAL", "SURF_HAB_CREEE", "SURF_LOC_CREEE", "NB_CHAMBRES",
        "SURF_COM_CREEE", "SURF_BUR_CREEE", "SURF_IND_CREEE", "SURF_ENT_CREEE", "SURF_AGR_CREEE",
        "SURF_PUB_CREEE", "SURF_HEB_CREEE", "SURF_LOC_AVANT"]
ETAT = {"2": "autorisé", "4": "annulé", "5": "commencé", "6": "terminé"}
TSP = {"1": "transport", "2": "enseignement / recherche", "3": "santé", "4": "action sociale",
       "5": "ouvrage spécial", "6": "culture / loisir", "8": "plusieurs types"}
RESIDENCE = {"1": "personnes âgées", "2": "étudiants", "3": "tourisme", "4": "hôtelière à vocation sociale",
             "5": "sociale", "6": "personnes handicapées", "7": "autre", "8": "plusieurs"}
LIENS = ["NUM_DAU", "SOURCE_URL", "SOURCE_URL_LOCAUX", "SIREN_DEM", "SIREN_URL"]


def load() -> pd.DataFrame:
    pc = pd.read_csv(P / "pc_78_classes.csv", dtype=str)
    com = pd.read_csv(ROOT / "data" / "ref" / "communes_78.csv", dtype=str)
    pc = pc.merge(com.rename(columns={"code": "COMM", "nom": "COMMUNE"}), on="COMM", how="left")
    pc["COMMUNE"] = pc["COMMUNE"].fillna("code " + pc["COMM"] + " (commune fusionnée)")
    for c in NUMS:
        pc[c] = pd.to_numeric(pc[c], errors="coerce").fillna(0)
    for c in ("DATE_REELLE_AUTORISATION", "DATE_REELLE_DOC", "DATE_REELLE_DAACT"):
        pc[c] = pd.to_datetime(pc[c], errors="coerce")
    pc["ANNEE_AUT"] = pc["DATE_REELLE_AUTORISATION"].dt.year
    pc["ETAT"] = pc["ETAT_DAU"].map(ETAT)
    pc["SERVICE_PUBLIC"] = pc["TYPE_SERVICE_PUBLIC"].map(TSP)
    pc["RESIDENCE_LIB"] = pc["RESIDENCE"].map(RESIDENCE)
    pc["EXTENSION"] = pc["I_EXTENSION"].eq("true")
    pc["DELAI_DOC_J"] = (pc["DATE_REELLE_DOC"] - pc["DATE_REELLE_AUTORISATION"]).dt.days
    return pc


def flag(s: pd.Series) -> pd.Series:
    return s.eq("true")


def md_table(df: pd.DataFrame, n: int | None = None) -> str:
    df = (df.head(n) if n else df).astype(str)
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def p1_medico_social(pc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    # Signaux « projet médico-social » (projet, pas demandeur). RES_* n'existent que depuis mai 2022 ;
    # avant, le code RESIDENCE porte l'information. Chambres : hors hébergement hôtelier/touristique.
    sig = pd.DataFrame({
        "résidence personnes âgées": flag(pc["RES_PERS_AGEES"]) | pc["RESIDENCE"].eq("1"),
        "résidence handicapés": flag(pc["RES_HANDICAPES"]) | pc["RESIDENCE"].eq("6"),
        "résidence sociale": flag(pc["RES_SOCIALE"]) | pc["RESIDENCE"].isin(["4", "5"])
                             | flag(pc["RES_HOTEL_SOCIALE"]),
        "service public : santé": pc["TYPE_SERVICE_PUBLIC"].eq("3"),
        "service public : action sociale": pc["TYPE_SERVICE_PUBLIC"].eq("4"),
        "chambres (hors hôtel)": (pc["NB_CHAMBRES"] > 0) & (pc["SURF_HEB_CREEE"] <= 0)
                                 & ~flag(pc["RES_TOURISME"]) & ~pc["RESIDENCE"].isin(["2", "3"]),
    })
    m = sig.any(axis=1)
    proj = pc[m].copy()
    proj["SIGNAUX"] = sig[m].apply(lambda r: " ; ".join(r.index[r]), axis=1)
    cols = ["famille", "sous_famille", "DENOM_DEM", "COMMUNE", "ANNEE_AUT", "ETAT", "SIGNAUX", "EXTENSION",
            "NB_LGT_TOT_CREES", "NB_LGT_PRET_LOC_SOCIAL", "NB_CHAMBRES", "SURF_LOC_CREEE", "SURF_PUB_CREEE"] + LIENS
    proj[cols].sort_values(["famille", "ANNEE_AUT"]).to_csv(OUT / "medico_social_projets.csv", index=False)

    x = sig[m].join(pc.loc[m, "famille"]).melt(id_vars="famille", var_name="signal")
    ct = pd.crosstab(x.loc[x.value, "signal"], x.loc[x.value, "famille"], margins=True, margins_name="total")
    ct.to_csv(OUT / "medico_social_signal_x_famille.csv")
    parts = proj["famille"].value_counts()
    porteurs = (proj[proj.famille.isin(["bailleur_social", "medico_social_sante", "association_ess"])]
                .groupby(["famille", "DENOM_DEM"]).size().sort_values(ascending=False).head(8))
    txt = (f"**{m.sum()} permis** portent au moins un signal médico-social "
           f"({m.mean():.1%} des PC de personnes morales). Répartition par famille du porteur : "
           + ", ".join(f"{k} {v}" for k, v in parts.items()) + ".\n\n"
           + md_table(ct.reset_index().rename(columns={"signal": "signal \\ famille"})) + "\n\n"
           "Porteurs ciblés les plus présents : "
           + "; ".join(f"{d} ({n}, {f})" for (f, d), n in porteurs.items()) + ".")
    return proj, txt


def p2_portefeuille(pc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    # Délai médian autorisation -> ouverture de chantier observé (permis commencés), pour situer l'attente
    delai = pc[pc["DELAI_DOC_J"].between(0, 3 * 365)].groupby("famille")["DELAI_DOC_J"].median()
    m = pc["ANNEE_AUT"].between(2024, 2026) & pc["DATE_REELLE_DOC"].isna() & pc["ETAT_DAU"].eq("2") \
        & pc["famille"].isin(CIBLES)
    pf = pc[m].copy()
    ref = pd.Timestamp("2026-10-31")  # millésime 2026-10
    pf["ANCIENNETE_MOIS"] = ((ref - pf["DATE_REELLE_AUTORISATION"]).dt.days / 30.44).round(0).astype("Int64")
    pf["DELAI_MEDIAN_FAMILLE_MOIS"] = (pf["famille"].map(delai) / 30.44).round(1)
    pf["AU_DELA_DU_DELAI_MEDIAN"] = pf["ANCIENNETE_MOIS"] > pf["DELAI_MEDIAN_FAMILLE_MOIS"]
    cols = ["famille", "sous_famille", "DENOM_DEM", "COMMUNE", "DATE_REELLE_AUTORISATION", "ANCIENNETE_MOIS",
            "DELAI_MEDIAN_FAMILLE_MOIS", "AU_DELA_DU_DELAI_MEDIAN", "NATURE_PROJET_DECLAREE", "EXTENSION",
            "NB_LGT_TOT_CREES", "NB_LGT_PRET_LOC_SOCIAL", "SURF_LOC_CREEE", "SERVICE_PUBLIC", "RESIDENCE_LIB"] + LIENS
    pf = pf.sort_values(["famille", "DATE_REELLE_AUTORISATION"])
    pf[cols].to_csv(OUT / "portefeuille_sans_doc.csv", index=False)
    g = pf.groupby("famille").agg(permis=("NUM_DAU", "size"), demandeurs=("SIREN_DEM", "nunique"),
                                  logements=("NB_LGT_TOT_CREES", "sum"), dont_LLS=("NB_LGT_PRET_LOC_SOCIAL", "sum"),
                                  m2_locaux=("SURF_LOC_CREEE", "sum"),
                                  au_dela_delai_median=("AU_DELA_DU_DELAI_MEDIAN", "sum")).reset_index()
    g["delai_median_mois (référence)"] = g["famille"].map(delai / 30.44).round(1)
    top = (pf.groupby(["famille", "DENOM_DEM"]).size().sort_values(ascending=False).head(8))
    txt = (f"**{len(pf)} permis** autorisés 2024-2026 sans ouverture de chantier déclarée, portés par les "
           f"familles cibles :\n\n" + md_table(g.astype({c: int for c in ['logements', 'dont_LLS', 'm2_locaux']}))
           + "\n\nDemandeurs les plus présents : " + "; ".join(f"{d} ({n})" for (_, d), n in top.items()) + ".\n\n"
           "Attention : environ 15 % des ouvertures de chantier n'arrivent jamais dans Sitadel (note SDES). "
           "« Sans DOC » veut dire « non déclarée à ce jour », pas « projet bloqué ».")
    return pf, txt


def p3_recurrents(pc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    g = (pc.groupby(["famille", "SIREN_DEM"])
         .agg(DENOM_DEM=("DENOM_DEM", "last"), n_pc=("NUM_DAU", "nunique"),
              premiere_annee=("ANNEE_AUT", "min"), derniere_annee=("ANNEE_AUT", "max"),
              annees_actives=("ANNEE_AUT", "nunique"), communes=("COMM", "nunique"),
              logements_crees=("NB_LGT_TOT_CREES", "sum"), dont_LLS=("NB_LGT_PRET_LOC_SOCIAL", "sum"),
              m2_locaux_crees=("SURF_LOC_CREEE", "sum"), n_annules=("ETAT_DAU", lambda s: s.eq("4").sum()),
              SIREN_URL=("SIREN_URL", "first")).reset_index())
    rec = g[g["n_pc"] >= 3].sort_values(["famille", "n_pc"], ascending=[True, False])
    for c in ("premiere_annee", "derniere_annee", "logements_crees", "dont_LLS", "m2_locaux_crees"):
        rec[c] = rec[c].astype(int)
    rec.to_csv(OUT / "constructeurs_recurrents.csv", index=False)
    synth = rec.groupby("famille").agg(recurrents=("SIREN_DEM", "size"), permis=("n_pc", "sum")).reset_index()
    synth["part_des_permis_famille"] = (synth["permis"] / synth["famille"].map(pc["famille"].value_counts())).map("{:.0%}".format)
    parts = [f"**{len(rec)} demandeurs récurrents** (≥ 3 PC) :\n\n" + md_table(synth)]
    for f in CIBLES:
        t = rec[rec.famille == f].head(5)[["DENOM_DEM", "n_pc", "premiere_annee", "derniere_annee",
                                            "logements_crees", "dont_LLS", "m2_locaux_crees"]]
        parts.append(f"\n**Top {f}**\n\n" + md_table(t))
    return rec, "\n".join(parts)


def p4_extensions(pc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    m = pc["EXTENSION"] & pc["famille"].isin(["association_ess", "medico_social_sante"])
    ex = pc[m].copy()
    cols = ["famille", "sous_famille", "DENOM_DEM", "COMMUNE", "ANNEE_AUT", "ETAT", "SURF_LOC_AVANT",
            "SURF_LOC_CREEE", "SURF_HAB_CREEE", "NB_LGT_TOT_CREES", "NB_CHAMBRES", "SERVICE_PUBLIC",
            "RESIDENCE_LIB"] + LIENS
    ex.sort_values(["famille", "ANNEE_AUT"])[cols].to_csv(OUT / "extensions_asso_medsoc.csv", index=False)
    tot = pc[pc.famille.isin(["association_ess", "medico_social_sante"])].groupby("famille").size()
    g = ex.groupby(["famille", "sous_famille"]).agg(extensions=("NUM_DAU", "size"),
                                                    m2_crees=("SURF_LOC_CREEE", "sum")).reset_index()
    g["m2_crees"] = g["m2_crees"].astype(int)
    rec = ex.groupby("DENOM_DEM").size().sort_values(ascending=False)
    rec = rec[rec >= 2]
    txt = (f"**{len(ex)} extensions** portées par des associations/ESS ou des acteurs médico-sociaux "
           f"({len(ex) / tot.sum():.0%} de leurs PC ; "
           + ", ".join(f"{f} {ex.famille.eq(f).sum()}/{n}" for f, n in tot.items()) + ").\n\n"
           + md_table(g.sort_values("extensions", ascending=False), 10)
           + "\n\nAgrandissent plusieurs fois : " + ("; ".join(f"{d} ({n})" for d, n in rec.head(8).items()) or "aucun")
           + ".")
    return ex, txt


def p5_mallet(pc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    m = pc["DENOM_DEM"].str.contains("FONDATION MALLET", case=False, na=False)
    fm = pc[m].copy()
    dest = {"SURF_COM_CREEE": "commerce", "SURF_BUR_CREEE": "bureaux", "SURF_IND_CREEE": "industrie",
            "SURF_ENT_CREEE": "entrepôt", "SURF_AGR_CREEE": "agricole", "SURF_PUB_CREEE": "service public",
            "SURF_HEB_CREEE": "hébergement hôtelier", "SURF_HAB_CREEE": "habitation"}
    cols = ["COMMUNE", "DATE_REELLE_AUTORISATION", "ETAT", "NATURE_PROJET_DECLAREE", "EXTENSION",
            "NB_LGT_TOT_CREES", "SURF_LOC_CREEE"] + list(dest) + ["SERVICE_PUBLIC"] + LIENS
    fm.sort_values("DATE_REELLE_AUTORISATION")[cols].to_csv(OUT / "cas_fondation_mallet.csv", index=False)
    if fm.empty:
        return fm, "Fondation Mallet absente des données."
    s = fm[list(dest)].sum()
    s = s[s > 0].sort_values(ascending=False).rename(index=dest).astype(int)
    com = fm["COMMUNE"].value_counts()
    an = fm["ANNEE_AUT"].value_counts().sort_index()
    info = pc.loc[m, ["sous_famille", "signal"]].iloc[0]
    txt = (f"Classée **{fm['famille'].iloc[0]}** ({info['sous_famille']}) via « {info['signal']} ». "
           f"**{len(fm)} PC** de {an.index.min()} à {an.index.max()}, dont {fm.EXTENSION.sum()} extensions ; "
           f"états : " + ", ".join(f"{k} {v}" for k, v in fm["ETAT"].value_counts().items()) + ".\n\n"
           f"Communes : " + ", ".join(f"{k} ({v})" for k, v in com.items()) + ".\n\n"
           f"Surfaces créées : {int(fm.SURF_LOC_CREEE.sum())} m² de locaux, dont "
           + ", ".join(f"{k} {v} m²" for k, v in s.items()) + f" ; {int(fm.NB_LGT_TOT_CREES.sum())} logement(s).\n\n"
           "Lecture : les permis déclarent très peu de surface « service public / santé » : la fondation dépose "
           "surtout des locaux d'activité (commerce, bureaux, industrie, entrepôt), majoritairement dans une même "
           "commune. Hypothèse à vérifier (pas tranchée par les données) : gestion d'un patrimoine foncier "
           "d'activité, distinct de l'activité hospitalière qui fonde son classement. Ce cas montre la limite "
           "d'un classement par demandeur : la famille dit qui dépose, pas ce qui est construit.")
    return fm, txt


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pc = load()
    sections = [("1. Projets médico-sociaux × famille du porteur", p1_medico_social),
                ("2. Portefeuille : PC autorisés 2024-2026 sans ouverture de chantier (familles cibles)", p2_portefeuille),
                ("3. Constructeurs récurrents par famille", p3_recurrents),
                ("4. Extensions portées par associations / médico-social", p4_extensions),
                ("5. Étude de cas : Fondation Mallet", p5_mallet)]
    md = ["# Étape 3 — Patterns (Yvelines, PC de personnes morales, Sitadel millésime 2026-10)\n",
          f"Base : {len(pc)} permis distincts, {pc.SIREN_DEM.nunique()} demandeurs. "
          "Détail ligne à ligne (avec liens sources) dans `data/processed/patterns/`.\n"]
    for title, fn in sections:
        _, txt = fn(pc)
        md.append(f"## {title}\n\n{txt}\n")
    MD.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
