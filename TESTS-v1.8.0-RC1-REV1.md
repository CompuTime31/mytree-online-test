# Tests — MyTree Professional v1.8.0 RC1 Rev.1

## Contrôles automatisés effectués
- [x] Compilation Python de `app.py`.
- [x] Analyse syntaxique AST.
- [x] Exécution complète du schéma SQLite en mémoire.
- [x] 52 tables SQLite créées.
- [x] `PRAGMA integrity_check` : `ok`.
- [x] Vérification statique des nouvelles routes :
  - `/public/action/<action>`
  - `/trees/<int:tid>/delete`
  - `/volunteers/<int:uid>/delete`
  - `/events/<int:eid>/delete`
- [x] Vérification de l'intégrité de l'archive ZIP.

## Scénarios à tester sur l'installation réelle
- [ ] Visiteur : bouton Connexion visible sur PC et téléphone.
- [ ] Utilisateur connecté dans l'espace public : Mon espace et Déconnexion visibles.
- [ ] Action Planter : inscription/connexion puis redirection vers le formulaire de plantation.
- [ ] Action Arroser : inscription/connexion puis redirection vers l'arrosage.
- [ ] Action Faire un don : inscription/connexion puis redirection vers le formulaire de don.
- [ ] Retour depuis une fiche arbre vers la même position de la liste.
- [ ] Conservation des filtres, recherche et paramètres de liste.
- [ ] Suppression d'un arbre sans historique.
- [ ] Archivage d'un arbre avec historique.
- [ ] Suppression d'un bénévole sans historique.
- [ ] Désactivation d'un bénévole avec historique.
- [ ] Événement sans limite de participants.
- [ ] Suppression d'un événement sans participant.
- [ ] Archivage d'un événement avec participants.

## Limite de l'environnement de construction
Les dépendances Flask ne sont pas installables dans l'environnement de construction. Les tests HTTP complets et le rendu navigateur doivent être effectués sur le PC d'installation.
