# Tests v1.7.3 Alpha 2

- Compilation Python : OK.
- Vérification du retrait des permissions automatiques du rôle bénévole : OK.
- Vérification du masquage conditionnel dans la navigation et le tableau de bord : OK.
- Vérification de la protection des routes Missions et Équipe : OK.

## Test manuel recommandé
1. Redémarrer l’application pour exécuter la migration.
2. Se connecter avec un bénévole sans droits : Missions, Interventions et Équipe doivent être absents.
3. Accorder un droit depuis Administration > Bénévoles > fiche > Droits d’accès.
4. Se déconnecter puis se reconnecter avec le bénévole : seul le menu autorisé doit apparaître.
