# MyTree Professional — Railway Deploy — Lot 12 FIXED3

Package allégé destiné au déploiement Railway.

## Contenu
- app.py
- data_catalogs.py
- requirements.txt
- railway.json
- .gitignore
- VERSION
- preflight_lot12.py (si présent)
- CHANGELOG.md
- TESTS.md

## Important
- Ne contient pas la base SQLite de production.
- Ne contient pas les photos/données persistantes Railway.
- MYTREE_SECRET et MYTREE_DATA_DIR restent configurés dans Railway.
- Le volume Railway ne doit pas être supprimé lors d'une mise à jour.
