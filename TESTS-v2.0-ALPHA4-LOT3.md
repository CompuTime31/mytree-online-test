# Tests — Alpha 4 Lot 3 Permissions

## Contrôles effectués dans le build
- Compilation Python de `app.py` : OK.
- Présence de la matrice de permissions par association : OK.
- Contrôle d'adhésion approuvée : OK.
- Contrôle du contexte association : OK.
- HTTP 403 sur permission associative refusée : OK.
- Journalisation des refus : implémentée.
- Garde de propriété des ressources du Lot 1 : conservé.

## Tests Online obligatoires
1. Compte A : administrateur Association A + bénévole Association B.
2. Compte B : bénévole Association A + administrateur Association B.
3. Compte C : bénévole Association A uniquement.
4. Vérifier lecture/création/modification/suppression dans A puis B.
5. Modifier manuellement les IDs dans les URL : accès croisé attendu = 403.
6. Envoyer des POST directs sans permission : attendu = 403.
7. Changer d'association puis réutiliser une ancienne URL : attendu = 403.
8. Retirer une adhésion pendant une session puis réessayer : accès attendu = refusé.
9. Vérifier qu'un administrateur partenaire ne devient pas administrateur de l'association propriétaire.

## Limite de l'environnement de génération
Flask n'est pas installé dans l'environnement de build actuel. Les tests HTTP/runtime doivent donc être exécutés sur l'environnement Online Test avec `requirements.txt` installé.
