# MyTree Professional v2.0 Alpha 4 — Lot 6
## Moteur de filtres commun

- Contrat de filtres commun : wilaya, commune, projet, zone, espèce, bénévole, état, type d'action et période.
- Validation serveur des `project_id`, `zone_id`, `volunteer_id` et `association_id` afin de bloquer les filtres forgés hors contexte.
- Projets proposés selon l'association active et les collaborations acceptées avec droit de consultation.
- Zones dépendantes des projets réellement accessibles.
- Communes dépendantes de la wilaya sélectionnée.
- Arbres : ajout bénévole + période et application du périmètre multi-associations.
- Missions : filtres géographiques, projet, zone, type, statut, priorité, bénévole et période.
- Événements : filtres géographiques, projet, zone, type, statut et période.
- Carte commune : reprise du même contrat de filtres et même validation serveur via `/api/map-data`.
- Rapports opérationnels et export CSV : reprise des filtres projet/zone/espèce/bénévole/période.
- APIs Projet→Zones et valeurs par défaut protégées contre l'accès direct à un projet non autorisé.
- Compatibilité maintenue avec les anciens paramètres `event_type` et `mission_type` via `action_type`.
