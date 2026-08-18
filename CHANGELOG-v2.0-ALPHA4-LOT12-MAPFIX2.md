# Alpha 4 Lot 12 — MapFix 2

## Correction critique carte connectée
- Correction du crash de `/api/map-data` lorsqu'une ressource sans colonnes GPS (ex. `projects`) est incluse dans la carte.
- Le helper de marqueurs vérifie désormais l'existence de `latitude` et `longitude` avant lecture.
- Les ressources non géolocalisables sont ignorées sans bloquer les arbres.
- La correction MapFix 1 sur les anciens arbres `association_id IS NULL` rattachés à un projet de l'association est conservée.

## Filtres
- Généralisation du bouton unique `🔎 Filtre` à tous les formulaires GET contenant au moins deux critères métier.
- Les filtres restent masqués au repos.
- Clic sur `Filtre` : affichage de tous les critères disponibles sur l'écran.
- Affichage du nombre de filtres actifs.
- Panneau plein écran adapté au téléphone.
- Le formulaire de carte conserve son panneau Filtre spécifique déjà validé.
