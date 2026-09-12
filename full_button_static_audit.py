"""Static regression audit of Web PC/Web mobile buttons and Android server endpoints.
Requires only Python stdlib. It validates literal internal destinations against Flask route declarations.
"""
import re,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
ANDROID_ROOT=BASE.parent.parent/'android'
ANDROID='\n'.join(p.read_text(encoding='utf-8',errors='ignore') for p in ANDROID_ROOT.rglob('*.kt')) if ANDROID_ROOT.exists() else ''
routes=[]
# @app.route('/x', methods=[...])
for m in re.finditer(r"@app\.route\(\s*(['\"])(.*?)\1([^)]*)\)",APP):
    path=m.group(2);tail=m.group(3); mm=re.search(r'methods\s*=\s*\[([^]]+)\]',tail)
    methods={'GET'} if not mm else {x.strip().strip("'\"") for x in mm.group(1).split(',')}
    routes.append((path,methods))
# @app.get/post/put/delete('/x')
for m in re.finditer(r"@app\.(get|post|put|delete)\(\s*(['\"])(.*?)\2",APP): routes.append((m.group(3),{m.group(1).upper()}))

def to_rx(route):
    parts=[]; pos=0
    for m in re.finditer(r'<(?:(int|string|path):)?([^>]+)>',route):
        parts.append(re.escape(route[pos:m.start()])); typ=m.group(1)
        parts.append(r'\d+' if typ=='int' else (r'.+' if typ=='path' else r'[^/]+'));pos=m.end()
    parts.append(re.escape(route[pos:]));return re.compile('^'+''.join(parts)+'$')
def route_exists(path):
    path=path.split('?',1)[0]
    if any(to_rx(r).match(path) for r,_ in routes): return True
    # concatenated prefix such as '/public/tree/' + id
    return any('<' in r and r.startswith(path) for r,_ in routes)

targets=[]
for kind,rx in [
 ('href',r'href\s*=\s*["\'](/[^"\'{} ]*)["\']'),
 ('action',r'action\s*=\s*["\'](/[^"\'{} ]*)["\']'),
 ('formaction',r'formaction\s*=\s*["\'](/[^"\'{} ]*)["\']'),
 ('js-location',r'(?:location\.href|window\.location)\s*=\s*["\'](/[^"\'{} ]*)["\']')]:
    targets += [(kind,u) for u in re.findall(rx,APP)]
missing_web=sorted(set((k,u) for k,u in targets if not route_exists(u)))
android_paths=sorted(set(re.findall(r'["\'](/api/v1/[A-Za-z0-9_./?=&-]*)["\']',ANDROID)))
missing_android=[]
for u in android_paths:
    path=u.split('?',1)[0]
    # API client often appends IDs to a literal prefix ending '/'. Accept matching dynamic route prefix.
    if not route_exists(path): missing_android.append(u)
# Explicit menu parity destinations must resolve.
menu_paths=sorted(set(re.findall(r"\('(/[^']*)','[^']*','[^']*'",APP)))
missing_menu=[u for u in menu_paths if not route_exists(u)]
report={'web_routes':len(routes),'web_literal_targets_checked':len(set(targets)),'menu_destinations_checked':len(menu_paths),'android_api_literals_checked':len(android_paths),'missing_web_targets':missing_web,'missing_menu_targets':missing_menu,'missing_android_api_targets':missing_android}
print(json.dumps(report,ensure_ascii=False,indent=2))
if missing_web or missing_menu or missing_android: raise SystemExit(2)
