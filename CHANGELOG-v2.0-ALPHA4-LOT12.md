# MyTree Professional v2.0 Alpha 4 — Lot 12 Online Test Candidate

## Consolidation
- Base : Lot 11 FR / AR / EN + RTL.
- `APP_VERSION` remis en cohérence avec le candidat Lot 12.
- Aucun nouveau module métier majeur ajouté.

## Base de données / migration
- Sauvegarde automatique unique de `mytree.db` avant la migration Lot 12 lorsqu'une base existe déjà.
- Migration conservée non destructive (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN`, `INSERT OR IGNORE`).
- SQLite configuré avec `busy_timeout=15000`, journal WAL et synchronisation NORMAL pour les essais multi-utilisateurs.
- Diagnostic base centralisé : intégrité, tables critiques et clés étrangères.

## Online Test
- `/healthz` vérifie intégrité SQLite, tables critiques, stockage inscriptible et présence d'un `MYTREE_SECRET` correct.
- `/readyz` fournit un contrôle strict de disponibilité de la base.
- En-têtes HTTP de sécurité ajoutés sans bloquer GPS/caméra.
- Script `preflight_lot12.py` inclus pour vérifier la configuration avant ouverture aux testeurs.

## Sécurité et régression
- Permissions, contexte association, collaborations, anti-double soumission, notifications, carte, filtres, PC/mobile et FR/AR/EN hérités des Lots 1 à 11.
- Les versions précédentes restent séparées et ne sont pas écrasées.
