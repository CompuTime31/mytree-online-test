# Tests — RC1 Rev.12

## Vérifications automatiques effectuées
- Compilation Python (`py_compile`) : OK.
- Analyse AST : OK.
- Création du schéma SQLite sur base vierge : OK (58 tables).
- Insertion de contrôle dans `purchase_groups` / `purchase_items` : OK.
- Présence des API projet → zones / valeurs par défaut et équipe → responsable : OK.
- Présence des workflows multi-achats et codes automatiques : OK.
- Génération du composant GPS/carte : OK.
- Intégrité du ZIP : OK.

## Tests en ligne à réaliser
- Migration de la base Online Test Rev.11 existante.
- Zone : héritage wilaya/commune, limites d’objectif et carte/GPS.
- Équipe : filtrage projet/zone, création avec plusieurs bénévoles, modification des membres.
- Mission : code automatique, filtrage des zones, responsable prérempli.
- Événement : carte et GPS.
- Caisse : achat multi-espèces / multi-matériels, Dons/Cotisations/Mixte et stock.
- FR / AR / EN, notamment affichage RTL en arabe.
- Synchronisation des communes nationales sur Railway/serveur connecté.
- Navigation téléphone et messages de confirmation.
