# Tests v1.5.3 Lot 3 Alpha 2

## Réalisés
- Compilation Python de `app.py` : réussie.
- Analyse syntaxique AST : réussie.
- Création SQLite en mémoire depuis le schéma : réussie.
- Présence des nouvelles colonnes `species` : réussie.
- Vérification des routes Lot 3 et absence de doublons : réussie.
- Vérification des liens Fiche, Carte et arrosage prérempli : réussie.
- Vérification d’intégrité de l’archive ZIP : réussie.

## Limite de l’environnement
- Les tests HTTP Flask complets n’ont pas été exécutés car Flask n’est pas installé dans l’environnement de construction. Ils doivent être réalisés après `pip install -r requirements.txt` sur la machine de test.
