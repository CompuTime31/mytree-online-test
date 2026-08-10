# Tests Alpha 10 Rev.1

## Tests automatisés réalisés
- Compilation Python de `app.py` : réussie.
- Analyse syntaxique AST : réussie.
- Exécution du schéma SQLite en mémoire : réussie, 52 tables.
- Présence des routes GPS rapide : vérifiée.
- Intégrité de l’archive ZIP : vérifiée.

## Tests à effectuer sur téléphone
1. Créer une plantation sans toucher au bouton Enregistrer : aucune création ne doit avoir lieu.
2. Rechercher une espèce en français, arabe ou nom scientifique et confirmer que la sélection reste dans le formulaire.
3. Ouvrir « Mes arbres sans GPS » puis « GPS rapide ».
4. Autoriser le GPS, enregistrer une position et vérifier le passage automatique à l’arbre suivant.
5. Tester « Passer », « À vérifier » et « Choisir sur la carte ».
6. Vérifier le Centre d’actions > Modifications d’arbres.

## Limites
- La géolocalisation du navigateur mobile nécessite généralement HTTPS, sauf sur localhost.
- Les essais réels de précision GPS doivent être réalisés en extérieur.
