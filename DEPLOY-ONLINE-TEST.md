# MyTree Professional — Déploiement de test Railway

## Variables Railway
- `MYTREE_DATA_DIR=/data`
- `MYTREE_SECRET=<une chaîne aléatoire longue>`

## Volume persistant
Attacher un volume au service avec le point de montage `/data`.

## Démarrage
Railway lit `railway.json` et démarre :
`waitress-serve --listen=0.0.0.0:$PORT app:app`

## Contrôle
La route `/healthz` doit répondre avec `status: ok`.

## Base de test
La base SQLite est créée dans `/data/mytree.db`. Le volume évite de perdre les données lors d'un redéploiement.

## RC1 Rev.12
Cette révision conserve la même configuration Online Test. Le référentiel national des communes peut être synchronisé automatiquement au premier démarrage connecté et est ensuite mis en cache dans `MYTREE_DATA_DIR`.

## RC1 Rev.13

Variables Railway conservées :

- `MYTREE_DATA_DIR=/data`
- `MYTREE_SECRET=<clé privée>`

Option pour la réinitialisation réelle du mot de passe par SMS :

- `MYTREE_SMS_WEBHOOK=<URL du connecteur SMS>`

Le webhook reçoit un POST JSON contenant `phone` et `message`. Ne configurez cette variable qu'après choix d'un fournisseur SMS.
