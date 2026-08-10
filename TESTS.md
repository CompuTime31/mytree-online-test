- v1.8.0 Alpha 10 : compilation, AST, schéma SQLite et archive validés ; tests HTTP à faire sur installation réelle.
# Tests — My Tree Professional v1.5.2 Lot 2

## Réussis dans l'environnement de génération
- Compilation Python de `app.py`.
- Analyse AST du code.
- Création du schéma SQLite en mémoire.
- Migration additive des colonnes Lot 2.
- Insertions représentatives Projet → Zone → Équipe.
- Contrôle des routes déclarées en double.
- Vérification d'intégrité de l'archive ZIP.

## À exécuter sur le poste utilisateur
- Démarrage Flask/Waitress.
- Connexion administrateur.
- Création/modification/archivage/réactivation des trois modules.
- Demande d'adhésion bénévole puis acceptation/refus administrateur.
- Navigation complète et contrôle des droits.
