# MyTree Professional v1.8.0 Alpha 7

## Fonctionnalités réellement intégrées

- Passage de l’application à la version Alpha 7.
- Enrichissement du formulaire administrateur des espèces avec les champs botaniques : famille, origine, présence en Algérie, régions, sol, exposition, résistances, distance de plantation, hauteur adulte, croissance, période de plantation, usages, entretien, maladies et précautions.
- Enregistrement réel de ces champs dans la table `species` lors de la création et de la modification.
- Ajout d’un outil public de recommandation d’espèces par région, besoin en eau, usage et type de sol.
- Ajout d’une fiche botanique imprimable.
- Enrichissement de la fiche publique avec entretien, maladies, parasites et précautions.
- Conservation de la recherche instantanée en français, arabe et nom scientifique.
- Conservation du référentiel des 58 wilayas et du chargement dynamique des communes déjà présentes dans la base.

## Compatibilité

- Migration SQLite non destructive.
- Les versions précédentes restent conservées.
- Les nouvelles données botaniques utilisent les colonnes déjà prévues par la migration Alpha 6.
