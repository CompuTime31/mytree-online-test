# Hotfix FilterUI1 FIXED 1

- Corrige l'erreur Railway `app.page() got multiple values for keyword argument 'volunteers'`.
- Vérifie les appels `page(..., **opts)` et retire les collisions `volunteers` / `associations`.
- Équipes et Missions conservent leurs listes opérationnelles spécifiques.
- `Mes arbres` conserve ses options bénévoles/associations.
- Bénévoles :
  - Global super-admin : liste globale ;
  - Association : membres approuvés de l'association ;
  - Personnel super-admin : liste administrative globale accessible ;
  - autres comptes : périmètre serveur conservé.
- Aucune migration SQLite.
