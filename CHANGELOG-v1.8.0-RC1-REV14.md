# MyTree Professional v1.8.0 RC1 Rev.14 — Online Test

Correctif final ciblé avant reprise du chantier Multi-Associations.

- Mot de passe oublié : choix SMS ou e-mail. Le SMS utilise `MYTREE_SMS_WEBHOOK`; l'e-mail utilise SMTP (`MYTREE_SMTP_HOST`, `MYTREE_SMTP_PORT`, `MYTREE_SMTP_USER`, `MYTREE_SMTP_PASSWORD`, `MYTREE_EMAIL_FROM`). Aucun envoi n'est simulé si le fournisseur n'est pas configuré.
- Planification : la sélection d'une équipe renseigne automatiquement le responsable déjà défini comme chef d'équipe. Correction du composant générique PC/mobile (`leader_user_id`).
- Mobile : `Mon accueil` et `Déconnexion` restent visibles côte à côte dans l'en-tête connecté.
- Retour : remplacement du `history.back()` du bouton applicatif par un retour logique. Les formulaires d'action (plantation/don/arrosage) ne sont pas rouverts après une opération terminée.
- Déconnexion : retour par défaut vers l'interface publique.
