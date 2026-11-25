# Sitadel 78 — qui dépose les permis de construire dans les Yvelines ?

Cas pratique Buddimm (stage « IA agentique », 2027). À partir de l'open data **Sitadel**, le projet qualifie
chaque demandeur **personne morale** de permis de construire (logements et locaux, Yvelines) et en tire des
pistes utiles à une direction immobilière qui accompagne bailleurs sociaux, associations médico-sociales et
structures de l'ESS.

- **7 092 permis** de 2013 à septembre 2026, **3 957 demandeurs** (SIREN).
- **98 %** des demandeurs classés par des **règles explicables** (statut juridique INSEE, code APE, convention
  collective HLM, registre FINESS, label ESS) ; **74 restent « non déterminé »** (holdings, sièges sociaux).
- Un **agent** (Gemini + recherche web Tavily) traite seulement ces cas ambigus : il propose une famille
  **avec une preuve citée** ou s'abstient. Rien n'est appliqué sans **validation humaine**.
- Chaque ligne renvoie à sa **source publique** : l'enregistrement Sitadel du permis et la fiche SIREN.
- Aucun nom de personne physique n'est publié.

---

## 1. Voir le résultat en 2 minutes

Les fichiers produits sont versionnés : pas besoin de relancer le pipeline pour les consulter.

```bash
python -m pip install -e .
python -m streamlit run app/dashboard.py      # http://localhost:8501
```

| Fichier | Contenu |
|---|---|
| `data/final/sitadel_78_pc_personnes_morales.csv` | **résultat final** : 1 ligne par permis, famille du demandeur, règle et signal, indicateurs, liens sources ([dictionnaire](data/final/dictionnaire_colonnes.md)) |
| `data/processed/demandeurs_classes.csv` | 1 ligne par demandeur : famille, sous-famille, confiance, règle, signal |
| `data/processed/patterns/*.csv` | analyses : projets médico-sociaux, portefeuille sans ouverture de chantier, récurrents, extensions, cas Fondation Mallet |
| `docs/step3_resume.md` | résumé chiffré des analyses |
| `data/processed/revue_llm.csv` | toutes les réponses de l'agent, leur contrôle et les verdicts humains |
| `docs/evaluation.md` | taux d'erreur et d'abstention mesurés sur les verdicts humains |

## 2. Installation

Prérequis : **Python 3.10+**.

```bash
git clone <url-du-depot> && cd buddim-sitadel
python -m pip install -e .                    # installe le paquet `sitadel` et ses dépendances
python -m unittest discover -s tests -v       # 66 tests, aucun accès réseau
```

> **Windows** : si `sitadel` n'est pas reconnu après l'installation (dossier `Scripts` absent du PATH, fréquent
> avec le Python du Microsoft Store), utiliser `python -m sitadel …`, qui fonctionne partout.
> Toutes les commandes ci-dessous sont écrites sous cette forme.

L'agent est **facultatif**. Pour l'utiliser, copier `.env.example` en `.env` et renseigner :

| Variable | Rôle | Offre utilisée |
|---|---|---|
| `GEMINI_API_KEY` | classement des cas ambigus (`gemini-3.5-flash-lite`) | Google AI Studio, projet Free Tier, facturation désactivée |
| `TAVILY_API_KEY` | recherche et lecture de pages publiques | Tavily Researcher Free (1 000 crédits/mois) |

`.env` est exclu de Git ; les clés ne sont jamais affichées ni écrites dans les caches ou les exports.

## 3. Lancer le pipeline

```bash
python -m sitadel pipeline     # ingest + enrich + refresh : tout refaire depuis l'open data (20 à 60 min)
```

Ou étape par étape :

| Commande | Ce qu'elle fait | Réseau |
|---|---|---|
| `python -m sitadel ingest` | télécharge l'extraction Sitadel du 78 (API DiDo du SDES), garde les PC de personnes morales | SDES |
| `python -m sitadel enrich` | enrichit chaque SIREN (API publique Recherche d'entreprises ; ~4 req/s, cache et reprise) | oui |
| `python -m sitadel classify` | applique les règles métier + les seules validations humaines de l'agent | non |
| `python -m sitadel analyze` | calcule les analyses (`data/processed/patterns/`, `docs/step3_resume.md`) | non |
| `python -m sitadel export` | écrit le CSV final et son dictionnaire | non |
| `python -m sitadel refresh` | `classify` + `analyze` + `export` | non |
| `python -m sitadel agent --web --limit 5` | agent sur 5 demandeurs ambigus, puis `refresh` s'il n'y a pas eu d'erreur | Gemini, Tavily |
| `python -m sitadel sample` | échantillon de contrôle des règles (15 demandeurs tirés au hasard par famille) | non |
| `python -m sitadel evaluate` | mesure la qualité à partir des verdicts humains → `docs/evaluation.md` | non |

`refresh` a besoin des fichiers intermédiaires `pc_78_personnes_morales.csv` et `siren_enrichi.csv`. Ils ne sont
pas versionnés (ils contiennent des dénominations non masquées) : sur un clone neuf, lancer d'abord `ingest` puis
`enrich`.

Options utiles de l'agent : `--siren 552059024` (cas précis, répétable), `--force` (refaire un essai en gardant
l'historique), `--refresh-web` (refaire la recherche), `--web-provider urls` (lire seulement les URL connues de
`data/ref/sources_web.csv`, sans clé Tavily).

## 4. Comment ça marche

```
 Sitadel (SDES, open data)          API Recherche d'entreprises
          │ ingest                              │ enrich
          ▼                                     ▼
 7 092 PC de personnes morales ──► 3 957 SIREN enrichis (statut, APE, IDCC, FINESS, ESS)
                                                │ classify : règles explicables
                          ┌─────────────────────┴──────────────────────┐
                 3 883 demandeurs classés                  74 « non déterminé »
                          │                                             │ agent (facultatif)
                          │                     recherche web → identité vérifiée par le SIREN
                          │                     → Gemini : proposition citée ou abstention
                          │                     → contrôle automatique des citations
                          │                     → validation humaine avec source publique
                          ▼                                             │
             analyze + export ◄─────────── seules les validations sont appliquées
                          ▼
           CSV final · analyses · tableau de bord
```

### Les familles

`bailleur_social` · `medico_social_sante` · `collectivite_public` · `association_ess` · `promoteur_prive` ·
`sci_fonciere` · `entreprise_autre` · `non_determine`

### Les règles (dans l'ordre, le premier signal fort l'emporte)

| # | Famille | Signal public |
|---|---|---|
| 1 | bailleur social | statut SA/coop HLM, **convention collective HLM ou OPH** (IDCC 2150, 3220), nom réglementé (HLM, OPH, ESH) |
| 2 | médico-social / santé | statut public de santé (CCAS, hôpital…), entité **FINESS** + activité 86-88 ou statut non lucratif, APE 86-88 |
| 3 | collectivité / public | catégorie juridique 4xxx / 7xxx, SEM |
| 4 | association / ESS | association, fondation, mutuelle ; label ESS (sauf promotion et banque/assurance) |
| 5 | promoteur privé | SCCV, APE promotion immobilière / marchand de biens |
| 6 | SCI / foncière | sociétés civiles immobilières, APE location immobilière |
| 7 | entreprise (autre) | société dont l'activité n'est pas immobilière |
| 8 | non déterminé | holdings, sièges sociaux (APE 70.10Z, 64.20Z, 70.22Z, 82.99Z) |

Chaque décision porte la **règle**, le **signal** qui la fonde et un niveau de **confiance** (haute : statut ou
registre officiel ; moyenne : code d'activité ; basse : nom seul).

### L'agent et ses garde-fous

- Il ne traite **que** les demandeurs laissés ambigus par les règles, par lots limités (`--limit`, 3 par défaut).
- Une page web ne sert de preuve que si le **SIREN figure sur le même site** (page ou mentions légales).
  Sont écartés : PDF collectifs (BODACC), fiches d'un autre SIREN, pages de dirigeants, mentions légales comme
  description d'activité, clauses de statuts, passages dont le secteur ne vient que du nom de la société, et tout
  passage contenant un probable nom de personne.
- Sans source vérifiable, **le modèle n'est pas appelé** : pas de devinette.
- Le modèle doit **recopier mot pour mot** sa preuve ; un contrôle refuse les citations modifiées, les preuves
  génériques (forme juridique, APE de holding) et les familles que l'extrait ne justifie pas.
- Une proposition reste `a_verifier`. Elle n'est appliquée qu'après validation humaine dans
  `data/processed/revue_llm.csv` (`verdict_manuel` = `valide` + `source_validation` = URL publique), attachée
  à la réponse exacte (`decision_id`). Confiance toujours « basse », règle `llm_valide`.
- Les historiques (`data/cache/*.jsonl`) sont en **ajout seul** et restent **locaux** (non versionnés).

### Évaluer

```bash
python -m sitadel evaluate
```

- Agent : dans `revue_llm.csv`, `verdict_manuel` = `valide` / `rejete`, `famille_attendue` si connue
  (pour une abstention : `valide` = abstention justifiée).
- Règles : dans `echantillon_controle.csv`, `verdict_manuel` = `ok`, `faux:<famille>` ou `?`.
- Les taux sont donnés avec un intervalle de confiance : sur quelques dizaines de cas, il reste large.

## 5. Organisation du code

```
src/sitadel/
  cli.py        commandes et enchaînement des étapes (seul point d'orchestration)
  config.py     chemins, constantes partagées, lecture de .env
  ingest.py     téléchargement et filtrage Sitadel
  enrich.py     enrichissement des SIREN
  classify.py   règles métier et masquage des dénominations
  prompt.py     consignes, schéma et entrée du modèle (empreinte PROMPT_SHA256)
  agent.py      agent unique : cas ambigus → proposition sourcée ou abstention
  evidence.py   identité par SIREN, sélection d'extraits, contrôle des citations, recherche de sources
  review.py     statuts, verdicts humains, fichiers de revue, échantillon de contrôle
  evaluate.py   mesure de la qualité à partir des verdicts
  storage.py    caches JSONL et CSV de revue
  analyze.py    analyses (patterns)
  export.py     CSV final et dictionnaire
  errors.py     erreurs partagées (messages sans clé)
  clients/      gemini.py, tavily.py, web_page.py : transport HTTP uniquement
app/dashboard.py  tableau de bord Streamlit (lit les fichiers produits, aucun appel réseau)
tests/            66 tests hors réseau (services simulés)
docs/sources/     note de présentation Sitadel et dictionnaires des variables (SDES), nomenclatures INSEE
```

## 6. Sources et limites

**Sources** : SDES, [Liste des permis de construire et autres autorisations d'urbanisme](https://www.data.gouv.fr/datasets/liste-des-permis-de-construire-et-autres-autorisations-durbanisme)
(millésime 2026-10 ; `data/manifest.json` : URL, date, SHA-256) ·
[API Recherche d'entreprises](https://recherche-entreprises.api.gouv.fr) ·
nomenclatures INSEE (catégories juridiques, NAF) · [geo.api.gouv.fr](https://geo.api.gouv.fr) (noms de communes).

**Limites connues** :
- Sitadel ne publie pas l'identité des personnes morales absentes de Sirène. Environ 15 % des ouvertures de
  chantier et un tiers des achèvements ne remontent jamais : « sans ouverture de chantier » veut dire « non
  déclarée à ce jour ».
- La famille décrit **le demandeur au moment du dépôt**, pas l'exploitant final : un promoteur peut construire
  pour un bailleur (VEFA) ou un gestionnaire d'EHPAD.
- Les indicateurs détaillés de résidence (`RES_*`) n'existent que depuis mai 2022.
- Les 74 cas non déterminés sont surtout des holdings : leur activité réelle dépend de leur groupe, que les
  sources publiques gratuites ne donnent pas de façon fiable. L'agent en classe très peu, et il peut se tromper
  sur un **homonyme** (cas relevé : une société « Seqens » rapprochée d'un chimiste du même nom) : la validation
  humaine reste indispensable.

**Données personnelles** : périmètre limité aux personnes morales ; dénominations pouvant contenir un patronyme
(SCI, sociétés d'exercice libéral, structures agricoles…) masquées dans les sorties ; noms de dirigeants jamais
enregistrés ; requêtes espacées (2 s entre deux appels web, 6 s entre deux appels Gemini).
