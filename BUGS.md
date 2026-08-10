- v1.8.0 Alpha 10 : navigation mobile et module sauvegarde corrigés ; validation terrain restante.
# Registre des bugs — v1.5.2

- BUG-003 Équipes : corrigé. Création, modification, adhésion, validation et retrait consolidés.
- BUG-004 Projets : corrigé. CRUD, pages de détail, archivage et duplication consolidés.
- BUG-005 Zones : corrigé. CRUD, pages de détail, GPS et archivage consolidés.

## Limite de vérification
Le test HTTP complet Flask/Waitress doit être exécuté sur le poste utilisateur, les dépendances Flask n'étant pas disponibles dans l'environnement de génération.
