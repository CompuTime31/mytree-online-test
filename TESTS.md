# Tests FIXED7 — Profile Switch

- [ ] Connecter un compte `volunteer`.
- [ ] Vérifier qu'en Profil Personnel il reste bénévole.
- [ ] Basculer vers Association A où il est `association_admin`.
- [ ] Le header affiche l'identité Association A, pas le bénévole comme profil principal.
- [ ] L'accueil devient `/association`.
- [ ] Il peut administrer uniquement Association A selon ses permissions.
- [ ] Il ne voit pas les fonctions Super Admin globales.
- [ ] Basculer vers Association B où il est `volunteer`.
- [ ] Les droits changent immédiatement vers ceux de B.
- [ ] Revenir à Personnel.
- [ ] Le rôle redevient bénévole et ses associations restent accessibles.
- [ ] Vérifier que `users.role` n'a pas changé après les bascules.
- [ ] Super Admin : Global reste disponible et séparé des profils Association.
