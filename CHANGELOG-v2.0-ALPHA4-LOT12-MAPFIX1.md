# Alpha 4 Lot 12 — MapFix 1

## Corrections
- Carte connectée : correction des arbres hérités d'Alpha 3 dont `association_id` est NULL mais dont le projet appartient à l'association active.
- Le contrôle serveur autorise maintenant explicitement :
  1. ressource appartenant à l'association active ;
  2. ressource rattachée à un projet propriétaire de l'association active ;
  3. projet partenaire avec collaboration `can_view`.
- La sécurité inter-associations reste active.

## Carte publique
- Remplacement du marqueur Leaflet standard par le symbole arbre `🌳`.
- Popup publique préfixée par `🌳`.

## Filtres carte connectée
- Tous les champs de filtre sont regroupés derrière un seul bouton `🔎 Filtre`.
- Clic sur `Filtre` : ouverture de tous les critères.
- Boutons `Appliquer`, `Réinitialiser` dans le panneau.
- `Ma position` reste une action de carte séparée, car ce n'est pas un filtre.
- Affichage du nombre de filtres actifs.
- Panneau adapté téléphone et PC.
