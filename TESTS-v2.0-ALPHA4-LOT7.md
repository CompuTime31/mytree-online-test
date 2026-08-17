# Tests — MyTree Professional v2.0 Alpha 4 Lot 7

## 1. Projet
1. Créer un projet avec Wilaya A + Commune appartenant à Wilaya B → refus.
2. Créer un projet cohérent → succès.
3. Créer des zones totalisant 100 arbres puis réduire l’objectif projet à 80 → refus.
4. Projet avec 120 arbres rattachés, réduire l’objectif à 100 → refus.
5. Changer Wilaya/Commune du projet → vérifier que toutes les zones et arbres du projet héritent de la nouvelle localisation.

## 2. Zone
1. Créer une zone dans un projet → vérifier Wilaya/Commune identiques au projet.
2. Modifier le POST manuellement avec une autre Wilaya/Commune → vérifier que le serveur conserve celles du projet.
3. Somme objectifs zones > objectif projet → refus.
4. Zone avec 25 arbres : passer objectif à 20 → refus.
5. Zone avec arbres : tenter de changer de projet → refus.
6. Zone vide : changement vers un autre projet propriétaire → autorisé et géographie resynchronisée.
7. Depuis une association partenaire, tenter de créer/modifier une zone du projet propriétaire → HTTP 403.

## 3. Arbre
1. Ajouter arbre avec Zone B mais Projet A → refus.
2. Ajouter arbre dans une zone dont l’objectif est atteint → refus.
3. Ajouter arbre dans un projet dont l’objectif est atteint → refus.
4. Ajouter arbre à un projet partenaire sans `can_add_tree` → refus.
5. Ajouter arbre à un projet partenaire avec `can_add_tree=1` → autorisé.
6. Modifier un arbre vers une zone incompatible → refus.
7. Modifier un arbre vers une zone valide → Wilaya/Commune/Association doivent suivre le projet.
8. Plantation en série jusqu’à capacité de zone puis un arbre supplémentaire → dernier ajout refusé.

## 4. Suppression
1. Zone sans dépendance → suppression physique autorisée.
2. Zone avec arbre, équipe, mission, événement ou tâche → archivage, pas de suppression physique.
3. Projet avec historique → archivage selon comportement existant.

## 5. Régression
- Carte commune Lot 5.
- Filtres communs Lot 6.
- Collaboration Lot 4.
- Permissions par association Lot 3.
- Vérification PC et téléphone des formulaires Projet/Zone/Plantation.
