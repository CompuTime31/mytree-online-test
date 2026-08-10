# My Tree Professional — v1.5.1 Lot 1

Cette version finalise le premier lot fonctionnel : **Utilisateurs et Bénévoles**.

## Installation Windows

1. Extraire le ZIP.
2. Double-cliquer sur `run-windows.bat`.
3. Ouvrir `http://localhost:8080`.

Compte initial :

- Identifiant : `admin`
- Mot de passe : `admin123`

## Mise à jour d’une base existante

Copier le fichier `mytree.db` de la version précédente dans le dossier de cette version avant le premier démarrage. La migration est automatique et non destructive.

Effectuer une copie de sauvegarde de `mytree.db` avant toute mise à jour.

## Nouveaux accès

- `/volunteers/new` : nouveau bénévole.
- `/volunteers/<id>` : fiche bénévole.
- `/users/new` : nouvel utilisateur.
- `/users/<id>/edit` : modification utilisateur.

Consulter `CHANGELOG-v1.5.1-LOT1.txt` et `TESTS-v1.5.1-LOT1.txt` pour les détails.
