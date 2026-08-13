# Bugs / points à confirmer — RC1 Rev.12

- Les tests HTTP complets Flask ne sont pas exécutables dans l’environnement de construction actuel ; validation nécessaire sur l’environnement Online Test.
- Le référentiel national des communes est téléchargé automatiquement si le cache n’existe pas. Si le serveur n’a pas accès à Internet au premier démarrage, MyTree conserve les communes déjà présentes et retentera à un prochain démarrage.
- La couverture FR/AR/EN a été renforcée ; les textes métier très spécifiques restant éventuellement non traduits doivent être signalés pendant le test afin de compléter le dictionnaire avant Stable.
- Vérifier sur iPhone/Android les permissions GPS et le rendu de Leaflet en HTTPS.
