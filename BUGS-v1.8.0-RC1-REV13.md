# Bugs / points à confirmer — RC1 Rev.13

- L'envoi SMS réel n'est actif que si `MYTREE_SMS_WEBHOOK` est configuré avec un fournisseur SMS compatible. Sans fournisseur, MyTree affiche explicitement que le service SMS n'est pas configuré.
- Le référentiel national des communes continue sa synchronisation/cache lors de l'initialisation en ligne si la base contient moins de 1541 communes. Vérifier le total sur Railway après le premier démarrage de Rev.13.
- La couverture FR/AR/EN est renforcée mais doit être validée écran par écran sur les parcours réels ; signaler tout libellé système restant en français.
- Les tests HTTP complets n'ont pas été exécutés dans l'environnement de construction car Flask n'y est pas installé ; ils doivent être poursuivis sur l'environnement Railway déjà opérationnel.
