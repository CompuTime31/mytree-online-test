# Tests Lot 12 — MapFix 1

## Bug carte connectée
- [ ] Connexion Admin Association A.
- [ ] Ouvrir Carte commune sans filtre.
- [ ] Les arbres validés/géolocalisés du projet A sont visibles.
- [ ] Tester un arbre ancien avec `trees.association_id IS NULL` mais `project.association_id=A`.
- [ ] L'arbre est visible dans A.
- [ ] Le même arbre n'est pas visible dans une association non autorisée.
- [ ] Projet collaboratif `can_view=1` : arbres visibles.
- [ ] Collaboration sans `can_view` : arbres non visibles.

## Public
- [ ] `/public/map` affiche `🌳` comme marqueur.
- [ ] Clic sur 🌳 ouvre la popup et la fiche publique.
- [ ] Plusieurs arbres proches restent visibles/zoomables.

## Filtres
- [ ] Un seul bouton `Filtre` est visible au repos.
- [ ] Clic : tous les filtres s'affichent.
- [ ] Fermer : le panneau disparaît.
- [ ] Appliquer conserve les critères.
- [ ] Réinitialiser efface les critères.
- [ ] Compteur de filtres actifs correct.
- [ ] Même comportement PC et téléphone.
- [ ] `Ma position` fonctionne indépendamment du panneau de filtres.
