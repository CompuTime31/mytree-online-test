# MyTree Professional v2.0 Alpha 4 — Lot 5
## Carte commune multi-associations

- Nouvelle API serveur `/api/map-data` centralisant les ressources cartographiques.
- Carte commune pour arbres, projets, zones, événements et missions.
- Respect du contexte actif : Personnel, Association ou Global Super Admin.
- En contexte Association : projets propres + collaborations acceptées avec `can_view=1` uniquement.
- Les ressources d'un projet partenaire ne sont affichées que si `collaboration_access(..., can_view)` l'autorise.
- Les filtres Projet et Zone sont construits uniquement avec les projets accessibles.
- Filtrage cartographique par type de ressource, projet, zone, santé et état d'arrosage.
- Ajout d'une légende commune et de marqueurs distincts par type.
- GPS utilisateur et liste des 20 éléments les plus proches.
- Gestion explicite du refus/indisponibilité de géolocalisation.
- Interface responsive conservée : carte pleine hauteur adaptée sur téléphone.
- VERSION mise à jour vers Alpha 4 Lot 5.
