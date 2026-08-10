# Tests — v1.8.0 Alpha 8

## Tests exécutés

- Compilation Python de `app.py` avec `py_compile` : réussie.
- Analyse syntaxique AST : réussie.
- Exécution du schéma SQLite dans une base en mémoire : réussie.
- Présence vérifiée des tables `project_phases`, `operational_tasks` et `volunteer_time_logs`.
- Vérification statique des nouvelles routes : réussie.
- Contrôle d'intégrité de l'archive ZIP : réussi.

## Limite de l'environnement

Les tests HTTP Flask n'ont pas été exécutés, car le paquet Flask n'est pas installé dans l'environnement de construction. Les essais fonctionnels complets doivent être réalisés après installation de `requirements.txt`.
