# MyTree Professional v1.8.0 RC1 Rev.11

## Correctif critique
- Correction de la migration SQLite du champ `users.preferred_language`.
- La définition SQL utilise maintenant explicitement `TEXT DEFAULT 'fr'`, ce qui évite `sqlite3.OperationalError: incomplete input`.
- Le démarrage Windows affiche maintenant la bonne version RC1 Rev.11 au lieu de l'ancien libellé Alpha 3.

## Compatibilité
- Migration non destructive : les bases existantes sont conservées.
- Les installations neuves et les anciennes bases sans colonne `preferred_language` sont prises en charge.
