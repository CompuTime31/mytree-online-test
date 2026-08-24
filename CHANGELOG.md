# Lot 12 — FIXED5 Association Approval

- Corrige l'erreur lors de l'acceptation d'une demande de création d'association.
- Cause : nombre de paramètres SQL incorrect lors de l'INSERT dans `associations`.
- Après acceptation :
  - association créée avec statut `active`;
  - demande mise à `approved`;
  - demandeur ajouté comme `association_admin`;
  - profil Personnel/Bénévole conservé;
  - nouveau contexte Association ajouté au même compte;
  - notification envoyée au demandeur.
- Transaction rollback en cas d'erreur : aucune création partielle.
- Redirection Super Admin vers la liste des associations après succès.
- Aucune migration SQLite.
