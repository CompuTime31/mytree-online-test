# Tests — Lot 3 Alpha 3

## Réussis

- Compilation Python de `app.py` avec `py_compile`.
- Analyse AST complète du fichier.
- Exécution du schéma SQLite dans une base en mémoire.
- Vérification de la création des trois nouvelles tables.
- Vérification statique des nouvelles routes photo, observation, GPS et historique.
- Vérification de l’intégrité de l’archive ZIP.

## Limite de l’environnement

Les tests HTTP Flask n’ont pas pu être exécutés dans l’environnement de génération, car les paquets Flask ne sont pas disponibles hors connexion. Le fichier `run-windows.bat` installe les dépendances sur le PC Windows avant le lancement.
