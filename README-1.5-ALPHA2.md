# My Tree Professional — Sprint 1.5 Alpha 2

Cette version poursuit directement le Sprint 1.5 Alpha 1.

## Nouveautés principales

### Missions avancées
- Liste avec recherche, statut et priorité
- Création et modification complètes
- Fiche détaillée de mission
- Affectation multiple de bénévoles
- Suivi des présences : invité, confirmé, présent, absent
- Objectif et quantité réalisée
- Rapport de fin de mission
- Archivage sans suppression physique
- Notifications lors de la création et de la clôture
- Journalisation des créations, modifications, présences et archivages

### Notifications
- Compteur des notifications non lues
- Marquage individuel comme lu
- Tout marquer comme lu
- Ouverture d'une notification avec mise à jour automatique de son état

### Recherche universelle
- Arbres
- Bénévoles
- Projets
- Zones
- Équipes
- Espèces
- Missions
- Liens directs vers les fiches correspondantes

### Tableau de bord
- Missions planifiées
- Missions en cours
- Missions terminées
- Notifications non lues

## Mise à jour

1. Sauvegarder le dossier et le fichier `mytree.db` existants.
2. Copier l'ancien `mytree.db` dans le dossier Alpha 2.
3. Lancer `run-windows.bat`.
4. La migration ajoute automatiquement les nouvelles colonnes et la table `mission_participants`.

## Compte initial

- Utilisateur : `admin`
- Mot de passe : `admin123`

Changer le mot de passe et la variable `MYTREE_SECRET` avant toute publication en ligne.
