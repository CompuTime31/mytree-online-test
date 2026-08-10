# Bugs — RC1 Rev.11

## Corrigé
- **RC1-REV10-MIG-001** : `sqlite3.OperationalError: incomplete input` pendant `init_db()` lors de l'ajout de `preferred_language`.

## À valider sur installation réelle
- Démarrage Windows via `run-windows.bat`.
- Migration de la base de l'utilisateur sans perte de données.
- Sélecteur FR / AR / EN après migration.
