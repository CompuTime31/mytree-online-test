# Lot 12 — FIXED3

- Bénévole simple : sélecteur Contexte masqué.
- Mes arbres : bouton `🗺️ Ma carte`.
- Ma carte : ouvre la Carte commune avec `Mes arbres` actif.
- `✕ Supprimer le filtre` : retour à tous les arbres accessibles en lecture.
- Carte commune : arbres seuls par défaut.
- Zones et événements : couches optionnelles depuis `🔎 Filtrer`.
- Popup arbre : `Voir la fiche` + `📍 Itinéraire` Google Maps.
- Carte publique : itinéraire disponible sans compte.
- QR nouveaux : ouvrent `/public/map?tree=<id>`, centrent l'arbre et ouvrent sa popup.
- QR anciens `/tree/<id>?token=...` : redirection automatique vers la carte publique si visiteur non connecté.
- Mes associations : boutons téléphone/PC `Rejoindre` et `Demander la création`.
- Suivi des demandes de création : statut et motif de refus.
- Super Admin : accès visible aux demandes d'association et à la liste de gestion.
- Aucune migration SQLite.
