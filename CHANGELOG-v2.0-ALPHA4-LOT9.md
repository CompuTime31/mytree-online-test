# MyTree Professional v2.0 Alpha 4 — Lot 9
## Notifications & Confirmations

- Confirmation visuelle homogène après opérations via messages flash succès / avertissement / erreur.
- Conservation du modèle POST → Redirect → GET afin de sortir des formulaires après validation et d'éviter le repost au rafraîchissement.
- Protection anti-double soumission côté navigateur : désactivation immédiate des boutons après un POST valide.
- Protection anti-double enregistrement côté serveur : jeton `_submit_token` unique et table `submission_tokens` avec clé primaire atomique.
- Les doublons sont interceptés et redirigés sans rejouer l'opération métier.
- Ajout de `read_at` et `processed_at` aux notifications.
- L'ouverture de la liste `/notifications` ne marque aucune notification comme lue.
- Une notification devient lue uniquement après ouverture explicite, action « Marquer lue » ou traitement d'une demande.
- Une décision Acceptée/Refusée enregistre également `processed_at`.
- « Tout marquer lu » ne touche que les notifications informatives sans action à traiter.
- Affichage des dates de lecture et de traitement dans le centre de notifications.
