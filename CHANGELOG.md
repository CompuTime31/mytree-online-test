# Lot 12 — FIXED8 Association Management

## Super Admin
- Correction du bouton `Voir` : vraie fiche association.
- Correction du bouton `Membres` : affiche les membres de l'association choisie, pas les demandes globales en attente.
- Bouton `Modifier` : informations, localisation, contact, site et symbole carte.
- Bouton `Archiver` : archivage immédiat par Super Admin.
- Bouton `Supprimer` : uniquement après archivage et uniquement si aucune donnée métier ne dépend encore de l'association.
- Écran des demandes d'archivage envoyées par les administrateurs d'association.
- Validation/refus d'une demande d'archivage avec notification.

## Administrateur d'association
- Bouton `Modifier l'association` dans le profil Association.
- Modification des informations et du symbole parmi les symboles encore disponibles.
- Bouton `Demander l'archivage`.
- L'archivage n'est pas exécuté immédiatement : demande envoyée au Super Admin.
- Super Admin doit accepter ou refuser.

## Symboles
- Un symbole déjà utilisé ou réservé ne peut pas être choisi.
- Lors d'un changement, l'ancien symbole redevient disponible.

## Sécurité
- Un association_admin ne peut modifier que l'association active.
- Suppression définitive réservée au Super Admin.
- Aucune suppression d'association contenant encore des données.
