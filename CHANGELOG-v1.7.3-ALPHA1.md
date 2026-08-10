# MyTree Professional v1.7.3 Alpha 1

## Modifications réellement intégrées

- Cloche de notifications dans l’en-tête avec compteur rouge des notifications non lues.
- Notifications automatiques aux administrateurs lors d’une nouvelle plantation bénévole.
- Notifications au bénévole après acceptation ou refus de sa plantation.
- Accès direct depuis chaque notification vers la fiche concernée.
- Boutons Accepter / Refuser dans la fiche d’une plantation en attente.
- Raccourcis Fiche et Carte dans la liste des plantations à valider.
- QR provisoire généré dès la création d’une plantation bénévole.
- Affichage et impression du QR provisoire depuis la fiche de l’arbre.
- Redirection vers la fiche après la création d’une plantation.
- Bouton Itinéraire Google Maps dans la fiche arbre et dans les fenêtres de carte.
- Carte administrateur autorisée à afficher également les plantations en attente.
- Statut En attente / Acceptée / Refusée visible dans la liste des arbres du bénévole.
- Scanner QR renforcé :
  - contrôle du contexte HTTPS ;
  - bouton de nouvelle tentative ;
  - caméra arrière ;
  - lecture depuis une image ;
  - saisie manuelle conservée ;
  - messages d’erreur plus précis.
- Permissions individuelles ajoutées pour les bénévoles.
- Menus Missions, Interventions et Équipe affichés selon les permissions individuelles.
- Page administrateur de gestion des droits d’un bénévole.
- Correction de recherche bénévole conservée depuis la v1.7.2.

## Limites de cette Alpha 1

- Les navigateurs mobiles peuvent toujours bloquer caméra et GPS si l’application est ouverte sur une adresse HTTP locale. Le code affiche maintenant un diagnostic explicite, mais un accès HTTPS reste nécessaire pour un fonctionnement fiable sur téléphone.
- Les tests d’exécution complets n’ont pas pu être réalisés dans l’environnement de génération faute de paquets Flask disponibles hors ligne. La compilation Python a réussi.
