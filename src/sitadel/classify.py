"""Règles métier déterministes : famille de chaque demandeur (SIREN), par règles explicables.

Entrées :
  data/processed/pc_78_personnes_morales.csv  (étape 1, Sitadel)
  data/processed/siren_enrichi.csv            (étape 2a, API Recherche d'entreprises)
  data/ref/cj_insee.csv, data/ref/naf_insee.csv (nomenclatures INSEE)
Sorties :
  data/processed/demandeurs_classes.csv  — 1 ligne par SIREN : famille, sous-famille, confiance, règle, source
  data/processed/pc_78_classes.csv       — 1 ligne par permis (dédoublonné logements/locaux) + famille

Principe : on n'invente rien. Chaque décision cite le signal public qui la fonde.
Ordre de priorité (le premier signal fort gagne) :
  1. bailleur social        statut HLM (CJ), convention collective HLM/OPH (IDCC), nom réglementé (« HLM », « ESH », « OPH »)
  2. médico-social / santé  établissement public de santé/médico-social (CJ), gestionnaire FINESS, APE 86-88
  3. collectivité / public  CJ 7xxx / 4xxx / État étranger ; SEM / EPL
  4. association / ESS     CJ 92xx, fondation, congrégation, mutuelle, label ESS
  5. promoteur privé        APE promotion immobilière / marchand de biens, SCCV
  6. SCI / foncière         sociétés civiles immobilières, location immobilière
  7. entreprise (autre)     société commerciale dont l'activité n'est pas immobilière -> locaux pour son activité
  8. non déterminé          holdings, sièges sociaux, SIREN introuvable… -> candidats pour l'agent
"""
from __future__ import annotations

import json
import re

import pandas as pd

from .config import APE_GENERIQUES, CJ_INSEE, DEMANDEURS, NAF_INSEE, PERMIS_CLASSES, PERMIS_PM, SIREN_ENRICHI, SIREN_URL
from .review import COLONNES_LLM

# --- Signaux -----------------------------------------------------------------------------
CJ_HLM = {"5546", "5646", "5547", "5647"}               # SA HLM, coop HLM
IDCC_HLM = {"2150": "CCN des SA et fondations d'HLM", "3220": "CCN des offices publics de l'habitat"}
RE_HLM = re.compile(r"\b(H\.?L\.?M|LOYER MODERE|ENTREPRISE SOCIALE (POUR|DE) L.?HABITAT|"
                    r"\bESH\b|OFFICE PUBLIC|\bOPH\b|OPIEVOY|LOGEMENT SOCIAL)", re.I)

CJ_MEDSOC = {"7361": "CCAS", "7364": "établissement d'hospitalisation",
             "7366": "établissement public social et médico-social", "7367": "CIAS",
             "7470": "groupement de coopération sanitaire"}
APE_MEDSOC = {  # NAF rév.2 divisions 86-88 (santé, hébergement médico-social, action sociale)
    "86": "santé", "87.10A": "EHPAD / hébergement médicalisé personnes âgées",
    "87.10B": "hébergement médicalisé enfants handicapés", "87.10C": "hébergement médicalisé adultes handicapés",
    "87.20A": "hébergement social handicap mental", "87.20B": "hébergement social addictions",
    "87.30A": "hébergement social personnes âgées", "87.30B": "hébergement social handicap physique",
    "87.90A": "hébergement social enfants en difficulté", "87.90B": "hébergement social adultes en difficulté",
    "88.10A": "aide à domicile", "88.10B": "accueil sans hébergement adultes handicapés",
    "88.10C": "aide par le travail (ESAT)", "88.91A": "petite enfance (crèches)",
    "88.91B": "accueil enfants handicapés", "88.99A": "accueil enfants/adolescents",
    "88.99B": "action sociale sans hébergement",
}

CJ_SEM = {"5515", "5615", "5510"}                          # SEM, SA nationale
CJ_ASSO = {"9210", "9220", "9221", "9222", "9223", "9224", "9230", "9240", "9260", "9300", "8210", "9150"}
APE_PROMO = {"41.10A": "promotion de logements", "41.10B": "promotion de bureaux",
             "41.10C": "promotion d'autres bâtiments", "41.10D": "support de programme (SCCV/SNC)",
             "68.10Z": "marchand de biens", "41.20A": "constructeur de maisons individuelles"}
CJ_SCCV = {"6541": "SCCV (société civile de construction-vente)"}
CJ_SCI = {"6540", "6539", "6521", "6542", "6543", "6599"}
APE_FONCIER = {"68.20A": "location de logements", "68.20B": "location de terrains/biens",
               "68.32A": "administration d'immeubles", "68.31Z": "agence immobilière",
               "66.30Z": "gestion de fonds", "64.30Z": "fonds de placement"}
APE_HOLDING = APE_GENERIQUES  # trop génériques pour conclure seuls
RE_PROMO = re.compile(r"\b(SCCV|PROMOTION|PROMOGIM|IMMOBILIER|NEXITY|KAUFMAN|COGEDIM|BOUYGUES IMMO|"
                      r"VINCI IMMO|EIFFAGE IMMO|ICADE|BNP PARIBAS IMMO|LINKCITY|PITCH|EDELIS|"
                      r"QUARTUS|SOGEPROM|OGIC|EMERIGE|GREEN CITY)\b", re.I)


# --- Données personnelles : dénominations susceptibles de contenir un nom de personne physique -------
# Sociétés d'exercice libéral, SCP, sociétés civiles (SCI familiales…), structures agricoles :
# leur dénomination reprend très souvent un patronyme. On les masque dans toutes les sorties publiées
# (le SIREN et le lien vers la fiche publique restent : la traçabilité est conservée).
CJ_MASQUE = {"5385", "5485", "5785", "6540", "6539", "6542", "6599", "6597", "6598", "6533", "6534",
             "6536", "6538"} | {str(c) for c in range(6561, 6590)}
RE_PERSONNE = re.compile(r"\b(DR|DRS|DOCTEURS?|MA[IÎ]TRES?|ME|MME|MR|MONSIEUR|MADAME|EPOUX|EPOUSE|"
                         r"FR[EÈ]RES|CONSORTS?|INDIVISION|SELARL|SELAS|SCP|EARL|GAEC)\b", re.I)


def masquer(denom, cj) -> tuple[str | None, bool]:
    if not isinstance(denom, str):
        return denom, False
    if (isinstance(cj, str) and cj in CJ_MASQUE) or RE_PERSONNE.search(denom):
        return "[dénomination masquée]", True
    return denom, False


def ape2(ape: str | None) -> str | None:
    return ape[:2] if isinstance(ape, str) else None


def jlist(v) -> list:
    if isinstance(v, str) and v.strip():
        try:
            x = json.loads(v)
            return x if isinstance(x, list) else [x]
        except json.JSONDecodeError:
            return []
    return []


def classify(r: pd.Series) -> dict:
    """Renvoie famille, sous_famille, confiance (haute/moyenne/basse), regle, signal."""
    r = r.astype(object).where(r.notna(), None)  # NaN -> None
    cj = r.get("CJ") or ""
    ape = r.get("APE")
    nom = str(r.get("DENOM") or "")
    idcc = set(jlist(r.get("liste_idcc")))
    finess = jlist(r.get("liste_finess_juridique"))
    lvl1 = cj[:1]
    # APE générique dans Sitadel (siège, holding) mais APE Sirène actuel parlant -> on prend l'actuel,
    # en le signalant (l'activité a pu changer depuis le permis).
    ape_note = ""
    cur = r.get("activite_principale")
    if (ape in APE_HOLDING or ape is None) and isinstance(cur, str) and cur not in APE_HOLDING:
        ape, ape_note = cur, " [APE Sirène actuel]"

    def out(f, sf, conf, regle, signal):
        return {"famille": f, "sous_famille": sf, "confiance": conf, "regle_appliquee": regle, "signal": signal + ape_note}

    # 1. Bailleur social (sous-famille déduite de la forme juridique, pas de la convention collective :
    #    une SA d'HLM peut appliquer la CCN des OPH, ex. filiales de groupes d'offices)
    sf_bailleur = ("office public de l'habitat (OPH)" if cj in {"4140", "7371"} else
                   "coopérative HLM" if cj in {"5547", "5647", "5560", "5558"} else
                   "SEM de logement" if cj in CJ_SEM else "ESH (SA d'HLM)")
    if cj in CJ_HLM:
        return out("bailleur_social", sf_bailleur, "haute", "CJ_HLM", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    for code, lib in IDCC_HLM.items():
        if code in idcc:
            return out("bailleur_social", sf_bailleur, "haute", "IDCC_HLM", f"IDCC {code} {lib}")
    if RE_HLM.search(nom):
        return out("bailleur_social", sf_bailleur, "moyenne", "NOM_HLM", f"dénomination « {nom} »")
    if cj in CJ_SEM and ape == "68.20A":
        return out("bailleur_social", "SEM de logement", "moyenne", "SEM_LOGEMENT", f"CJ {cj} + APE 68.20A")
    if finess and ape == "68.20A" and lvl1 == "5":
        return out("bailleur_social", "société de logement gérant des structures FINESS", "moyenne",
                   "FINESS_LOGEMENT", f"APE 68.20A + entité juridique FINESS {finess[0]}")

    # 2. Médico-social / santé
    #    FINESS seul ne suffit pas : de grandes entreprises y figurent pour leur service de santé au travail
    #    (SNCF, EDF, Safran…), les pharmacies aussi. On l'exige avec une activité 86-88 ou un statut non lucratif.
    if cj in CJ_MEDSOC:
        return out("medico_social_sante", CJ_MEDSOC[cj], "haute", "CJ_MEDSOC", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    is_collectivite = lvl1 == "7"
    medsoc_ape = ape in APE_MEDSOC or ape2(ape) in {"86", "87", "88"}
    non_lucratif = lvl1 == "9"  # associations, fondations (pas « ESS » : inclut banques coopératives)
    sf_med = (APE_MEDSOC.get(ape) or
              ("cabinet / centre de santé" if isinstance(ape, str) and ape.startswith("86.2") else None) or
              APE_MEDSOC.get(ape2(ape)) or "gestionnaire FINESS")
    if finess and not is_collectivite and (medsoc_ape or non_lucratif):
        return out("medico_social_sante", sf_med, "haute", "FINESS",
                   f"entité juridique FINESS {', '.join(map(str, finess[:3]))} + APE {ape}")
    if medsoc_ape and not is_collectivite:
        return out("medico_social_sante", sf_med, "moyenne", "APE_MEDSOC", f"APE {ape} {r.get('APE_LIBELLE')}")

    # 3. Collectivité / public
    if lvl1 == "7" or lvl1 == "4" or cj in {"3205", "3210", "8110"}:
        sf = ("commune" if cj == "7210" else
              "intercommunalité / syndicat" if cj.startswith("73") and cj[:3] in {"734", "735"} else
              "département / région" if cj in {"7220", "7230"} else
              "État" if cj.startswith("71") else
              "établissement public" if lvl1 in "47" else "autre public")
        return out("collectivite_public", sf, "haute", "CJ_PUBLIC", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    if cj in CJ_SEM:
        return out("collectivite_public", "SEM / entreprise publique locale", "haute", "CJ_SEM",
                   f"CJ {cj} {r.get('CJ_LIBELLE')}")

    # 4. Association / ESS
    if cj in CJ_ASSO or lvl1 == "9" or r.get("est_association") is True:
        sf = ("fondation" if cj == "9300" else "congrégation / culte" if cj == "9240" or ape == "94.91Z"
              else "mutuelle" if cj == "8210" else "association")
        return out("association_ess", sf, "haute", "CJ_ASSO", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    # Label ESS d'une société commerciale : on ne le laisse pas primer sur une activité de promotion
    # (incohérence observée : un promoteur de grand groupe porte le label dans l'annuaire).
    # Idem pour les banques/assurances coopératives (APE 64-66) : ESS au sens légal, pas une cible.
    if (r.get("est_ess") is True or r.get("est_siae") is True) and ape not in APE_PROMO \
            and ape2(ape) not in {"64", "65", "66"}:
        sf = "foncière solidaire" if ape in {"68.20A", "68.20B"} else "entreprise de l'ESS"
        return out("association_ess", sf, "moyenne", "LABEL_ESS", "label ESS (annuaire des entreprises)")

    # 5. Promoteur privé
    if cj in CJ_SCCV:
        return out("promoteur_prive", CJ_SCCV[cj], "haute", "CJ_SCCV", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    if ape in APE_PROMO:
        return out("promoteur_prive", APE_PROMO[ape], "moyenne", "APE_PROMO", f"APE {ape} {r.get('APE_LIBELLE')}")

    # 6. SCI / foncière
    if cj in CJ_SCI:
        sf = "SCI de location / patrimoniale" if ape in APE_FONCIER or ape is None else "SCI (activité déclarée non immobilière)"
        return out("sci_fonciere", sf, "moyenne", "CJ_SCI", f"CJ {cj} {r.get('CJ_LIBELLE')}")
    if ape in APE_FONCIER:
        return out("sci_fonciere", "foncière / " + APE_FONCIER[ape], "moyenne", "APE_FONCIER",
                   f"APE {ape} {r.get('APE_LIBELLE')}")

    # 7. Holdings / sièges : trop générique -> non déterminé (avec indice de nom éventuel)
    if ape in APE_HOLDING or ape is None:
        if RE_PROMO.search(nom):
            return out("promoteur_prive", "groupe de promotion (indice nom)", "basse", "NOM_PROMO",
                       f"APE {ape} générique + dénomination « {nom} »")
        return out("non_determine", "holding / siège / activité générique", "-", "AMBIGU",
                   f"APE {ape} {r.get('APE_LIBELLE') or ''}".strip())

    # 8. Entreprise (autre) : société dont l'activité n'est pas immobilière
    if lvl1 in {"5", "6", "3"}:
        sf = "exploitation agricole" if ape2(ape) in {"01", "02", "03"} or cj in {"6597", "6598", "6533", "6534"} \
            else (r.get("APE_LIBELLE") or "activité non immobilière")
        return out("entreprise_autre", sf, "moyenne", "APE_ACTIVITE", f"APE {ape} {r.get('APE_LIBELLE')}")

    return out("non_determine", "signal insuffisant", "-", "AUCUN", f"CJ {cj} / APE {ape}")


# --- Construction des tables -----------------------------------------------------------------------

COLONNES_DEMANDEURS = [
    "SIREN_DEM", "DENOM", "CJ", "CJ_LIBELLE", "APE", "APE_LIBELLE", "n_pc", "famille", "sous_famille",
    "confiance", "regle_appliquee", "signal", "trouve", "etat_administratif", "categorie_entreprise",
    "tranche_effectif_salarie", "liste_idcc", "liste_finess_juridique", "est_ess", "est_association",
    "activite_principale", "nature_juridique", "cj_source", "denom_masquee", "regle_initiale",
    "SOURCE_SIREN_URL"] + COLONNES_LLM


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Permis (étape ingest), SIREN enrichis (étape enrich), nomenclatures CJ et NAF."""
    pc = pd.read_csv(PERMIS_PM, dtype=str)
    enr = pd.read_csv(SIREN_ENRICHI, dtype=str)
    for c in ("trouve", "est_association", "est_ess", "est_siae", "est_finess"):
        enr[c] = enr[c].map({"True": True, "False": False})
    return pc, enr, pd.read_csv(CJ_INSEE, dtype=str), pd.read_csv(NAF_INSEE, dtype=str)


def classify_demandeurs(pc: pd.DataFrame, enr: pd.DataFrame, cj: pd.DataFrame, naf: pd.DataFrame) -> pd.DataFrame:
    """Un demandeur = un SIREN, classé par les règles puis masqué si sa dénomination est à risque."""
    # CJ/APE/dénomination Sitadel : valeur au moment du permis, la plus récente
    pc = pc.assign(_d=pd.to_datetime(pc["DATE_REELLE_AUTORISATION"], errors="coerce"))
    last = (pc.sort_values("_d").groupby("SIREN_DEM")
            .agg(DENOM=("DENOM_DEM", "last"), CJ=("CJ_DEM", "last"), APE=("APE_DEM", "last"),
                 n_pc=("NUM_DAU", "nunique")).reset_index())
    d = last.merge(enr, left_on="SIREN_DEM", right_on="siren", how="left")
    # Sitadel peut avoir CJ/APE vides : compléter par Sirène actuel (tracé dans 'cj_source')
    d["cj_source"] = d["CJ"].notna().map({True: "sitadel", False: "sirene"})
    d["CJ"] = d["CJ"].fillna(d["nature_juridique"])
    d["APE"] = d["APE"].fillna(d["activite_principale"])
    d = d.merge(cj, on="CJ", how="left").merge(naf, on="APE", how="left")

    res = d.apply(classify, axis=1, result_type="expand")
    d = pd.concat([d, res], axis=1)

    d["regle_initiale"] = d["regle_appliquee"]
    d["SOURCE_SIREN_URL"] = SIREN_URL + d["SIREN_DEM"]
    # Masquage des dénominations à risque (après classement : les règles NOM_* ont vu le vrai nom)
    mk = d.apply(lambda x: masquer(x["DENOM"], x["CJ"]), axis=1, result_type="expand")
    d["DENOM"], d["denom_masquee"] = mk[0], mk[1]
    d.loc[d["denom_masquee"] & d["signal"].str.contains("dénomination", na=False), "signal"] = "dénomination (masquée)"
    return d


def merge_permits(pc: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """1 ligne par NUM_DAU, avec la famille de son demandeur.

    Un permis mixte figure dans les deux fichiers : on fusionne les deux lignes champ par champ
    (1re valeur non vide, logements d'abord) pour garder aussi les champs propres au fichier locaux
    (TYPE_SERVICE_PUBLIC, NB_CHAMBRES, surfaces par destination).
    """
    pc = pc.sort_values("SOURCE_FICHIER")
    both = pc["DANS_LOGEMENTS"].eq("True") & pc["DANS_LOCAUX"].eq("True")
    pc["SOURCE_URL_LOCAUX"] = pc["SOURCE_URL"].where(pc["SOURCE_FICHIER"].eq("locaux"))
    pc.loc[both, "SOURCE_FICHIER"] = "logements+locaux"
    pc = pc.groupby("NUM_DAU", sort=False).first().copy().reset_index()
    return pc.drop(columns=["DENOM_DEM"]).merge(
        d[["SIREN_DEM", "DENOM", "famille", "sous_famille", "confiance", "regle_appliquee", "signal",
           "regle_initiale"] + COLONNES_LLM]
        .rename(columns={"DENOM": "DENOM_DEM"}), on="SIREN_DEM", how="left")


def write_outputs(d: pd.DataFrame, permits: pd.DataFrame) -> None:
    d[COLONNES_DEMANDEURS].sort_values(["famille", "n_pc"], ascending=[True, False]).to_csv(
        DEMANDEURS, index=False, encoding="utf-8")
    permits.to_csv(PERMIS_CLASSES, index=False, encoding="utf-8")


def summary(d: pd.DataFrame, permits: pd.DataFrame) -> str:
    return "\n".join([
        "== Demandeurs (SIREN) par famille ==",
        d.groupby(["famille", "confiance"]).size().unstack(fill_value=0).to_string(),
        "\n== Permis par famille ==", permits["famille"].value_counts().to_string(),
        "\n== Règles déclenchées ==", d["regle_appliquee"].value_counts().to_string()])
