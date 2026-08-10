# Tests RC1 Rev.3

## Réussis dans l’environnement de construction
- Compilation Python de `app.py`.
- Analyse syntaxique AST.
- Exécution complète du schéma SQLite en mémoire.
- Vérification des colonnes `species_id` et `equipment_id` dans `donations`.
- Vérification de l’absence de fonctions Python dupliquées.
- Vérification des routes de suppression des missions et du GPS rapide.
- Vérification de la correction du conflit `title` dans le parcours public.

## À confirmer sur installation réelle
- Parcours visiteur → compte/connexion → retour vers l’action demandée.
- Affichage dynamique des formulaires de dons sur téléphone et PC.
- Synchronisation visuelle des dons d’argent dans la caisse.
- Géolocalisation GPS sur téléphone via HTTPS.
- Suppression/archivage d’une mission selon son historique.
