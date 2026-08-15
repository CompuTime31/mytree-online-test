# MyTree Professional v2.0 Alpha 1 — Multi-Associations Online Test

## Fondations multi-associations
- Nouvelle entité `associations` avec code, identité, localisation, présentation, statut et symbole cartographique préparé.
- Nouvelles tables : `association_memberships`, `association_creation_requests`, `association_roles`, `user_contexts`.
- Ajout non destructif de `association_id` aux principales entités métier existantes.
- Migration des données historiques vers une association principale afin de préserver les données v1.8.
- Ajout de `visibility` aux arbres, avec `public` par défaut pour préparer la confidentialité v2.0.

## Comptes et adhésions
- L'inscription MyTree reste indépendante d'une association.
- Activation automatique des nouveaux bénévoles par défaut.
- Paramètre Super Admin permettant de basculer temporairement en validation manuelle.
- Notification informative envoyée au Super Admin lors d'une nouvelle inscription automatique.
- Demande séparée pour rejoindre une association comme bénévole ou demander une adhésion comme adhérent.
- Validation obligatoire des demandes d'association par un administrateur autorisé ou le Super Admin.
- Un même compte peut déposer des demandes vers plusieurs associations.

## Gestion des associations
- Page publique Associations avec filtres Wilaya / Commune / recherche.
- Demande de création d'association par un utilisateur connecté.
- Validation/refus par le Super Admin.
- Création directe d'une association par le Super Admin.
- Le demandeur devient administrateur de l'association après validation de sa demande.
- Page `Mes associations` pour suivre les appartenances et demandes.

## Mobile / terrain
- Le bouton Mode Terrain est désormais explicitement accessible sur mobile en plus du PC.

## Déploiement
- Version préparée pour Railway avec `MYTREE_DATA_DIR=/data` et migration non destructive du volume SQLite existant.
