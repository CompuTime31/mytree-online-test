# Déploiement Railway — v2.0 Alpha 2

1. Sauvegarder la base Railway actuelle avant le déploiement.
2. Conserver le volume existant monté sur `/data`.
3. Conserver `MYTREE_DATA_DIR=/data` et `MYTREE_SECRET`.
4. Remplacer le code du dépôt GitHub par le contenu de cette archive.
5. Laisser Railway redéployer automatiquement.
6. Vérifier `/healthz`.
7. Se connecter en Super Admin et tester le sélecteur de contexte : Global / Personnel / Association principale.
8. Tester ensuite avec un compte membre d’une association.

La migration est conçue pour être non destructive ; ne supprimez pas le volume `/data`.
