# MyTree Professional v1.8.0 Alpha 1

## Nouveau module Événements
- Création et modification d’événements : plantation, arrosage, nettoyage, réunion et formation.
- Dates de début et de fin, lieu, projet, zone, équipe, capacité maximale et coordonnées GPS.
- États : Planifié, Ouvert, Complet, Terminé et Annulé.
- Liste filtrable par type, état et recherche.
- Inscription et annulation par les bénévoles.
- Blocage automatique lorsque la capacité maximale est atteinte.
- Pointage de présence par l’administrateur.
- Bouton Itinéraire Google Maps lorsque les coordonnées sont renseignées.
- Notification automatique à la création d’un événement.

## Équipes
- Nombre d’événements affiché dans la liste des équipes.
- Événements récents affichés dans la fiche d’une équipe.

## Permissions
- `event.view` : consulter les événements.
- `event.register` : s’inscrire aux événements.
- `event.manage` : créer, modifier et gérer les présences.
- Les bénévoles reçoivent uniquement les droits de consultation et d’inscription par défaut.

## Base de données
- Ajout des tables `events` et `event_participants` sans suppression des données existantes.
