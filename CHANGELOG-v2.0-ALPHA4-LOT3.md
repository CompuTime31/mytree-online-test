# MyTree Professional v2.0 Alpha 4 — Lot 3 Permissions

## Développement
- Permissions recalculées association par association à partir de `association_memberships`.
- Un rôle administrateur dans une association ne donne plus de privilège dans une autre association.
- Matrice centrale `ASSOCIATION_ROLE_PERMISSIONS` pour `association_admin/admin` et `volunteer`.
- Contrôle serveur strict du contexte actif et de l'adhésion approuvée.
- Réponses HTTP 403 pour les permissions associatives refusées.
- Conservation des permissions historiques uniquement dans l'espace Personnel.
- Ajout du journal `association_audit_logs` pour tracer les refus d'autorisation.
- Ajout des codes de permissions granulaires préparant projets, zones, arbres, missions, équipes, rapports et collaborations.
- Le garde tenant Alpha 4 du Lot 1 reste actif pour vérifier l'appartenance de la ressource à l'association.

## Sécurité
La chaîne de contrôle est désormais : utilisateur connecté -> contexte association -> adhésion approuvée -> rôle dans cette association -> permission -> association propriétaire de la ressource.
