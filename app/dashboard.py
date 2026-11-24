"""Tableau de bord — permis de construire des personnes morales, Yvelines (Sitadel).

Lancer : streamlit run app/dashboard.py
Lit uniquement des fichiers produits par le pipeline (data/final, data/processed/patterns) : aucun appel réseau.
"""
from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data" / "final" / "sitadel_78_pc_personnes_morales.csv"
PAT = ROOT / "data" / "processed" / "patterns"

# Couleur fixée par famille (l'entité garde sa couleur quel que soit le filtre). Ordre catégoriel validé ;
# « non déterminé » en gris neutre.
FAMILLES = {
    "bailleur_social": ("Bailleur social", "#2a78d6"),
    "medico_social_sante": ("Médico-social / santé", "#eb6834"),
    "association_ess": ("Association / ESS", "#1baf7a"),
    "collectivite_public": ("Collectivité / public", "#eda100"),
    "promoteur_prive": ("Promoteur privé", "#e87ba4"),
    "sci_fonciere": ("SCI / foncière", "#008300"),
    "entreprise_autre": ("Entreprise (autre)", "#6250d6"),
    "non_determine": ("Non déterminé", "#9a9893"),
}
LIB = {k: v[0] for k, v in FAMILLES.items()}
COLOR = alt.Scale(domain=[v[0] for v in FAMILLES.values()], range=[v[1] for v in FAMILLES.values()])
CIBLES = ["bailleur_social", "association_ess", "medico_social_sante"]

LINKS = {
    "SOURCE_PERMIS_URL": st.column_config.LinkColumn("Permis (Sitadel)", display_text="enregistrement"),
    "SIREN_URL": st.column_config.LinkColumn("Demandeur", display_text="fiche SIREN"),
    "SOURCE_URL": st.column_config.LinkColumn("Fichier Sitadel", display_text="jeu de données"),
    "ANNEE": st.column_config.NumberColumn("Année", format="%d"),
}

st.set_page_config(page_title="Sitadel 78 — personnes morales", layout="wide")


@st.cache_data
def load() -> pd.DataFrame:
    df = pd.read_csv(FINAL, dtype={"NUM_DAU": str, "SIREN_DEM": str, "COMM": str, "CJ": str},
                     encoding="utf-8-sig", parse_dates=["DATE_AUTORISATION", "DATE_OUVERTURE_CHANTIER"])
    df["ANNEE"] = df["DATE_AUTORISATION"].dt.year
    for c in ("DATE_AUTORISATION", "DATE_OUVERTURE_CHANTIER"):
        df[c] = df[c].dt.date
    df["Famille"] = df["FAMILLE"].map(LIB)
    return df


@st.cache_data
def pattern(name: str) -> pd.DataFrame:
    return pd.read_csv(PAT / name, dtype={"NUM_DAU": str, "SIREN_DEM": str})


def bar_tooltip_chart(data: pd.DataFrame, y: str, x: str, color: bool, title: str, height: int = 280):
    base = alt.Chart(data).mark_bar(cornerRadiusEnd=4, height={"band": 0.7}, stroke="white", strokeWidth=2)
    height = max(height, 28 * len(data))
    enc = dict(y=alt.Y(f"{y}:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False, labelLimit=220)),
               x=alt.X(f"{x}:Q", title=title, axis=alt.Axis(grid=True, gridOpacity=0.3)),
               tooltip=[alt.Tooltip(f"{y}:N"), alt.Tooltip(f"{x}:Q", format=",.0f")])
    if color:
        enc["color"] = alt.Color("Famille:N", scale=COLOR, legend=None)
    else:
        enc["color"] = alt.value("#2a78d6")
    return base.encode(**enc).properties(height=height)


df = load()

# ---------------------------------------------------------------- filtres
st.title("Permis de construire des personnes morales — Yvelines")
st.caption("Source : SDES, Sitadel (liste des permis de construire), millésime 2026-10 · demandeurs qualifiés "
           "par règles publiques (INSEE, annuaire des entreprises) · chaque ligne renvoie à son enregistrement source.")

with st.sidebar:
    st.header("Filtres")
    cible = st.toggle("Familles cibles seulement", value=False,
                      help="Bailleurs sociaux, associations / ESS, médico-social")
    fams = st.multiselect("Famille du demandeur", list(LIB.values()),
                          default=[LIB[f] for f in CIBLES] if cible else list(LIB.values()))
    a0, a1 = int(df["ANNEE"].min()), int(df["ANNEE"].max())
    annees = st.slider("Année d'autorisation", a0, a1, (a0, a1))
    etats = st.multiselect("État du projet", sorted(df["ETAT"].dropna().unique()),
                           default=sorted(df["ETAT"].dropna().unique()))
    communes = st.multiselect("Communes", sorted(df["COMMUNE"].dropna().unique()))
    conf = st.multiselect("Confiance du classement", ["haute", "moyenne", "basse", "-"],
                          default=["haute", "moyenne", "basse", "-"])
    q = st.text_input("Recherche (dénomination ou SIREN)")

f = df[df["Famille"].isin(fams) & df["ANNEE"].between(*annees) & df["ETAT"].isin(etats)
       & df["CONFIANCE"].fillna("-").isin(conf)]
if communes:
    f = f[f["COMMUNE"].isin(communes)]
if q:
    f = f[f["DENOMINATION"].str.contains(q, case=False, na=False) | f["SIREN_DEM"].str.contains(q, na=False)]

k = st.columns(5)
k[0].metric("Permis", f"{len(f):,}".replace(",", " "))
k[1].metric("Demandeurs", f"{f['SIREN_DEM'].nunique():,}".replace(",", " "))
k[2].metric("Logements créés", f"{int(f['NB_LOGEMENTS_CREES'].sum()):,}".replace(",", " "))
k[3].metric("dont locatifs sociaux", f"{int(f['DONT_LOCATIFS_SOCIAUX'].sum()):,}".replace(",", " "))
k[4].metric("m² de locaux créés", f"{int(f['SURF_LOCAUX_CREEE_M2'].sum()):,}".replace(",", " "))

tabs = st.tabs(["Vue d'ensemble", "Portefeuille sans chantier", "Projets médico-sociaux", "Constructeurs récurrents",
                "Extensions", "Cas : Fondation Mallet", "Données", "Méthode & limites"])

# ---------------------------------------------------------------- vue d'ensemble
with tabs[0]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Permis par famille de demandeur")
        g = f.groupby("Famille").size().rename("Permis").reset_index()
        st.altair_chart(bar_tooltip_chart(g, "Famille", "Permis", True, "Permis"), use_container_width=True)
    with c2:
        st.subheader("Communes les plus concernées")
        g = f.groupby("COMMUNE").size().rename("Permis").reset_index().nlargest(12, "Permis")
        st.altair_chart(bar_tooltip_chart(g, "COMMUNE", "Permis", False, "Permis"), use_container_width=True)

    st.subheader("Permis autorisés par année")
    g = f.groupby(["ANNEE", "Famille"]).size().rename("Permis").reset_index()
    order = [v for v in LIB.values() if v in set(g["Famille"])]
    chart = (alt.Chart(g).mark_bar(stroke="white", strokeWidth=2)
             .encode(x=alt.X("ANNEE:O", title=None),
                     y=alt.Y("Permis:Q", title="Permis", axis=alt.Axis(gridOpacity=0.3)),
                     color=alt.Color("Famille:N", scale=COLOR, sort=order,
                                     legend=alt.Legend(orient="top", title=None, columns=4, labelLimit=200)),
                     order=alt.Order("famille_rank:Q"),
                     tooltip=["ANNEE:O", "Famille:N", alt.Tooltip("Permis:Q", format=",.0f")])
             .transform_calculate(famille_rank=f"indexof({order}, datum.Famille)")
             .properties(height=320))
    st.altair_chart(chart, use_container_width=True)
    st.caption("2026 : année partielle (autorisations jusqu'à fin septembre). Délais de remontée : les dernières "
               "autorisations sont encore incomplètes.")

    st.subheader("Synthèse par famille")
    s = f.groupby("Famille").agg(Permis=("NUM_DAU", "size"), Demandeurs=("SIREN_DEM", "nunique"),
                                 Logements=("NB_LOGEMENTS_CREES", "sum"), LLS=("DONT_LOCATIFS_SOCIAUX", "sum"),
                                 m2_locaux=("SURF_LOCAUX_CREEE_M2", "sum"),
                                 Delai_median_DOC_j=("DELAI_AUT_DOC_JOURS", "median")).reset_index()
    s["Délai médian aut. → DOC (mois)"] = (s.pop("Delai_median_DOC_j") / 30.44).round(1)
    st.dataframe(s.sort_values("Permis", ascending=False), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- portefeuille
with tabs[1]:
    st.subheader("PC autorisés 2024-2026 sans ouverture de chantier — bailleurs, associations / ESS, médico-social")
    st.info("« Sans ouverture de chantier » = non déclarée dans Sitadel à ce jour. Environ 15 % des ouvertures "
            "de chantier ne remontent jamais (note SDES) : c'est une liste de projets à vérifier, pas de projets bloqués.")
    p = pattern("portefeuille_sans_doc.csv")
    p["famille"] = p["famille"].map(LIB)
    p = p[p["famille"].isin(fams)]
    if communes:
        p = p[p["COMMUNE"].isin(communes)]
    st.dataframe(p.drop(columns=["SOURCE_URL_LOCAUX"]), hide_index=True, use_container_width=True,
                 column_config={"SOURCE_URL": LINKS["SOURCE_URL"], "SIREN_URL": LINKS["SIREN_URL"]})

# ---------------------------------------------------------------- médico-social
with tabs[2]:
    st.subheader("Projets à caractère médico-social × famille du porteur")
    st.caption("Signal porté par le projet (résidence personnes âgées / handicapées / sociale, service public "
               "santé ou action sociale, chambres hors hôtellerie), indépendamment de qui dépose.")
    m = f[f["SIGNAUX_MEDICO_SOCIAUX"].notna()].copy()
    x = m.assign(Signal=m["SIGNAUX_MEDICO_SOCIAUX"].str.split(" ; ")).explode("Signal")
    g = x.groupby(["Signal", "Famille"]).size().rename("Permis").reset_index()
    order = [v for v in LIB.values() if v in set(g["Famille"])]
    chart = (alt.Chart(g).mark_bar(stroke="white", strokeWidth=2, height={"band": 0.7})
             .encode(y=alt.Y("Signal:N", title=None, sort="-x", axis=alt.Axis(labelLimit=260)),
                     x=alt.X("Permis:Q", stack="zero", axis=alt.Axis(gridOpacity=0.3)),
                     color=alt.Color("Famille:N", scale=COLOR, sort=order,
                                     legend=alt.Legend(orient="top", title=None, columns=4, labelLimit=200)),
                     order=alt.Order("famille_rank:Q"),
                     tooltip=["Signal:N", "Famille:N", "Permis:Q"])
             .transform_calculate(famille_rank=f"indexof({order}, datum.Famille)")
             .properties(height=260))
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(pd.crosstab(x["Signal"], x["Famille"], margins=True, margins_name="total"),
                 use_container_width=True)
    st.dataframe(m[["Famille", "DENOMINATION", "COMMUNE", "ANNEE", "ETAT", "SIGNAUX_MEDICO_SOCIAUX", "EXTENSION",
                    "NB_LOGEMENTS_CREES", "NB_CHAMBRES", "SURF_LOCAUX_CREEE_M2", "SOURCE_PERMIS_URL", "SIREN_URL"]],
                 hide_index=True, use_container_width=True, column_config=LINKS)

# ---------------------------------------------------------------- récurrents
with tabs[3]:
    st.subheader("Demandeurs récurrents (≥ 3 permis sur la période)")
    r = pattern("constructeurs_recurrents.csv")
    r["famille"] = r["famille"].map(LIB)
    r = r[r["famille"].isin(fams)]
    if q:
        r = r[r["DENOM_DEM"].str.contains(q, case=False, na=False)]
    st.dataframe(r, hide_index=True, use_container_width=True, column_config={"SIREN_URL": LINKS["SIREN_URL"]})

# ---------------------------------------------------------------- extensions
with tabs[4]:
    st.subheader("Extensions portées par des associations / ESS et des acteurs médico-sociaux")
    e = f[f["EXTENSION"] & f["FAMILLE"].isin(["association_ess", "medico_social_sante"])]
    c1, c2 = st.columns([1, 2])
    c1.metric("Extensions", len(e))
    c1.metric("m² créés", f"{int(e['SURF_LOCAUX_CREEE_M2'].sum()):,}".replace(",", " "))
    g = e.groupby("DENOMINATION").size().rename("Extensions").reset_index().nlargest(10, "Extensions")
    with c2:
        st.altair_chart(bar_tooltip_chart(g, "DENOMINATION", "Extensions", False, "Extensions", 260),
                        use_container_width=True)
    st.dataframe(e[["Famille", "SOUS_FAMILLE", "DENOMINATION", "COMMUNE", "ANNEE", "ETAT", "SURF_LOCAUX_CREEE_M2",
                    "SERVICE_PUBLIC", "SOURCE_PERMIS_URL", "SIREN_URL"]],
                 hide_index=True, use_container_width=True, column_config=LINKS)

# ---------------------------------------------------------------- Mallet
with tabs[5]:
    st.subheader("Étude de cas : Fondation Mallet")
    fm = df[df["DENOMINATION"].str.contains("FONDATION MALLET", case=False, na=False)]
    m2 = f"{int(fm['SURF_LOCAUX_CREEE_M2'].sum()):,}".replace(",", " ")
    st.markdown(
        f"Classée **{LIB[fm['FAMILLE'].iloc[0]]}** ({fm['SOUS_FAMILLE'].iloc[0]}) d'après « {fm['SIGNAL'].iloc[0]} ». "
        f"**{len(fm)} permis** entre {fm['ANNEE'].min()} et {fm['ANNEE'].max()}, "
        f"{int(fm['EXTENSION'].sum())} extensions, {m2} m² de locaux créés "
        "— surtout industrie, commerce, bureaux et entrepôt, très peu en service public. "
        "Hypothèse à vérifier : gestion d'un patrimoine d'activité distinct de l'activité hospitalière. "
        "La famille dit **qui dépose**, pas **ce qui est construit**.")
    c1, c2 = st.columns(2)
    surf = pattern("cas_fondation_mallet.csv")
    dest = {"SURF_IND_CREEE": "industrie", "SURF_COM_CREEE": "commerce", "SURF_BUR_CREEE": "bureaux",
            "SURF_ENT_CREEE": "entrepôt", "SURF_AGR_CREEE": "agricole", "SURF_HAB_CREEE": "habitation",
            "SURF_PUB_CREEE": "service public"}
    sd = surf[list(dest)].sum().rename(index=dest).rename("m2").reset_index().rename(columns={"index": "Destination"})
    with c1:
        st.altair_chart(bar_tooltip_chart(sd[sd.m2 > 0], "Destination", "m2", False, "m² créés", 240),
                        use_container_width=True)
    with c2:
        g = fm.groupby("COMMUNE").size().rename("Permis").reset_index()
        st.altair_chart(bar_tooltip_chart(g, "COMMUNE", "Permis", False, "Permis", 240), use_container_width=True)
    st.dataframe(fm[["DATE_AUTORISATION", "COMMUNE", "ETAT", "NATURE_PROJET", "EXTENSION", "SURF_LOCAUX_CREEE_M2",
                     "NB_LOGEMENTS_CREES", "SERVICE_PUBLIC", "SOURCE_PERMIS_URL", "SIREN_URL"]]
                 .sort_values("DATE_AUTORISATION"), hide_index=True, use_container_width=True, column_config=LINKS)

# ---------------------------------------------------------------- données
with tabs[6]:
    st.subheader(f"{len(f)} permis (filtres appliqués)")
    st.dataframe(f.drop(columns=["ANNEE", "Famille"]), hide_index=True, use_container_width=True,
                 column_config={**LINKS, "SOURCE_PERMIS_URL_2": st.column_config.LinkColumn(
                     "Permis (2e fichier)", display_text="enregistrement"),
                     "SOURCE_JEU_DE_DONNEES": st.column_config.LinkColumn("Jeu de données", display_text="SDES")})
    st.download_button("Télécharger la sélection (CSV)", f.drop(columns=["ANNEE", "Famille"]).to_csv(index=False)
                       .encode("utf-8-sig"), "sitadel_78_selection.csv", "text/csv")

# ---------------------------------------------------------------- méthode
with tabs[7]:
    st.markdown("""
**Périmètre.** Permis de construire (PC) des fichiers Sitadel *logements* et *locaux*, Yvelines, déposés par une
personne morale (SIREN ou catégorie juridique renseigné). Un permis mixte apparaît une fois (lignes fusionnées).

**Classement du demandeur.** Règles explicables, dans l'ordre : statut HLM / convention collective HLM-OPH →
médico-social (statut public de santé, entité FINESS + activité 86-88, APE 86-88) → public (CJ 4xxx / 7xxx) →
association / ESS → promoteur (SCCV, APE promotion) → SCI / foncière → entreprise. Chaque ligne porte la règle,
le signal et sa confiance. Les cas sans signal suffisant restent **non déterminés** ; un LLM local peut les
arbitrer (confiance « basse », marqué `llm`).

**Limites.**
- Sitadel ne publie pas l'identité des personnes morales absentes de Sirène ni de celles assimilées à des
  personnes physiques ; ~15 % des ouvertures de chantier, ~1/3 des achèvements et près de la moitié des
  annulations ne remontent jamais.
- La famille décrit le **demandeur** au moment du dépôt, pas le futur exploitant (VEFA : un promoteur peut
  construire pour un bailleur ou un gestionnaire d'EHPAD).
- Les indicateurs de résidence détaillés (RES_*) n'existent que depuis mai 2022.
- Les dénominations pouvant contenir un nom de personne (SCI, sociétés d'exercice libéral…) sont masquées ;
  le lien vers l'enregistrement source reste disponible.
""")
