"""Generate a deterministic large MyTree demo database for regression testing.
Uses only Python stdlib. It NEVER overwrites production mytree.db.
"""
import os,re,random,sqlite3,hashlib
from pathlib import Path
from datetime import datetime,timedelta,date
BASE=Path(__file__).resolve().parent

def demo_password_hash(password,salt):
    # Werkzeug-compatible PBKDF2 hash without requiring Flask/Werkzeug to generate the demo DB.
    iterations=1000
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt.encode('utf-8'),iterations).hex()
    return f'pbkdf2:sha256:{iterations}${salt}${digest}'
OUT=Path(os.environ.get('MYTREE_DEMO_DB', BASE/'demo'/'mytree_large_test.db'))
OUT.parent.mkdir(parents=True,exist_ok=True)
if OUT.exists(): OUT.unlink()
text=(BASE/'app.py').read_text(encoding='utf-8')
m=re.search(r"SCHEMA='''(.*?)'''",text,re.S)
if not m: raise SystemExit('SCHEMA not found')
c=sqlite3.connect(OUT); c.row_factory=sqlite3.Row
c.executescript(m.group(1))
# Add additive columns normally introduced by init_db/migrate_legacy.
def cols(t): return {r[1] for r in c.execute(f'PRAGMA table_info({t})')}
def add(t,decl):
    name=decl.split()[0]
    if name not in cols(t): c.execute(f'ALTER TABLE {t} ADD COLUMN {decl}')
for t in ['projects','zones','teams','missions','events','trees','members','donations','cash_movements','agents','agent_payments','purchase_records','purchase_groups','operational_tasks','nursery_stock','nursery_movements','equipment','memberships','watering_batches','assignments']:
    try:add(t,'association_id INTEGER')
    except sqlite3.OperationalError: pass
for d in ['family TEXT','origin TEXT','algeria_presence TEXT','regions TEXT','soil_type TEXT','sun_exposure TEXT','drought_tolerance TEXT','cold_tolerance TEXT','salt_tolerance TEXT','wind_tolerance TEXT','planting_distance TEXT','adult_height TEXT','growth_rate TEXT','planting_period TEXT','uses TEXT']:
    try:add('species',d)
    except:pass
for d in ['is_read INTEGER DEFAULT 0']:
    try:add('notifications',d)
    except:pass

for d in ['created_by_user_id INTEGER','created_at TEXT','updated_at TEXT']:
    try:add('teams',d)
    except:pass
try:add('events','code TEXT')
except:pass
for d in ['category TEXT','action_type TEXT','action_id INTEGER','decision TEXT','read_at TEXT','processed_at TEXT']:
    try:add('notifications',d)
    except:pass
for d in ['requested_map_symbol TEXT','requested_login_id TEXT','requested_password_hash TEXT',"organization_type TEXT DEFAULT 'volunteer_group'",'approval_number TEXT','approval_document TEXT','approval_document_name TEXT','approval_document_mime TEXT']:
    try:add('association_creation_requests',d)
    except:pass
# new messaging table wins over historic messages table
c.execute("CREATE TABLE IF NOT EXISTS internal_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,thread_id INTEGER NOT NULL,sender_user_id INTEGER,sender_association_id INTEGER,body TEXT NOT NULL,created_at TEXT NOT NULL)")
# deterministic base geography/catalog
now=datetime.now(); ts=lambda d=0:(now+timedelta(days=d)).isoformat(timespec='minutes'); rng=random.Random(1618)
roles=[('super_admin','Super administrateur',100),('volunteer','Bénévole',10)]
for n,l,lv in roles:c.execute('INSERT OR IGNORE INTO roles(name,label,level) VALUES(?,?,?)',(n,l,lv))
adminrole=c.execute("SELECT id FROM roles WHERE name='super_admin'").fetchone()[0]; volrole=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()[0]
c.execute("INSERT OR IGNORE INTO wilayas(code,name) VALUES('31','Oran')"); oran=c.execute("SELECT id FROM wilayas WHERE code='31'").fetchone()[0]
for n in ['Oran','Bir El Djir','Es Sénia','Aïn El Turk','Sidi Chami','Hassi Bounif','Misserghin','Gdyel']:
    c.execute('INSERT OR IGNORE INTO communes(wilaya_id,name) VALUES(?,?)',(oran,n))
communes=[r[0] for r in c.execute('SELECT id FROM communes WHERE wilaya_id=?',(oran,))]
for i,n in enumerate(['Caroubier','Olivier','Mûrier','Pistachier','Eucalyptus','Figuier','Pin d’Alep','Cyprès','Grenadier','Amandier','Sidr','Acacia'],1):
    c.execute('INSERT OR IGNORE INTO species(name_fr,name_ar,name_en,scientific_name,category,water_need,watering_frequency_days,color,active,created_at) VALUES(?,?,?,?,?,?,?,?,1,?)',(n,n,n,n,'Forestier','Moyen',7,'#2e7b47',ts(-1000)))
sp=[r[0] for r in c.execute('SELECT id FROM species')]
# RC16.18.1: demo accounts use real Werkzeug hashes so the large test database supports real login flows.
c.execute("INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('Super','Admin','Super Admin','Homme','0550002026','admin@demo.local','admin',demo_password_hash('MyTree2026!','mytreeadmin2026'),adminrole,'super_admin',1,oran,communes[0],ts(-1000)))
admin=c.execute('SELECT last_insert_rowid()').fetchone()[0]
for i in range(1,301):
    c.execute("INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(f'Bénévole{i}',f'Démo{i}',f'Bénévole {i:03d}','Homme' if i%2 else 'Femme',f'06{i:08d}'[-10:],f'vol{i}@demo.local',f'vol{i:03d}',demo_password_hash('Volunteer2026!','mytreevolunteer2026'),volrole,'volunteer',1,oran,communes[i%len(communes)],ts(-rng.randint(1,900))))
users=[r[0] for r in c.execute("SELECT id FROM users WHERE role='volunteer'")]
assocs=[]
for i in range(1,16):
    c.execute("INSERT INTO associations(code,name,short_name,description,wilaya_id,commune_id,address,latitude,longitude,map_symbol,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(f'DEMO-A{i:02d}',f'Association Démo {i:02d}',f'AD{i:02d}','Association test',oran,communes[i%len(communes)],f'Oran {i}',35.69+rng.random()*.12,-0.72+rng.random()*.18,'🌳','active',admin,ts(-500)))
    aid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; assocs.append(aid)
    c.execute("INSERT INTO association_accounts(association_id,login_id,password_hash,active,created_at) VALUES(?,?,?,?,?)",(aid,f'DEMO-A{i:02d}',demo_password_hash('Association2026!','mytreeassociation2026'),1,ts(-400)))
    for j,uid in enumerate(rng.sample(users,50)):
        c.execute("INSERT OR IGNORE INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at,reviewed_by_user_id,reviewed_at) VALUES(?,?,?,?,?,?,?,?)",(aid,uid,'volunteer','association_admin' if j==0 else 'volunteer','approved',ts(-300),admin,ts(-299)))
projects=[];zones=[]
for ai,aid in enumerate(assocs,1):
    for j in range(1,4):
        code=f'DP-{ai:02d}-{j:02d}';cid=communes[(ai+j)%len(communes)]
        c.execute("INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,manager_user_id,active,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(code,f'Projet Démo {ai}-{j}','En cours',1500,2500000,oran,cid,'Oran',admin,1,aid));pid=c.execute('SELECT last_insert_rowid()').fetchone()[0];projects.append((pid,aid,cid))
        for k in range(1,4):
            c.execute("INSERT INTO zones(project_id,wilaya_id,commune_id,code,name,area,target_trees,color,manager_user_id,active,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(pid,oran,cid,f'Z-{ai}-{j}-{k}',f'Zone {ai}-{j}-{k}',4.0,500,'#3a7d44',admin,1,aid));zones.append((c.execute('SELECT last_insert_rowid()').fetchone()[0],pid,aid,cid))
for i in range(1,8001):
    zid,pid,aid,cid=zones[(i-1)%len(zones)];uid=users[i%len(users)];sid=sp[i%len(sp)]
    health='Bon' if i%10 not in (0,1) else ('À surveiller' if i%10==0 else 'Moyen'); watering='Urgent' if i%13==0 else ('À arroser' if i%7==0 else 'À jour')
    code=f'DTREE-{i:05d}'; lat=35.64+rng.random()*.19;lon=-0.76+rng.random()*.25
    c.execute("INSERT INTO trees(tree_code,qr_code,species_id,species,project_id,zone_id,wilaya_id,commune_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,gps_accuracy,health_status,watering_status,last_watered_at,approval_status,approved_by_user_id,approved_at,planting_type,notes,active,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(code,'QR-'+code,sid,None,pid,zid,oran,cid,(date.today()-timedelta(days=i%900)).isoformat(),uid,f'Bénévole {uid}',lat,lon,5,health,watering,ts(-(i%20)),'approved',admin,ts(-(i%800)),'simple','Test volume',1,ts(-(i%900)),aid))
treeids=[r[0] for r in c.execute("SELECT id FROM trees WHERE tree_code LIKE 'DTREE-%'")]
teamids=[]
for i,(pid,aid,cid) in enumerate(projects,1):
    c.execute("INSERT INTO teams(code,name,leader_user_id,project_id,zone_id,phone,mission,active,created_by_user_id,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(f'DTEAM-{i:03d}',f'Équipe {i:03d}',users[i%len(users)],pid,zones[i%len(zones)][0],'0550000000','Terrain',1,admin,ts(-100),ts(),aid));teamids.append(c.execute('SELECT last_insert_rowid()').fetchone()[0])
for i in range(1,301):
    pid,aid,cid=projects[i%len(projects)];zid=zones[i%len(zones)][0]
    c.execute("INSERT INTO missions(code,title,mission_type,status,priority,project_id,zone_id,team_id,leader_user_id,start_at,end_at,target_count,completed_count,description,active,created_by_user_id,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(f'DMIS-{i:04d}',f'Mission {i:04d}','Arrosage',['Planifiée','En cours','Terminée'][i%3],'Normale',pid,zid,teamids[i%len(teamids)],users[i%len(users)],ts(i%90-30),ts(i%90-29),100,i%100,'Mission test',1,admin,ts(-100),ts(),aid))
for i in range(1,501):
    c.execute("INSERT INTO interventions(tree_id,user_id,intervention_type,status,planned_at,performed_at,quantity,unit,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(treeids[i%len(treeids)],users[i%len(users)],['Arrosage','Taille','Observation'][i%3],'Réalisée',ts(-(i%30)),ts(-(i%30)),10,'L','Test',ts(-(i%30))))
for i in range(1,121):
    pid,aid,cid=projects[i%len(projects)];zid=zones[i%len(zones)][0]
    c.execute("INSERT INTO events(code,title,event_type,status,start_at,end_at,location,project_id,zone_id,max_participants,description,active,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(f'DEV-{i:04d}',f'Événement {i:03d}','Plantation','Planifié',ts(i%120),ts(i%120+1),'Oran',pid,zid,100,'Événement test',1,admin,ts(-30),aid))
for i in range(1,1201):
    c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,?,?)",(users[i%len(users)],f'Notification {i}',f'Message {i}','/notifications','Test',1 if i%3==0 else 0,ts(-(i%60))))
for i in range(1,201):
    c.execute("INSERT INTO donors(name,donor_type,phone,created_at) VALUES(?,?,?,?)",(f'Donateur {i:03d}','Particulier',f'077{i:07d}'[-10:],ts(-i)));did=c.execute('SELECT last_insert_rowid()').fetchone()[0];aid=assocs[i%len(assocs)]
    c.execute("INSERT INTO donations(donor_id,donation_type,status,amount,currency,quantity,unit,received_at,estimated_value,receipt_number,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,'Argent','Confirmé',1000+i*50,'DZD',0,'DA',date.today().isoformat(),1000+i*50,f'DON-{i:05d}',admin,ts(-i),aid))
for i in range(1,401):
    c.execute("INSERT INTO members(member_number,first_name,last_name,sex,phone,member_type,membership_date,active,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?)",(f'M-{i:05d}',f'Adhérent{i}',f'Démo{i}','Homme' if i%2 else 'Femme',f'056{i:07d}'[-10:],'Adhérent',date.today().isoformat(),1,ts(-i),assocs[i%len(assocs)]))
for i in range(1,501):
    c.execute("INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,status,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?)",('Association','Recette' if i%2 else 'Dépense',500+i*10,'Test',f'Mouvement {i}','Validé',admin,ts(-(i%180)),assocs[i%len(assocs)]))
for aid in assocs:
    for sid in sp:
        c.execute("INSERT OR IGNORE INTO nursery_stock(species_id,quantity_available,quantity_reserved,quantity_planted,quantity_lost,low_stock_threshold,unit_value,location,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?)",(sid,100,10,50,2,10,500,'Pépinière Démo',ts(),aid))
for i in range(1,161):
    creator=users[i%len(users)];aid=assocs[i%len(assocs)]
    c.execute("INSERT INTO message_threads(subject,created_by_user_id,created_at,updated_at) VALUES(?,?,?,?)",(f'Conversation {i:03d}',creator,ts(-i),ts(-i)));th=c.execute('SELECT last_insert_rowid()').fetchone()[0]
    c.execute("INSERT INTO message_participants(thread_id,user_id,participant_type) VALUES(?,?,?)",(th,creator,'user'));c.execute("INSERT INTO message_participants(thread_id,association_id,participant_type) VALUES(?,?,?)",(th,aid,'association'))
    for j in range(4):c.execute("INSERT INTO internal_messages(thread_id,sender_user_id,sender_association_id,body,created_at) VALUES(?,?,?,?,?)",(th,creator if j%2==0 else None,aid if j%2 else None,f'Message {i}-{j+1}',ts(-i)))
for i in range(1,151):
    c.execute("INSERT INTO app_suggestions(author_user_id,title,description,category,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(users[i%len(users)],f'Suggestion {i:03d}','Suggestion test','Amélioration',['Nouvelle','En étude','Acceptée'][i%3],ts(-i),ts(-i)))
c.commit();c.execute('ANALYZE');c.commit()
summary={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['users','associations','projects','zones','trees','missions','interventions','events','notifications','donations','members','cash_movements','message_threads','internal_messages','app_suggestions']};c.close()
print(OUT);print(summary)
