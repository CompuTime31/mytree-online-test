# Déploiement — MyTree Professional v2.0 Alpha 4 Online Test Candidate

## Variables obligatoires
- `MYTREE_DATA_DIR=/data`
- `MYTREE_SECRET=<clé aléatoire de 24 caractères minimum>`

## Stockage
Attacher un volume persistant monté sur `/data`. Ne pas déployer la base SQLite sur un stockage éphémère.

## Avant démarrage
Exécuter si possible :

```bash
python preflight_lot12.py
```

Une base existante est sauvegardée automatiquement une seule fois avant la migration Lot 12 sous le nom `mytree-pre-alpha4-lot12-YYYYMMDD-HHMMSS.db`.

## Démarrage Railway
`railway.json` conserve :

```bash
waitress-serve --listen=0.0.0.0:$PORT app:app
```

## Validation
- `/healthz` doit répondre HTTP 200 / `status: ok`.
- `/readyz` doit répondre HTTP 200 / `ready: true`.
- Si `MYTREE_SECRET` est absent ou conserve la valeur par défaut, `/healthz` renvoie 503 : ne pas ouvrir le test aux utilisateurs.

## Retour arrière
1. Arrêter le service.
2. Conserver la base courante pour diagnostic.
3. Restaurer la sauvegarde pré-Lot12 ou la sauvegarde manuelle Alpha 3/Alpha 4 précédente.
4. Redéployer le build précédent.
