# Qui dépose les permis de construire dans les Yvelines ? — Note de rendu

Cas « qualification des permis de construire (Sitadel) » · Stage IA agentique 2027 · 25 novembre 2026<br>
Dépôt : https://github.com/Abbasdir/sitadel-78

## 1. Angle choisi

Sitadel dit **qui** construit, pas **ce qu'est** le demandeur. Pour une direction immobilière qui accompagne
bailleurs sociaux, associations médico-sociales et structures de l'ESS, la vraie question est donc : *qui, parmi
les demandeurs, ressemble à nos clients, et quels projets sont en cours ?*

J'ai fait deux choix :

- **D'abord des règles explicables, l'IA seulement en dernier recours.** Un statut juridique INSEE, une convention
  collective HLM ou une entité FINESS sont des faits publics, vérifiables et gratuits : un LLM n'y ajouterait que
  du risque. Chaque classement porte la règle, le signal qui la fonde et un niveau de confiance.
- **Un agent restreint aux cas ambigus, qui a le droit de dire « je ne sais pas ».** Il cherche des pages
  publiques dont l'identité est prouvée par le SIREN, cite mot pour mot sa preuve ou s'abstient ; un contrôle
  automatique rejette les citations inventées, et rien n'est appliqué sans validation humaine.

Périmètre : PC de logements et de locaux du 78, personnes morales, 2013 – septembre 2026 (millésime 2026-10).
**7 092 permis, 3 957 demandeurs.** Chaque ligne du CSV final renvoie à l'enregistrement Sitadel du permis et à
la fiche publique du SIREN.

## 2. Ce que j'ai trouvé

**Qualification.** Les règles classent **3 883 demandeurs sur 3 957 (98 %)** ; 974 décisions reposent sur un
statut ou un registre officiel, 2 903 sur le code d'activité. **74 restent « non déterminé »** (103 permis) :
presque tous des holdings et sièges sociaux. Repérer les bailleurs exige la **convention collective** (IDCC 2150
et 3220) : Immobilière 3F, Domnis ou Les Résidences sont des SA « ordinaires » pour l'INSEE.

| Famille | Demandeurs | Permis |
|---|---|---|
| SCI / foncière | 1 625 | 2 118 |
| Promoteur privé | 982 | 1 686 |
| Collectivité / public | 313 | 1 179 |
| Entreprise (autre activité) | 695 | 1 172 |
| **Bailleur social** | **52** | **393** |
| **Médico-social / santé** | **100** | **231** |
| **Association / ESS** | **116** | **210** |
| Non déterminé | 74 | 103 |

**Pistes pour Buddimm**

1. **Le logement social passe d'abord par les promoteurs.** Les permis des promoteurs portent **13 443 logements
   locatifs sociaux (54 %)**, contre 8 186 pour les bailleurs (33 %) : la VEFA domine. Un bailleur actif dans le
   78 se voit autant dans les permis des promoteurs que dans les siens.
2. **Un portefeuille de projets à suivre :** **81 permis autorisés en 2024-2026 sans ouverture de chantier
   déclarée**, portés par des bailleurs (33 permis, 989 logements dont 790 sociaux), des acteurs médico-sociaux
   (23, environ 12 800 m²) et des associations (25, environ 12 800 m²). Immobilière 3F, CDC Habitat, l'Association
   diocésaine, l'hôpital Théophile Roussel, Avenir APEI en tête. Un projet autorisé mais non lancé est un moment
   où un accompagnement peut être utile.
3. **Le médico-social ne se lit pas dans la famille du demandeur.** 479 permis portent un signal médico-social
   (résidence personnes âgées / handicapées / sociale, service public santé ou action sociale) : seuls 131 sont
   déposés par des acteurs médico-sociaux ; 143 par des collectivités, 69 par des promoteurs (25 des 35
   résidences pour personnes âgées).
4. **Les associations et le médico-social agrandissent :** 52 % de leurs permis sont des **extensions** (228). Ce
   sont des structures qui ont déjà un patrimoine et des besoins immobiliers récurrents.
5. **Clients récurrents :** 32 bailleurs déposent 93 % des permis de leur famille ; 25 acteurs médico-sociaux en
   déposent 62 %. Le marché est concentré : peu d'acteurs, à fort volume.
6. **Cas Fondation Mallet :** classée « santé » (FINESS, activité hospitalière), elle dépose 33 permis
   (19 à Houdan) pour 13 268 m² surtout industriels, commerciaux et de bureaux, 103 m² seulement de service
   public. Hypothèse à vérifier : la gestion d'un patrimoine d'activité. **La famille dit qui dépose, pas ce qui
   est construit.**

## 3. Ce qui est fragile, ce qui bloque

- **L'agent apporte peu sur les 74 cas restants.** Sur 36 demandeurs recherchés, 8 seulement ont une page
  publique dont le SIREN prouve l'identité : une holding a rarement un site. Sans preuve, le modèle n'est pas
  appelé. Sur 11 demandeurs soumis : 1 proposition plausible à vérifier (Thales), 1 abstention, 1 réponse rejetée
  par le contrôle (citation retouchée), les autres périmées après durcissement des filtres. **Aucune
  proposition n'a encore été validée : les 74 restent « non déterminé ».**
- **Une erreur instructive :** pour la holding « SEQENS », l'agent a proposé « entreprise industrielle » en citant
  la page Wikipédia d'un **chimiste homonyme** ; un groupe HLM porte le même nom. Le contrôle de citation ne
  détecte pas ce cas : seule la validation humaine l'arrête. C'est pourquoi elle est obligatoire.
- **Ce que j'ai corrigé en route :** des extraits web qui laissaient passer une clause de statuts, un secteur tiré
  du seul nom de la société, et le nom d'un fondateur. Les filtres sont durcis et testés ; aucun nom de personne
  physique n'est publié.
- **Limites de la base :** identité absente pour les personnes morales hors Sirène ; ~15 % des ouvertures de
  chantier et un tiers des achèvements jamais remontés (« sans ouverture » = « non déclarée à ce jour ») ;
  indicateurs de résidence détaillés seulement depuis mai 2022 ; le demandeur n'est pas l'exploitant (VEFA).
- **Non fait :** la mesure de précision. L'outil est prêt (`sitadel evaluate`, échantillon aléatoire de 120
  demandeurs et revue des réponses de l'agent), mais les verdicts manuels ne sont pas encore remplis : je ne
  donne donc **aucun taux de précision**.

## 4. Ce que je ferais ensuite

1. Remplir les verdicts (≈ 1 h) pour publier une précision par famille avec son intervalle de confiance.
2. Pour les holdings : rattacher chaque SIREN à son groupe à partir d'une source de liens financiers plutôt
   que d'une recherche web par nom ; signaler explicitement les homonymes.
3. Lier les permis entre eux : même adresse ou même parcelle cadastrale (promoteur puis bailleur en VEFA),
   pour reconstituer « qui exploitera » plutôt que « qui dépose ».
4. Mettre le pipeline en mise à jour mensuelle et ne signaler que les nouveautés (nouveaux permis, ouvertures
   de chantier, nouveaux demandeurs ciblés).

## 5. Brancher le résultat sur la prospection

```
Sitadel (mensuel) → qualification (règles + agent + validation) → score d'opportunité
   ├─ cible : bailleur, médico-social, association/ESS — ou promoteur avec logements sociaux / résidence
   ├─ signal : permis autorisé non lancé, extension, demandeur récurrent, nouvelle commune
   └─ fiche : permis, surfaces, état, liens sources → CRM → revue par un chargé d'affaires
```

Le résultat sert à **prioriser et préparer** une démarche, pas à contacter automatiquement : aucun contact avec les
demandeurs n'a été fait dans ce test, et aucun nom de personne n'est collecté.

## 6. Temps et outils

- **Temps passé :** environ deux journées (24 et 25 novembre 2026), après une période d'examens.
- **Outils :** Claude Code (assistant de code, utilisé pour une grande partie de l'écriture du code, la refonte et
  les tests), Python, pandas, Streamlit ; agent : Gemini 3.5 Flash-Lite (offre gratuite) et Tavily (recherche web,
  offre gratuite). Données : SDES (Sitadel), API Recherche d'entreprises, nomenclatures INSEE, geo.api.gouv.fr.
- **Pour reproduire :** README du dépôt (`python -m pip install -e .`, puis `python -m sitadel pipeline` et
  `python -m streamlit run app/dashboard.py`). 66 tests, sans accès réseau.
