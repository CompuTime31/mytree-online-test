# Plan de tests — v1.8.0 Alpha 2

## Vérifications automatiques effectuées
- Compilation Python de app.py : réussie.
- Présence des nouvelles tables dans le schéma : vérifiée statiquement.
- Présence des routes /donations, /nursery et /equipment : vérifiée dans le code.
- Intégrité de l'archive ZIP : à vérifier lors de la génération.

## Tests fonctionnels à exécuter sur PC
1. Se connecter en Super Admin.
2. Créer un don d'argent puis un don d'arbres.
3. Vérifier le reçu automatique et la notification.
4. Ajouter un stock de pépinière.
5. Tester chaque type de mouvement.
6. Vérifier l'alerte lorsque le stock libre passe sous le seuil.
7. Ajouter un matériel avec une quantité supérieure à 1.
8. Prêter une partie du stock à un bénévole.
9. Vérifier la diminution de la quantité disponible.
10. Enregistrer le retour et vérifier la remise en stock.

## Tests de permissions
- Un administrateur doit accéder aux trois modules.
- Un bénévole sans permission doit être redirigé.
- Les droits individuels peuvent être accordés depuis la fiche des permissions du bénévole.

## Limite de l'environnement de construction
Le test Flask complet n'a pas été exécuté dans l'environnement de génération, car le paquet Flask n'y est pas installé. La compilation syntaxique Python a réussi.
