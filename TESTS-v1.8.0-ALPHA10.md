# Tests — MyTree Professional v1.8.0 Alpha 10

## Tests exécutés dans l’environnement de construction
- Compilation Python (`python -m py_compile app.py`) : réussie.
- Analyse syntaxique AST : réussie.
- Exécution du schéma SQLite en mémoire : réussie.
- Contrôle d’intégrité SQLite en mémoire : `ok`.
- Vérification statique des nouvelles routes de sauvegarde : réussie.
- Vérification statique des composants mobiles : réussie.
- Vérification de l’intégrité de l’archive ZIP : réussie.

## Tests à réaliser sur l’installation réelle
- Connexion administrateur et bénévole.
- Accueil bénévole sur Android et iPhone.
- Ouverture de chaque bouton vertical dans une page distincte.
- Bouton Retour et barre inférieure.
- Caméra, GPS, QR Code et photos.
- Téléchargement d’une sauvegarde.
- Restauration d’une copie de test, jamais directement sur la base de production sans sauvegarde préalable.

## Limite de l’environnement
Flask n’était pas installé dans l’environnement de construction. Les tests HTTP complets doivent être exécutés sur le PC d’installation avec les dépendances du fichier `requirements.txt`.
