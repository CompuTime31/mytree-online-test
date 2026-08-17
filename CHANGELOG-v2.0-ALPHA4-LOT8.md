# MyTree Professional v2.0 Alpha 4 — Lot 8
## Équipes, Missions et Événements multi-associations

### Développements
- Contrôles serveur centralisés des liaisons Projet → Zone → Équipe.
- Vérification des droits de collaboration selon l'opération : `can_manage_missions` pour équipes/missions et `can_intervene` pour événements partenaires.
- Membres, responsables et participants limités aux adhésions actives/approuvées de l'association de la ressource.
- Création et modification d'équipe sécurisées contre l'injection d'IDs d'une autre association.
- Demande pour rejoindre une équipe autorisée uniquement depuis la même association active.
- Missions : projet, zone, équipe, responsable et participants validés côté serveur.
- Événements : projet, zone et équipe validés côté serveur ; GPS/carte conservés.
- Codes équipe et mission générés côté serveur et non modifiables par le formulaire.
- Ajout d'un code unique `EVT-xxxx` pour les événements, avec index unique SQLite.
- Lecture des missions/événements de projets collaboratifs autorisée au propriétaire/partenaire via `can_view`.
- Actions de gestion masquées lorsque l'association active ne possède pas la mission ou l'événement.
- Sélecteurs de projets limités aux projets propres ou collaborations disposant du droit requis.
- Sélecteurs d'équipes limités à l'association active.
- Ajout du sélecteur carte/GPS aux formulaires de mission.

### Compatibilité
- Les lots Alpha 4 précédents restent séparés et ne sont pas écrasés.
- Migration additive : colonne `events.code` et index unique conditionnel.
