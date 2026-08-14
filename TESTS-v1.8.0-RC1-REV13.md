# Tests — MyTree Professional v1.8.0 RC1 Rev.13

## Contrôles exécutés dans l'environnement de construction

- `python -m py_compile app.py` : OK.
- Analyse AST de `app.py` : OK.
- Exécution du schéma SQLite en mémoire : OK.
- `PRAGMA quick_check` : OK.
- Table `password_reset_codes` présente : OK.
- Syntaxe JavaScript `DEPENDENT_SELECTS_SCRIPT` via Node.js : OK.
- Syntaxe JavaScript `UNIVERSAL_SEARCH_SCRIPT` via Node.js : OK.
- Présence du code projet automatique : vérifiée.
- Présence de la confirmation de mot de passe sur les deux inscriptions : vérifiée.
- Présence du filtre Wilaya/Commune universel sur les pages publiques et connectées : vérifiée.
- Présence de la recherche intelligente des membres d'équipe : vérifiée.

## Tests à réaliser sur Railway / téléphone / PC

- Création de compte : sélectionner plusieurs wilayas et vérifier que seules leurs communes apparaissent.
- Vérifier le même comportement sur Projet, Zone, profil et autres formulaires comportant Wilaya/Commune.
- Notifications : ouvrir la liste sans ouvrir les notifications et confirmer que le compteur reste inchangé.
- Équipe : rechercher un bénévole par nom puis téléphone.
- Planification / Mission : sélectionner Projet → Zone, puis Équipe → Responsable.
- Changer FR / AR / EN et relever tout texte système restant non traduit.
- Mot de passe oublié : nécessite la configuration réelle du fournisseur SMS avant test d'envoi.
