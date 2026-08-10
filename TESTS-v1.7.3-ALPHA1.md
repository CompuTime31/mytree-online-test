# Tests v1.7.3 Alpha 1

## Tests réalisés

- Compilation Python : `python -m py_compile app.py` — réussie.
- Vérification de la présence des nouvelles routes et du nouveau schéma SQLite.
- Vérification de l’intégrité de l’archive ZIP.

## Tests terrain à réaliser

1. Administrateur sur PC et bénévole sur téléphone, même réseau.
2. Créer une plantation avec le compte bénévole.
3. Vérifier la redirection vers la fiche et l’affichage du QR provisoire.
4. Vérifier la notification rouge côté administrateur.
5. Ouvrir la notification et accepter la plantation depuis la fiche.
6. Vérifier la notification d’acceptation côté bénévole.
7. Tester Refuser avec motif sur une autre plantation.
8. Tester Scanner QR : caméra, image de galerie et saisie manuelle.
9. Tester GPS dans la création d’une plantation.
10. Tester le bouton Itinéraire vers Google Maps.
11. Retirer puis accorder les permissions Missions, Interventions et Équipe.
12. Vérifier que les menus apparaissent uniquement après autorisation.

## Accès réseau

Pour la caméra et le GPS sur téléphone, privilégier une adresse HTTPS. Une adresse comme `http://192.168.x.x:8080` peut être bloquée par le navigateur mobile pour les API sensibles.
