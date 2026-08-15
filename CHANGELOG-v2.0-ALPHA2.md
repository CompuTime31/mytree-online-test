# MyTree Professional v2.0 Alpha 2 — Multi-Associations Online Test

## Nouveautés
- Sélecteur de contexte actif : Personnel / Association / Global MyTree pour le Super Admin.
- Mémorisation du contexte par utilisateur dans `user_contexts`.
- Un utilisateur peut basculer entre plusieurs associations approuvées sans recréer de compte.
- Droits d’administration adaptés au contexte actif : le Super Admin reste global, l’administrateur d’association administre son association active.
- Isolation par `association_id` renforcée pour les projets, zones, équipes, missions, événements, arbres, dons, caisse et stock.
- Protection des fiches par identifiant pour empêcher l’accès direct aux données d’une autre association.
- Filtres et listes de projets/zones limités au contexte actif.
- Équipes : sélection des bénévoles limitée aux membres approuvés de l’association active.
- Carte/API arbres : le contexte Personnel / Association / Global est appliqué aux arbres affichés.
- Migration non destructive des utilisateurs historiques vers l’association principale afin de préserver l’accès aux anciennes données.
- Colonnes `association_id` préparées sur des tables supplémentaires de stock et d’exploitation.

## Compatibilité
- Compatible avec la base v2.0 Alpha 1 et les données v1.8 migrées.
- Conserve le volume Railway `/data`.
- Les données historiques restent affectées à l’association principale créée lors de la migration v2.0.

## Reporté à Alpha 3
- Symboles uniques avancés par association sur la carte.
- Filtres cartographiques multi-associations avancés.
- Collaboration entre associations par invitation.
