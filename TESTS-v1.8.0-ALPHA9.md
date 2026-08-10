# Tests — v1.8.0 Alpha 9

## Tests automatisés réalisés
- Compilation Python de `app.py` : réussie.
- Analyse syntaxique AST : réussie.
- Exécution du schéma SQLite dans une base mémoire : réussie (52 tables).
- Présence des routes de modification/suppression contrôlée : vérifiée.
- Présence des 26 communes d'Oran dans le seed : vérifiée.
- Vérification de l'intégrité de l'archive ZIP : réussie.

## Tests fonctionnels à réaliser sur le PC et le téléphone
1. Connexion administrateur et bénévole avec « Se souvenir de moi ».
2. Vérifier la navigation mobile verticale dans l'espace bénévole.
3. Vérifier la navigation publique verticale et le bouton Connexion.
4. Visiteur → Faire un don → créer un compte → redirection vers le formulaire de don.
5. Bénévole → Faire un don → notification administrateur → accepter/refuser.
6. Modifier et supprimer/archiver un don.
7. Supprimer ou archiver un projet, une zone, une équipe, un utilisateur et une planification.
8. Vérifier la liste des communes lorsque la wilaya Oran est choisie.

## Limite de l'environnement de construction
Les tests HTTP complets avec Flask et navigateur mobile n'ont pas été exécutés dans l'environnement de construction, car Flask n'y est pas installé. Ils doivent être confirmés sur l'installation Windows du projet.
