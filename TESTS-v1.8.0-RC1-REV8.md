# Tests RC1 Rev.8

- Compilation Python : OK.
- Routes dons en nature et distribution présentes : OK.
- Colonnes stock_source / stock_deducted migrées : vérification statique OK.
- Protection anti double synchronisation des dons en nature : OK (table donation_stock_sync).
- Contrôle de stock avant plantation/distribution : OK par inspection du flux.
- Tests HTTP complets : à effectuer sur l'installation réelle (Flask indisponible dans l'environnement de construction).
