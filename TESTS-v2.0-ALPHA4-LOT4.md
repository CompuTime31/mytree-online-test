# Tests Alpha 4 — Lot 4 Collaboration

1. Admin association A invite B sur un projet appartenant à A.
2. Bénévole A tente d’inviter : HTTP 403 attendu.
3. Admin B accepte/refuse ; bénévole B ne peut pas traiter l’invitation.
4. Une invitation déjà traitée ne peut pas être retraitée (HTTP 409).
5. Vérifier les droits partenaire : voir/intervenir par défaut ; ajout arbre et gestion missions seulement si accordés.
6. Admin B peut quitter une collaboration active, mais ne peut pas terminer le projet/collaboration au nom de A.
7. Admin A peut terminer la collaboration et renseigner un motif.
8. Vérifier l’historique invitation/acceptation/refus/quitter/fin.
9. Changer d’association active et vérifier l’absence d’accès à une collaboration étrangère.
10. Tester PC et téléphone sur Centre de collaboration.
