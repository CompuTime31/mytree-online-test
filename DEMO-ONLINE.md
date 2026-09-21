# Demo Online RC16.18.3.1

Variables minimales :
- MYTREE_DEMO_MODE=1
- MYTREE_SECRET=<secret-fort>

La base par défaut en Demo est `mytree-demo.db`, distincte de `mytree.db`.
Le seed `demo/mytree_large_test.db` est copié au premier démarrage si la base Demo n'existe pas.

Pour réinitialiser volontairement la Demo au redémarrage :
- MYTREE_DEMO_RESET_ON_START=1
Puis remettre la variable à 0 après réinitialisation si les modifications de test doivent être conservées.
