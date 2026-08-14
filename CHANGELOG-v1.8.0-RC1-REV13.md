# MyTree Professional v1.8.0 RC1 Rev.13 — Online Test / Cohérence multi-interface

## Correctifs et améliorations

- Filtrage universel Wilaya → Commune dans les formulaires PC, téléphone et interface publique.
- Filtrage universel Projet → Zone dans les formulaires utilisant ces deux sélecteurs.
- Préremplissage du responsable à partir de l'équipe lorsque le formulaire contient Équipe + Responsable.
- Confirmation obligatoire du mot de passe lors de la création de compte, publique et connectée.
- Ajout du parcours « Mot de passe oublié ? » avec code SMS à 6 chiffres, expiration 10 minutes et réinitialisation sécurisée.
- Connecteur SMS configurable via `MYTREE_SMS_WEBHOOK` ; aucun faux SMS n'est simulé lorsque le fournisseur n'est pas configuré.
- Code projet automatique `PROJET-0001`, `PROJET-0002`, etc. ; le code n'est plus saisi manuellement.
- Recherche intelligente des bénévoles dans la création/modification d'équipe (nom ou téléphone).
- Renforcement du comportement Projet → Zone → Équipe → Responsable dans les formulaires dynamiques.
- Renforcement de l'internationalisation FR / AR / EN sur les écrans d'authentification, notifications, organisation, navigation et formulaires courants.
- Traduction dynamique renforcée pour les éléments ajoutés après chargement de page.
- Conservation de la logique notifications : l'ouverture de la liste ne marque pas automatiquement toutes les notifications comme lues.
- Même scripts fonctionnels injectés sur PC, téléphone et interface publique pour éviter les écarts de comportement.

## Compatibilité

- Migration non destructive de la base SQLite existante.
- Nouvelle table `password_reset_codes` créée automatiquement.
- Compatible avec le volume Railway `/data` et `MYTREE_DATA_DIR=/data`.
