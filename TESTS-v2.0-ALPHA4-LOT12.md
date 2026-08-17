# Tests — Alpha 4 Online Test Candidate

## 1. Préflight et migration
- [ ] Copier une vraie base Alpha 3 dans `MYTREE_DATA_DIR`.
- [ ] Sauvegarder manuellement la base avant tout essai externe.
- [ ] Définir `MYTREE_SECRET` (24+ caractères) et `MYTREE_DATA_DIR`.
- [ ] Lancer l'application : une sauvegarde `mytree-pre-alpha4-lot12-*.db` doit être créée une seule fois.
- [ ] `/healthz` = HTTP 200 et `status=ok`.
- [ ] `/readyz` = HTTP 200 et `ready=true`.
- [ ] Vérifier que les utilisateurs, projets, zones, arbres et photos historiques sont conservés.

## 2. Multi-associations / permissions
Utiliser au minimum : Admin A + Bénévole B ; Bénévole A + Admin B ; Bénévole A uniquement.
- [ ] Changement d'association sans fuite de données.
- [ ] URL d'une autre association = 403.
- [ ] POST forcé avec IDs externes = refus.
- [ ] Retrait/désactivation d'un membre immédiatement pris en compte.

## 3. Collaboration
- [ ] Invitation, acceptation, refus, retrait, quitter.
- [ ] Propriétaire conserve les droits maîtres.
- [ ] Partenaire limité à can_view/can_intervene/can_add_tree/can_manage_missions.
- [ ] Fin de collaboration retire l'accès partagé.

## 4. Métier
- [ ] Projet → Zone → Arbre cohérent.
- [ ] Objectifs Projet/Zone non dépassés.
- [ ] Équipes/Missions/Événements : membres et zones compatibles.
- [ ] Carte et filtres donnent les mêmes données autorisées.

## 5. Notifications / formulaires
- [ ] Ouverture liste notifications ne diminue pas le compteur.
- [ ] Lecture/traitement réel met à jour read_at/processed_at.
- [ ] Double clic / rafraîchissement ne crée pas de doublon.
- [ ] Après POST, sortie logique du formulaire + confirmation visible.

## 6. PC ↔ téléphone
- [ ] PC crée → téléphone consulte/modifie → PC vérifie.
- [ ] Téléphone crée → PC consulte/modifie → téléphone vérifie.
- [ ] GPS, caméra, photo, carte et filtres fonctionnent sur téléphone.
- [ ] Aucun « Accueil public » dans l'espace connecté.

## 7. FR / AR / EN
- [ ] Parcours complet FR.
- [ ] Parcours complet AR avec RTL.
- [ ] Parcours complet EN.
- [ ] Aucun mélange involontaire de langues sur les écrans testés.

## 8. Non-régression Alpha 3
- [ ] Connexion de comptes historiques.
- [ ] Consultation des arbres historiques.
- [ ] Arrosage, plantation, mission et rapport historiques.
- [ ] QR existants ouvrent la bonne fiche.
