# MyTree Professional v1.5.3 — Lot 3 Alpha 3

## Fonctionnalités réelles ajoutées

- Fiche arbre professionnelle enrichie : identification, espèce scientifique, projet, zone, planteur, état, GPS, notes et QR individuel.
- Galerie de photos par arbre avec URL, légende, auteur et date.
- Observations terrain avec mise à jour de l’état sanitaire.
- Modification GPS assistée par la géolocalisation du navigateur.
- Historique des changements GPS avec ancienne et nouvelle position, précision, auteur et motif.
- Historique unifié de l’arbre : arrosages, observations, photos et changements GPS.
- Actions rapides sur la fiche et dans le popup de la carte : fiche, arrosage, photo, observation et GPS.
- Carte centrée sur l’arbre avec position utilisateur et accès à l’itinéraire OpenStreetMap.

## Base de données

Nouvelles tables :

- `tree_photos`
- `tree_observations`
- `tree_gps_history`

Les tables sont créées automatiquement au démarrage sans supprimer les données existantes.
