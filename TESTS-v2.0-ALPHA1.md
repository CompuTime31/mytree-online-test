# Tests — MyTree Professional v2.0 Alpha 1

## Contrôles réalisés hors serveur
- `python -m py_compile app.py` : OK.
- Parsing AST Python : OK.
- Exécution du schéma SQLite isolé : OK.
- `PRAGMA quick_check` sur schéma isolé : OK.
- 64 tables créées par le schéma, dont les nouvelles tables multi-associations.
- Vérification statique des routes Associations / Mes associations / demandes : OK.
- Vérification de la présence du Mode Terrain mobile : OK.

## Tests à effectuer sur Railway
1. Déploiement sur le volume `/data` existant après sauvegarde.
2. Vérifier `/healthz`.
3. Vérifier la création automatique de l'association principale de migration.
4. Créer une nouvelle association comme Super Admin.
5. Faire une demande de création d'association depuis un compte bénévole.
6. Accepter/refuser cette demande.
7. Rejoindre une association comme bénévole.
8. Demander une adhésion comme adhérent.
9. Vérifier les notifications Super Admin et association.
10. Tester le mode d'inscription automatique puis manuel.
11. Tester PC + téléphone, dont Mode Terrain sur téléphone.

## Limite de l'environnement de construction
Flask n'est pas installé dans l'environnement local de construction ; les tests HTTP runtime doivent être exécutés sur Railway.
