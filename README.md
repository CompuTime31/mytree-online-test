# My Tree Professional Edition — Sprint 1.3

Cette version conserve les fonctions du Sprint 1.2 et stabilise les bénévoles, les équipes, les plantations et les validations.

## Nouveautés

- Fiche bénévole modifiable par un administrateur
- Promotion et rétrogradation des rôles
- Activation et désactivation des comptes
- Filtres bénévoles et statistiques Homme/Femme conservés
- Liste des équipes avec filtres par projet, zone et état
- Création d'équipe via un écran « Nouvelle équipe » séparé
- Modification d'équipe via une fiche dédiée
- Fiche d'équipe et liste de ses membres
- Demande d'adhésion d'un bénévole à une équipe
- Liste administrative des demandes en attente
- Acceptation ou refus avec motif
- Retrait d'un membre d'une équipe
- Synchronisation de l'équipe principale du bénévole
- Page « Mes plantations » pour chaque bénévole
- Statut de plantation : pending, approved ou rejected
- Historique des décisions de validation
- QR imprimable uniquement après validation de la plantation
- Journalisation des créations, modifications, validations et refus
- Migration automatique des anciennes bases SQLite

## Mise à jour depuis le Sprint 1.2

1. Sauvegarder l'ancien dossier.
2. Copier le fichier `mytree.db` du Sprint 1.2 dans ce nouveau dossier.
3. Lancer `run-windows.bat`.
4. La migration crée automatiquement les nouvelles tables et colonnes.

## Installation neuve

1. Installer Python 3.11 ou plus récent.
2. Lancer `run-windows.bat`.
3. Ouvrir `http://localhost:8080`.

Compte initial :

- utilisateur : `admin`
- mot de passe : `admin123`

Changez le mot de passe administrateur et la variable `MYTREE_SECRET` avant une mise en ligne.
