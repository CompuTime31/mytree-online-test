# Tests — Alpha 4 Lot 5 Carte commune

## Contrôles serveur obligatoires
1. Association A : voir ses propres projets/zones/arbres/événements/missions géolocalisés.
2. Association A : ne jamais voir les données privées de l'Association B hors collaboration.
3. Projet A partagé avec B, `can_view=1` : B voit le projet et ses ressources cartographiques.
4. Collaboration pending/rejected/ended/left : aucune ressource partenaire sur la carte.
5. Collaboration accepted avec `can_view=0` : aucune ressource partenaire.
6. Changer d'association active puis réutiliser l'ancienne URL `/map?...` : les données sont recalculées côté serveur.
7. Contexte Personnel : uniquement les arbres individuels de l'utilisateur connecté.
8. Super Admin / Global : accès cartographique global.

## Filtres
- Type arbre/projet/zone/événement/mission.
- Projet autorisé uniquement.
- Zone autorisée uniquement.
- Santé et arrosage appliqués aux arbres.
- Réinitialisation complète.

## PC ↔ téléphone
- Carte chargée sur PC et téléphone.
- Boutons/filtres utilisables au tactile.
- GPS accepté : position + tri par distance.
- GPS refusé : message sans blocage de la carte.
- Popup ouvre la fiche correspondante.

## Régression
- `/trees/<id>/map` reste disponible.
- Carte publique `/public/map` reste indépendante.
- Carte opérationnelle `/operations/map` n'est pas supprimée dans ce lot.
