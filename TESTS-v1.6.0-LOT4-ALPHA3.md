# Tests — v1.6.0 Lot 4 Alpha 3

- Compilation Python : réussie.
- Analyse syntaxique AST : réussie.
- Création du schéma SQLite en mémoire : réussie.
- Présence de la table `watering_batches` : vérifiée.
- Migration `batch_id` prévue pour les bases existantes : vérifiée dans le code.
- Routes Arrosage groupé, Plantation en série et Interventions : vérifiées.
- Contrôle des identifiants d’arbres soumis avant arrosage : présent.
- Intégrité ZIP : vérifiée.

Les tests HTTP Flask complets doivent être confirmés sous Windows, car Flask n’est pas disponible dans l’environnement de construction hors connexion.
