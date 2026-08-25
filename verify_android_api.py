"""Static verification for MyTree Android API v1 routes."""
from pathlib import Path
import re, sys
app = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
required = [
    ('GET','/api/v1'), ('GET','/api/v1/status'), ('GET','/api/v1/app-version'),
    ('POST','/api/v1/auth/login'), ('GET','/api/v1/auth/me'), ('POST','/api/v1/auth/logout'),
    ('GET','/api/v1/associations'), ('POST','/api/v1/context/association'), ('GET','/api/v1/home'),
    ('GET','/api/v1/map')
]
missing=[]
for method,path in required:
    pat = rf"@app\.{method.lower()}\(['\"]{re.escape(path)}['\"]\)"
    if not re.search(pat, app): missing.append(f'{method} {path}')
if missing:
    print('MISSING API ROUTES:')
    print('\n'.join(missing))
    sys.exit(1)
print(f'OK: {len(required)} critical Android API routes found.')
