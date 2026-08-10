# Tests — MyTree Professional v1.8.0 Alpha 7

## Réalisés

- Compilation Python de `app.py` avec `python -m py_compile app.py` : réussie.
- Analyse syntaxique AST : réussie.
- Extraction et exécution du schéma SQLite dans une base temporaire : réussie.
- Vérification de la présence des nouvelles routes : réussie.
- Vérification des fonctions d’enregistrement des champs botaniques : réussie par inspection statique.
- Vérification de l’intégrité de l’archive ZIP : réussie.

## Non exécutés dans l’environnement de construction

Les tests HTTP Flask n’ont pas pu être exécutés, car le paquet `flask` n’est pas installé dans l’environnement de construction. Le fichier `requirements.txt` reste fourni pour l’installation normale du projet.
