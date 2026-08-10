# Tests - v1.8.0 RC1 Rev.10

## Tests exécutés dans l'environnement de construction
- `python -m py_compile app.py` : OK.
- Analyse AST Python : OK.
- Exécution du schéma SQLite en mémoire : OK.
- Nombre de tables créées : 56.
- `PRAGMA integrity_check` : OK.
- Colonnes `species.name_en` et `users.preferred_language` : présentes.
- Route `/language/<lang>` : présente.
- Script de recherche intelligente universelle : présent.
- Catalogue : 304 espèces / 136 types de matériel.

## Tests à effectuer sur l'installation réelle
- Basculer FR -> AR -> EN sur PC et téléphone.
- Vérifier le RTL arabe sur menus, formulaires, tableaux, pages publiques et espace bénévole.
- Fermer/réouvrir le navigateur et vérifier la mémorisation de la langue.
- Se connecter avec un utilisateur et vérifier la mémorisation de sa langue préférée.
- Tester la recherche intelligente dans Don > Arbres et Don > Matériel.
- Tester la recherche dans bénévoles, adhérents, projets, zones, communes, équipes et événements.
- Tester les listes dynamiques de dons mixtes.
- Vérifier la sélection et la soumission des formulaires après filtrage d'une liste.

## Limite de l'environnement
Flask n'est pas installé dans l'environnement de construction ; les tests HTTP complets et le rendu navigateur doivent être confirmés sur l'installation MyTree réelle.
