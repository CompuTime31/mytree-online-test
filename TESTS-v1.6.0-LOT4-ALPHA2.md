# Tests — v1.6.0 Lot 4 Alpha 2

- [x] Compilation Python (`python -m py_compile app.py`).
- [x] Schéma SQLite extrait et exécuté dans une base temporaire.
- [x] Vérification de présence des routes `/projects`, `/zones`, `/zones/new`, `/zones/<id>`, `/team-requests`.
- [x] Vérification de l’absence de doublons de routes exactes.
- [x] Vérification des liens de navigation séparés Projets / Zones.
- [x] Vérification des boutons Enregistrer / Annuler du formulaire Zone.
- [x] Vérification de l’intégrité ZIP.
- [ ] Tests HTTP Flask sous Windows : non exécutés dans l’environnement de génération, car les dépendances Flask ne sont pas disponibles hors connexion.
