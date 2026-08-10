# Bugs et limites connus — v1.8.0 Alpha 8

- Les exports sont fournis en CSV compatible Excel ; l'export XLSX natif et le PDF seront étudiés après stabilisation.
- Les tâches apparaissent sur la carte uniquement lorsqu'elles sont rattachées à une zone possédant des coordonnées GPS.
- Le module `volunteer_time_logs` est préparé dans la base pour les heures de bénévolat ; son interface détaillée de saisie et validation reste à compléter dans une version suivante.
- Les tests HTTP automatisés n'ont pas pu être exécutés dans l'environnement de construction faute de Flask installé.
