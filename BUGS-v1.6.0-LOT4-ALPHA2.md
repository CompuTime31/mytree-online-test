# Registre des bugs — v1.6.0 Lot 4 Alpha 2

## BUG-007 — Bouton « Demandes équipes » non fonctionnel
**Cause :** le menu pointait vers `/team-requests`, mais aucune route GET ne gérait cette URL.

**Correction :** ajout d’une page complète des demandes et connexion aux routes d’acceptation/refus.

**État :** corrigé par analyse statique. Test HTTP à confirmer sur Windows après installation des dépendances.
