# Lot 12 — FIXED2
- Corrige réellement le périmètre Bénévoles en contexte Personnel pour le super-admin.
- Global super-admin : tous les bénévoles.
- Personnel super-admin : liste administrative des bénévoles.
- Association : uniquement les membres approuvés de l'association, puis filtrage sur le rôle bénévole.
- Détection du rôle bénévole compatible `roles.name` et ancien champ `users.role`.
- Ajout du marqueur visible `Lot 12 — FIXED2` dans l'interface.
- Aucune migration SQLite.
