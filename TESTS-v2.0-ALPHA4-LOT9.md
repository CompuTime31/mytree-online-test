# Tests — Alpha 4 Lot 9

## A. Confirmations et sortie de formulaire
1. Créer puis modifier une ressource métier.
2. Vérifier qu'un message de confirmation est affiché après redirection.
3. Vérifier que l'URL finale est une fiche/liste logique et non un POST rejouable.
4. Actualiser la page : aucune seconde création/modification ne doit apparaître.

## B. Double soumission
1. Ouvrir un formulaire POST.
2. Double-cliquer rapidement sur Enregistrer.
3. Vérifier qu'une seule ligne métier est créée.
4. Rejouer manuellement le même `_submit_token` : le serveur doit rediriger avec l'avertissement « opération déjà envoyée ».
5. Vérifier que la table `submission_tokens` contient un seul jeton.

## C. Notifications non lues
1. Créer 2 notifications non lues.
2. Ouvrir `/notifications` : compteur inchangé.
3. Ouvrir explicitement une notification : compteur -1 et `read_at` renseigné.
4. Marquer une notification comme lue : `read_at` renseigné.
5. Traiter une demande Acceptée/Refusée : `is_read=1`, `read_at` et `processed_at` renseignés.
6. Vérifier qu'une notification d'action non traitée n'est pas affectée par `/notifications/read-all`.

## D. PC / téléphone
1. Effectuer les tests A-C sur navigateur PC.
2. Refaire sur téléphone.
3. Vérifier que le bouton soumis est désactivé immédiatement et que le message de confirmation reste lisible.
