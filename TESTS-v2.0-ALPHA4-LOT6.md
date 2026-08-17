# Tests — Alpha 4 Lot 6

## Tests fonctionnels prioritaires
1. Association A : sélectionner Wilaya → Commune → Projet → Zone et vérifier que chaque liste se réduit correctement.
2. Réutiliser la même combinaison Projet/Zone sur Arbres, Missions, Carte et Rapports : aucun élément hors périmètre ne doit apparaître.
3. Compte membre de A et B : changer d'association active et confirmer que les projets/zones proposés changent immédiatement.
4. Projet collaboratif accepté avec `can_view=1` : il doit être disponible dans les filtres. Collaboration pending/refusée/terminée : il ne doit pas apparaître.
5. Injecter manuellement dans l'URL un `project_id` d'une association C inaccessible : réponse 403.
6. Injecter une `zone_id` appartenant à un autre projet : réponse 403.
7. Injecter un `volunteer_id` non membre de l'association active : réponse 403.
8. Tester date_from/date_to sur Arbres, Missions, Événements et Rapports.
9. Tester téléphone : changements Wilaya/Projet doivent rafraîchir Commune/Zone sans casser le formulaire.
10. Réinitialiser chaque écran puis vérifier qu'aucun ancien filtre n'est conservé.

## Contrôles de non-régression
- Carte GPS et éléments proches toujours fonctionnels.
- Permissions Lot 3 conservées.
- Collaborations Lot 4 conservées.
- Carte multi-associations Lot 5 conservée.
- `python -m py_compile app.py` doit réussir.
