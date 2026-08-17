#!/usr/bin/env python3
import os, sqlite3, sys
from pathlib import Path
DATA_DIR=Path(os.environ.get('MYTREE_DATA_DIR', Path(__file__).resolve().parent))
DB=DATA_DIR/'mytree.db'
required={'users','projects','zones','trees','associations','association_memberships','association_collaborations','notifications','submission_tokens'}
errors=[]; warnings=[]
secret=os.environ.get('MYTREE_SECRET','')
if not secret or secret=='change-this-secret' or len(secret)<24:
    errors.append('MYTREE_SECRET absent ou trop court (24 caractères minimum recommandés).')
if not DATA_DIR.exists():
    errors.append(f'Dossier de données absent: {DATA_DIR}')
if DATA_DIR.exists() and not os.access(DATA_DIR,os.W_OK):
    errors.append(f'Dossier de données non inscriptible: {DATA_DIR}')
if not DB.exists():
    warnings.append(f'Base absente: {DB} — elle sera créée au premier démarrage.')
else:
    try:
        c=sqlite3.connect(DB,timeout=10)
        integrity=c.execute('PRAGMA quick_check').fetchone()[0]
        if integrity!='ok': errors.append('PRAGMA quick_check: '+str(integrity))
        names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing=sorted(required-names)
        if missing: warnings.append('Tables Lot 12 absentes avant migration: '+', '.join(missing))
        fk=c.execute('PRAGMA foreign_key_check').fetchall()
        if fk: warnings.append(f'{len(fk)} anomalie(s) de clé étrangère détectée(s).')
        c.close()
    except Exception as exc: errors.append('Lecture base impossible: '+str(exc))
print('MyTree Alpha 4 Lot 12 — Preflight')
print('DATA_DIR:',DATA_DIR)
print('DB:',DB)
for x in warnings: print('WARNING:',x)
for x in errors: print('ERROR:',x)
print('RESULT:', 'FAIL' if errors else 'OK')
sys.exit(1 if errors else 0)
