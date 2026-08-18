# Tests Alpha 4 Lot 12 — MapFix 2

## Carte connectée
- [ ] Global : `/map` charge sans message d'erreur.
- [ ] Association principale : arbres validés et géolocalisés visibles.
- [ ] Personnel : uniquement les arbres personnels autorisés.
- [ ] Ancien arbre avec `association_id NULL` + projet de l'association : visible.
- [ ] Ressource sans coordonnées GPS : ignorée sans erreur API.
- [ ] `/api/map-data` répond HTTP 200.
- [ ] Les marqueurs arbre utilisent 🌳.
- [ ] Carte publique conserve 🌳.

## Bouton Filtre généralisé
Sur Arbres, Missions, Événements, Rapports et autres listes filtrables :
- [ ] Un seul bouton `Filtre` apparaît au repos.
- [ ] Clic sur Filtre affiche tous les critères.
- [ ] Appliquer fonctionne.
- [ ] Réinitialiser fonctionne.
- [ ] Nombre de filtres actifs correct.
- [ ] PC OK.
- [ ] Téléphone OK.
- [ ] Les formulaires d'action POST ne sont jamais transformés en filtre.
