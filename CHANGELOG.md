# Lot 12 — FIXED7 Profile Switch

## Sécurité des rôles
- `association_admin` ne devient jamais `super_admin`.
- Le rôle global du compte reste indépendant des rôles associatifs.
- Le changement de profil ne modifie jamais `users.role`.

## Bascule façon Facebook
- Profil Personnel : identité de la personne.
- Profil Association : identité visuelle de l'association.
- Le header affiche l'association comme identité active, avec le rôle associatif.
- Changer de profil redirige vers l'accueil du profil choisi.
- Un même compte peut avoir plusieurs associations avec des rôles différents.

## Permissions
- En profil Association, les permissions sont prises uniquement dans `association_memberships`.
- Un administrateur de l'Association A n'obtient aucun droit global sur MyTree.
- Les droits de l'Association A ne s'appliquent pas à l'Association B.

## Interface
- Nouvel accueil `/association`.
- Navigation Association spécifique.
- Navigation mobile spécifique au profil Association.
- Le profil Personnel reste disponible en permanence.

Aucune migration SQLite ajoutée.
