# Tests — Alpha 4 Lot 8

## Préparation
Créer deux associations A et B avec :
- Admin A / bénévole A
- Admin B / bénévole B
- un projet A
- un projet B
- une collaboration A → B avec droits variables

## Équipes
1. Créer une équipe A avec projet/zone A et plusieurs bénévoles A : attendu 200 + création.
2. Injecter l'ID d'un bénévole B dans `member_ids` : attendu 403.
3. Injecter une zone ne correspondant pas au projet : attendu 403.
4. Affecter une équipe A à un projet B sans collaboration `can_manage_missions` : attendu 403.
5. Autoriser `can_manage_missions`, puis réessayer : attendu autorisé.
6. Depuis B, tenter de rejoindre une équipe A : attendu 403.
7. Vérifier que le code EQUIPE-xxxx reste inchangé à la modification.

## Missions
1. Créer une mission A avec projet/zone/équipe A : attendu succès.
2. Injecter une équipe B : attendu 403.
3. Injecter un participant B dans une mission A : attendu 403.
4. Utiliser une zone d'un autre projet : attendu 403.
5. Sur projet collaboratif, sans `can_manage_missions` : attendu 403.
6. Avec `can_manage_missions` : création autorisée pour le partenaire.
7. Vérifier que le code MISSION-xxxx n'est pas modifiable.
8. Vérifier GPS et choix carte sur PC et téléphone.

## Événements
1. Créer un événement A avec projet/zone/équipe A : attendu succès.
2. Injecter une équipe B ou zone incohérente : attendu 403.
3. Projet collaboratif sans `can_intervene` : attendu 403.
4. Projet collaboratif avec `can_intervene` : attendu succès.
5. Vérifier la génération du code EVT-xxxx.
6. Vérifier qu'un second événement ne peut pas réutiliser le même code via la base.
7. Vérifier GPS/carte sur PC et téléphone.

## Collaboration et lecture
1. Une mission/événement partenaire attaché à un projet partagé est visible au propriétaire si `can_view=1`.
2. Une association sans collaboration ne peut pas ouvrir directement l'URL : attendu 403.
3. Les boutons Modifier/Supprimer ne doivent pas apparaître pour l'association qui ne possède pas la ressource opérationnelle.

## Régression
- Liste équipes, missions, événements.
- Filtres du Lot 6.
- Carte du Lot 5.
- Projet → Zone → Arbre du Lot 7.
- Compilation `python -m py_compile app.py`.
