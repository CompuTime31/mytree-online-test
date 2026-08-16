# Tests MyTree Professional v2.0 Alpha 4 — Online Test

## A. Sécurité multi-associations
- [ ] Admin Association A : ouvrir un arbre A -> autorisé.
- [ ] Admin Association A : saisir directement l'URL d'un arbre B -> HTTP 403.
- [ ] Admin Association A : ouvrir une équipe A -> autorisé.
- [ ] Admin Association A : saisir directement l'URL d'une équipe B -> HTTP 403.
- [ ] Vérifier qu'un identifiant `tid` identique arbre/équipe ne crée plus de confusion.
- [ ] Admin Association A : ouvrir une mission A -> autorisé.
- [ ] Admin Association A : saisir directement l'URL d'une mission B -> HTTP 403.
- [ ] Admin Association A : ouvrir un membre A -> autorisé.
- [ ] Admin Association A : saisir directement l'URL d'un membre B -> HTTP 403.
- [ ] Contexte Personnel : les fiches liées à une association sont refusées.
- [ ] Super Admin en contexte Global : accès autorisé aux associations.

## B. Collaboration inter-associations
- [ ] Créer/ouvrir un projet appartenant à Association A.
- [ ] Un simple bénévole A ne peut pas envoyer d'invitation de collaboration -> HTTP 403.
- [ ] Admin A peut inviter Association B.
- [ ] Une seconde invitation pending/accepted A -> B n'est pas dupliquée.
- [ ] Les administrateurs B reçoivent une notification vers `/collaborations`.
- [ ] En contexte Association B, ouvrir `/collaborations` et voir l'invitation.
- [ ] Simple bénévole B : aucun bouton de décision administrateur.
- [ ] Admin B : accepter l'invitation -> statut accepted.
- [ ] Refaire avec une autre invitation et vérifier Refuser -> statut rejected.
- [ ] Projet personnel : collaboration refusée avec message explicite.

## C. Régression Alpha 3
- [ ] /healthz = OK sur Online Test.
- [ ] Carte : Tous / Mes arbres / Individuels / Associations / À arroser.
- [ ] Filtres PC et téléphone.
- [ ] Liste -> Carte conserve les filtres.
- [ ] Carte -> fiche -> Retour conserve l'URL filtrée.
- [ ] Marqueur 🌳 arbres individuels.
- [ ] Symbole propre de chaque association et unicité du symbole.
- [ ] Mode Terrain sur téléphone.
- [ ] Connexion MyTree + 🇩🇿.
- [ ] FR / AR / EN sur les nouveaux libellés.
