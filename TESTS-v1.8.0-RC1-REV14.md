# Contrôles Rev.14

- [x] Compilation Python (`py_compile`).
- [x] Contrôle statique du sélecteur Équipe → Responsable.
- [x] Contrôle CSS mobile : Mon accueil + Déconnexion explicitement visibles.
- [x] Contrôle du workflow Mot de passe oublié : SMS / e-mail, expiration 10 min, code hashé.
- [x] Contrôle du bouton Retour applicatif : lien logique, sans `history.back()` dans l'en-tête.
- [ ] Test SMTP réel : nécessite les identifiants du fournisseur e-mail sur Railway.
- [ ] Test SMS réel : nécessite `MYTREE_SMS_WEBHOOK`.
- [ ] Test HTTP complet PC/iPhone sur Railway après déploiement.
