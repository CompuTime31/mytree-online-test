# MyTree Professional v1.6.1 — Interface Bénévole Sprint 2 Alpha 1

## Plantation
- Ajout des choix **Hors projet** et **Hors zone**.
- Ajout explicite de la wilaya et de la commune sur chaque plantation.
- Contrôle de cohérence commune/wilaya et zone/projet.
- Conservation automatique des derniers choix par utilisateur : wilaya, commune, projet, zone, espèce et équipe.
- Les derniers choix sont restaurés dans les interfaces administrateur et bénévole.

## Rôles et droits
- Nouveau menu **Rôles et droits**.
- Création, modification, archivage et suppression contrôlée des rôles.
- Description, couleur, niveau hiérarchique et état du rôle.
- Attribution détaillée des droits d’accès par rôle.
- Suppression interdite lorsqu’un rôle est attribué à un utilisateur.
- Les boutons **Enregistrer** et **Annuler** sont présents sur les formulaires.

## Photos téléphone
- Boutons distincts **Choisir une photo** et **Prendre une photo**.
- Ouverture de l’appareil photo arrière sur téléphone lorsque le navigateur le permet.
- Prévisualisation, compression et retrait de la photo avant enregistrement.
- Disponible pour les profils, les plantations, les photos d’arbres et les observations.

## Base SQLite
- Colonnes `wilaya_id` et `commune_id` ajoutées aux arbres.
- Table `user_preferences` ajoutée.
- Rôles enrichis avec description, couleur et état.
- Photos ajoutées aux observations.
- Migration automatique conservée pour les bases existantes.
