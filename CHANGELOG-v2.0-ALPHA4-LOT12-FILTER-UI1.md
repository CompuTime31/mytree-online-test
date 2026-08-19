# Alpha 4 Lot 12 — Filter UI 1

## Standardisation des filtres
Tous les formulaires GET comportant au moins deux critères métier sont automatiquement regroupés sous un seul bouton `🔎 Filtrer`.

Écrans détectés dans ce build :
- Tableau de bord
- Arbres
- Bénévoles
- Projets
- Zones
- Utilisateurs
- Carte
- Sélection QR
- Interventions
- Équipes
- Événements
- Missions
- Mes arbres bénévole
- Planning opérations
- Rapports opérationnels
- Associations publiques

## Comportement
- Au repos : uniquement `🔎 Filtrer` + compteur de filtres actifs.
- Clic : tous les critères de l'écran apparaissent.
- `Fermer` ferme le panneau sans modifier les critères.
- `Appliquer` conserve le comportement GET existant.
- `Réinitialiser` efface les paramètres de filtre.
- `Échap` ferme le panneau au clavier.
- Focus clavier transféré correctement ouverture/fermeture.
- Panneau plein écran sur téléphone.
- Les formulaires POST de création/modification/actions sont exclus.
- La Carte commune garde son panneau spécialisé déjà validé.
