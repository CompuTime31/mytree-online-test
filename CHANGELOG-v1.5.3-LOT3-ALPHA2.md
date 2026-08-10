# MyTree Professional v1.5.3 — Lot 3 Alpha 2

## Modifications réelles

### Espèces
- CRUD complet : création, liste, modification et suppression contrôlée.
- Recherche par nom, nom scientifique et catégorie.
- Archivage et réactivation.
- Blocage de suppression lorsqu’une espèce est utilisée par un arbre.
- Compteur d’arbres par espèce.
- Ajout des champs description, photo, dates de création et de mise à jour.
- Validation des doublons et de la fréquence d’arrosage.
- Boutons Enregistrer et Annuler.

### Arbres
- Ajout des actions Fiche, Carte et Modifier dans la liste.
- Fiche arbre enrichie avec accès direct à la carte, à l’arrosage et à l’historique.
- Nouvelle carte dédiée à un arbre, centrée sur ses coordonnées.
- Affichage de la position utilisateur lorsque l’autorisation GPS est accordée.
- Lien vers un itinéraire OpenStreetMap.
- Appel `invalidateSize()` pour éviter l’affichage gris de Leaflet.
- Arrosage prérempli depuis la fiche ou la carte de l’arbre.
- Bouton Annuler ajouté au formulaire de modification d’un arbre.

### Base de données
- Migration non destructive de la table `species`.
- Conservation des données existantes et des fonctions validées.
