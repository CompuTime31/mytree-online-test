# MyTree Professional v2.0 Alpha 4 — Lot 7
## Cohérence métier Projet → Zone → Arbre

### Implémenté
- Validation de la commune par rapport à la wilaya lors de la création/modification d’un projet.
- Blocage de la réduction de l’objectif d’un projet sous les quantités déjà réparties dans les zones ou déjà plantées.
- `target_trees = 0` conserve le sens historique MyTree : objectif non défini / illimité.
- Synchronisation de la localisation d’un projet vers ses zones et ses arbres lors d’un changement Wilaya/Commune.
- Création de zone réservée à l’association propriétaire du projet.
- Modification de zone réservée à l’association propriétaire du projet.
- Wilaya et commune d’une zone héritées côté serveur depuis le projet ; les valeurs forcées par le navigateur sont ignorées.
- Rattachement `association_id` de la zone hérité du projet.
- Blocage du déplacement d’une zone vers un autre projet lorsqu’elle contient déjà des arbres actifs.
- Blocage d’un objectif de zone inférieur au nombre d’arbres déjà présents.
- Contrôle de capacité avant nouvelle plantation : objectif projet et objectif zone.
- Vérification systématique `zone.project_id == project_id`.
- Vérification de cohérence géographique Zone ↔ Projet.
- Plantation sur projet partenaire autorisée uniquement si la collaboration active possède `can_add_tree`.
- Modification d’un arbre : validation du nouveau couple Projet/Zone et synchronisation Wilaya/Commune/Association.
- Plantation en série : mêmes contrôles de capacité et héritage géographique/associatif.
- Duplication de projet : maintien explicite de l’association propriétaire.
- Suppression de zone avec historique : archivage obligatoire, suppression physique interdite.

### Compatibilité
- Les lots Alpha 4 précédents restent inchangés.
- Les arbres hors projet restent possibles selon le fonctionnement existant.
