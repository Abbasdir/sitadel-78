# Dictionnaire — sitadel_78_pc_personnes_morales.csv

Source : SDES Sitadel, millésime 2026-10, Yvelines, permis de construire déposés par des personnes morales. 1 ligne par permis.

| colonne | description |
|---|---|
| `NUM_DAU` | numéro du permis de construire |
| `COMM` | code INSEE de la commune |
| `COMMUNE` | nom de la commune (geo.api.gouv.fr) |
| `ADRESSE_TERRAIN` | adresse du terrain (Sitadel) |
| `FICHIER` | fichier(s) Sitadel où figure le permis : logements, locaux, logements+locaux |
| `ETAT` | autorisé / commencé / terminé / annulé (ETAT_DAU) |
| `DATE_AUTORISATION` | date réelle d'autorisation |
| `DATE_OUVERTURE_CHANTIER` | date réelle de DOC (si déclarée) |
| `DATE_ACHEVEMENT` | date réelle de DAACT (si déclarée) |
| `DELAI_AUT_DOC_JOURS` | jours entre autorisation et ouverture de chantier |
| `SIREN_DEM` | SIREN du demandeur |
| `DENOMINATION` | dénomination (masquée si risque de nom de personne) |
| `CJ` | catégorie juridique au permis |
| `APE` | code APE au permis |
| `FAMILLE` | famille du demandeur |
| `SOUS_FAMILLE` | précision |
| `CONFIANCE` | haute / moyenne / basse |
| `REGLE_APPLIQUEE` | règle de classement déclenchée (ou « llm ») |
| `SIGNAL` | signal public qui fonde la décision |
| `FAMILLE_CIBLE` | bailleur social, association/ESS ou médico-social |
| `NATURE_PROJET` | nouvelle construction / travaux sur existant |
| `EXTENSION` | indicateur d'extension |
| `NB_LOGEMENTS_CREES` | logements créés |
| `DONT_LOCATIFS_SOCIAUX` | dont financés par prêt locatif social |
| `SURF_HAB_CREEE_M2` | surface d'habitation créée |
| `SURF_LOCAUX_CREEE_M2` | surface de locaux créée |
| `NB_CHAMBRES` | chambres (hébergement) |
| `SERVICE_PUBLIC` | type de service public ou d'intérêt collectif |
| `RESIDENCE` | type de résidence déclaré |
| `SIGNAUX_MEDICO_SOCIAUX` | signaux projet médico-social (étape 3) |
| `SOURCE_PERMIS_URL` | enregistrement Sitadel du permis (CSV public, API DiDo) |
| `SOURCE_PERMIS_URL_2` | idem dans le 2e fichier (permis mixtes) |
| `SOURCE_JEU_DE_DONNEES` | page catalogue SDES du fichier |
| `SIREN_URL` | fiche publique du demandeur |
