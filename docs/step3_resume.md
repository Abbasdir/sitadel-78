# Étape 3 — Patterns (Yvelines, PC de personnes morales, Sitadel millésime 2026-10)

Base : 7092 permis distincts, 3957 demandeurs. Détail ligne à ligne (avec liens sources) dans `data/processed/patterns/`.

## 1. Projets médico-sociaux × famille du porteur

**479 permis** portent au moins un signal médico-social (6.8% des PC de personnes morales). Répartition par famille du porteur : collectivite_public 143, medico_social_sante 131, promoteur_prive 69, sci_fonciere 59, bailleur_social 34, entreprise_autre 23, association_ess 14, non_determine 6.

| signal \ famille | association_ess | bailleur_social | collectivite_public | entreprise_autre | medico_social_sante | non_determine | promoteur_prive | sci_fonciere | total |
|---|---|---|---|---|---|---|---|---|---|
| chambres (hors hôtel) | 2 | 3 | 2 | 4 | 4 | 0 | 7 | 3 | 25 |
| résidence handicapés | 0 | 1 | 0 | 0 | 3 | 0 | 0 | 0 | 4 |
| résidence personnes âgées | 0 | 3 | 0 | 2 | 0 | 0 | 25 | 5 | 35 |
| résidence sociale | 0 | 13 | 9 | 1 | 1 | 1 | 4 | 0 | 29 |
| service public : action sociale | 10 | 8 | 92 | 11 | 55 | 3 | 27 | 25 | 231 |
| service public : santé | 4 | 8 | 41 | 7 | 72 | 2 | 15 | 27 | 176 |
| total | 16 | 36 | 144 | 25 | 135 | 6 | 78 | 60 | 500 |

Porteurs ciblés les plus présents : AVENIR APEI (8, medico_social_sante); CENTRE HOSPITALIER INTERCOMMUNAL DE POISSY SAINT GERMAIN (6, medico_social_sante); LES COLORIES (6, medico_social_sante); CENTRE HOSPITALIER DE PLAISIR (5, medico_social_sante); ASSOCIATION DELOS APEI 78 (5, medico_social_sante); CDC HABITAT SOCIAL SOCIETE ANONYME D'HABITATIONS A LOYER MODERE (4, bailleur_social); LA MAISON BLEUE (4, medico_social_sante); CENTRE HOSPITALIER DE VERSAILLES (4, medico_social_sante).

## 2. Portefeuille : PC autorisés 2024-2026 sans ouverture de chantier (familles cibles)

**81 permis** autorisés 2024-2026 sans ouverture de chantier déclarée, portés par les familles cibles :

| famille | permis | demandeurs | logements | dont_LLS | m2_locaux | au_dela_delai_median | delai_median_mois (référence) |
|---|---|---|---|---|---|---|---|
| association_ess | 25 | 19 | 1 | 0 | 12764 | 23 | 4.4 |
| bailleur_social | 33 | 15 | 989 | 790 | 745 | 26 | 9.5 |
| medico_social_sante | 23 | 16 | 26 | 0 | 12799 | 23 | 3.8 |

Demandeurs les plus présents : IMMOBILIERE 3F (8); CDC HABITAT SOCIAL SOCIETE ANONYME D'HABITATIONS A LOYER MODERE (5); ASSOCIATION DIOCESAINE DE VERSAILLES (5); CENTRE HOSPITALIER THEOPHILE ROUSSEL (3); AVENIR APEI (3); FEDERATION FRANCAISE FOOTBALL - FFF (3); LES RESIDENCES SOCIETE ANONYME D'HABITATIONS A LOYER MODERE (3); ENTREPRISE SOCIALE POUR L'HABITAT DOMNIS (2).

Attention : environ 15 % des ouvertures de chantier n'arrivent jamais dans Sitadel (note SDES). « Sans DOC » veut dire « non déclarée à ce jour », pas « projet bloqué ».

## 3. Constructeurs récurrents par famille

**478 demandeurs récurrents** (≥ 3 PC) :

| famille | recurrents | permis | part_des_permis_famille |
|---|---|---|---|
| association_ess | 17 | 93 | 44% |
| bailleur_social | 32 | 367 | 93% |
| collectivite_public | 130 | 934 | 79% |
| entreprise_autre | 76 | 463 | 40% |
| medico_social_sante | 25 | 143 | 62% |
| non_determine | 5 | 24 | 23% |
| promoteur_prive | 101 | 691 | 41% |
| sci_fonciere | 92 | 398 | 19% |

**Top bailleur_social**

| DENOM_DEM | n_pc | premiere_annee | derniere_annee | logements_crees | dont_LLS | m2_locaux_crees |
|---|---|---|---|---|---|---|
| IMMOBILIERE 3F | 48 | 2013 | 2026 | 1552 | 1358 | 1545 |
| LES RESIDENCES SOCIETE ANONYME D'HABITATIONS A LOYER MODERE | 36 | 2013 | 2026 | 700 | 462 | 2357 |
| SEQENS SOCIETE ANONYME D'HABITATIONS A LOYER MODERE | 32 | 2013 | 2025 | 1059 | 879 | 885 |
| ANTIN RESIDENCES SA HABITAT LOYER MODERE | 30 | 2013 | 2025 | 1442 | 935 | 9412 |
| ENTREPRISE SOCIALE POUR L'HABITAT DOMNIS | 29 | 2013 | 2025 | 933 | 728 | 377 |

**Top association_ess**

| DENOM_DEM | n_pc | premiere_annee | derniere_annee | logements_crees | dont_LLS | m2_locaux_crees |
|---|---|---|---|---|---|---|
| ASSOCIATION DIOCESAINE DE VERSAILLES | 19 | 2013 | 2025 | 25 | 0 | 4315 |
| FEDERATION FRANCAISE FOOTBALL - FFF | 12 | 2013 | 2026 | 0 | 0 | 10219 |
| OGEC SAINTE THERESE | 7 | 2013 | 2016 | 7 | 0 | 1046 |
| FONCIERE D'HABITAT ET HUMANISME | 7 | 2013 | 2023 | 38 | 35 | 0 |
| SCOUTS ET GUIDES DE FRANCE | 6 | 2014 | 2023 | 1 | 0 | 3793 |

**Top medico_social_sante**

| DENOM_DEM | n_pc | premiere_annee | derniere_annee | logements_crees | dont_LLS | m2_locaux_crees |
|---|---|---|---|---|---|---|
| FONDATION MALLET | 33 | 2015 | 2025 | 11 | 0 | 13268 |
| AVENIR APEI | 10 | 2016 | 2026 | 8 | 0 | 3707 |
| CENTRE HOSPITALIER INTERCOMMUNAL DE POISSY SAINT GERMAIN | 8 | 2017 | 2023 | 0 | 0 | 22542 |
| LES COLORIES | 7 | 2018 | 2022 | 0 | 0 | 149 |
| APAJH COMITE DES YVELINES | 6 | 2014 | 2025 | 0 | 0 | 1146 |

## 4. Extensions portées par associations / médico-social

**228 extensions** portées par des associations/ESS ou des acteurs médico-sociaux (52% de leurs PC ; association_ess 98/210, medico_social_sante 130/231).

| famille | sous_famille | extensions | m2_crees |
|---|---|---|---|
| association_ess | association | 65 | 20378 |
| medico_social_sante | petite enfance (crèches) | 31 | 1405 |
| medico_social_sante | santé | 23 | 7225 |
| association_ess | congrégation / culte | 20 | 4191 |
| medico_social_sante | action sociale sans hébergement | 19 | 5716 |
| medico_social_sante | établissement d'hospitalisation | 16 | 27279 |
| medico_social_sante | hébergement social handicap mental | 8 | 3883 |
| association_ess | entreprise de l'ESS | 8 | 9752 |
| medico_social_sante | aide par le travail (ESAT) | 7 | 974 |
| medico_social_sante | accueil sans hébergement adultes handicapés | 5 | 1798 |

Agrandissent plusieurs fois : FONDATION MALLET (16); ASSOCIATION DIOCESAINE DE VERSAILLES (11); CENTRE HOSPITALIER INTERCOMMUNAL DE POISSY SAINT GERMAIN (6); LES COLORIES (6); AVENIR APEI (5); ASSOCIATION DELOS APEI 78 (5); ASS L ARCHE D AIGREFOIN (4); BABYBULLE (4).

## 5. Étude de cas : Fondation Mallet

Classée **medico_social_sante** (santé) via « entité juridique FINESS 780003638 + APE 86.10Z ». **33 PC** de 2015 à 2025, dont 16 extensions ; états : autorisé 25, terminé 5, commencé 3.

Communes : Houdan (19), Richebourg (5), Bazainville (4), Maulette (3), Thoiry (1), Orvilliers (1).

Surfaces créées : 13268 m² de locaux, dont industrie 5428 m², commerce 3148 m², bureaux 1632 m², entrepôt 1612 m², agricole 1345 m², habitation 823 m², service public 103 m² ; 11 logement(s).

Lecture : les permis déclarent très peu de surface « service public / santé » : la fondation dépose surtout des locaux d'activité (commerce, bureaux, industrie, entrepôt), majoritairement dans une même commune. Hypothèse à vérifier (pas tranchée par les données) : gestion d'un patrimoine foncier d'activité, distinct de l'activité hospitalière qui fonde son classement. Ce cas montre la limite d'un classement par demandeur : la famille dit qui dépose, pas ce qui est construit.
