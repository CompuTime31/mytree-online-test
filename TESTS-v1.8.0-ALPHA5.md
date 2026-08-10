# Tests — v1.8.0 Alpha 5

## Tests exécutés

- Compilation Python de `app.py` : réussie.
- Analyse AST de `app.py` et `data_catalogs.py` : réussie.
- Contrôle des routes Flask déclarées : 114 routes, aucun doublon d’URL après correction.
- Présence vérifiée des routes publiques et terrain : `/public`, `/public/projects`, `/public/events`, `/public/map`, `/public/species`, `/public/help`, `/public/register`, `/volunteer/field`.
- Exécution du schéma SQLite en mémoire : réussie, 49 tables créées.
- Vérification de l’intégrité de l’archive ZIP finale : réussie.

## Tests non exécutés dans l’environnement de génération

- Tests HTTP avec le client Flask non exécutés, car le module Flask n’est pas installé dans l’environnement de génération.
- Test caméra, GPS, affichage Leaflet et ergonomie sur téléphone réel à effectuer lors du test terrain.

## Contrôles recommandés après installation

1. Ouvrir `/public` sur PC et téléphone.
2. Tester la barre mobile publique.
3. Ouvrir les pages Projets, Événements, Carte, Encyclopédie et Je veux aider.
4. Créer un compte via `/public/register`.
5. Se connecter en bénévole et ouvrir `/volunteer/field`.
6. Vérifier la caméra et le GPS depuis une connexion HTTPS.
