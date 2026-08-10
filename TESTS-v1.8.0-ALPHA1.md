# Plan de tests — v1.8.0 Alpha 1

## Contrôles réalisés
- Compilation Python de `app.py` réussie.
- Présence des routes événements vérifiée dans le code.
- Présence des deux nouvelles tables vérifiée.
- Permissions événements ajoutées au modèle de droits.
- Version et lanceur Windows mis à jour.

## Scénario administrateur
1. Ouvrir Événements.
2. Créer un événement avec capacité de 2 personnes.
3. L’associer à un projet, une zone et une équipe.
4. Modifier son état.
5. Pointer un participant présent.

## Scénario bénévole
1. Se connecter avec un compte bénévole.
2. Ouvrir Événements.
3. S’inscrire.
4. Annuler puis refaire l’inscription.
5. Vérifier que le troisième bénévole est bloqué lorsque la capacité est atteinte.
6. Ouvrir l’itinéraire Google Maps.
