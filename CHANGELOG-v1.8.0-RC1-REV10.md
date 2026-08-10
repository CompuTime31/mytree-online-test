# MyTree Professional v1.8.0 RC1 Rev.10

## Internationalisation
- Ajout du sélecteur de langue Français / العربية / English sur les interfaces privées et publiques.
- Mémorisation de la langue dans la session, un cookie et le profil utilisateur connecté.
- Ajout du mode RTL pour l'arabe (navigation, formulaires, tableaux et structure responsive).
- Mise en place d'un dictionnaire centralisé pour les libellés système courants afin que les prochaines évolutions soient traduites dans les trois langues.
- Ajout du champ `preferred_language` aux utilisateurs avec migration non destructive.

## Espèces multilingues
- Ajout du champ `name_en` au référentiel des espèces.
- Fiches espèces : français, arabe, anglais et nom scientifique.
- Recherche des espèces étendue au nom anglais.
- Ajout du nom anglais dans le formulaire d'administration des espèces.
- Préremplissage de noms anglais pour les espèces courantes ; les autres fiches utilisent le nom scientifique comme valeur de repli afin de rester recherchables.

## Recherche intelligente universelle
- Ajout automatique d'un champ de recherche devant les listes importantes.
- Filtrage instantané pendant la saisie.
- Recherche insensible à la casse et aux accents.
- Fonctionne aussi sur les listes ajoutées dynamiquement (par exemple les lignes de dons mixtes).
- Priorité aux espèces, matériel, personnes, projets, zones, communes, équipes, missions et événements.

## Compatibilité
- Migration conservant les bases existantes.
- Les données saisies par l'association ne sont pas traduites automatiquement.
