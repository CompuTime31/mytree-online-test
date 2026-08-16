# MyTree Professional v2.0 Alpha 4 — Online Test

## Lot 1 — Consolidation multi-associations

- Version interne et fichiers VERSION alignés sur Alpha 4.
- Alpha 3 conservée comme archive source séparée.
- Refonte du garde multi-associations : la ressource est déterminée à partir de la route réelle et non plus seulement de paramètres réutilisés (`tid`, `mid`, `pid`).
- Correction du risque de confusion arbres/équipes et missions/membres dans le contrôle d'accès direct aux fiches.
- Ajout d'un helper central `can_administer_association` pour les opérations sensibles.
- Collaboration inter-associations limitée aux administrateurs de l'association propriétaire du projet (ou Super Admin global).
- Refus explicite de la collaboration pour un projet personnel.
- Contrôle de l'association invitée et prévention des invitations actives en double.
- Notification des administrateurs de l'association invitée.
- Ajout du Centre de collaboration `/collaborations` : invitations entrantes/sortantes, statut, accepter/refuser.
- Après décision, retour cohérent vers le Centre de collaboration.

## Tests effectués dans l'environnement de développement

- Compilation Python `py_compile` : OK.
- Vérification des fichiers de version : OK.
- Vérification statique des nouvelles fonctions et routes : OK.
- Tests Flask d'exécution : non exécutables dans l'environnement de génération actuel car les dépendances Python ne sont pas préinstallées et l'accès réseau de `pip` est indisponible. Ils restent obligatoires sur l'environnement Online Test/Railway avant validation du lot.
