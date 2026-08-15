# Déploiement Railway — v2.0 Alpha 1

1. Sauvegarder la base Rev.14 avant déploiement.
2. Remplacer le code du dépôt GitHub par le contenu de cette archive.
3. Conserver le volume Railway existant monté sur `/data`.
4. Conserver `MYTREE_DATA_DIR=/data` et `MYTREE_SECRET`.
5. Laisser Railway redéployer.
6. Vérifier `/healthz` puis l'interface publique.

La migration est conçue pour conserver les données existantes et rattacher l'historique à une association principale créée automatiquement si aucune association n'existe encore.
