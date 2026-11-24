# Sitadel 78 — qualification des demandeurs de permis de construire

Test de recrutement Buddimm (stage IA agentique 2027).
Périmètre : permis de construire (PC) de logements et de locaux, Yvelines (78), demandeurs personnes morales.

## Étape 1 — données

```bash
pip install -r requirements.txt
python src/step1_download.py          # millésime le plus récent
python src/step1_download.py --millesime 2026-10 --force
```

- Source : SDES, [Liste des permis de construire et autres autorisations d'urbanisme](https://www.data.gouv.fr/datasets/liste-des-permis-de-construire-et-autres-autorisations-durbanisme)
  (API DiDo, filtre `DEP_CODE=eq:78` appliqué côté serveur).
- `data/manifest.json` : URL exacte, millésime, date de téléchargement, empreinte SHA-256 de chaque fichier.
- `data/processed/pc_78_personnes_morales.csv` : une ligne par (permis × fichier source), avec `SOURCE_URL` (page catalogue SDES)
  et `SIREN_URL` (fiche publique annuaire-entreprises).
- `docs/sources/` : note de présentation officielle et dictionnaires des variables.

## Étape 2 — qualification des demandeurs

```bash
python src/step2a_enrich_siren.py   # API publique Recherche d'entreprises (~1 h, cache + reprise)
python src/step2b_classify.py       # règles explicables -> famille / sous-famille / confiance / signal
python src/step2b_llm.py            # LLM local (Ollama, qwen2.5) sur les seuls « non déterminé »
python src/qc_echantillon.py        # 15 demandeurs tirés au hasard par famille (graine 42) à vérifier à la main
```

LLM : uniquement sur les cas `non_determine`, avec dénomination (masquée si besoin), catégorie juridique,
APE et activité du siège. Toute sortie LLM porte `regle_appliquee="llm"` et `confiance="basse"` ; entrée
et sortie brute sont gardées dans `data/cache/ollama_decisions.jsonl`. Si Ollama ne répond pas, le script
s'arrête proprement et les cas restent « non déterminé » (état actuel : non exécuté, 74 cas).

Contrôle qualité : `data/processed/echantillon_controle.csv` (120 lignes, colonne `verdict_manuel` à remplir).

Familles : `bailleur_social`, `medico_social_sante`, `collectivite_public`, `association_ess`,
`promoteur_prive`, `sci_fonciere`, `entreprise_autre`, `non_determine`.

Chaque décision porte la règle déclenchée et le signal public qui la fonde (catégorie juridique INSEE,
code APE, convention collective HLM/OPH, entité FINESS, label ESS…), ainsi qu'un lien vers la fiche
publique du SIREN. Sorties : `data/processed/demandeurs_classes.csv` (1 ligne / SIREN) et
`data/processed/pc_78_classes.csv` (1 ligne / permis).

Données personnelles : les dénominations susceptibles de contenir un patronyme (SCI, sociétés
d'exercice libéral, SCP, structures agricoles, mentions « DR », « EARL »…) sont masquées dans les
sorties ; le SIREN et le lien restent. Les noms de dirigeants renvoyés par l'API ne sont jamais écrits.

## Étape 3 — patterns

```bash
python src/step3_patterns.py        # CSV dans data/processed/patterns/, résumé dans docs/step3_resume.md
```

1. projets médico-sociaux (résidences, service public santé / action sociale, chambres) × famille du porteur ;
2. portefeuille : PC autorisés 2024-2026 sans ouverture de chantier, familles cibles ;
3. constructeurs récurrents (≥ 3 PC) : années actives, logements, m² créés ;
4. extensions portées par associations / acteurs médico-sociaux ;
5. étude de cas : Fondation Mallet.

Noms de communes : `data/ref/communes_78.csv` (geo.api.gouv.fr, une requête).

## Étape 4 — CSV final et tableau de bord

```bash
python src/step4_export.py          # data/final/sitadel_78_pc_personnes_morales.csv (+ dictionnaire_colonnes.md)
streamlit run app/dashboard.py      # tableau de bord local, aucun appel réseau
```

CSV final : 1 ligne par permis (7 092), famille du demandeur, règle, signal, indicateurs, et trois liens :
`SOURCE_PERMIS_URL` (l'enregistrement Sitadel exact, via l'API publique DiDo filtrée sur `NUM_DAU`),
`SOURCE_JEU_DE_DONNEES` (page du fichier SDES) et `SIREN_URL` (fiche publique du demandeur).

Tableau de bord : filtres (famille, années, état, commune, confiance, recherche), vue d'ensemble, portefeuille
sans ouverture de chantier, projets médico-sociaux, récurrents, extensions, cas Fondation Mallet, données
filtrées téléchargeables, méthode et limites.
