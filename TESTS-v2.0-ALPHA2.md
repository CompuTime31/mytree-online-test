# Tests — v2.0 Alpha 2

## Contrôles effectués
- Compilation Python (`py_compile`) : OK.
- Initialisation sur base SQLite neuve avec environnement Flask simulé : OK.
- `PRAGMA quick_check` : OK.
- 64 tables détectées après initialisation : OK.
- Migration `association_id` vérifiée sur projets, zones, équipes, missions, événements, arbres, dons, caisse, pépinière et matériel : OK.
- Bascule Super Admin vers association principale : OK.
- Retour au contexte Personnel : OK.
- Chargement des écrans principaux en contexte Association : projets, zones, équipes, événements, missions, dons, caisse, stock, bénévoles : OK.
- Création test d’un projet, d’une équipe, d’un événement et d’une mission : `association_id` de l’association active enregistré : OK.

## À tester sur Railway
- Bascule de contexte sur téléphone, tablette et PC.
- Utilisateur membre de deux associations réelles.
- Administrateur d’association : impossibilité d’accéder aux données d’une autre association.
- Super Admin en contexte Global puis association spécifique.
- Carte, Mode Terrain, dons, caisse et stock sur plusieurs contextes.
- Migration du volume `/data` actuel Alpha 1 vers Alpha 2.
