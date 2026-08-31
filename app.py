from flask import Flask, request, redirect, session, flash, render_template_string, send_file, send_from_directory, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from functools import wraps
from datetime import datetime, date, timedelta
import sqlite3, os, io, json, shutil, tempfile, urllib.request, urllib.parse, secrets, smtplib, base64
from email.message import EmailMessage
from data_catalogs import SPECIES_CATALOG, EQUIPMENT_CATALOG
import qrcode

BASE_DIR=os.path.abspath(os.path.dirname(__file__))
DATA_DIR=os.environ.get('MYTREE_DATA_DIR', BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH=os.path.join(DATA_DIR,'mytree.db')
app=Flask(__name__)
app.secret_key=os.environ.get('MYTREE_SECRET','change-this-secret')
app.permanent_session_lifetime=timedelta(days=30)
APP_VERSION='v2.0 Alpha 4 — RC16.1 Test Consolidé — Comptes séparés'

SCHEMA='''
CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,label TEXT NOT NULL,description TEXT,color TEXT DEFAULT '#2e7b47',level INTEGER DEFAULT 10,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS permissions(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS role_permissions(role_id INTEGER,permission_id INTEGER,PRIMARY KEY(role_id,permission_id));
CREATE TABLE IF NOT EXISTS user_permissions(user_id INTEGER,permission_id INTEGER,granted INTEGER DEFAULT 1,PRIMARY KEY(user_id,permission_id));
CREATE TABLE IF NOT EXISTS association_audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,association_id INTEGER,permission_code TEXT,action TEXT,resource_type TEXT,resource_id INTEGER,result TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wilayas(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT UNIQUE NOT NULL,name_ar TEXT,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS communes(id INTEGER PRIMARY KEY AUTOINCREMENT,wilaya_id INTEGER NOT NULL,name TEXT NOT NULL,name_ar TEXT,active INTEGER DEFAULT 1,UNIQUE(wilaya_id,name));
CREATE TABLE IF NOT EXISTS species(id INTEGER PRIMARY KEY AUTOINCREMENT,name_fr TEXT UNIQUE NOT NULL,name_ar TEXT,name_en TEXT,scientific_name TEXT,category TEXT,water_need TEXT,watering_frequency_days INTEGER,color TEXT DEFAULT '#2e7b47',description TEXT,photo_url TEXT,active INTEGER DEFAULT 1,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,first_name TEXT,last_name TEXT,name TEXT,sex TEXT,phone TEXT UNIQUE,email TEXT,username TEXT UNIQUE,password_hash TEXT NOT NULL,role_id INTEGER,role TEXT,active INTEGER DEFAULT 1,wilaya_id INTEGER,commune_id INTEGER,team_id INTEGER,created_at TEXT,last_login TEXT,birth_date TEXT,address TEXT,skills TEXT,availability TEXT,photo_url TEXT,preferred_language TEXT DEFAULT 'fr');
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,status TEXT DEFAULT 'Brouillon',target_trees INTEGER DEFAULT 0,budget REAL DEFAULT 0,wilaya_id INTEGER,commune_id INTEGER,location TEXT,manager_user_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS zones(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,wilaya_id INTEGER,commune_id INTEGER,code TEXT,name TEXT NOT NULL,area REAL DEFAULT 0,target_trees INTEGER DEFAULT 0,color TEXT DEFAULT '#3a7d44',manager_user_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sectors(id INTEGER PRIMARY KEY AUTOINCREMENT,zone_id INTEGER NOT NULL,code TEXT,name TEXT NOT NULL,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT NOT NULL,leader_user_id INTEGER,project_id INTEGER,zone_id INTEGER,phone TEXT,mission TEXT,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,event_type TEXT NOT NULL,status TEXT DEFAULT 'Planifié',start_at TEXT NOT NULL,end_at TEXT,location TEXT,project_id INTEGER,zone_id INTEGER,team_id INTEGER,max_participants INTEGER DEFAULT 0,description TEXT,latitude REAL,longitude REAL,active INTEGER DEFAULT 1,created_by_user_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS event_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT DEFAULT 'Inscrit',registered_at TEXT NOT NULL,attendance_status TEXT DEFAULT 'Non pointé',checked_in_at TEXT,notes TEXT,UNIQUE(event_id,user_id));
CREATE TABLE IF NOT EXISTS trees(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_code TEXT UNIQUE,qr_code TEXT UNIQUE,species_id INTEGER,species TEXT,project_id INTEGER,zone_id INTEGER,wilaya_id INTEGER,commune_id INTEGER,sector_id INTEGER,sector TEXT,planted_at TEXT,planted_by_user_id INTEGER,planted_by TEXT,latitude REAL,longitude REAL,gps_accuracy REAL,health_status TEXT DEFAULT 'Bon',watering_status TEXT DEFAULT 'À jour',last_watered_at TEXT,approval_status TEXT DEFAULT 'approved',approved_by_user_id INTEGER,approved_at TEXT,rejection_reason TEXT,planting_type TEXT DEFAULT 'simple',notes TEXT,active INTEGER DEFAULT 1,created_at TEXT);
CREATE TABLE IF NOT EXISTS watering_batches(id INTEGER PRIMARY KEY AUTOINCREMENT,zone_id INTEGER NOT NULL,user_id INTEGER,watered_at TEXT NOT NULL,tree_count INTEGER DEFAULT 0,total_liters REAL,source TEXT,notes TEXT,latitude REAL,longitude REAL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watering_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,watered_at TEXT NOT NULL,user_id INTEGER,volunteer TEXT,quantity_range TEXT,quantity_liters REAL,source TEXT,notes TEXT,latitude REAL,longitude REAL,photo_url TEXT,tree_condition TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,project_id INTEGER,zone_id INTEGER,team_id INTEGER,role_label TEXT,start_date TEXT,end_date TEXT,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS activity_log(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,details TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS team_members(id INTEGER PRIMARY KEY AUTOINCREMENT,team_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT DEFAULT 'active',joined_at TEXT,approved_by_user_id INTEGER,approved_at TEXT,UNIQUE(team_id,user_id));
CREATE TABLE IF NOT EXISTS team_join_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,team_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT DEFAULT 'pending',requested_at TEXT,reviewed_by_user_id INTEGER,reviewed_at TEXT,rejection_reason TEXT,UNIQUE(team_id,user_id,status));
CREATE TABLE IF NOT EXISTS planting_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,reviewer_user_id INTEGER NOT NULL,decision TEXT NOT NULL,reason TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,title TEXT NOT NULL,mission_type TEXT,status TEXT DEFAULT 'Planifiée',priority TEXT DEFAULT 'Normale',project_id INTEGER,zone_id INTEGER,team_id INTEGER,leader_user_id INTEGER,start_at TEXT,end_at TEXT,target_count INTEGER DEFAULT 0,completed_count INTEGER DEFAULT 0,description TEXT,report TEXT,latitude REAL,longitude REAL,active INTEGER DEFAULT 1,created_by_user_id INTEGER,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS mission_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attendance_status TEXT DEFAULT 'Invité',notes TEXT,created_at TEXT,UNIQUE(mission_id,user_id));
CREATE TABLE IF NOT EXISTS mission_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id INTEGER NOT NULL,user_id INTEGER,action_type TEXT NOT NULL,details TEXT,quantity INTEGER DEFAULT 0,latitude REAL,longitude REAL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mission_photos(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id INTEGER NOT NULL,user_id INTEGER,photo_url TEXT NOT NULL,caption TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,mission_id INTEGER,user_id INTEGER NOT NULL,intervention_type TEXT NOT NULL,status TEXT DEFAULT 'Réalisée',planned_at TEXT,performed_at TEXT,quantity REAL,unit TEXT,notes TEXT,photo_url TEXT,next_due_at TEXT,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS intervention_reminders(id INTEGER PRIMARY KEY AUTOINCREMENT,intervention_id INTEGER,tree_id INTEGER NOT NULL,reminder_type TEXT NOT NULL,due_at TEXT NOT NULL,status TEXT DEFAULT 'À faire',assigned_user_id INTEGER,notes TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL,completed_at TEXT);
CREATE TABLE IF NOT EXISTS project_phases(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,name TEXT NOT NULL,status TEXT DEFAULT 'À faire',start_date TEXT,end_date TEXT,progress INTEGER DEFAULT 0,notes TEXT,position INTEGER DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS operational_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,task_type TEXT NOT NULL,status TEXT DEFAULT 'Planifiée',priority TEXT DEFAULT 'Normale',project_id INTEGER,zone_id INTEGER,team_id INTEGER,assigned_user_id INTEGER,start_at TEXT NOT NULL,end_at TEXT,description TEXT,completed_at TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS volunteer_time_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,project_id INTEGER,task_id INTEGER,work_date TEXT NOT NULL,hours REAL NOT NULL,activity TEXT,notes TEXT,validated INTEGER DEFAULT 0,validated_by_user_id INTEGER,created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT NOT NULL,message TEXT,link TEXT,category TEXT DEFAULT 'Général',action_type TEXT,action_id INTEGER,decision TEXT,is_read INTEGER DEFAULT 0,read_at TEXT,processed_at TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submission_tokens(token TEXT PRIMARY KEY,user_id INTEGER,route TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_user_id INTEGER NOT NULL,recipient_user_id INTEGER,team_id INTEGER,project_id INTEGER,zone_id INTEGER,subject TEXT,body TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,login_value TEXT,success INTEGER DEFAULT 0,ip_address TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS password_reset_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,phone TEXT NOT NULL,code_hash TEXT NOT NULL,expires_at TEXT NOT NULL,used INTEGER DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tree_photos(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,photo_url TEXT NOT NULL,caption TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tree_observations(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,observation TEXT NOT NULL,health_status TEXT,photo_url TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tree_change_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,requested_by_user_id INTEGER NOT NULL,changes_json TEXT NOT NULL,reason TEXT,status TEXT DEFAULT 'pending',reviewed_by_user_id INTEGER,reviewed_at TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tree_gps_history(id INTEGER PRIMARY KEY AUTOINCREMENT,tree_id INTEGER NOT NULL,old_latitude REAL,old_longitude REAL,new_latitude REAL,new_longitude REAL,accuracy REAL,changed_by_user_id INTEGER,reason TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_preferences(user_id INTEGER NOT NULL,key TEXT NOT NULL,value TEXT,PRIMARY KEY(user_id,key));
CREATE TABLE IF NOT EXISTS donors(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,donor_type TEXT DEFAULT 'Particulier',phone TEXT,email TEXT,address TEXT,notes TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS donation_groups(id INTEGER PRIMARY KEY AUTOINCREMENT,donor_id INTEGER,status TEXT DEFAULT 'Confirmé',receipt_number TEXT,received_at TEXT NOT NULL,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS donations(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER,donor_id INTEGER,donation_type TEXT NOT NULL,status TEXT DEFAULT 'Confirmé',amount REAL DEFAULT 0,currency TEXT DEFAULT 'DZD',quantity REAL DEFAULT 0,unit TEXT,description TEXT,received_at TEXT NOT NULL,estimated_value REAL DEFAULT 0,species_id INTEGER,equipment_id INTEGER,receipt_number TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nursery_stock(id INTEGER PRIMARY KEY AUTOINCREMENT,species_id INTEGER NOT NULL,quantity_available INTEGER DEFAULT 0,quantity_reserved INTEGER DEFAULT 0,quantity_planted INTEGER DEFAULT 0,quantity_lost INTEGER DEFAULT 0,low_stock_threshold INTEGER DEFAULT 10,unit_value REAL DEFAULT 0,location TEXT,updated_at TEXT NOT NULL,UNIQUE(species_id,location));
CREATE TABLE IF NOT EXISTS nursery_movements(id INTEGER PRIMARY KEY AUTOINCREMENT,stock_id INTEGER NOT NULL,movement_type TEXT NOT NULL,quantity INTEGER NOT NULL,notes TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS donation_stock_sync(donation_id INTEGER PRIMARY KEY,sync_type TEXT NOT NULL,stock_id INTEGER,quantity INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nursery_distributions(id INTEGER PRIMARY KEY AUTOINCREMENT,beneficiary_name TEXT NOT NULL,beneficiary_type TEXT NOT NULL,stock_id INTEGER NOT NULL,quantity INTEGER NOT NULL,distribution_date TEXT NOT NULL,project_id INTEGER,notes TEXT,justification TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equipment(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT,inventory_code TEXT UNIQUE,quantity_total INTEGER DEFAULT 0,quantity_available INTEGER DEFAULT 0,condition_status TEXT DEFAULT 'Bon',location TEXT,notes TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS equipment_loans(id INTEGER PRIMARY KEY AUTOINCREMENT,equipment_id INTEGER NOT NULL,user_id INTEGER NOT NULL,quantity INTEGER DEFAULT 1,loaned_at TEXT NOT NULL,due_at TEXT,returned_at TEXT,status TEXT DEFAULT 'En cours',notes TEXT,created_by_user_id INTEGER);
CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,member_number TEXT UNIQUE NOT NULL,first_name TEXT NOT NULL,last_name TEXT NOT NULL,sex TEXT,birth_date TEXT,phone TEXT,email TEXT,address TEXT,wilaya_id INTEGER,commune_id INTEGER,profession TEXT,emergency_contact TEXT,photo_url TEXT,member_type TEXT DEFAULT 'Adhérent',membership_date TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS memberships(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER NOT NULL,membership_year INTEGER NOT NULL,amount REAL NOT NULL,status TEXT DEFAULT 'Payée',paid_at TEXT,payment_method TEXT DEFAULT 'Espèces',receipt_number TEXT UNIQUE,notes TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL,UNIQUE(member_id,membership_year));
CREATE TABLE IF NOT EXISTS cash_movements(id INTEGER PRIMARY KEY AUTOINCREMENT,fund_type TEXT NOT NULL,movement_type TEXT NOT NULL,amount REAL NOT NULL,category TEXT,description TEXT,reference_type TEXT,reference_id INTEGER,project_id INTEGER,zone_id INTEGER,justification TEXT,status TEXT DEFAULT 'Validé',created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agents(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT,function_title TEXT,active INTEGER DEFAULT 1,notes TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_payments(id INTEGER PRIMARY KEY AUTOINCREMENT,agent_id INTEGER NOT NULL,work_type TEXT NOT NULL,period_label TEXT,project_id INTEGER,zone_id INTEGER,hours REAL DEFAULT 0,days REAL DEFAULT 0,total_amount REAL NOT NULL,from_memberships REAL DEFAULT 0,from_donations REAL DEFAULT 0,payment_date TEXT NOT NULL,payment_method TEXT DEFAULT 'Espèces',justification TEXT NOT NULL,notes TEXT,status TEXT DEFAULT 'Validé',created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS purchase_records(id INTEGER PRIMARY KEY AUTOINCREMENT,purchase_type TEXT NOT NULL,item_id INTEGER,quantity REAL DEFAULT 0,total_amount REAL NOT NULL,from_memberships REAL DEFAULT 0,from_donations REAL DEFAULT 0,supplier TEXT,project_id INTEGER,zone_id INTEGER,justification TEXT NOT NULL,notes TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS purchase_groups(id INTEGER PRIMARY KEY AUTOINCREMENT,reference TEXT UNIQUE NOT NULL,from_memberships REAL DEFAULT 0,from_donations REAL DEFAULT 0,total_amount REAL DEFAULT 0,supplier TEXT,project_id INTEGER,zone_id INTEGER,justification TEXT NOT NULL,notes TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS purchase_items(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER NOT NULL,item_type TEXT NOT NULL,item_id INTEGER NOT NULL,quantity REAL NOT NULL,line_amount REAL NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS associations(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,short_name TEXT,description TEXT,logo_url TEXT,wilaya_id INTEGER,commune_id INTEGER,address TEXT,latitude REAL,longitude REAL,phone TEXT,email TEXT,website TEXT,map_symbol TEXT DEFAULT '🌳',status TEXT DEFAULT 'active',created_by_user_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS association_memberships(id INTEGER PRIMARY KEY AUTOINCREMENT,association_id INTEGER NOT NULL,user_id INTEGER NOT NULL,member_kind TEXT DEFAULT 'volunteer',role_code TEXT DEFAULT 'volunteer',status TEXT DEFAULT 'pending',requested_at TEXT NOT NULL,reviewed_by_user_id INTEGER,reviewed_at TEXT,rejection_reason TEXT,UNIQUE(association_id,user_id,member_kind));
CREATE TABLE IF NOT EXISTS association_creation_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,requested_by_user_id INTEGER,name TEXT NOT NULL,description TEXT,wilaya_id INTEGER,commune_id INTEGER,address TEXT,phone TEXT,email TEXT,status TEXT DEFAULT 'pending',requested_at TEXT NOT NULL,reviewed_by_user_id INTEGER,reviewed_at TEXT,rejection_reason TEXT);
CREATE TABLE IF NOT EXISTS association_accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,association_id INTEGER UNIQUE NOT NULL,login_id TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,last_login TEXT);
CREATE TABLE IF NOT EXISTS association_archive_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,association_id INTEGER NOT NULL,requested_by_user_id INTEGER NOT NULL,status TEXT DEFAULT 'pending',reason TEXT,requested_at TEXT NOT NULL,reviewed_by_user_id INTEGER,reviewed_at TEXT,rejection_reason TEXT);
CREATE TABLE IF NOT EXISTS association_collaborations(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,inviting_association_id INTEGER NOT NULL,invited_association_id INTEGER NOT NULL,status TEXT DEFAULT 'pending',can_view INTEGER DEFAULT 1,can_intervene INTEGER DEFAULT 1,can_add_tree INTEGER DEFAULT 0,can_manage_missions INTEGER DEFAULT 0,created_by_user_id INTEGER,created_at TEXT NOT NULL,reviewed_by_user_id INTEGER,reviewed_at TEXT,ended_by_user_id INTEGER,ended_at TEXT,end_reason TEXT,UNIQUE(project_id,inviting_association_id,invited_association_id));
CREATE TABLE IF NOT EXISTS association_collaboration_history(id INTEGER PRIMARY KEY AUTOINCREMENT,collaboration_id INTEGER NOT NULL,action TEXT NOT NULL,actor_user_id INTEGER,association_id INTEGER,details TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS association_roles(id INTEGER PRIMARY KEY AUTOINCREMENT,association_id INTEGER NOT NULL,code TEXT NOT NULL,label TEXT NOT NULL,level INTEGER DEFAULT 10,active INTEGER DEFAULT 1,UNIQUE(association_id,code));
CREATE TABLE IF NOT EXISTS user_contexts(user_id INTEGER PRIMARY KEY,context_type TEXT DEFAULT 'personal',association_id INTEGER,updated_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
'''

def db():
 # Lot 12 — SQLite durci pour les essais multi-utilisateurs en ligne.
 c=sqlite3.connect(DB_PATH,timeout=15)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON')
 c.execute('PRAGMA busy_timeout=15000')
 return c

LOT12_BACKUP_TAG='alpha4-lot12-pre-migration'
def backup_before_lot12_migration():
 """Sauvegarde non destructive, une seule fois, avant migration du candidat Online Test."""
 if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH)==0: return None
 marker=os.path.join(DATA_DIR,'.'+LOT12_BACKUP_TAG)
 if os.path.exists(marker): return None
 stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
 backup=os.path.join(DATA_DIR,f'mytree-pre-alpha4-lot12-{stamp}.db')
 src=sqlite3.connect(DB_PATH,timeout=15); dst=sqlite3.connect(backup)
 try: src.backup(dst)
 finally: dst.close(); src.close()
 with open(marker,'w',encoding='utf-8') as f: f.write(os.path.basename(backup))
 return backup

def database_diagnostics(c=None):
 own=c is None; c=c or db()
 try:
  integrity=c.execute('PRAGMA quick_check').fetchone()[0]
  names={r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  required={'users','projects','zones','trees','associations','association_memberships','association_collaborations','notifications','submission_tokens'}
  missing=sorted(required-names)
  fk=c.execute('PRAGMA foreign_key_check').fetchall()
  return {'integrity':integrity,'missing_tables':missing,'foreign_key_errors':len(fk),'tables':len(names)}
 finally:
  if own: c.close()


def columns(c,table): return {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
def add_column(c,table,definition):
 name=definition.split()[0]
 if name not in columns(c,table): c.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')

def migrate_legacy(c):
 # Preserve databases created by Sprint 1.
 if 'users' in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
  for d in ['first_name TEXT','last_name TEXT','sex TEXT','phone TEXT','email TEXT','role_id INTEGER','wilaya_id INTEGER','commune_id INTEGER','team_id INTEGER','created_at TEXT','last_login TEXT','birth_date TEXT','address TEXT','skills TEXT','availability TEXT','photo_url TEXT',"preferred_language TEXT DEFAULT 'fr'"]:
   add_column(c,'users',d)
 for d in ['wilaya_id INTEGER','commune_id INTEGER','manager_user_id INTEGER','active INTEGER DEFAULT 1','description TEXT','start_date TEXT','end_date TEXT','created_at TEXT','updated_at TEXT']:
  add_column(c,'projects',d)
 for d in ['wilaya_id INTEGER','commune_id INTEGER','manager_user_id INTEGER','active INTEGER DEFAULT 1','description TEXT','latitude REAL','longitude REAL','created_at TEXT','updated_at TEXT']:
  add_column(c,'zones',d)
 for d in ['group_id INTEGER']:
  add_column(c,'donations',d)
 for d in ['description TEXT','photo_url TEXT','created_at TEXT','updated_at TEXT','family TEXT','origin TEXT','algeria_presence TEXT','regions TEXT','soil_type TEXT','sun_exposure TEXT','drought_tolerance TEXT','cold_tolerance TEXT','salt_tolerance TEXT','wind_tolerance TEXT','planting_distance TEXT','adult_height TEXT','growth_rate TEXT','planting_period TEXT','uses TEXT','maintenance TEXT','diseases TEXT','compatibility_note TEXT','name_en TEXT']:
  add_column(c,'species',d)
 for d in ['species_id INTEGER','wilaya_id INTEGER','commune_id INTEGER','sector_id INTEGER','planted_by_user_id INTEGER','gps_accuracy REAL',"approval_status TEXT DEFAULT 'approved'",'approved_by_user_id INTEGER','approved_at TEXT','rejection_reason TEXT',"planting_type TEXT DEFAULT 'simple'",'created_at TEXT',"gps_review_status TEXT DEFAULT 'ok'",'gps_updated_at TEXT',"stock_source TEXT DEFAULT 'personal'",'stock_deducted INTEGER DEFAULT 0']:
  add_column(c,'trees',d)
 add_column(c,'notifications',"category TEXT DEFAULT 'Général'")
 for d in ['action_type TEXT','action_id INTEGER','decision TEXT','read_at TEXT','processed_at TEXT']:
  add_column(c,'notifications',d)
 add_column(c,'members','membership_date TEXT')
 for table in ['projects','zones','teams','missions','events','trees','members','donations','cash_movements','agents','agent_payments','purchase_records','purchase_groups','operational_tasks','nursery_stock','nursery_movements','equipment','memberships','watering_batches','assignments']:
  if table in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
   add_column(c,table,'association_id INTEGER')
 add_column(c,'trees',"visibility TEXT DEFAULT 'public'")
 for d in ['can_view INTEGER DEFAULT 1','can_intervene INTEGER DEFAULT 1','can_add_tree INTEGER DEFAULT 0','can_manage_missions INTEGER DEFAULT 0','ended_by_user_id INTEGER','ended_at TEXT','end_reason TEXT']:
  add_column(c,'association_collaborations',d)
 for d in ['species_id INTEGER','equipment_id INTEGER']:
  add_column(c,'donations',d)
 for d in ['user_id INTEGER','quantity_range TEXT','latitude REAL','longitude REAL','photo_url TEXT','tree_condition TEXT','batch_id INTEGER','created_at TEXT']:
  add_column(c,'watering_logs',d)
 for d in ['created_by_user_id INTEGER','created_at TEXT','updated_at TEXT','code TEXT']:
  add_column(c,'teams',d)
 add_column(c,'events','code TEXT')
 try: c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_code_unique ON events(code) WHERE code IS NOT NULL AND code<>''")
 except Exception: pass
 add_column(c,'wilayas','name_ar TEXT')
 add_column(c,'communes','name_ar TEXT')
 if 'tree_observations' in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}: add_column(c,'tree_observations','photo_url TEXT')
 for d in ["description TEXT","color TEXT DEFAULT '#2e7b47'","active INTEGER DEFAULT 1"]:
  add_column(c,'roles',d)
 if 'missions' in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
  for d in ['actual_start_at TEXT','actual_end_at TEXT','completion_notes TEXT']:
   add_column(c,'missions',d)
  for d in ["priority TEXT DEFAULT 'Normale'",'completed_count INTEGER DEFAULT 0','report TEXT']:
   add_column(c,'missions',d)

def next_entity_code(c,table,column,prefix,width=4):
 rows=c.execute(f"SELECT {column} code FROM {table} WHERE {column} LIKE ? ORDER BY id DESC LIMIT 200",(prefix+'-%',)).fetchall()
 highest=0
 for r in rows:
  try: highest=max(highest,int(str(r['code']).split('-')[-1]))
  except Exception: pass
 return f"{prefix}-{highest+1:0{width}d}"

def sync_algeria_communes(c):
 try:
  if c.execute('SELECT COUNT(*) n FROM communes').fetchone()['n']>=1541:return
  cache=os.path.join(DATA_DIR,'algeria_cities.json');data=None
  if os.path.exists(cache):
   try:data=json.load(open(cache,encoding='utf-8'))
   except Exception:data=None
  if not data:
   try:
    with urllib.request.urlopen('https://raw.githubusercontent.com/othmanus/algeria-cities/master/json/algeria_cities.json',timeout=8) as r:data=json.loads(r.read().decode('utf-8'))
    with open(cache,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
   except Exception:return
  ids={r['code']:r['id'] for r in c.execute('SELECT id,code FROM wilayas').fetchall()}
  for x in data:
   wcode=str(x.get('wilaya_code') or '').zfill(2);wid=ids.get(wcode);w_ar=(x.get('wilaya_name') or '').strip();fr=(x.get('commune_name_ascii') or '').strip();ar=(x.get('commune_name') or '').strip()
   if wid and w_ar:c.execute('UPDATE wilayas SET name_ar=COALESCE(NULLIF(name_ar,""),?) WHERE id=?',(w_ar,wid))
   if wid and fr:
    c.execute('INSERT OR IGNORE INTO communes(wilaya_id,name,name_ar,active) VALUES(?,?,?,1)',(wid,fr,ar or None));c.execute('UPDATE communes SET name_ar=COALESCE(NULLIF(name_ar,""),?) WHERE wilaya_id=? AND name=?',(ar or None,wid,fr))
 except Exception:pass

def validate_zone_target(c,project_id,target_trees,exclude_zone_id=None):
 try: target=int(target_trees or 0)
 except Exception:return False,0
 p=c.execute('SELECT target_trees FROM projects WHERE id=?',(project_id,)).fetchone()
 if not p:return False,0
 q='SELECT COALESCE(SUM(target_trees),0) n FROM zones WHERE active=1 AND project_id=?';a=[project_id]
 if exclude_zone_id:q+=' AND id<>?';a.append(exclude_zone_id)
 used=c.execute(q,a).fetchone()['n'] or 0;mx=p['target_trees'] or 0;remaining=max(0,mx-used)
 if mx and target>remaining:return False,remaining
 return True,max(0,remaining-target)

def validate_project_target(c,project_id,target_trees):
 try: target=int(target_trees or 0)
 except Exception:return False,0,0
 allocated=c.execute('SELECT COALESCE(SUM(target_trees),0) n FROM zones WHERE project_id=? AND active=1',(project_id,)).fetchone()['n'] or 0
 planted=c.execute("SELECT COUNT(*) n FROM trees WHERE project_id=? AND active=1 AND COALESCE(approval_status,'approved')<>'rejected'",(project_id,)).fetchone()['n'] or 0
 # target=0 keeps the historic MyTree meaning: objective not defined / unlimited.
 if target>0 and target<max(allocated,planted): return False,allocated,planted
 return True,allocated,planted

def project_owner_allowed(c,project_id,permission='project.update'):
 p=c.execute('SELECT id,association_id,active FROM projects WHERE id=?',(project_id,)).fetchone()
 if not p or not p['active']: return False,p
 if is_super_admin(): return True,p
 ctx=active_context(c); aid=ctx.get('association_id')
 if ctx.get('type')!='association' or not aid or int(p['association_id'] or 0)!=int(aid): return False,p
 return has_association_permission(permission,aid,resource_type='project',resource_id=project_id),p

def resolve_project_geo(c,project_id):
 return c.execute('SELECT id,association_id,wilaya_id,commune_id,target_trees FROM projects WHERE id=? AND active=1',(project_id,)).fetchone()

def validate_tree_assignment(c,project_id=None,zone_id=None,exclude_tree_id=None):
 if not project_id and zone_id: return False,'Une zone doit appartenir à un projet.',None,None
 p=resolve_project_geo(c,project_id) if project_id else None
 if project_id and not p: return False,'Le projet sélectionné est invalide ou archivé.',None,None
 z=None
 if zone_id:
  z=c.execute('SELECT id,project_id,wilaya_id,commune_id,target_trees,active FROM zones WHERE id=?',(zone_id,)).fetchone()
  if not z or not z['active']: return False,'La zone sélectionnée est invalide ou archivée.',p,None
  if int(z['project_id'] or 0)!=int(project_id or 0): return False,'La zone ne correspond pas au projet sélectionné.',p,z
  # Alpha 4 Lot 7: zone geography is inherited from its project.
  if int(z['wilaya_id'] or 0)!=int(p['wilaya_id'] or 0) or int(z['commune_id'] or 0)!=int(p['commune_id'] or 0):
   return False,'La géographie de la zone est incohérente avec celle du projet.',p,z
 def count(where,args):
  q="SELECT COUNT(*) n FROM trees WHERE active=1 AND COALESCE(approval_status,'approved')<>'rejected' AND "+where
  a=list(args)
  if exclude_tree_id: q+=' AND id<>?';a.append(exclude_tree_id)
  return c.execute(q,a).fetchone()['n'] or 0
 if p and (p['target_trees'] or 0)>0 and count('project_id=?',[project_id])>=int(p['target_trees']):
  return False,'Objectif du projet atteint : aucune plantation supplémentaire ne peut être affectée à ce projet.',p,z
 if z and (z['target_trees'] or 0)>0 and count('zone_id=?',[zone_id])>=int(z['target_trees']):
  return False,'Objectif de la zone atteint : aucune plantation supplémentaire ne peut être affectée à cette zone.',p,z
 return True,None,p,z

def location_picker_markup(prefix):
 safe=''.join(ch for ch in str(prefix) if ch.isalnum() or ch=='_') or 'loc'
 return f'''<div class="full location-tools"><button type="button" class="btn alt" onclick="gps_{safe}()">📡 Ma position GPS</button> <button type="button" class="btn" onclick="map_{safe}()">🗺 Choisir sur la carte</button><span id="{safe}Msg" class="sub"></span></div><div class="full" id="{safe}Wrap" style="display:none"><div id="{safe}Map" class="map-picker"></div></div><script>(function(){{let m,k;window.gps_{safe}=function(){{let z=document.getElementById("{safe}Msg");if(!navigator.geolocation){{z.textContent="GPS indisponible";return}}navigator.geolocation.getCurrentPosition(p=>{{document.querySelector("[name=latitude]").value=p.coords.latitude.toFixed(7);document.querySelector("[name=longitude]").value=p.coords.longitude.toFixed(7);z.textContent="Position GPS enregistrée"}},()=>z.textContent="GPS indisponible",{{enableHighAccuracy:true,timeout:15000}})}};window.map_{safe}=function(){{let w=document.getElementById("{safe}Wrap");w.style.display="block";let a=parseFloat(document.querySelector("[name=latitude]").value)||35.70,b=parseFloat(document.querySelector("[name=longitude]").value)||-0.64;if(!m){{m=L.map("{safe}Map").setView([a,b],13);L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",{{maxZoom:20}}).addTo(m);k=L.marker([a,b],{{draggable:true}}).addTo(m);function set(q){{document.querySelector("[name=latitude]").value=q.lat.toFixed(7);document.querySelector("[name=longitude]").value=q.lng.toFixed(7)}}k.on("dragend",e=>set(e.target.getLatLng()));m.on("click",e=>{{k.setLatLng(e.latlng);set(e.latlng)}})}}setTimeout(()=>m.invalidateSize(),100)}}}})();</script>'''

def seed(c):
 roles=[('super_admin','Super administrateur',100),('admin','Administrateur',80),('coordinator','Coordinateur',60),('project_manager','Responsable de projet',50),('zone_manager','Responsable de zone',40),('team_leader','Chef d’équipe',30),('volunteer','Bénévole',10),('visitor','Visiteur',1)]
 for x in roles:c.execute('INSERT OR IGNORE INTO roles(name,label,level) VALUES(?,?,?)',x)
 perms=[('dashboard.view','Voir le tableau de bord'),('tree.view','Voir les arbres'),('tree.create','Créer une plantation'),('tree.approve','Valider une plantation'),('tree.edit','Modifier un arbre'),('tree.delete','Supprimer un arbre'),('watering.view','Voir les arrosages'),('watering.create','Enregistrer un arrosage'),('mission.view','Voir les missions'),('event.view','Voir les événements'),('event.register','S’inscrire aux événements'),('event.manage','Gérer les événements'),('intervention.view','Voir les interventions'),('intervention.create','Créer une intervention'),('intervention.manage','Gérer et planifier les interventions'),('team.view','Voir son équipe'),('map.view','Voir la carte'),('notification.view','Voir les notifications'),('volunteer.manage','Gérer les bénévoles'),('project.manage','Gérer les projets'),('zone.manage','Gérer les zones'),('geo.manage','Gérer la géographie'),('species.manage','Gérer les espèces'),('role.manage','Gérer les rôles et droits'),('user.manage','Gérer les utilisateurs'),('donation.view','Voir les dons'),('donation.manage','Gérer les dons'),('nursery.view','Voir la pépinière'),('nursery.manage','Gérer la pépinière'),('equipment.view','Voir le matériel'),('equipment.manage','Gérer le matériel'),('member.view','Voir les adhérents'),('member.manage','Gérer les adhérents'),('cash.view','Voir la caisse'),('cash.manage','Gérer la caisse'),('print.manage','Imprimer les documents'),('association.read','Voir association'),('association.update','Modifier association'),('member.roles','Gérer les rôles association'),('project.read','Voir projets'),('project.create','Créer projets'),('project.update','Modifier projets'),('project.delete','Supprimer projets'),('zone.read','Voir zones'),('zone.create','Créer zones'),('zone.update','Modifier zones'),('zone.delete','Supprimer zones'),('tree.request_delete','Demander suppression arbre'),('mission.create','Créer missions'),('mission.update','Modifier missions'),('mission.close','Clôturer missions'),('team.create','Créer équipes'),('team.update','Modifier équipes'),('collaboration.read','Voir collaborations'),('collaboration.invite','Inviter association'),('collaboration.accept','Traiter invitation'),('collaboration.manage','Gérer collaborations'),('report.read','Voir rapports'),('report.full','Rapports complets')]
 for x in perms:c.execute('INSERT OR IGNORE INTO permissions(code,label) VALUES(?,?)',x)
 admin_role=c.execute("SELECT id FROM roles WHERE name='super_admin'").fetchone()['id']
 for p in c.execute('SELECT id FROM permissions'): c.execute('INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)',(admin_role,p['id']))
 volunteer_role_seed=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']
 for code in ['dashboard.view','tree.view','tree.create','watering.view','watering.create','map.view','notification.view','event.view','event.register']:
  pid=c.execute('SELECT id FROM permissions WHERE code=?',(code,)).fetchone()['id']; c.execute('INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)',(volunteer_role_seed,pid))
 # Correctif Alpha 2 : ces modules sont accordés uniquement par permission individuelle.
 c.execute("DELETE FROM role_permissions WHERE role_id=? AND permission_id IN (SELECT id FROM permissions WHERE code IN ('mission.view','intervention.view','intervention.create','team.view'))",(volunteer_role_seed,))
 wilayas=[('01','Adrar'),('02','Chlef'),('03','Laghouat'),('04','Oum El Bouaghi'),('05','Batna'),('06','Béjaïa'),('07','Biskra'),('08','Béchar'),('09','Blida'),('10','Bouira'),('11','Tamanrasset'),('12','Tébessa'),('13','Tlemcen'),('14','Tiaret'),('15','Tizi Ouzou'),('16','Alger'),('17','Djelfa'),('18','Jijel'),('19','Sétif'),('20','Saïda'),('21','Skikda'),('22','Sidi Bel Abbès'),('23','Annaba'),('24','Guelma'),('25','Constantine'),('26','Médéa'),('27','Mostaganem'),('28','M’Sila'),('29','Mascara'),('30','Ouargla'),('31','Oran'),('32','El Bayadh'),('33','Illizi'),('34','Bordj Bou Arréridj'),('35','Boumerdès'),('36','El Tarf'),('37','Tindouf'),('38','Tissemsilt'),('39','El Oued'),('40','Khenchela'),('41','Souk Ahras'),('42','Tipaza'),('43','Mila'),('44','Aïn Defla'),('45','Naâma'),('46','Aïn Témouchent'),('47','Ghardaïa'),('48','Relizane'),('49','Timimoun'),('50','Bordj Badji Mokhtar'),('51','Ouled Djellal'),('52','Béni Abbès'),('53','In Salah'),('54','In Guezzam'),('55','Touggourt'),('56','Djanet'),('57','El M’Ghair'),('58','El Meniaâ')]
 for x in wilayas:c.execute('INSERT OR IGNORE INTO wilayas(code,name) VALUES(?,?)',x)
 oran=c.execute("SELECT id FROM wilayas WHERE name='Oran'").fetchone()['id']
 oran_communes=['Oran','Gdyel','Bir El Djir','Hassi Bounif','Es Sénia','Arzew','Bethioua','Marsat El Hadjadj','Aïn El Turk','El Ançor','Oued Tlelat','Tafraoui','Sidi Chami','Boufatis','Mers El Kébir','Bousfer','El Kerma','El Braya','Hassi Ben Okba','Ben Freha','Hassi Mefsoukh','Sidi Ben Yebka','Misserghin','Boutlelis','Aïn El Kerma','Aïn El Bia']
 for n in oran_communes: c.execute('INSERT OR IGNORE INTO communes(wilaya_id,name) VALUES(?,?)',(oran,n))
 species=[('Caroubier','الخروب','Ceratonia siliqua','Forestier','Faible',14,'#337a43'),('Olivier','الزيتون','Olea europaea','Fruitier','Faible',14,'#77933c'),('Mûrier','التوت','Morus','Fruitier','Moyen',7,'#4c7b45'),('Pistachier','الفستق','Pistacia','Forestier','Faible',14,'#5f7b37'),('Eucalyptus','الكاليتوس','Eucalyptus','Forestier','Moyen',10,'#497c69'),('Figuier','التين','Ficus carica','Fruitier','Moyen',7,'#607c39')]
 for x in species:c.execute('INSERT OR IGNORE INTO species(name_fr,name_ar,scientific_name,category,water_need,watering_frequency_days,color) VALUES(?,?,?,?,?,?,?)',x)
 for x in SPECIES_CATALOG:
  c.execute('''INSERT OR IGNORE INTO species(name_fr,name_ar,scientific_name,category,water_need,watering_frequency_days,color,family,origin,algeria_presence,regions,soil_type,sun_exposure,drought_tolerance,cold_tolerance,salt_tolerance,wind_tolerance,planting_distance,adult_height,growth_rate,planting_period,uses,description,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',x)
 english_names={'Caroubier':'Carob tree','Olivier':'Olive tree','Mûrier':'Mulberry','Mûrier blanc':'White mulberry','Mûrier noir':'Black mulberry','Pistachier':'Pistachio','Pistachier lentisque':'Mastic tree','Pistachier de l’Atlas':'Atlas pistachio','Eucalyptus':'Eucalyptus','Figuier':'Fig tree','Pin d’Alep':'Aleppo pine','Pin maritime':'Maritime pine','Pin parasol':'Stone pine','Chêne-liège':'Cork oak','Chêne vert':'Holm oak','Chêne zéen':'Algerian oak','Cèdre de l’Atlas':'Atlas cedar','Cyprès':'Cypress','Palmier dattier':'Date palm','Grenadier':'Pomegranate','Amandier':'Almond tree','Abricotier':'Apricot tree','Pêcher':'Peach tree','Poirier':'Pear tree','Pommier':'Apple tree','Oranger':'Orange tree','Citronnier':'Lemon tree','Mandarinier':'Mandarin tree','Néflier':'Loquat','Jujubier':'Jujube tree','Sidr':'Sidr / Christ’s thorn jujube','Acacia':'Acacia','Tamaris':'Tamarisk','Faux poivrier':'Peruvian pepper tree','Jacaranda':'Jacaranda','Platane':'Plane tree','Micocoulier':'Hackberry','Frêne':'Ash tree','Peuplier':'Poplar','Saule':'Willow','Tecoma stans':'Yellow trumpetbush'}
 for fr,en in english_names.items():c.execute('UPDATE species SET name_en=? WHERE name_fr=?',(en,fr))
 c.execute("UPDATE species SET name_en=COALESCE(NULLIF(name_en,''),NULLIF(scientific_name,''),name_fr)")
 if c.execute('SELECT COUNT(*) n FROM equipment').fetchone()['n']==0:
  now=datetime.now().isoformat(timespec='minutes')
  for i,(name,category) in enumerate(EQUIPMENT_CATALOG,1):
   c.execute('INSERT OR IGNORE INTO equipment(name,category,inventory_code,quantity_total,quantity_available,condition_status,active,created_at) VALUES(?,?,?,?,?,?,1,?)',(name,category,f'CAT-{i:03d}',0,0,'Catalogue',now))
 if c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']==0:
  c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('Super','Admin','Super Admin','Homme','0500000000','admin@mytree.local','admin',generate_password_hash('admin123'),admin_role,'super_admin',1,oran,c.execute("SELECT id FROM communes WHERE name='Oran'").fetchone()['id'],datetime.now().isoformat(timespec='minutes')))
 else:
  c.execute("UPDATE users SET role_id=COALESCE(role_id,?), role=COALESCE(role,'super_admin'), created_at=COALESCE(created_at,?) WHERE username='admin'",(admin_role,datetime.now().isoformat(timespec='minutes')))
 volunteer_role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']
 if not c.execute("SELECT 1 FROM users WHERE username='benevole'").fetchone():
  c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('Bénévole','Démo','Bénévole Démo','Homme','0550000000','benevole@mytree.local','benevole',generate_password_hash('benevole123'),volunteer_role,'volunteer',1,oran,c.execute("SELECT id FROM communes WHERE name='Oran'").fetchone()['id'],datetime.now().isoformat(timespec='minutes')))
 if c.execute('SELECT COUNT(*) n FROM projects').fetchone()['n']==0:
  commune=c.execute("SELECT id FROM communes WHERE name='Oran'").fetchone()['id']
  c.execute("INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,active) VALUES('PROJ-001','Reboisement Forêt de Canastel','Étude et préparation',500,850000,?,?,?,1)",(oran,commune,'Forêt de Canastel'))
 p=c.execute('SELECT id,wilaya_id,commune_id FROM projects ORDER BY id LIMIT 1').fetchone()
 if p and c.execute('SELECT COUNT(*) n FROM zones').fetchone()['n']==0:
  c.execute("INSERT INTO zones(project_id,wilaya_id,commune_id,code,name,area,target_trees,color) VALUES(?,?,?,?,?,?,?,?)",(p['id'],p['wilaya_id'],p['commune_id'],'ZA','Zone A',2.4,180,'#3f8b4f'))
  c.execute("INSERT INTO zones(project_id,wilaya_id,commune_id,code,name,area,target_trees,color) VALUES(?,?,?,?,?,?,?,?)",(p['id'],p['wilaya_id'],p['commune_id'],'ZC','Zone Cafétéria',1.8,140,'#d39b2a'))
 if c.execute('SELECT COUNT(*) n FROM trees').fetchone()['n']==0:
  z=c.execute('SELECT id FROM zones ORDER BY id LIMIT 1').fetchone()['id']; sp=c.execute("SELECT id FROM species WHERE name_fr='Caroubier'").fetchone()['id']; u=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()['id']
  c.execute("INSERT INTO trees(tree_code,qr_code,species_id,species,project_id,zone_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,health_status,watering_status,approval_status,approved_by_user_id,approved_at,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",('TREE-0001','QR-TREE-0001',sp,'Caroubier',p['id'],z,'2026-11-15',u,'Super Admin',35.767,-0.606,'Bon','À jour','approved',u,datetime.now().isoformat(timespec='minutes'),datetime.now().isoformat(timespec='minutes')))

def init_db():
 backup_before_lot12_migration()
 c=db()
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA synchronous=NORMAL')
 c.executescript(SCHEMA)
 # FIXED6 : migrations additives, compatibles avec les bases Railway existantes.
 if 'requested_map_symbol' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN requested_map_symbol TEXT")
 if 'requested_login_id' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN requested_login_id TEXT")
 if 'requested_password_hash' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN requested_password_hash TEXT")
 if 'organization_type' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN organization_type TEXT DEFAULT 'volunteer_group'")
 if 'approval_number' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN approval_number TEXT")
 if 'approval_document' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN approval_document TEXT")
 if 'approval_document_name' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN approval_document_name TEXT")
 if 'approval_document_mime' not in columns(c,'association_creation_requests'):
  c.execute("ALTER TABLE association_creation_requests ADD COLUMN approval_document_mime TEXT")
 for col,typ in [('reviewed_by_role','TEXT'),('reviewed_by_association_id','INTEGER')]:
  if col not in columns(c,'trees'): c.execute(f"ALTER TABLE trees ADD COLUMN {col} {typ}")
 migrate_legacy(c)
 seed(c)
 sync_algeria_communes(c)
 # v2.0 Alpha 1: migration non destructive vers le contexte multi-associations.
 if not c.execute('SELECT 1 FROM associations LIMIT 1').fetchone():
  oran_row=c.execute("SELECT id FROM wilayas WHERE name='Oran' LIMIT 1").fetchone(); commune_row=c.execute("SELECT id FROM communes WHERE name='Oran' LIMIT 1").fetchone()
  c.execute("INSERT INTO associations(code,name,short_name,description,wilaya_id,commune_id,status,created_by_user_id,created_at) VALUES('ASSOC-0001','Association principale','Principale','Association créée automatiquement lors de la migration v2.0 afin de préserver les données historiques.',?,?, 'active',(SELECT id FROM users WHERE role='super_admin' ORDER BY id LIMIT 1),?)",((oran_row['id'] if oran_row else None),(commune_row['id'] if commune_row else None),datetime.now().isoformat(timespec='minutes')))
 default_assoc=c.execute('SELECT id FROM associations ORDER BY id LIMIT 1').fetchone()['id']
 for table in ['projects','zones','teams','missions','events','trees','members','donations','cash_movements','agents','agent_payments','purchase_records','purchase_groups','operational_tasks','nursery_stock','nursery_movements','equipment','memberships','watering_batches','assignments']:
  if table in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")} and 'association_id' in columns(c,table):
   c.execute(f'UPDATE {table} SET association_id=? WHERE association_id IS NULL',(default_assoc,))
 # Super admin rattaché à l’association historique pour les tests, sans limiter ses droits globaux.
 su=c.execute("SELECT id FROM users WHERE role='super_admin' ORDER BY id LIMIT 1").fetchone()
 if su:
  c.execute("INSERT OR IGNORE INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at,reviewed_by_user_id,reviewed_at) VALUES(?,?, 'volunteer','association_admin','approved',?,?,?)",(default_assoc,su['id'],datetime.now().isoformat(timespec='minutes'),su['id'],datetime.now().isoformat(timespec='minutes')))
 # Alpha 2: préserver les utilisateurs historiques dans l'association principale.
 for u in c.execute("SELECT id,COALESCE(role,'volunteer') role FROM users WHERE active=1").fetchall():
  role_code='association_admin' if u['role'] in ('admin','super_admin') else 'volunteer'
  c.execute("INSERT OR IGNORE INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at,reviewed_by_user_id,reviewed_at) VALUES(?,?, 'volunteer',?,'approved',?,?,?)",(default_assoc,u['id'],role_code,datetime.now().isoformat(timespec='minutes'),(su['id'] if su else u['id']),datetime.now().isoformat(timespec='minutes')))
 c.execute("INSERT OR IGNORE INTO user_contexts(user_id,context_type,association_id,updated_at) SELECT id,'personal',NULL,? FROM users",(datetime.now().isoformat(timespec='minutes'),))
 c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('volunteer_registration_mode','auto')")
 # RC1: indexation des recherches et listes les plus utilisées.
 c.executescript("""
 CREATE INDEX IF NOT EXISTS idx_trees_project_zone ON trees(project_id,zone_id);
 CREATE INDEX IF NOT EXISTS idx_trees_approval_active ON trees(approval_status,active);
 CREATE INDEX IF NOT EXISTS idx_trees_gps ON trees(latitude,longitude);
 CREATE INDEX IF NOT EXISTS idx_trees_species ON trees(species_id,species);
 CREATE INDEX IF NOT EXISTS idx_trees_species_status ON trees(species_id,active,approval_status);
 CREATE INDEX IF NOT EXISTS idx_trees_association_status ON trees(association_id,active,approval_status);
 CREATE INDEX IF NOT EXISTS idx_trees_planter_status ON trees(planted_by_user_id,active,approval_status);
 CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role,active);
 CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id,is_read,created_at);
 CREATE INDEX IF NOT EXISTS idx_notifications_action_pending ON notifications(user_id,action_type,decision,is_read);
 CREATE INDEX IF NOT EXISTS idx_submission_tokens_created ON submission_tokens(created_at);
 CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
 CREATE INDEX IF NOT EXISTS idx_events_start_status ON events(start_at,status,active);
 CREATE INDEX IF NOT EXISTS idx_tasks_start_status ON operational_tasks(start_at,status);
 CREATE INDEX IF NOT EXISTS idx_assoc_geo_status ON associations(wilaya_id,commune_id,status);
 CREATE INDEX IF NOT EXISTS idx_assoc_members_user ON association_memberships(user_id,status,association_id);
 """)
 c.commit()
 c.close()

SUPPORTED_LANGS=('fr','ar','en')
I18N={
 'Accueil':{'ar':'الرئيسية','en':'Home'},'Mon accueil':{'ar':'صفحتي الرئيسية','en':'My home'},'Accueil public':{'ar':'الواجهة العامة','en':'Public home'},'Administration':{'ar':'الإدارة','en':'Administration'},
 'Terrain':{'ar':'الميدان','en':'Field'},'Organisation':{'ar':'التنظيم','en':'Organization'},'Personnes':{'ar':'الأشخاص','en':'People'},'Gestion':{'ar':'التسيير','en':'Management'},'Public':{'ar':'عام','en':'Public'},
 'Arbres':{'ar':'الأشجار','en':'Trees'},'Mes arbres':{'ar':'أشجاري','en':'My trees'},'Plantations':{'ar':'الغرس','en':'Plantings'},'Planter':{'ar':'غرس','en':'Plant'},'Planter un arbre':{'ar':'غرس شجرة','en':'Plant a tree'},
 'Arrosages':{'ar':'السقي','en':'Watering'},'Arroser':{'ar':'سقي','en':'Water'},'Carte':{'ar':'الخريطة','en':'Map'},'Carte publique':{'ar':'الخريطة العامة','en':'Public map'},'GPS rapide':{'ar':'تحديد GPS السريع','en':'Quick GPS'},'QR Code':{'ar':'رمز QR','en':'QR Code'},'Scanner QR':{'ar':'مسح QR','en':'Scan QR'},
 'Projets':{'ar':'المشاريع','en':'Projects'},'Zones':{'ar':'المناطق','en':'Zones'},'Équipes':{'ar':'الفرق','en':'Teams'},'Missions':{'ar':'المهام','en':'Missions'},'Planifications':{'ar':'التخطيط','en':'Planning'},'Événements':{'ar':'الفعاليات','en':'Events'},
 'Bénévoles':{'ar':'المتطوعون','en':'Volunteers'},'Adhérents':{'ar':'الأعضاء','en':'Members'},'Utilisateurs':{'ar':'المستخدمون','en':'Users'},'Rôles et droits':{'ar':'الأدوار والصلاحيات','en':'Roles & permissions'},
 'Caisse':{'ar':'الصندوق','en':'Cash management'},'Dons':{'ar':'التبرعات','en':'Donations'},'Cotisations':{'ar':'الاشتراكات','en':'Membership fees'},'Stock':{'ar':'المخزون','en':'Inventory'},'Matériel':{'ar':'المعدات','en':'Equipment'},'Pépinière':{'ar':'المشتلة','en':'Nursery'},
 'Centre d’actions':{'ar':'مركز الإجراءات','en':'Action center'},'Notifications':{'ar':'الإشعارات','en':'Notifications'},'Alertes':{'ar':'التنبيهات','en':'Alerts'},'Rapports':{'ar':'التقارير','en':'Reports'},'Journal d’activité':{'ar':'سجل النشاط','en':'Activity log'},'Sauvegarde':{'ar':'النسخ الاحتياطي','en':'Backup'},'Espèces':{'ar':'الأنواع','en':'Species'},'Géographie':{'ar':'الجغرافيا','en':'Geography'},'Recherche':{'ar':'البحث','en':'Search'},
 'Connexion':{'ar':'تسجيل الدخول','en':'Sign in'},'Déconnexion':{'ar':'تسجيل الخروج','en':'Sign out'},'Se connecter':{'ar':'تسجيل الدخول','en':'Sign in'},'Créer un compte':{'ar':'إنشاء حساب','en':'Create account'},'Créer mon compte':{'ar':'إنشاء حسابي','en':'Create my account'},'Se souvenir de moi pendant 30 jours':{'ar':'تذكرني لمدة 30 يوماً','en':'Remember me for 30 days'},
 'Téléphone ou utilisateur':{'ar':'الهاتف أو اسم المستخدم','en':'Phone or username'},'Mot de passe':{'ar':'كلمة المرور','en':'Password'},'Téléphone':{'ar':'الهاتف','en':'Phone'},'E-mail':{'ar':'البريد الإلكتروني','en':'Email'},'Prénom':{'ar':'الاسم','en':'First name'},'Nom':{'ar':'اللقب','en':'Last name'},'Sexe':{'ar':'الجنس','en':'Sex'},'Adresse':{'ar':'العنوان','en':'Address'},
 'Wilaya':{'ar':'الولاية','en':'Province'},'Commune':{'ar':'البلدية','en':'Municipality'},'Projet':{'ar':'المشروع','en':'Project'},'Zone':{'ar':'المنطقة','en':'Zone'},'Espèce':{'ar':'النوع','en':'Species'},'Quantité':{'ar':'الكمية','en':'Quantity'},'Montant':{'ar':'المبلغ','en':'Amount'},'Montant (DA)':{'ar':'المبلغ (دج)','en':'Amount (DZD)'},'Prix total (DA)':{'ar':'السعر الإجمالي (دج)','en':'Total price (DZD)'},
 'Enregistrer':{'ar':'حفظ','en':'Save'},'Annuler':{'ar':'إلغاء','en':'Cancel'},'Annuler / Retour':{'ar':'إلغاء / رجوع','en':'Cancel / Back'},'Retour':{'ar':'رجوع','en':'Back'},'Ajouter':{'ar':'إضافة','en':'Add'},'Modifier':{'ar':'تعديل','en':'Edit'},'Supprimer':{'ar':'حذف','en':'Delete'},'Archiver':{'ar':'أرشفة','en':'Archive'},'Ouvrir':{'ar':'فتح','en':'Open'},'Fiche':{'ar':'بطاقة','en':'Details'},'Imprimer':{'ar':'طباعة','en':'Print'},'Accepter':{'ar':'قبول','en':'Accept'},'Refuser':{'ar':'رفض','en':'Reject'},'Choisir':{'ar':'اختيار','en':'Choose'},
 'Faire un don':{'ar':'تقديم تبرع','en':'Make a donation'},'Devenir adhérent':{'ar':'الانضمام كعضو','en':'Become a member'},'Je veux aider':{'ar':'أريد المساعدة','en':'I want to help'},'Participer à l’arrosage':{'ar':'المشاركة في السقي','en':'Help with watering'},
 'Tous':{'ar':'الكل','en':'All'},'Argent':{'ar':'مال','en':'Money'},'Dons disponibles':{'ar':'التبرعات المتاحة','en':'Available donations'},'Cotisations disponibles':{'ar':'الاشتراكات المتاحة','en':'Available membership funds'},'Solde global':{'ar':'الرصيد الإجمالي','en':'Total balance'},
 'En attente':{'ar':'قيد الانتظار','en':'Pending'},'Confirmé':{'ar':'مؤكد','en':'Confirmed'},'Refusé':{'ar':'مرفوض','en':'Rejected'},'Validé':{'ar':'مصادق عليه','en':'Validated'},'Actif':{'ar':'نشط','en':'Active'},'Inactif':{'ar':'غير نشط','en':'Inactive'},'Planifié':{'ar':'مبرمج','en':'Planned'},'Terminé':{'ar':'منتهي','en':'Completed'},'Annulé':{'ar':'ملغى','en':'Cancelled'},
 'Rechercher':{'ar':'بحث','en':'Search'},'Recherche intelligente':{'ar':'بحث ذكي','en':'Smart search'},'Recherche intelligente dans la liste…':{'ar':'بحث ذكي في القائمة…','en':'Smart search in list…'},'Français, arabe, anglais ou nom scientifique':{'ar':'الفرنسية، العربية، الإنجليزية أو الاسم العلمي','en':'French, Arabic, English or scientific name'},
 'Encyclopédie':{'ar':'الموسوعة','en':'Encyclopedia'},'Encyclopédie des arbres':{'ar':'موسوعة الأشجار','en':'Tree encyclopedia'},'Nos projets':{'ar':'مشاريعنا','en':'Our projects'},'Arbres suivis':{'ar':'الأشجار المتابعة','en':'Tracked trees'},'Projets actifs':{'ar':'المشاريع النشطة','en':'Active projects'},'Espèces référencées':{'ar':'الأنواع المسجلة','en':'Referenced species'},
 'Date':{'ar':'التاريخ','en':'Date'},'Statut':{'ar':'الحالة','en':'Status'},'Notes':{'ar':'ملاحظات','en':'Notes'},'Description':{'ar':'الوصف','en':'Description'},'Emplacement':{'ar':'الموقع','en':'Location'},'Disponible':{'ar':'المتاح','en':'Available'},'Réservé':{'ar':'محجوز','en':'Reserved'},'Photo':{'ar':'صورة','en':'Photo'},'Prendre une photo':{'ar':'التقاط صورة','en':'Take a photo'},'Choisir depuis la galerie':{'ar':'اختيار من المعرض','en':'Choose from gallery'},
 'Homme':{'ar':'رجل','en':'Male'},'Femme':{'ar':'امرأة','en':'Female'},'Oui':{'ar':'نعم','en':'Yes'},'Non':{'ar':'لا','en':'No'},
 'Reste à répartir':{'ar':'المتبقي للتوزيع','en':'Remaining to allocate'},'Nouvel achat':{'ar':'شراء جديد','en':'New purchase'},'Fournisseur':{'ar':'المورد','en':'Supplier'},'Prix unitaire DA':{'ar':'سعر الوحدة دج','en':'Unit price DZD'},'Source de paiement':{'ar':'مصدر الدفع','en':'Payment source'},'Depuis cotisations':{'ar':'من الاشتراكات','en':'From memberships'},'Depuis dons':{'ar':'من التبرعات','en':'From donations'},'Justificatif / facture':{'ar':'الإثبات / الفاتورة','en':'Receipt / invoice'},'Chef d’équipe':{'ar':'رئيس الفريق','en':'Team leader'},'Participants':{'ar':'المشاركون','en':'Participants'},'Objectif arbres':{'ar':'هدف الأشجار','en':'Tree target'},'Superficie (ha)':{'ar':'المساحة (هكتار)','en':'Area (ha)'},'Ma position GPS':{'ar':'موقعي GPS','en':'My GPS position'},'Choisir sur la carte':{'ar':'اختيار على الخريطة','en':'Choose on map'},
 'Arbres personnels / apportés directement (aucun mouvement de stock)':{'ar':'أشجار شخصية / جلبها المتطوع مباشرة (بدون حركة مخزون)','en':'Personal / directly supplied trees (no inventory movement)'},'Stock de l’association (déduire automatiquement)':{'ar':'مخزون الجمعية (خصم تلقائي)','en':'Association inventory (deduct automatically)'},
 'Confirmer le mot de passe':{'ar':'تأكيد كلمة المرور','en':'Confirm password'},'Les mots de passe ne correspondent pas.':{'ar':'كلمتا المرور غير متطابقتين.','en':'Passwords do not match.'},'Mot de passe oublié ?':{'ar':'نسيت كلمة المرور؟','en':'Forgot password?'},'Téléphone ou utilisateur':{'ar':'الهاتف أو اسم المستخدم','en':'Phone or username'},'Se souvenir de moi pendant 30 jours':{'ar':'تذكرني لمدة 30 يومًا','en':'Remember me for 30 days'},
 'Créer mon compte':{'ar':'إنشاء حسابي','en':'Create my account'},'Créer un compte bénévole':{'ar':'إنشاء حساب متطوع','en':'Create a volunteer account'},'E-mail':{'ar':'البريد الإلكتروني','en':'Email'},'E-mail facultatif':{'ar':'البريد الإلكتروني اختياري','en':'Optional email'},'Téléphone':{'ar':'الهاتف','en':'Phone'},
 'Nouvelle équipe':{'ar':'فريق جديد','en':'New team'},'Nouvelle mission':{'ar':'مهمة جديدة','en':'New mission'},'Nouvelle zone':{'ar':'منطقة جديدة','en':'New zone'},'Nouveau projet':{'ar':'مشروع جديد','en':'New project'},'Nouvel événement':{'ar':'فعالية جديدة','en':'New event'},'Nouvelle planification':{'ar':'تخطيط جديد','en':'New planning'},
 'Équipe':{'ar':'الفريق','en':'Team'},'Équipes':{'ar':'الفرق','en':'Teams'},'Mission':{'ar':'المهمة','en':'Mission'},'Missions':{'ar':'المهام','en':'Missions'},'Planification':{'ar':'التخطيط','en':'Planning'},'Planifications':{'ar':'التخطيطات','en':'Plannings'},'Événement':{'ar':'الفعالية','en':'Event'},'Événements':{'ar':'الفعاليات','en':'Events'},
 'Notifications':{'ar':'الإشعارات','en':'Notifications'},'Centre de notifications':{'ar':'مركز الإشعارات','en':'Notification center'},'Non lues seulement':{'ar':'غير المقروءة فقط','en':'Unread only'},'Nouvelle':{'ar':'جديدة','en':'New'},'Lue':{'ar':'مقروءة','en':'Read'},'Marquer lue':{'ar':'تحديد كمقروء','en':'Mark read'},'Tout sélectionner':{'ar':'تحديد الكل','en':'Select all'},
 'Rechercher par nom ou téléphone…':{'ar':'البحث بالاسم أو الهاتف…','en':'Search by name or phone…'},'Responsable':{'ar':'المسؤول','en':'Responsible'},'Code':{'ar':'الرمز','en':'Code'},'Nom affiché':{'ar':'الاسم المعروض','en':'Display name'},'Date début':{'ar':'تاريخ البداية','en':'Start date'},'Date fin':{'ar':'تاريخ النهاية','en':'End date'},
 'Mot de passe réinitialisé.':{'ar':'تمت إعادة تعيين كلمة المرور.','en':'Password reset.'},'Code SMS':{'ar':'رمز الرسالة القصيرة','en':'SMS code'},'Nouveau mot de passe':{'ar':'كلمة مرور جديدة','en':'New password'}

}

I18N_LOT11={'Erreur': {'ar': 'خطأ', 'en': 'Error'}, 'Succès': {'ar': 'نجاح', 'en': 'Success'}, 'Avertissement': {'ar': 'تنبيه', 'en': 'Warning'}, 'Information': {'ar': 'معلومة', 'en': 'Information'}, 'Opération effectuée avec succès.': {'ar': 'تمت العملية بنجاح.', 'en': 'Operation completed successfully.'}, 'Enregistrement effectué.': {'ar': 'تم الحفظ.', 'en': 'Saved successfully.'}, 'Modification enregistrée.': {'ar': 'تم حفظ التعديلات.', 'en': 'Changes saved.'}, 'Suppression effectuée.': {'ar': 'تم الحذف.', 'en': 'Deleted successfully.'}, 'Élément archivé.': {'ar': 'تمت الأرشفة.', 'en': 'Item archived.'}, 'Accès refusé.': {'ar': 'تم رفض الوصول.', 'en': 'Access denied.'}, 'Action non autorisée.': {'ar': 'الإجراء غير مسموح.', 'en': 'Action not allowed.'}, 'Association active': {'ar': 'الجمعية النشطة', 'en': 'Active association'}, 'Espace personnel': {'ar': 'المساحة الشخصية', 'en': 'Personal space'}, 'Espace association': {'ar': 'مساحة الجمعية', 'en': 'Association space'}, 'Personnel': {'ar': 'شخصي', 'en': 'Personal'}, 'Association': {'ar': 'الجمعية', 'en': 'Association'}, 'Associations': {'ar': 'الجمعيات', 'en': 'Associations'}, 'Changer d’association': {'ar': 'تغيير الجمعية', 'en': 'Switch association'}, 'Collaboration': {'ar': 'التعاون', 'en': 'Collaboration'}, 'Collaborations': {'ar': 'التعاونات', 'en': 'Collaborations'}, 'Centre de collaboration': {'ar': 'مركز التعاون', 'en': 'Collaboration center'}, 'Association propriétaire': {'ar': 'الجمعية المالكة', 'en': 'Owner association'}, 'Association partenaire': {'ar': 'الجمعية الشريكة', 'en': 'Partner association'}, 'Partenaire': {'ar': 'شريك', 'en': 'Partner'}, 'Propriétaire': {'ar': 'المالك', 'en': 'Owner'}, 'Invitation': {'ar': 'دعوة', 'en': 'Invitation'}, 'Invitations': {'ar': 'الدعوات', 'en': 'Invitations'}, 'Invitation envoyée.': {'ar': 'تم إرسال الدعوة.', 'en': 'Invitation sent.'}, 'Invitation acceptée.': {'ar': 'تم قبول الدعوة.', 'en': 'Invitation accepted.'}, 'Invitation refusée.': {'ar': 'تم رفض الدعوة.', 'en': 'Invitation rejected.'}, 'Quitter la collaboration': {'ar': 'مغادرة التعاون', 'en': 'Leave collaboration'}, 'Terminer la collaboration': {'ar': 'إنهاء التعاون', 'en': 'End collaboration'}, 'Lecture': {'ar': 'قراءة', 'en': 'View'}, 'Intervenir': {'ar': 'التدخل', 'en': 'Intervene'}, 'Ajouter des arbres': {'ar': 'إضافة أشجار', 'en': 'Add trees'}, 'Gérer les missions': {'ar': 'إدارة المهام', 'en': 'Manage missions'}, 'Non lue': {'ar': 'غير مقروءة', 'en': 'Unread'}, 'Non lu': {'ar': 'غير مقروء', 'en': 'Unread'}, 'Traitée': {'ar': 'تمت المعالجة', 'en': 'Processed'}, 'Traité': {'ar': 'تمت المعالجة', 'en': 'Processed'}, 'Marquer comme lue': {'ar': 'تحديد كمقروء', 'en': 'Mark as read'}, 'Tout marquer comme lu': {'ar': 'تحديد الكل كمقروء', 'en': 'Mark all as read'}, 'Date de lecture': {'ar': 'تاريخ القراءة', 'en': 'Read date'}, 'Date de traitement': {'ar': 'تاريخ المعالجة', 'en': 'Processed date'}, 'Action requise': {'ar': 'إجراء مطلوب', 'en': 'Action required'}, 'Priorité': {'ar': 'الأولوية', 'en': 'Priority'}, 'Basse': {'ar': 'منخفضة', 'en': 'Low'}, 'Normale': {'ar': 'عادية', 'en': 'Normal'}, 'Haute': {'ar': 'مرتفعة', 'en': 'High'}, 'Urgente': {'ar': 'عاجلة', 'en': 'Urgent'}, 'À faire': {'ar': 'للإنجاز', 'en': 'To do'}, 'En cours': {'ar': 'قيد التنفيذ', 'en': 'In progress'}, 'Terminée': {'ar': 'منتهية', 'en': 'Completed'}, 'Clôturée': {'ar': 'مغلقة', 'en': 'Closed'}, 'Clôturer': {'ar': 'إغلاق', 'en': 'Close'}, 'Ouvert': {'ar': 'مفتوح', 'en': 'Open'}, 'Fermé': {'ar': 'مغلق', 'en': 'Closed'}, 'Approuvé': {'ar': 'موافق عليه', 'en': 'Approved'}, 'Rejeté': {'ar': 'مرفوض', 'en': 'Rejected'}, 'Brouillon': {'ar': 'مسودة', 'en': 'Draft'}, 'Archivé': {'ar': 'مؤرشف', 'en': 'Archived'}, 'Archivée': {'ar': 'مؤرشفة', 'en': 'Archived'}, 'Bon': {'ar': 'جيد', 'en': 'Good'}, 'Moyen': {'ar': 'متوسط', 'en': 'Fair'}, 'Mauvais': {'ar': 'سيئ', 'en': 'Poor'}, 'Critique': {'ar': 'حرج', 'en': 'Critical'}, 'À arroser': {'ar': 'يحتاج إلى السقي', 'en': 'Needs watering'}, 'Arrosé': {'ar': 'تم سقيه', 'en': 'Watered'}, 'Arrosée': {'ar': 'تم سقيها', 'en': 'Watered'}, 'Observation': {'ar': 'ملاحظة', 'en': 'Observation'}, 'Observations': {'ar': 'ملاحظات', 'en': 'Observations'}, 'Intervention': {'ar': 'تدخل', 'en': 'Intervention'}, 'Interventions': {'ar': 'التدخلات', 'en': 'Interventions'}, 'Historique': {'ar': 'السجل', 'en': 'History'}, 'Voir l’historique': {'ar': 'عرض السجل', 'en': 'View history'}, 'Créer': {'ar': 'إنشاء', 'en': 'Create'}, 'Valider': {'ar': 'تأكيد', 'en': 'Validate'}, 'Confirmer': {'ar': 'تأكيد', 'en': 'Confirm'}, 'Fermer': {'ar': 'إغلاق', 'en': 'Close'}, 'Réinitialiser': {'ar': 'إعادة تعيين', 'en': 'Reset'}, 'Filtrer': {'ar': 'تصفية', 'en': 'Filter'}, 'Filtres': {'ar': 'الفلاتر', 'en': 'Filters'}, 'Effacer les filtres': {'ar': 'مسح الفلاتر', 'en': 'Clear filters'}, 'Du': {'ar': 'من', 'en': 'From'}, 'Au': {'ar': 'إلى', 'en': 'To'}, 'Période': {'ar': 'الفترة', 'en': 'Period'}, 'Type d’action': {'ar': 'نوع الإجراء', 'en': 'Action type'}, 'État': {'ar': 'الحالة', 'en': 'Condition'}, 'Santé': {'ar': 'الصحة', 'en': 'Health'}, 'Bénévole': {'ar': 'متطوع', 'en': 'Volunteer'}, 'Tous les projets': {'ar': 'كل المشاريع', 'en': 'All projects'}, 'Toutes les zones': {'ar': 'كل المناطق', 'en': 'All zones'}, 'Toutes les espèces': {'ar': 'كل الأنواع', 'en': 'All species'}, 'Tous les bénévoles': {'ar': 'كل المتطوعين', 'en': 'All volunteers'}, 'Tous les statuts': {'ar': 'كل الحالات', 'en': 'All statuses'}, 'Tous les types': {'ar': 'كل الأنواع', 'en': 'All types'}, 'Aucun résultat': {'ar': 'لا توجد نتائج', 'en': 'No results'}, 'Aucune donnée': {'ar': 'لا توجد بيانات', 'en': 'No data'}, 'Aucune notification': {'ar': 'لا توجد إشعارات', 'en': 'No notifications'}, 'Aucune mission': {'ar': 'لا توجد مهام', 'en': 'No missions'}, 'Aucun événement': {'ar': 'لا توجد فعاليات', 'en': 'No events'}, 'Aucun arbre': {'ar': 'لا توجد أشجار', 'en': 'No trees'}, 'Aucune zone': {'ar': 'لا توجد مناطق', 'en': 'No zones'}, 'Aucun projet': {'ar': 'لا توجد مشاريع', 'en': 'No projects'}, 'Latitude': {'ar': 'خط العرض', 'en': 'Latitude'}, 'Longitude': {'ar': 'خط الطول', 'en': 'Longitude'}, 'Position GPS': {'ar': 'موقع GPS', 'en': 'GPS position'}, 'Utiliser ma position': {'ar': 'استخدام موقعي', 'en': 'Use my location'}, 'Localiser': {'ar': 'تحديد الموقع', 'en': 'Locate'}, 'GPS indisponible': {'ar': 'GPS غير متاح', 'en': 'GPS unavailable'}, 'Autorisation GPS refusée': {'ar': 'تم رفض إذن GPS', 'en': 'GPS permission denied'}, 'Photo actuelle': {'ar': 'الصورة الحالية', 'en': 'Current photo'}, 'Remplacer la photo': {'ar': 'استبدال الصورة', 'en': 'Replace photo'}, 'Supprimer la photo': {'ar': 'حذف الصورة', 'en': 'Delete photo'}, 'Caméra': {'ar': 'الكاميرا', 'en': 'Camera'}, 'Démarrer / réessayer': {'ar': 'بدء / إعادة المحاولة', 'en': 'Start / retry'}, 'Arrêter': {'ar': 'إيقاف', 'en': 'Stop'}, 'Lire une photo': {'ar': 'قراءة صورة', 'en': 'Read an image'}, 'Ouvrir la fiche': {'ar': 'فتح البطاقة', 'en': 'Open details'}, 'Code arbre ou QR': {'ar': 'رمز الشجرة أو QR', 'en': 'Tree code or QR'}, 'Scanner le QR d’un arbre': {'ar': 'مسح رمز QR لشجرة', 'en': 'Scan a tree QR code'}, 'Caméra non démarrée.': {'ar': 'الكاميرا لم تبدأ.', 'en': 'Camera not started.'}, 'Autorisez la caméra.': {'ar': 'اسمح باستخدام الكاميرا.', 'en': 'Allow camera access.'}, 'Objectif': {'ar': 'الهدف', 'en': 'Target'}, 'Objectif du projet': {'ar': 'هدف المشروع', 'en': 'Project target'}, 'Objectif de la zone': {'ar': 'هدف المنطقة', 'en': 'Zone target'}, 'Arbres plantés': {'ar': 'الأشجار المغروسة', 'en': 'Planted trees'}, 'Arbres restants': {'ar': 'الأشجار المتبقية', 'en': 'Remaining trees'}, 'Capacité': {'ar': 'السعة', 'en': 'Capacity'}, 'Dépasser l’objectif': {'ar': 'تجاوز الهدف', 'en': 'Exceed target'}, 'Membres': {'ar': 'الأعضاء', 'en': 'Members'}, 'Membre': {'ar': 'عضو', 'en': 'Member'}, 'Ajouter des membres': {'ar': 'إضافة أعضاء', 'en': 'Add members'}, 'Modifier les membres': {'ar': 'تعديل الأعضاء', 'en': 'Edit members'}, 'Date d’inscription': {'ar': 'تاريخ التسجيل', 'en': 'Registration date'}, 'Activer': {'ar': 'تفعيل', 'en': 'Activate'}, 'Désactiver': {'ar': 'تعطيل', 'en': 'Deactivate'}, 'Administrateur': {'ar': 'مسؤول', 'en': 'Administrator'}, 'Permissions': {'ar': 'الصلاحيات', 'en': 'Permissions'}, 'Lecture seule': {'ar': 'قراءة فقط', 'en': 'Read only'}, 'Accès interdit': {'ar': 'الوصول ممنوع', 'en': 'Access forbidden'}, 'Vous n’avez pas accès à cette ressource.': {'ar': 'ليس لديك صلاحية للوصول إلى هذا المورد.', 'en': 'You do not have access to this resource.'}, 'Cette action nécessite les droits administrateur.': {'ar': 'يتطلب هذا الإجراء صلاحيات المسؤول.', 'en': 'This action requires administrator permissions.'}, 'Ressource introuvable.': {'ar': 'المورد غير موجود.', 'en': 'Resource not found.'}, 'Projet incompatible avec la zone.': {'ar': 'المشروع غير متوافق مع المنطقة.', 'en': 'Project is incompatible with the zone.'}, 'Zone incompatible avec le projet.': {'ar': 'المنطقة غير متوافقة مع المشروع.', 'en': 'Zone is incompatible with the project.'}, 'Objectif dépassé.': {'ar': 'تم تجاوز الهدف.', 'en': 'Target exceeded.'}, 'Quantité invalide.': {'ar': 'الكمية غير صالحة.', 'en': 'Invalid quantity.'}, 'Ce formulaire a déjà été envoyé.': {'ar': 'تم إرسال هذا النموذج مسبقاً.', 'en': 'This form has already been submitted.'}, 'Traitement en cours…': {'ar': 'جارٍ المعالجة…', 'en': 'Processing…'}, 'Enregistrer les modifications': {'ar': 'حفظ التعديلات', 'en': 'Save changes'}, 'Créer le projet': {'ar': 'إنشاء المشروع', 'en': 'Create project'}, 'Créer la zone': {'ar': 'إنشاء المنطقة', 'en': 'Create zone'}, 'Créer l’équipe': {'ar': 'إنشاء الفريق', 'en': 'Create team'}, 'Créer la mission': {'ar': 'إنشاء المهمة', 'en': 'Create mission'}, 'Créer l’événement': {'ar': 'إنشاء الفعالية', 'en': 'Create event'}, 'Rapport': {'ar': 'تقرير', 'en': 'Report'}, 'Statistiques': {'ar': 'الإحصائيات', 'en': 'Statistics'}, 'Exporter CSV': {'ar': 'تصدير CSV', 'en': 'Export CSV'}, 'Télécharger': {'ar': 'تنزيل', 'en': 'Download'}, 'Imprimer la fiche': {'ar': 'طباعة البطاقة', 'en': 'Print details'}, 'Origine': {'ar': 'الأصل', 'en': 'Origin'}, 'Régions': {'ar': 'المناطق', 'en': 'Regions'}, 'Sol': {'ar': 'التربة', 'en': 'Soil'}, 'Eau': {'ar': 'الماء', 'en': 'Water'}, 'Distance': {'ar': 'المسافة', 'en': 'Distance'}, 'Hauteur adulte': {'ar': 'الارتفاع عند النضج', 'en': 'Adult height'}, 'Usages': {'ar': 'الاستخدامات', 'en': 'Uses'}, 'Entretien': {'ar': 'العناية', 'en': 'Maintenance'}, 'Maladies et précautions': {'ar': 'الأمراض والاحتياطات', 'en': 'Diseases and precautions'}, 'Maladies et parasites': {'ar': 'الأمراض والآفات', 'en': 'Diseases and pests'}, 'Compatibilité et précautions': {'ar': 'التوافق والاحتياطات', 'en': 'Compatibility and precautions'}, 'Famille non renseignée': {'ar': 'العائلة غير محددة', 'en': 'Family not specified'}, 'Variable': {'ar': 'متغير', 'en': 'Variable'}, 'Soleil': {'ar': 'الشمس', 'en': 'Sun'}, 'À adapter': {'ar': 'يُحدد حسب الحالة', 'en': 'To be adapted'}, 'Biodiversité et paysage': {'ar': 'التنوع البيولوجي والمنظر الطبيعي', 'en': 'Biodiversity and landscape'}, 'Année': {'ar': 'السنة', 'en': 'Year'}, 'Carte d’adhérent': {'ar': 'بطاقة العضو', 'en': 'Membership card'}, 'Imprimer la carte PVC': {'ar': 'طباعة بطاقة PVC', 'en': 'Print PVC card'}, 'Retour à la liste': {'ar': 'العودة إلى القائمة', 'en': 'Back to list'}, 'Précédent': {'ar': 'السابق', 'en': 'Previous'}, 'Suivant': {'ar': 'التالي', 'en': 'Next'}}
I18N.update(I18N_LOT11)
def current_lang():
 lang=session.get('lang') or request.cookies.get('mytree_lang') or 'fr'
 return lang if lang in SUPPORTED_LANGS else 'fr'

def current_dir(): return 'rtl' if current_lang()=='ar' else 'ltr'

def tr(text):
 if text is None:return ''
 lang=current_lang(); text=str(text)
 return text if lang=='fr' else I18N.get(text,{}).get(lang,text)

def language_switcher():
 lang=current_lang(); back=request.full_path.rstrip('?') or '/'; out=[]
 for code,label in [('fr','FR'),('ar','العربية'),('en','EN')]:
  cls='lang-active' if code==lang else ''
  out.append(f'<a class="lang-link {cls}" href="/language/{code}?next={back}">{label}</a>')
 return '<div class="lang-switch">'+''.join(out)+'</div>'

def i18n_script():
 lang=current_lang()
 trans={} if lang=='fr' else {k:v.get(lang,k) for k,v in I18N.items()}
 js = r'''<script id="mytree-i18n">window.MYTREE_LANG=__LANG__;window.MYTREE_I18N=__DICT__;
(function(){
 const D=window.MYTREE_I18N||{};
 function ex(s){return (s||'').replace(/\s+/g,' ').trim()}
 function tv(k){if(!k)return null;if(D[k])return D[k];const keys=Object.keys(D).sort((a,b)=>b.length-a.length);for(const x of keys){if(k.endsWith(x)){const pre=k.slice(0,k.length-x.length);if(!pre||/[^A-Za-zÀ-ÿ\u0600-\u06FF]$/.test(pre))return pre+D[x]}}return null}
 function attr(e,n){if(!e.hasAttribute(n))return;let k=ex(e.getAttribute(n)),v=tv(k);if(v)e.setAttribute(n,v)}
 function oneText(n){if(!n.parentElement||['SCRIPT','STYLE','TEXTAREA','CODE','PRE'].includes(n.parentElement.tagName))return;let raw=n.nodeValue,k=ex(raw),v=tv(k);if(v){let l=(raw.match(/^\s*/)||[''])[0],r=(raw.match(/\s*$/)||[''])[0];n.nodeValue=l+v+r}}
 function go(root){if(!root||!D)return;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),a=[];while(w.nextNode())a.push(w.currentNode);a.forEach(oneText);(root.querySelectorAll?root.querySelectorAll('[placeholder],[title],[aria-label],[data-i18n],input[type=submit],input[type=button],option'):[]).forEach(e=>{attr(e,'placeholder');attr(e,'title');attr(e,'aria-label');if(e.dataset&&e.dataset.i18n){let v=tv(ex(e.dataset.i18n));if(v)e.textContent=v}if(e.matches('input[type=submit],input[type=button]')){let v=tv(ex(e.value));if(v)e.value=v}if(e.tagName==='OPTION'){let v=tv(ex(e.textContent));if(v)e.textContent=v}})}
 document.documentElement.lang=window.MYTREE_LANG||'fr';document.documentElement.dir=window.MYTREE_LANG==='ar'?'rtl':'ltr';
 document.addEventListener('DOMContentLoaded',()=>go(document.body));
 new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType===1)go(n);else if(n.nodeType===3)oneText(n)}))).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''
 return js.replace('__LANG__',json.dumps(lang)).replace('__DICT__',json.dumps(trans,ensure_ascii=False))

@app.route('/language/<lang>')
def set_language(lang):
 if lang not in SUPPORTED_LANGS:lang='fr'
 session['lang']=lang
 if session.get('uid'):
  c=db(); c.execute('UPDATE users SET preferred_language=? WHERE id=?',(lang,session['uid'])); c.commit(); c.close()
 target=request.args.get('next') or '/public'
 if not target.startswith('/'):target='/public'
 resp=redirect(target); resp.set_cookie('mytree_lang',lang,max_age=365*24*3600,samesite='Lax'); return resp

UNIVERSAL_SEARCH_SCRIPT='''<script id="mytree-smart-search">(function(){function n(v){return (v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim()}function ph(){return window.MYTREE_LANG==='ar'?'بحث ذكي في القائمة…':window.MYTREE_LANG==='en'?'Smart search in list…':'Recherche intelligente dans la liste…'}function enhance(s){if(!s||s.dataset.smartSearch==='1'||s.dataset.noSmartSearch==='1'||s.multiple||s.options.length<4)return;s.dataset.smartSearch='1';const q=document.createElement('input');q.type='search';q.className='smart-list-search';q.placeholder=ph();q.autocomplete='off';s.parentNode.insertBefore(q,s);let src=[];function snap(){src=[...s.options].map(o=>({v:o.value,t:o.text,d:o.disabled}))}snap();q.addEventListener('focus',snap);q.addEventListener('input',()=>{const z=n(q.value),cur=s.value,base=src.length?src:[...s.options].map(o=>({v:o.value,t:o.text,d:o.disabled}));const m=base.filter((o,i)=>i===0||!z||n(o.t).includes(z));s.innerHTML='';m.forEach(o=>{const x=document.createElement('option');x.value=o.v;x.textContent=o.t;x.disabled=o.d;if(o.v===cur)x.selected=true;s.appendChild(x)});if(z&&m.length>1&&!s.value)s.selectedIndex=1});s.addEventListener('change',()=>{const o=s.options[s.selectedIndex];if(o&&o.value)q.value=o.text})}function scan(r){(r||document).querySelectorAll('select').forEach(enhance)}document.addEventListener('DOMContentLoaded',()=>scan(document));new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(x=>{if(x.nodeType===1){if(x.matches&&x.matches('select'))enhance(x);scan(x)}}))).observe(document.documentElement,{childList:true,subtree:true});})();</script>'''

DEPENDENT_SELECTS_SCRIPT='''<script id="mytree-dependent-selects">(function(){
async function fill(url,sel,selected,label){if(!sel)return;const cur=selected??sel.value;sel.innerHTML='<option value="">'+(label||'—')+'</option>';if(!url)return;try{const rows=await fetch(url).then(r=>r.ok?r.json():[]);rows.forEach(x=>{let o=new Option((x.name||'')+(x.name_ar?' — '+x.name_ar:''),x.id);if(String(x.id)===String(cur))o.selected=true;sel.add(o)})}catch(e){}}
async function bindGeo(root){for(const w of root.querySelectorAll('select[name="wilaya_id"]')){if(w.dataset.depGeo)return;w.dataset.depGeo='1';const form=w.closest('form')||root,c=form.querySelector('select[name="commune_id"]');if(!c)continue;const initial=c.value;w.addEventListener('change',()=>fill(w.value?'/api/communes/'+w.value:null,c,null,'—'));if(w.value)await fill('/api/communes/'+w.value,c,initial,'—')}}
async function bindProject(root){for(const p of root.querySelectorAll('select[name="project_id"]')){if(p.dataset.depProject)return;p.dataset.depProject='1';const form=p.closest('form')||root,z=form.querySelector('select[name="zone_id"]');if(!z)continue;const initial=z.value;p.addEventListener('change',()=>fill(p.value?'/api/projects/'+p.value+'/zones':null,z,null,'—'));if(p.value)await fill('/api/projects/'+p.value+'/zones',z,initial,'—')}}
async function bindTeam(root){for(const t of root.querySelectorAll('select[name="team_id"]')){if(t.dataset.depTeam)return;t.dataset.depTeam='1';const form=t.closest('form')||root,l=form.querySelector('select[name="leader_user_id"],select[name="assigned_user_id"]');if(!l)continue;t.addEventListener('change',async()=>{if(!t.value)return;try{const d=await fetch('/api/teams/'+t.value+'/leader').then(r=>r.ok?r.json():{});if(d.leader_user_id){l.value=String(d.leader_user_id);l.dispatchEvent(new Event('change',{bubbles:true}))}}catch(e){}})}}
async function scan(root){await bindGeo(root);await bindProject(root);await bindTeam(root)}document.addEventListener('DOMContentLoaded',()=>scan(document));new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType===1)scan(n)}))).observe(document.documentElement,{childList:true,subtree:true});})();</script>'''

def log_action(action,entity_type,entity_id=None,details=''):
 c=db(); c.execute('INSERT INTO activity_log(user_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session.get('uid'),action,entity_type,entity_id,details,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close()

def notify(title,message='',link=None,user_id=None,category='Général'):
 c=db(); c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(user_id,title,message,link,category,datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close()

def notify_admins_in_tx(c,title,message='',link=None,category='Général',action_type=None,action_id=None):
 rows=c.execute("SELECT DISTINCT u.id FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND (COALESCE(r.name,u.role) IN ('admin','super_admin'))").fetchall()
 now=datetime.now().isoformat(timespec='minutes')
 for r in rows:
  c.execute('INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)',(r['id'],title,message,link,category,action_type,action_id,now))

def login_required(fn):
 @wraps(fn)
 def w(*a,**k):
  if not session.get('uid'):
   # Compatibilité avec les QR déjà imprimés : ancien lien /tree/<id>?token=...
   mt=re.fullmatch(r'/tree/(\d+)',request.path or '')
   if mt and request.args.get('token'): return redirect('/public/map?tree='+mt.group(1))
   return redirect('/login')
  return fn(*a,**k)
 return w

def _safe_local_target(value, fallback='/'):
 value=(value or '').strip()
 return value if value.startswith('/') and not value.startswith('//') else fallback

@app.before_request
def prevent_duplicate_post():
 """Lot 9 — bloque la répétition du même formulaire POST par jeton unique SQL."""
 if request.method!='POST': return None
 token=(request.form.get('_submit_token') or request.headers.get('X-MyTree-Submit-Token') or '').strip()
 if not token: return None
 c=db()
 try:
  c.execute('INSERT INTO submission_tokens(token,user_id,route,created_at) VALUES(?,?,?,?)',(token,session.get('uid'),request.path,datetime.now().isoformat(timespec='seconds')))
  cutoff=(datetime.now()-timedelta(days=1)).isoformat(timespec='seconds')
  c.execute('DELETE FROM submission_tokens WHERE created_at<?',(cutoff,))
  c.commit(); c.close(); return None
 except sqlite3.IntegrityError:
  c.close()
  flash('Cette opération a déjà été envoyée. Aucun double enregistrement n’a été créé.','warning')
  fallback='/' if is_admin() else '/volunteer'
  return redirect(_safe_local_target(request.form.get('return_to') or request.referrer or fallback,fallback))

def is_admin():
 # Rôle GLOBAL uniquement. Un association_admin ne devient jamais admin global.
 return session.get('role') in ('super_admin','admin')

def is_association_admin():
 ctx=active_context()
 return ctx.get('type')=='association' and ctx.get('role_code') in ('association_admin','admin')

def profile_home():
 ctx=active_context()
 if ctx.get('type')=='association': return '/association'
 if is_admin(): return '/'
 return '/volunteer'

def profile_identity():
 if not session.get('uid'): return {'type':'public','name':'Public','subtitle':''}
 c=db(); ctx=active_context(c)
 if ctx.get('type')=='association' and ctx.get('association_id'):
  a=c.execute("SELECT name,map_symbol FROM associations WHERE id=?",(ctx['association_id'],)).fetchone()
  c.close()
  role='Administrateur' if ctx.get('role_code') in ('association_admin','admin') else 'Bénévole'
  return {'type':'association','name':((a['map_symbol'] or '🌿')+' '+a['name']) if a else ctx.get('name','Association'),
          'subtitle':role+' · géré par '+str(session.get('name') or '')}
 c.close()
 if ctx.get('type')=='global': return {'type':'global','name':'🌐 MyTree Global','subtitle':'Super Admin · '+str(session.get('name') or '')}
 return {'type':'personal','name':'👤 '+str(session.get('name') or 'Mon profil'),'subtitle':'Profil personnel'}


def has_permission(code):
 if not session.get('uid'): return False
 ctx=active_context()
 # Une identité Association utilise exclusivement les permissions de cette association.
 if ctx.get('type')=='association' and not is_super_admin():
  return has_association_permission(code,ctx.get('association_id'))
 # Global/Personnel conservent uniquement les droits du compte global/personnel.
 if is_admin(): return True
 c=db()
 override=c.execute('''SELECT up.granted FROM user_permissions up JOIN permissions p ON p.id=up.permission_id WHERE up.user_id=? AND p.code=?''',(session['uid'],code)).fetchone()
 if override is not None:
  c.close(); return bool(override['granted'])
 row=c.execute('''SELECT 1 FROM users u JOIN role_permissions rp ON rp.role_id=u.role_id JOIN permissions p ON p.id=rp.permission_id JOIN roles r ON r.id=u.role_id WHERE u.id=? AND u.active=1 AND r.active=1 AND p.code=?''',(session['uid'],code)).fetchone(); c.close(); return bool(row)


def permission_required(code):
 def deco(fn):
  @wraps(fn)
  def wrapped(*a,**k):
   if not session.get('uid'): return redirect('/login')
   if not has_permission(code): flash('Accès non autorisé pour votre rôle.'); return redirect('/volunteer' if not is_admin() else '/')
   return fn(*a,**k)
  return wrapped
 return deco

def get_preferences(c,user_id):
 return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM user_preferences WHERE user_id=?',(user_id,))}

def save_preferences(c,user_id,values):
 for key,value in values.items():
  c.execute('INSERT INTO user_preferences(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value',(user_id,key,str(value or '')))


def clean(value):
 return (value or '').strip()

def user_display_name(first_name,last_name):
 return (clean(first_name)+' '+clean(last_name)).strip()

def user_form_values(form):
 return dict(first_name=clean(form.get('first_name')),last_name=clean(form.get('last_name')),sex=clean(form.get('sex')) or 'Homme',phone=clean(form.get('phone')),email=clean(form.get('email')) or None,wilaya_id=form.get('wilaya_id') or None,commune_id=form.get('commune_id') or None,birth_date=form.get('birth_date') or None,address=clean(form.get('address')) or None,skills=clean(form.get('skills')) or None,availability=clean(form.get('availability')) or None,photo_url=clean(form.get('photo_url')) or None)

def validate_user_form(c,values,user_id=None,password_required=False,password=None):
 errors=[]
 if not values['first_name']: errors.append('Le prénom est obligatoire.')
 if not values['last_name']: errors.append('Le nom est obligatoire.')
 if not values['phone']: errors.append('Le téléphone est obligatoire.')
 if password_required and not password: errors.append('Le mot de passe est obligatoire.')
 if password and len(password)<6: errors.append('Le mot de passe doit contenir au moins 6 caractères.')
 if values['email'] and '@' not in values['email']: errors.append("L’adresse e-mail n’est pas valide.")
 if values['commune_id'] and values['wilaya_id']:
  ok=c.execute('SELECT 1 FROM communes WHERE id=? AND wilaya_id=?',(values['commune_id'],values['wilaya_id'])).fetchone()
  if not ok: errors.append('La commune sélectionnée ne correspond pas à la wilaya.')
 sql='SELECT id FROM users WHERE phone=?'
 params=[values['phone']]
 if user_id is not None: sql+=' AND id<>?'; params.append(user_id)
 if values['phone'] and c.execute(sql,params).fetchone(): errors.append('Ce numéro de téléphone est déjà utilisé.')
 if values['email']:
  sql='SELECT id FROM users WHERE lower(email)=lower(?)'; params=[values['email']]
  if user_id is not None: sql+=' AND id<>?'; params.append(user_id)
  if c.execute(sql,params).fetchone(): errors.append('Cette adresse e-mail est déjà utilisée.')
 return errors

STYLE='''<style>:root{--bg:#f3f6f1;--card:#fff;--text:#223129;--muted:#748079;--line:#dfe7df;--deep:#102b1c;--green:#2e7b47;--red:#bd4747;--amber:#bd8120;--blue:#2c68b8}*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}header{height:64px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px}.layout{display:grid;grid-template-columns:250px 1fr;min-height:calc(100vh - 64px)}aside{background:linear-gradient(180deg,#102b1c,#0b2015);padding:18px 13px;color:#fff}.brand{font-size:23px;font-weight:800}.slogan{font-size:12px;color:#b9cabf;margin:4px 0 18px}aside a{display:block;color:#dce9df;text-decoration:none;padding:10px 13px;border-radius:9px;margin:3px 0}aside a:hover{background:#205837}main{padding:20px}.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(5,1fr)}.two{grid-template-columns:2fr 1fr}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px}.kpi{cursor:pointer;text-decoration:none;color:inherit}.kpi small{color:var(--muted)}.kpi b{font-size:28px;display:block;margin:8px 0}.btn{display:inline-block;border:0;background:var(--green);color:#fff;padding:9px 13px;border-radius:8px;text-decoration:none;cursor:pointer}.btn.alt{background:#edf2ed;color:#24352b}.btn.red{background:#fff;color:#8b3434;border:1px solid #e4caca}.btn.red:hover{background:#fff6f6;border-color:#c98f8f}.btn.amber{background:var(--amber)}.toolbar{display:flex;gap:9px;flex-wrap:wrap;align-items:end;margin-bottom:12px}.toolbar label{min-width:145px;flex:1}input,select,textarea{width:100%;padding:9px;border:1px solid #cbd6ce;border-radius:8px;background:#fff}textarea{min-height:75px}.form{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.full{grid-column:1/-1}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}th{background:#f8faf7}.badge{padding:4px 8px;border-radius:20px;font-size:11px;font-weight:bold}.good{background:#e1f1e4;color:#28643b}.watch{background:#fff0d4;color:#885800}.danger{background:#fbe1e1;color:#983636}.pending{background:#e7edfa;color:#315fa2}.flash{background:#fff0d4;padding:10px;border-radius:8px;margin-bottom:12px}.section-title{display:flex;align-items:center;justify-content:space-between}.sub{font-size:12px;color:var(--muted)}@media(max-width:1050px){.layout{grid-template-columns:1fr}aside{display:flex;overflow:auto;padding:8px}.brand,.slogan{display:none}aside a{min-width:max-content}.kpis{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}@media(max-width:600px){main{padding:10px}.form,.kpis{grid-template-columns:1fr}.full{grid-column:auto}}.real-map{height:560px;border-radius:12px;border:1px solid var(--line)}.leaflet-popup-content{min-width:230px}.qr-grid{display:grid;grid-template-columns:repeat(var(--qr-cols,3),1fr);gap:14px}.qr-grid.qr-1{--qr-cols:1}.qr-grid.qr-6{--qr-cols:2}.qr-grid.qr-12{--qr-cols:3}.qr-grid.qr-24{--qr-cols:4}.qr-grid.qr-thermal{--qr-cols:1;max-width:80mm;margin:auto}.qr-grid.qr-1 .qr-label img{width:360px;height:360px}.qr-grid.qr-24 .qr-label{padding:6px;font-size:10px}.qr-grid.qr-24 .qr-label img{width:105px;height:105px}.qr-grid.qr-thermal .qr-label{border:0;border-bottom:1px dashed #777;border-radius:0}.photo-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.photo-preview{max-width:280px;max-height:240px;border-radius:10px;object-fit:cover;cursor:pointer}.gps-quality{font-weight:700}.gps-good{color:#2e7b47}.gps-medium{color:#bd8120}.gps-bad{color:#bd4747}.qr-label{border:1px dashed #78867d;border-radius:10px;padding:12px;text-align:center;background:#fff;break-inside:avoid}.qr-label img{width:180px;height:180px;max-width:100%}.nearby{background:#eaf4ff;color:#275c91;padding:8px;border-radius:8px}.compact-table{max-height:310px;overflow:auto}.priority{padding:10px;border-bottom:1px solid var(--line)}.priority b,.priority span{display:block}@media print{header,aside,.noprint{display:none!important}.layout{display:block}.qr-grid{grid-template-columns:repeat(var(--qr-cols,3),1fr)!important}main{padding:0}.qr-label{page-break-inside:avoid}}@media(max-width:700px){.qr-grid{grid-template-columns:1fr}.real-map{height:65vh}}.vol-hero{background:linear-gradient(135deg,#174d2d,#2e7b47);color:#fff;border-radius:18px;padding:20px;margin-bottom:14px}.vol-actions{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.vol-action{display:flex;min-height:105px;flex-direction:column;align-items:center;justify-content:center;text-align:center;font-weight:700;font-size:15px;background:#fff;border:1px solid var(--line);border-radius:16px;text-decoration:none;color:var(--text);box-shadow:0 5px 18px rgba(16,43,28,.06)}.vol-action span{font-size:30px;margin-bottom:8px}.mobile-note{background:#eaf4ee;border-left:4px solid var(--green);padding:10px 12px;border-radius:8px}.scan-box{max-width:620px;margin:auto}.scan-preview{width:100%;min-height:260px;background:#102b1c;border-radius:14px;object-fit:cover}.bottom-space{height:20px}@media(max-width:700px){header{height:auto;padding:12px 14px;align-items:flex-start}.vol-actions{grid-template-columns:repeat(2,1fr)}.vol-action{min-height:112px}.layout{padding-bottom:68px}.vol-nav{position:fixed;bottom:0;left:0;right:0;z-index:1200;display:flex!important;overflow-x:auto;background:#102b1c;padding:5px 6px}.vol-nav a{font-size:11px;text-align:center;min-width:74px;padding:7px 6px;margin:0}.vol-nav .brand,.vol-nav .slogan{display:none}.card{border-radius:12px}.kpi b{font-size:24px}}.header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.context-switch{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.context-pill{padding:7px 9px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--text);text-decoration:none;font-size:12px;font-weight:700}.context-pill.active{background:var(--deep);color:#fff}.context-badge{font-size:11px;color:var(--muted)}.account-home,.account-logout{padding:8px 10px;border-radius:9px;text-decoration:none;font-weight:700}.account-home{background:#e9f4ec;color:#205d36}.account-logout{background:#f4eeee;color:#683b3b}.location-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.member-picker{max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:10px}.member-picker label{display:flex;align-items:center;gap:8px;padding:5px}.member-picker input{width:auto}.notif-bell{position:relative;text-decoration:none;font-size:23px}.notif-bell span{position:absolute;top:-7px;right:-10px;background:#d92727;color:#fff;border-radius:999px;min-width:19px;height:19px;padding:2px 5px;font-size:11px;text-align:center;font-weight:800;border:2px solid #fff}.public-hero{background:linear-gradient(135deg,#0e3b25,#3c8d55);color:#fff;border-radius:22px;padding:42px 28px}.public-actions{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.public-action{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;text-decoration:none;color:var(--text);text-align:center;font-weight:700}.species-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.species-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;text-decoration:none;color:inherit}.map-picker{height:420px;border-radius:12px;border:1px solid var(--line)}@media(max-width:800px){.public-actions,.species-grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.public-actions,.species-grid{grid-template-columns:1fr}}
.public-shell{max-width:1240px;margin:auto;padding:0 18px}.public-header{position:sticky;top:0;z-index:1100;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);min-height:72px}.public-brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--deep);font-size:21px;font-weight:800}.public-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.hero-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:18px;align-items:stretch}.hero-side{background:#fff;border:1px solid var(--line);border-radius:22px;padding:24px;display:flex;flex-direction:column;justify-content:center}.hero-side b{font-size:34px}.public-section{margin:28px 0}.public-section h2{margin-bottom:8px}.public-action{min-height:132px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:17px;box-shadow:0 8px 24px rgba(16,43,28,.06);transition:.18s transform,.18s box-shadow}.public-action:hover,.species-card:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(16,43,28,.10)}.public-action .icon{font-size:34px;margin-bottom:8px}.public-kpis{grid-template-columns:repeat(4,1fr)}.public-kpis .kpi{cursor:default}.public-footer{margin-top:36px;background:var(--deep);color:#dce9df;padding:28px 18px}.public-footer a{color:#fff}.mobile-public-nav{display:none}.field-hero{background:linear-gradient(135deg,#102b1c,#2e7b47);color:#fff;border-radius:20px;padding:22px}.field-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:16px}.field-action{min-height:132px;background:#fff;border:1px solid var(--line);border-radius:18px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-decoration:none;color:var(--text);font-size:17px;font-weight:800}.field-action span{font-size:38px;margin-bottom:8px}.home-shortcut{font-weight:700;text-decoration:none;color:var(--green)}
@media(max-width:900px){.hero-grid{grid-template-columns:1fr}.public-kpis{grid-template-columns:repeat(2,1fr)}.public-header{position:relative}.public-nav{display:none}.mobile-public-nav{display:grid;grid-template-columns:repeat(6,1fr);position:fixed;bottom:0;left:0;right:0;z-index:1300;background:#fff;border-top:1px solid var(--line);padding:5px 4px}.mobile-public-nav a{text-align:center;text-decoration:none;color:var(--text);font-size:10px;padding:6px 2px}.mobile-public-nav span{display:block;font-size:21px}.public-page-body{padding-bottom:68px}.field-actions{grid-template-columns:repeat(2,1fr)}}
.vertical-actions{display:flex;flex-direction:column;gap:12px}.vertical-action{display:flex;align-items:center;gap:14px;width:100%;min-height:68px;padding:14px 18px;border-radius:14px;background:#fff;border:1px solid var(--line);text-decoration:none;color:var(--text);font-weight:800;font-size:17px;box-shadow:0 5px 18px rgba(16,43,28,.06)}.vertical-action .icon{font-size:30px;min-width:38px;text-align:center}.nav-return-highlight{outline:3px solid #65a97b!important;background:#e8f6ec!important;transition:background .4s,outline .4s}.quick-actions{display:flex;gap:6px;flex-wrap:wrap}.quick-actions form{display:inline}.bulk-bar{position:sticky;top:0;z-index:10;background:#fff;border:1px solid var(--line);padding:12px;border-radius:12px;margin-bottom:10px}.action-card{border-left:5px solid var(--amber)}@media(max-width:700px){.vol-actions,.public-actions,.field-actions{display:flex;flex-direction:column}.vol-action,.public-action,.field-action{min-height:72px;flex-direction:row;justify-content:flex-start;padding:14px 18px;text-align:left}.vol-action span,.public-action .icon,.field-action span{font-size:30px;margin:0 14px 0 0}.header-actions .btn{min-height:44px;padding:12px 14px}.btn{min-height:44px;padding:12px 14px}.quick-actions .btn{min-height:38px;padding:8px 10px}.mobile-login{display:block!important;width:100%;margin-top:8px;text-align:center}}@media(max-width:560px){.public-shell{padding:0 10px}.public-hero{padding:28px 20px;border-radius:18px}.public-hero h1{font-size:28px;line-height:1.15}.public-hero .btn{display:block;width:100%;margin:8px 0;padding:14px}.public-kpis{grid-template-columns:1fr 1fr}.public-kpis .card{padding:13px}.public-actions{grid-template-columns:1fr}.public-action{min-height:96px;flex-direction:row;justify-content:flex-start;text-align:left;padding:18px;gap:14px}.public-action .icon{margin:0;font-size:30px}.species-grid{grid-template-columns:1fr}.field-actions{grid-template-columns:1fr}.field-action{min-height:94px;flex-direction:row;gap:14px}.field-action span{margin:0}.header-actions b{display:none}}

.don-line{display:grid;grid-template-columns:2fr 1fr auto;gap:8px;align-items:center;margin:9px 0}.action-set{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.action-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:10px;border:1px solid transparent;text-decoration:none;font-weight:700;cursor:pointer}.action-view{background:#eef5ff;color:#23558b}.action-map{background:#f1f0ff;color:#5848a5}.action-edit{background:#fff6df;color:#8a6113}.action-delete{background:#fff;color:#8b3434;border-color:#e4caca}.action-delete:hover{background:#fff6f6;border-color:#c98f8f}.action-primary{background:var(--green);color:#fff}.don-type-panel{display:none}.don-type-panel.active{display:contents}.mobile-only,.mobile-back{display:none}.private-section-label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#9fb5a7;padding:10px 13px 3px}.danger-zone{border:1px solid #efc4c4;background:#fff8f8}.crud-actions{display:flex;gap:7px;flex-wrap:wrap}.public-login-cta{display:inline-block}.public-auth-banner{display:none;gap:8px;justify-content:flex-end;padding-top:12px}.public-auth-banner .btn{display:inline-block}
@media(max-width:700px){
 header{height:auto;min-height:66px;position:sticky;top:0;z-index:1150;padding:10px 12px;flex-direction:row;align-items:center;gap:8px}.mobile-title-row{display:flex;align-items:center;gap:9px;min-width:0}.mobile-title-row b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:55vw}.mobile-back{display:inline-flex!important;width:42px;height:42px;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:24px;color:var(--deep)}.header-actions{margin-left:auto;width:auto;gap:10px}.header-actions>a:not(.notif-bell):not(.account-home):not(.account-logout),.header-actions>b{display:none}.header-actions .account-home,.header-actions .account-logout{display:inline-flex!important;align-items:center;justify-content:center;font-size:12px;padding:7px 8px;white-space:nowrap}.header-actions{display:flex!important;align-items:center;gap:5px}.lang-switch{display:none!important}.layout{display:block!important;padding-bottom:72px}.layout>aside.vol-nav{position:fixed!important;bottom:0;left:0;right:0;z-index:1200;height:66px;width:100%;display:grid!important;grid-template-columns:repeat(5,1fr)!important;background:#fff!important;border-top:1px solid var(--line);padding:4px!important;overflow:visible!important}.vol-nav .brand,.vol-nav .slogan,.vol-nav .desktop-only,.vol-nav .private-section-label{display:none!important}.vol-nav a{display:none!important}.vol-nav a.mobile-primary{display:flex!important;min-width:0!important;width:auto!important;margin:0!important;padding:5px 2px!important;border:0!important;border-radius:9px!important;background:transparent!important;color:var(--deep)!important;font-size:10px!important;line-height:1.15;text-align:center!important;align-items:center;justify-content:center;white-space:normal}.vol-nav a.mobile-primary:hover{background:#edf5ef!important}.layout>aside:not(.vol-nav){display:none!important}main{padding:12px 10px}.section-title{align-items:flex-start;gap:10px;flex-direction:column}.section-title>div,.section-title>.crud-actions{width:100%}.section-title .btn,.crud-actions .btn,.crud-actions form{width:100%}.crud-actions form .btn{width:100%}.toolbar{display:flex;flex-direction:column;align-items:stretch}.toolbar label,.toolbar .btn{width:100%;min-width:0}.form{grid-template-columns:1fr}.card{overflow-x:auto}.vertical-actions{width:100%}.vertical-action{min-height:64px;padding:13px 15px}.vertical-action .icon{font-size:28px}.secondary-action{background:#eef5f0}.desktop-dashboard-details{display:none}.mobile-only{display:block}.public-header .public-shell{flex-direction:column;align-items:stretch!important}.public-auth-banner{display:flex!important}.public-brand{text-align:center}.public-login-cta{display:block!important;width:100%;text-align:center}.mobile-public-nav{position:fixed!important;bottom:0!important;display:grid!important;grid-template-columns:repeat(5,1fr)!important;background:#fff!important;border-top:1px solid var(--line)!important;padding:4px!important;gap:0!important}.mobile-public-nav a{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;background:transparent!important;border:0!important;border-radius:9px!important;padding:5px 2px!important;font-size:10px!important;font-weight:700!important;text-align:center!important}.mobile-public-nav a:nth-child(n+6){display:none!important}.mobile-public-nav span{display:block!important;font-size:21px!important}.public-page-body{padding-bottom:68px!important}.vol-actions,.public-actions,.field-actions{display:flex!important;flex-direction:column!important}.vol-action,.public-action,.field-action{width:100%;min-height:68px!important}table{min-width:680px}
}
</style>'''
ALPHA3_STYLE="<style id='alpha3-filters'>.filter-panel{display:none}.filter-panel.open{display:block}.filter-quick{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.filter-actions{position:sticky;bottom:0;background:#fff;padding:12px 0;display:flex;justify-content:flex-end;gap:10px}.tree-emoji-marker{background:transparent!important;border:0!important}.tree-emoji-marker span{font-size:27px;filter:drop-shadow(0 1px 2px #fff)}@media(max-width:720px){.filter-panel.open{display:block;position:fixed;inset:4vh 2vw 0;z-index:9999;overflow:auto;border-radius:18px;padding-bottom:80px}.filter-panel .form{grid-template-columns:1fr}.filter-actions{position:fixed;left:2vw;right:2vw;bottom:0;padding:12px;background:white;z-index:10000}}</style>"
PHOTO_SCRIPT='''<script>
function mtPhoto(input,hiddenId,previewId,boxId){const f=input.files&&input.files[0];if(!f)return;const reader=new FileReader();reader.onload=e=>{const img=new Image();img.onload=()=>{let w=img.width,h=img.height,max=1280;if(w>max||h>max){const r=Math.min(max/w,max/h);w=Math.round(w*r);h=Math.round(h*r)}const cv=document.createElement('canvas');cv.width=w;cv.height=h;cv.getContext('2d').drawImage(img,0,0,w,h);const data=cv.toDataURL('image/jpeg',.82);document.getElementById(hiddenId).value=data;const p=document.getElementById(previewId);p.src=data;p.style.display='block';const b=document.getElementById(boxId);if(b)b.style.display='flex'};img.src=e.target.result};reader.readAsDataURL(f)}
function mtClearPhoto(hiddenId,previewId,boxId){document.getElementById(hiddenId).value='';const p=document.getElementById(previewId);p.src='';p.style.display='none';const b=document.getElementById(boxId);if(b)b.style.display='none'}
function mtViewPhoto(previewId){const p=document.getElementById(previewId);if(!p.src)return;const w=window.open('','_blank');w.document.write('<title>Photo</title><img src="'+p.src+'" style="max-width:100%;height:auto;display:block;margin:auto">')}
function mtTrigger(inputId){document.getElementById(inputId).click()}
</script>'''

def photo_fields(value='',prefix='photo'):
 value=value or ''
 shown='flex' if value else 'none'
 imgshown='block' if value else 'none'
 return f'''<div class="full card" style="background:#f8faf7"><b>Photo</b><input type="hidden" name="photo_url" id="{prefix}_value" value="{value}"><input id="{prefix}_camera" type="file" accept="image/*" capture="environment" style="display:none" onchange="mtPhoto(this,'{prefix}_value','{prefix}_preview','{prefix}_actions')"><input id="{prefix}_gallery" type="file" accept="image/*" style="display:none" onchange="mtPhoto(this,'{prefix}_value','{prefix}_preview','{prefix}_actions')"><div class="photo-actions"><button type="button" class="btn" onclick="mtTrigger('{prefix}_camera')">📷 Prendre une photo</button><button type="button" class="btn alt" onclick="mtTrigger('{prefix}_gallery')">🖼 Choisir depuis la galerie</button></div><img id="{prefix}_preview" class="photo-preview" src="{value}" style="display:{imgshown};margin-top:10px" onclick="mtViewPhoto('{prefix}_preview')"><div id="{prefix}_actions" class="photo-actions" style="display:{shown}"><button type="button" class="btn alt" onclick="mtViewPhoto('{prefix}_preview')">👁 Voir</button><button type="button" class="btn alt" onclick="mtTrigger('{prefix}_camera')">🔄 Reprendre</button><button type="button" class="btn alt" onclick="mtTrigger('{prefix}_gallery')">🖼 Remplacer</button><button type="button" class="btn red" onclick="mtClearPhoto('{prefix}_value','{prefix}_preview','{prefix}_actions')">❌ Supprimer</button></div></div>'''

NAV_ADMIN='''<aside class="admin-nav"><div class="brand">🌳 My Tree 🇩🇿</div><div class="slogan">Administration</div>
<div class="admin-nav-block"><div class="admin-nav-title">🌳 Terrain</div><a href="/trees">🌳 Arbres</a><a href="/plantings/pending">🌱 Plantations</a><a href="/watering">💧 Arrosages</a><a href="/map">🗺 Carte</a><a href="/volunteer/gps-quick">📍 GPS rapide</a><a href="/qr">▣ QR Code</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">📂 Organisation</div><a href="/projects">📁 Projets</a><a href="/zones">📍 Zones</a><a href="/teams">👥 Équipes</a><a href="/missions">🎯 Missions</a><a href="/operations">🗓 Planifications</a><a href="/events">📆 Événements</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">🏛 Multi-associations</div><a href="/admin/associations">🏛 Associations</a><a href="/association-requests">📨 Demandes associations</a><a href="/membership-requests">🤝 Demandes adhésion</a><a href="/admin/registration-settings">⚙️ Inscriptions</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">👥 Personnes</div><a href="/volunteers">🙋 Bénévoles</a><a href="/members">🪪 Adhérents</a><a href="/users">🔐 Utilisateurs</a><a href="/roles">🛡 Rôles et droits</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">💰 Gestion</div><a href="/cash">💰 Caisse</a><a href="/donations">🎁 Dons</a><a href="/members">🤝 Cotisations</a><a href="/stock">📦 Stock</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">📊 Administration</div><a href="/action-center">✅ Centre d’actions</a><a href="/notifications">🔔 Notifications</a><a href="/reports/operations">📊 Rapports</a><a href="/activity">🕘 Journal d’activité</a><a href="/backup">💾 Sauvegarde</a><a href="/species">🍃 Espèces</a><a href="/geography">📍 Géographie</a><a href="/search">🔎 Recherche</a></div>
</aside>'''
SMART_NAV_SCRIPT='''<script>
(function(){
 const prefix='mytree-nav:';
 const key=()=>prefix+location.pathname+location.search;
 const pathKey=()=>prefix+'path:'+location.pathname;
 function saveContext(clicked){
   const state={x:window.scrollX,y:window.scrollY,at:Date.now()};
   if(clicked){
     if(!clicked.dataset.navKey) clicked.dataset.navKey='nav-'+Math.random().toString(36).slice(2);
     state.element=clicked.dataset.navKey;
   }
   try{sessionStorage.setItem(key(),JSON.stringify(state));sessionStorage.setItem(pathKey(),JSON.stringify(state));}catch(e){}
 }
 document.addEventListener('click',function(e){
   const a=e.target.closest('a[href]');
   if(!a || a.target==='_blank' || a.hasAttribute('download')) return;
   const href=a.getAttribute('href')||'';
   if(href.startsWith('#') || href.startsWith('javascript:')) return;
   try{const u=new URL(a.href,location.href); if(u.origin===location.origin) saveContext(a);}catch(err){}
 },true);
 document.addEventListener('submit',function(e){
   saveContext(e.submitter||e.target);
   const f=e.target;
   if(f && f.method && f.method.toLowerCase()==='post'){
     let i=f.querySelector('input[name="return_to"]');
     if(!i){i=document.createElement('input');i.type='hidden';i.name='return_to';f.appendChild(i);}
     i.value=location.pathname+location.search;
   }
 },true);
 window.addEventListener('beforeunload',()=>saveContext(null));
 window.addEventListener('DOMContentLoaded',function(){
   let st=null; try{st=JSON.parse(sessionStorage.getItem(key())||sessionStorage.getItem(pathKey())||'null')}catch(e){}
   if(st && Date.now()-st.at<24*3600*1000){
     requestAnimationFrame(()=>requestAnimationFrame(()=>{
       window.scrollTo(st.x||0,st.y||0);
       if(st.element){
         const el=document.querySelector('[data-nav-key="'+st.element+'"]');
         if(el){el.classList.add('nav-return-highlight');setTimeout(()=>el.classList.remove('nav-return-highlight'),2200);}
       }
     }));
   }
 });
})();
</script>'''

STYLE += '''
<style id="rc1rev4-ui">
.admin-nav-block{margin:10px 0 16px}.admin-nav-title{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:#9fc1aa;padding:8px 12px 5px;border-top:1px solid rgba(255,255,255,.08)}
.admin-nav-block a{margin:2px 0!important}.action-set,.crud-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.action-set form,.crud-actions form{margin:0}.action-btn{min-height:38px}
.login-card{max-width:620px;margin:28px auto;padding:28px}.login-card h1,.login-card h2{font-size:30px;margin-top:0}.login-card input{font-size:17px;padding:14px 12px}.login-card .login-actions{display:grid;gap:10px;margin-top:18px}.login-card .login-actions .btn{width:100%;text-align:center;padding:13px 16px;font-size:16px}.account-home{display:inline-flex;align-items:center;gap:6px;text-decoration:none;font-weight:800;color:var(--green);background:#eef6f0;border:1px solid #d4e6d8;border-radius:10px;padding:8px 11px}
.admin-home-blocks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:0 0 18px}.admin-home-block{background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px}.admin-home-block h3{margin:0 0 12px}.admin-home-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.admin-home-links a{display:flex;align-items:center;justify-content:flex-start;min-height:48px;padding:10px 12px;border:1px solid var(--line);border-radius:11px;text-decoration:none;color:var(--text);font-weight:700;background:#fafcf9}.admin-home-links a:hover{background:#eef6f0;border-color:#bdd6c3}
@media(max-width:1050px) and (min-width:701px){.admin-nav{display:block!important;overflow:auto!important}.admin-home-links{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.don-line{grid-template-columns:1fr}.admin-home-block h3{cursor:pointer;margin:0!important;padding:7px 2px;display:flex;align-items:center;justify-content:space-between}.admin-home-block h3:after{content:'⌄';font-size:20px}.admin-home-block.open h3:after{content:'⌃'}.admin-home-block .admin-home-links{display:none!important;margin-top:10px}.admin-home-block.open .admin-home-links{display:grid!important}.login-card{margin:8px 0;padding:22px 16px;border-radius:16px}.login-card h1,.login-card h2{font-size:27px}.account-home{display:inline-flex!important;font-size:13px;padding:8px 9px}.header-actions .account-home{display:inline-flex!important}.admin-home-blocks{grid-template-columns:1fr}.admin-home-block{padding:14px}.admin-home-links{grid-template-columns:1fr}.admin-home-links a{min-height:56px;font-size:16px}.admin-nav{display:none!important}.action-set,.crud-actions{display:grid!important;grid-template-columns:1fr 1fr;width:100%}.action-set>a,.action-set>form,.crud-actions>a,.crud-actions>form,.action-set button,.crud-actions button{width:100%!important}.action-btn{justify-content:center}.public-auth-banner{align-items:stretch;flex-direction:column}.public-auth-banner .btn{width:100%;text-align:center}}
</style>
'''


STYLE += '''<style id="rev10-i18n-search">.lang-switch{display:inline-flex;gap:3px;align-items:center;background:#f5f8f5;border:1px solid var(--line);border-radius:10px;padding:3px}.lang-link{padding:6px 8px;border-radius:7px;text-decoration:none;color:var(--text);font-size:12px;font-weight:800}.lang-link.lang-active{background:var(--deep);color:#fff}.smart-list-search{margin:5px 0 6px!important;border:1px solid #b8c9bd!important;background:#fbfdfb!important;padding:9px 10px!important}html[dir="rtl"] body{text-align:right}html[dir="rtl"] th,html[dir="rtl"] td{text-align:right}html[dir="rtl"] .layout{grid-template-columns:1fr 250px}html[dir="rtl"] aside{grid-column:2}html[dir="rtl"] main{grid-column:1;grid-row:1}html[dir="rtl"] input,html[dir="rtl"] textarea,html[dir="rtl"] select{text-align:right}@media(max-width:1050px){html[dir="rtl"] .layout{grid-template-columns:1fr}html[dir="rtl"] aside,html[dir="rtl"] main{grid-column:auto;grid-row:auto}}@media(max-width:700px){.lang-switch{order:-1}.header-actions{flex-wrap:wrap}}</style>'''

ACTION_UI_SCRIPT='''<script>
(function(){
 function decorate(){
  document.querySelectorAll('a.btn,button.btn,.crud-actions a,.crud-actions button,.action-set a,.action-set button').forEach(function(el){
   const t=(el.textContent||'').toLowerCase();
   el.classList.add('action-btn');
   if(t.includes('supprim')||t.includes('désactiv')) el.classList.add('action-delete');
   else if(t.includes('modif')) el.classList.add('action-edit');
   else if(t.includes('carte')||t.includes('gps')||t.includes('itin')) el.classList.add('action-map');
   else if(t.includes('fiche')||t.includes('ouvrir')||t.includes('consulter')||t.includes('imprim')) el.classList.add('action-view');
   else if(t.includes('accept')||t.includes('enregistr')||t.includes('nouveau')||t.includes('ajouter')) el.classList.add('action-primary');
  });
 }
 document.addEventListener('DOMContentLoaded',decorate);
})();
</script>'''

def volunteer_nav():
 links=[('/volunteer','🏠 Accueil',None,'mobile-primary'),('/volunteer/field','🚜 Mode Terrain',None,'mobile-primary'),('/volunteer/trees','🌳 Mes arbres','tree.view','desktop-only'),('/volunteer/trees/no-gps','📍 Arbres sans GPS','tree.view','desktop-only'),('/volunteer/gps-quick','⚡ GPS rapide','tree.view','desktop-only'),('/planting/new','🌱 Planter','tree.create','desktop-only'),('/volunteer/watering','💧 Arroser','watering.view','desktop-only'),('/volunteer/scan','▣ Scanner QR','tree.view','mobile-primary'),('/map','📍 Carte','map.view','mobile-primary'),('/volunteer/donate','🎁 Faire un don',None,'desktop-only'),('/my-associations','🏛 Mes associations',None,'desktop-only'),('/volunteer/events','📆 Événements','event.view','desktop-only'),('/volunteer/missions','📋 Missions','mission.view','desktop-only'),('/interventions','🛠 Interventions','intervention.view','desktop-only'),('/volunteer/team','👥 Mon équipe','team.view','desktop-only'),('/notifications','🔔 Alertes','notification.view','mobile-primary'),('/volunteer/profile','👤 Profil',None,'mobile-primary')]
 body='<aside class="vol-nav"><div class="brand">🌳 My Tree 🇩🇿</div><div class="slogan">Espace bénévole privé</div>'
 for href,label,perm,css in links:
  if not perm or has_permission(perm): body+=f'<a class="{css}" href="{href}">{label}</a>'
 return body+'</aside>'



def association_nav():
 ctx=active_context()
 aid=ctx.get('association_id')
 role=ctx.get('role_code')
 admin=role in ('association_admin','admin')
 links=[
  ('/association','🏠 Accueil association',None),
  ('/map','🗺 Carte','map.view'),
  ('/volunteer/trees','🌳 Arbres','tree.view'),
  ('/projects','📁 Projets','project.read'),
  ('/zones','📍 Zones','zone.read'),
  ('/missions','🎯 Missions','mission.view'),
  ('/events','📆 Événements','event.view'),
  ('/teams','👥 Équipes','team.view'),
  ('/membership-requests','👥 Demandes membres',None if admin else '__admin__'),
  ('/collaborations','🤝 Collaborations',None if admin else '__admin__'),
  ('/notifications','🔔 Notifications','notification.view'),
 ]
 body='<aside class="vol-nav association-nav"><div class="brand">🏛 '+str(ctx.get('name') or 'Association')+'</div><div class="slogan">'+('Administration de l’association' if admin else 'Profil bénévole de l’association')+'</div>'
 for href,label,perm in links:
  if perm=='__admin__': continue
  if not perm or has_permission(perm): body+=f'<a href="{href}">{label}</a>'
 return body+'</aside>'

LOT11_STYLE='''<style id="mytree-lot11-i18n">
html[dir="rtl"] body{direction:rtl;text-align:right}
html[dir="rtl"] header,html[dir="rtl"] .header-actions,html[dir="rtl"] .toolbar,html[dir="rtl"] .section-title,html[dir="rtl"] .crud-actions{direction:rtl}
html[dir="rtl"] input,html[dir="rtl"] select,html[dir="rtl"] textarea{direction:rtl;text-align:right}
html[dir="rtl"] input[type="email"],html[dir="rtl"] input[type="tel"],html[dir="rtl"] input[type="number"],html[dir="rtl"] input[type="date"],html[dir="rtl"] input[type="datetime-local"],html[dir="rtl"] .code,html[dir="rtl"] .gps-coordinates{direction:ltr;text-align:left}
html[dir="rtl"] table{direction:rtl}html[dir="rtl"] th,html[dir="rtl"] td{text-align:right}
html[dir="rtl"] .leaflet-container,html[dir="rtl"] .leaflet-control,html[dir="rtl"] .leaflet-popup-content{direction:ltr;text-align:left}
html[dir="rtl"] .leaflet-popup-content .rtl-content{direction:rtl;text-align:right}
html[dir="rtl"] .lang-switch{direction:ltr}
html[dir="rtl"] .mobile-connected-nav{direction:rtl}html[dir="rtl"] .mobile-connected-nav a{text-align:center}
html[dir="rtl"] .flash{border-left:0;border-right-width:4px}
html[dir="rtl"] ul,html[dir="rtl"] ol{padding-right:22px;padding-left:0}
html[dir="rtl"] .filter-panel,html[dir="rtl"] .modal,html[dir="rtl"] .card{direction:rtl;text-align:right}
html[dir="rtl"] .smart-list-search{direction:rtl;text-align:right}
@media(max-width:700px){html[dir="rtl"] .header-actions,html[dir="rtl"] .mobile-title-row{direction:rtl}html[dir="rtl"] .form label{text-align:right}}
</style>'''

def connected_mobile_nav():
 ctx=active_context()
 if ctx.get('type')=='association':
  items=[
   ('/association','🏠','Accueil',None),
   ('/map','🗺','Carte','map.view'),
   ('/volunteer/trees','🌳','Arbres','tree.view'),
   ('/missions','🎯','Missions','mission.view'),
   ('/notifications','🔔','Alertes','notification.view'),
  ]
 else:
  items=[
   ('/' if is_admin() else '/volunteer','🏠','Accueil',None),
   ('/map','🗺','Carte','map.view'),
   ('/admin/associations' if is_super_admin() else '/my-associations','🏛','Associations',None),
   ('/notifications','🔔','Alertes','notification.view'),
   ('/missions' if is_admin() else '/volunteer/missions','🎯','Missions','mission.view'),
   ('/trees' if is_admin() else '/volunteer/field','🌳','Terrain','tree.view'),
  ]
 out='<nav class="mobile-connected-nav" aria-label="Navigation mobile">'
 for href,icon,label,perm in items:
  if perm and not has_permission(perm): continue
  active=' active' if request.path==href or (href!='/' and request.path.startswith(href+'/')) else ''
  out+=f'<a class="{active.strip()}" href="{href}"><span>{icon}</span>{tr(label)}</a>'
 return out+'</nav>'


LOT9_UX_SCRIPT='''<script id="mytree-lot9-ux">
(function(){
 function token(){try{return crypto.randomUUID()}catch(e){return Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)}}
 function prepareForm(f){
  if(!f || (f.method||'get').toLowerCase()!=='post' || f.dataset.lot9==='1')return;
  f.dataset.lot9='1';
  let t=f.querySelector('input[name="_submit_token"]');
  if(!t){t=document.createElement('input');t.type='hidden';t.name='_submit_token';t.value=token();f.appendChild(t)}
  f.addEventListener('submit',function(e){
   if(f.dataset.submitting==='1'){e.preventDefault();return false}
   if(!f.checkValidity())return;
   f.dataset.submitting='1';
   const active=e.submitter;
   // Preserve submitter semantics before disabling buttons (name/value, formaction, formmethod).
   if(active){
    if(active.name){const h=document.createElement('input');h.type='hidden';h.name=active.name;h.value=active.value||'';f.appendChild(h)}
    if(active.getAttribute('formaction'))f.action=active.formAction;
    if(active.getAttribute('formmethod'))f.method=active.formMethod;
   }
   const buttons=f.querySelectorAll('button[type="submit"],input[type="submit"],button:not([type])');
   buttons.forEach(function(b){b.disabled=true;b.classList.add('is-submitting')});
   if(active&&active.tagName==='BUTTON')active.textContent='Enregistrement…';
  },true);
 }
 function flashType(el){
  const t=(el.textContent||'').toLowerCase();
  if(/incorrect|invalide|introuvable|erreur|impossible|obligatoire|non autoris|refus/.test(t))el.classList.add('flash-error');
  else if(/déjà|attention|aucun|manquant|ne peut|avert/.test(t))el.classList.add('flash-warning');
  else el.classList.add('flash-success');
 }
 function scan(root){(root||document).querySelectorAll('form').forEach(prepareForm);(root||document).querySelectorAll('.flash').forEach(flashType)}
 document.addEventListener('DOMContentLoaded',function(){scan(document)});
 new MutationObserver(function(ms){ms.forEach(function(m){m.addedNodes.forEach(function(n){if(n.nodeType===1)scan(n)})})}).observe(document.documentElement,{childList:true,subtree:true});
})();
</script>'''

LOT9_STYLE='''<style id="mytree-lot9-style">
.flash{border-left:5px solid #2e7b47}.flash-success{background:#eef8f1;border-color:#2e7b47}.flash-warning{background:#fff8e5;border-color:#c58b13}.flash-error{background:#fff0f0;border-color:#b43b3b}.is-submitting{opacity:.68;cursor:wait!important}.notif-state{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.notif-help{font-size:13px;color:var(--muted);margin:8px 0 14px}
</style>'''

LOT10_STYLE='''<style id="mytree-lot10-mobile">
.mobile-menu-toggle{display:none}.mobile-connected-nav{display:none}
.table-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
img,video,canvas{max-width:100%}
@media(max-width:700px){
 body{overflow-x:hidden}
 header{position:sticky;top:0;z-index:1250;background:#fff;padding:9px 10px!important;gap:8px}
 .mobile-title-row{width:100%;display:flex;align-items:center;gap:8px}
 .mobile-title-row .mobile-back{display:none!important}
 .header-actions{width:100%;display:grid!important;grid-template-columns:1fr auto auto;gap:6px!important;align-items:center}
 .header-actions .context-switch{grid-column:1/-1;overflow-x:auto;flex-wrap:nowrap!important;padding-bottom:2px}
 .header-actions>b{display:none}
 .account-home,.account-logout{min-height:42px;display:flex;align-items:center;justify-content:center;padding:8px!important}
 .notif-bell{min-width:42px;min-height:42px;display:flex;align-items:center;justify-content:center}
 main{padding:10px!important;padding-bottom:82px!important;min-width:0}
 .layout{display:block!important;padding-bottom:0!important}
 aside.admin-nav,aside.vol-nav{display:none!important}
 .mobile-connected-nav{display:grid!important;grid-template-columns:repeat(5,1fr);position:fixed;left:0;right:0;bottom:0;z-index:1400;background:#102b1c;border-top:1px solid rgba(255,255,255,.18);padding:4px;gap:2px}
 .mobile-connected-nav a{color:#fff;text-decoration:none;text-align:center;font-size:10px;padding:5px 2px;border-radius:8px;min-width:0}
 .mobile-connected-nav a span{display:block;font-size:20px;line-height:22px}
 .mobile-connected-nav a.active{background:#2e7b47}
 .form{grid-template-columns:1fr!important}
 input,select,textarea,button,.btn,.action-btn{font-size:16px;min-height:44px}
 textarea{min-height:110px}
 .toolbar{display:grid!important;grid-template-columns:1fr!important}
 .toolbar label,.toolbar .btn{width:100%!important;min-width:0!important}
 .section-title{display:flex!important;flex-direction:column!important;align-items:stretch!important}
 .section-title .btn,.section-title .action-btn,.crud-actions,.crud-actions .btn,.crud-actions form{width:100%!important}
 .crud-actions{display:grid!important;grid-template-columns:1fr!important;gap:7px}
 .card{overflow-x:auto}
 table{min-width:680px}
 .real-map{height:58vh!important;min-height:360px}
 .map-picker{height:52vh!important;min-height:330px}
 .photo-actions{display:grid!important;grid-template-columns:1fr!important}
 .photo-actions .btn{width:100%}
 .member-picker{max-height:42vh}
 .filter-panel.open{inset:2vh 1.5vw 0!important}
 .filter-actions{left:1.5vw!important;right:1.5vw!important}
}
</style>'''

LOT12_MAPFIX_STYLE='''<style id="lot12-mapfix-style">
.map-filter-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.map-filter-drawer{display:none}
.map-filter-drawer.open{display:block}
.map-filter-drawer .map-filter-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;align-items:end}
.map-filter-drawer label{display:flex;flex-direction:column;gap:4px}
.map-filter-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.public-tree-marker,.tree-emoji-marker{background:transparent!important;border:0!important;font-size:28px;line-height:34px;text-align:center}
@media(max-width:700px){
 .map-filter-bar .btn{width:100%}
 .map-filter-drawer{position:fixed;z-index:1600;left:8px;right:8px;top:74px;bottom:78px;overflow:auto;background:#fff;border-radius:14px;padding:12px;box-shadow:0 12px 38px rgba(0,0,0,.25)}
 .map-filter-drawer .map-filter-grid{grid-template-columns:1fr}
 .map-filter-actions{position:sticky;bottom:0;background:#fff;padding-top:10px}
 .map-filter-actions .btn{flex:1;min-width:120px}
}
</style>'''

LOT12_UNIFIED_FILTER_STYLE='''<style id="mytree-unified-filter-style">
.unified-filter-launcher{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0 12px}
.unified-filter-launcher .filter-count{font-size:.9rem;opacity:.75}
.unified-filter-drawer{display:none!important}
.unified-filter-drawer.open{display:grid!important}
.unified-filter-close{display:none}
.unified-filter-actions{display:flex;gap:8px;flex-wrap:wrap;grid-column:1/-1}
.unified-filter-actions .btn{min-width:120px}
@media(max-width:700px){
 .unified-filter-launcher .btn{width:100%}
 .unified-filter-drawer.open{
   display:grid!important;position:fixed;z-index:1700;left:8px;right:8px;top:70px;bottom:76px;
   overflow:auto;background:#fff;border-radius:14px;padding:14px;box-shadow:0 12px 38px rgba(0,0,0,.28);
   grid-template-columns:1fr!important;align-content:start
 }
 .unified-filter-drawer.open .unified-filter-close{display:block;position:sticky;top:0;z-index:3;width:100%;margin-bottom:8px}
 .unified-filter-actions{position:sticky;bottom:0;background:#fff;padding-top:10px}
 .unified-filter-actions .btn{flex:1;min-width:0}
}
</style>'''
LOT12_UNIFIED_FILTER_SCRIPT='''<script id="mytree-unified-filter-script">
(function(){
 const filterNames=new Set([
  'wilaya_id','commune_id','association_id','owner_type','volunteer_id','project_id','zone_id',
  'species_id','sex','health_status','watering_status','approval_status','gps_status','q','quick',
  'status','priority','action_type','event_type','mission_type','date_from','date_to','type','role','active'
 ]);
 function clearUrl(form){
   const url=new URL(window.location.href);
   [...url.searchParams.keys()].forEach(k=>{ if(filterNames.has(k)) url.searchParams.delete(k); });
   window.location.href=url.pathname+(url.searchParams.toString()?'?'+url.searchParams.toString():'');
 }
 function enhance(form){
   if(!form || form.dataset.unifiedFilter==='1' || form.id==='mapFilters') return;
   const method=(form.getAttribute('method')||'get').toLowerCase();
   if(method!=='get') return;
   const controls=[...form.querySelectorAll('input[name],select[name]')];
   const filterControls=controls.filter(x=>filterNames.has(x.name));
   if(new Set(filterControls.map(x=>x.name)).size<2) return;

   form.dataset.unifiedFilter='1';
   form.classList.add('unified-filter-drawer');
   form.setAttribute('aria-hidden','true');

   const launch=document.createElement('div');
   launch.className='unified-filter-launcher noprint';
   const btn=document.createElement('button');
   btn.type='button'; btn.className='btn unified-filter-open'; btn.innerHTML='🔎 Filtrer';
   btn.setAttribute('aria-expanded','false');
   const count=document.createElement('span'); count.className='filter-count';

   function activeCount(){
     return filterControls.filter(x=>{
       if(x.type==='checkbox'||x.type==='radio') return x.checked;
       return String(x.value||'').trim()!=='';
     }).length;
   }
   function refresh(){
     const n=activeCount();
     count.textContent=n?n+' filtre(s) actif(s)':'Aucun filtre actif';
   }
   function setOpen(open){
     form.classList.toggle('open',open);
     form.setAttribute('aria-hidden',open?'false':'true');
     btn.setAttribute('aria-expanded',open?'true':'false');
     if(open) setTimeout(()=>close.focus(),0);
     else setTimeout(()=>btn.focus(),0);
   }

   btn.onclick=()=>setOpen(true);
   launch.append(btn,count);
   form.parentNode.insertBefore(launch,form);

   const close=document.createElement('button');
   close.type='button'; close.className='btn alt unified-filter-close'; close.textContent='Fermer';
   close.setAttribute('aria-label','Fermer les filtres');
   close.onclick=()=>setOpen(false);
   form.insertBefore(close,form.firstChild);

   let reset=[...form.querySelectorAll('a,button')].find(x=>{
      const t=(x.textContent||'').toLowerCase();
      return t.includes('réinitialiser')||t.includes('reinitialiser')||t.includes('reset');
   });
   if(!reset){
      reset=document.createElement('button');
      reset.type='button'; reset.className='btn alt'; reset.textContent='Réinitialiser';
      reset.onclick=()=>clearUrl(form);
      let actions=form.querySelector('.unified-filter-actions');
      if(!actions){
         actions=document.createElement('div');
         actions.className='unified-filter-actions';
         const submit=[...form.querySelectorAll('button[type=submit],input[type=submit],button:not([type])')].find(x=>x!==close);
         if(submit) submit.parentNode.insertBefore(actions,submit), actions.appendChild(submit);
         else form.appendChild(actions);
      }
      actions.appendChild(reset);
   }

   // Group existing action buttons so they remain at the bottom of the drawer.
   const candidates=[...form.querySelectorAll('button,a.btn,input[type=submit]')].filter(x=>x!==close && !x.closest('.unified-filter-actions'));
   if(candidates.length){
     let actions=form.querySelector('.unified-filter-actions');
     if(!actions){actions=document.createElement('div');actions.className='unified-filter-actions';form.appendChild(actions);}
     candidates.forEach(x=>actions.appendChild(x));
   }

   form.addEventListener('change',refresh);
   form.addEventListener('input',refresh);
   form.addEventListener('submit',()=>setOpen(false));
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&form.classList.contains('open')){e.preventDefault();setOpen(false);}});
   refresh();
 }
 function scan(root=document){
   root.querySelectorAll('form').forEach(enhance);
 }
 document.addEventListener('DOMContentLoaded',()=>scan());
 new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{
   if(n.nodeType===1){if(n.matches&&n.matches('form'))enhance(n);scan(n);}
 }))).observe(document.documentElement,{childList:true,subtree:true});
})();
</script>'''

FIXED3_STYLE='''<style id="fixed3-ui">.association-mobile-actions,.section-actions,.map-layer-choices{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.map-layer-choices label{min-height:44px;display:flex;align-items:center;gap:7px;padding:6px 10px}@media(max-width:700px){.association-mobile-actions .btn,.section-actions .btn{width:100%;min-height:48px;display:flex;align-items:center;justify-content:center}.map-layer-choices{display:grid;grid-template-columns:1fr}.map-layer-choices label{min-height:48px}}</style>'''

FIXED6_STYLE='''<style id="fixed6-ui">
.symbol-picker{display:grid;grid-template-columns:repeat(auto-fill,minmax(58px,1fr));gap:8px;margin-top:10px}
.symbol-choice input{position:absolute;opacity:0;pointer-events:none}
.symbol-choice span{display:flex;align-items:center;justify-content:center;min-height:52px;font-size:28px;border:1px solid #ccd8d0;border-radius:12px;cursor:pointer}
.symbol-choice input:checked+span{outline:3px solid currentColor;font-weight:700}
</style>'''

FIXED7_STYLE='''<style id="fixed7-profile-switch">
.active-profile-identity{display:flex;flex-direction:column;min-width:160px;padding:6px 10px;border-radius:10px;background:#eef6f0}
.active-profile-identity.association{background:#e8f4ec;border:1px solid #b8d8c2}
.active-profile-identity b{font-size:14px}.active-profile-identity small{font-size:11px;color:#5c6d62}
.association-profile-hero{display:flex;gap:14px;align-items:center;padding:18px;border-radius:16px;background:#eef7f1;margin-bottom:14px}
.association-avatar{font-size:42px;width:64px;height:64px;display:flex;align-items:center;justify-content:center;background:white;border-radius:50%}
@media(max-width:700px){.active-profile-identity{grid-column:1/-1;width:100%;box-sizing:border-box}.association-profile-hero{align-items:flex-start}.association-avatar{width:54px;height:54px;font-size:34px;flex:0 0 auto}}
</style>'''

def page(title,body,**ctx):
 content=render_template_string(body,tr=tr,lang=current_lang(),**ctx)
 if session.get('uid'):
  active=active_context()
  if active.get('type')=='association': nav=association_nav()
  elif is_admin(): nav=NAV_ADMIN
  else: nav=volunteer_nav()
  c=db(); unread=c.execute('SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0',(session['uid'],)).fetchone()['n']; c.close()
  bell=f'<a class="notif-bell" href="/notifications" title="Notifications">🔔<span>{unread}</span></a>' if unread else '<a class="notif-bell" href="/notifications" title="Notifications">🔔</a>'
  home_path=profile_home(); ref=request.referrer or ''; back_path=home_path
  if ref:
   try:
    from urllib.parse import urlparse
    rp=urlparse(ref); back_path=(rp.path + (('?'+rp.query) if rp.query else '')) if rp.path and rp.path!=request.path else home_path
   except Exception: back_path=home_path
  # Never send Retour back into action-entry forms after a completed/redirected operation.
  if any(x in back_path for x in ['/planting/new','/volunteer/donate','/donations/new','/watering/new']): back_path=home_path
  back_btn='' if request.path==home_path else '<a class="mobile-back" href="'+back_path+'">←</a>'
  ident=profile_identity()
  identity_html='<div class="active-profile-identity '+ident['type']+'"><b>'+ident['name']+'</b><small>'+ident['subtitle']+'</small></div>'
  tpl='<!doctype html><html lang="'+current_lang()+'" dir="'+current_dir()+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+tr(title)+'</title>'+STYLE+ALPHA3_STYLE+LOT9_STYLE+LOT10_STYLE+LOT11_STYLE+LOT12_MAPFIX_STYLE+LOT12_UNIFIED_FILTER_STYLE+FIXED3_STYLE+FIXED6_STYLE+FIXED7_STYLE+PHOTO_SCRIPT+SMART_NAV_SCRIPT+ACTION_UI_SCRIPT+UNIVERSAL_SEARCH_SCRIPT+DEPENDENT_SELECTS_SCRIPT+LOT9_UX_SCRIPT+i18n_script()+'<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script></head><body><header><div class="mobile-title-row">'+back_btn+'<div><b>'+tr(title)+'</b><div class="sub">🌳 MyTree 🇩🇿 — '+APP_VERSION+'</div></div></div><div class="header-actions">'+language_switcher()+identity_html+bell+' <a class="account-home" href="'+home_path+'">🏠 '+tr('Mon accueil')+'</a> <a class="account-logout" href="/logout">↪ '+tr('Déconnexion')+'</a></div></header><div class="layout">'+nav+'<main>{% for cat,m in get_flashed_messages(with_categories=true) %}<div class="flash flash-{{cat}}">{{m}}</div>{% endfor %}{{content|safe}}</main></div>'+connected_mobile_nav()+LOT12_UNIFIED_FILTER_SCRIPT+'</body></html>'
  return render_template_string(tpl,content=content)
 return render_template_string('<!doctype html><html lang="'+current_lang()+'" dir="'+current_dir()+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+STYLE+LOT9_STYLE+LOT10_STYLE+LOT11_STYLE+LOT12_MAPFIX_STYLE+LOT12_UNIFIED_FILTER_STYLE+UNIVERSAL_SEARCH_SCRIPT+DEPENDENT_SELECTS_SCRIPT+LOT9_UX_SCRIPT+i18n_script()+'</head><body><main style="max-width:680px;margin:28px auto;padding:0 14px">'+language_switcher()+'{{content|safe}}</main>'+LOT12_UNIFIED_FILTER_SCRIPT+'</body></html>',content=content)

def filters_from_request():
 # Alpha 4 Lot 6 — contrat de filtres commun à tous les écrans métier.
 keys=['wilaya_id','commune_id','association_id','owner_type','volunteer_id','project_id','zone_id','species_id','sex','health_status','watering_status','approval_status','gps_status','q','quick','status','priority','action_type','date_from','date_to']
 f={k:clean(request.args.get(k,'')) for k in keys}
 # Compatibilité avec les anciens écrans : event_type/mission_type deviennent action_type.
 if not f['action_type']:
  f['action_type']=clean(request.args.get('event_type') or request.args.get('mission_type') or '')
 return f

def accessible_filter_projects(c,ctx=None):
 ctx=ctx or active_context(c)
 # Réutilise la politique de visibilité Lot 5 : association propriétaire + collaborations acceptées/can_view.
 return accessible_map_projects(c,ctx)

def common_filter_options(c,f=None):
 f=f or filters_from_request(); ctx=active_context(c)
 projects=list(accessible_filter_projects(c,ctx)); project_ids=[int(x['id']) for x in projects]
 if f.get('wilaya_id'):
  projects=[x for x in projects if str(x['wilaya_id'] or '')==str(f['wilaya_id'])]
 if f.get('commune_id'):
  projects=[x for x in projects if str(x['commune_id'] or '')==str(f['commune_id'])]
 project_ids=[int(x['id']) for x in projects]
 zones=[]
 if project_ids:
  marks=','.join('?'*len(project_ids)); args=list(project_ids); q=f'SELECT * FROM zones WHERE active=1 AND project_id IN ({marks})'
  if f.get('project_id'): q+=' AND project_id=?'; args.append(f['project_id'])
  q+=' ORDER BY name'; zones=c.execute(q,args).fetchall()
 communes_q='SELECT * FROM communes WHERE active=1'; communes_args=[]
 if f.get('wilaya_id'): communes_q+=' AND wilaya_id=?'; communes_args.append(f['wilaya_id'])
 communes_q+=' ORDER BY name'
 if ctx.get('type')=='association' and ctx.get('association_id'):
  volunteers=c.execute("SELECT u.id,u.name FROM association_memberships am JOIN users u ON u.id=am.user_id WHERE am.association_id=? AND am.status='approved' AND u.active=1 ORDER BY u.name",(ctx['association_id'],)).fetchall()
 elif ctx.get('type')=='global' and is_super_admin(): volunteers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 else: volunteers=c.execute('SELECT id,name FROM users WHERE id=?',(session.get('uid'),)).fetchall()
 return dict(
  wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(),
  communes=c.execute(communes_q,communes_args).fetchall(),projects=projects,zones=zones,
  species=c.execute('SELECT * FROM species WHERE active=1 ORDER BY name_fr').fetchall(),volunteers=volunteers,
  associations=approved_associations(c,session.get('uid')) if session.get('uid') else []
 )

def validate_common_filters(c,f):
 """Reject forged cross-association IDs instead of silently returning foreign rows."""
 ctx=active_context(c); allowed_projects={int(x['id']) for x in accessible_filter_projects(c,ctx)}
 if f.get('association_id'):
  if ctx.get('type')=='association' and int(f['association_id'])!=int(ctx.get('association_id') or 0): return False,'association_id'
  if ctx.get('type')=='personal': return False,'association_id'
 if f.get('project_id'):
  try: pid=int(f['project_id'])
  except ValueError: return False,'project_id'
  if pid not in allowed_projects: return False,'project_id'
 if f.get('zone_id'):
  try: zid=int(f['zone_id'])
  except ValueError: return False,'zone_id'
  z=c.execute('SELECT id,project_id FROM zones WHERE id=? AND active=1',(zid,)).fetchone()
  if not z or int(z['project_id']) not in allowed_projects: return False,'zone_id'
  if f.get('project_id') and int(z['project_id'])!=int(f['project_id']): return False,'zone_id'
 if f.get('volunteer_id'):
  try: uid=int(f['volunteer_id'])
  except ValueError: return False,'volunteer_id'
  if ctx.get('type')=='association' and not c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(ctx['association_id'],uid)).fetchone(): return False,'volunteer_id'
  if ctx.get('type')=='personal' and uid!=int(session.get('uid') or 0): return False,'volunteer_id'
 return True,None

def common_filter_guard(c,f):
 ok,bad=validate_common_filters(c,f)
 if ok: return None
 try: audit_permission_denied('filter.forbidden',bad or 'filter',None,current_association_id(),'Filtre non autorisé: '+str(f.get(bad,'')))
 except Exception: pass
 return (jsonify({'error':'forbidden_filter','filter':bad}),403) if request.path.startswith('/api/') else ('Filtre non autorisé pour le contexte actif.',403)

def apply_common_geo_filters(w,p,f,project_alias='p'):
 if f.get('wilaya_id'): w.append(f'{project_alias}.wilaya_id=?'); p.append(f['wilaya_id'])
 if f.get('commune_id'): w.append(f'{project_alias}.commune_id=?'); p.append(f['commune_id'])
 return w,p

def tree_where(f):
 # Lot 6 : visibilité pilotée par le contexte + projets collaboratifs accessibles.
 w=['t.active=1']; p=[]; ctx=active_context()
 if ctx.get('type')=='personal': w+=['t.association_id IS NULL','t.planted_by_user_id=?']; p.append(session.get('uid'))
 elif ctx.get('type')=='association' and ctx.get('association_id'):
  c=db(); ids=[int(x['id']) for x in accessible_filter_projects(c,ctx)]; c.close()
  if ids:
   marks=','.join('?'*len(ids)); w.append(f'(t.association_id=? OR t.project_id IN ({marks}))'); p.append(ctx['association_id']); p.extend(ids)
  else: w.append('t.association_id=?'); p.append(ctx['association_id'])
 elif not is_super_admin(): w.append('1=0')
 mapping={'project_id':'t.project_id','zone_id':'t.zone_id','species_id':'t.species_id','health_status':'t.health_status','watering_status':'t.watering_status','approval_status':'t.approval_status','volunteer_id':'t.planted_by_user_id'}
 for k,col in mapping.items():
  if f.get(k): w.append(col+'=?'); p.append(f[k])
 if f.get('wilaya_id'): w.append('COALESCE(t.wilaya_id,z.wilaya_id,p.wilaya_id)=?'); p.append(f['wilaya_id'])
 if f.get('commune_id'): w.append('COALESCE(t.commune_id,z.commune_id,p.commune_id)=?'); p.append(f['commune_id'])
 if f.get('owner_type')=='individual': w.append('t.association_id IS NULL')
 if f.get('owner_type')=='association': w.append('t.association_id IS NOT NULL')
 if f.get('quick')=='mine': w.append('t.planted_by_user_id=?'); p.append(session.get('uid'))
 if f.get('quick')=='watering': w.append("t.watering_status IN ('À arroser','Urgent')")
 if f.get('gps_status')=='missing': w.append('(t.latitude IS NULL OR t.longitude IS NULL)')
 if f.get('gps_status')=='mapped': w.append('(t.latitude IS NOT NULL AND t.longitude IS NOT NULL)')
 if f.get('gps_status')=='verify': w.append("COALESCE(t.gps_review_status,'ok')='to_verify'")
 if f.get('date_from'): w.append("date(COALESCE(t.planted_at,t.created_at))>=date(?)"); p.append(f['date_from'])
 if f.get('date_to'): w.append("date(COALESCE(t.planted_at,t.created_at))<=date(?)"); p.append(f['date_to'])
 if f.get('q'): w.append('(t.tree_code LIKE ? OR s.name_fr LIKE ? OR u.name LIKE ? OR a.name LIKE ?)'); p += ['%'+f['q']+'%']*4
 return ' AND '.join(w),p

def filter_options(c):
 # Compatibilité historique : tous les formulaires existants bénéficient désormais des options Lot 6.
 return common_filter_options(c,filters_from_request())

@app.route('/login',methods=['GET','POST'])
def login():
 login_type=clean(request.values.get('account_type')) or 'personal'
 if login_type not in ('personal','association'): login_type='personal'
 if request.method=='POST':
  login_value=clean(request.form.get('login')); password=request.form.get('password',''); c=db()
  if login_type=='association':
   acc=c.execute("SELECT aa.*,a.name association_name,a.status association_status FROM association_accounts aa JOIN associations a ON a.id=aa.association_id WHERE lower(aa.login_id)=lower(?) AND aa.active=1 AND a.status='active'",(login_value,)).fetchone()
   success=bool(acc and check_password_hash(acc['password_hash'],password))
   if success:
    session.clear(); session.permanent=request.form.get('remember')=='1'; session.update(account_type='association',association_account_id=acc['id'],association_id=acc['association_id'],name=acc['association_name'],role='association_account',lang=current_lang())
    c.execute('UPDATE association_accounts SET last_login=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),acc['id'])); c.commit(); c.close(); return redirect('/association/dashboard')
   c.close(); flash('ID Association ou mot de passe incorrect.')
  else:
   u=c.execute('SELECT u.*,r.name role_name FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.phone=? AND u.active=1',(login_value,)).fetchone(); success=bool(u and check_password_hash(u['password_hash'],password))
   c.execute('INSERT INTO login_history(user_id,login_value,success,ip_address,created_at) VALUES(?,?,?,?,?)',(u['id'] if u else None,login_value,1 if success else 0,request.headers.get('X-Forwarded-For',request.remote_addr),datetime.now().isoformat(timespec='seconds')))
   if success:
    saved_lang=u['preferred_language'] if 'preferred_language' in u.keys() and u['preferred_language'] in SUPPORTED_LANGS else current_lang(); session.clear(); session.permanent=request.form.get('remember')=='1'; session.update(uid=u['id'],account_type='personal',name=u['name'] or user_display_name(u['first_name'],u['last_name']),role=u['role_name'] or u['role'] or 'volunteer',lang=saved_lang); c.execute('UPDATE users SET last_login=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),u['id'])); c.commit(); c.close(); target=request.form.get('next') or request.args.get('next'); return redirect(target if target and target.startswith('/') else ('/' if is_admin() else '/volunteer'))
   c.commit(); c.close(); flash('Numéro de téléphone ou mot de passe incorrect.')
 return page('Connexion',r'''<div class="card login-card"><div style="text-align:center;margin-bottom:18px"><div style="font-size:44px">🌳 🇩🇿</div><h2>Connexion MyTree</h2><p class="sub">Choisissez votre type de compte.</p></div><div class="action-set" style="margin-bottom:16px"><a class="btn {{'alt' if login_type!='personal' else ''}}" href="/login?account_type=personal">👤 Personnel / Bénévole</a><a class="btn {{'alt' if login_type!='association' else ''}}" href="/login?account_type=association">🏛 Association</a></div><form method="post"><input type="hidden" name="account_type" value="{{login_type}}"><label>{{'ID Association' if login_type=='association' else 'Numéro de téléphone'}}<input name="login" autocomplete="username" required></label><label style="display:block;margin-top:14px">Mot de passe<input type="password" name="password" autocomplete="current-password" required></label><input type="hidden" name="next" value="{{request.args.get('next','')}}"><p><label style="display:flex;align-items:center;gap:8px"><input type="checkbox" name="remember" value="1" style="width:auto"> Se souvenir de moi pendant 30 jours</label></p><div class="login-actions"><button class="btn">🔐 Se connecter</button>{% if login_type=='personal' %}<a class="btn alt" href="/public/register">👤 Créer un compte personnel</a><a class="btn alt" href="/forgot-password">🔑 Mot de passe oublié ?</a>{% endif %}<a class="btn alt" href="/public">← Retour</a></div></form></div>''',login_type=login_type)

@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
 if request.method=='POST':
  identifier=clean(request.form.get('identifier')); method=clean(request.form.get('method')) or 'sms'; c=db()
  u=c.execute('SELECT id,phone,email FROM users WHERE active=1 AND (phone=? OR lower(email)=lower(?))',(identifier,identifier)).fetchone()
  if u:
   destination=clean(u['email'] if method=='email' else u['phone'])
   if not destination:
    flash('Ce mode de récupération n’est pas disponible pour ce compte.'); c.close(); return redirect('/forgot-password')
   code=f"{secrets.randbelow(1000000):06d}"; now=datetime.now(); exp=(now+timedelta(minutes=10)).isoformat(timespec='seconds')
   c.execute('UPDATE password_reset_codes SET used=1 WHERE user_id=? AND used=0',(u['id'],)); c.execute('INSERT INTO password_reset_codes(user_id,phone,code_hash,expires_at,used,created_at) VALUES(?,?,?,?,0,?)',(u['id'],destination,generate_password_hash(code),exp,now.isoformat(timespec='seconds'))); c.commit()
   sent=False
   if method=='sms':
    webhook=os.environ.get('MYTREE_SMS_WEBHOOK','').strip()
    if webhook:
     try:
      data=json.dumps({'phone':destination,'message':f'MyTree - code de réinitialisation : {code} (valable 10 minutes)'}).encode('utf-8'); req=urllib.request.Request(webhook,data=data,headers={'Content-Type':'application/json'},method='POST'); urllib.request.urlopen(req,timeout=10).read(); sent=True
     except Exception: pass
    if sent: flash('Un code SMS a été envoyé.')
    else: flash('Le fournisseur SMS n’est pas encore configuré ou est indisponible.')
   else:
    host=os.environ.get('MYTREE_SMTP_HOST','').strip(); user=os.environ.get('MYTREE_SMTP_USER','').strip(); password=os.environ.get('MYTREE_SMTP_PASSWORD',''); sender=os.environ.get('MYTREE_EMAIL_FROM',user).strip(); port=int(os.environ.get('MYTREE_SMTP_PORT','587'))
    if host and sender:
     try:
      msg=EmailMessage(); msg['Subject']='MyTree - Réinitialisation du mot de passe'; msg['From']=sender; msg['To']=destination; msg.set_content(f'Votre code MyTree est : {code}\nCe code est valable 10 minutes.')
      with smtplib.SMTP(host,port,timeout=10) as smtp:
       smtp.starttls()
       if user: smtp.login(user,password)
       smtp.send_message(msg)
      sent=True
     except Exception: pass
    if sent: flash('Un code a été envoyé par e-mail.')
    else: flash('Le service e-mail n’est pas encore configuré ou est indisponible.')
   c.close()
   if sent: return redirect('/reset-password?destination='+urllib.parse.quote(destination))
  else: flash('Si ce compte existe, les instructions de réinitialisation seront envoyées.')
  c.close()
 return page('Mot de passe oublié',"""<div class='card login-card'><h2>Mot de passe oublié ?</h2><p class='sub'>Saisissez votre téléphone ou e-mail, puis choisissez comment recevoir le code.</p><form method='post'><label>Téléphone ou e-mail<input name='identifier' required></label><label style='display:block;margin-top:14px'>Recevoir le code par<select name='method'><option value='sms'>SMS</option><option value='email'>E-mail</option></select></label><div class='login-actions'><button class='btn'>Envoyer le code</button><a class='btn alt' href='/login'>Retour</a></div></form></div>""")

@app.route('/reset-password',methods=['GET','POST'])
def reset_password():
 destination=clean(request.values.get('destination') or request.values.get('phone'))
 if request.method=='POST':
  code=clean(request.form.get('code')); password=request.form.get('password',''); confirm=request.form.get('password_confirm',''); c=db(); row=c.execute("SELECT * FROM password_reset_codes WHERE phone=? AND used=0 ORDER BY id DESC LIMIT 1",(destination,)).fetchone(); u=c.execute('SELECT id FROM users WHERE id=? AND active=1',(row['user_id'],)).fetchone() if row else None
  if not u or not row or row['expires_at']<datetime.now().isoformat(timespec='seconds') or not check_password_hash(row['code_hash'],code): flash('Code invalide ou expiré.')
  elif len(password)<6: flash('Le mot de passe doit contenir au moins 6 caractères.')
  elif password!=confirm: flash('Les mots de passe ne correspondent pas.')
  else:
   c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(password),u['id'])); c.execute('UPDATE password_reset_codes SET used=1 WHERE id=?',(row['id'],)); c.commit(); c.close(); flash('Mot de passe réinitialisé.'); return redirect('/login')
  c.close()
 return page('Nouveau mot de passe',"""<div class='card login-card'><form method='post'><input type='hidden' name='destination' value='{{destination}}'><label>Code reçu<input name='code' inputmode='numeric' maxlength='6' required></label><label>Nouveau mot de passe<input type='password' name='password' minlength='6' required></label><label>Confirmer le mot de passe<input type='password' name='password_confirm' minlength='6' required></label><div class='login-actions'><button class='btn'>Enregistrer</button><a class='btn alt' href='/login'>Annuler</a></div></form></div>""",destination=destination)

@app.route('/public/events')
def public_events():
 c=db(); rows=c.execute("SELECT e.*,p.name project_name,z.name zone_name FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id WHERE e.active=1 ORDER BY e.start_at DESC").fetchall(); c.close()
 return public_page('Événements',"""<section class='public-section'><h1>Événements et actions terrain</h1><p class='sub'>Plantations, arrosages, formations et rencontres de l’association.</p><div class='species-grid'>{% for e in rows %}<article class='species-card'><div class='sub'>{{e.event_type}} • {{e.status}}</div><h3>{{e.title}}</h3><p><b>{{e.start_at or 'Date à confirmer'}}</b></p><p>{{e.location or e.zone_name or 'Lieu à confirmer'}}</p><p>{{e.description or ''}}</p><a class='btn' href='/public/action/event'>Participer</a></article>{% else %}<div class='card'>Aucun événement enregistré.</div>{% endfor %}</div></section>""",rows=rows)

@app.route('/public/map')
def public_map():
 c=db(); rows=c.execute("SELECT t.id,t.tree_code,t.latitude,t.longitude,t.health_status,s.name_fr,p.name project_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.active=1 AND t.approval_status='approved' AND t.latitude IS NOT NULL AND t.longitude IS NOT NULL").fetchall(); c.close()
 data=[dict(id=r['id'],code=r['tree_code'],lat=r['latitude'],lon=r['longitude'],health=r['health_status'],species=r['name_fr'],project=r['project_name']) for r in rows]; target=clean(request.args.get('tree',''))
 return public_page('Carte publique',"""<section class='public-section'><h1>Carte publique des arbres</h1><p class='sub'>Consultation et itinéraire accessibles sans compte.</p><div id='publicMap' class='real-map'></div></section><script>(function(){const trees={{data|tojson}},target={{target|tojson}};const m=L.map('publicMap').setView([35.70,-0.64],11);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(m);const ic=L.divIcon({className:'tree-emoji-marker public-tree-marker',html:'<span aria-label="Arbre">🌳</span>',iconSize:[34,34],iconAnchor:[17,29]});const pts=[];let selected=null;const esc=v=>String(v||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));trees.forEach(t=>{pts.push([t.lat,t.lon]);const route='https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(t.lat+','+t.lon),html='<b>🌳 '+esc(t.species||'Arbre')+'</b><br>'+esc(t.code)+'<br>'+esc(t.project)+'<br><a href="/public/tree/'+t.id+'">Voir la fiche</a><br><a target="_blank" rel="noopener" href="'+route+'">📍 Itinéraire</a>';const mk=L.marker([t.lat,t.lon],{icon:ic}).addTo(m).bindPopup(html);if(target&&(String(t.id)===target||String(t.code).toLowerCase()===String(target).toLowerCase()))selected={t,mk}});if(selected){m.setView([selected.t.lat,selected.t.lon],17);selected.mk.openPopup()}else if(pts.length)m.fitBounds(pts,{padding:[30,30],maxZoom:16})})();</script>""",data=data,target=target)

@app.route('/public/action/<action>')
def public_action(action):
 actions={
  'plant':('Planter un arbre','Enregistrez une nouvelle plantation et suivez sa validation.','/planting/new','🌱'),
  'water':('Arroser un arbre','Enregistrez rapidement un arrosage depuis votre téléphone.','/volunteer/watering','💧'),
  'donate':('Faire un don','Déclarez un don en argent, arbres, matériel, eau ou service.','/volunteer/donate','🎁'),
  'event':('Participer à un événement','Consultez les événements et inscrivez-vous à une action.','/volunteer/events','📆'),
  'member':('Devenir adhérent','Accédez à la demande d’adhésion de l’association.','/members/new','❤️'),
  'scan':('Scanner un QR Code','Scannez le QR d’un arbre pour consulter ou enregistrer une action.','/volunteer/scan','▣'),
  'volunteer':('Devenir bénévole','Créez votre compte pour participer aux plantations, arrosages et activités.','/volunteer','🙋')
 }
 item=actions.get(action)
 if not item:return ('Action inconnue',404)
 title,description,target,icon=item
 if session.get('uid'):return redirect(target if not is_admin() else ('/donations/new' if action=='donate' else target))
 return public_page(title,"""<section class='public-section'><div class='card' style='max-width:720px;margin:auto;text-align:center'><div style='font-size:64px'>{{icon}}</div><h1>{{action_title}}</h1><p>{{description}}</p><p class='mobile-note'>Pour continuer, créez un compte ou connectez-vous. Après l’authentification, MyTree vous ramènera automatiquement vers cette action.</p><div class='vertical-actions' style='max-width:420px;margin:20px auto'><a class='vertical-action' href='/public/register?next={{target}}&cancel=/public/action/{{action_code}}'><span class='icon'>👤</span>Créer un compte</a><a class='vertical-action secondary-action' href='/login?next={{target}}&cancel=/public/action/{{action_code}}'><span class='icon'>🔐</span>Se connecter</a><a class='btn alt' href='/public'>Annuler</a></div></div></section>""",action_title=title,description=description,target=target,icon=icon,action_code=action)

@app.route('/public/help')
def public_help():
 return public_page('Je veux aider',"""<section class='public-section'><div class='public-hero'><h1>Comment souhaitez-vous aider ?</h1><p>Chaque participation compte, sur le terrain ou à distance.</p></div><div class='public-actions' style='margin-top:18px'><a class='public-action' href='/public/action/plant'><span class='icon'>🌱</span><span>Planter</span></a><a class='public-action' href='/public/action/water'><span class='icon'>💧</span><span>Arroser</span></a><a class='public-action' href='/public/action/donate'><span class='icon'>💶</span><span>Faire un don</span></a><a class='public-action' href='/public/action/donate'><span class='icon'>🧰</span><span>Donner du matériel</span></a><a class='public-action' href='/public/action/volunteer'><span class='icon'>🙋</span><span>Devenir bénévole</span></a><a class='public-action' href='/public/action/member'><span class='icon'>❤️</span><span>Devenir adhérent</span></a></div></section>""")

@app.route('/volunteer/field')
@login_required
def volunteer_field_mode():
 if is_admin(): return redirect('/')
 c=db(); uid=session['uid']; urgent=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='approved' AND (planted_by_user_id=? OR zone_id IN (SELECT zone_id FROM assignments WHERE user_id=? AND active=1)) AND watering_status='Urgent'",(uid,uid)).fetchone()['n']; nearby=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='approved' AND (planted_by_user_id=? OR zone_id IN (SELECT zone_id FROM assignments WHERE user_id=? AND active=1))",(uid,uid)).fetchone()['n']; c.close()
 return page('Mode Terrain',"""<div class='field-hero'><div class='sub' style='color:#d6e9dc'>Interface simplifiée</div><h2>🚜 Mode Terrain</h2><p>Actions essentielles, grands boutons et accès rapide depuis le téléphone.</p><div><b>{{urgent}}</b> arrosage(s) urgent(s) • <b>{{nearby}}</b> arbre(s) dans votre périmètre</div></div><div class='field-actions'><a class='field-action' href='/planting/new'><span>🌱</span>Planter</a><a class='field-action' href='/volunteer/watering'><span>💧</span>Arroser</a><a class='field-action' href='/volunteer/scan'><span>▣</span>Scanner QR</a><a class='field-action' href='/map'><span>🗺</span>Carte</a><a class='field-action' href='/volunteer/trees?priority=1'><span>📍</span>Arbres prioritaires</a><a class='field-action' href='/notifications'><span>🔔</span>Alertes</a></div><p class='mobile-note'>Le GPS et la caméra sont utilisés uniquement lorsque vous lancez une action correspondante.</p>""",urgent=urgent,nearby=nearby)

@app.route('/register',methods=['GET','POST'])
def register():
 c=db(); opts=filter_options(c); values=user_form_values(request.form)
 if request.method=='POST':
  password=request.form.get('password',''); errors=validate_user_form(c,values,password_required=True,password=password);
  if password!=request.form.get('password_confirm',''): errors.append('Les mots de passe ne correspondent pas.')
  if not errors:
   role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']; name=user_display_name(values['first_name'],values['last_name'])
   try:
    cur=c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,birth_date,address,skills,availability,photo_url,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(values['first_name'],values['last_name'],name,values['sex'],values['phone'],values['email'],values['phone'],generate_password_hash(password),role,'volunteer',1,values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],datetime.now().isoformat(timespec='minutes'))); c.commit(); uid=cur.lastrowid; c.close(); log_action('self_register','user',uid); flash('Compte créé. Vous pouvez vous connecter immédiatement.'); return redirect('/login')
   except sqlite3.IntegrityError: errors=['Ce téléphone, cet e-mail ou ce nom d’utilisateur est déjà utilisé.']
  for error in errors: flash(error)
 c.close(); return page('Inscription bénévole','''<div class="card"><h2>Nouveau bénévole</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{request.form.get('first_name','')}}" required></label><label>Nom<input name="last_name" value="{{request.form.get('last_name','')}}" required></label><label>Sexe<select name="sex"><option {% if request.form.get('sex')=='Homme' %}selected{% endif %}>Homme</option><option {% if request.form.get('sex')=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone','')}}" required></label><label>Email facultatif<input type="email" name="email" value="{{request.form.get('email','')}}"></label><label>Mot de passe<input type="password" name="password" minlength="6" autocomplete="new-password" required></label><label>Confirmer le mot de passe<input type="password" name="password_confirm" minlength="6" autocomplete="new-password" required></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% for x in wilayas %}<option value="{{x.id}}" {% if request.form.get('wilaya_id')|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% for x in communes %}<option value="{{x.id}}" {% if request.form.get('commune_id')|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{request.form.get('address','')}}"></label><div class="full"><button class="btn">Créer mon compte</button> <a class="btn alt" href="/login">Annuler</a></div></form></div>''',**opts)

@app.route('/logout')
def logout():
 target=request.args.get('next') or '/public'; session.clear(); return redirect(target if target.startswith('/') else '/public')

@app.route('/')
def dashboard():
 if not session.get('uid'): return redirect('/public')
 if not is_admin(): return redirect('/volunteer')
 f=filters_from_request(); c=db(); where,params=tree_where(f); opts=filter_options(c)
 base=' FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE '+where
 total=c.execute('SELECT COUNT(*) n'+base,params).fetchone()['n']; watering=c.execute('SELECT COUNT(*) n'+base+' AND t.watering_status IN (\'À arroser\',\'Urgent\')',params).fetchone()['n']; alerts=c.execute('SELECT COUNT(*) n'+base+' AND t.health_status IN (\'À surveiller\',\'En danger\',\'Mort\')',params).fetchone()['n']; pending=c.execute('SELECT COUNT(*) n'+base+" AND t.approval_status='pending'",params).fetchone()['n']
 vw=['u.active=1']; vp=[]
 if f['wilaya_id']:vw.append('u.wilaya_id=?');vp.append(f['wilaya_id'])
 if f['commune_id']:vw.append('u.commune_id=?');vp.append(f['commune_id'])
 vwhere=' AND '.join(vw); vols=c.execute('SELECT COUNT(*) n FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE '+vwhere+" AND COALESCE(r.name,u.role)='volunteer'",vp).fetchone()['n']; men=c.execute('SELECT COUNT(*) n FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE '+vwhere+" AND COALESCE(r.name,u.role)='volunteer' AND u.sex='Homme'",vp).fetchone()['n']; women=c.execute('SELECT COUNT(*) n FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE '+vwhere+" AND COALESCE(r.name,u.role)='volunteer' AND u.sex='Femme'",vp).fetchone()['n']
 recent=c.execute('SELECT t.*,s.name_fr species_name,z.name zone_name,u.name volunteer_name'+base+' ORDER BY t.id DESC LIMIT 8',params).fetchall()
 ms,mp=context_condition('missions'); ts,tp=context_condition('trees'); mission_planned=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='Planifiée' AND "+ms,mp).fetchone()['n']; mission_active=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='En cours' AND "+ms,mp).fetchone()['n']; mission_done=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='Terminée' AND "+ms,mp).fetchone()['n']; overdue=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status NOT IN ('Terminée','Annulée') AND end_at IS NOT NULL AND end_at < ? AND "+ms,[datetime.now().isoformat(timespec='minutes')]+mp).fetchone()['n']; approved_today=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='approved' AND substr(approved_at,1,10)=? AND "+ts,[date.today().isoformat()]+tp).fetchone()['n']; rejected=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='rejected' AND "+ts,tp).fetchone()['n']; new_volunteers=c.execute("SELECT COUNT(*) n FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE COALESCE(r.name,u.role)='volunteer' AND u.active=1 AND datetime(u.created_at)>=datetime('now','-7 days')").fetchone()['n']; unread=c.execute('SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0',(session['uid'],)).fetchone()['n']; c.close()
 qs='&'.join(k+'='+str(v) for k,v in f.items() if v)
 return page('Tableau de bord','''<div class="admin-home-blocks">
<div class="admin-home-block"><h3>🌳 Terrain</h3><div class="admin-home-links"><a href="/trees">🌳 Arbres</a><a href="/plantings/pending">🌱 Plantations</a><a href="/watering">💧 Arrosages</a><a href="/map">🗺 Carte</a><a href="/volunteer/gps-quick">📍 GPS rapide</a><a href="/qr">▣ QR Code</a></div></div>
<div class="admin-home-block"><h3>📂 Organisation</h3><div class="admin-home-links"><a href="/admin/associations">🏛 Associations</a><a href="/projects">📁 Projets</a><a href="/zones">📍 Zones</a><a href="/teams">👥 Équipes</a><a href="/missions">🎯 Missions</a><a href="/operations">🗓 Planifications</a><a href="/events">📆 Événements</a></div></div>
<div class="admin-home-block"><h3>👥 Personnes</h3><div class="admin-home-links"><a href="/volunteers">🙋 Bénévoles</a><a href="/members">🪪 Adhérents</a><a href="/users">🔐 Utilisateurs</a><a href="/roles">🛡 Droits d’accès</a></div></div>
<div class="admin-home-block"><h3>💰 Gestion</h3><div class="admin-home-links"><a href="/cash">💰 Caisse centrale</a><a href="/donations">🎁 Dons</a><a href="/members">🤝 Cotisations</a><a href="/stock">📦 Stock unique</a></div></div>
<div class="admin-home-block"><h3>📊 Administration</h3><div class="admin-home-links"><a href="/association-requests">📨 Demandes d’associations</a><a href="/action-center">✅ Centre d’actions</a><a href="/notifications">🔔 Notifications</a><a href="/reports/operations">📊 Rapports</a><a href="/activity">🕘 Journal</a><a href="/backup">💾 Sauvegarde</a><a href="/species">🍃 Espèces</a></div></div></div><script>document.querySelectorAll('.admin-home-block h3').forEach(h=>h.addEventListener('click',()=>{if(innerWidth>700)return;const b=h.parentElement;document.querySelectorAll('.admin-home-block').forEach(x=>{if(x!==b)x.classList.remove('open')});b.classList.toggle('open')}));</script><div style='display:none'>
</div><form class="card toolbar" method="get">{% include 'filters' ignore missing %}<label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id" id="eventProject"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id" id="eventZone"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/">Effacer</a></form>
 <div class="grid kpis"><a class="card kpi" href="/trees?{{qs}}"><small>Arbres</small><b>{{total}}</b></a><a class="card kpi" href="/trees?watering_status=À+arroser&{{qs}}"><small>À arroser</small><b>{{watering}}</b></a><a class="card kpi" href="/trees?health_status=À+surveiller&{{qs}}"><small>Alertes santé</small><b>{{alerts}}</b></a><a class="card kpi" href="/plantings/pending"><small>Plantations en attente</small><b>{{pending}}</b></a><a class="card kpi" href="/volunteers"><small>Bénévoles</small><b>{{vols}}</b><span class="sub">{{men}} hommes • {{women}} femmes</span></a></div>
 <div class="grid kpis"><a class="card kpi" href="/trees?approval_status=approved"><small>Validées aujourd’hui</small><b>{{approved_today}}</b></a><a class="card kpi" href="/trees?approval_status=rejected"><small>Plantations refusées</small><b>{{rejected}}</b></a><a class="card kpi" href="/volunteers"><small>Nouveaux bénévoles (7 j)</small><b>{{new_volunteers}}</b></a><a class="card kpi" href="/missions"><small>Missions en retard</small><b>{{overdue}}</b></a><a class="card kpi" href="/notifications"><small>Notifications non lues</small><b>{{unread}}</b></a></div>
 <div class="grid two"><div class="card"><div class="section-title"><h3>Derniers arbres</h3><a href="/trees">Voir tout</a></div><table><tr><th>Code</th><th>Espèce</th><th>Zone</th><th>Bénévole</th><th>Statut</th></tr>{% for t in recent %}<tr><td>{{t.tree_code or 'Génération après validation'}}</td><td>{{t.species_name or t.species}}</td><td>{{t.zone_name}}</td><td>{{t.volunteer_name or t.planted_by}}</td><td><span class="badge {% if t.approval_status=='pending' %}pending{% else %}good{% endif %}">{{t.approval_status}}</span></td></tr>{% endfor %}</table></div><div class="card"><h3>Répartition bénévoles</h3><p><b>{{men}}</b> hommes</p><p><b>{{women}}</b> femmes</p><p><b>{{vols}}</b> total</p></div></div>''',f=f,qs=qs,total=total,watering=watering,alerts=alerts,pending=pending,vols=vols,men=men,women=women,recent=recent,mission_planned=mission_planned,mission_active=mission_active,mission_done=mission_done,overdue=overdue,approved_today=approved_today,rejected=rejected,new_volunteers=new_volunteers,unread=unread,**opts)

@app.route('/trees')
@login_required
def trees():
 f=filters_from_request(); c=db(); guard=common_filter_guard(c,f)
 if guard: c.close(); return guard
 where,params=tree_where(f); opts=common_filter_options(c,f)
 rows=c.execute('''SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name,u.name volunteer_name,c.name commune_name,w.name wilaya_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN communes c ON c.id=p.commune_id LEFT JOIN wilayas w ON w.id=p.wilaya_id WHERE '''+where+' ORDER BY t.id DESC',params).fetchall(); c.close()
 return page('Arbres','''<div class="section-title"><div><h2>Liste des arbres</h2><p class="sub">Filtrez les arbres sans GPS puis lancez le positionnement rapide.</p></div><div class="action-set"><a class="action-btn action-primary" href="/planting/new">＋ Nouvel arbre</a><a class="action-btn action-map" href="/trees?gps_status=missing">📍 Sans GPS</a><a class="action-btn action-view" href="/volunteer/gps-quick">⚡ Position GPS rapide</a></div></div><form class="card toolbar"><label>Recherche<input name="q" value="{{f.q}}"></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><label>Position carte<select name="gps_status"><option value="">Toutes</option><option value="mapped" {% if f.gps_status=='mapped' %}selected{% endif %}>Avec GPS</option><option value="missing" {% if f.gps_status=='missing' %}selected{% endif %}>Sans GPS</option><option value="verify" {% if f.gps_status=='verify' %}selected{% endif %}>À vérifier</option></select></label><label>Santé<select name="health_status"><option value="">Toutes</option>{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if f.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Arrosage<select name="watering_status"><option value="">Tous</option>{% for x in ['À jour','À arroser','Urgent'] %}<option {% if f.watering_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Bénévole<select name="volunteer_id"><option value="">Tous</option>{% for x in volunteers %}<option value="{{x.id}}" {% if f.volunteer_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Du<input type="date" name="date_from" value="{{f.date_from}}"></label><label>Au<input type="date" name="date_to" value="{{f.date_to}}"></label><button class="btn">Filtrer</button><a class="btn alt" href="/trees">Effacer</a></form><div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Espèce</th><th>Wilaya / Commune</th><th>Projet / Zone</th><th>Bénévole</th><th>GPS</th><th>Santé</th><th>Arrosage</th><th>Validation</th><th>Actions</th></tr>{% for t in rows %}<tr data-nav-key="tree-{{t.id}}"><td>{{t.tree_code or 'En attente'}}</td><td>{{t.species_name or t.species}}</td><td>{{t.wilaya_name}} / {{t.commune_name}}</td><td>{{t.project_name}} / {{t.zone_name}}</td><td>{{t.volunteer_name or t.planted_by}}</td><td>{% if t.latitude is not none and t.longitude is not none %}<span class="badge good">Positionné</span>{% else %}<span class="badge danger">Sans GPS</span>{% endif %}</td><td>{{t.health_status}}</td><td>{{t.watering_status}}</td><td>{{t.approval_status}}</td><td><div class="action-set"><a class="action-btn action-view" href="/tree/{{t.id}}">👁 Fiche</a><a class="action-btn action-map" href="/trees/{{t.id}}/map">🗺 Carte</a><a class="action-btn action-edit" href="/trees/{{t.id}}/edit">✏ Modifier</a>{% if admin %}<form method="post" action="/trees/{{t.id}}/delete" onsubmit="return confirm('Supprimer ou archiver cet arbre ?')"><button class="action-btn action-delete">🗑 Supprimer</button></form>{% endif %}</div></td></tr>{% else %}<tr><td colspan="10">Aucun arbre correspondant.</td></tr>{% endfor %}</table></div>''',rows=rows,f=f,admin=is_admin(),**opts)

@app.post('/trees/<int:tid>/delete')
@login_required
def tree_delete(tid):
 if not is_admin():return redirect('/trees')
 c=db(); tree=c.execute('SELECT id,tree_code FROM trees WHERE id=? AND active=1',(tid,)).fetchone()
 if not tree:c.close();flash('Arbre introuvable.');return redirect('/trees')
 history=sum(c.execute(f'SELECT COUNT(*) n FROM {table} WHERE tree_id=?',(tid,)).fetchone()['n'] for table in ['watering_logs','tree_photos','tree_observations','interventions','tree_change_requests','tree_gps_history'])
 if history:
  c.execute('UPDATE trees SET active=0 WHERE id=?',(tid,)); message='Arbre archivé afin de conserver son historique.'; action='archive'
 else:
  c.execute('DELETE FROM trees WHERE id=?',(tid,)); message='Arbre supprimé.'; action='delete'
 c.commit();c.close();log_action(action,'tree',tid,tree['tree_code'] or '');flash(message);return redirect(request.form.get('return_to') or '/trees')

@app.route('/planting/new',methods=['GET','POST'])
@login_required
def planting_new():
 c=db(); opts=filter_options(c); prefs=get_preferences(c,session['uid'])
 if request.method=='POST':
  wilaya_id=request.form.get('wilaya_id') or None; commune_id=request.form.get('commune_id') or None
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None
  errors=[]
  if not wilaya_id: errors.append('La wilaya est obligatoire.')
  if not commune_id: errors.append('La commune est obligatoire.')
  if commune_id and wilaya_id and not c.execute('SELECT 1 FROM communes WHERE id=? AND wilaya_id=?',(commune_id,wilaya_id)).fetchone(): errors.append('La commune ne correspond pas à la wilaya sélectionnée.')
  if zone_id:
   z=c.execute('SELECT project_id,wilaya_id,commune_id FROM zones WHERE id=? AND active=1',(zone_id,)).fetchone()
   if not z: errors.append('La zone sélectionnée est invalide.')
   elif project_id and str(z['project_id'])!=str(project_id): errors.append('La zone ne correspond pas au projet sélectionné.')
  if project_id:
   ok_assign,msg_assign,p0,z0=validate_tree_assignment(c,project_id,zone_id)
   if not ok_assign: errors.append(msg_assign)
   elif p0:
    # A project/zone assignment always carries the project's geography.
    wilaya_id=p0['wilaya_id']; commune_id=p0['commune_id']
    if current_association_id() and p0['association_id'] and int(current_association_id())!=int(p0['association_id']):
     can_partner=collaboration_access(c,project_id,current_association_id(),'can_add_tree')
     if not can_partner: errors.append('Cette association partenaire n’est pas autorisée à ajouter des arbres à ce projet.')
  if errors:
   for e in errors: flash(e)
  else:
   ctx=active_context(c); assoc_id=ctx.get('association_id') if ctx.get('type')=='association' else None
   # Une plantation associative saisie par un bénévole reste en attente. Le Super Admin
   # et les administrateurs de CETTE association partagent une seule décision finale.
   pending=(not is_super_admin()) and not (assoc_id and c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(assoc_id,session['uid'])).fetchone())
   status='pending' if pending else 'approved'; now=datetime.now().isoformat(timespec='minutes'); species=c.execute('SELECT name_fr FROM species WHERE id=?',(request.form['species_id'],)).fetchone()
   cur=c.execute('''INSERT INTO trees(species_id,species,project_id,zone_id,wilaya_id,commune_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,gps_accuracy,health_status,watering_status,approval_status,approved_by_user_id,approved_at,planting_type,notes,active,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(request.form['species_id'],species['name_fr'] if species else None,project_id,zone_id,wilaya_id,commune_id,request.form.get('planted_at') or date.today().isoformat(),session['uid'],session['name'],request.form.get('latitude') or None,request.form.get('longitude') or None,request.form.get('gps_accuracy') or None,'Bon','À jour',status,session['uid'] if is_admin() else None,now if is_admin() else None,'free' if not project_id else ('outside_zone' if not zone_id else 'simple'),request.form.get('notes'),1,now,assoc_id)); tid=cur.lastrowid
   stock_source=(request.form.get('stock_source') if is_admin() else 'personal') or 'personal'; c.execute('UPDATE trees SET stock_source=? WHERE id=?',(stock_source,tid))
   if request.form.get('photo_url'): c.execute('INSERT INTO tree_photos(tree_id,photo_url,caption,created_by_user_id,created_at) VALUES(?,?,?,?,?)',(tid,request.form.get('photo_url'),'Photo de plantation',session['uid'],now))
   if status=='approved':
    code=f'TREE-{tid:06d}'; c.execute('UPDATE trees SET tree_code=?,qr_code=? WHERE id=?',(code,'MYTREE:'+code,tid))
    ok,msg=deduct_tree_from_nursery(c,tid)
    if not ok: c.rollback(); c.close(); flash(msg); return redirect('/planting/new')
   else:
    c.execute('UPDATE trees SET qr_code=? WHERE id=?',(f'MYTREE:PENDING:{tid}',tid))
    reviewers={x['id'] for x in c.execute("SELECT u.id FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND COALESCE(r.name,u.role)='super_admin'").fetchall()}
    if assoc_id:
     reviewers.update(x['user_id'] for x in c.execute("SELECT user_id FROM association_memberships WHERE association_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(assoc_id,)).fetchall())
    for reviewer_id in reviewers:
     c.execute('INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)',(reviewer_id,'Nouvelle plantation à valider',f'Plantation #{tid} créée par {session.get("name")}.',f'/tree/{tid}','Plantation','tree',tid,now))
   save_preferences(c,session['uid'],{'wilaya_id':wilaya_id,'commune_id':commune_id,'project_id':project_id,'zone_id':zone_id,'species_id':request.form.get('species_id'),'team_id':request.form.get('team_id')})
   c.commit(); c.close(); log_action('create','tree',tid,status); flash('Plantation enregistrée.'+(' Elle attend la validation administrative.' if pending else '')); return redirect('/tree/'+str(tid))
 selected={k:request.form.get(k,prefs.get(k,'')) for k in ['wilaya_id','commune_id','project_id','zone_id','species_id']}
 c.close(); return page('Nouvelle plantation','''<div class="card"><div class="mobile-note">Vous pouvez enregistrer un arbre hors projet et hors zone, puis l’affecter plus tard.</div><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Wilaya<select name="wilaya_id" required><option value="">Choisir</option>{% for x in wilayas %}<option value="{{x.id}}" {% if selected.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id" required><option value="">Choisir</option>{% for x in communes %}<option value="{{x.id}}" {% if selected.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>{% if is_admin_user %}<label>Projet<select name="project_id"><option value="">Hors projet</option>{% for x in projects %}<option value="{{x.id}}" {% if selected.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Hors zone</option>{% for x in zones %}<option value="{{x.id}}" {% if selected.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>{% else %}<input type="hidden" name="project_id" value="{{selected.project_id}}"><input type="hidden" name="zone_id" value="{{selected.zone_id}}"><div class="full mobile-note">Projet et zone masqués pour simplifier la saisie. L'arbre sera classé plus tard par un responsable.</div>{% endif %}<label>Rechercher une espèce<input type="search" id="speciesSearch" placeholder="Français, arabe, anglais ou nom scientifique" oninput="filterSpecies(this.value)"></label><label>Espèce<select id="speciesSelect" name="species_id" required>{% for x in species %}<option value="{{x.id}}" {% if selected.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}} — {{x.name_ar or ''}} — {{x.name_en or ''}}</option>{% endfor %}</select></label><label>Date<input type="date" name="planted_at" value="{{today}}"></label><label>Latitude<input id="lat" name="latitude" readonly></label><label>Longitude<input id="lon" name="longitude" readonly></label><input type="hidden" id="acc" name="gps_accuracy"><div class="full"><button type="button" class="btn alt" onclick="gps()">📡 Ma position actuelle</button> <button type="button" class="btn" onclick="openPicker()">🗺 Choisir sur la carte</button> <span id="gpsmsg" class="sub"></span></div><div class="full" id="pickerWrap" style="display:none"><div id="pickerMap" class="map-picker"></div><p class="sub">Touchez la carte ou déplacez le marqueur pour corriger précisément l’emplacement.</p></div>{{photo|safe}}{% if is_admin_user %}<label class="full">Origine des arbres<select name="stock_source"><option value="personal">Arbres personnels / apportés directement (aucun mouvement de stock)</option><option value="association">Stock de l’association (déduire automatiquement)</option></select></label>{% else %}<div class="full mobile-note">Les plantations déclarées par un bénévole sont considérées comme ses propres arbres et ne diminuent pas le stock de l’association.</div>{% endif %}<label class="full">Notes<textarea name="notes"></textarea></label><div class="full"><button class="btn" type="submit" name="save" value="1">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div><script>let pickerMap,pickerMarker;function setPoint(a,b){lat.value=Number(a).toFixed(7);lon.value=Number(b).toFixed(7)}function openPicker(){pickerWrap.style.display='block';if(!pickerMap){let a=parseFloat(lat.value)||35.70,b=parseFloat(lon.value)||-0.64;pickerMap=L.map('pickerMap').setView([a,b],13);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(pickerMap);pickerMarker=L.marker([a,b],{draggable:true}).addTo(pickerMap);pickerMarker.on('dragend',e=>{let q=e.target.getLatLng();setPoint(q.lat,q.lng)});pickerMap.on('click',e=>{pickerMarker.setLatLng(e.latlng);setPoint(e.latlng.lat,e.latlng.lng)})}setTimeout(()=>pickerMap.invalidateSize(),100)}function gps(){let m=document.getElementById('gpsmsg');if(!navigator.geolocation){m.textContent='GPS non disponible';return}m.textContent='Localisation…';navigator.geolocation.getCurrentPosition(p=>{setPoint(p.coords.latitude,p.coords.longitude);acc.value=p.coords.accuracy.toFixed(1);m.textContent='Position récupérée, précision '+p.coords.accuracy.toFixed(0)+' m'},e=>m.textContent='Autorisation GPS refusée ou position indisponible',{enableHighAccuracy:true,timeout:15000})}function norm(x){return (x||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')}function filterSpecies(q){q=norm(q);let first=null;for(const o of speciesSelect.options){const ok=!q||norm(o.text).includes(q);o.hidden=!ok;if(ok&&!first)first=o}if(first&&q){speciesSelect.value=first.value}}document.getElementById('speciesSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();speciesSelect.focus()}}); </script>''',today=date.today().isoformat(),selected=selected,photo=photo_fields(prefix='planting'),cancel_url='/volunteer' if not is_admin() else '/trees',is_admin_user=is_admin(),**opts)

@app.route('/plantings/pending')
@login_required
def pending_plantings():
 c=db(); rows=c.execute("SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name,u.name volunteer_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE t.active=1 AND t.approval_status='pending' ORDER BY t.id DESC").fetchall(); c.close(); return page('Plantations à valider','''<div class="card"><table><tr><th>Bénévole</th><th>Espèce</th><th>Projet</th><th>Zone</th><th>Date</th><th>GPS</th><th>Actions</th></tr>{% for t in rows %}<tr><td>{{t.volunteer_name}}</td><td>{{t.species_name}}</td><td>{{t.project_name}}</td><td>{{t.zone_name}}</td><td>{{t.planted_at}}</td><td>{{t.latitude}}, {{t.longitude}}</td><td><a class="btn alt" href="/tree/{{t.id}}">Fiche</a> <a class="btn alt" href="/trees/{{t.id}}/map">Carte</a> {% if admin %}<form method="post" action="/plantings/{{t.id}}/approve" style="display:inline"><button class="btn">Accepter</button></form> <form method="post" action="/plantings/{{t.id}}/reject" style="display:inline"><input name="reason" placeholder="Motif obligatoire" required style="width:150px;display:inline"><button class="btn red">Refuser</button></form>{% else %}<span class="sub">Réservé à l’administration</span>{% endif %}</td></tr>{% endfor %}</table></div>''',rows=rows,admin=is_admin())

def deduct_tree_from_nursery(c,tid):
 t=c.execute('SELECT * FROM trees WHERE id=?',(tid,)).fetchone()
 if not t or t['stock_source']!='association' or int(t['stock_deducted'] or 0)==1:return True,None
 st=c.execute("SELECT * FROM nursery_stock WHERE species_id=? ORDER BY (quantity_available-quantity_reserved) DESC,id LIMIT 1",(t['species_id'],)).fetchone()
 if not st or (st['quantity_available']-st['quantity_reserved'])<1:return False,'Stock insuffisant pour cette espèce.'
 now=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE nursery_stock SET quantity_available=quantity_available-1,quantity_planted=quantity_planted+1,updated_at=? WHERE id=?',(now,st['id'])); c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(st['id'],'Plantation',1,'Arbre #'+str(tid),session['uid'],now)); c.execute('UPDATE trees SET stock_deducted=1 WHERE id=?',(tid,)); return True,None

@app.post('/plantings/<int:tid>/approve')
@login_required
def approve(tid):
 c=db(); t=c.execute("SELECT * FROM trees WHERE id=?",(tid,)).fetchone()
 if not t or t['approval_status']!='pending': c.close(); flash('Cette plantation a déjà été traitée.'); return redirect('/tree/'+str(tid))
 assoc_id=t['association_id']; reviewer_role=None
 if is_super_admin(): reviewer_role='super_admin'
 elif assoc_id and c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(assoc_id,session['uid'])).fetchone(): reviewer_role='association_admin'
 if not reviewer_role: c.close(); flash('Vous n’êtes pas autorisé à valider cette plantation.'); return redirect('/tree/'+str(tid))
 ok,msg=deduct_tree_from_nursery(c,tid)
 if not ok: c.close(); flash(msg); return redirect('/tree/'+str(tid))
 code=f'TREE-{tid:06d}'; now=datetime.now().isoformat(timespec='minutes')
 c.execute("UPDATE trees SET approval_status='approved',tree_code=?,qr_code=?,approved_by_user_id=?,approved_at=?,rejection_reason=NULL,reviewed_by_role=?,reviewed_by_association_id=? WHERE id=?",(code,'MYTREE:'+code,session['uid'],now,reviewer_role,assoc_id if reviewer_role=='association_admin' else None,tid))
 c.execute("INSERT INTO planting_reviews(tree_id,reviewer_user_id,decision,reason,created_at) VALUES(?,?,'approved',NULL,?)",(tid,session['uid'],now))
 c.execute("UPDATE notifications SET is_read=1,decision='approved',decided_at=? WHERE action_type='tree' AND action_id=? AND is_read=0",(now,tid))
 if t['planted_by_user_id']: c.execute('INSERT INTO notifications(user_id,title,message,link,is_read,created_at) VALUES(?,?,?,?,0,?)',(t['planted_by_user_id'],'Plantation acceptée',f'Votre plantation {code} a été acceptée.',f'/tree/{tid}',now))
 c.commit(); c.close(); log_action('approve','tree',tid,reviewer_role); flash('Plantation acceptée.'); return redirect('/tree/'+str(tid))

@app.post('/plantings/<int:tid>/reject')
@login_required
def reject(tid):
 c=db(); t=c.execute("SELECT * FROM trees WHERE id=?",(tid,)).fetchone()
 if not t or t['approval_status']!='pending': c.close(); flash('Cette plantation a déjà été traitée.'); return redirect('/tree/'+str(tid))
 assoc_id=t['association_id']; reviewer_role=None
 if is_super_admin(): reviewer_role='super_admin'
 elif assoc_id and c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(assoc_id,session['uid'])).fetchone(): reviewer_role='association_admin'
 if not reviewer_role: c.close(); flash('Vous n’êtes pas autorisé à refuser cette plantation.'); return redirect('/tree/'+str(tid))
 now=datetime.now().isoformat(timespec='minutes'); reason=clean(request.form.get('reason'))
 if not reason: c.close(); flash('Le motif du refus est obligatoire.'); return redirect('/tree/'+str(tid))
 c.execute("UPDATE trees SET approval_status='rejected',rejection_reason=?,approved_by_user_id=?,approved_at=?,reviewed_by_role=?,reviewed_by_association_id=? WHERE id=?",(reason,session['uid'],now,reviewer_role,assoc_id if reviewer_role=='association_admin' else None,tid))
 c.execute("INSERT INTO planting_reviews(tree_id,reviewer_user_id,decision,reason,created_at) VALUES(?,?,'rejected',?,?)",(tid,session['uid'],reason,now))
 c.execute("UPDATE notifications SET is_read=1,decision='rejected',decided_at=? WHERE action_type='tree' AND action_id=? AND is_read=0",(now,tid))
 if t['planted_by_user_id']: c.execute('INSERT INTO notifications(user_id,title,message,link,is_read,created_at) VALUES(?,?,?,?,0,?)',(t['planted_by_user_id'],'Plantation refusée',reason,f'/tree/{tid}',now))
 c.commit(); c.close(); log_action('reject','tree',tid,reviewer_role+' · '+reason); flash('Plantation refusée.'); return redirect('/tree/'+str(tid))

@app.route('/trees/<int:tid>/edit',methods=['GET','POST'])
@login_required
def tree_edit(tid):
 c=db(); opts=filter_options(c); t=c.execute('SELECT * FROM trees WHERE id=?',(tid,)).fetchone()
 if not t: c.close(); return redirect('/trees')
 if request.method=='POST':
  new_project=request.form.get('project_id') or None; new_zone=request.form.get('zone_id') or None
  if new_project:
   ok_assign,msg_assign,p0,z0=validate_tree_assignment(c,new_project,new_zone,tid)
   if not ok_assign: flash(msg_assign); c.close(); return redirect('/trees/'+str(tid)+'/edit')
  else: p0=z0=None
  changes={'species_id':request.form['species_id'],'project_id':new_project,'zone_id':new_zone,'health_status':request.form['health_status'],'watering_status':request.form['watering_status'],'latitude':request.form.get('latitude') or None,'longitude':request.form.get('longitude') or None,'notes':request.form.get('notes')}
  if is_admin() or t['approval_status']!='approved':
   c.execute('UPDATE trees SET species_id=?,project_id=?,zone_id=?,wilaya_id=?,commune_id=?,association_id=?,health_status=?,watering_status=?,latitude=?,longitude=?,notes=? WHERE id=?',(changes['species_id'],changes['project_id'],changes['zone_id'],p0['wilaya_id'] if p0 else t['wilaya_id'],p0['commune_id'] if p0 else t['commune_id'],p0['association_id'] if p0 else t['association_id'],changes['health_status'],changes['watering_status'],changes['latitude'],changes['longitude'],changes['notes'],tid)); c.commit(); c.close(); log_action('edit','tree',tid); flash('Fiche arbre modifiée avec cohérence Projet → Zone → localisation.'); return redirect('/tree/'+str(tid))
  if t['planted_by_user_id']!=session.get('uid'):
   c.close(); flash('Vous ne pouvez proposer une correction que pour vos propres arbres.'); return redirect('/tree/'+str(tid))
  now=datetime.now().isoformat(timespec='minutes'); reason=clean(request.form.get('change_reason')) or 'Correction demandée par le bénévole'; c.execute("INSERT INTO tree_change_requests(tree_id,requested_by_user_id,changes_json,reason,status,created_at) VALUES(?,?,?,?,'pending',?)",(tid,session['uid'],json.dumps(changes,ensure_ascii=False),reason,now)); rid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; admins=c.execute("SELECT u.id FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND COALESCE(r.name,u.role) IN ('super_admin','admin')").fetchall();
  for a in admins: c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(a['id'],'Correction d’arbre à valider',f'Demande #{rid} pour l’arbre {t["tree_code"] or tid}.','/tree-change-requests','Plantation',now))
  c.commit(); c.close(); flash('Votre correction a été envoyée à l’administrateur.'); return redirect('/tree/'+str(tid))
 c.close(); return page('Modifier un arbre','''<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Espèce<select name="species_id">{% for x in species %}<option value="{{x.id}}" {% if t.species_id==x.id %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><label>Projet<select name="project_id">{% for x in projects %}<option value="{{x.id}}" {% if t.project_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id">{% for x in zones %}<option value="{{x.id}}" {% if t.zone_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Santé<select name="health_status">{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if t.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Arrosage<select name="watering_status">{% for x in ['À jour','À arroser','Urgent'] %}<option {% if t.watering_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Latitude<input name="latitude" value="{{t.latitude or ''}}"></label><label>Longitude<input name="longitude" value="{{t.longitude or ''}}"></label><label class="full">Notes<textarea name="notes">{{t.notes or ''}}</textarea></label>{% if not admin and t.approval_status=='approved' %}<label class="full">Motif de la correction<textarea name="change_reason" required></textarea><span class="sub">L’arbre validé ne sera pas changé avant acceptation administrative.</span></label>{% endif %}<div class="full"><a class="btn alt" href="/trees/{{t.id}}/gps">📍 Choisir la position sur la carte / utiliser ma position</a></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/tree/{{t.id}}">Annuler</a></div></form></div>''',t=t,admin=is_admin(),**opts)

@app.route('/watering',methods=['GET','POST'])
@login_required
def watering():
 prefill=''; tree_id=request.args.get('tree_id')
 if tree_id:
  c0=db(); tr=c0.execute("SELECT tree_code FROM trees WHERE id=? AND active=1 AND approval_status='approved'",(tree_id,)).fetchone(); c0.close(); prefill=tr['tree_code'] if tr else ''
 if request.method=='POST':
  c=db(); scan=clean(request.form.get('scan')); result=c.execute("SELECT * FROM trees WHERE active=1 AND approval_status='approved' AND (qr_code=? OR tree_code=?)",(scan,scan)).fetchone()
  if result:
   now=datetime.now().isoformat(timespec='minutes'); liters=request.form.get('quantity_liters') or None
   c.execute('INSERT INTO watering_logs(tree_id,watered_at,user_id,volunteer,quantity_range,quantity_liters,source,notes,latitude,longitude,photo_url,tree_condition,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(result['id'],now,session['uid'],session['name'],request.form.get('quantity_range'),liters,request.form.get('source'),request.form.get('notes'),request.form.get('latitude') or None,request.form.get('longitude') or None,request.form.get('photo_url') or None,request.form.get('tree_condition') or None,now))
   c.execute("UPDATE trees SET last_watered_at=?,watering_status='À jour',health_status=? WHERE id=?",(now,request.form.get('tree_condition') or result['health_status'],result['id']))
   c.commit(); c.close(); log_action('water','tree',result['id'],str(liters or request.form.get('quantity_range'))); flash('Arrosage terminé. Merci pour l’arrosage 🌳💧'); return redirect('/tree/'+str(result['id']))
  c.close(); flash('Arbre approuvé introuvable.')
 return page('Arrosage rapide',"""<div class="section-title"><h2>Arrosage terrain</h2><div><a class="btn alt" href="/watering/needs">Arbres à arroser</a> <a class="btn alt" href="/watering/history">Historique</a></div></div><div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label class="full">QR ou code arbre<input name="scan" value="{{prefill}}" autofocus required></label><label>Quantité<select name="quantity_range"><option>1–5 L</option><option>5–10 L</option><option>10–15 L</option><option>15–25 L</option></select></label><label>Litres exacts<input type="number" min="0" step="0.1" name="quantity_liters"></label><label>Source<select name="source"><option>Bidon</option><option>Camion</option><option>Réservoir</option><option>Goutte-à-goutte</option><option>Autre</option></select></label><label>État observé<select name="tree_condition"><option>Bon</option><option>À surveiller</option><option>En danger</option><option>Mort</option></select></label><label>Photo facultative (URL)<input type="url" name="photo_url"></label><label class="full">Observation<textarea name="notes"></textarea></label><input type="hidden" name="latitude" id="lat"><input type="hidden" name="longitude" id="lon"><div class="full"><span id="gpsWater" class="sub">Position GPS facultative.</span></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{home_url}}">Annuler</a></div></form></div><script>if(navigator.geolocation){navigator.geolocation.getCurrentPosition(p=>{lat.value=p.coords.latitude;lon.value=p.coords.longitude;gpsWater.textContent='Position GPS ajoutée.'},()=>gpsWater.textContent='Arrosage possible sans GPS.',{enableHighAccuracy:true,timeout:8000})}</script>""",prefill=prefill,home_url=('/' if is_admin() else '/volunteer'))

@app.route('/watering/history')
@login_required
def watering_history():
 c=db(); q=clean(request.args.get('q')); where='1=1'; params=[]
 if q: where='(t.tree_code LIKE ? OR s.name_fr LIKE ? OR u.name LIKE ?)'; params=['%'+q+'%']*3
 rows=c.execute("SELECT wl.*,t.tree_code,s.name_fr species_name,u.name user_name FROM watering_logs wl LEFT JOIN trees t ON t.id=wl.tree_id LEFT JOIN species s ON s.id=t.species_id LEFT JOIN users u ON u.id=wl.user_id WHERE "+where+" ORDER BY wl.id DESC LIMIT 300",params).fetchall(); total=c.execute('SELECT COUNT(*) n,COALESCE(SUM(quantity_liters),0) liters FROM watering_logs').fetchone(); c.close()
 return page('Historique des arrosages',"""<div class="section-title"><h2>Historique des arrosages</h2><a class="btn" href="/watering">+ Nouvel arrosage</a></div><div class="grid two"><div class="card kpi"><small>Total</small><b>{{total.n}}</b></div><div class="card kpi"><small>Eau comptabilisée</small><b>{{'%.1f'|format(total.liters)}} L</b></div></div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}"></label><button class="btn">Rechercher</button></form><div class="card"><table><tr><th>Date</th><th>Arbre</th><th>Espèce</th><th>Bénévole</th><th>Quantité</th><th>Source</th><th>État</th></tr>{% for x in rows %}<tr><td>{{x.watered_at}}</td><td><a href="/tree/{{x.tree_id}}">{{x.tree_code}}</a></td><td>{{x.species_name}}</td><td>{{x.user_name or x.volunteer}}</td><td>{{x.quantity_liters|string+' L' if x.quantity_liters is not none else x.quantity_range}}</td><td>{{x.source or '—'}}</td><td>{{x.tree_condition or '—'}}</td></tr>{% else %}<tr><td colspan="7">Aucun arrosage.</td></tr>{% endfor %}</table></div>""",rows=rows,total=total,q=q)

@app.route('/watering/needs')
@login_required
def watering_needs():
 c=db(); rows=c.execute("SELECT t.id,t.tree_code,t.last_watered_at,t.watering_status,t.health_status,s.name_fr species_name,s.watering_frequency_days,p.name project_name,z.name zone_name,CAST(julianday('now')-julianday(COALESCE(t.last_watered_at,t.planted_at,t.created_at)) AS INTEGER) days_since FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.active=1 AND t.approval_status='approved' ORDER BY days_since DESC").fetchall(); c.close(); items=[]
 for r in rows:
  d=dict(r); freq=d.get('watering_frequency_days') or 7; days=d.get('days_since') or 0; d['due']=days>=freq or d.get('watering_status') in ('À arroser','Urgent'); d['overdue']=max(0,days-freq); items.append(d)
 return page('Plan d’arrosage',"""<div class="section-title"><h2>Planification des arrosages</h2><a class="btn" href="/watering">Arrosage rapide</a></div><div class="card"><table><tr><th>Priorité</th><th>Arbre</th><th>Espèce</th><th>Projet / Zone</th><th>Dernier arrosage</th><th>Fréquence</th><th>Retard</th><th></th></tr>{% for x in items if x.due %}<tr><td><span class="badge {% if x.health_status=='En danger' or x.watering_status=='Urgent' %}danger{% else %}pending{% endif %}">{{'Urgent' if x.health_status=='En danger' or x.watering_status=='Urgent' else 'À arroser'}}</span></td><td><a href="/tree/{{x.id}}">{{x.tree_code}}</a></td><td>{{x.species_name}}</td><td>{{x.project_name}} / {{x.zone_name}}</td><td>{{x.last_watered_at or 'Jamais'}}</td><td>{{x.watering_frequency_days or 7}} jours</td><td>{{x.overdue}} jours</td><td><a class="btn alt" href="/watering?tree_id={{x.id}}">Arroser</a></td></tr>{% else %}<tr><td colspan="8">Tous les arbres sont à jour.</td></tr>{% endfor %}</table></div>""",items=items)

@app.route('/volunteers')
@login_required
def volunteers():
 f=filters_from_request(); include_inactive=request.args.get('inactive')=='1'; c=db(); us,up=context_user_condition('u'); w=["(r.name='volunteer' OR (r.name IS NULL AND u.role='volunteer'))",us];p=list(up)
 if not include_inactive:w.append('u.active=1')
 for k,col in [('sex','u.sex'),('wilaya_id','u.wilaya_id'),('commune_id','u.commune_id')]:
  if f[k]:w.append(col+'=?');p.append(f[k])
 if f['q']:w.append('(u.name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?)');p += ['%'+f['q']+'%']*3
 rows=c.execute('''SELECT u.*,w.name wilaya_name,c.name commune_name,r.label role_label,
 (SELECT COUNT(*) FROM trees t WHERE t.planted_by_user_id=u.id AND t.active=1) planting_count,
 (SELECT COUNT(*) FROM watering_logs wl WHERE wl.user_id=u.id) watering_count,
 (SELECT COUNT(*) FROM mission_participants mp WHERE mp.user_id=u.id) mission_count
 FROM users u LEFT JOIN roles r ON r.id=u.role_id LEFT JOIN wilayas w ON w.id=u.wilaya_id LEFT JOIN communes c ON c.id=u.commune_id WHERE '''+' AND '.join(w)+' ORDER BY u.active DESC,u.name',p).fetchall(); men=sum(1 for x in rows if x['sex']=='Homme'); women=sum(1 for x in rows if x['sex']=='Femme'); opts=filter_options(c); c.close()
 return page('Bénévoles','''<div class="section-title"><h2>Gestion des bénévoles</h2>{% if admin %}<a class="btn" href="/volunteers/new">+ Nouveau bénévole</a>{% endif %}</div><div class="grid kpis" style="grid-template-columns:repeat(3,1fr)"><div class="card kpi"><small>Total affiché</small><b>{{rows|length}}</b></div><div class="card kpi"><small>Hommes</small><b>{{men}}</b></div><div class="card kpi"><small>Femmes</small><b>{{women}}</b></div></div><form class="card toolbar"><label>Recherche<input name="q" value="{{f.q}}" placeholder="Nom, téléphone, e-mail"></label><label>Sexe<select name="sex"><option value="">Tous</option><option {% if f.sex=='Homme' %}selected{% endif %}>Homme</option><option {% if f.sex=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>{% if admin %}<label>Comptes<select name="inactive"><option value="0">Actifs</option><option value="1" {% if include_inactive %}selected{% endif %}>Actifs et inactifs</option></select></label>{% endif %}<button class="btn">Filtrer</button><a class="btn alt" href="/volunteers">Annuler</a></form><div class="card"><table><tr><th>Nom</th><th>État</th><th>Téléphone</th><th>Localisation</th><th>Plantations</th><th>Arrosages</th><th>Missions</th><th>Action</th></tr>{% for u in rows %}<tr><td><a href="/volunteers/{{u.id}}"><b>{{u.name}}</b></a><div class="sub">{{u.sex}} • {{u.email or 'sans e-mail'}}</div></td><td><span class="badge {% if u.active %}good{% else %}danger{% endif %}">{{'Actif' if u.active else 'Inactif'}}</span></td><td>{{u.phone}}</td><td>{{u.wilaya_name or '—'}} / {{u.commune_name or '—'}}</td><td>{{u.planting_count}}</td><td>{{u.watering_count}}</td><td>{{u.mission_count}}</td><td>{% if admin %}<a class="btn alt" href="/volunteers/{{u.id}}/edit">Modifier</a> <form method="post" action="/volunteers/{{u.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou désactiver ce bénévole ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="8">Aucun bénévole trouvé.</td></tr>{% endfor %}</table></div><div class="mobile-only">{% for u in rows %}<div class="card"><b>{{u.name}}</b><p class="sub">{{u.phone}} • {{'Actif' if u.active else 'Inactif'}}</p><div class="vertical-actions"><a class="vertical-action" href="/volunteers/{{u.id}}"><span class="icon">👁</span>Ouvrir la fiche</a>{% if admin %}<a class="vertical-action secondary-action" href="/volunteers/{{u.id}}/edit"><span class="icon">✏️</span>Modifier</a><form method="post" action="/volunteers/{{u.id}}/delete" onsubmit="return confirm('Supprimer ou désactiver ce bénévole ?')"><button class="vertical-action danger-zone" style="color:var(--red)"><span class="icon">🗑️</span>Supprimer / désactiver</button></form>{% endif %}</div></div>{% endfor %}</div>''',rows=rows,men=men,women=women,f=f,include_inactive=include_inactive,admin=is_admin(),**opts)

@app.route('/volunteers/new',methods=['GET','POST'])
@login_required
def volunteer_new():
 if not is_admin(): return redirect('/volunteers')
 c=db(); opts=filter_options(c); values=user_form_values(request.form)
 if request.method=='POST':
  password=request.form.get('password',''); errors=validate_user_form(c,values,password_required=True,password=password)
  if not errors:
   role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone();
   if not role: errors.append('Le rôle Bénévole est introuvable.')
  if not errors:
   try:
    cur=c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,birth_date,address,skills,availability,photo_url,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],values['phone'],generate_password_hash(password),role['id'],'volunteer',1,values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],datetime.now().isoformat(timespec='minutes'))); c.commit(); uid=cur.lastrowid; c.close(); log_action('create','volunteer',uid); flash('Bénévole ajouté avec succès.'); return redirect('/volunteers/'+str(uid))
   except sqlite3.IntegrityError: errors=['Impossible d’enregistrer : le téléphone, l’e-mail ou le nom d’utilisateur existe déjà.']
  for error in errors: flash(error)
 c.close(); return page('Nouveau bénévole',VOLUNTEER_FORM,form_title='Nouveau bénévole',u=None,submit_label='Enregistrer',cancel_url='/volunteers',password_required=True,**opts)

VOLUNTEER_FORM='''<div class="card"><h2>{{form_title}}</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{request.form.get('first_name',u.first_name if u else '')}}" required></label><label>Nom<input name="last_name" value="{{request.form.get('last_name',u.last_name if u else '')}}" required></label><label>Sexe<select name="sex">{% set sx=request.form.get('sex',u.sex if u else 'Homme') %}<option {% if sx=='Homme' %}selected{% endif %}>Homme</option><option {% if sx=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone',u.phone if u else '')}}" required></label><label>Email facultatif<input type="email" name="email" value="{{request.form.get('email',u.email if u and u.email else '')}}"></label><label>{% if password_required %}Mot de passe{% else %}Nouveau mot de passe (facultatif){% endif %}<input type="password" name="password" minlength="6" {% if password_required %}required{% endif %}></label><label>Date de naissance<input type="date" name="birth_date" value="{{request.form.get('birth_date',u.birth_date if u and u.birth_date else '')}}"></label><label>Photo (URL)<input type="url" name="photo_url" value="{{request.form.get('photo_url',u.photo_url if u and u.photo_url else '')}}"></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% set wid=request.form.get('wilaya_id',u.wilaya_id if u else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% set cid=request.form.get('commune_id',u.commune_id if u else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{request.form.get('address',u.address if u and u.address else '')}}"></label><label class="full">Compétences<textarea name="skills">{{request.form.get('skills',u.skills if u and u.skills else '')}}</textarea></label><label class="full">Disponibilités<textarea name="availability">{{request.form.get('availability',u.availability if u and u.availability else '')}}</textarea></label>{% if u %}<label>Compte<select name="active"><option value="1" {% if request.form.get('active',u.active)|string=='1' %}selected{% endif %}>Actif</option><option value="0" {% if request.form.get('active',u.active)|string=='0' %}selected{% endif %}>Inactif</option></select></label>{% endif %}<div class="full"><button class="btn">{{submit_label}}</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>'''

@app.post('/volunteers/<int:uid>/delete')
@login_required
def volunteer_delete(uid):
 if not is_admin() or uid==session.get('uid'):return redirect('/volunteers')
 c=db(); u=c.execute("SELECT u.id,u.name FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.id=? AND COALESCE(r.name,u.role)='volunteer'",(uid,)).fetchone()
 if not u:c.close();flash('Bénévole introuvable.');return redirect('/volunteers')
 refs=0
 for table,col in [('trees','planted_by_user_id'),('watering_logs','user_id'),('mission_participants','user_id'),('donations','created_by_user_id'),('event_participants','user_id')]:
  refs+=c.execute(f'SELECT COUNT(*) n FROM {table} WHERE {col}=?',(uid,)).fetchone()['n']
 if refs:
  c.execute('UPDATE users SET active=0 WHERE id=?',(uid,));message='Bénévole désactivé afin de conserver son historique.';action='deactivate'
 else:
  c.execute('DELETE FROM user_permissions WHERE user_id=?',(uid,));c.execute('DELETE FROM users WHERE id=?',(uid,));message='Bénévole supprimé.';action='delete'
 c.commit();c.close();log_action(action,'volunteer',uid,u['name'] or '');flash(message);return redirect(request.form.get('return_to') or '/volunteers')

@app.route('/volunteers/<int:uid>/edit',methods=['GET','POST'])
@login_required
def volunteer_edit(uid):
 if not is_admin():return redirect('/volunteers/'+str(uid))
 c=db();u=c.execute("SELECT u.* FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.id=? AND COALESCE(r.name,u.role)='volunteer'",(uid,)).fetchone()
 if not u:c.close();flash('Bénévole introuvable.');return redirect('/volunteers')
 opts=filter_options(c);values=user_form_values(request.form)
 if request.method=='POST':
  errors=validate_user_form(c,values,password_required=False,password=request.form.get('password',''))
  if not errors:
   try:
    sql='UPDATE users SET first_name=?,last_name=?,name=?,sex=?,phone=?,email=?,username=?,active=?,wilaya_id=?,commune_id=?,birth_date=?,address=?,skills=?,availability=?,photo_url=?';args=[values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],values['phone'],int(request.form.get('active','1')),values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url']]
    if request.form.get('password'):sql+=',password_hash=?';args.append(generate_password_hash(request.form['password']))
    sql+=' WHERE id=?';args.append(uid);c.execute(sql,args);c.commit();c.close();log_action('edit','volunteer',uid);flash('Bénévole modifié avec succès.');return redirect('/volunteers/'+str(uid))
   except sqlite3.IntegrityError:errors=['Téléphone ou identifiant déjà utilisé.']
  for e in errors:flash(e)
 c.close();return page('Modifier bénévole',VOLUNTEER_FORM,form_title='Modifier bénévole',u=u,submit_label='Enregistrer',cancel_url='/volunteers/'+str(uid),password_required=False,**opts)

@app.route('/volunteers/<int:uid>')
@login_required
def volunteer_detail(uid):
 c=db(); u=c.execute('SELECT u.*,r.label role_label,w.name wilaya_name,cm.name commune_name,t.name team_name FROM users u LEFT JOIN roles r ON r.id=u.role_id LEFT JOIN wilayas w ON w.id=u.wilaya_id LEFT JOIN communes cm ON cm.id=u.commune_id LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=?',(uid,)).fetchone()
 if not u: c.close(); return ('Introuvable',404)
 stats=dict(plantings=c.execute('SELECT COUNT(*) n FROM trees WHERE planted_by_user_id=? AND active=1',(uid,)).fetchone()['n'],waterings=c.execute('SELECT COUNT(*) n FROM watering_logs WHERE user_id=?',(uid,)).fetchone()['n'],missions=c.execute('SELECT COUNT(*) n FROM mission_participants WHERE user_id=?',(uid,)).fetchone()['n'])
 recent_trees=c.execute('SELECT id,tree_code,planted_at,approval_status FROM trees WHERE planted_by_user_id=? ORDER BY id DESC LIMIT 8',(uid,)).fetchall(); recent_water=c.execute('SELECT wl.watered_at,t.tree_code,wl.quantity_range FROM watering_logs wl LEFT JOIN trees t ON t.id=wl.tree_id WHERE wl.user_id=? ORDER BY wl.id DESC LIMIT 8',(uid,)).fetchall(); c.close()
 return page('Fiche bénévole','''<div class="section-title"><h2>{{u.name}}</h2><div>{% if admin %}<a class="btn" href="/volunteers/{{u.id}}/edit">Modifier</a> <a class="btn amber" href="/volunteers/{{u.id}}/permissions">Droits d’accès</a>{% endif %} <a class="btn alt" href="/volunteers">Retour</a></div></div><div class="grid kpis" style="grid-template-columns:repeat(3,1fr)"><div class="card kpi"><small>Plantations</small><b>{{stats.plantings}}</b></div><div class="card kpi"><small>Arrosages</small><b>{{stats.waterings}}</b></div><div class="card kpi"><small>Missions</small><b>{{stats.missions}}</b></div></div><div class="grid two"><div class="card"><h3>Profil</h3>{% if u.photo_url %}<img src="{{u.photo_url}}" alt="Photo" style="max-width:130px;border-radius:12px">{% endif %}<p><b>État :</b> {{'Actif' if u.active else 'Inactif'}}</p><p><b>Téléphone :</b> {{u.phone}}</p><p><b>E-mail :</b> {{u.email or '—'}}</p><p><b>Sexe :</b> {{u.sex or '—'}}</p><p><b>Naissance :</b> {{u.birth_date or '—'}}</p><p><b>Wilaya / Commune :</b> {{u.wilaya_name or '—'}} / {{u.commune_name or '—'}}</p><p><b>Adresse :</b> {{u.address or '—'}}</p><p><b>Équipe :</b> {{u.team_name or '—'}}</p><p><b>Compétences :</b> {{u.skills or '—'}}</p><p><b>Disponibilités :</b> {{u.availability or '—'}}</p><p><b>Date d’inscription :</b> {{u.created_at or '—'}}</p><p><b>Dernière connexion :</b> {{u.last_login or 'Jamais'}}</p></div><div><div class="card"><h3>Dernières plantations</h3>{% for x in recent_trees %}<div class="priority"><b><a href="/tree/{{x.id}}">{{x.tree_code or 'En attente'}}</a></b><span>{{x.planted_at or '—'}} • {{'Acceptée' if x.approval_status=='approved' else ('En attente' if x.approval_status=='pending' else 'Refusée')}}</span>{% if admin and x.approval_status=='pending' %}<span><a href="/tree/{{x.id}}">Traiter</a> · <a href="/trees/{{x.id}}/map">Carte</a></span>{% endif %}</div>{% else %}<p class="sub">Aucune plantation.</p>{% endfor %}</div><div class="card"><h3>Derniers arrosages</h3>{% for x in recent_water %}<div class="priority"><b>{{x.tree_code or 'Arbre'}}</b><span>{{x.watered_at}} • {{x.quantity_range}}</span></div>{% else %}<p class="sub">Aucun arrosage.</p>{% endfor %}</div></div></div>''',u=u,stats=stats,recent_trees=recent_trees,recent_water=recent_water,admin=is_admin())

SPECIES_FORM='''<div class="card"><h2>{{form_title}}</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Nom français<input name="name_fr" value="{{request.form.get('name_fr',s.name_fr if s else '')}}" required></label><label>Nom arabe<input name="name_ar" value="{{request.form.get('name_ar',s.name_ar if s and s.name_ar else '')}}"></label><label>Nom scientifique<input name="scientific_name" value="{{request.form.get('scientific_name',s.scientific_name if s and s.scientific_name else '')}}"></label><label>Catégorie<input name="category" value="{{request.form.get('category',s.category if s and s.category else '')}}"></label><label>Besoin en eau<select name="water_need">{% set wn=request.form.get('water_need',s.water_need if s and s.water_need else 'Faible') %}{% for x in ['Faible','Moyen','Élevé'] %}<option {% if wn==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Fréquence d’arrosage (jours)<input type="number" min="1" name="watering_frequency_days" value="{{request.form.get('watering_frequency_days',s.watering_frequency_days if s and s.watering_frequency_days else '')}}"></label><label>Couleur de repérage<input type="color" name="color" value="{{request.form.get('color',s.color if s and s.color else '#2e7b47')}}"></label><label>Photo (URL)<input type="url" name="photo_url" value="{{request.form.get('photo_url',s.photo_url if s and s.photo_url else '')}}"></label><label>Famille<input name="family" value="{{request.form.get('family',s.family if s and s.family else '')}}"></label><label>Origine<input name="origin" value="{{request.form.get('origin',s.origin if s and s.origin else '')}}"></label><label>Présence en Algérie<input name="algeria_presence" value="{{request.form.get('algeria_presence',s.algeria_presence if s and s.algeria_presence else '')}}"></label><label>Régions adaptées<input name="regions" value="{{request.form.get('regions',s.regions if s and s.regions else '')}}"></label><label>Type de sol<input name="soil_type" value="{{request.form.get('soil_type',s.soil_type if s and s.soil_type else '')}}"></label><label>Exposition<input name="sun_exposure" value="{{request.form.get('sun_exposure',s.sun_exposure if s and s.sun_exposure else '')}}"></label><label>Résistance sécheresse<input name="drought_tolerance" value="{{request.form.get('drought_tolerance',s.drought_tolerance if s and s.drought_tolerance else '')}}"></label><label>Résistance froid<input name="cold_tolerance" value="{{request.form.get('cold_tolerance',s.cold_tolerance if s and s.cold_tolerance else '')}}"></label><label>Résistance salinité<input name="salt_tolerance" value="{{request.form.get('salt_tolerance',s.salt_tolerance if s and s.salt_tolerance else '')}}"></label><label>Résistance vent<input name="wind_tolerance" value="{{request.form.get('wind_tolerance',s.wind_tolerance if s and s.wind_tolerance else '')}}"></label><label>Distance de plantation<input name="planting_distance" value="{{request.form.get('planting_distance',s.planting_distance if s and s.planting_distance else '')}}"></label><label>Hauteur adulte<input name="adult_height" value="{{request.form.get('adult_height',s.adult_height if s and s.adult_height else '')}}"></label><label>Vitesse de croissance<input name="growth_rate" value="{{request.form.get('growth_rate',s.growth_rate if s and s.growth_rate else '')}}"></label><label>Période de plantation<input name="planting_period" value="{{request.form.get('planting_period',s.planting_period if s and s.planting_period else '')}}"></label><label class="full">Usages<textarea name="uses">{{request.form.get('uses',s.uses if s and s.uses else '')}}</textarea></label><label class="full">Entretien<textarea name="maintenance">{{request.form.get('maintenance',s.maintenance if s and s.maintenance else '')}}</textarea></label><label class="full">Maladies et parasites<textarea name="diseases">{{request.form.get('diseases',s.diseases if s and s.diseases else '')}}</textarea></label><label class="full">Compatibilité / précautions<textarea name="compatibility_note">{{request.form.get('compatibility_note',s.compatibility_note if s and s.compatibility_note else '')}}</textarea></label><label class="full">Description<textarea name="description">{{request.form.get('description',s.description if s and s.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/species">Annuler</a></div></form></div>'''

SPECIES_EXTRA_FIELDS=['family','origin','algeria_presence','regions','soil_type','sun_exposure','drought_tolerance','cold_tolerance','salt_tolerance','wind_tolerance','planting_distance','adult_height','growth_rate','planting_period','uses','maintenance','diseases','compatibility_note']

def save_species_extras(c,sid,form):
 values=[clean(form.get(k)) or None for k in SPECIES_EXTRA_FIELDS]
 c.execute('UPDATE species SET '+','.join(k+'=?' for k in SPECIES_EXTRA_FIELDS)+' WHERE id=?',values+[sid])

def validate_species(c,form,species_id=None):
 name=clean(form.get('name_fr')); errors=[]
 if not name: errors.append('Le nom français est obligatoire.')
 q='SELECT id FROM species WHERE lower(name_fr)=lower(?)'; params=[name]
 if species_id is not None: q+=' AND id<>?'; params.append(species_id)
 if name and c.execute(q,params).fetchone(): errors.append('Une espèce portant ce nom existe déjà.')
 freq=form.get('watering_frequency_days')
 if freq:
  try:
   if int(freq)<1: errors.append('La fréquence d’arrosage doit être supérieure à zéro.')
  except ValueError: errors.append('La fréquence d’arrosage doit être un nombre entier.')
 return errors

@app.route('/species')
@login_required
def species_page():
 c=db(); q=clean(request.args.get('q')); include_inactive=request.args.get('inactive')=='1'
 where=[]; params=[]
 if not include_inactive: where.append('s.active=1')
 if q:
  where.append('(s.name_fr LIKE ? OR s.name_ar LIKE ? OR s.name_en LIKE ? OR s.scientific_name LIKE ? OR s.category LIKE ?)'); params += ['%'+q+'%']*5
 sql='''SELECT s.*,(SELECT COUNT(*) FROM trees t WHERE t.species_id=s.id AND t.active=1) tree_count FROM species s'''
 if where: sql+=' WHERE '+' AND '.join(where)
 rows=c.execute(sql+' ORDER BY s.active DESC,s.name_fr',params).fetchall(); c.close()
 return page('Espèces','''<div class="section-title"><h2>Référentiel des espèces</h2>{% if admin %}<a class="btn" href="/species/new">+ Nouvelle espèce</a>{% endif %}</div><form class="card toolbar" onsubmit="return false"><label>Recherche intelligente<input id="speciesLiveSearch" name="q" value="{{q}}" placeholder="Tapez quelques lettres…" oninput="filterSpeciesRows(this.value)"></label>{% if admin %}<label>Affichage<select name="inactive"><option value="0">Espèces actives</option><option value="1" {% if include_inactive %}selected{% endif %}>Actives et archivées</option></select></label>{% endif %}<button class="btn">Filtrer</button><a class="btn alt" href="/species">Annuler</a></form><div class="card" style="overflow:auto"><table><tr><th>Espèce</th><th>Scientifique</th><th>Catégorie</th><th>Eau</th><th>Fréquence</th><th>Arbres</th><th>État</th><th>Actions</th></tr>{% for s in rows %}<tr class="species-row" data-search="{{(s.name_fr~' '~(s.name_ar or '')~' '~(s.name_en or '')~' '~(s.scientific_name or '')~' '~(s.category or ''))|lower}}"><td><b>{{s.name_fr}}</b><div class="sub">{{s.name_ar or '—'}} • {{s.name_en or '—'}}</div></td><td><i>{{s.scientific_name or '—'}}</i></td><td>{{s.category or '—'}}</td><td>{{s.water_need or '—'}}</td><td>{{s.watering_frequency_days or '—'}}{% if s.watering_frequency_days %} jours{% endif %}</td><td>{{s.tree_count}}</td><td><span class="badge {% if s.active %}good{% else %}danger{% endif %}">{{'Active' if s.active else 'Archivée'}}</span></td><td>{% if admin %}<a href="/species/{{s.id}}/edit">Modifier</a> · <form method="post" action="/species/{{s.id}}/toggle" style="display:inline"><button class="btn alt" style="padding:5px 8px">{{'Archiver' if s.active else 'Réactiver'}}</button></form>{% if s.tree_count==0 %} <form method="post" action="/species/{{s.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer définitivement cette espèce ?')"><button class="btn red" style="padding:5px 8px">Supprimer</button></form>{% endif %}{% else %}—{% endif %}</td></tr>{% else %}<tr><td colspan="8">Aucune espèce trouvée.</td></tr>{% endfor %}</table></div><script>function filterSpeciesRows(q){q=(q||'').toLowerCase().trim();document.querySelectorAll('.species-row').forEach(r=>r.style.display=!q||r.dataset.search.includes(q)?'':'none')}</script>''',rows=rows,q=q,include_inactive=include_inactive,admin=is_admin())

@app.route('/species/new',methods=['GET','POST'])
@login_required
def species_new():
 if not is_admin(): return redirect('/species')
 c=db()
 if request.method=='POST':
  errors=validate_species(c,request.form)
  if not errors:
   now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('''INSERT INTO species(name_fr,name_ar,name_en,scientific_name,category,water_need,watering_frequency_days,color,description,photo_url,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)''',(clean(request.form.get('name_fr')),clean(request.form.get('name_ar')) or None,clean(request.form.get('name_en')) or None,clean(request.form.get('scientific_name')) or None,clean(request.form.get('category')) or None,request.form.get('water_need'),request.form.get('watering_frequency_days') or None,request.form.get('color') or '#2e7b47',clean(request.form.get('description')) or None,clean(request.form.get('photo_url')) or None,now,now)); sid=cur.lastrowid; save_species_extras(c,sid,request.form); c.commit(); c.close(); log_action('create','species',sid); flash('Espèce ajoutée.'); return redirect('/species')
  for e in errors: flash(e)
 c.close(); return page('Nouvelle espèce',SPECIES_FORM,form_title='Nouvelle espèce',s=None)

@app.route('/species/<int:sid>/edit',methods=['GET','POST'])
@login_required
def species_edit(sid):
 if not is_admin(): return redirect('/species')
 c=db(); sp=c.execute('SELECT * FROM species WHERE id=?',(sid,)).fetchone()
 if not sp: c.close(); return ('Espèce introuvable',404)
 if request.method=='POST':
  errors=validate_species(c,request.form,sid)
  if not errors:
   now=datetime.now().isoformat(timespec='minutes'); c.execute('''UPDATE species SET name_fr=?,name_ar=?,name_en=?,scientific_name=?,category=?,water_need=?,watering_frequency_days=?,color=?,description=?,photo_url=?,updated_at=? WHERE id=?''',(clean(request.form.get('name_fr')),clean(request.form.get('name_ar')) or None,clean(request.form.get('name_en')) or None,clean(request.form.get('scientific_name')) or None,clean(request.form.get('category')) or None,request.form.get('water_need'),request.form.get('watering_frequency_days') or None,request.form.get('color') or '#2e7b47',clean(request.form.get('description')) or None,clean(request.form.get('photo_url')) or None,now,sid)); c.execute('UPDATE trees SET species=? WHERE species_id=?',(clean(request.form.get('name_fr')),sid)); save_species_extras(c,sid,request.form); c.commit(); c.close(); log_action('edit','species',sid); flash('Espèce modifiée.'); return redirect('/species')
  for e in errors: flash(e)
 c.close(); return page('Modifier une espèce',SPECIES_FORM,form_title='Modifier une espèce',s=sp)

@app.post('/species/<int:sid>/toggle')
@login_required
def species_toggle(sid):
 if not is_admin(): return redirect('/species')
 c=db(); sp=c.execute('SELECT active FROM species WHERE id=?',(sid,)).fetchone()
 if sp:
  new_state=0 if sp['active'] else 1; c.execute('UPDATE species SET active=?,updated_at=? WHERE id=?',(new_state,datetime.now().isoformat(timespec='minutes'),sid)); c.commit(); log_action('archive' if not new_state else 'reactivate','species',sid); flash('Espèce archivée.' if not new_state else 'Espèce réactivée.')
 c.close(); return redirect('/species?inactive=1')

@app.post('/species/<int:sid>/delete')
@login_required
def species_delete(sid):
 if not is_admin(): return redirect('/species')
 c=db(); n=c.execute('SELECT COUNT(*) n FROM trees WHERE species_id=?',(sid,)).fetchone()['n']
 if n: flash('Suppression impossible : cette espèce est utilisée par des arbres.')
 else: c.execute('DELETE FROM species WHERE id=?',(sid,)); c.commit(); log_action('delete','species',sid); flash('Espèce supprimée définitivement.')
 c.close(); return redirect('/species')

@app.route('/geography',methods=['GET','POST'])
@login_required
def geography():
 c=db()
 if request.method=='POST' and is_admin():
  if request.form['kind']=='wilaya':c.execute('INSERT INTO wilayas(code,name) VALUES(?,?)',(request.form['code'],request.form['name']))
  else:c.execute('INSERT INTO communes(wilaya_id,name) VALUES(?,?)',(request.form['wilaya_id'],request.form['name']))
  c.commit(); c.close(); flash('Élément géographique ajouté.'); return redirect('/geography')
 rows=c.execute('SELECT c.*,w.name wilaya_name FROM communes c JOIN wilayas w ON w.id=c.wilaya_id ORDER BY w.name,c.name').fetchall(); wilayas=c.execute('SELECT * FROM wilayas ORDER BY name').fetchall(); c.close(); return page('Géographie','''{% if admin %}<div class="grid two"><details class="card"><summary class="btn">+ Nouvelle wilaya</summary><form method="post" class="form" style="margin-top:12px"><input type="hidden" name="kind" value="wilaya"><label>Code<input name="code"></label><label>Nom<input name="name" required></label><div class="full"><button class="btn">Enregistrer</button></div></form></details><details class="card"><summary class="btn">+ Nouvelle commune</summary><form method="post" class="form" style="margin-top:12px"><input type="hidden" name="kind" value="commune"><label>Wilaya<select name="wilaya_id">{% for w in wilayas %}<option value="{{w.id}}">{{w.name}}</option>{% endfor %}</select></label><label>Nom<input name="name" required></label><div class="full"><button class="btn">Enregistrer</button></div></form></details></div>{% endif %}<div class="card"><table><tr><th>Wilaya</th><th>Commune</th></tr>{% for x in rows %}<tr><td>{{x.wilaya_name}}</td><td>{{x.name}}</td></tr>{% endfor %}</table></div>''',rows=rows,wilayas=wilayas,admin=is_admin())

@app.route('/projects')
@login_required
def projects_page():
 c=db(); q=request.args.get('q','').strip(); status=request.args.get('status',''); active=request.args.get('active','1'); scope,scope_params=context_condition('p'); w=[scope]; params=list(scope_params)
 if q: w.append('(p.code LIKE ? OR p.name LIKE ? OR p.location LIKE ?)'); params += ['%'+q+'%']*3
 if status: w.append('p.status=?'); params.append(status)
 if active!='': w.append('p.active=?'); params.append(active)
 rows=c.execute("""SELECT p.*,w.name wilaya_name,cm.name commune_name,u.name manager_name,
 (SELECT COUNT(*) FROM zones z WHERE z.project_id=p.id AND z.active=1) zone_count,
 (SELECT COUNT(*) FROM teams t WHERE t.project_id=p.id AND t.active=1) team_count,
 (SELECT COUNT(*) FROM trees tr WHERE tr.project_id=p.id AND tr.active=1 AND tr.approval_status='approved') tree_count,
 (SELECT COUNT(*) FROM missions m WHERE m.project_id=p.id AND m.active=1) mission_count
 FROM projects p LEFT JOIN wilayas w ON w.id=p.wilaya_id LEFT JOIN communes cm ON cm.id=p.commune_id LEFT JOIN users u ON u.id=p.manager_user_id
 WHERE """+' AND '.join(w)+' ORDER BY p.active DESC,p.id DESC',params).fetchall(); c.close()
 return page('Projets',"""<div class="section-title"><h2>Liste des projets</h2>{% if admin %}<a class="btn" href="/projects/new">+ Nouveau projet</a>{% endif %}</div>
 <form class="card toolbar"><label>Recherche<input name="q" value="{{q}}" placeholder="Code, nom ou lieu"></label><label>Statut<select name="status"><option value="">Tous</option>{% for x in ['Brouillon','Étude et préparation','Validé','En cours','Terminé'] %}<option {% if status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>État<select name="active"><option value="">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actifs</option><option value="0" {% if active=='0' %}selected{% endif %}>Archivés</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/projects">Effacer</a></form>
 <div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Projet</th><th>Responsable</th><th>Localisation</th><th>Statut</th><th>Progression</th><th>Zones</th><th>Équipes</th><th>Missions</th><th>Actions</th></tr>{% for p in rows %}{% set pct=(100*p.tree_count/p.target_trees)|round|int if p.target_trees else 0 %}<tr><td>{{p.code}}</td><td><a href="/projects/{{p.id}}"><b>{{p.name}}</b></a><div class="sub">{{p.location or ''}}</div></td><td>{{p.manager_name or '—'}}</td><td>{{p.wilaya_name or '—'}} / {{p.commune_name or '—'}}</td><td><span class="badge {% if not p.active %}danger{% elif p.status=='Terminé' %}good{% else %}watch{% endif %}">{{'Archivé' if not p.active else p.status}}</span></td><td>{{p.tree_count}} / {{p.target_trees or 0}} ({{pct}} %)</td><td>{{p.zone_count}}</td><td>{{p.team_count}}</td><td>{{p.mission_count}}</td><td><a class="btn alt" href="/projects/{{p.id}}">Ouvrir</a>{% if admin %} <a class="btn alt" href="/projects/{{p.id}}/edit">Modifier</a> <form method="post" action="/projects/{{p.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver ce projet ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="10">Aucun projet.</td></tr>{% endfor %}</table></div>""",rows=rows,q=q,status=status,active=active,admin=is_admin())

PROJECT_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Code<input name="code" value="{{request.form.get('code',p.code if p else suggested_code)}}" readonly></label><label>Nom<input name="name" value="{{request.form.get('name',p.name if p else '')}}" required></label><label>Statut<select name="status">{% set st=request.form.get('status',p.status if p else 'Brouillon') %}{% for x in ['Brouillon','Étude et préparation','Validé','En cours','Terminé'] %}<option {% if st==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Responsable<select name="manager_user_id"><option value="">—</option>{% set mid=request.form.get('manager_user_id',p.manager_user_id if p else '') %}{% for x in managers %}<option value="{{x.id}}" {% if mid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Objectif arbres<input type="number" min="0" name="target_trees" value="{{request.form.get('target_trees',p.target_trees if p else 0)}}"></label><label>Budget<input type="number" min="0" step="0.01" name="budget" value="{{request.form.get('budget',p.budget if p else 0)}}"></label><label>Date début<input type="date" name="start_date" value="{{request.form.get('start_date',p.start_date if p and p.start_date else '')}}"></label><label>Date fin<input type="date" name="end_date" value="{{request.form.get('end_date',p.end_date if p and p.end_date else '')}}"></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% set wid=request.form.get('wilaya_id',p.wilaya_id if p else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% set cid=request.form.get('commune_id',p.commune_id if p else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Lieu<input name="location" value="{{request.form.get('location',p.location if p and p.location else '')}}"></label>{% if p %}<label>État<select name="active"><option value="1" {% if request.form.get('active',p.active)|string=='1' %}selected{% endif %}>Actif</option><option value="0" {% if request.form.get('active',p.active)|string=='0' %}selected{% endif %}>Archivé</option></select></label>{% endif %}<label class="full">Description<textarea name="description">{{request.form.get('description',p.description if p and p.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>"""

@app.route('/projects/new',methods=['GET','POST'])
@login_required
def project_new():
 if not is_admin(): return redirect('/projects')
 if not require_association_context() and not is_super_admin(): return redirect('/my-associations')
 c=db(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); suggested=next_entity_code(c,'projects','code','PROJET')
 if request.method=='POST':
  code=clean(request.form.get('code')) or suggested; name=request.form['name'].strip(); errors=[]
  if c.execute('SELECT id FROM projects WHERE code=?',(code,)).fetchone(): errors.append('Ce code projet existe déjà.')
  wid=request.form.get('wilaya_id') or None; cid=request.form.get('commune_id') or None
  if cid and (not wid or not c.execute('SELECT 1 FROM communes WHERE id=? AND wilaya_id=?',(cid,wid)).fetchone()): errors.append('La commune ne correspond pas à la wilaya sélectionnée.')
  if not errors:
   now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,manager_user_id,active,description,start_date,end_date,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)',(code,name,request.form.get('status') or 'Brouillon',request.form.get('target_trees') or 0,request.form.get('budget') or 0,wid,cid,request.form.get('location'),request.form.get('manager_user_id') or None,request.form.get('description'),request.form.get('start_date') or None,request.form.get('end_date') or None,now,now,current_association_id())); c.commit(); pid=cur.lastrowid; c.close(); log_action('create','project',pid,name); flash('Projet créé.'); return redirect('/projects/'+str(pid))
  for e in errors: flash(e)
 c.close(); return page('Nouveau projet',PROJECT_FORM,p=None,managers=managers,cancel_url='/projects',suggested_code=suggested,**opts)

@app.route('/projects/<int:pid>')
@login_required
def project_detail(pid):
 c=db(); p=c.execute("""SELECT p.*,w.name wilaya_name,cm.name commune_name,u.name manager_name FROM projects p LEFT JOIN wilayas w ON w.id=p.wilaya_id LEFT JOIN communes cm ON cm.id=p.commune_id LEFT JOIN users u ON u.id=p.manager_user_id WHERE p.id=?""",(pid,)).fetchone()
 if not p: c.close(); return ('Projet introuvable',404)
 stats={'zones':c.execute('SELECT COUNT(*) n FROM zones WHERE project_id=? AND active=1',(pid,)).fetchone()['n'],'teams':c.execute('SELECT COUNT(*) n FROM teams WHERE project_id=? AND active=1',(pid,)).fetchone()['n'],'trees':c.execute("SELECT COUNT(*) n FROM trees WHERE project_id=? AND active=1 AND approval_status='approved'",(pid,)).fetchone()['n'],'missions':c.execute('SELECT COUNT(*) n FROM missions WHERE project_id=? AND active=1',(pid,)).fetchone()['n'],'waterings':c.execute('SELECT COUNT(*) n FROM watering_logs wl JOIN trees t ON t.id=wl.tree_id WHERE t.project_id=?',(pid,)).fetchone()['n']}
 zones=c.execute('SELECT z.*,u.name manager_name,(SELECT COUNT(*) FROM trees t WHERE t.zone_id=z.id AND t.active=1) tree_count FROM zones z LEFT JOIN users u ON u.id=z.manager_user_id WHERE z.project_id=? AND z.active=1 ORDER BY z.name',(pid,)).fetchall(); teams=c.execute('SELECT t.*,u.name leader_name,(SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.status=\'active\') member_count FROM teams t LEFT JOIN users u ON u.id=t.leader_user_id WHERE t.project_id=? AND t.active=1 ORDER BY t.name',(pid,)).fetchall(); c.close()
 return page('Fiche projet',"""<div class="section-title"><div><h2>{{p.name}}</h2><span class="badge watch">{{p.code}}</span> <span class="badge {% if p.active %}good{% else %}danger{% endif %}">{{p.status if p.active else 'Archivé'}}</span></div><div>{% if admin %}<a class="btn" href="/projects/{{p.id}}/edit">Modifier</a> <form method="post" action="/projects/{{p.id}}/duplicate" style="display:inline"><button class="btn alt">Dupliquer</button></form> <form method="post" action="/projects/{{p.id}}/archive" style="display:inline"><button class="btn red">{{'Archiver' if p.active else 'Réactiver'}}</button></form>{% endif %} <a class="btn alt" href="/projects/{{p.id}}/phases">Phases</a> <a class="btn alt" href="/operations?project_id={{p.id}}">Planning</a> <a class="btn alt" href="/projects">Retour</a></div></div><div class="grid kpis" style="grid-template-columns:repeat(5,1fr)">{% for label,value in [('Zones',stats.zones),('Équipes',stats.teams),('Arbres',stats.trees),('Arrosages',stats.waterings),('Missions',stats.missions)] %}<div class="card kpi"><small>{{label}}</small><b>{{value}}</b></div>{% endfor %}</div><div class="grid two"><div class="card"><h3>Informations</h3><p><b>Responsable :</b> {{p.manager_name or '—'}}</p><p><b>Wilaya / Commune :</b> {{p.wilaya_name or '—'}} / {{p.commune_name or '—'}}</p><p><b>Lieu :</b> {{p.location or '—'}}</p><p><b>Période :</b> {{p.start_date or '—'}} → {{p.end_date or '—'}}</p><p><b>Budget :</b> {{p.budget or 0}}</p><p><b>Objectif :</b> {{stats.trees}} / {{p.target_trees or 0}} arbres</p><p>{{p.description or ''}}</p></div><div class="card"><h3>Zones</h3>{% for z in zones %}<div class="priority"><b><a href="/zones/{{z.id}}">{{z.name}}</a></b><span>{{z.tree_count}} arbres • {{z.manager_name or 'Sans responsable'}}</span></div>{% else %}<p class="sub">Aucune zone.</p>{% endfor %}</div></div><div class="card"><h3>Équipes</h3>{% for t in teams %}<div class="priority"><b><a href="/teams/{{t.id}}">{{t.name}}</a></b><span>{{t.member_count}} membres • {{t.leader_name or 'Sans chef'}}</span></div>{% else %}<p class="sub">Aucune équipe.</p>{% endfor %}</div>""",p=p,stats=stats,zones=zones,teams=teams,admin=is_admin())

@app.route('/projects/<int:pid>/edit',methods=['GET','POST'])
@login_required
def project_edit(pid):
 if not is_admin(): return redirect('/projects')
 c=db(); p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if not p: c.close(); return ('Introuvable',404)
 if request.method=='POST':
  code=request.form['code'].strip(); duplicate=c.execute('SELECT id FROM projects WHERE code=? AND id<>?',(code,pid)).fetchone(); target=int(request.form.get('target_trees') or 0)
  ok_target,allocated,planted=validate_project_target(c,pid,target)
  wid=request.form.get('wilaya_id') or None; cid=request.form.get('commune_id') or None
  geo_ok=(not cid) or (wid and c.execute('SELECT 1 FROM communes WHERE id=? AND wilaya_id=?',(cid,wid)).fetchone())
  if duplicate: flash('Ce code projet existe déjà.')
  elif not geo_ok: flash('La commune ne correspond pas à la wilaya sélectionnée.')
  elif not ok_target: flash(f'Objectif impossible : {allocated} arbre(s) sont déjà répartis dans les zones et {planted} plantation(s) sont rattachées au projet.')
  else:
   geo_changed=str(p['wilaya_id'] or '')!=str(wid or '') or str(p['commune_id'] or '')!=str(cid or '')
   c.execute('UPDATE projects SET code=?,name=?,status=?,target_trees=?,budget=?,wilaya_id=?,commune_id=?,location=?,manager_user_id=?,active=?,description=?,start_date=?,end_date=?,updated_at=? WHERE id=?',(code,request.form['name'].strip(),request.form.get('status'),target,request.form.get('budget') or 0,wid,cid,request.form.get('location'),request.form.get('manager_user_id') or None,request.form.get('active',1),request.form.get('description'),request.form.get('start_date') or None,request.form.get('end_date') or None,datetime.now().isoformat(timespec='minutes'),pid))
   if geo_changed:
    c.execute('UPDATE zones SET wilaya_id=?,commune_id=?,updated_at=? WHERE project_id=?',(wid,cid,datetime.now().isoformat(timespec='minutes'),pid))
    c.execute('UPDATE trees SET wilaya_id=?,commune_id=? WHERE project_id=?',(wid,cid,pid))
   c.commit(); c.close(); log_action('edit','project',pid,'geo cascade' if geo_changed else ''); flash('Projet modifié.'+(' La localisation a été répercutée sur ses zones et arbres.' if geo_changed else '')); return redirect('/projects/'+str(pid))
 c.close(); return page('Modifier projet',PROJECT_FORM,p=p,managers=managers,cancel_url='/projects/'+str(pid),suggested_code=p['code'],**opts)

@app.post('/projects/<int:pid>/archive')
@login_required
def project_archive(pid):
 if not is_admin(): return redirect('/projects')
 c=db(); p=c.execute('SELECT active FROM projects WHERE id=?',(pid,)).fetchone()
 if p: c.execute('UPDATE projects SET active=?,updated_at=? WHERE id=?',(0 if p['active'] else 1,datetime.now().isoformat(timespec='minutes'),pid)); c.commit()
 c.close(); log_action('archive_toggle','project',pid); flash('État du projet mis à jour.'); return redirect('/projects/'+str(pid))

@app.post('/projects/<int:pid>/duplicate')
@login_required
def project_duplicate(pid):
 if not is_admin(): return redirect('/projects')
 c=db(); p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
 if not p: c.close(); return redirect('/projects')
 base=p['code']+'-COPIE'; code=base; i=2
 while c.execute('SELECT id FROM projects WHERE code=?',(code,)).fetchone(): code=f'{base}-{i}'; i+=1
 now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,manager_user_id,active,description,start_date,end_date,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)',(code,p['name']+' (copie)','Brouillon',p['target_trees'],p['budget'],p['wilaya_id'],p['commune_id'],p['location'],p['manager_user_id'],p['description'],p['start_date'],p['end_date'],now,now,p['association_id'])); c.commit(); nid=cur.lastrowid; c.close(); log_action('duplicate','project',nid); flash('Projet dupliqué dans la même association.'); return redirect('/projects/'+str(nid))

@app.route('/api/projects/<int:pid>/defaults')
@login_required
def api_project_defaults(pid):
 c=db(); allowed={int(x['id']) for x in accessible_filter_projects(c,active_context(c))}
 if pid not in allowed: c.close(); return jsonify({'error':'forbidden_project'}),403
 p=c.execute('SELECT id,wilaya_id,commune_id,target_trees FROM projects WHERE id=? AND active=1',(pid,)).fetchone(); allocated=c.execute('SELECT COALESCE(SUM(target_trees),0) n FROM zones WHERE project_id=? AND active=1',(pid,)).fetchone()['n'] if p else 0; c.close()
 if not p:return jsonify({'error':'not_found'}),404
 return jsonify({'wilaya_id':p['wilaya_id'],'commune_id':p['commune_id'],'target_trees':p['target_trees'] or 0,'allocated':allocated,'remaining':max(0,(p['target_trees'] or 0)-allocated)})

@app.route('/api/projects/<int:pid>/zones')
@login_required
def api_project_zones(pid):
 c=db(); allowed={int(x['id']) for x in accessible_filter_projects(c,active_context(c))}
 if pid not in allowed: c.close(); return jsonify({'error':'forbidden_project'}),403
 rows=c.execute('SELECT id,name FROM zones WHERE project_id=? AND active=1 ORDER BY name',(pid,)).fetchall(); c.close(); return jsonify([dict(x) for x in rows])

@app.route('/api/teams/<int:tid>/leader')
@login_required
def api_team_leader(tid):
 c=db(); r=c.execute('SELECT t.leader_user_id,u.name leader_name,t.project_id,t.zone_id FROM teams t LEFT JOIN users u ON u.id=t.leader_user_id WHERE t.id=?',(tid,)).fetchone(); c.close(); return jsonify(dict(r)) if r else (jsonify({'error':'not_found'}),404)

@app.route('/zones')
@login_required
def zones_page():
 c=db(); q=request.args.get('q','').strip(); project_id=request.args.get('project_id',''); wilaya_id=request.args.get('wilaya_id',''); commune_id=request.args.get('commune_id',''); manager_id=request.args.get('manager_id',''); active=request.args.get('active','1'); scope,scope_params=context_condition('z'); w=[scope]; params=list(scope_params)
 if q: w.append('(z.code LIKE ? OR z.name LIKE ? OR z.description LIKE ?)'); params += ['%'+q+'%']*3
 if project_id: w.append('z.project_id=?'); params.append(project_id)
 if wilaya_id: w.append('z.wilaya_id=?'); params.append(wilaya_id)
 if commune_id: w.append('z.commune_id=?'); params.append(commune_id)
 if manager_id: w.append('z.manager_user_id=?'); params.append(manager_id)
 if active!='': w.append('z.active=?'); params.append(active)
 rows=c.execute("""SELECT z.*,p.name project_name,u.name manager_name,w.name wilaya_name,cm.name commune_name,(SELECT COUNT(*) FROM trees t WHERE t.zone_id=z.id AND t.active=1) tree_count,(SELECT COUNT(*) FROM teams tm WHERE tm.zone_id=z.id AND tm.active=1) team_count,(SELECT COUNT(*) FROM trees t WHERE t.zone_id=z.id AND t.active=1 AND (t.watering_status!='À jour' OR t.health_status IN ('À surveiller','Urgent','Critique'))) priority_count FROM zones z LEFT JOIN projects p ON p.id=z.project_id LEFT JOIN users u ON u.id=z.manager_user_id LEFT JOIN wilayas w ON w.id=z.wilaya_id LEFT JOIN communes cm ON cm.id=z.commune_id WHERE """+' AND '.join(w)+' ORDER BY z.active DESC,z.name',params).fetchall()
 ps,pp=context_condition('projects'); projects=c.execute('SELECT id,name FROM projects WHERE active=1 AND '+ps+' ORDER BY name',pp).fetchall(); wilayas=c.execute('SELECT id,name FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT id,name FROM communes WHERE active=1 ORDER BY name').fetchall(); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); c.close()
 return page('Zones',"""<div class="section-title"><h2>Zones</h2>{% if admin %}<a class="btn" href="/zones/new">+ Nouvelle zone</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}" placeholder="Nom, code ou description"></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="manager_id"><option value="">Tous</option>{% for x in managers %}<option value="{{x.id}}" {% if manager_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>État<select name="active"><option value="">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actives</option><option value="0" {% if active=='0' %}selected{% endif %}>Archivées</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/zones">Annuler les filtres</a></form><div class="card" style="overflow:auto"><table><tr><th>Zone</th><th>Projet</th><th>Responsable</th><th>Wilaya / Commune</th><th>Superficie</th><th>Arbres</th><th>Priorités</th><th>Équipes</th><th>État</th><th>Actions</th></tr>{% for z in rows %}<tr><td><a href="/zones/{{z.id}}"><b>{{z.name}}</b></a><div class="sub">{{z.code or 'Sans code'}}</div></td><td>{{z.project_name or '—'}}</td><td>{{z.manager_name or '—'}}</td><td>{{z.wilaya_name or '—'}} / {{z.commune_name or '—'}}</td><td>{{z.area or 0}} ha</td><td>{{z.tree_count}} / {{z.target_trees or 0}}</td><td><span class="badge {% if z.priority_count %}danger{% else %}good{% endif %}">{{z.priority_count}}</span></td><td>{{z.team_count}}</td><td><span class="badge {% if z.active %}good{% else %}danger{% endif %}">{{'Active' if z.active else 'Archivée'}}</span></td><td><a class="btn alt" href="/zones/{{z.id}}">Fiche</a>{% if admin %} <a class="btn alt" href="/zones/{{z.id}}/edit">Modifier</a> <form method="post" action="/zones/{{z.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cette zone ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="10">Aucune zone ne correspond aux filtres.</td></tr>{% endfor %}</table></div>""",rows=rows,projects=projects,wilayas=wilayas,communes=communes,managers=managers,q=q,project_id=project_id,wilaya_id=wilaya_id,commune_id=commune_id,manager_id=manager_id,active=active,admin=is_admin())

ZONE_FORM="""<div class="card"><form method="post" class="form" id="zoneForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Projet<select name="project_id" id="zoneProject" required><option value="">—</option>{% set pid=request.form.get('project_id',z.project_id if z else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select><span class="sub" id="zoneRemaining"></span></label><label>Code<input name="code" value="{{request.form.get('code',z.code if z and z.code else suggested_code)}}" readonly></label><label>Nom<input name="name" value="{{request.form.get('name',z.name if z else '')}}" required></label><label>Responsable<select name="manager_user_id"><option value="">—</option>{% set mid=request.form.get('manager_user_id',z.manager_user_id if z else '') %}{% for x in managers %}<option value="{{x.id}}" {% if mid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Wilaya <span class="sub">(héritée du projet)</span><select name="wilaya_id" id="zoneWilaya" disabled><option value="">—</option>{% set wid=request.form.get('wilaya_id',z.wilaya_id if z else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune <span class="sub">(héritée du projet)</span><select name="commune_id" id="zoneCommune" disabled><option value="">—</option>{% set cid=request.form.get('commune_id',z.commune_id if z else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Superficie (ha)<input type="number" step="0.01" min="0" name="area" value="{{request.form.get('area',z.area if z else 0)}}"></label><label>Objectif arbres<input type="number" min="0" name="target_trees" id="zoneTarget" value="{{request.form.get('target_trees',z.target_trees if z else 0)}}"></label><label>Latitude<input id="zoneLat" type="number" step="any" name="latitude" value="{{request.form.get('latitude',z.latitude if z and z.latitude is not none else '')}}"></label><label>Longitude<input id="zoneLon" type="number" step="any" name="longitude" value="{{request.form.get('longitude',z.longitude if z and z.longitude is not none else '')}}"></label><div class="full">{{location_picker|safe}}</div><label>Couleur<input type="color" name="color" value="{{request.form.get('color',z.color if z and z.color else '#3a7d44')}}"></label>{% if z %}<label>État<select name="active"><option value="1" {% if request.form.get('active',z.active)|string=='1' %}selected{% endif %}>Active</option><option value="0" {% if request.form.get('active',z.active)|string=='0' %}selected{% endif %}>Archivée</option></select></label>{% endif %}<label class="full">Description<textarea name="description">{{request.form.get('description',z.description if z and z.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div><script>
async function zoneProjectChanged(){let p=zoneProject.value;if(!p)return;let d=await fetch('/api/projects/'+p+'/defaults').then(r=>r.json());zoneWilaya.value=d.wilaya_id||'';await loadZoneCommunes(d.commune_id);zoneRemaining.textContent='Reste à répartir : '+d.remaining+' arbre(s)';}
async function loadZoneCommunes(selected){let w=zoneWilaya.value;zoneCommune.innerHTML='<option value="">—</option>';if(!w)return;let rows=await fetch('/api/communes/'+w).then(r=>r.json());rows.forEach(x=>{let o=new Option(x.name+(x.name_ar?' — '+x.name_ar:''),x.id);if(String(x.id)==String(selected))o.selected=true;zoneCommune.add(o)})}
zoneProject.addEventListener('change',zoneProjectChanged);if(zoneProject.value){fetch('/api/projects/'+zoneProject.value+'/defaults').then(r=>r.json()).then(d=>{zoneRemaining.textContent='Reste à répartir : '+d.remaining+' arbre(s)'})}
</script>"""

@app.route('/zones/new',methods=['GET','POST'])
@login_required
def zone_new():
 if not is_admin(): return redirect('/zones')
 c=db(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); suggested=next_entity_code(c,'zones','code','ZONE')
 if request.method=='POST':
  project_id=request.form.get('project_id'); allowed,p0=project_owner_allowed(c,project_id,'zone.create')
  target=int(request.form.get('target_trees') or 0); ok,remaining=validate_zone_target(c,project_id,target)
  if not allowed:
   c.close(); return ('Seule l’association propriétaire du projet peut créer une zone.',403)
  if not ok:
   flash('Objectif impossible : les zones dépasseraient l’objectif du projet. Reste disponible : '+str(remaining)+' arbre(s).'); c.close(); return page('Nouvelle zone',ZONE_FORM,z=None,managers=managers,cancel_url='/zones',suggested_code=suggested,location_picker=location_picker_markup('zone'),**opts)
  now=datetime.now().isoformat(timespec='minutes'); code=clean(request.form.get('code')) or suggested
  cur=c.execute('INSERT INTO zones(project_id,wilaya_id,commune_id,code,name,area,target_trees,color,manager_user_id,active,description,latitude,longitude,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)',(project_id,p0['wilaya_id'],p0['commune_id'],code,request.form['name'].strip(),request.form.get('area') or 0,target,request.form.get('color') or '#3a7d44',request.form.get('manager_user_id') or None,request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,now,now,p0['association_id'])); c.commit(); zid=cur.lastrowid; c.close(); log_action('create','zone',zid); flash('Zone créée avec la wilaya et la commune du projet. Reste du projet : '+str(remaining)+' arbre(s).'); return redirect('/zones/'+str(zid))
 c.close(); return page('Nouvelle zone',ZONE_FORM,z=None,managers=managers,cancel_url='/zones',suggested_code=suggested,location_picker=location_picker_markup('zone'),**opts)

@app.route('/zones/<int:zid>')
@login_required
def zone_detail(zid):
 c=db(); z=c.execute("SELECT z.*,p.name project_name,u.name manager_name,w.name wilaya_name,cm.name commune_name FROM zones z LEFT JOIN projects p ON p.id=z.project_id LEFT JOIN users u ON u.id=z.manager_user_id LEFT JOIN wilayas w ON w.id=z.wilaya_id LEFT JOIN communes cm ON cm.id=z.commune_id WHERE z.id=?",(zid,)).fetchone()
 if not z: c.close(); return ('Zone introuvable',404)
 stats={'trees':c.execute('SELECT COUNT(*) n FROM trees WHERE zone_id=? AND active=1',(zid,)).fetchone()['n'],'alive':c.execute("SELECT COUNT(*) n FROM trees WHERE zone_id=? AND active=1 AND health_status NOT IN ('Mort','Perdu')",(zid,)).fetchone()['n'],'priority':c.execute("SELECT COUNT(*) n FROM trees WHERE zone_id=? AND active=1 AND (watering_status!='À jour' OR health_status IN ('À surveiller','Urgent','Critique'))",(zid,)).fetchone()['n'],'teams':c.execute('SELECT COUNT(*) n FROM teams WHERE zone_id=? AND active=1',(zid,)).fetchone()['n'],'missions':c.execute('SELECT COUNT(*) n FROM missions WHERE zone_id=? AND active=1',(zid,)).fetchone()['n'],'waterings':c.execute('SELECT COUNT(*) n FROM watering_logs wl JOIN trees t ON t.id=wl.tree_id WHERE t.zone_id=?',(zid,)).fetchone()['n']}
 stats['survival']=round(100*stats['alive']/stats['trees']) if stats['trees'] else 0
 teams=c.execute("SELECT t.*,u.name leader_name,(SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.status='active') member_count FROM teams t LEFT JOIN users u ON u.id=t.leader_user_id WHERE t.zone_id=? AND t.active=1 ORDER BY t.name",(zid,)).fetchall()
 trees=c.execute("SELECT t.id,t.tree_code,t.species,t.latitude,t.longitude,t.health_status,t.watering_status,t.last_watered_at FROM trees t WHERE t.zone_id=? AND t.active=1 ORDER BY t.id DESC",(zid,)).fetchall()
 missions=c.execute("SELECT id,code,title,status,priority,start_at FROM missions WHERE zone_id=? AND active=1 ORDER BY id DESC LIMIT 8",(zid,)).fetchall()
 history=c.execute("SELECT a.*,u.name user_name FROM activity_log a LEFT JOIN users u ON u.id=a.user_id WHERE (a.entity_type='zone' AND a.entity_id=?) OR (a.entity_type IN ('tree','watering') AND a.entity_id IN (SELECT id FROM trees WHERE zone_id=?)) ORDER BY a.id DESC LIMIT 12",(zid,zid)).fetchall(); c.close()
 tree_data=[dict(x) for x in trees if x['latitude'] is not None and x['longitude'] is not None]
 return page('Tableau de bord zone',"""<div class="section-title"><div><h2>{{z.name}}</h2><span class="badge {% if z.active %}good{% else %}danger{% endif %}">{{'Active' if z.active else 'Archivée'}}</span> <span class="badge watch">{{z.code or 'Sans code'}}</span></div><div>{% if admin %}<a class="btn" href="/zones/{{z.id}}/edit">Modifier</a> <form method="post" action="/zones/{{z.id}}/archive" style="display:inline"><button class="btn red">{{'Archiver' if z.active else 'Réactiver'}}</button></form>{% endif %} <a class="btn alt" href="/zones">Retour</a></div></div><div class="grid kpis" style="grid-template-columns:repeat(6,1fr)">{% for label,value in [('Arbres',stats.trees),('À arroser / surveiller',stats.priority),('Arrosages',stats.waterings),('Équipes',stats.teams),('Missions',stats.missions),('Survie',stats.survival|string+' %')] %}<div class="card kpi"><small>{{label}}</small><b>{{value}}</b></div>{% endfor %}</div><div class="grid two"><div class="card"><h3>Carte de la zone</h3><div id="zoneMap" class="real-map" style="height:420px"></div><div class="sub">{{tree_data|length}} arbre(s) avec coordonnées GPS.</div></div><div class="card"><h3>Informations</h3><p><b>Projet :</b> <a href="/projects/{{z.project_id}}">{{z.project_name or '—'}}</a></p><p><b>Responsable :</b> {{z.manager_name or '—'}}</p><p><b>Wilaya / Commune :</b> {{z.wilaya_name or '—'}} / {{z.commune_name or '—'}}</p><p><b>Superficie :</b> {{z.area or 0}} ha</p><p><b>Objectif :</b> {{stats.trees}} / {{z.target_trees or 0}} arbres</p><p><b>GPS zone :</b> {{z.latitude or '—'}}, {{z.longitude or '—'}}</p>{% if z.latitude and z.longitude %}<p><a class="btn alt" target="_blank" href="https://www.openstreetmap.org/?mlat={{z.latitude}}&mlon={{z.longitude}}#map=17/{{z.latitude}}/{{z.longitude}}">Voir la zone sur la carte</a></p>{% endif %}<p>{{z.description or ''}}</p></div></div><div class="grid two"><div class="card"><h3>Arbres prioritaires</h3><table><tr><th>Arbre</th><th>Espèce</th><th>Santé</th><th>Arrosage</th></tr>{% for t in trees if t.watering_status!='À jour' or t.health_status in ['À surveiller','Urgent','Critique'] %}<tr><td><a href="/trees/{{t.id}}">{{t.tree_code or t.id}}</a></td><td>{{t.species or '—'}}</td><td>{{t.health_status}}</td><td>{{t.watering_status}}</td></tr>{% else %}<tr><td colspan="4">Aucun arbre prioritaire.</td></tr>{% endfor %}</table></div><div class="card"><h3>Équipes affectées</h3>{% for t in teams %}<div class="priority"><b><a href="/teams/{{t.id}}">{{t.name}}</a></b><span>{{t.member_count}} membres • {{t.leader_name or 'Sans chef'}}</span></div>{% else %}<p class="sub">Aucune équipe.</p>{% endfor %}</div></div><div class="grid two"><div class="card"><h3>Missions récentes</h3>{% for m in missions %}<div class="priority"><b><a href="/missions/{{m.id}}">{{m.code}} — {{m.title}}</a></b><span>{{m.status}} • {{m.priority}} • {{m.start_at or '—'}}</span></div>{% else %}<p class="sub">Aucune mission.</p>{% endfor %}</div><div class="card"><h3>Historique récent</h3>{% for h in history %}<div class="priority"><b>{{h.action}} — {{h.entity_type}}</b><span>{{h.user_name or 'Système'}} • {{h.created_at}}</span></div>{% else %}<p class="sub">Aucune activité.</p>{% endfor %}</div></div><script>const zoneTrees={{tree_data|tojson}};const center=[{{z.latitude if z.latitude is not none else 35.697}},{{z.longitude if z.longitude is not none else -0.633}}];const map=L.map('zoneMap').setView(center,15);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(map);const bounds=[];zoneTrees.forEach(t=>{const urgent=t.watering_status!=='À jour'||['À surveiller','Urgent','Critique'].includes(t.health_status);const marker=L.circleMarker([t.latitude,t.longitude],{radius:8,color:urgent?'#bd4747':'#2e7b47',fillOpacity:.85}).addTo(map);marker.bindPopup(`<b>${t.tree_code||'Arbre'}</b><br>${t.species||''}<br>${t.health_status} • ${t.watering_status}<br><a href="/trees/${t.id}">Ouvrir la fiche</a>`);bounds.push([t.latitude,t.longitude]);});{% if z.latitude and z.longitude %}L.marker([{{z.latitude}},{{z.longitude}}]).addTo(map).bindPopup('<b>Centre de la zone</b>');bounds.push([{{z.latitude}},{{z.longitude}}]);{% endif %}if(bounds.length>1)map.fitBounds(bounds,{padding:[25,25],maxZoom:17});setTimeout(()=>map.invalidateSize(),150);</script>""",z=z,stats=stats,teams=teams,trees=trees,missions=missions,history=history,tree_data=tree_data,admin=is_admin())

@app.route('/zones/<int:zid>/edit',methods=['GET','POST'])
@login_required
def zone_edit(zid):
 if not is_admin(): return redirect('/zones')
 c=db(); z=c.execute('SELECT * FROM zones WHERE id=?',(zid,)).fetchone(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if not z: c.close(); return ('Introuvable',404)
 if request.method=='POST':
  project_id=request.form.get('project_id'); allowed,p0=project_owner_allowed(c,project_id,'zone.update'); target=int(request.form.get('target_trees') or 0); ok,remaining=validate_zone_target(c,project_id,target,zid)
  tree_count=c.execute("SELECT COUNT(*) n FROM trees WHERE zone_id=? AND active=1 AND COALESCE(approval_status,'approved')<>'rejected'",(zid,)).fetchone()['n'] or 0
  if not allowed: c.close(); return ('Seule l’association propriétaire du projet peut modifier cette zone.',403)
  if int(project_id)!=int(z['project_id']) and tree_count:
   flash('Impossible de déplacer cette zone vers un autre projet : elle contient déjà '+str(tree_count)+' arbre(s).'); c.close(); return page('Modifier zone',ZONE_FORM,z=z,managers=managers,cancel_url='/zones/'+str(zid),suggested_code=z['code'] or '',location_picker=location_picker_markup('zone'),**opts)
  if target>0 and target<tree_count:
   flash('Objectif impossible : la zone contient déjà '+str(tree_count)+' arbre(s).'); c.close(); return page('Modifier zone',ZONE_FORM,z=z,managers=managers,cancel_url='/zones/'+str(zid),suggested_code=z['code'] or '',location_picker=location_picker_markup('zone'),**opts)
  if not ok:
   flash('Objectif impossible : les zones dépasseraient l’objectif du projet. Reste disponible hors cette zone : '+str(remaining)+' arbre(s).'); c.close(); return page('Modifier zone',ZONE_FORM,z=z,managers=managers,cancel_url='/zones/'+str(zid),suggested_code=z['code'] or '',location_picker=location_picker_markup('zone'),**opts)
  c.execute('UPDATE zones SET project_id=?,wilaya_id=?,commune_id=?,association_id=?,code=?,name=?,area=?,target_trees=?,color=?,manager_user_id=?,active=?,description=?,latitude=?,longitude=?,updated_at=? WHERE id=?',(project_id,p0['wilaya_id'],p0['commune_id'],p0['association_id'],request.form.get('code'),request.form['name'].strip(),request.form.get('area') or 0,target,request.form.get('color') or '#3a7d44',request.form.get('manager_user_id') or None,request.form.get('active',1),request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,datetime.now().isoformat(timespec='minutes'),zid)); c.commit(); c.close(); log_action('edit','zone',zid); flash('Zone modifiée. Wilaya et commune synchronisées avec le projet.'); return redirect('/zones/'+str(zid))
 c.close(); return page('Modifier zone',ZONE_FORM,z=z,managers=managers,cancel_url='/zones/'+str(zid),suggested_code=z['code'] or '',location_picker=location_picker_markup('zone'),**opts)

@app.post('/zones/<int:zid>/archive')
@login_required
def zone_archive(zid):
 if not is_admin(): return redirect('/zones')
 c=db(); z=c.execute('SELECT active FROM zones WHERE id=?',(zid,)).fetchone()
 if z: c.execute('UPDATE zones SET active=?,updated_at=? WHERE id=?',(0 if z['active'] else 1,datetime.now().isoformat(timespec='minutes'),zid)); c.commit()
 c.close(); log_action('archive_toggle','zone',zid); flash('État de la zone mis à jour.'); return redirect('/zones/'+str(zid))

@app.route('/users')
@login_required
def users_page():
 if not is_admin(): return redirect('/')
 c=db(); q=clean(request.args.get('q')); active=request.args.get('active','all'); w=['1=1']; params=[]
 if q:w.append('(u.name LIKE ? OR u.phone LIKE ? OR u.email LIKE ? OR u.username LIKE ?)');params += ['%'+q+'%']*5
 if active in ('0','1'):w.append('u.active=?');params.append(active)
 rows=c.execute('SELECT u.*,r.label role_label FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE '+' AND '.join(w)+' ORDER BY u.active DESC,u.name',params).fetchall(); c.close()
 return page('Utilisateurs et droits','''<div class="section-title"><h2>Utilisateurs</h2><a class="btn" href="/users/new">+ Nouvel utilisateur</a></div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}" placeholder="Nom, téléphone, e-mail, identifiant"></label><label>État<select name="active"><option value="all">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actifs</option><option value="0" {% if active=='0' %}selected{% endif %}>Inactifs</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/users">Annuler</a></form><div class="card"><table><tr><th>Nom</th><th>Identifiant</th><th>Téléphone</th><th>Rôle</th><th>État</th><th>Dernière connexion</th><th>Action</th></tr>{% for u in rows %}<tr><td>{{u.name}}</td><td>{{u.username}}</td><td>{{u.phone}}</td><td>{{u.role_label or u.role}}</td><td><span class="badge {% if u.active %}good{% else %}danger{% endif %}">{{'Actif' if u.active else 'Inactif'}}</span></td><td>{{u.last_login or 'Jamais'}}</td><td><div class="crud-actions"><a class="btn alt" href="/users/{{u.id}}/edit">Modifier</a>{% if u.id != session.uid %}<form method="post" action="/users/{{u.id}}/delete" onsubmit="return confirm('Supprimer ou désactiver cet utilisateur ?')"><button class="btn red">Supprimer</button></form>{% endif %}</div></td></tr>{% endfor %}</table></div>''',rows=rows,q=q,active=active)

@app.route('/users/new',methods=['GET','POST'])
@login_required
def user_new():
 if not is_admin(): return redirect('/')
 c=db(); roles=c.execute('SELECT * FROM roles ORDER BY level DESC').fetchall(); opts=filter_options(c); values=user_form_values(request.form)
 if request.method=='POST':
  password=request.form.get('password',''); username=clean(request.form.get('username')) or values['phone']; errors=validate_user_form(c,values,password_required=True,password=password)
  if c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone(): errors.append('Cet identifiant est déjà utilisé.')
  role=c.execute('SELECT name FROM roles WHERE id=?',(request.form.get('role_id'),)).fetchone()
  if not role: errors.append('Le rôle sélectionné est invalide.')
  if not errors:
   try:
    cur=c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,birth_date,address,skills,availability,photo_url,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],username,generate_password_hash(password),request.form['role_id'],role['name'],1,values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],datetime.now().isoformat(timespec='minutes')));c.commit();uid=cur.lastrowid;c.close();log_action('create','user',uid);flash('Utilisateur ajouté.');return redirect('/users')
   except sqlite3.IntegrityError: errors=['Impossible d’enregistrer cet utilisateur : donnée déjà utilisée.']
  for e in errors: flash(e)
 c.close(); return page('Nouvel utilisateur',USER_FORM,u=None,roles=roles,password_required=True,form_title='Nouvel utilisateur',cancel_url='/users',photo=photo_fields(request.form.get('photo_url',''),prefix='userphoto'),**opts)

USER_FORM='''<div class="card"><h2>{{form_title}}</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{request.form.get('first_name',u.first_name if u else '')}}" required></label><label>Nom<input name="last_name" value="{{request.form.get('last_name',u.last_name if u else '')}}" required></label><label>Sexe<select name="sex">{% set sx=request.form.get('sex',u.sex if u else 'Homme') %}<option {% if sx=='Homme' %}selected{% endif %}>Homme</option><option {% if sx=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone',u.phone if u else '')}}" required></label><label>E-mail<input type="email" name="email" value="{{request.form.get('email',u.email if u and u.email else '')}}"></label><label>Identifiant<input name="username" value="{{request.form.get('username',u.username if u else '')}}" placeholder="Par défaut : téléphone"></label><label>{% if password_required %}Mot de passe{% else %}Nouveau mot de passe (facultatif){% endif %}<input type="password" name="password" minlength="6" {% if password_required %}required{% endif %}></label><label>Rôle<select name="role_id">{% set rid=request.form.get('role_id',u.role_id if u else '') %}{% for r in roles %}<option value="{{r.id}}" {% if rid|string==r.id|string %}selected{% endif %}>{{r.label}}</option>{% endfor %}</select></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% set wid=request.form.get('wilaya_id',u.wilaya_id if u else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% set cid=request.form.get('commune_id',u.commune_id if u else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{request.form.get('address',u.address if u and u.address else '')}}"></label>{% if u %}<label>Compte<select name="active"><option value="1" {% if request.form.get('active',u.active)|string=='1' %}selected{% endif %}>Actif</option><option value="0" {% if request.form.get('active',u.active)|string=='0' %}selected{% endif %}>Inactif</option></select></label>{% endif %}{{photo|safe}}<div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>'''

@app.route('/users/<int:uid>/edit',methods=['GET','POST'])
@login_required
def user_edit(uid):
 if not is_admin(): return redirect('/')
 c=db();u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone();roles=c.execute('SELECT * FROM roles ORDER BY level DESC').fetchall();opts=filter_options(c)
 if not u:c.close();return ('Introuvable',404)
 if request.method=='POST':
  values=user_form_values(request.form); password=request.form.get('password','');username=clean(request.form.get('username')) or values['phone'];errors=validate_user_form(c,values,user_id=uid,password=password)
  existing=c.execute('SELECT id FROM users WHERE username=? AND id<>?',(username,uid)).fetchone()
  if existing: errors.append('Cet identifiant est déjà utilisé.')
  role=c.execute('SELECT name FROM roles WHERE id=?',(request.form.get('role_id'),)).fetchone()
  if not role: errors.append('Le rôle sélectionné est invalide.')
  if uid==session['uid'] and request.form.get('active','1')=='0': errors.append('Vous ne pouvez pas désactiver votre propre compte.')
  if not errors:
   fields=[values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],username,request.form['role_id'],role['name'],int(request.form.get('active','1')),values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url']]
   sql='UPDATE users SET first_name=?,last_name=?,name=?,sex=?,phone=?,email=?,username=?,role_id=?,role=?,active=?,wilaya_id=?,commune_id=?,birth_date=?,address=?,skills=?,availability=?,photo_url=?'
   if password:sql+=',password_hash=?';fields.append(generate_password_hash(password))
   sql+=' WHERE id=?';fields.append(uid);c.execute(sql,fields);c.commit();c.close();log_action('edit','user',uid);flash('Utilisateur modifié.');return redirect('/users')
  for e in errors: flash(e)
 c.close();return page('Modifier utilisateur',USER_FORM,u=u,roles=roles,password_required=False,form_title='Modifier utilisateur',cancel_url='/users',photo=photo_fields(request.form.get('photo_url',u['photo_url'] or ''),prefix='userphoto'),**opts)

@app.route('/roles')
@login_required
def roles_list():
 if not is_admin(): flash('Accès réservé à l’administration.'); return redirect('/')
 c=db(); rows=c.execute('''SELECT r.*,COUNT(DISTINCT u.id) user_count,COUNT(DISTINCT rp.permission_id) permission_count FROM roles r LEFT JOIN users u ON u.role_id=r.id LEFT JOIN role_permissions rp ON rp.role_id=r.id GROUP BY r.id ORDER BY r.level DESC,r.label''').fetchall(); c.close()
 return page('Rôles et droits','''<div class="section-title"><h2>Rôles des bénévoles et droits d’accès</h2><a class="btn" href="/roles/new">+ Nouveau rôle</a></div><div class="card"><table><tr><th>Rôle</th><th>Description</th><th>Niveau</th><th>Utilisateurs</th><th>Droits</th><th>État</th><th></th></tr>{% for r in rows %}<tr><td><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{{r.color}}"></span> <b>{{r.label}}</b><div class="sub">{{r.name}}</div></td><td>{{r.description or '—'}}</td><td>{{r.level}}</td><td>{{r.user_count}}</td><td>{{r.permission_count}}</td><td>{{'Actif' if r.active else 'Archivé'}}</td><td><a class="btn alt" href="/roles/{{r.id}}/edit">Modifier</a> {% if r.name not in ['super_admin','admin','volunteer'] %}<form method="post" action="/roles/{{r.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ce rôle ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% endfor %}</table></div>''',rows=rows)

ROLE_FORM='''<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Nom affiché<input name="label" value="{{request.form.get('label',r.label if r else '')}}" required></label><label>Identifiant technique<input name="name" value="{{request.form.get('name',r.name if r else '')}}" pattern="[a-z0-9_]+" required></label><label>Niveau hiérarchique<input type="number" name="level" value="{{request.form.get('level',r.level if r else 10)}}" min="1" max="99"></label><label>Couleur<input type="color" name="color" value="{{request.form.get('color',r.color if r and r.color else '#2e7b47')}}"></label><label>État<select name="active"><option value="1" {% if request.form.get('active',r.active if r else 1)|string=='1' %}selected{% endif %}>Actif</option><option value="0" {% if request.form.get('active',r.active if r else 1)|string=='0' %}selected{% endif %}>Archivé</option></select></label><label class="full">Description<textarea name="description">{{request.form.get('description',r.description if r and r.description else '')}}</textarea></label><div class="full card"><h3>Droits d’accès</h3><div class="grid two">{% for p in permissions %}<label><input style="width:auto" type="checkbox" name="permissions" value="{{p.id}}" {% if p.id in selected_permissions %}checked{% endif %}> {{p.label}} <span class="sub">({{p.code}})</span></label>{% endfor %}</div></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/roles">Annuler</a></div></form></div>'''

def save_role_permissions(c,rid):
 c.execute('DELETE FROM role_permissions WHERE role_id=?',(rid,))
 for pid in request.form.getlist('permissions'): c.execute('INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)',(rid,pid))

@app.route('/roles/new',methods=['GET','POST'])
@login_required
def role_new():
 if not is_admin(): return redirect('/')
 c=db(); permissions=c.execute('SELECT * FROM permissions ORDER BY label').fetchall()
 if request.method=='POST':
  name=clean(request.form.get('name')).lower().replace(' ','_'); label=clean(request.form.get('label'))
  errors=[]
  if not name or not label: errors.append('Le nom et le libellé sont obligatoires.')
  if c.execute('SELECT 1 FROM roles WHERE name=?',(name,)).fetchone(): errors.append('Cet identifiant de rôle existe déjà.')
  if not errors:
   cur=c.execute('INSERT INTO roles(name,label,description,color,level,active) VALUES(?,?,?,?,?,?)',(name,label,clean(request.form.get('description')),request.form.get('color') or '#2e7b47',int(request.form.get('level') or 10),int(request.form.get('active') or 1))); save_role_permissions(c,cur.lastrowid); c.commit(); c.close(); flash('Rôle enregistré.'); return redirect('/roles')
  for e in errors: flash(e)
 selected_permissions={int(x) for x in request.form.getlist('permissions') if str(x).isdigit()}; c.close(); return page('Nouveau rôle',ROLE_FORM,r=None,permissions=permissions,selected_permissions=selected_permissions)

@app.route('/roles/<int:rid>/edit',methods=['GET','POST'])
@login_required
def role_edit(rid):
 if not is_admin(): return redirect('/')
 c=db(); r=c.execute('SELECT * FROM roles WHERE id=?',(rid,)).fetchone(); permissions=c.execute('SELECT * FROM permissions ORDER BY label').fetchall()
 if not r: c.close(); return ('Introuvable',404)
 if request.method=='POST':
  name=clean(request.form.get('name')).lower().replace(' ','_'); label=clean(request.form.get('label')); errors=[]
  if r['name']=='super_admin': name='super_admin'; request_active=1
  else: request_active=int(request.form.get('active') or 1)
  if not name or not label: errors.append('Le nom et le libellé sont obligatoires.')
  if c.execute('SELECT 1 FROM roles WHERE name=? AND id<>?',(name,rid)).fetchone(): errors.append('Cet identifiant de rôle existe déjà.')
  if not errors:
   c.execute('UPDATE roles SET name=?,label=?,description=?,color=?,level=?,active=? WHERE id=?',(name,label,clean(request.form.get('description')),request.form.get('color') or '#2e7b47',int(request.form.get('level') or 10),request_active,rid)); save_role_permissions(c,rid); c.execute('UPDATE users SET role=? WHERE role_id=?',(name,rid)); c.commit(); c.close(); flash('Rôle et droits modifiés.'); return redirect('/roles')
  for e in errors: flash(e)
 selected_permissions={int(x) for x in request.form.getlist('permissions')} if request.method=='POST' else {x['permission_id'] for x in c.execute('SELECT permission_id FROM role_permissions WHERE role_id=?',(rid,))}; c.close(); return page('Modifier le rôle',ROLE_FORM,r=r,permissions=permissions,selected_permissions=selected_permissions)

@app.post('/roles/<int:rid>/delete')
@login_required
def role_delete(rid):
 if not is_admin(): return redirect('/')
 c=db(); r=c.execute('SELECT * FROM roles WHERE id=?',(rid,)).fetchone()
 if not r: c.close(); return ('Introuvable',404)
 if r['name'] in ('super_admin','admin','volunteer'): flash('Ce rôle système ne peut pas être supprimé.')
 elif c.execute('SELECT 1 FROM users WHERE role_id=? LIMIT 1',(rid,)).fetchone(): flash('Impossible de supprimer un rôle attribué à un utilisateur.')
 else: c.execute('DELETE FROM role_permissions WHERE role_id=?',(rid,)); c.execute('DELETE FROM roles WHERE id=?',(rid,)); c.commit(); flash('Rôle supprimé.')
 c.close(); return redirect('/roles')

@app.route('/activity')
@login_required
def activity():
 c=db(); rows=c.execute('SELECT a.*,u.name user_name FROM activity_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200').fetchall(); c.close(); return page('Journal d’activité','''<div class="card"><table><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Objet</th><th>Détails</th></tr>{% for x in rows %}<tr><td>{{x.created_at}}</td><td>{{x.user_name}}</td><td>{{x.action}}</td><td>{{x.entity_type}} #{{x.entity_id or ''}}</td><td>{{x.details}}</td></tr>{% endfor %}</table></div>''',rows=rows)

@app.route('/api/trees')
@login_required
def api_trees():
 f=filters_from_request(); c=db(); where,params=tree_where(f)
 rows=c.execute("""SELECT t.id,t.tree_code,t.qr_code,t.latitude,t.longitude,t.gps_accuracy,t.health_status,t.watering_status,t.last_watered_at,t.approval_status,t.planted_at,t.notes,t.association_id,s.name_fr species_name,p.name project_name,z.name zone_name,cm.name commune_name,w.name wilaya_name,u.name volunteer_name,a.name association_name,a.map_symbol association_symbol
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN associations a ON a.id=t.association_id LEFT JOIN communes cm ON cm.id=COALESCE(t.commune_id,z.commune_id,p.commune_id) LEFT JOIN wilayas w ON w.id=COALESCE(t.wilaya_id,z.wilaya_id,p.wilaya_id)
 WHERE """+where+" AND t.approval_status='approved' AND t.latitude IS NOT NULL AND t.longitude IS NOT NULL ORDER BY t.id DESC",params).fetchall(); c.close()
 return jsonify([dict(x) for x in rows])

# --- MyTree Professional v2.0 Alpha 4 Lot 5 : carte commune multi-associations ---
def accessible_map_projects(c,ctx):
 """Projects visible in the current context, including accepted read-only collaborations."""
 if ctx.get('type')=='global' and is_super_admin():
  return c.execute("SELECT p.*,a.name association_name,a.map_symbol association_symbol,0 collaborative FROM projects p LEFT JOIN associations a ON a.id=p.association_id WHERE p.active=1 ORDER BY p.name").fetchall()
 if ctx.get('type')=='association' and ctx.get('association_id'):
  aid=ctx['association_id']
  return c.execute("""SELECT DISTINCT p.*,a.name association_name,a.map_symbol association_symbol,
   CASE WHEN p.association_id=? THEN 0 ELSE 1 END collaborative
   FROM projects p LEFT JOIN associations a ON a.id=p.association_id
   LEFT JOIN association_collaborations ac ON ac.project_id=p.id AND ac.invited_association_id=? AND ac.status='accepted' AND ac.can_view=1
   WHERE p.active=1 AND (p.association_id=? OR ac.id IS NOT NULL) ORDER BY collaborative,p.name""",(aid,aid,aid)).fetchall()
 return []

def map_resource_allowed(c,ctx,association_id=None,project_id=None):
 # RC16.13 Map visibility fix:
 # - la Carte commune est une vue de lecture : un compte Personnel peut voir tous les
 #   arbres validés/géolocalisés, même s'ils appartiennent à un projet ou une association;
 # - le filtre quick=mine limite ensuite explicitement la requête aux arbres du bénévole;
 # - un compte Association reste limité à son périmètre/collaborations, sauf quand il
 #   demande explicitement la Carte globale avec scope=global.
 if ctx.get('type')=='global' and is_super_admin(): return True
 if request.args.get('scope')=='global' and ctx.get('type') in ('personal','association'): return True
 if ctx.get('type')=='personal': return True
 aid=ctx.get('association_id')
 if not aid: return False
 if association_id is not None and int(association_id or 0)==int(aid): return True
 if project_id:
  owner=c.execute("SELECT association_id FROM projects WHERE id=? AND active=1",(project_id,)).fetchone()
  if owner and owner['association_id'] is not None and int(owner['association_id'])==int(aid): return True
  return collaboration_access(c,project_id,aid,'can_view')
 return False

@app.route('/api/map-data')
@login_required
def api_map_data():
 f=filters_from_request(); c=db()
 ctx=active_context(c); uid=session.get('uid'); types=set(request.args.getlist('type')) or {'tree'}
 projects=list(accessible_filter_projects(c,ctx)); project_ids={int(x['id']) for x in projects}; data=[]
 def add(kind,row,title,subtitle='',url=''):
  # MapFix 2 — certaines ressources (notamment projects) n'ont pas de colonnes GPS.
  # Ne jamais lever d'exception : ignorer proprement les ressources non géolocalisables.
  keys=set(row.keys())
  if 'latitude' not in keys or 'longitude' not in keys: return
  lat=row['latitude']; lon=row['longitude']
  if lat is None or lon is None: return
  data.append({'type':kind,'id':row['id'],'lat':lat,'lon':lon,'title':title,'subtitle':subtitle,'url':url,
               'association_id':row['association_id'] if 'association_id' in keys else None,
               'project_id':row['project_id'] if 'project_id' in keys else None})
 if 'tree' in types:
  where,args=['t.active=1',"t.approval_status='approved'",'t.latitude IS NOT NULL','t.longitude IS NOT NULL'],[]
  if f.get('quick')=='mine': where.append('t.planted_by_user_id=?'); args.append(uid)
  for key,col in [('project_id','t.project_id'),('zone_id','t.zone_id'),('species_id','t.species_id'),('volunteer_id','t.planted_by_user_id'),('health_status','t.health_status'),('watering_status','t.watering_status')]:
   if f.get(key): where.append(col+'=?'); args.append(f[key])
  if f.get('association_id'): where.append('t.association_id=?'); args.append(f['association_id'])
  q="""SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name,a.name association_name,a.map_symbol association_symbol FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN associations a ON a.id=t.association_id WHERE """+' AND '.join(where)
  for r in c.execute(q,args).fetchall():
   if map_resource_allowed(c,ctx,r['association_id'],r['project_id']): add('tree',r,r['tree_code'] or 'Arbre',(r['species_name'] or r['species'] or '')+' · '+(r['project_name'] or 'Hors projet'),'/tree/'+str(r['id']))
 if ctx.get('type')!='personal' and project_ids:
  marks=','.join('?'*len(project_ids))
  if 'project' in types:
   for r in projects:
    if f['project_id'] and str(r['id'])!=str(f['project_id']): continue
    if f['wilaya_id'] and str(r['wilaya_id'] or '')!=str(f['wilaya_id']): continue
    if f['commune_id'] and str(r['commune_id'] or '')!=str(f['commune_id']): continue
    add('project',r,r['name'],'Projet'+(' · collaboration' if r['collaborative'] else ''),'/projects/'+str(r['id']))
  if 'zone' in types:
   q=f"SELECT z.*,p.name project_name,p.wilaya_id project_wilaya_id,p.commune_id project_commune_id FROM zones z LEFT JOIN projects p ON p.id=z.project_id WHERE z.active=1 AND z.project_id IN ({marks}) AND z.latitude IS NOT NULL AND z.longitude IS NOT NULL"; args=list(sorted(project_ids))
   if f['project_id']: q+=' AND z.project_id=?'; args.append(f['project_id'])
   if f['zone_id']: q+=' AND z.id=?'; args.append(f['zone_id'])
   if f['wilaya_id']: q+=' AND COALESCE(z.wilaya_id,p.wilaya_id)=?'; args.append(f['wilaya_id'])
   if f['commune_id']: q+=' AND COALESCE(z.commune_id,p.commune_id)=?'; args.append(f['commune_id'])
   for r in c.execute(q,args).fetchall(): add('zone',r,r['name'],'Zone · '+(r['project_name'] or ''),'/zones/'+str(r['id']))
  if 'event' in types:
   q=f"SELECT e.*,p.name project_name FROM events e LEFT JOIN projects p ON p.id=e.project_id WHERE e.active=1 AND e.project_id IN ({marks}) AND e.latitude IS NOT NULL AND e.longitude IS NOT NULL"; args=list(sorted(project_ids))
   if f['project_id']: q+=' AND e.project_id=?'; args.append(f['project_id'])
   if f['zone_id']: q+=' AND e.zone_id=?'; args.append(f['zone_id'])
   if f['status']: q+=' AND e.status=?'; args.append(f['status'])
   if f['action_type']: q+=' AND e.event_type=?'; args.append(f['action_type'])
   if f['date_from']: q+=' AND date(e.start_at)>=date(?)'; args.append(f['date_from'])
   if f['date_to']: q+=' AND date(e.start_at)<=date(?)'; args.append(f['date_to'])
   if f['wilaya_id']: q+=' AND p.wilaya_id=?'; args.append(f['wilaya_id'])
   if f['commune_id']: q+=' AND p.commune_id=?'; args.append(f['commune_id'])
   for r in c.execute(q,args).fetchall(): add('event',r,r['title'],'Événement · '+(r['project_name'] or ''),'/events/'+str(r['id']))
  if 'mission' in types:
   q=f"SELECT m.*,p.name project_name FROM missions m LEFT JOIN projects p ON p.id=m.project_id WHERE m.active=1 AND m.project_id IN ({marks}) AND m.latitude IS NOT NULL AND m.longitude IS NOT NULL"; args=list(sorted(project_ids))
   if f['project_id']: q+=' AND m.project_id=?'; args.append(f['project_id'])
   if f['zone_id']: q+=' AND m.zone_id=?'; args.append(f['zone_id'])
   if f['status']: q+=' AND m.status=?'; args.append(f['status'])
   if f['priority']: q+=' AND m.priority=?'; args.append(f['priority'])
   if f['action_type']: q+=' AND m.mission_type=?'; args.append(f['action_type'])
   if f['volunteer_id']: q+=' AND (m.leader_user_id=? OR EXISTS(SELECT 1 FROM mission_participants mp WHERE mp.mission_id=m.id AND mp.user_id=?))'; args += [f['volunteer_id'],f['volunteer_id']]
   if f['date_from']: q+=' AND date(m.start_at)>=date(?)'; args.append(f['date_from'])
   if f['date_to']: q+=' AND date(m.start_at)<=date(?)'; args.append(f['date_to'])
   if f['wilaya_id']: q+=' AND p.wilaya_id=?'; args.append(f['wilaya_id'])
   if f['commune_id']: q+=' AND p.commune_id=?'; args.append(f['commune_id'])
   for r in c.execute(q,args).fetchall(): add('mission',r,r['title'],'Mission · '+(r['project_name'] or ''),'/missions/'+str(r['id']))
 c.close(); return jsonify({'context':ctx,'filters':f,'items':data})

@app.route('/map')
@login_required
def real_map():
 f=filters_from_request(); c=db(); ctx=active_context(c); opts=common_filter_options(c,f)
 opts['associations']=c.execute("SELECT id,name,map_symbol FROM associations WHERE status='active' ORDER BY name").fetchall()
 # La carte est publique en lecture pour les arbres; la liste de bénévoles sert seulement au filtre.
 opts['volunteers']=c.execute("SELECT id,name FROM users WHERE active=1 AND (role='volunteer' OR role_id IN (SELECT id FROM roles WHERE name='volunteer')) ORDER BY name").fetchall()
 c.close()
 return page('Carte commune',"""<div class='section-title'><div><h2>🗺 Carte commune</h2><p class='sub'>Par défaut, seuls les arbres sont affichés. Ajoutez Zones ou Événements depuis Filtrer.</p></div></div><div class='map-filter-bar noprint'>{% if ctx.type=='personal' %}<a class='btn {% if f.quick=="mine" %}active{% else %}alt{% endif %}' href='/map?quick=mine'>👤 Ma carte</a><a class='btn {% if f.quick!="mine" %}active{% else %}alt{% endif %}' href='/map'>🌐 Carte globale</a>{% elif ctx.type=='association' %}<a class='btn {% if request.args.get("scope")!="global" %}active{% else %}alt{% endif %}' href='/map'>🏛 Carte Association</a><a class='btn {% if request.args.get("scope")=="global" %}active{% else %}alt{% endif %}' href='/map?scope=global'>🌐 Carte globale</a>{% endif %}</div><div class='map-filter-bar noprint'><button class='btn' type='button' id='toggleMapFilters'>🔎 Filtrer</button>{% if f.quick=='mine' %}<span class='badge good'>👤 Mes arbres ✓</span><a class='btn alt' href='/map'>✕ Supprimer le filtre</a>{% endif %}<span id='activeFilterSummary' class='sub'></span></div><form id='mapFilters' class='card map-filter-drawer noprint' method='get' aria-hidden='true'><div class='section-title'><h3>🔎 Filtres de la carte</h3><button class='btn alt' type='button' id='closeMapFilters'>Fermer</button></div>{% if f.quick %}<input type='hidden' name='quick' value='{{f.quick}}'>{% endif %}<div class='card'><b>Afficher sur la carte</b><div class='map-layer-choices'><label><input type='checkbox' name='type' value='tree' checked> 🌳 Arbres</label><label><input type='checkbox' name='type' value='zone' {% if 'zone' in request.args.getlist('type') %}checked{% endif %}> 🟩 Zones</label><label><input type='checkbox' name='type' value='event' {% if 'event' in request.args.getlist('type') %}checked{% endif %}> 📆 Événements</label></div></div><div class='map-filter-grid'><label>Association<select name='association_id'><option value=''>Toutes</option>{% for a in associations %}<option value='{{a.id}}' {% if f.association_id|string==a.id|string %}selected{% endif %}>{{a.map_symbol or '🌳'}} {{a.name}}</option>{% endfor %}</select></label><label>Projet<select name='project_id'><option value=''>Tous</option>{% for p in projects %}<option value='{{p.id}}' {% if f.project_id|string==p.id|string %}selected{% endif %}>{{p.name}}</option>{% endfor %}</select></label><label>Zone<select name='zone_id'><option value=''>Toutes</option>{% for z in zones %}<option value='{{z.id}}' {% if f.zone_id|string==z.id|string %}selected{% endif %}>{{z.name}}</option>{% endfor %}</select></label><label>Espèce<select name='species_id'><option value=''>Toutes</option>{% for x in species %}<option value='{{x.id}}' {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><label>Bénévole<select name='volunteer_id'><option value=''>Tous</option>{% for x in volunteers %}<option value='{{x.id}}' {% if f.volunteer_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Santé<select name='health_status'><option value=''>Toutes</option>{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if f.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Arrosage<select name='watering_status'><option value=''>Tous</option>{% for x in ['À jour','À arroser','Urgent'] %}<option {% if f.watering_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label></div><div class='map-filter-actions'><button class='btn'>Appliquer</button><a class='btn alt' href='/map'>Réinitialiser</a></div></form><div class='map-filter-bar noprint'><button class='btn alt' type='button' id='locateBtn'>📍 Ma position</button></div><div class='card'><b id='resultCount'>Chargement…</b></div><div class='grid two map-layout'><div class='card'><div id='map' class='real-map'></div></div><div class='card'><h3>Éléments proches</h3><div id='locationStatus' class='sub'>Utilisez « Ma position » pour calculer les distances.</div><div id='nearbyList'></div></div></div><script>(function(){const qp=new URLSearchParams(location.search);if(!qp.getAll('type').length)qp.append('type','tree');const box=mapFilters,open=toggleMapFilters,close=closeMapFilters;function drawer(v){box.classList.toggle('open',v);box.setAttribute('aria-hidden',v?'false':'true');(v?close:open).focus()}open.onclick=()=>drawer(true);close.onclick=()=>drawer(false);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&box.classList.contains('open'))drawer(false)});const map=L.map('map').setView([35.697,-0.633],11),group=L.featureGroup().addTo(map);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'&copy; OpenStreetMap'}).addTo(map);let items=[],me=null,meMarker=null;const icons={tree:'🌳',zone:'🟩',event:'📆'};const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));function icon(x){return L.divIcon({className:'tree-emoji-marker map-common-marker',html:'<span>'+icons[x.type]+'</span>',iconSize:[32,32],iconAnchor:[16,27]})}function pop(x){let h='<b>'+icons[x.type]+' '+esc(x.title)+'</b><br>'+esc(x.subtitle);if(x.url)h+='<br><a href="'+x.url+'">Voir la fiche</a>';if(x.type==='tree')h+='<br><a target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(x.lat+','+x.lon)+'">📍 Itinéraire</a>';return h}fetch('/api/map-data?'+qp).then(r=>r.ok?r.json():Promise.reject()).then(p=>{items=p.items||[];resultCount.textContent=items.length+' élément(s) visible(s)';items.forEach(x=>L.marker([x.lat,x.lon],{icon:icon(x)}).bindPopup(pop(x)).addTo(group));if(items.length)map.fitBounds(group.getBounds().pad(.18),{maxZoom:16})}).catch(()=>resultCount.textContent='Impossible de charger la carte.');locateBtn.onclick=()=>navigator.geolocation&&navigator.geolocation.getCurrentPosition(p=>{me={lat:p.coords.latitude,lng:p.coords.longitude};if(meMarker)map.removeLayer(meMarker);meMarker=L.marker(me).addTo(map).bindPopup('Votre position');map.setView(me,15);locationStatus.textContent='Position obtenue.'},()=>locationStatus.textContent='Position refusée ou indisponible.');})();</script>""",ctx=ctx,f=f,**opts)

@app.route('/trees/<int:tid>/map')
@login_required
def tree_map(tid):
 c=db(); t=c.execute("""SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.id=? AND t.active=1""",(tid,)).fetchone(); c.close()
 if not t: return ('Arbre introuvable',404)
 if t['latitude'] is None or t['longitude'] is None:
  flash('Cet arbre ne possède pas encore de coordonnées GPS.'); return redirect('/tree/'+str(tid))
 return page('Carte de l’arbre',"""<div class="section-title"><h2>{{t.tree_code}} — {{t.species_name or t.species}}</h2><div><a class="btn alt" href="/tree/{{t.id}}">Fiche arbre</a> <a class="btn" href="/watering?tree_id={{t.id}}">Arroser</a></div></div><div class="card"><div id="treeMap" class="real-map"></div><p id="routeInfo" class="sub">La position de l’utilisateur et l’itinéraire seront affichés après autorisation GPS.</p></div><script>
const tree=[{{t.latitude}},{{t.longitude}}];
const map=L.map('treeMap',{zoomControl:true}).setView(tree,18);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'&copy; OpenStreetMap'}).addTo(map);
L.marker(tree).addTo(map).bindPopup(`<b>{{t.tree_code}}</b><br>{{t.species_name or t.species}}<br>{{t.project_name or ''}} — {{t.zone_name or ''}}<hr><a href="/tree/{{t.id}}">Fiche</a> · <a href="/watering?tree_id={{t.id}}">Arroser</a> · <a href="/trees/{{t.id}}/photo/new">Photo</a> · <a href="/trees/{{t.id}}/observation/new">Observation</a> · <a href="/trees/{{t.id}}/gps">Modifier GPS</a>`).openPopup();
setTimeout(()=>map.invalidateSize(true),150);
if(navigator.geolocation){navigator.geolocation.getCurrentPosition(p=>{const me=[p.coords.latitude,p.coords.longitude];L.circleMarker(me,{radius:9}).addTo(map).bindPopup('Votre position');const line=L.polyline([me,tree],{dashArray:'7,7'}).addTo(map);map.fitBounds(line.getBounds().pad(.25));const url=`https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${me[0]}%2C${me[1]}%3B${tree[0]}%2C${tree[1]}`;document.getElementById('routeInfo').innerHTML=`<a class="btn" target="_blank" rel="noopener" href="${url}">Ouvrir l’itinéraire réel</a>`;setTimeout(()=>map.invalidateSize(true),100)},()=>{document.getElementById('routeInfo').textContent='Position utilisateur non autorisée. La position de l’arbre reste visible.'},{enableHighAccuracy:true,timeout:12000})}
</script>""",t=t)

@app.route('/qr',methods=['GET','POST'])
@login_required
def qr_selection():
 c=db(); f=filters_from_request(); where,params=tree_where(f); opts=filter_options(c)
 rows=c.execute("""SELECT t.id,t.tree_code,t.qr_code,s.name_fr species_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE """+where+" AND t.approval_status='approved' ORDER BY t.tree_code",params).fetchall(); c.close()
 selected={int(x) for x in request.form.getlist('tree_ids') if x.isdigit()} if request.method=='POST' else set(); printing=request.method=='POST' and bool(selected)
 layout=request.form.get('layout','12') if request.method=='POST' else '12'
 if layout not in {'1','6','12','24','thermal'}: layout='12'
 return page('QR codes',"""<form method="get" class="card toolbar noprint"><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/qr">Effacer</a></form>
 {% if not printing %}<form method="post"><div class="card noprint"><div class="section-title"><h3>Sélectionner les arbres à imprimer</h3><div><button type="button" class="btn alt" onclick="document.querySelectorAll('[name=tree_ids]').forEach(x=>x.checked=true)">Tout sélectionner</button></div></div><div class="toolbar"><label>Format d'impression<select name="layout"><option value="1">A4 — 1 grand QR</option><option value="6">A4 — 6 QR</option><option value="12" selected>A4 — 12 QR (recommandé)</option><option value="24">A4 — 24 petits QR</option><option value="thermal">Thermique 58/80 mm</option></select></label><button class="btn">Préparer l’impression</button></div><div class="compact-table"><table><tr><th></th><th>Code</th><th>Espèce</th><th>Projet</th><th>Zone</th></tr>{% for t in rows %}<tr><td><input style="width:auto" type="checkbox" name="tree_ids" value="{{t.id}}"></td><td>{{t.tree_code}}</td><td>{{t.species_name}}</td><td>{{t.project_name or 'À classer'}}</td><td>{{t.zone_name or 'À classer'}}</td></tr>{% endfor %}</table></div></div></form>{% else %}<div class="toolbar noprint"><button class="btn" onclick="window.print()">Imprimer</button><a class="btn alt" href="/qr">Nouvelle sélection</a><span class="badge good">Format : {{layout}}</span></div><div class="qr-grid qr-{{layout}}">{% for t in rows if t.id in selected %}<div class="qr-label"><img src="/qr/{{t.id}}.png" alt="QR {{t.tree_code}}"><h3>{{t.tree_code}}</h3><div>{{t.species_name}}</div><small>{{t.project_name or 'À classer'}} — {{t.zone_name or 'À classer'}}</small></div>{% endfor %}</div>{% endif %}""",rows=rows,selected=selected,printing=printing,layout=layout,f=f,**opts)

@app.route('/tree/<int:tid>')
@login_required
def tree_detail(tid):
 c=db(); t=c.execute("""SELECT t.*,s.name_fr species_name,s.scientific_name,p.name project_name,z.name zone_name,cm.name commune_name,w.name wilaya_name,u.name volunteer_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN communes cm ON cm.id=COALESCE(t.commune_id,z.commune_id,p.commune_id) LEFT JOIN wilayas w ON w.id=COALESCE(t.wilaya_id,z.wilaya_id,p.wilaya_id) LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE t.id=? AND t.active=1""",(tid,)).fetchone()
 if not t: c.close(); return ('Arbre introuvable',404)
 token=request.args.get('token')
 if token and token!=t['qr_code']: c.close(); return ('QR invalide',403)
 photos=c.execute("SELECT tp.*,u.name author_name FROM tree_photos tp LEFT JOIN users u ON u.id=tp.created_by_user_id WHERE tp.tree_id=? ORDER BY tp.id DESC",(tid,)).fetchall()
 observations=c.execute("SELECT o.*,u.name author_name FROM tree_observations o LEFT JOIN users u ON u.id=o.created_by_user_id WHERE o.tree_id=? ORDER BY o.id DESC LIMIT 10",(tid,)).fetchall()
 waterings=c.execute("SELECT wl.*,u.name user_name FROM watering_logs wl LEFT JOIN users u ON u.id=wl.user_id WHERE wl.tree_id=? ORDER BY wl.id DESC LIMIT 10",(tid,)).fetchall(); interventions=c.execute("SELECT i.*,u.name user_name,m.title mission_title FROM interventions i LEFT JOIN users u ON u.id=i.user_id LEFT JOIN missions m ON m.id=i.mission_id WHERE i.tree_id=? ORDER BY COALESCE(i.performed_at,i.planned_at,i.created_at) DESC LIMIT 12",(tid,)).fetchall(); c.close()
 return page('Fiche arbre',"""<div class="section-title"><div><h2>{{t.tree_code or ('Plantation #' ~ t.id)}}</h2><span class="badge {% if t.approval_status=='approved' %}good{% elif t.approval_status=='pending' %}watch{% else %}danger{% endif %}">{{'Acceptée' if t.approval_status=='approved' else ('En attente' if t.approval_status=='pending' else 'Refusée')}}</span></div><div>{% if admin and t.approval_status=='pending' %}<form method="post" action="/plantings/{{t.id}}/approve" style="display:inline"><button class="btn">Accepter</button></form> <form method="post" action="/plantings/{{t.id}}/reject" style="display:inline"><input name="reason" placeholder="Motif du refus" style="width:150px;display:inline" required><button class="btn red">Refuser</button></form> {% endif %}{% if t.latitude is not none and t.longitude is not none %}<a class="btn amber" target="_blank" href="https://www.google.com/maps/dir/?api=1&destination={{t.latitude}},{{t.longitude}}">🧭 Itinéraire</a> {% endif %}<a class="btn" href="/trees/{{t.id}}/map">Carte réelle</a> <a class="btn alt" href="/watering?tree_id={{t.id}}">Arroser</a> <a class="btn alt" href="/trees/{{t.id}}/photo/new">Ajouter photo</a> <a class="btn alt" href="/trees/{{t.id}}/observation/new">Observation</a> <a class="btn alt" href="/trees/{{t.id}}/interventions/new">Nouvelle intervention</a> <a class="btn alt" href="/trees/{{t.id}}/gps">Modifier GPS</a> <a class="btn alt" href="/trees/{{t.id}}/history">Historique</a> <a class="btn alt" href="/trees/{{t.id}}/edit">Modifier</a></div></div>
 <div class="grid two"><div class="card"><h3>Identification</h3><p><b>Identifiant :</b> {{t.tree_code}}</p><p><b>Espèce :</b> {{t.species_name or t.species}}{% if t.scientific_name %} — <i>{{t.scientific_name}}</i>{% endif %}</p><p><b>Wilaya / Commune :</b> {{t.wilaya_name or '—'}} / {{t.commune_name or '—'}}</p><p><b>Projet / Zone :</b> {{t.project_name or '—'}} / {{t.zone_name or '—'}}</p><p><b>Planté par :</b> {{t.volunteer_name or t.planted_by or '—'}}</p><p><b>Date :</b> {{t.planted_at or '—'}}</p><p><b>Type :</b> {{t.planting_type or 'simple'}}</p><p><b>Notes :</b> {{t.notes or '—'}}</p></div>
 <div class="card"><h3>Suivi terrain</h3><p><b>Santé :</b> {{t.health_status}}</p><p><b>Arrosage :</b> {{t.watering_status}}</p><p><b>Dernier arrosage :</b> {{t.last_watered_at or '—'}}</p><p><b>GPS :</b> {{t.latitude if t.latitude is not none else '—'}}, {{t.longitude if t.longitude is not none else '—'}}</p><p><b>Précision :</b> {{t.gps_accuracy or '—'}} m</p><div style="text-align:center"><div class="sub">{% if t.approval_status=='pending' %}QR provisoire — en attente de validation{% endif %}</div><img src="/qr/{{t.id}}.png" alt="QR {{t.tree_code}}" style="max-width:180px"><div><a href="/qr/{{t.id}}.png" target="_blank">Ouvrir / imprimer le QR</a></div></div></div></div>
 <div class="card"><div class="section-title"><h3>Photos</h3><a href="/trees/{{t.id}}/photo/new">Ajouter</a></div><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">{% for p in photos %}<div><img src="{{p.photo_url}}" alt="Photo arbre" style="width:100%;height:160px;object-fit:cover;border-radius:10px"><p>{{p.caption or ''}}</p><small>{{p.created_at}} — {{p.author_name or 'Utilisateur'}}</small></div>{% else %}<p class="sub">Aucune photo.</p>{% endfor %}</div></div>
 <div class="grid two"><div class="card"><h3>Dernières observations</h3>{% for o in observations %}<div class="priority"><b>{{o.health_status or 'Observation'}}</b><span>{{o.observation}}<br>{{o.created_at}} — {{o.author_name or 'Utilisateur'}}</span></div>{% else %}<p class="sub">Aucune observation.</p>{% endfor %}</div><div class="card"><h3>Derniers arrosages</h3>{% for w in waterings %}<div class="priority"><b>{{w.watered_at}}</b><span>{{w.quantity_range or '—'}} • {{w.source or '—'}} • {{w.user_name or w.volunteer or 'Utilisateur'}}</span></div>{% else %}<p class="sub">Aucun arrosage.</p>{% endfor %}</div></div><div class="card"><div class="section-title"><h3>Interventions</h3><a class="btn" href="/trees/{{t.id}}/interventions/new">Ajouter</a></div><table><tr><th>Date</th><th>Type</th><th>État</th><th>Utilisateur</th><th>Prochaine échéance</th></tr>{% for i in interventions %}<tr><td>{{i.performed_at or i.planned_at or i.created_at}}</td><td><b>{{i.intervention_type}}</b>{% if i.mission_title %}<br><small>{{i.mission_title}}</small>{% endif %}</td><td>{{i.status}}</td><td>{{i.user_name or 'Utilisateur'}}</td><td>{{i.next_due_at or '—'}}</td></tr>{% else %}<tr><td colspan="5">Aucune intervention.</td></tr>{% endfor %}</table></div>""",t=t,photos=photos,observations=observations,waterings=waterings,interventions=interventions,admin=is_admin())

@app.route('/trees/<int:tid>/photo/new',methods=['GET','POST'])
@login_required
def tree_photo_new(tid):
 c=db(); t=c.execute('SELECT id,tree_code FROM trees WHERE id=? AND active=1',(tid,)).fetchone()
 if not t: c.close(); return ('Arbre introuvable',404)
 if request.method=='POST':
  url=request.form.get('photo_url','').strip()
  if not url: flash('Choisissez une photo ou prenez une photo.')
  else:
   c.execute('INSERT INTO tree_photos(tree_id,photo_url,caption,created_by_user_id,created_at) VALUES(?,?,?,?,?)',(tid,url,request.form.get('caption','').strip(),session['uid'],datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close(); log_action('add_photo','tree',tid,url); flash('Photo ajoutée.'); return redirect('/tree/'+str(tid))
 c.close(); return page('Ajouter une photo',"""<div class="card"><h2>{{t.tree_code}}</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}">{{photo|safe}}<label class="full">Légende<input name="caption"></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/tree/{{t.id}}">Annuler</a></div></form></div>""",t=t,photo=photo_fields(prefix='treephoto'))

@app.route('/trees/<int:tid>/observation/new',methods=['GET','POST'])
@login_required
def tree_observation_new(tid):
 c=db(); t=c.execute('SELECT id,tree_code,health_status FROM trees WHERE id=? AND active=1',(tid,)).fetchone()
 if not t: c.close(); return ('Arbre introuvable',404)
 if request.method=='POST':
  text=request.form.get('observation','').strip(); health=request.form.get('health_status') or t['health_status']
  if not text: flash('L’observation est obligatoire.')
  else:
   now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO tree_observations(tree_id,observation,health_status,photo_url,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(tid,text,health,request.form.get('photo_url') or None,session['uid'],now)); c.execute('UPDATE trees SET health_status=? WHERE id=?',(health,tid)); c.commit(); c.close(); log_action('observe','tree',tid,text); flash('Observation enregistrée.'); return redirect('/tree/'+str(tid))
 c.close(); return page('Ajouter une observation',"""<div class="card"><h2>{{t.tree_code}}</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>État de santé<select name="health_status">{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if t.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label class="full">Observation<textarea name="observation" required></textarea></label>{{photo|safe}}<div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/tree/{{t.id}}">Annuler</a></div></form></div>""",t=t,photo=photo_fields(prefix='observation'))

@app.route('/trees/<int:tid>/gps',methods=['GET','POST'])
@login_required
def tree_gps_update(tid):
 c=db(); t=c.execute('SELECT * FROM trees WHERE id=? AND active=1',(tid,)).fetchone()
 if not t: c.close(); return ('Arbre introuvable',404)
 if request.method=='POST':
  try: lat=float(request.form['latitude']); lon=float(request.form['longitude'])
  except (ValueError,KeyError): flash('Coordonnées GPS invalides.'); c.close(); return redirect('/trees/'+str(tid)+'/gps')
  if not (-90<=lat<=90 and -180<=lon<=180): flash('Coordonnées hors limites.'); c.close(); return redirect('/trees/'+str(tid)+'/gps')
  acc=request.form.get('gps_accuracy') or None; reason=request.form.get('reason','').strip(); now=datetime.now().isoformat(timespec='minutes')
  c.execute('INSERT INTO tree_gps_history(tree_id,old_latitude,old_longitude,new_latitude,new_longitude,accuracy,changed_by_user_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(tid,t['latitude'],t['longitude'],lat,lon,acc,session['uid'],reason,now)); c.execute('UPDATE trees SET latitude=?,longitude=?,gps_accuracy=? WHERE id=?',(lat,lon,acc,tid)); c.commit(); c.close(); log_action('gps_update','tree',tid,reason); flash('Position GPS mise à jour.'); return redirect('/trees/'+str(tid)+'/map')
 c.close(); return page('Modifier le GPS',"""<div class="card"><h2>{{t.tree_code}}</h2><p class="sub">Choisissez la position sur la carte ou utilisez la position actuelle de l'utilisateur connecté.</p><div id="gpsMap" class="real-map" style="height:390px;margin-bottom:14px"></div><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Latitude<input id="gpsLat" name="latitude" type="number" step="any" value="{{t.latitude if t.latitude is not none else ''}}" required></label><label>Longitude<input id="gpsLon" name="longitude" type="number" step="any" value="{{t.longitude if t.longitude is not none else ''}}" required></label><label>Précision (m)<input id="gpsAcc" name="gps_accuracy" type="number" step="any" value="{{t.gps_accuracy or ''}}"></label><label class="full">Motif du déplacement / correction<input name="reason" placeholder="Correction GPS, déplacement, contrôle terrain..."></label><div class="full"><button type="button" class="btn alt" onclick="captureGps()">📍 Utiliser ma position / position du bénévole</button> <span id="gpsStatus" class="sub"></span></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/tree/{{t.id}}">Annuler</a></div></form></div><script>const initial=[{{t.latitude if t.latitude is not none else 35.697}},{{t.longitude if t.longitude is not none else -0.633}}];const gm=L.map('gpsMap').setView(initial,17);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20}).addTo(gm);const marker=L.marker(initial,{draggable:true}).addTo(gm);function applyPos(ll){gpsLat.value=ll.lat.toFixed(7);gpsLon.value=ll.lng.toFixed(7);marker.setLatLng(ll)}marker.on('dragend',e=>{applyPos(e.target.getLatLng());gpsStatus.textContent='Position choisie manuellement sur la carte.'});gm.on('click',e=>{applyPos(e.latlng);gpsStatus.textContent='Position choisie manuellement sur la carte.'});function captureGps(){const s=document.getElementById('gpsStatus');if(!navigator.geolocation){s.textContent='GPS non disponible.';return}s.textContent='Recherche de la position...';navigator.geolocation.getCurrentPosition(p=>{const ll={lat:p.coords.latitude,lng:p.coords.longitude};applyPos(ll);gm.setView(ll,18);gpsAcc.value=p.coords.accuracy||'';const a=Math.round(p.coords.accuracy||0);s.className='gps-quality '+(a<=5?'gps-good':a<=15?'gps-medium':'gps-bad');s.textContent='Position récupérée — précision '+a+' m.'},()=>s.textContent='Impossible de récupérer la position.',{enableHighAccuracy:true,timeout:12000,maximumAge:0})}setTimeout(()=>gm.invalidateSize(),100)</script>""",t=t)

@app.route('/trees/<int:tid>/history')
@login_required
def tree_history(tid):
 c=db(); t=c.execute('SELECT id,tree_code FROM trees WHERE id=?',(tid,)).fetchone()
 if not t: c.close(); return ('Arbre introuvable',404)
 events=[]
 for r in c.execute("SELECT watered_at dt,'Arrosage' type,COALESCE(quantity_range,'')||' '||COALESCE(source,'') detail,COALESCE(u.name,wl.volunteer,'Utilisateur') author FROM watering_logs wl LEFT JOIN users u ON u.id=wl.user_id WHERE tree_id=?",(tid,)): events.append(dict(r))
 for r in c.execute("SELECT o.created_at dt,'Observation' type,o.observation detail,COALESCE(u.name,'Utilisateur') author FROM tree_observations o LEFT JOIN users u ON u.id=o.created_by_user_id WHERE tree_id=?",(tid,)): events.append(dict(r))
 for r in c.execute("SELECT g.created_at dt,'GPS' type,'Nouvelle position : '||g.new_latitude||', '||g.new_longitude||CASE WHEN g.reason IS NOT NULL AND g.reason<>'' THEN ' — '||g.reason ELSE '' END detail,COALESCE(u.name,'Utilisateur') author FROM tree_gps_history g LEFT JOIN users u ON u.id=g.changed_by_user_id WHERE tree_id=?",(tid,)): events.append(dict(r))
 for r in c.execute("SELECT p.created_at dt,'Photo' type,COALESCE(p.caption,p.photo_url) detail,COALESCE(u.name,'Utilisateur') author FROM tree_photos p LEFT JOIN users u ON u.id=p.created_by_user_id WHERE tree_id=?",(tid,)): events.append(dict(r))
 for r in c.execute("SELECT COALESCE(i.performed_at,i.planned_at,i.created_at) dt,'Intervention — '||i.intervention_type type,COALESCE(i.notes,'')||CASE WHEN i.quantity IS NOT NULL THEN ' — '||i.quantity||' '||COALESCE(i.unit,'') ELSE '' END detail,COALESCE(u.name,'Utilisateur') author FROM interventions i LEFT JOIN users u ON u.id=i.user_id WHERE i.tree_id=?",(tid,)): events.append(dict(r))
 events.sort(key=lambda x:x.get('dt') or '',reverse=True); c.close()
 return page('Historique arbre',"""<div class="section-title"><h2>Historique — {{t.tree_code}}</h2><a class="btn alt" href="/tree/{{t.id}}">Retour à la fiche</a></div><div class="card"><table><tr><th>Date</th><th>Action</th><th>Détail</th><th>Utilisateur</th></tr>{% for e in events %}<tr><td>{{e.dt}}</td><td><b>{{e.type}}</b></td><td>{{e.detail}}</td><td>{{e.author}}</td></tr>{% else %}<tr><td colspan="4">Aucun événement.</td></tr>{% endfor %}</table></div>""",t=t,events=events)

INTERVENTION_TYPES=['Plantation','Arrosage','Taille','Désherbage','Fertilisation','Traitement','Remplacement du tuteur','Remplacement du QR Code','Photo','Observation','Contrôle sanitaire','Autre']

@app.route('/interventions')
@login_required
def interventions_list():
 if not (has_permission('intervention.view') or is_admin()): flash('Accès non autorisé.'); return redirect('/')
 c=db(); status=clean(request.args.get('status')); itype=clean(request.args.get('type')); tree_id=request.args.get('tree_id')
 where=['1=1']; params=[]
 if not is_admin(): where.append('i.user_id=?'); params.append(session['uid'])
 if status: where.append('i.status=?'); params.append(status)
 if itype: where.append('i.intervention_type=?'); params.append(itype)
 if tree_id and str(tree_id).isdigit(): where.append('i.tree_id=?'); params.append(int(tree_id))
 rows=c.execute("""SELECT i.*,t.tree_code,s.name_fr species_name,u.name user_name,m.title mission_title FROM interventions i JOIN trees t ON t.id=i.tree_id LEFT JOIN species s ON s.id=t.species_id LEFT JOIN users u ON u.id=i.user_id LEFT JOIN missions m ON m.id=i.mission_id WHERE """+' AND '.join(where)+" ORDER BY COALESCE(i.performed_at,i.planned_at,i.created_at) DESC",params).fetchall()
 stats={r['status']:r['n'] for r in c.execute("SELECT status,COUNT(*) n FROM interventions GROUP BY status")}; c.close()
 return page('Interventions',"""<div class="section-title"><div><h2>Gestion des interventions</h2><p class="sub">Suivi des soins, contrôles et opérations réalisés sur les arbres.</p></div><div><a class="btn" href="/interventions/new">＋ Nouvelle intervention</a> <a class="btn alt" href="/interventions/calendar">Calendrier</a></div></div><div class="grid kpis" style="grid-template-columns:repeat(3,1fr)"><a class="card kpi" href="/interventions?status=Planifiée"><small>Planifiées</small><b>{{stats.get('Planifiée',0)}}</b></a><a class="card kpi" href="/interventions?status=Réalisée"><small>Réalisées</small><b>{{stats.get('Réalisée',0)}}</b></a><a class="card kpi" href="/interventions?status=Annulée"><small>Annulées</small><b>{{stats.get('Annulée',0)}}</b></a></div><form method="get" class="card toolbar"><label>État<select name="status"><option value="">Tous</option>{% for x in ['Planifiée','Réalisée','Annulée'] %}<option {% if status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Type<select name="type"><option value="">Tous</option>{% for x in types %}<option {% if itype==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/interventions">Effacer</a></form><div class="card"><table><tr><th>Date</th><th>Arbre</th><th>Intervention</th><th>État</th><th>Bénévole</th><th>Échéance suivante</th><th></th></tr>{% for i in rows %}<tr><td>{{i.performed_at or i.planned_at or i.created_at}}</td><td><a href="/tree/{{i.tree_id}}"><b>{{i.tree_code}}</b></a><br><small>{{i.species_name or ''}}</small></td><td>{{i.intervention_type}}{% if i.quantity %}<br><small>{{i.quantity}} {{i.unit or ''}}</small>{% endif %}</td><td><span class="badge {% if i.status=='Réalisée' %}good{% elif i.status=='Planifiée' %}watch{% else %}danger{% endif %}">{{i.status}}</span></td><td>{{i.user_name or '—'}}</td><td>{{i.next_due_at or '—'}}</td><td><a href="/interventions/{{i.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="7">Aucune intervention trouvée.</td></tr>{% endfor %}</table></div>""",rows=rows,stats=stats,status=status,itype=itype,types=INTERVENTION_TYPES)

def intervention_options(c):
 trees=c.execute("SELECT t.id,t.tree_code,s.name_fr species_name FROM trees t LEFT JOIN species s ON s.id=t.species_id WHERE t.active=1 AND t.approval_status='approved' ORDER BY t.tree_code").fetchall()
 missions=c.execute("SELECT id,code,title FROM missions WHERE active=1 ORDER BY id DESC").fetchall()
 users=c.execute("SELECT id,name FROM users WHERE active=1 ORDER BY name").fetchall()
 return trees,missions,users

@app.route('/interventions/new',methods=['GET','POST'])
@app.route('/trees/<int:tid>/interventions/new',methods=['GET','POST'])
@login_required
def intervention_new(tid=None):
 if not (has_permission('intervention.create') or is_admin()): flash('Accès non autorisé.'); return redirect('/')
 c=db(); trees,missions,users=intervention_options(c); selected_tree=tid or request.args.get('tree_id')
 if request.method=='POST':
  try: tree_id=int(request.form.get('tree_id') or 0)
  except ValueError: tree_id=0
  exists=c.execute('SELECT id FROM trees WHERE id=? AND active=1',(tree_id,)).fetchone()
  if not exists: flash('Sélectionnez un arbre valide.')
  else:
   status=request.form.get('status','Réalisée'); now=datetime.now().isoformat(timespec='minutes')
   performed=request.form.get('performed_at') or (now if status=='Réalisée' else None)
   planned=request.form.get('planned_at') or None
   assigned=int(request.form.get('user_id') or session['uid']) if is_admin() else session['uid']
   cur=c.execute("""INSERT INTO interventions(tree_id,mission_id,user_id,intervention_type,status,planned_at,performed_at,quantity,unit,notes,photo_url,next_due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(tree_id,request.form.get('mission_id') or None,assigned,request.form.get('intervention_type'),status,planned,performed,request.form.get('quantity') or None,clean(request.form.get('unit')),clean(request.form.get('notes')),request.form.get('photo_url') or None,request.form.get('next_due_at') or None,now,now))
   iid=cur.lastrowid
   if request.form.get('next_due_at'):
    c.execute('INSERT INTO intervention_reminders(intervention_id,tree_id,reminder_type,due_at,status,assigned_user_id,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(iid,tree_id,request.form.get('intervention_type'),request.form.get('next_due_at'),'À faire',assigned,clean(request.form.get('notes')),session['uid'],now))
   if request.form.get('intervention_type')=='Arrosage' and status=='Réalisée': c.execute("UPDATE trees SET last_watered_at=?,watering_status='À jour' WHERE id=?",(performed,tree_id))
   c.commit(); c.close(); log_action('create','intervention',iid,request.form.get('intervention_type')); flash('Intervention enregistrée.'); return redirect('/interventions/'+str(iid))
 c.close()
 return page('Nouvelle intervention',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Arbre<select name="tree_id" required><option value="">Sélectionner</option>{% for t in trees %}<option value="{{t.id}}" {% if selected_tree|string==t.id|string %}selected{% endif %}>{{t.tree_code}} — {{t.species_name or 'Espèce inconnue'}}</option>{% endfor %}</select></label><label>Type<select name="intervention_type">{% for x in types %}<option>{{x}}</option>{% endfor %}</select></label><label>État<select name="status"><option>Réalisée</option><option>Planifiée</option><option>Annulée</option></select></label><label>Mission liée<select name="mission_id"><option value="">Aucune</option>{% for m in missions %}<option value="{{m.id}}">{{m.code}} — {{m.title}}</option>{% endfor %}</select></label>{% if admin %}<label>Attribuée à<select name="user_id">{% for u in users %}<option value="{{u.id}}" {% if u.id==session.get('uid') %}selected{% endif %}>{{u.name}}</option>{% endfor %}</select></label>{% endif %}<label>Date prévue<input type="datetime-local" name="planned_at"></label><label>Date réalisée<input type="datetime-local" name="performed_at"></label><label>Quantité<input type="number" step="any" min="0" name="quantity"></label><label>Unité<input name="unit" placeholder="L, arbre(s), kg..."></label><label>Prochaine échéance<input type="datetime-local" name="next_due_at"></label><label class="full">Notes<textarea name="notes"></textarea></label>{{photo|safe}}<div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/interventions">Annuler</a></div></form></div>""",trees=trees,missions=missions,users=users,types=INTERVENTION_TYPES,selected_tree=selected_tree,admin=is_admin(),photo=photo_fields(prefix='intervention'))

@app.route('/interventions/<int:iid>')
@login_required
def intervention_detail(iid):
 c=db(); i=c.execute("""SELECT i.*,t.tree_code,s.name_fr species_name,u.name user_name,m.title mission_title FROM interventions i JOIN trees t ON t.id=i.tree_id LEFT JOIN species s ON s.id=t.species_id LEFT JOIN users u ON u.id=i.user_id LEFT JOIN missions m ON m.id=i.mission_id WHERE i.id=?""",(iid,)).fetchone(); c.close()
 if not i: return ('Intervention introuvable',404)
 if not is_admin() and i['user_id']!=session['uid']: flash('Accès non autorisé.'); return redirect('/interventions')
 return page('Détail intervention',"""<div class="section-title"><div><h2>{{i.intervention_type}}</h2><span class="badge {% if i.status=='Réalisée' %}good{% elif i.status=='Planifiée' %}watch{% else %}danger{% endif %}">{{i.status}}</span></div><div>{% if i.status=='Planifiée' %}<form method="post" action="/interventions/{{i.id}}/complete" style="display:inline"><button class="btn">Marquer réalisée</button></form>{% endif %} {% if admin %}<a class="btn alt" href="/interventions/{{i.id}}/edit">Modifier</a>{% endif %} <a class="btn alt" href="/interventions">Retour</a></div></div><div class="grid two"><div class="card"><h3>Arbre</h3><p><a href="/tree/{{i.tree_id}}"><b>{{i.tree_code}}</b></a></p><p>{{i.species_name or 'Espèce inconnue'}}</p><p><b>Bénévole :</b> {{i.user_name or '—'}}</p><p><b>Mission :</b> {{i.mission_title or 'Aucune'}}</p></div><div class="card"><h3>Suivi</h3><p><b>Prévue :</b> {{i.planned_at or '—'}}</p><p><b>Réalisée :</b> {{i.performed_at or '—'}}</p><p><b>Quantité :</b> {{i.quantity or '—'}} {{i.unit or ''}}</p><p><b>Prochaine échéance :</b> {{i.next_due_at or '—'}}</p><p><b>Notes :</b> {{i.notes or '—'}}</p></div></div>{% if i.photo_url %}<div class="card"><h3>Photo</h3><img src="{{i.photo_url}}" alt="Photo intervention" style="max-width:520px;width:100%;border-radius:12px"></div>{% endif %}""",i=i,admin=is_admin())

@app.post('/interventions/<int:iid>/complete')
@login_required
def intervention_complete(iid):
 c=db(); i=c.execute('SELECT * FROM interventions WHERE id=?',(iid,)).fetchone()
 if not i: c.close(); return ('Intervention introuvable',404)
 if not is_admin() and i['user_id']!=session['uid']: c.close(); flash('Accès non autorisé.'); return redirect('/interventions')
 now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE interventions SET status='Réalisée',performed_at=COALESCE(performed_at,?),updated_at=? WHERE id=?",(now,now,iid)); c.execute("UPDATE intervention_reminders SET status='Terminée',completed_at=? WHERE intervention_id=?",(now,iid))
 if i['intervention_type']=='Arrosage': c.execute("UPDATE trees SET last_watered_at=?,watering_status='À jour' WHERE id=?",(now,i['tree_id']))
 c.commit(); c.close(); log_action('complete','intervention',iid); flash('Intervention marquée comme réalisée.'); return redirect('/interventions/'+str(iid))

@app.route('/interventions/<int:iid>/edit',methods=['GET','POST'])
@login_required
def intervention_edit(iid):
 if not is_admin(): flash('Accès administrateur requis.'); return redirect('/interventions/'+str(iid))
 c=db(); i=c.execute('SELECT * FROM interventions WHERE id=?',(iid,)).fetchone()
 if not i: c.close(); return ('Intervention introuvable',404)
 trees,missions,users=intervention_options(c)
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes'); c.execute("""UPDATE interventions SET tree_id=?,mission_id=?,user_id=?,intervention_type=?,status=?,planned_at=?,performed_at=?,quantity=?,unit=?,notes=?,photo_url=?,next_due_at=?,updated_at=? WHERE id=?""",(request.form.get('tree_id'),request.form.get('mission_id') or None,request.form.get('user_id'),request.form.get('intervention_type'),request.form.get('status'),request.form.get('planned_at') or None,request.form.get('performed_at') or None,request.form.get('quantity') or None,clean(request.form.get('unit')),clean(request.form.get('notes')),request.form.get('photo_url') or None,request.form.get('next_due_at') or None,now,iid)); c.commit(); c.close(); log_action('edit','intervention',iid); flash('Intervention modifiée.'); return redirect('/interventions/'+str(iid))
 c.close(); return page('Modifier intervention',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Arbre<select name="tree_id">{% for t in trees %}<option value="{{t.id}}" {% if i.tree_id==t.id %}selected{% endif %}>{{t.tree_code}} — {{t.species_name or ''}}</option>{% endfor %}</select></label><label>Type<select name="intervention_type">{% for x in types %}<option {% if i.intervention_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>État<select name="status">{% for x in ['Planifiée','Réalisée','Annulée'] %}<option {% if i.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Utilisateur<select name="user_id">{% for u in users %}<option value="{{u.id}}" {% if i.user_id==u.id %}selected{% endif %}>{{u.name}}</option>{% endfor %}</select></label><label>Mission<select name="mission_id"><option value="">Aucune</option>{% for m in missions %}<option value="{{m.id}}" {% if i.mission_id==m.id %}selected{% endif %}>{{m.title}}</option>{% endfor %}</select></label><label>Date prévue<input type="datetime-local" name="planned_at" value="{{i.planned_at or ''}}"></label><label>Date réalisée<input type="datetime-local" name="performed_at" value="{{i.performed_at or ''}}"></label><label>Quantité<input type="number" step="any" name="quantity" value="{{i.quantity or ''}}"></label><label>Unité<input name="unit" value="{{i.unit or ''}}"></label><label>Prochaine échéance<input type="datetime-local" name="next_due_at" value="{{i.next_due_at or ''}}"></label><label class="full">Notes<textarea name="notes">{{i.notes or ''}}</textarea></label>{{photo|safe}}<div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/interventions/{{i.id}}">Annuler</a></div></form></div>""",i=i,trees=trees,missions=missions,users=users,types=INTERVENTION_TYPES,photo=photo_fields(i['photo_url'] or '',prefix='interventionedit'))

@app.route('/interventions/calendar')
@login_required
def interventions_calendar():
 if not (has_permission('intervention.view') or is_admin()): flash('Accès non autorisé.'); return redirect('/')
 c=db(); rows=c.execute("""SELECT r.*,t.tree_code,s.name_fr species_name,u.name assigned_name FROM intervention_reminders r JOIN trees t ON t.id=r.tree_id LEFT JOIN species s ON s.id=t.species_id LEFT JOIN users u ON u.id=r.assigned_user_id WHERE r.status='À faire' ORDER BY r.due_at""").fetchall(); today=date.today().isoformat(); c.close()
 return page('Calendrier des interventions',"""<div class="section-title"><div><h2>Calendrier et rappels</h2><p class="sub">Les échéances sont créées depuis le champ « Prochaine échéance » d’une intervention.</p></div><a class="btn" href="/interventions/new">Nouvelle intervention</a></div><div class="card"><table><tr><th>Échéance</th><th>Arbre</th><th>Type</th><th>Attribuée à</th><th>État</th></tr>{% for r in rows %}<tr><td><b>{{r.due_at}}</b></td><td><a href="/tree/{{r.tree_id}}">{{r.tree_code}}</a><br><small>{{r.species_name or ''}}</small></td><td>{{r.reminder_type}}</td><td>{{r.assigned_name or '—'}}</td><td><span class="badge {% if r.due_at[:10] < today %}danger{% else %}watch{% endif %}">{{'En retard' if r.due_at[:10] < today else 'À venir'}}</span></td></tr>{% else %}<tr><td colspan="5">Aucune intervention planifiée.</td></tr>{% endfor %}</table></div>""",rows=rows,today=today)

@app.route('/qr/<int:tid>.png')
@login_required
def qr_png(tid):
 c=db(); t=c.execute("SELECT * FROM trees WHERE id=? AND active=1",(tid,)).fetchone(); c.close()
 if not t:return ('Introuvable',404)
 if not is_admin() and t['planted_by_user_id']!=session.get('uid'): return ('Accès refusé',403)
 token=t['qr_code'] or f'MYTREE:PENDING:{tid}'
 payload=request.url_root.rstrip('/')+'/public/map?tree='+str(tid); img=qrcode.make(payload); b=io.BytesIO(); img.save(b,format='PNG'); b.seek(0); return send_file(b,mimetype='image/png',download_name=(t['tree_code'] or f'plantation-{tid}')+'.png')


@app.route('/my-plantings')
@login_required
def my_plantings():
 c=db(); rows=c.execute("""SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.planted_by_user_id=? AND t.active=1 ORDER BY t.id DESC""",(session['uid'],)).fetchall(); c.close()
 return page('Mes plantations',"""<div class="section-title"><h2>Mes plantations</h2><a class="btn" href="/planting/new">+ Nouvelle plantation</a></div><div class="card"><table><tr><th>Code</th><th>Espèce</th><th>Projet</th><th>Zone</th><th>Statut</th><th>Motif</th><th>QR</th></tr>{% for t in rows %}<tr><td>{{t.tree_code or 'Après validation'}}</td><td>{{t.species_name or t.species}}</td><td>{{t.project_name}}</td><td>{{t.zone_name}}</td><td><span class="badge {% if t.approval_status=='pending' %}pending{% elif t.approval_status=='approved' %}good{% else %}danger{% endif %}">{{t.approval_status}}</span></td><td>{{t.rejection_reason or '—'}}</td><td>{% if t.approval_status=='approved' %}<a href="/qr/{{t.id}}.png" target="_blank">Imprimer</a>{% else %}—{% endif %}</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/planting/<int:tid>/review')
@login_required
def planting_review_history(tid):
 c=db(); t=c.execute("SELECT t.*,s.name_fr species_name,u.name volunteer_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE t.id=?",(tid,)).fetchone(); reviews=c.execute("SELECT pr.*,u.name reviewer_name FROM planting_reviews pr LEFT JOIN users u ON u.id=pr.reviewer_user_id WHERE pr.tree_id=? ORDER BY pr.id DESC",(tid,)).fetchall(); c.close()
 if not t:return ('Introuvable',404)
 return page('Historique de validation',"""<div class="card"><h2>{{t.species_name}} — {{t.volunteer_name}}</h2><p>Statut actuel : <b>{{t.approval_status}}</b></p><p>Motif : {{t.rejection_reason or '—'}}</p></div><div class="card"><table><tr><th>Date</th><th>Décision</th><th>Administrateur</th><th>Motif</th></tr>{% for r in reviews %}<tr><td>{{r.created_at}}</td><td>{{r.decision}}</td><td>{{r.reviewer_name}}</td><td>{{r.reason or '—'}}</td></tr>{% endfor %}</table></div>""",t=t,reviews=reviews)


# Alpha 4 Lot 8 — operational multi-association integrity.
def association_user_allowed(c,user_id,association_id):
 if not user_id: return True
 return bool(c.execute("SELECT 1 FROM association_memberships am JOIN users u ON u.id=am.user_id WHERE am.association_id=? AND am.user_id=? AND am.status='approved' AND u.active=1",(association_id,user_id)).fetchone())

def validate_association_users(c,user_ids,association_id):
 bad=[]
 for uid in {str(x) for x in user_ids if x not in (None,'')}:
  try: iid=int(uid)
  except Exception: bad.append(uid); continue
  if not association_user_allowed(c,iid,association_id): bad.append(uid)
 return bad

def operation_project_allowed(c,project_id,association_id,capability):
 if not project_id: return True,None
 p=c.execute('SELECT id,association_id,active FROM projects WHERE id=?',(project_id,)).fetchone()
 if not p or not p['active']: return False,p
 if int(p['association_id'] or 0)==int(association_id or 0): return True,p
 return collaboration_access(c,project_id,association_id,capability),p

def validate_operational_links(c,association_id,project_id=None,zone_id=None,team_id=None,capability='can_manage_missions'):
 ok,p=operation_project_allowed(c,project_id,association_id,capability)
 if not ok: return False,'Projet non autorisé pour cette association.'
 z=None
 if zone_id:
  z=c.execute('SELECT id,project_id,active FROM zones WHERE id=?',(zone_id,)).fetchone()
  if not z or not z['active']: return False,'Zone invalide ou archivée.'
  if not project_id or int(z['project_id'] or 0)!=int(project_id): return False,'La zone ne correspond pas au projet sélectionné.'
 t=None
 if team_id:
  t=c.execute('SELECT id,association_id,project_id,zone_id,active FROM teams WHERE id=?',(team_id,)).fetchone()
  if not t or not t['active']: return False,'Équipe invalide ou inactive.'
  if int(t['association_id'] or 0)!=int(association_id or 0): return False,'Cette équipe appartient à une autre association.'
  if project_id and t['project_id'] and int(t['project_id'])!=int(project_id): return False,'L’équipe appartient à un autre projet.'
  if zone_id and t['zone_id'] and int(t['zone_id'])!=int(zone_id): return False,'L’équipe appartient à une autre zone.'
 return True,None

def association_operational_people(c,association_id):
 return c.execute("SELECT DISTINCT u.id,u.name,u.phone FROM users u JOIN association_memberships am ON am.user_id=u.id WHERE u.active=1 AND am.association_id=? AND am.status='approved' ORDER BY u.name",(association_id,)).fetchall()

def association_operation_projects(c,association_id,capability):
 rows=c.execute("SELECT id,name,association_id FROM projects WHERE active=1 AND (association_id=? OR id IN (SELECT project_id FROM association_collaborations WHERE invited_association_id=? AND status='accepted' AND "+capability+"=1)) ORDER BY name",(association_id,association_id)).fetchall()
 return rows

def resource_admin_context(c,table,rid):
 row=c.execute(f'SELECT association_id FROM {table} WHERE id=?',(rid,)).fetchone()
 if not row:return False,row
 aid=row['association_id']; ctx=active_context(c)
 return bool(is_super_admin() or (ctx.get('type')=='association' and int(ctx.get('association_id') or 0)==int(aid or 0) and has_association_permission('association.update',aid,audit_denied=False))),row

@app.route('/teams')
@login_required
def teams_page():
 c=db(); q=request.args.get('q','').strip(); project_id=request.args.get('project_id',''); zone_id=request.args.get('zone_id',''); active=request.args.get('active','1'); scope,sp=context_condition('tm'); w=[scope];p=list(sp)
 if q:w.append('(tm.name LIKE ? OR tm.mission LIKE ? OR tm.phone LIKE ?)');p += ['%'+q+'%']*3
 if project_id:w.append('tm.project_id=?');p.append(project_id)
 if zone_id:w.append('tm.zone_id=?');p.append(zone_id)
 if active!='':w.append('tm.active=?');p.append(active)
 rows=c.execute("""SELECT tm.*,p.name project_name,z.name zone_name,u.name leader_name,(SELECT COUNT(*) FROM team_members m WHERE m.team_id=tm.id AND m.status='active') member_count,(SELECT COUNT(*) FROM team_join_requests r WHERE r.team_id=tm.id AND r.status='pending') pending_count,(SELECT COUNT(*) FROM missions ms WHERE ms.team_id=tm.id AND ms.active=1) mission_count,(SELECT COUNT(*) FROM events ev WHERE ev.team_id=tm.id AND ev.active=1) event_count FROM teams tm LEFT JOIN projects p ON p.id=tm.project_id LEFT JOIN zones z ON z.id=tm.zone_id LEFT JOIN users u ON u.id=tm.leader_user_id WHERE """+' AND '.join(w)+' ORDER BY tm.active DESC,tm.id DESC',p).fetchall(); opts=filter_options(c); c.close()
 return page('Équipes',"""<div class="section-title"><h2>Liste des équipes</h2>{% if admin %}<a class="btn" href="/teams/new">+ Nouvelle équipe</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}"></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>État<select name="active"><option value="">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actives</option><option value="0" {% if active=='0' %}selected{% endif %}>Inactives</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/teams">Effacer</a></form><div class="card"><table><tr><th>Équipe</th><th>Chef</th><th>Projet / Zone</th><th>Membres</th><th>Demandes</th><th>Missions</th><th>Événements</th><th>État</th><th>Actions</th></tr>{% for t in rows %}<tr><td><a href="/teams/{{t.id}}"><b>{{t.name}}</b></a><div class="sub">{{t.phone or ''}}</div></td><td>{{t.leader_name or '—'}}</td><td>{{t.project_name or '—'}} / {{t.zone_name or '—'}}</td><td>{{t.member_count}}</td><td>{{t.pending_count}}</td><td>{{t.mission_count}}</td><td>{{t.event_count}}</td><td><span class="badge {% if t.active %}good{% else %}danger{% endif %}">{{'Active' if t.active else 'Inactive'}}</span></td><td><a class="btn alt" href="/teams/{{t.id}}">Ouvrir</a>{% if admin %} <a class="btn alt" href="/teams/{{t.id}}/edit">Modifier</a> <form method="post" action="/teams/{{t.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou désactiver cette équipe ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% endfor %}</table></div>""",rows=rows,q=q,project_id=project_id,zone_id=zone_id,active=active,admin=is_admin(),**opts)

TEAM_FORM="""<div class="card"><form method="post" class="form" id="teamForm"><label>Code<input name="code" value="{{request.form.get('code',t.code if t and t.code else suggested_code)}}" readonly></label><label>Nom<input name="name" value="{{request.form.get('name',t.name if t else '')}}" required></label><label>Chef d’équipe<select name="leader_user_id" id="teamLeader"><option value="">—</option>{% set lid=request.form.get('leader_user_id',t.leader_user_id if t else '') %}{% for x in leaders %}<option value="{{x.id}}" {% if lid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id" id="teamProject"><option value="">—</option>{% set pid=request.form.get('project_id',t.project_id if t else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id" id="teamZone"><option value="">—</option>{% set zid=request.form.get('zone_id',t.zone_id if t else '') %}{% for x in zones %}{% if not pid or x.project_id|string==pid|string %}<option value="{{x.id}}" {% if zid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endif %}{% endfor %}</select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone',t.phone if t and t.phone else '')}}"></label>{% if t %}<label>État<select name="active"><option value="1" {% if request.form.get('active',t.active)|string=='1' %}selected{% endif %}>Active</option><option value="0" {% if request.form.get('active',t.active)|string=='0' %}selected{% endif %}>Inactive</option></select></label>{% endif %}<label class="full">Mission / rôle de l’équipe<textarea name="mission">{{request.form.get('mission',t.mission if t and t.mission else '')}}</textarea></label><div class="full"><h3>Bénévoles de l’équipe</h3><input type="search" id="teamMemberSearch" placeholder="Rechercher par nom ou téléphone…" oninput="filterTeamMembers(this.value)"><div class="member-picker" id="teamMemberPicker">{% for x in volunteers %}<label><input type="checkbox" name="member_ids" value="{{x.id}}" {% if x.id in selected_members %}checked{% endif %}> {{x.name}}{% if x.phone %} — {{x.phone}}{% endif %}</label>{% endfor %}</div></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div><script>async function loadTeamZones(sel){let p=teamProject.value;teamZone.innerHTML='<option value="">—</option>';if(!p)return;let rows=await fetch('/api/projects/'+p+'/zones').then(r=>r.json());rows.forEach(x=>{let o=new Option(x.name,x.id);if(String(x.id)==String(sel))o.selected=true;teamZone.add(o)})}teamProject.addEventListener('change',()=>loadTeamZones(null));function filterTeamMembers(q){q=(q||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');document.querySelectorAll('#teamMemberPicker label').forEach(x=>{let t=x.textContent.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');x.style.display=!q||t.includes(q)?'flex':'none'})}</script>"""

@app.route('/teams/new',methods=['GET','POST'])
@login_required
def team_new():
 if not is_admin(): return ('Administration association requise',403)
 c=db(); ctx=active_context(c); aid=ctx.get('association_id')
 if ctx.get('type')!='association' or not aid: c.close(); return ('Contexte association requis',403)
 projects=association_operation_projects(c,aid,'can_manage_missions'); pids=[x['id'] for x in projects]
 zones=c.execute('SELECT id,name,project_id FROM zones WHERE active=1 AND project_id IN ('+(','.join('?'*len(pids)) if pids else 'NULL')+') ORDER BY name',pids).fetchall() if pids else []
 people=association_operational_people(c,aid); leaders=people; volunteers=people; suggested=next_entity_code(c,'teams','code','EQUIPE')
 opts=filter_options(c); opts.update(projects=projects,zones=zones)
 if request.method=='POST':
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None; leader=request.form.get('leader_user_id') or None
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,None,'can_manage_missions')
  members=set(request.form.getlist('member_ids'))
  if leader: members.add(str(leader))
  bad=validate_association_users(c,members,aid)
  if not ok or bad:
   c.close(); return ((msg or 'Membre non autorisé : '+','.join(map(str,bad))),403)
  now=datetime.now().isoformat(timespec='minutes'); code=suggested
  try:
   cur=c.execute('INSERT INTO teams(code,name,leader_user_id,project_id,zone_id,phone,mission,active,created_by_user_id,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,1,?,?,?,?)',(code,request.form['name'].strip(),leader,project_id,zone_id,request.form.get('phone'),request.form.get('mission'),session['uid'],now,now,aid)); tid=cur.lastrowid
  except sqlite3.IntegrityError:
   c.close(); return ('Code équipe déjà utilisé',409)
  for uid in members:
   c.execute("INSERT OR REPLACE INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?)",(tid,uid,now,session['uid'],now)); c.execute('UPDATE users SET team_id=? WHERE id=?',(tid,uid))
  c.commit(); c.close(); log_action('create','team',tid); flash('Équipe créée avec ses membres autorisés.'); return redirect('/teams/'+str(tid))
 c.close(); opts.update(volunteers=volunteers); return page('Nouvelle équipe',TEAM_FORM,t=None,leaders=leaders,selected_members=set(),suggested_code=suggested,cancel_url='/teams',**opts)

@app.route('/teams/<int:tid>')
@login_required
def team_detail(tid):
 c=db(); t=c.execute('SELECT tm.*,p.name project_name,z.name zone_name,u.name leader_name FROM teams tm LEFT JOIN projects p ON p.id=tm.project_id LEFT JOIN zones z ON z.id=tm.zone_id LEFT JOIN users u ON u.id=tm.leader_user_id WHERE tm.id=?',(tid,)).fetchone()
 if not t: c.close(); return ('Équipe introuvable',404)
 members=c.execute("SELECT m.*,u.name,u.phone FROM team_members m JOIN users u ON u.id=m.user_id WHERE m.team_id=? AND m.status='active' ORDER BY u.name",(tid,)).fetchall(); requests=c.execute("SELECT r.*,u.name,u.phone FROM team_join_requests r JOIN users u ON u.id=r.user_id WHERE r.team_id=? AND r.status='pending' ORDER BY r.id",(tid,)).fetchall(); missions=c.execute('SELECT id,code,title,status,start_at FROM missions WHERE team_id=? AND active=1 ORDER BY id DESC LIMIT 10',(tid,)).fetchall(); events=c.execute('SELECT id,title,event_type,status,start_at FROM events WHERE team_id=? AND active=1 ORDER BY start_at DESC LIMIT 10',(tid,)).fetchall(); c.close()
 is_member=any(m['user_id']==session['uid'] for m in members)
 return page('Fiche équipe',"""<div class="section-title"><div><h2>{{t.name}}</h2><span class="badge {% if t.active %}good{% else %}danger{% endif %}">{{'Active' if t.active else 'Inactive'}}</span></div><div>{% if admin %}<a class="btn" href="/teams/{{t.id}}/edit">Modifier</a> <form method="post" action="/teams/{{t.id}}/archive" style="display:inline"><button class="btn red">{{'Désactiver' if t.active else 'Réactiver'}}</button></form>{% elif not is_member %}<form method="post" action="/teams/{{t.id}}/join" style="display:inline"><button class="btn">Demander à rejoindre</button></form>{% endif %} <a class="btn alt" href="/teams">Retour</a></div></div><div class="grid two"><div class="card"><h3>Informations</h3><p><b>Chef :</b> {{t.leader_name or '—'}}</p><p><b>Projet :</b> {{t.project_name or '—'}}</p><p><b>Zone :</b> {{t.zone_name or '—'}}</p><p><b>Téléphone :</b> {{t.phone or '—'}}</p><p>{{t.mission or ''}}</p></div><div class="card"><h3>Missions récentes</h3>{% for m in missions %}<div class="priority"><b><a href="/missions/{{m.id}}">{{m.code}} — {{m.title}}</a></b><span>{{m.status}} • {{m.start_at or '—'}}</span></div>{% else %}<p class="sub">Aucune mission.</p>{% endfor %}</div><div class="card"><h3>Événements de l’équipe</h3>{% for e in events %}<div class="priority"><b><a href="/events/{{e.id}}">{{e.title}}</a></b><span>{{e.event_type}} • {{e.start_at}}</span></div>{% else %}<p class="sub">Aucun événement.</p>{% endfor %}</div></div><div class="card"><h3>Membres ({{members|length}})</h3><table><tr><th>Nom</th><th>Téléphone</th>{% if admin %}<th>Action</th>{% endif %}</tr>{% for m in members %}<tr><td><a href="/volunteers/{{m.user_id}}">{{m.name}}</a>{% if m.user_id==t.leader_user_id %} <span class="badge watch">Chef</span>{% endif %}</td><td>{{m.phone}}</td>{% if admin %}<td>{% if m.user_id!=t.leader_user_id %}<form method="post" action="/teams/{{t.id}}/members/{{m.user_id}}/remove"><button class="btn red">Retirer</button></form>{% endif %}</td>{% endif %}</tr>{% else %}<tr><td colspan="3">Aucun membre.</td></tr>{% endfor %}</table></div>{% if admin %}<div class="card"><h3>Demandes en attente ({{requests|length}})</h3>{% for r in requests %}<div class="priority"><b>{{r.name}} — {{r.phone}}</b><span><form method="post" action="/team-requests/{{r.id}}/accept" style="display:inline"><button class="btn">Accepter</button></form> <form method="post" action="/team-requests/{{r.id}}/reject" style="display:inline"><button class="btn red">Refuser</button></form></span></div>{% else %}<p class="sub">Aucune demande.</p>{% endfor %}</div>{% endif %}""",t=t,members=members,requests=requests,missions=missions,events=events,admin=is_admin(),is_member=is_member)

@app.route('/teams/<int:tid>/edit',methods=['GET','POST'])
@login_required
def team_edit(tid):
 c=db(); t=c.execute('SELECT * FROM teams WHERE id=?',(tid,)).fetchone()
 if not t: c.close(); return ('Équipe introuvable',404)
 aid=t['association_id']; ctx=active_context(c)
 if not (is_super_admin() or (ctx.get('type')=='association' and int(ctx.get('association_id') or 0)==int(aid or 0) and is_admin())): c.close(); return ('Administration de l’association de l’équipe requise',403)
 projects=association_operation_projects(c,aid,'can_manage_missions'); pids=[x['id'] for x in projects]
 zones=c.execute('SELECT id,name,project_id FROM zones WHERE active=1 AND project_id IN ('+(','.join('?'*len(pids)) if pids else 'NULL')+') ORDER BY name',pids).fetchall() if pids else []
 people=association_operational_people(c,aid); leaders=people; volunteers=people; selected={r['user_id'] for r in c.execute("SELECT user_id FROM team_members WHERE team_id=? AND status='active'",(tid,))}; opts=filter_options(c); opts.update(projects=projects,zones=zones)
 if request.method=='POST':
  new=request.form.get('leader_user_id') or None; project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,None,'can_manage_missions'); desired=set(request.form.getlist('member_ids'))
  if new: desired.add(str(new))
  bad=validate_association_users(c,desired,aid)
  if not ok or bad: c.close(); return ((msg or 'Membre non autorisé : '+','.join(map(str,bad))),403)
  now=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE teams SET name=?,leader_user_id=?,project_id=?,zone_id=?,phone=?,mission=?,active=?,updated_at=? WHERE id=?',(request.form['name'].strip(),new,project_id,zone_id,request.form.get('phone'),request.form.get('mission'),request.form.get('active',1),now,tid))
  current={str(x['user_id']) for x in c.execute("SELECT user_id FROM team_members WHERE team_id=? AND status='active'",(tid,))}
  for uid in desired: c.execute("INSERT OR REPLACE INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?)",(tid,uid,now,session['uid'],now)); c.execute('UPDATE users SET team_id=? WHERE id=?',(tid,uid))
  for uid in current-desired: c.execute("UPDATE team_members SET status='removed' WHERE team_id=? AND user_id=?",(tid,uid)); c.execute('UPDATE users SET team_id=NULL WHERE id=? AND team_id=?',(uid,tid))
  c.commit(); c.close(); log_action('edit','team',tid); flash('Équipe modifiée et membres synchronisés.'); return redirect('/teams/'+str(tid))
 c.close(); opts.update(volunteers=volunteers); return page('Modifier équipe',TEAM_FORM,t=t,leaders=leaders,selected_members=selected,suggested_code=t['code'] or '',cancel_url='/teams/'+str(tid),**opts)

@app.post('/teams/<int:tid>/archive')
@login_required
def team_archive(tid):
 if not is_admin(): return redirect('/teams')
 c=db(); t=c.execute('SELECT active FROM teams WHERE id=?',(tid,)).fetchone()
 if t: c.execute('UPDATE teams SET active=?,updated_at=? WHERE id=?',(0 if t['active'] else 1,datetime.now().isoformat(timespec='minutes'),tid)); c.commit()
 c.close(); log_action('archive_toggle','team',tid); flash('État de l’équipe mis à jour.'); return redirect('/teams/'+str(tid))

@app.post('/teams/<int:tid>/join')
@login_required
def team_join(tid):
 c=db(); t=c.execute('SELECT id,association_id,active FROM teams WHERE id=?',(tid,)).fetchone()
 if not t or not t['active']: c.close(); return ('Équipe introuvable ou inactive',404)
 if not association_user_allowed(c,session['uid'],t['association_id']): c.close(); return ('Vous n’êtes pas membre de cette association',403)
 ctx=active_context(c)
 if ctx.get('type')!='association' or int(ctx.get('association_id') or 0)!=int(t['association_id'] or 0): c.close(); return ('Activez l’association de cette équipe avant de la rejoindre',403)
 now=datetime.now().isoformat(timespec='minutes'); existing=c.execute("SELECT id,status FROM team_join_requests WHERE team_id=? AND user_id=? ORDER BY id DESC LIMIT 1",(tid,session['uid'])).fetchone()
 if existing and existing['status']=='pending': flash('Votre demande est déjà en attente.')
 elif c.execute("SELECT id FROM team_members WHERE team_id=? AND user_id=? AND status='active'",(tid,session['uid'])).fetchone(): flash('Vous êtes déjà membre de cette équipe.')
 else: c.execute("INSERT INTO team_join_requests(team_id,user_id,status,requested_at) VALUES(?,?,'pending',?)",(tid,session['uid'],now)); c.commit(); flash('Demande envoyée.')
 c.close(); return redirect('/teams/'+str(tid))

@app.route('/team-requests')
@login_required
def team_requests_page():
 c=db(); status=request.args.get('status','pending'); team_id=request.args.get('team_id',''); w=[]; params=[]
 if is_admin():
  if status: w.append('r.status=?'); params.append(status)
  if team_id: w.append('r.team_id=?'); params.append(team_id)
 else:
  w.append('r.user_id=?'); params.append(session['uid'])
  if status: w.append('r.status=?'); params.append(status)
 where=' AND '.join(w) if w else '1=1'
 rows=c.execute("""SELECT r.*,tm.name team_name,u.name user_name,u.phone,rv.name reviewer_name FROM team_join_requests r JOIN teams tm ON tm.id=r.team_id JOIN users u ON u.id=r.user_id LEFT JOIN users rv ON rv.id=r.reviewed_by_user_id WHERE """+where+" ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,r.id DESC",params).fetchall(); teams=c.execute('SELECT id,name FROM teams WHERE active=1 ORDER BY name').fetchall(); c.close()
 return page('Demandes équipes',"""<div class="section-title"><h2>Demandes d’équipes</h2><a class="btn alt" href="/teams">Retour aux équipes</a></div><form class="card toolbar"><label>État<select name="status"><option value="">Tous</option>{% for code,label in [('pending','En attente'),('accepted','Acceptées'),('rejected','Refusées')] %}<option value="{{code}}" {% if status==code %}selected{% endif %}>{{label}}</option>{% endfor %}</select></label>{% if admin %}<label>Équipe<select name="team_id"><option value="">Toutes</option>{% for t in teams %}<option value="{{t.id}}" {% if team_id|string==t.id|string %}selected{% endif %}>{{t.name}}</option>{% endfor %}</select></label>{% endif %}<button class="btn">Filtrer</button><a class="btn alt" href="/team-requests">Annuler les filtres</a></form><div class="card" style="overflow:auto"><table><tr><th>Bénévole</th><th>Équipe</th><th>Demandée le</th><th>État</th><th>Traitée par</th>{% if admin %}<th>Actions</th>{% endif %}</tr>{% for r in rows %}<tr><td>{{r.user_name}}<div class="sub">{{r.phone or ''}}</div></td><td><a href="/teams/{{r.team_id}}">{{r.team_name}}</a></td><td>{{r.requested_at or '—'}}</td><td><span class="badge {% if r.status=='accepted' %}good{% elif r.status=='rejected' %}danger{% else %}watch{% endif %}">{{'En attente' if r.status=='pending' else ('Acceptée' if r.status=='accepted' else 'Refusée')}}</span></td><td>{{r.reviewer_name or '—'}}{% if r.reviewed_at %}<div class="sub">{{r.reviewed_at}}</div>{% endif %}</td>{% if admin %}<td>{% if r.status=='pending' %}<form method="post" action="/team-requests/{{r.id}}/accept" style="display:inline"><button class="btn">Accepter</button></form> <form method="post" action="/team-requests/{{r.id}}/reject" style="display:inline"><button class="btn red">Refuser</button></form>{% else %}—{% endif %}</td>{% endif %}</tr>{% else %}<tr><td colspan="6">Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows,teams=teams,status=status,team_id=team_id,admin=is_admin())

@app.post('/team-requests/<int:rid>/accept')
@login_required
def team_request_accept(rid):
 if not is_admin(): return redirect('/teams')
 c=db(); r=c.execute('SELECT * FROM team_join_requests WHERE id=?',(rid,)).fetchone(); now=datetime.now().isoformat(timespec='minutes')
 if r and r['status']=='pending': c.execute("UPDATE team_join_requests SET status='accepted',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid)); c.execute("INSERT OR REPLACE INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?)",(r['team_id'],r['user_id'],now,session['uid'],now)); c.execute('UPDATE users SET team_id=? WHERE id=?',(r['team_id'],r['user_id'])); c.commit()
 c.close(); log_action('accept','team_request',rid); flash('Demande acceptée.'); return redirect('/teams/'+str(r['team_id']) if r else '/teams')

@app.post('/team-requests/<int:rid>/reject')
@login_required
def team_request_reject(rid):
 if not is_admin(): return redirect('/teams')
 c=db(); r=c.execute('SELECT * FROM team_join_requests WHERE id=?',(rid,)).fetchone(); now=datetime.now().isoformat(timespec='minutes')
 if r: c.execute("UPDATE team_join_requests SET status='rejected',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid)); c.commit()
 c.close(); log_action('reject','team_request',rid); flash('Demande refusée.'); return redirect('/teams/'+str(r['team_id']) if r else '/teams')

@app.post('/teams/<int:tid>/members/<int:uid>/remove')
@login_required
def team_member_remove(tid,uid):
 if not is_admin(): return redirect('/teams/'+str(tid))
 c=db(); c.execute("UPDATE team_members SET status='removed' WHERE team_id=? AND user_id=?",(tid,uid)); c.execute('UPDATE users SET team_id=NULL WHERE id=? AND team_id=?',(uid,tid)); c.commit(); c.close(); log_action('remove','team_member',uid,'team '+str(tid)); flash('Membre retiré.'); return redirect('/teams/'+str(tid))

@app.route('/events')
@login_required
def events_page():
 f=filters_from_request(); c=db(); guard=common_filter_guard(c,f)
 if guard: c.close(); return guard
 opts=common_filter_options(c,f); ctx=active_context(c); ids=[int(x['id']) for x in accessible_filter_projects(c,ctx)]
 w=['e.active=1']; p=[]
 if ctx.get('type')=='personal': w.append('e.association_id IS NULL')
 elif ctx.get('type')=='association':
  if ids: w.append('e.project_id IN ('+','.join('?'*len(ids))+')'); p.extend(ids)
  else: w.append('1=0')
 elif not is_super_admin(): w.append('1=0')
 if f['q']: w.append('(e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)'); p += ['%'+f['q']+'%']*3
 if f['status']: w.append('e.status=?'); p.append(f['status'])
 if f['action_type']: w.append('e.event_type=?'); p.append(f['action_type'])
 if f['project_id']: w.append('e.project_id=?'); p.append(f['project_id'])
 if f['zone_id']: w.append('e.zone_id=?'); p.append(f['zone_id'])
 if f['date_from']: w.append('date(e.start_at)>=date(?)'); p.append(f['date_from'])
 if f['date_to']: w.append('date(e.start_at)<=date(?)'); p.append(f['date_to'])
 apply_common_geo_filters(w,p,f,'pr')
 rows=c.execute("SELECT e.*,pr.name project_name,z.name zone_name,tm.name team_name,(SELECT COUNT(*) FROM event_participants ep WHERE ep.event_id=e.id AND ep.status='Inscrit') participant_count FROM events e LEFT JOIN projects pr ON pr.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id LEFT JOIN teams tm ON tm.id=e.team_id WHERE "+' AND '.join(w)+' ORDER BY e.start_at ASC',p).fetchall(); c.close()
 return page('Événements',"""<div class="section-title"><h2>Calendrier des événements</h2>{% if admin %}<a class="btn" href="/events/new">+ Nouvel événement</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{f.q}}"></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Type<select name="action_type"><option value="">Tous</option>{% for x in ['Plantation','Arrosage','Nettoyage','Réunion','Formation'] %}<option {% if f.action_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>État<select name="status"><option value="">Tous</option>{% for x in ['Planifié','Ouvert','Complet','Terminé','Annulé'] %}<option {% if f.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Du<input type="date" name="date_from" value="{{f.date_from}}"></label><label>Au<input type="date" name="date_to" value="{{f.date_to}}"></label><button class="btn">Filtrer</button><a class="btn alt" href="/events">Effacer</a></form><div class="grid two">{% for e in rows %}<div class="card"><div class="section-title"><div><span class="badge watch">{{e.event_type}}</span><h3><a href="/events/{{e.id}}">{{e.title}}</a></h3></div><span class="badge {% if e.status=='Annulé' %}danger{% elif e.status=='Terminé' %}good{% else %}watch{% endif %}">{{e.status}}</span></div><p><b>Début :</b> {{e.start_at}}</p><p><b>Lieu :</b> {{e.location or e.zone_name or e.project_name or '—'}}</p><p><b>Participants :</b> {{e.participant_count}}{% if e.max_participants %} / {{e.max_participants}}{% endif %}</p><a class="btn alt" href="/events/{{e.id}}">Ouvrir</a>{% if admin %} <form method="post" action="/events/{{e.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cet événement ?')"><button class="btn red">Supprimer</button></form>{% endif %}</div>{% else %}<div class="card">Aucun événement.</div>{% endfor %}</div>""",rows=rows,f=f,admin=is_admin(),**opts)

EVENT_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Code<input name="code" value="{{e.code if e and e.code else suggested_code}}" readonly></label><label>Titre<input name="title" value="{{request.form.get('title',e.title if e else '')}}" required></label><label>Type<select name="event_type">{% set et=request.form.get('event_type',e.event_type if e else 'Plantation') %}{% for x in ['Plantation','Arrosage','Nettoyage','Réunion','Formation'] %}<option {% if et==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at" value="{{request.form.get('start_at',e.start_at if e else '')}}" required></label><label>Fin<input type="datetime-local" name="end_at" value="{{request.form.get('end_at',e.end_at if e and e.end_at else '')}}"></label><label>Lieu<input name="location" value="{{request.form.get('location',e.location if e and e.location else '')}}"></label><label>Places maximum <span class="sub">(facultatif — vide = illimité)</span><input type="number" min="1" name="max_participants" placeholder="Laisser vide = illimité" value="{{request.form.get('max_participants',(e.max_participants if e and e.max_participants else ''))}}"></label><label>Projet<select name="project_id" id="eventProject"><option value="">—</option>{% set pid=request.form.get('project_id',e.project_id if e else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id" id="eventZone"><option value="">—</option>{% set zid=request.form.get('zone_id',e.zone_id if e else '') %}{% for x in zones %}<option value="{{x.id}}" {% if zid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Équipe<select name="team_id"><option value="">—</option>{% set tid=request.form.get('team_id',e.team_id if e else '') %}{% for x in teams %}<option value="{{x.id}}" {% if tid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>{% if e %}<label>État<select name="status">{% for x in ['Planifié','Ouvert','Complet','Terminé','Annulé'] %}<option {% if request.form.get('status',e.status)==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>{% endif %}<label>Latitude<input id="eventLat" name="latitude" value="{{request.form.get('latitude',e.latitude if e and e.latitude is not none else '')}}"></label><label>Longitude<input id="eventLon" name="longitude" value="{{request.form.get('longitude',e.longitude if e and e.longitude is not none else '')}}"></label><div class="full">{{location_picker|safe}}</div><label class="full">Description<textarea name="description">{{request.form.get('description',e.description if e and e.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div><script>async function loadEventZones(sel){let p=eventProject.value;eventZone.innerHTML='<option value="">—</option>';if(!p)return;let rows=await fetch('/api/projects/'+p+'/zones').then(r=>r.json());rows.forEach(x=>{let o=new Option(x.name,x.id);if(String(x.id)==String(sel))o.selected=true;eventZone.add(o)})}eventProject.addEventListener('change',()=>loadEventZones(null));</script>"""

def event_form_context(c):
 ctx=active_context(c); aid=ctx.get('association_id')
 if ctx.get('type')!='association' or not aid: return dict(projects=[],zones=[],teams=[],suggested_code=next_entity_code(c,'events','code','EVT'))
 projects=association_operation_projects(c,aid,'can_intervene'); pids=[x['id'] for x in projects]
 zones=c.execute('SELECT id,name,project_id FROM zones WHERE active=1 AND project_id IN ('+(','.join('?'*len(pids)) if pids else 'NULL')+') ORDER BY name',pids).fetchall() if pids else []
 teams=c.execute('SELECT id,name,project_id,zone_id FROM teams WHERE active=1 AND association_id=? ORDER BY name',(aid,)).fetchall()
 return dict(projects=projects,zones=zones,teams=teams,suggested_code=next_entity_code(c,'events','code','EVT'))

@app.route('/events/new',methods=['GET','POST'])
@login_required
def event_new():
 c=db(); ac=active_context(c); aid=ac.get('association_id')
 if ac.get('type')!='association' or not aid or not is_admin(): c.close(); return ('Administration association requise',403)
 ctx=event_form_context(c); ctx['location_picker']=location_picker_markup('event')
 if request.method=='POST':
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None; team_id=request.form.get('team_id') or None
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,team_id,'can_intervene')
  if not ok: c.close(); return (msg,403)
  now=datetime.now().isoformat(timespec='minutes'); code=ctx['suggested_code']
  try:
   sql="INSERT INTO events(code,title,event_type,status,start_at,end_at,location,project_id,zone_id,team_id,max_participants,description,latitude,longitude,active,created_by_user_id,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)"; cur=c.execute(sql,(code,clean(request.form.get('title')),request.form.get('event_type'),request.form.get('status','Planifié'),request.form.get('start_at'),request.form.get('end_at') or None,clean(request.form.get('location')) or None,project_id,zone_id,team_id,int(request.form.get('max_participants') or 0),clean(request.form.get('description')) or None,request.form.get('latitude') or None,request.form.get('longitude') or None,session['uid'],now,now,aid)); eid=cur.lastrowid
  except sqlite3.IntegrityError: c.close(); return ('Code événement déjà utilisé',409)
  c.commit(); c.close(); log_action('create','event',eid); notify('Nouvel événement',clean(request.form.get('title')),'/events/'+str(eid)); flash('Événement créé.'); return redirect('/events/'+str(eid))
 c.close(); return page('Nouvel événement',EVENT_FORM,e=None,cancel_url='/events',**ctx)

@app.route('/events/<int:eid>')
@login_required
@permission_required('event.view')
def event_detail(eid):
 c=db(); e=c.execute('SELECT e.*,p.name project_name,z.name zone_name,tm.name team_name FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id LEFT JOIN teams tm ON tm.id=e.team_id WHERE e.id=?',(eid,)).fetchone()
 if not e: c.close(); return ('Événement introuvable',404)
 participants=c.execute("SELECT ep.*,u.name,u.phone FROM event_participants ep JOIN users u ON u.id=ep.user_id WHERE ep.event_id=? ORDER BY ep.registered_at",(eid,)).fetchall(); mine=c.execute('SELECT * FROM event_participants WHERE event_id=? AND user_id=?',(eid,session['uid'])).fetchone(); c.close()
 full=bool(e['max_participants'] and sum(1 for x in participants if x['status']=='Inscrit')>=e['max_participants']); maps='' if e['latitude'] is None or e['longitude'] is None else f'https://www.google.com/maps/dir/?api=1&destination={e["latitude"]},{e["longitude"]}'
 return page('Fiche événement',"""<div class="section-title"><div><h2>{{e.title}}</h2><span class="badge watch">{{e.event_type}}</span> <span class="badge">{{e.status}}</span></div><div>{% if admin %}<a class="btn" href="/events/{{e.id}}/edit">Modifier</a> <form method="post" action="/events/{{e.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cet événement ?')"><button class="btn red">Supprimer</button></form>{% endif %} <a class="btn alt" href="/events">Retour</a></div></div><div class="grid two"><div class="card"><p><b>Début :</b> {{e.start_at}}</p><p><b>Fin :</b> {{e.end_at or '—'}}</p><p><b>Lieu :</b> {{e.location or '—'}}</p><p><b>Projet / Zone :</b> {{e.project_name or '—'}} / {{e.zone_name or '—'}}</p><p><b>Équipe :</b> {{e.team_name or '—'}}</p><p>{{e.description or ''}}</p>{% if maps %}<a class="btn alt" target="_blank" href="{{maps}}">🧭 Itinéraire Google Maps</a>{% endif %}</div><div class="card"><h3>Inscription</h3><p><b>{{participants|selectattr('status','equalto','Inscrit')|list|length}}</b>{% if e.max_participants %} / {{e.max_participants}}{% endif %} participants</p>{% if not admin %}{% if mine and mine.status=='Inscrit' %}<form method="post" action="/events/{{e.id}}/cancel"><button class="btn red">Annuler mon inscription</button></form>{% elif not full and e.status not in ['Terminé','Annulé'] %}<form method="post" action="/events/{{e.id}}/register"><button class="btn">M’inscrire</button></form>{% else %}<span class="badge danger">Inscriptions fermées</span>{% endif %}{% endif %}</div></div><div class="card"><h3>Participants</h3><table><tr><th>Nom</th><th>Téléphone</th><th>Inscription</th><th>Présence</th>{% if admin %}<th>Action</th>{% endif %}</tr>{% for p in participants %}<tr><td>{{p.name}}</td><td>{{p.phone or '—'}}</td><td>{{p.status}}</td><td>{{p.attendance_status}}</td>{% if admin %}<td><form method="post" action="/events/{{e.id}}/participants/{{p.user_id}}/attendance"><button class="btn alt">{{'Annuler présence' if p.attendance_status=='Présent' else 'Marquer présent'}}</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="5">Aucun participant.</td></tr>{% endfor %}</table></div>""",e=e,participants=participants,mine=mine,full=full,maps=maps,admin=(is_admin() and (is_super_admin() or int(active_context().get('association_id') or 0)==int(e['association_id'] or 0))))

@app.route('/events/<int:eid>/edit',methods=['GET','POST'])
@login_required
def event_edit(eid):
 c=db(); e=c.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
 if not e: c.close(); return ('Événement introuvable',404)
 aid=e['association_id']; ac=active_context(c)
 if not (is_super_admin() or (ac.get('type')=='association' and int(ac.get('association_id') or 0)==int(aid or 0) and is_admin())): c.close(); return ('Administration de l’association de l’événement requise',403)
 ctx=event_form_context(c); ctx['location_picker']=location_picker_markup('event'); ctx['suggested_code']=e['code'] or next_entity_code(c,'events','code','EVT')
 if request.method=='POST':
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None; team_id=request.form.get('team_id') or None
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,team_id,'can_intervene')
  if not ok: c.close(); return (msg,403)
  sql='UPDATE events SET code=COALESCE(code,?),title=?,event_type=?,status=?,start_at=?,end_at=?,location=?,project_id=?,zone_id=?,team_id=?,max_participants=?,description=?,latitude=?,longitude=?,updated_at=? WHERE id=?'; c.execute(sql,(ctx['suggested_code'],clean(request.form.get('title')),request.form.get('event_type'),request.form.get('status'),request.form.get('start_at'),request.form.get('end_at') or None,clean(request.form.get('location')) or None,project_id,zone_id,team_id,int(request.form.get('max_participants') or 0),clean(request.form.get('description')) or None,request.form.get('latitude') or None,request.form.get('longitude') or None,datetime.now().isoformat(timespec='minutes'),eid)); c.commit(); c.close(); log_action('edit','event',eid); flash('Événement modifié.'); return redirect('/events/'+str(eid))
 c.close(); return page('Modifier événement',EVENT_FORM,e=e,cancel_url='/events/'+str(eid),**ctx)

@app.post('/events/<int:eid>/delete')
@login_required
@permission_required('event.manage')
def event_delete(eid):
 c=db(); e=c.execute('SELECT id,title FROM events WHERE id=? AND active=1',(eid,)).fetchone()
 if not e:c.close();flash('Événement introuvable.');return redirect('/events')
 participants=c.execute('SELECT COUNT(*) n FROM event_participants WHERE event_id=?',(eid,)).fetchone()['n']
 if participants:
  c.execute("UPDATE events SET active=0,status='Annulé',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec='minutes'),eid));message='Événement archivé afin de conserver les inscriptions.';action='archive'
 else:
  c.execute('DELETE FROM events WHERE id=?',(eid,));message='Événement supprimé.';action='delete'
 c.commit();c.close();log_action(action,'event',eid,e['title']);flash(message);return redirect(request.form.get('return_to') or '/events')

@app.post('/events/<int:eid>/register')
@login_required
@permission_required('event.register')
def event_register(eid):
 c=db(); e=c.execute('SELECT * FROM events WHERE id=? AND active=1',(eid,)).fetchone()
 if not e or e['status'] in ('Terminé','Annulé'): flash('Inscription impossible.'); c.close(); return redirect('/events/'+str(eid))
 count=c.execute("SELECT COUNT(*) n FROM event_participants WHERE event_id=? AND status='Inscrit'",(eid,)).fetchone()['n']
 if e['max_participants'] and count>=e['max_participants']: flash('Événement complet.'); c.close(); return redirect('/events/'+str(eid))
 now=datetime.now().isoformat(timespec='minutes'); c.execute("INSERT INTO event_participants(event_id,user_id,status,registered_at) VALUES(?,?,'Inscrit',?) ON CONFLICT(event_id,user_id) DO UPDATE SET status='Inscrit',registered_at=excluded.registered_at",(eid,session['uid'],now)); c.commit(); c.close(); log_action('register','event',eid); flash('Inscription confirmée.'); return redirect('/events/'+str(eid))

@app.post('/events/<int:eid>/cancel')
@login_required
def event_cancel(eid):
 c=db(); c.execute("UPDATE event_participants SET status='Annulé' WHERE event_id=? AND user_id=?",(eid,session['uid'])); c.commit(); c.close(); log_action('cancel_registration','event',eid); flash('Inscription annulée.'); return redirect('/events/'+str(eid))

@app.post('/events/<int:eid>/participants/<int:uid>/attendance')
@login_required
@permission_required('event.manage')
def event_attendance(eid,uid):
 c=db(); p=c.execute('SELECT attendance_status FROM event_participants WHERE event_id=? AND user_id=?',(eid,uid)).fetchone(); now=datetime.now().isoformat(timespec='minutes')
 if p:
  new='Non pointé' if p['attendance_status']=='Présent' else 'Présent'; c.execute('UPDATE event_participants SET attendance_status=?,checked_in_at=? WHERE event_id=? AND user_id=?',(new,now if new=='Présent' else None,eid,uid)); c.commit()
 c.close(); return redirect('/events/'+str(eid))

@app.route('/volunteer/events')
@login_required
@permission_required('event.view')
def volunteer_events():
 return redirect('/events')

@app.route('/missions')
@login_required
def missions_page():
 f=filters_from_request(); c=db(); guard=common_filter_guard(c,f)
 if guard: c.close(); return guard
 opts=common_filter_options(c,f); ctx=active_context(c); ids=[int(x['id']) for x in accessible_filter_projects(c,ctx)]
 w=['m.active=1']; p=[]
 if ctx.get('type')=='personal': w.append('m.association_id IS NULL')
 elif ctx.get('type')=='association':
  if ids: w.append('m.project_id IN ('+','.join('?'*len(ids))+')'); p.extend(ids)
  else: w.append('1=0')
 elif not is_super_admin(): w.append('1=0')
 if f['q']: w.append('(m.code LIKE ? OR m.title LIKE ? OR m.description LIKE ?)'); p += ['%'+f['q']+'%']*3
 if f['status']: w.append('m.status=?'); p.append(f['status'])
 if f['priority']: w.append('m.priority=?'); p.append(f['priority'])
 if f['action_type']: w.append('m.mission_type=?'); p.append(f['action_type'])
 if f['project_id']: w.append('m.project_id=?'); p.append(f['project_id'])
 if f['zone_id']: w.append('m.zone_id=?'); p.append(f['zone_id'])
 if f['volunteer_id']: w.append('(m.leader_user_id=? OR EXISTS(SELECT 1 FROM mission_participants mpf WHERE mpf.mission_id=m.id AND mpf.user_id=?))'); p += [f['volunteer_id'],f['volunteer_id']]
 if f['date_from']: w.append('date(m.start_at)>=date(?)'); p.append(f['date_from'])
 if f['date_to']: w.append('date(m.start_at)<=date(?)'); p.append(f['date_to'])
 apply_common_geo_filters(w,p,f,'pr')
 rows=c.execute("SELECT m.*,pr.name project_name,z.name zone_name,t.name team_name,u.name leader_name,(SELECT COUNT(*) FROM mission_participants mp WHERE mp.mission_id=m.id) participant_count FROM missions m LEFT JOIN projects pr ON pr.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id LEFT JOIN users u ON u.id=m.leader_user_id WHERE "+' AND '.join(w)+" ORDER BY CASE m.status WHEN 'En cours' THEN 1 WHEN 'Planifiée' THEN 2 ELSE 3 END,m.start_at DESC,m.id DESC",p).fetchall(); c.close()
 return page('Missions',"""<div class="section-title"><h2>Liste des missions</h2>{% if admin %}<a class="btn" href="/missions/new">+ Nouvelle mission</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{f.q}}"></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Type<select name="action_type"><option value="">Tous</option>{% for x in ['Plantation','Arrosage','Entretien','Inventaire','Nettoyage'] %}<option {% if f.action_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Statut<select name="status"><option value="">Tous</option>{% for x in ['Planifiée','En cours','Terminée','Annulée'] %}<option {% if f.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Priorité<select name="priority"><option value="">Toutes</option>{% for x in ['Basse','Normale','Haute','Urgente'] %}<option {% if f.priority==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Bénévole<select name="volunteer_id"><option value="">Tous</option>{% for x in volunteers %}<option value="{{x.id}}" {% if f.volunteer_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Du<input type="date" name="date_from" value="{{f.date_from}}"></label><label>Au<input type="date" name="date_to" value="{{f.date_to}}"></label><button class="btn">Filtrer</button><a class="btn alt" href="/missions">Effacer</a></form><div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Mission</th><th>Date</th><th>Projet / Zone</th><th>Équipe</th><th>Participants</th><th>Priorité</th><th>Progression</th><th>Statut</th><th></th></tr>{% for m in rows %}<tr><td>{{m.code}}</td><td><a href="/missions/{{m.id}}"><b>{{m.title}}</b></a><div class="sub">{{m.mission_type or ''}}</div></td><td>{{m.start_at or '—'}}</td><td>{{m.project_name or '—'}} / {{m.zone_name or '—'}}</td><td>{{m.team_name or '—'}}</td><td>{{m.participant_count}}</td><td>{{m.priority or 'Normale'}}</td><td>{{m.completed_count or 0}} / {{m.target_count or 0}}</td><td><span class="badge {% if m.status=='Terminée' %}good{% elif m.status=='En cours' %}pending{% elif m.status=='Annulée' %}danger{% else %}watch{% endif %}">{{m.status}}</span></td><td><a class="btn alt" href="/missions/{{m.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="10">Aucune mission.</td></tr>{% endfor %}</table></div>""",rows=rows,f=f,admin=is_admin(),**opts)

@app.route('/missions/new',methods=['GET','POST'])
@login_required
def mission_new():
 c=db(); ac=active_context(c); aid=ac.get('association_id')
 if ac.get('type')!='association' or not aid or not is_admin(): c.close(); return ('Administration association requise',403)
 projects=association_operation_projects(c,aid,'can_manage_missions'); pids=[x['id'] for x in projects]
 zones=c.execute('SELECT id,name,project_id FROM zones WHERE active=1 AND project_id IN ('+(','.join('?'*len(pids)) if pids else 'NULL')+') ORDER BY name',pids).fetchall() if pids else []
 teams=c.execute('SELECT * FROM teams WHERE active=1 AND association_id=? ORDER BY name',(aid,)).fetchall(); people=association_operational_people(c,aid); leaders=people; volunteers=people; suggested=next_entity_code(c,'missions','code','MISSION'); opts=filter_options(c); opts.update(projects=projects,zones=zones)
 if request.method=='POST':
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None; team_id=request.form.get('team_id') or None; leader=request.form.get('leader_user_id') or None; participants=set(request.form.getlist('participant_ids'))
  if leader: participants.add(str(leader))
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,team_id,'can_manage_missions'); bad=validate_association_users(c,participants,aid)
  if not ok or bad: c.close(); return ((msg or 'Participant non autorisé : '+','.join(map(str,bad))),403)
  now=datetime.now().isoformat(timespec='minutes'); code=suggested
  try:
   cur=c.execute("INSERT INTO missions(code,title,mission_type,status,priority,project_id,zone_id,team_id,leader_user_id,start_at,end_at,target_count,completed_count,description,report,latitude,longitude,active,created_by_user_id,created_at,updated_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,NULL,?,?,1,?,?,?,?)",(code,request.form['title'].strip(),request.form.get('mission_type'),request.form.get('status') or 'Planifiée',request.form.get('priority') or 'Normale',project_id,zone_id,team_id,leader,request.form.get('start_at'),request.form.get('end_at'),request.form.get('target_count') or 0,request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,session['uid'],now,now,aid)); mid=cur.lastrowid
  except sqlite3.IntegrityError: c.close(); return ('Code mission déjà utilisé',409)
  for uid in participants: c.execute("INSERT OR IGNORE INTO mission_participants(mission_id,user_id,attendance_status,created_at) VALUES(?,?,'Invité',?)",(mid,uid,now))
  c.commit(); c.close(); log_action('create','mission',mid,request.form['title']); notify('Nouvelle mission',request.form['title'],'/missions/'+str(mid),leader); flash('Mission créée.'); return redirect('/missions/'+str(mid))
 c.close(); opts.update(volunteers=volunteers); return page('Nouvelle mission',"""<div class="card"><form method="post" class="form" id="missionForm"><label>Code<input name="code" value="{{suggested}}" readonly></label><label>Titre<input name="title" required></label><label>Type<select name="mission_type"><option>Plantation</option><option>Arrosage</option><option>Entretien</option><option>Inventaire</option><option>Nettoyage</option></select></label><label>Statut<select name="status"><option>Planifiée</option><option>En cours</option><option>Terminée</option><option>Annulée</option></select></label><label>Priorité<select name="priority"><option>Basse</option><option selected>Normale</option><option>Haute</option><option>Urgente</option></select></label><label>Projet<select name="project_id" id="missionProject"><option value="">—</option>{% for x in projects %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id" id="missionZone"><option value="">—</option></select></label><label>Équipe<select name="team_id" id="missionTeam"><option value="">—</option>{% for x in teams %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="leader_user_id" id="missionLeader"><option value="">—</option>{% for x in leaders %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at"></label><label>Fin<input type="datetime-local" name="end_at"></label><label>Objectif<input type="number" min="0" name="target_count"></label><label>Latitude<input id="missionLat" type="number" step="any" name="latitude"></label><label>Longitude<input id="missionLon" type="number" step="any" name="longitude"></label><div class="full">{{location_picker|safe}}</div><label class="full">Participants<select name="participant_ids" multiple size="7">{% for x in volunteers %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label class="full">Description<textarea name="description"></textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/missions">Annuler</a></div></form></div><script>async function missionZones(){missionZone.innerHTML='<option value="">—</option>';if(!missionProject.value)return;let rows=await fetch('/api/projects/'+missionProject.value+'/zones').then(r=>r.json());rows.forEach(x=>missionZone.add(new Option(x.name,x.id)))}async function missionLeaderFromTeam(){if(!missionTeam.value)return;let d=await fetch('/api/teams/'+missionTeam.value+'/leader').then(r=>r.json());if(d.leader_user_id)missionLeader.value=d.leader_user_id;if(d.project_id){missionProject.value=d.project_id;await missionZones();if(d.zone_id)missionZone.value=d.zone_id}}missionProject.addEventListener('change',missionZones);missionTeam.addEventListener('change',missionLeaderFromTeam);</script>""",suggested=suggested,teams=teams,leaders=leaders,location_picker=location_picker_markup('mission'),**opts)

@app.route('/missions/<int:mid>')
@login_required
def mission_detail(mid):
 c=db(); m=c.execute("SELECT m.*,p.name project_name,z.name zone_name,t.name team_name,u.name leader_name FROM missions m LEFT JOIN projects p ON p.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id LEFT JOIN users u ON u.id=m.leader_user_id WHERE m.id=?",(mid,)).fetchone()
 if not m: c.close(); return ('Mission introuvable',404)
 participant=c.execute('SELECT * FROM mission_participants WHERE mission_id=? AND user_id=?',(mid,session['uid'])).fetchone()
 allowed=is_admin() or bool(participant) or m['leader_user_id']==session['uid']
 if not allowed: c.close(); flash('Cette mission ne vous est pas attribuée.'); return redirect('/volunteer/missions')
 participants=c.execute("SELECT mp.*,u.name,u.phone FROM mission_participants mp JOIN users u ON u.id=mp.user_id WHERE mp.mission_id=? ORDER BY u.name",(mid,)).fetchall()
 actions=c.execute("SELECT a.*,u.name user_name FROM mission_actions a LEFT JOIN users u ON u.id=a.user_id WHERE a.mission_id=? ORDER BY a.id DESC LIMIT 100",(mid,)).fetchall()
 photos=c.execute("SELECT ph.*,u.name user_name FROM mission_photos ph LEFT JOIN users u ON u.id=ph.user_id WHERE ph.mission_id=? ORDER BY ph.id DESC",(mid,)).fetchall(); c.close()
 can_execute=not is_admin() and bool(participant)
 return page('Fiche mission',"""<div class="section-title"><div><h2>{{m.title}}</h2><span class="badge pending">{{m.code}}</span> <span class="badge watch">{{m.priority or 'Normale'}}</span></div><div>{% if admin %}<a class="btn alt" href="/missions/{{m.id}}/edit">Modifier</a> <form method="post" action="/missions/{{m.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cette mission ?')"><button class="action-btn action-delete">🗑 Supprimer</button></form>{% else %}<a class="btn alt" href="/volunteer/missions">Retour</a>{% endif %}</div></div>
<div class="grid kpis"><div class="card kpi"><small>Statut</small><b style="font-size:22px">{{m.status}}</b></div><div class="card kpi"><small>Objectif</small><b>{{m.target_count or 0}}</b></div><div class="card kpi"><small>Réalisé</small><b>{{m.completed_count or 0}}</b></div><div class="card kpi"><small>Participants</small><b>{{participants|length}}</b></div></div>
{% if can_execute %}<div class="card"><h3>Exécution terrain</h3><div class="toolbar">{% if m.status=='Planifiée' %}<form method="post" action="/missions/{{m.id}}/start"><button class="btn">▶ Commencer la mission</button></form>{% elif m.status=='En cours' %}<form method="post" action="/missions/{{m.id}}/complete" class="toolbar"><label>Nombre traité<input type="number" min="0" name="completed_count" value="{{m.completed_count or 0}}"></label><label>Compte rendu<input name="completion_notes" placeholder="Travail réalisé, difficultés…"></label><button class="btn">✓ Terminer la mission</button></form>{% endif %}</div></div>{% endif %}
<div class="grid two"><div class="card"><h3>Informations</h3><p><b>Type :</b> {{m.mission_type or '—'}}</p><p><b>Prévue :</b> {{m.start_at or '—'}} → {{m.end_at or '—'}}</p><p><b>Réelle :</b> {{m.actual_start_at or 'Non commencée'}} → {{m.actual_end_at or '—'}}</p><p><b>Projet / Zone :</b> {{m.project_name or '—'}} / {{m.zone_name or '—'}}</p><p><b>Équipe :</b> {{m.team_name or '—'}}</p><p><b>Responsable :</b> {{m.leader_name or '—'}}</p><p>{{m.description or ''}}</p></div><div class="card"><h3>Rapport</h3><p>{{m.completion_notes or m.report or 'Aucun rapport enregistré.'}}</p><p class="sub">GPS : {{m.latitude or '—'}}, {{m.longitude or '—'}}</p></div></div>
{% if can_execute or admin %}<div class="grid two"><div class="card"><h3>Ajouter une intervention</h3><form method="post" action="/missions/{{m.id}}/actions" class="form"><label>Type<select name="action_type"><option>Progression</option><option>Plantation</option><option>Arrosage</option><option>Contrôle</option><option>Entretien</option><option>Signalement</option></select></label><label>Quantité<input type="number" min="0" name="quantity" value="0"></label><label class="full">Détails<textarea name="details" required></textarea></label><label>Latitude<input name="latitude" type="number" step="any"></label><label>Longitude<input name="longitude" type="number" step="any"></label><div class="full"><button class="btn">Enregistrer</button></div></form></div><div class="card"><h3>Ajouter une photo</h3><form method="post" action="/missions/{{m.id}}/photos" class="form"><label class="full">URL ou donnée de la photo<input name="photo_url" required placeholder="Photo prise ou choisie"></label><label class="full">Légende<input name="caption"></label><div class="full"><button class="btn">Ajouter la photo</button></div></form></div></div>{% endif %}
<div class="grid two"><div class="card"><h3>Journal de mission</h3>{% for a in actions %}<div class="priority"><b>{{a.action_type}} — {{a.user_name or 'Système'}}</b><span>{{a.created_at}}{% if a.quantity %} • {{a.quantity}} traité(s){% endif %}</span><div>{{a.details or ''}}</div></div>{% else %}<p class="sub">Aucune intervention enregistrée.</p>{% endfor %}</div><div class="card"><h3>Photos ({{photos|length}})</h3>{% for ph in photos %}<div class="priority"><b>{{ph.caption or 'Photo de mission'}}</b><span>{{ph.user_name or '—'}} • {{ph.created_at}}</span><a href="{{ph.photo_url}}" target="_blank">Voir la photo</a></div>{% else %}<p class="sub">Aucune photo.</p>{% endfor %}</div></div>
<div class="card"><h3>Participants ({{participants|length}})</h3><table><tr><th>Nom</th><th>Téléphone</th><th>Présence</th>{% if admin %}<th>Action</th>{% endif %}</tr>{% for p in participants %}<tr><td>{{p.name}}</td><td>{{p.phone}}</td><td>{{p.attendance_status}}</td>{% if admin %}<td><form method="post" action="/missions/{{m.id}}/participants/{{p.user_id}}"><select name="attendance_status"><option {% if p.attendance_status=='Invité' %}selected{% endif %}>Invité</option><option {% if p.attendance_status=='Confirmé' %}selected{% endif %}>Confirmé</option><option {% if p.attendance_status=='Présent' %}selected{% endif %}>Présent</option><option {% if p.attendance_status=='Absent' %}selected{% endif %}>Absent</option></select><button class="btn alt">Enregistrer</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="4">Aucun participant affecté.</td></tr>{% endfor %}</table></div>""",m=m,participants=participants,actions=actions,photos=photos,admin=(is_admin() and (is_super_admin() or int(active_context().get('association_id') or 0)==int(m['association_id'] or 0))),can_execute=can_execute)

@app.post('/missions/<int:mid>/start')
@login_required
def mission_start(mid):
 c=db(); allowed=c.execute('SELECT 1 FROM mission_participants WHERE mission_id=? AND user_id=?',(mid,session['uid'])).fetchone()
 if not allowed and not is_admin(): c.close(); flash('Mission non attribuée.'); return redirect('/volunteer/missions')
 now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE missions SET status='En cours',actual_start_at=COALESCE(actual_start_at,?),updated_at=? WHERE id=? AND active=1",(now,now,mid)); c.execute("INSERT INTO mission_actions(mission_id,user_id,action_type,details,created_at) VALUES(?,?, 'Démarrage','Mission commencée',?)",(mid,session['uid'],now)); c.execute("UPDATE mission_participants SET attendance_status='Présent' WHERE mission_id=? AND user_id=?",(mid,session['uid'])); c.commit(); c.close(); log_action('start','mission',mid); flash('Mission commencée.'); return redirect('/missions/'+str(mid))

@app.post('/missions/<int:mid>/complete')
@login_required
def mission_complete(mid):
 c=db(); allowed=c.execute('SELECT 1 FROM mission_participants WHERE mission_id=? AND user_id=?',(mid,session['uid'])).fetchone()
 if not allowed and not is_admin(): c.close(); flash('Mission non attribuée.'); return redirect('/volunteer/missions')
 now=datetime.now().isoformat(timespec='minutes'); count=max(0,int(request.form.get('completed_count') or 0)); notes=clean(request.form.get('completion_notes'))
 c.execute("UPDATE missions SET status='Terminée',completed_count=?,completion_notes=?,actual_end_at=?,updated_at=? WHERE id=?",(count,notes,now,now,mid)); c.execute("INSERT INTO mission_actions(mission_id,user_id,action_type,details,quantity,created_at) VALUES(?,?, 'Clôture',?,?,?)",(mid,session['uid'],notes,count,now)); c.commit(); c.close(); log_action('complete','mission',mid,notes); flash('Mission terminée et rapport enregistré.'); return redirect('/missions/'+str(mid))

@app.post('/missions/<int:mid>/actions')
@login_required
def mission_add_action(mid):
 c=db(); allowed=is_admin() or bool(c.execute('SELECT 1 FROM mission_participants WHERE mission_id=? AND user_id=?',(mid,session['uid'])).fetchone())
 if not allowed: c.close(); flash('Action non autorisée.'); return redirect('/volunteer/missions')
 now=datetime.now().isoformat(timespec='minutes'); qty=max(0,int(request.form.get('quantity') or 0)); c.execute('INSERT INTO mission_actions(mission_id,user_id,action_type,details,quantity,latitude,longitude,created_at) VALUES(?,?,?,?,?,?,?,?)',(mid,session['uid'],request.form.get('action_type') or 'Progression',clean(request.form.get('details')),qty,request.form.get('latitude') or None,request.form.get('longitude') or None,now));
 if qty: c.execute('UPDATE missions SET completed_count=MIN(COALESCE(target_count,0),COALESCE(completed_count,0)+?),updated_at=? WHERE id=?',(qty,now,mid))
 c.commit(); c.close(); log_action('action','mission',mid,request.form.get('action_type')); flash('Intervention ajoutée au journal.'); return redirect('/missions/'+str(mid))

@app.post('/missions/<int:mid>/photos')
@login_required
def mission_add_photo(mid):
 c=db(); allowed=is_admin() or bool(c.execute('SELECT 1 FROM mission_participants WHERE mission_id=? AND user_id=?',(mid,session['uid'])).fetchone())
 if not allowed: c.close(); flash('Action non autorisée.'); return redirect('/volunteer/missions')
 photo=clean(request.form.get('photo_url'))
 if not photo: c.close(); flash('Photo obligatoire.'); return redirect('/missions/'+str(mid))
 now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO mission_photos(mission_id,user_id,photo_url,caption,created_at) VALUES(?,?,?,?,?)',(mid,session['uid'],photo,clean(request.form.get('caption')),now)); c.execute("INSERT INTO mission_actions(mission_id,user_id,action_type,details,created_at) VALUES(?,?, 'Photo','Photo ajoutée à la mission',?)",(mid,session['uid'],now)); c.commit(); c.close(); flash('Photo ajoutée.'); return redirect('/missions/'+str(mid))

@app.route('/missions/<int:mid>/edit',methods=['GET','POST'])
@login_required
def mission_edit(mid):
 c=db(); m=c.execute('SELECT * FROM missions WHERE id=?',(mid,)).fetchone()
 if not m: c.close(); return ('Mission introuvable',404)
 aid=m['association_id']; ac=active_context(c)
 if not (is_super_admin() or (ac.get('type')=='association' and int(ac.get('association_id') or 0)==int(aid or 0) and is_admin())): c.close(); return ('Administration de l’association de la mission requise',403)
 projects=association_operation_projects(c,aid,'can_manage_missions'); pids=[x['id'] for x in projects]; zones=c.execute('SELECT id,name,project_id FROM zones WHERE active=1 AND project_id IN ('+(','.join('?'*len(pids)) if pids else 'NULL')+') ORDER BY name',pids).fetchall() if pids else []; teams=c.execute('SELECT * FROM teams WHERE active=1 AND association_id=? ORDER BY name',(aid,)).fetchall(); people=association_operational_people(c,aid); leaders=people; volunteers=people; selected={r['user_id'] for r in c.execute('SELECT user_id FROM mission_participants WHERE mission_id=?',(mid,))}; opts=filter_options(c); opts.update(projects=projects,zones=zones)
 if request.method=='POST':
  project_id=request.form.get('project_id') or None; zone_id=request.form.get('zone_id') or None; team_id=request.form.get('team_id') or None; leader=request.form.get('leader_user_id') or None; participants=set(request.form.getlist('participant_ids'))
  if leader: participants.add(str(leader))
  ok,msg=validate_operational_links(c,aid,project_id,zone_id,team_id,'can_manage_missions'); bad=validate_association_users(c,participants,aid)
  if not ok or bad: c.close(); return ((msg or 'Participant non autorisé : '+','.join(map(str,bad))),403)
  now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE missions SET title=?,mission_type=?,status=?,priority=?,project_id=?,zone_id=?,team_id=?,leader_user_id=?,start_at=?,end_at=?,target_count=?,completed_count=?,description=?,report=?,latitude=?,longitude=?,updated_at=? WHERE id=?",(request.form['title'].strip(),request.form.get('mission_type'),request.form.get('status'),request.form.get('priority'),project_id,zone_id,team_id,leader,request.form.get('start_at'),request.form.get('end_at'),request.form.get('target_count') or 0,request.form.get('completed_count') or 0,request.form.get('description'),request.form.get('report'),request.form.get('latitude') or None,request.form.get('longitude') or None,now,mid)); c.execute('DELETE FROM mission_participants WHERE mission_id=?',(mid,))
  for uid in participants: c.execute("INSERT INTO mission_participants(mission_id,user_id,attendance_status,created_at) VALUES(?,?,'Invité',?)",(mid,uid,now))
  c.commit(); c.close(); log_action('edit','mission',mid,request.form['status']); flash('Mission modifiée.'); return redirect('/missions/'+str(mid))
 c.close(); opts.update(volunteers=volunteers); return page('Modifier mission',"""<div class="card"><form method="post" class="form" id="missionEdit"><label>Code<input value="{{m.code}}" readonly></label><label>Titre<input name="title" value="{{m.title}}" required></label><label>Type<select name="mission_type">{% for x in ['Plantation','Arrosage','Entretien','Inventaire','Nettoyage'] %}<option {% if m.mission_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Statut<select name="status">{% for x in ['Planifiée','En cours','Terminée','Annulée'] %}<option {% if m.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Priorité<select name="priority">{% for x in ['Basse','Normale','Haute','Urgente'] %}<option {% if m.priority==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Projet<select name="project_id" id="missionProject"><option value="">—</option>{% for x in projects %}<option value="{{x.id}}" {% if m.project_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id" id="missionZone"><option value="">—</option>{% for x in zones %}{% if x.project_id==m.project_id %}<option value="{{x.id}}" {% if m.zone_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endif %}{% endfor %}</select></label><label>Équipe<select name="team_id"><option value="">—</option>{% for x in teams %}<option value="{{x.id}}" {% if m.team_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="leader_user_id"><option value="">—</option>{% for x in leaders %}<option value="{{x.id}}" {% if m.leader_user_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at" value="{{m.start_at or ''}}"></label><label>Fin<input type="datetime-local" name="end_at" value="{{m.end_at or ''}}"></label><label>Objectif<input type="number" min="0" name="target_count" value="{{m.target_count or 0}}"></label><label>Réalisé<input type="number" min="0" name="completed_count" value="{{m.completed_count or 0}}"></label><label>Latitude<input name="latitude" value="{{m.latitude or ''}}"></label><label>Longitude<input name="longitude" value="{{m.longitude or ''}}"></label><div class="full">{{location_picker|safe}}</div><label class="full">Participants<select name="participant_ids" multiple size="7">{% for x in volunteers %}<option value="{{x.id}}" {% if x.id in selected %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Description<textarea name="description">{{m.description or ''}}</textarea></label><label class="full">Rapport<textarea name="report">{{m.report or ''}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/missions/{{m.id}}">Annuler</a></div></form></div><script>async function missionZones(){let old=missionZone.value;missionZone.innerHTML='<option value="">—</option>';if(!missionProject.value)return;let rows=await fetch('/api/projects/'+missionProject.value+'/zones').then(r=>r.json());rows.forEach(x=>{let o=new Option(x.name,x.id);if(String(x.id)==String(old))o.selected=true;missionZone.add(o)})}missionProject.addEventListener('change',missionZones);</script>""",m=m,teams=teams,leaders=leaders,selected=selected,location_picker=location_picker_markup('missionedit'),**opts)

@app.post('/missions/<int:mid>/participants/<int:uid>')
@login_required
def mission_participant_status(mid,uid):
 if not is_admin(): return redirect('/missions/'+str(mid))
 c=db(); c.execute('UPDATE mission_participants SET attendance_status=? WHERE mission_id=? AND user_id=?',(request.form.get('attendance_status'),mid,uid)); c.commit(); c.close(); log_action('attendance','mission',mid,str(uid)+':'+request.form.get('attendance_status','')); return redirect('/missions/'+str(mid))

@app.post('/missions/<int:mid>/archive')
@login_required
def mission_archive(mid):
 if not is_admin(): return redirect('/missions')
 c=db(); c.execute('UPDATE missions SET active=0,updated_at=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),mid)); c.commit(); c.close(); log_action('archive','mission',mid); flash('Mission archivée.'); return redirect('/missions')

@app.post('/missions/<int:mid>/delete')
@login_required
def mission_delete(mid):
 if not is_admin():return redirect('/missions')
 c=db(); m=c.execute('SELECT * FROM missions WHERE id=?',(mid,)).fetchone()
 if not m:c.close();return redirect('/missions')
 linked=c.execute('SELECT COUNT(*) n FROM mission_actions WHERE mission_id=?',(mid,)).fetchone()['n']
 if linked:c.execute('UPDATE missions SET active=0 WHERE id=?',(mid,));msg='Mission archivée.'
 else:c.execute('DELETE FROM missions WHERE id=?',(mid,));msg='Mission supprimée.'
 c.commit();c.close();flash(msg);return redirect('/missions')

@app.route('/notifications')
@login_required
def notifications_page():
 category=clean(request.args.get('category')); unread_only=request.args.get('unread')=='1'; c=db(); where=['(user_id=? OR user_id IS NULL)']; params=[session['uid']]
 if category: where.append('category=?'); params.append(category)
 if unread_only: where.append('is_read=0')
 rows=c.execute('SELECT * FROM notifications WHERE '+' AND '.join(where)+' ORDER BY is_read,created_at DESC LIMIT 150',params).fetchall(); unread=c.execute('SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0',(session['uid'],)).fetchone()['n']; categories=c.execute("SELECT DISTINCT COALESCE(category,'Général') category FROM notifications WHERE user_id=? OR user_id IS NULL ORDER BY category",(session['uid'],)).fetchall(); c.close()
 return page('Notifications',"""<div class="section-title"><h2>Centre de notifications <span class="badge pending">{{unread}} non lues</span></h2><a class="btn" href="/action-center">Centre d’actions</a></div><div class="notif-help">Ouvrir cette liste ne marque aucune notification comme lue. Le compteur diminue seulement après ouverture explicite d’une notification, marquage manuel comme lue, ou traitement réel d’une demande.</div><form class="card toolbar"><label>Catégorie<select name="category"><option value="">Toutes</option>{% for c in categories %}<option {% if category==c.category %}selected{% endif %}>{{c.category}}</option>{% endfor %}</select></label><label>État<select name="unread"><option value="0">Toutes</option><option value="1" {% if unread_only %}selected{% endif %}>Non lues seulement</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/notifications">Effacer</a></form><form method="post" action="/notifications/bulk" class="card"><div class="bulk-bar"><label><input type="checkbox" id="selectAll" onclick="toggleAll(this)"> Tout sélectionner</label> <button class="btn" name="decision" value="accept">✓ Accepter la sélection</button> <button class="btn red" name="decision" value="reject">✕ Refuser la sélection</button></div><div style="overflow:auto"><table><tr><th></th><th>État</th><th>Catégorie</th><th>Date</th><th>Titre</th><th>Message</th><th>Actions</th></tr>{% for n in rows %}<tr><td><input class="notif-check" type="checkbox" name="notification_ids" value="{{n.id}}" {% if not n.action_type %}disabled{% endif %}></td><td>{% if n.is_read %}<span class="badge good">Lue</span>{% else %}<span class="badge pending">Nouvelle</span>{% endif %}</td><td><span class="badge watch">{{n.category or 'Général'}}</span></td><td>{{n.created_at}}</td><td><b>{{n.title}}</b><div class="notif-state">{% if n.decision %}<span class="badge good">Décision : {{n.decision}}</span>{% endif %}{% if n.processed_at %}<span class="sub">Traitée {{n.processed_at}}</span>{% elif n.read_at %}<span class="sub">Lue {{n.read_at}}</span>{% endif %}</div></td><td>{{n.message or ''}}</td><td><div class="quick-actions">{% if n.action_type and not n.decision %}<button class="btn" formaction="/notifications/{{n.id}}/decide/accept" formmethod="post">Accepter</button><button class="btn red" formaction="/notifications/{{n.id}}/decide/reject" formmethod="post">Refuser</button>{% endif %}{% if n.link %}<a class="btn alt" href="/notifications/{{n.id}}/open">Ouvrir</a>{% else %}<button class="btn alt" formaction="/notifications/{{n.id}}/read" formmethod="post">Marquer lue</button>{% endif %}</div></td></tr>{% else %}<tr><td colspan="7">Aucune notification.</td></tr>{% endfor %}</table></div></form><script>function toggleAll(x){document.querySelectorAll('.notif-check:not(:disabled)').forEach(c=>c.checked=x.checked)}</script>""",rows=rows,unread=unread,categories=categories,category=category,unread_only=unread_only)

@app.post('/notifications/read-all')
@login_required
def notifications_read_all():
 c=db(); now=datetime.now().isoformat(timespec='minutes'); cur=c.execute("UPDATE notifications SET is_read=1,read_at=COALESCE(read_at,?) WHERE (user_id=? OR user_id IS NULL) AND is_read=0 AND action_type IS NULL",(now,session['uid'])); c.commit(); c.close(); flash(f'{cur.rowcount} notification(s) informative(s) marquée(s) comme lue(s).','success'); return redirect('/notifications')

@app.post('/notifications/<int:nid>/read')
@login_required
def notification_read(nid):
 c=db(); now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('UPDATE notifications SET is_read=1,read_at=COALESCE(read_at,?) WHERE id=? AND (user_id=? OR user_id IS NULL)',(now,nid,session['uid'])); c.commit(); c.close(); flash('Notification marquée comme lue.','success' if cur.rowcount else 'warning'); return redirect('/notifications')

@app.route('/notifications/<int:nid>/open')
@login_required
def notification_open(nid):
 c=db(); n=c.execute('SELECT * FROM notifications WHERE id=? AND (user_id=? OR user_id IS NULL)',(nid,session['uid'])).fetchone()
 if not n: c.close(); return redirect('/notifications')
 now=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE notifications SET is_read=1,read_at=COALESCE(read_at,?) WHERE id=?',(now,nid)); c.commit(); link=n['link']; c.close(); return redirect(link or '/notifications')

@app.route('/search')
@login_required
def global_search():
 q=request.args.get('q','').strip(); data={}
 if q:
  like='%'+q+'%'; c=db()
  data['Arbres']=[dict(id=r['id'],label=r['label'],link='/trees/'+str(r['id'])+'/edit') for r in c.execute("SELECT id,tree_code label FROM trees WHERE active=1 AND (tree_code LIKE ? OR species LIKE ?) LIMIT 20",(like,like)).fetchall()]
  data['Bénévoles']=[dict(id=r['id'],label=r['label'],link='/volunteers/'+str(r['id'])) for r in c.execute("SELECT id,name label FROM users WHERE active=1 AND (name LIKE ? OR phone LIKE ? OR email LIKE ?) LIMIT 20",(like,like,like)).fetchall()]
  data['Projets']=[dict(id=r['id'],label=r['label'],link='/projects/'+str(r['id'])+'/edit') for r in c.execute("SELECT id,name label FROM projects WHERE active=1 AND (name LIKE ? OR code LIKE ?) LIMIT 20",(like,like)).fetchall()]
  data['Zones']=[dict(id=r['id'],label=r['label'],link='/zones/'+str(r['id'])+'/edit') for r in c.execute("SELECT id,name label FROM zones WHERE active=1 AND (name LIKE ? OR code LIKE ?) LIMIT 20",(like,like)).fetchall()]
  data['Équipes']=[dict(id=r['id'],label=r['label'],link='/teams/'+str(r['id'])) for r in c.execute("SELECT id,name label FROM teams WHERE active=1 AND name LIKE ? LIMIT 20",(like,)).fetchall()]
  data['Espèces']=[dict(id=r['id'],label=r['label'],link='/species') for r in c.execute("SELECT id,name_fr label FROM species WHERE active=1 AND (name_fr LIKE ? OR name_ar LIKE ? OR scientific_name LIKE ?) LIMIT 20",(like,like,like)).fetchall()]
  data['Missions']=[dict(id=r['id'],label=r['label'],link='/missions/'+str(r['id'])) for r in c.execute("SELECT id,title label FROM missions WHERE active=1 AND (title LIKE ? OR code LIKE ? OR description LIKE ?) LIMIT 20",(like,like,like)).fetchall()]; c.close()
 return page('Recherche universelle',"""<form class="card toolbar"><label>Rechercher dans toute l’application<input name="q" value="{{q}}" autofocus placeholder="Code arbre, nom, téléphone, projet, mission…"></label><button class="btn">Rechercher</button></form>{% if q %}<div class="grid two">{% for key,rows in data.items() %}<div class="card"><h3>{{key}} ({{rows|length}})</h3>{% for r in rows %}<a class="priority" style="display:block;text-decoration:none;color:inherit" href="{{r.link}}"><b>{{r.label or 'Sans nom'}}</b><span class="sub">Ouvrir la fiche</span></a>{% else %}<p class="sub">Aucun résultat</p>{% endfor %}</div>{% endfor %}</div>{% endif %}""",q=q,data=data)


@app.route('/zones/<int:zid>/watering-batch',methods=['GET','POST'])
@login_required
def zone_watering_batch(zid):
 c=db(); z=c.execute("SELECT z.*,p.name project_name FROM zones z LEFT JOIN projects p ON p.id=z.project_id WHERE z.id=? AND z.active=1",(zid,)).fetchone()
 if not z: c.close(); return ('Zone introuvable',404)
 trees=c.execute("SELECT t.id,t.tree_code,t.health_status,t.watering_status,t.latitude,t.longitude,s.name_fr species_name FROM trees t LEFT JOIN species s ON s.id=t.species_id WHERE t.zone_id=? AND t.active=1 AND t.approval_status='approved' ORDER BY CASE t.watering_status WHEN 'Urgent' THEN 0 WHEN 'À arroser' THEN 1 ELSE 2 END,t.tree_code",(zid,)).fetchall()
 if request.method=='POST':
  ids=[]
  for raw in request.form.getlist('tree_ids'):
   try: ids.append(int(raw))
   except ValueError: pass
  valid={r['id'] for r in trees}; ids=[x for x in ids if x in valid]
  if not ids:
   c.close(); flash('Sélectionnez au moins un arbre.'); return redirect(f'/zones/{zid}/watering-batch')
  now=datetime.now().isoformat(timespec='minutes'); total=float(request.form.get('total_liters') or 0); per_tree=round(total/len(ids),2) if total else None
  cur=c.execute('INSERT INTO watering_batches(zone_id,user_id,watered_at,tree_count,total_liters,source,notes,latitude,longitude,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(zid,session['uid'],now,len(ids),total or None,request.form.get('source'),request.form.get('notes'),request.form.get('latitude') or None,request.form.get('longitude') or None,now)); bid=cur.lastrowid
  for tid in ids:
   tr=c.execute('SELECT health_status FROM trees WHERE id=?',(tid,)).fetchone()
   c.execute('INSERT INTO watering_logs(tree_id,watered_at,user_id,volunteer,quantity_range,quantity_liters,source,notes,latitude,longitude,tree_condition,batch_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(tid,now,session['uid'],session['name'],'Arrosage groupé',per_tree,request.form.get('source'),request.form.get('notes'),request.form.get('latitude') or None,request.form.get('longitude') or None,tr['health_status'],bid,now))
   c.execute("UPDATE trees SET last_watered_at=?,watering_status='À jour' WHERE id=?",(now,tid))
  c.commit(); c.close(); log_action('water_batch','zone',zid,f'{len(ids)} arbres; {total} L'); flash(f'Arrosage groupé enregistré pour {len(ids)} arbres.'); return redirect('/zones/'+str(zid))
 tree_data=[dict(x) for x in trees if x['latitude'] is not None and x['longitude'] is not None]; c.close()
 return page('Arrosage groupé',"""<div class="section-title"><div><h2>Arroser la zone — {{z.name}}</h2><span class="sub">{{z.project_name}}</span></div><a class="btn alt" href="/zones/{{z.id}}">Annuler</a></div><form method="post"><div class="grid two"><div class="card"><div class="toolbar"><button type="button" class="btn alt" onclick="selectBy('all')">Tous</button><button type="button" class="btn alt" onclick="selectBy('due')">À arroser</button><button type="button" class="btn alt" onclick="selectBy('urgent')">Urgents</button><button type="button" class="btn alt" onclick="selectBy('none')">Aucun</button></div><div style="max-height:440px;overflow:auto"><table><tr><th></th><th>Arbre</th><th>Espèce</th><th>État</th></tr>{% for t in trees %}<tr><td><input class="tree-check" type="checkbox" name="tree_ids" value="{{t.id}}" data-water="{{t.watering_status}}"></td><td><a href="/tree/{{t.id}}">{{t.tree_code}}</a></td><td>{{t.species_name}}</td><td>{{t.watering_status}}</td></tr>{% else %}<tr><td colspan="4">Aucun arbre approuvé.</td></tr>{% endfor %}</table></div></div><div><div class="card"><div id="batchMap" class="real-map"></div></div><div class="card form"><label>Total d'eau (L)<input type="number" min="0" step="0.1" name="total_liters"></label><label>Source<select name="source"><option>Camion</option><option>Bidon</option><option>Réservoir</option><option>Goutte-à-goutte</option><option>Autre</option></select></label><label class="full">Observation<textarea name="notes"></textarea></label><input type="hidden" name="latitude" id="lat"><input type="hidden" name="longitude" id="lon"><div class="full"><b id="countSelected">0 arbre sélectionné</b></div><div class="full"><button class="btn">Enregistrer l'arrosage groupé</button> <a class="btn alt" href="/zones/{{z.id}}">Annuler</a></div></div></div></div></form><script>const data={{tree_data|tojson}};const m=L.map('batchMap').setView([{{z.latitude or 35.697}},{{z.longitude or -0.633}}],15);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20}).addTo(m);const marks={};data.forEach(t=>{marks[t.id]=L.circleMarker([t.latitude,t.longitude],{radius:8}).addTo(m).bindPopup(t.tree_code+' — '+t.species_name)});function refresh(){const c=[...document.querySelectorAll('.tree-check:checked')];countSelected.textContent=c.length+' arbre(s) sélectionné(s)';Object.values(marks).forEach(x=>x.setStyle({weight:2,fillOpacity:.35}));c.forEach(x=>marks[x.value]&&marks[x.value].setStyle({weight:5,fillOpacity:.9}))}function selectBy(k){document.querySelectorAll('.tree-check').forEach(x=>x.checked=k==='all'||(k==='due'&&x.dataset.water!=='À jour')||(k==='urgent'&&x.dataset.water==='Urgent'));refresh()}document.querySelectorAll('.tree-check').forEach(x=>x.addEventListener('change',refresh));if(navigator.geolocation)navigator.geolocation.getCurrentPosition(p=>{lat.value=p.coords.latitude;lon.value=p.coords.longitude});setTimeout(()=>m.invalidateSize(),150);</script>""",z=z,trees=trees,tree_data=tree_data)

@app.route('/zones/<int:zid>/planting-series',methods=['GET','POST'])
@login_required
def zone_planting_series(zid):
 c=db(); z=c.execute("SELECT z.*,p.name project_name FROM zones z LEFT JOIN projects p ON p.id=z.project_id WHERE z.id=? AND z.active=1",(zid,)).fetchone(); species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall()
 if not z: c.close(); return ('Zone introuvable',404)
 if request.method=='POST':
  ok_assign,msg_assign,p0,z0=validate_tree_assignment(c,z['project_id'],zid)
  if not ok_assign: c.close(); flash(msg_assign); return redirect(f'/zones/{zid}/planting-series')
  now=datetime.now().isoformat(timespec='minutes'); approval='approved' if is_admin() else 'pending'; code=None; qr=None
  cur=c.execute('INSERT INTO trees(species_id,project_id,zone_id,wilaya_id,commune_id,association_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,gps_accuracy,health_status,watering_status,approval_status,approved_by_user_id,approved_at,planting_type,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',(request.form['species_id'],z['project_id'],zid,p0['wilaya_id'],p0['commune_id'],p0['association_id'],request.form.get('planted_at') or date.today().isoformat(),session['uid'],session['name'],request.form.get('latitude') or None,request.form.get('longitude') or None,request.form.get('gps_accuracy') or None,'Bon','À jour',approval,session['uid'] if approval=='approved' else None,now if approval=='approved' else None,'série',request.form.get('notes'),now)); tid=cur.lastrowid
  if approval=='approved':
   code=f'TREE-{tid:05d}'; qr=f'QR-{code}'; c.execute('UPDATE trees SET tree_code=?,qr_code=? WHERE id=?',(code,qr,tid))
  c.commit(); c.close(); log_action('plant_series','tree',tid,f'zone {zid}'); flash('Arbre enregistré. Le formulaire reste ouvert pour le suivant.'); return redirect(f'/zones/{zid}/planting-series?last={tid}')
 last=None
 if request.args.get('last'): last=c.execute('SELECT id,tree_code,approval_status FROM trees WHERE id=? AND zone_id=?',(request.args.get('last'),zid)).fetchone()
 recent=c.execute("SELECT t.id,t.tree_code,t.approval_status,t.planted_at,s.name_fr species_name FROM trees t LEFT JOIN species s ON s.id=t.species_id WHERE t.zone_id=? ORDER BY t.id DESC LIMIT 10",(zid,)).fetchall(); c.close()
 return page('Plantation en série',"""<div class="section-title"><div><h2>Plantation en série — {{z.name}}</h2><span class="sub">Après chaque enregistrement, le formulaire reste prêt pour l'arbre suivant.</span></div><a class="btn alt" href="/zones/{{z.id}}">Terminer</a></div>{% if last %}<div class="card"><b>Dernier arbre :</b> {{last.tree_code or 'En attente de validation'}} — {{last.approval_status}}</div>{% endif %}<div class="grid two"><div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Rechercher une espèce<input type="search" id="speciesSearch" placeholder="Français, arabe, anglais ou nom scientifique" oninput="filterSpecies(this.value)"></label><label>Espèce<select id="speciesSelect" name="species_id" required>{% for s in species %}<option value="{{s.id}}">{{s.name_fr}}</option>{% endfor %}</select></label><label>Date<input type="date" name="planted_at" value="{{today}}"></label><label>Latitude<input id="lat" name="latitude"></label><label>Longitude<input id="lon" name="longitude"></label><input type="hidden" id="acc" name="gps_accuracy"><label class="full">Notes<textarea name="notes"></textarea></label><div class="full"><button class="btn">Enregistrer et continuer</button> <a class="btn alt" href="/zones/{{z.id}}">Annuler</a></div></form></div><div class="card"><h3>Dernières plantations de la zone</h3><table><tr><th>Code</th><th>Espèce</th><th>Date</th><th>Statut</th></tr>{% for t in recent %}<tr><td><a href="/tree/{{t.id}}">{{t.tree_code or 'En attente'}}</a></td><td>{{t.species_name}}</td><td>{{t.planted_at}}</td><td>{{t.approval_status}}</td></tr>{% endfor %}</table></div></div><script>if(navigator.geolocation)navigator.geolocation.getCurrentPosition(p=>{lat.value=p.coords.latitude;lon.value=p.coords.longitude;acc.value=p.coords.accuracy},{},{enableHighAccuracy:true,timeout:8000});</script>""",z=z,species=species,recent=recent,last=last,today=date.today().isoformat())

@app.route('/zones/<int:zid>/interventions')
@login_required
def zone_interventions(zid):
 c=db(); z=c.execute('SELECT * FROM zones WHERE id=?',(zid,)).fetchone()
 if not z: c.close(); return ('Zone introuvable',404)
 monthly=c.execute("SELECT substr(watered_at,1,7) month,COUNT(*) waterings,COALESCE(SUM(quantity_liters),0) liters FROM watering_logs wl JOIN trees t ON t.id=wl.tree_id WHERE t.zone_id=? GROUP BY substr(watered_at,1,7) ORDER BY month DESC LIMIT 12",(zid,)).fetchall(); batches=c.execute("SELECT wb.*,u.name user_name FROM watering_batches wb LEFT JOIN users u ON u.id=wb.user_id WHERE wb.zone_id=? ORDER BY wb.id DESC LIMIT 50",(zid,)).fetchall(); volunteers=c.execute("SELECT COALESCE(u.name,wl.volunteer) name,COUNT(*) actions,COALESCE(SUM(wl.quantity_liters),0) liters FROM watering_logs wl JOIN trees t ON t.id=wl.tree_id LEFT JOIN users u ON u.id=wl.user_id WHERE t.zone_id=? GROUP BY COALESCE(u.name,wl.volunteer) ORDER BY actions DESC LIMIT 20",(zid,)).fetchall(); c.close()
 return page('Interventions zone',"""<div class="section-title"><h2>Interventions — {{z.name}}</h2><a class="btn alt" href="/zones/{{z.id}}">Retour zone</a></div><div class="grid two"><div class="card"><h3>Arrosages groupés</h3><table><tr><th>Date</th><th>Arbres</th><th>Eau</th><th>Responsable</th></tr>{% for b in batches %}<tr><td>{{b.watered_at}}</td><td>{{b.tree_count}}</td><td>{{b.total_liters or '—'}} L</td><td>{{b.user_name or '—'}}</td></tr>{% else %}<tr><td colspan="4">Aucun arrosage groupé.</td></tr>{% endfor %}</table></div><div class="card"><h3>Activité des bénévoles</h3><table><tr><th>Bénévole</th><th>Actions</th><th>Eau</th></tr>{% for v in volunteers %}<tr><td>{{v.name}}</td><td>{{v.actions}}</td><td>{{'%.1f'|format(v.liters)}} L</td></tr>{% else %}<tr><td colspan="3">Aucune activité.</td></tr>{% endfor %}</table></div></div><div class="card"><h3>Évolution mensuelle</h3><table><tr><th>Mois</th><th>Arrosages</th><th>Volume</th></tr>{% for m in monthly %}<tr><td>{{m.month}}</td><td>{{m.waterings}}</td><td>{{'%.1f'|format(m.liters)}} L</td></tr>{% else %}<tr><td colspan="3">Aucune donnée.</td></tr>{% endfor %}</table></div>""",z=z,batches=batches,monthly=monthly)


@app.route('/volunteers/<int:uid>/permissions',methods=['GET','POST'])
@login_required
def volunteer_permissions(uid):
 if not is_admin(): return redirect('/')
 c=db(); u=c.execute('SELECT id,name FROM users WHERE id=?',(uid,)).fetchone()
 if not u: c.close(); return ('Bénévole introuvable',404)
 codes=['mission.view','intervention.view','intervention.create','team.view']
 perms=c.execute('SELECT * FROM permissions WHERE code IN (?,?,?,?) ORDER BY label',codes).fetchall()
 if request.method=='POST':
  selected=set(request.form.getlist('permissions'))
  for p in perms: c.execute('INSERT INTO user_permissions(user_id,permission_id,granted) VALUES(?,?,?) ON CONFLICT(user_id,permission_id) DO UPDATE SET granted=excluded.granted',(uid,p['id'],1 if p['code'] in selected else 0))
  c.commit(); c.close(); flash('Permissions du bénévole mises à jour.'); return redirect('/volunteers/'+str(uid))
 states={p['code']:has for p in perms for has in [bool(c.execute('SELECT granted FROM user_permissions WHERE user_id=? AND permission_id=?',(uid,p['id'])).fetchone()['granted']) if c.execute('SELECT granted FROM user_permissions WHERE user_id=? AND permission_id=?',(uid,p['id'])).fetchone() else False]}
 c.close(); return page('Permissions bénévole',"""<div class="card"><h2>{{u.name}}</h2><p>Les menus Missions, Interventions et Équipe restent masqués tant que le droit correspondant n’est pas accordé.</p><form method="post">{% for p in perms %}<label style="display:block;padding:12px;border-bottom:1px solid #ddd"><input style="width:auto" type="checkbox" name="permissions" value="{{p.code}}" {% if states.get(p.code) %}checked{% endif %}> <b>{{p.label}}</b><div class="sub">{{p.code}}</div></label>{% endfor %}<p><button class="btn">Enregistrer les droits</button> <a class="btn alt" href="/volunteers/{{u.id}}">Annuler</a></p></form></div>""",u=u,perms=perms,states=states)

@app.route('/association/edit',methods=['GET','POST'])
@login_required
def association_edit():
 ctx=active_context()
 if ctx.get('type')!='association' or ctx.get('role_code') not in ('association_admin','admin'): return ('Administration association requise',403)
 aid=ctx['association_id']; c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return redirect('/volunteer')
 if request.method=='POST':
  symbol=clean(request.form.get('map_symbol'))
  allowed=set(available_association_symbols(c,current_association_id=aid,include_pending=True))
  if symbol!=a['map_symbol'] and symbol not in allowed:
   c.close(); flash('Ce symbole est déjà utilisé ou réservé.'); return redirect('/association/edit')
  c.execute("UPDATE associations SET name=?,short_name=?,description=?,wilaya_id=?,commune_id=?,address=?,phone=?,email=?,website=?,map_symbol=?,updated_at=? WHERE id=?",
            (clean(request.form.get('name')),clean(request.form.get('short_name')),clean(request.form.get('description')),request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,clean(request.form.get('address')),clean(request.form.get('phone')),clean(request.form.get('email')),clean(request.form.get('website')),symbol,datetime.now().isoformat(timespec='minutes'),aid))
  c.commit(); c.close(); flash('Informations de l’association modifiées.'); return redirect('/association')
 symbols=[a['map_symbol']]+[x for x in available_association_symbols(c,current_association_id=aid,include_pending=True) if x!=a['map_symbol']]
 wilayas=c.execute("SELECT * FROM wilayas WHERE active=1 ORDER BY name").fetchall(); communes=c.execute("SELECT * FROM communes WHERE active=1 ORDER BY name").fetchall(); c.close()
 return page('Modifier association',"""<div class='card'><h2>Modifier {{a.name}}</h2><form method='post' class='form'><label>Nom<input name='name' value='{{a.name}}' required></label><label>Nom court<input name='short_name' value='{{a.short_name or ''}}'></label><label>Symbole<select name='map_symbol'>{% for s in symbols %}<option value='{{s}}' {% if s==a.map_symbol %}selected{% endif %}>{{s}}</option>{% endfor %}</select></label><label>Wilaya<select name='wilaya_id'><option value=''>—</option>{% for w in wilayas %}<option value='{{w.id}}' {% if w.id==a.wilaya_id %}selected{% endif %}>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>—</option>{% for x in communes %}<option value='{{x.id}}' {% if x.id==a.commune_id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Téléphone<input name='phone' value='{{a.phone or ''}}'></label><label>E-mail<input name='email' value='{{a.email or ''}}'></label><label>Site<input name='website' value='{{a.website or ''}}'></label><label class='full'>Adresse<input name='address' value='{{a.address or ''}}'></label><label class='full'>Description<textarea name='description'>{{a.description or ''}}</textarea></label><div class='full'><button class='btn'>Enregistrer</button><a class='btn alt' href='/association'>Annuler</a></div></form></div>""",a=a,symbols=symbols,wilayas=wilayas,communes=communes)

@app.route('/association')
@login_required
def association_dashboard():
 ctx=active_context()
 if ctx.get('type')!='association' or not ctx.get('association_id'):
  return redirect('/volunteer')
 c=db(); aid=ctx['association_id']
 a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return redirect('/volunteer')
 members=c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n']
 trees=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND association_id=?",(aid,)).fetchone()['n']
 projects=c.execute("SELECT COUNT(*) n FROM projects WHERE active=1 AND association_id=?",(aid,)).fetchone()['n']
 pending=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND association_id=? AND approval_status='pending'",(aid,)).fetchone()['n']
 c.close()
 admin=ctx.get('role_code') in ('association_admin','admin')
 return page('Accueil association',"""<div class='association-profile-hero'><div class='association-avatar'>{{a.map_symbol or '🌿'}}</div><div><div class='sub'>Profil Association</div><h2>{{a.name}}</h2><p>{{'Administrateur de cette association' if admin else 'Bénévole de cette association'}}</p></div></div><div class='grid kpis'><a class='card kpi' href='/association/trees'><small>Arbres</small><b>{{trees}}</b><span class='sub'>Voir les arbres</span></a><a class='card kpi' href='/association/projects'><small>Projets</small><b>{{projects}}</b><span class='sub'>Voir les projets</span></a><a class='card kpi' href='/association/members'><small>Membres</small><b>{{members}}</b><span class='sub'>Voir les membres</span></a>{% if admin %}<a class='card kpi' href='/plantings/pending'><small>Plantations en attente</small><b>{{pending}}</b></a>{% endif %}</div><div class='association-mobile-actions'>{% if admin %}<a class='btn' href='/association/edit'>✏️ Modifier l’association</a><form method='post' action='/association/archive-request'><input name='reason' placeholder='Motif de la demande d’archivage'><button class='btn amber'>🗄 Demander l’archivage</button></form>{% endif %}</div><div class='vertical-actions'><a class='vertical-action' href='/map'><span class='icon'>🗺</span><span>Carte de l’association</span></a><a class='vertical-action' href='/volunteer/trees'><span class='icon'>🌳</span><span>Arbres</span></a><a class='vertical-action' href='/projects'><span class='icon'>📁</span><span>Projets</span></a>{% if admin %}<a class='vertical-action' href='/membership-requests'><span class='icon'>👥</span><span>Gérer les membres</span></a>{% endif %}</div>""",a=a,admin=admin,trees=trees,projects=projects,members=members,pending=pending)

@app.route('/volunteer')
@login_required
def volunteer_dashboard():
 if is_admin(): return redirect('/')
 c=db(); uid=session['uid']
 can_missions=has_permission('mission.view')
 can_interventions=has_permission('intervention.view') or has_permission('intervention.create')
 can_team=has_permission('team.view')
 my_trees=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND planted_by_user_id=?",(uid,)).fetchone()['n']
 need_water=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND planted_by_user_id=? AND watering_status IN ('À arroser','Urgent')",(uid,)).fetchone()['n']
 missions=c.execute("SELECT COUNT(*) n FROM mission_participants mp JOIN missions m ON m.id=mp.mission_id WHERE mp.user_id=? AND m.active=1 AND m.status IN ('Planifiée','En cours')",(uid,)).fetchone()['n']
 unread=c.execute("SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0",(uid,)).fetchone()['n']
 recent_missions=c.execute("SELECT m.*,z.name zone_name FROM mission_participants mp JOIN missions m ON m.id=mp.mission_id LEFT JOIN zones z ON z.id=m.zone_id WHERE mp.user_id=? AND m.active=1 ORDER BY COALESCE(m.start_at,m.created_at) DESC LIMIT 5",(uid,)).fetchall()
 priority=c.execute("SELECT t.id,t.tree_code,t.watering_status,t.health_status,s.name_fr species_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.active=1 AND t.approval_status='approved' AND (t.planted_by_user_id=? OR t.zone_id IN (SELECT zone_id FROM assignments WHERE user_id=? AND active=1)) AND (t.watering_status IN ('À arroser','Urgent') OR t.health_status IN ('À surveiller','En danger')) ORDER BY CASE t.watering_status WHEN 'Urgent' THEN 0 WHEN 'À arroser' THEN 1 ELSE 2 END LIMIT 8",(uid,uid)).fetchall()
 c.close()
 ctx=active_context(); return page('Accueil bénévole',"""<div class="vol-hero"><div class="sub" style="color:#d6e9dc">Espace bénévole privé</div><h2 style="margin:5px 0">Bonjour {{session.get('name')}} 👋</h2><div>{{my_trees}} arbre(s) suivi(s) • {{need_water}} à arroser • {{unread}} notification(s)</div></div><div class="card volunteer-association-actions"><h3>🏛 Associations</h3><div class="association-mobile-actions"><a class="btn" href="/public/associations">🏛 Consulter les associations</a><a class="btn alt" href="/association-request/new">➕ Créer une association</a></div></div><div class="vertical-actions volunteer-home-actions"><a class="vertical-action" href="/volunteer/trees"><span class="icon">🌳</span><span>Mes arbres</span></a><a class="vertical-action" href="/volunteer/gps-quick"><span class="icon">📍</span><span>Position GPS rapide</span></a><a class="vertical-action" href="/planting/new"><span class="icon">🌱</span><span>Planter un arbre</span></a><a class="vertical-action" href="/volunteer/watering"><span class="icon">💧</span><span>Arroser</span></a><a class="vertical-action" href="/volunteer/scan"><span class="icon">📷</span><span>Scanner un QR code</span></a><a class="vertical-action" href="/map"><span class="icon">🗺️</span><span>Carte</span></a><a class="vertical-action" href="/volunteer/donate"><span class="icon">🎁</span><span>Faire un don</span></a><a class="vertical-action" href="/volunteer/events"><span class="icon">📆</span><span>Événements</span></a>{% if can_missions %}<a class="vertical-action" href="/volunteer/missions"><span class="icon">📋</span><span>Mes missions</span></a>{% endif %}{% if can_interventions %}<a class="vertical-action" href="/interventions"><span class="icon">🛠</span><span>Interventions</span></a>{% endif %}{% if can_team %}<a class="vertical-action" href="/volunteer/team"><span class="icon">👥</span><span>Mon équipe</span></a>{% endif %}<a class="vertical-action" href="/notifications"><span class="icon">🔔</span><span>Notifications</span></a><a class="vertical-action" href="/volunteer/profile"><span class="icon">👤</span><span>Mon profil</span></a></div><div class="card desktop-dashboard-details" style="margin-top:16px"><h3>Priorités terrain</h3><table><tr><th>Arbre</th><th>Zone</th><th>État</th><th></th></tr>{% for t in priority %}<tr><td>{{t.tree_code or 'En attente'}}<div class="sub">{{t.species_name}}</div></td><td>{{t.zone_name or '—'}}</td><td>{{t.watering_status}} / {{t.health_status}}</td><td><a class="btn alt" href="/tree/{{t.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="4">Aucune priorité actuellement.</td></tr>{% endfor %}</table></div><div class="bottom-space"></div>""",missions=missions,my_trees=my_trees,need_water=need_water,unread=unread,priority=priority,recent_missions=recent_missions,can_missions=can_missions,can_interventions=can_interventions,can_team=can_team)

@app.route('/volunteer/missions')
@login_required
@permission_required('mission.view')
def volunteer_missions():
 c=db(); scope,sp=context_condition('t'); rows=c.execute("SELECT m.*,p.name project_name,z.name zone_name,t.name team_name,mp.attendance_status FROM mission_participants mp JOIN missions m ON m.id=mp.mission_id LEFT JOIN projects p ON p.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id WHERE mp.user_id=? AND m.active=1 ORDER BY COALESCE(m.start_at,m.created_at) DESC",(session['uid'],)).fetchall(); c.close()
 return page('Mes missions',"""<div class="card" style="overflow:auto"><table><tr><th>Mission</th><th>Projet / Zone</th><th>Date</th><th>État</th><th>Participation</th><th></th></tr>{% for m in rows %}<tr><td><a href="/missions/{{m.id}}"><b>{{m.title}}</b></a><div class="sub">{{m.mission_type}} • {{m.priority}}</div></td><td>{{m.project_name or '—'}} / {{m.zone_name or '—'}}</td><td>{{m.start_at or 'À confirmer'}}</td><td>{{m.status}}</td><td>{{m.attendance_status}}</td><td><a class="btn" href="/missions/{{m.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="6">Aucune mission assignée.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/volunteer/trees')
@login_required
def volunteer_trees():
 f=filters_from_request(); c=db(); where,params=tree_where(f); opts=filter_options(c); assocs=association_options(c); volunteers=c.execute("SELECT id,name FROM users WHERE active=1 ORDER BY name").fetchall()
 rows=c.execute("""SELECT t.*,s.name_fr species_name,z.name zone_name,p.name project_name,u.name volunteer_name,a.name association_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN associations a ON a.id=t.association_id WHERE """+where+" AND t.approval_status='approved' ORDER BY t.id DESC",params).fetchall(); c.close()
 opts.update(volunteers=volunteers,associations=assocs); return page('Arbres',"""<div class="section-title"><div><h2>🌳 Mes arbres</h2><p class="sub">Vos arbres et vos accès rapides.</p></div><div class="section-actions"><a class="btn" href="/map?quick=mine">🗺️ Ma carte</a><a class="btn" href="/planting/new">+ Planter</a></div></div><div class="filter-quick card"><a class="btn alt" href="/volunteer/trees">Tous</a><a class="btn alt" href="/volunteer/trees?quick=mine">Mes arbres</a><a class="btn alt" href="/volunteer/trees?quick=individuals">Individuels</a><a class="btn alt" href="/volunteer/trees?quick=associations">Associations</a><a class="btn alt" href="/volunteer/trees?quick=watering">À arroser</a><a class="btn" href="/map?{{request.query_string.decode()}}">🗺 Carte avec ces filtres</a><button class="btn" onclick="advancedFilters.classList.toggle('open')">⚙️ Plus de filtres</button></div><form id="advancedFilters" class="filter-panel card" method="get"><input type="hidden" name="quick" value="{{f.quick}}"><div class="form"><label>Type<select name="owner_type"><option value="">Tous</option><option value="individual">Individuels</option><option value="association">Associations</option></select></label><label>Association<select name="association_id"><option value="">Toutes</option>{% for x in associations %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Bénévole<select name="volunteer_id"><option value="">Tous</option>{% for x in volunteers %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}">{{x.name_fr}}</option>{% endfor %}</select></label><label>Arrosage<select name="watering_status"><option value="">Tous</option><option>À jour</option><option>À arroser</option><option>Urgent</option></select></label></div><div class="filter-actions"><a class="btn alt" href="/volunteer/trees">Réinitialiser</a><button class="btn">Appliquer</button></div></form><div class="card"><b>{{rows|length}} arbre(s) trouvé(s)</b><div style="overflow:auto"><table><tr><th>Code</th><th>Espèce</th><th>Origine</th><th>Projet / Zone</th><th>État</th><th></th></tr>{% for t in rows %}<tr><td>{{t.tree_code or '—'}}</td><td>{{t.species_name}}</td><td>{{t.association_name or ('Individuel — '+(t.volunteer_name or 'Bénévole'))}}</td><td>{{t.project_name or '—'}} / {{t.zone_name or '—'}}</td><td>{{t.health_status}}<br><span class="sub">{{t.watering_status}}</span></td><td><a class="btn alt" href="/tree/{{t.id}}">Fiche</a></td></tr>{% else %}<tr><td colspan="6">Aucun arbre avec ces filtres.</td></tr>{% endfor %}</table></div></div>""",rows=rows,f=f,**opts)

@app.route('/volunteer/trees/no-gps')
@login_required
def volunteer_trees_no_gps():
 c=db(); rows=c.execute("""SELECT t.*,s.name_fr species_name,z.name zone_name,p.name project_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN projects p ON p.id=t.project_id
 WHERE t.active=1 AND t.planted_by_user_id=? AND (t.latitude IS NULL OR t.longitude IS NULL)
 ORDER BY COALESCE(t.planted_at,t.created_at),t.id""",(session['uid'],)).fetchall(); c.close()
 return page('Mes arbres sans GPS',"""<div class='section-title'><div><h2>Arbres sans position</h2><p class='sub'>{{rows|length}} arbre(s) à géolocaliser.</p></div>{% if rows %}<a class='btn' href='/volunteer/gps-quick'>⚡ Démarrer le mode rapide</a>{% endif %}</div><div class='card' style='overflow:auto'><table><tr><th>Arbre</th><th>Espèce</th><th>Projet / Zone</th><th>Date</th><th></th></tr>{% for t in rows %}<tr><td>{{t.tree_code or ('Arbre #'+t.id|string)}}</td><td>{{t.species_name or t.species or '—'}}</td><td>{{t.project_name or 'Hors projet'}} / {{t.zone_name or 'Hors zone'}}</td><td>{{t.planted_at or '—'}}</td><td><a class='btn alt' href='/volunteer/gps-quick?tree_id={{t.id}}'>Positionner</a></td></tr>{% else %}<tr><td colspan='5'>Tous vos arbres sont géolocalisés.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/volunteer/gps-quick')
@login_required
def volunteer_gps_quick():
 c=db(); tid=request.args.get('tree_id',type=int); admin=is_admin(); scope='' if admin else ' AND t.planted_by_user_id=?'; scope_args=[] if admin else [session['uid']]
 if tid:
  tree=c.execute("""SELECT t.*,s.name_fr species_name,z.name zone_name,p.name project_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.id=? AND t.active=1"""+scope,[tid]+scope_args).fetchone()
 else:
  tree=c.execute("""SELECT t.*,s.name_fr species_name,z.name zone_name,p.name project_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.active=1 AND (t.latitude IS NULL OR t.longitude IS NULL)"""+scope+" ORDER BY COALESCE(t.planted_at,t.created_at),t.id LIMIT 1",scope_args).fetchone()
 total=c.execute("SELECT COUNT(*) n FROM trees t WHERE t.active=1 AND (t.latitude IS NULL OR t.longitude IS NULL)"+scope,scope_args).fetchone()['n']; c.close()
 return page('Position GPS rapide',"""{% if tree %}<div class='vol-hero'><h2>{{tree.species_name or tree.species or 'Arbre'}}</h2><div>{{tree.tree_code or ('Arbre #'+tree.id|string)}} • {{tree.project_name or 'Hors projet'}} • {{tree.zone_name or 'Hors zone'}}</div><div>{{total}} arbre(s) restent sans GPS</div></div><div class='card'><div id='gpsStatus' class='mobile-note'>Placez-vous devant l’arbre puis appuyez.</div><button class='btn' style='width:100%;min-height:64px;font-size:18px' onclick='saveGps()'>📍 Enregistrer ma position</button><a class='btn alt' style='display:block;text-align:center;margin-top:10px' href='/trees/{{tree.id}}/map'>🗺 Choisir sur la carte</a></div><form id='gpsForm' method='post' action='/volunteer/gps-quick/{{tree.id}}/save'><input type='hidden' name='latitude' id='quickLat'><input type='hidden' name='longitude' id='quickLon'><input type='hidden' name='gps_accuracy' id='quickAcc'></form><script>function saveGps(){navigator.geolocation.getCurrentPosition(p=>{quickLat.value=p.coords.latitude;quickLon.value=p.coords.longitude;quickAcc.value=p.coords.accuracy||'';gpsForm.submit()},e=>{gpsStatus.textContent='GPS indisponible. Vérifiez HTTPS et les autorisations.'},{enableHighAccuracy:true,timeout:15000})}</script>{% else %}<div class='card'><h2>✅ Terminé</h2><a class='btn' href='{{"/trees" if admin else "/volunteer/trees"}}'>Retour</a></div>{% endif %}""",tree=tree,total=total,admin=admin)

@app.post('/volunteer/gps-quick/<int:tid>/save')
@login_required
def volunteer_gps_quick_save(tid):
 lat=request.form.get('latitude'); lon=request.form.get('longitude'); acc=request.form.get('gps_accuracy')
 if not lat or not lon:
  flash('Position GPS manquante.'); return redirect('/volunteer/gps-quick?tree_id='+str(tid))
 c=db(); tree=c.execute('SELECT * FROM trees WHERE id=? AND active=1'+('' if is_admin() else ' AND planted_by_user_id=?'),(tid,) if is_admin() else (tid,session['uid'])).fetchone()
 if not tree:
  c.close(); flash('Arbre introuvable.'); return redirect('/volunteer/trees/no-gps')
 now=datetime.now().isoformat(timespec='minutes')
 if tree['latitude'] is None or tree['longitude'] is None:
  c.execute("UPDATE trees SET latitude=?,longitude=?,gps_accuracy=?,gps_review_status='ok',gps_updated_at=? WHERE id=?",(lat,lon,acc or None,now,tid))
  c.execute('INSERT INTO tree_gps_history(tree_id,old_latitude,old_longitude,new_latitude,new_longitude,accuracy,changed_by_user_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(tid,None,None,lat,lon,acc or None,session['uid'],'Position GPS initiale',now))
  c.commit(); log_action('gps_add','tree',tid)
 else:
  changes=json.dumps({'latitude':float(lat),'longitude':float(lon),'gps_accuracy':float(acc) if acc else None})
  c.execute("INSERT INTO tree_change_requests(tree_id,requested_by_user_id,changes_json,reason,status,created_at) VALUES(?,?,?,?, 'pending',?)",(tid,session['uid'],changes,'Correction GPS rapide',now)); c.commit(); log_action('gps_change_request','tree',tid)
 c.close(); flash('Position enregistrée. Passage à l’arbre suivant.'); return redirect('/volunteer/gps-quick')

@app.post('/volunteer/gps-quick/<int:tid>/verify')
@login_required
def volunteer_gps_quick_verify(tid):
 c=db(); c.execute("UPDATE trees SET gps_review_status='to_verify' WHERE id=?"+('' if is_admin() else ' AND planted_by_user_id=?'),(tid,) if is_admin() else (tid,session['uid'])); c.commit(); c.close(); log_action('gps_to_verify','tree',tid); flash('Arbre marqué à vérifier.'); return redirect('/volunteer/gps-quick')


@app.route('/volunteer/watering')
@login_required
def volunteer_watering():
 if is_admin(): return redirect('/watering/needs')
 c=db(); uid=session['uid']
 rows=c.execute("""SELECT t.id,t.tree_code,t.watering_status,t.health_status,t.last_watered_at,s.name_fr species_name,z.name zone_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id
 WHERE t.active=1 AND t.approval_status='approved'
 AND (t.planted_by_user_id=? OR t.zone_id IN (SELECT zone_id FROM assignments WHERE user_id=? AND active=1))
 AND (t.watering_status IN ('À arroser','Urgent') OR t.health_status IN ('À surveiller','En danger'))
 ORDER BY CASE t.watering_status WHEN 'Urgent' THEN 0 WHEN 'À arroser' THEN 1 ELSE 2 END,t.id""",(uid,uid)).fetchall(); c.close()
 return page('Arbres à arroser',"""<div class="section-title"><h2>Priorités d’arrosage</h2><a class="btn alt" href="/volunteer">Retour</a></div><div class="card" style="overflow:auto"><table><tr><th>Arbre</th><th>Espèce</th><th>Zone</th><th>Priorité</th><th>Dernier arrosage</th><th></th></tr>{% for t in rows %}<tr><td><b>{{t.tree_code or 'En attente'}}</b></td><td>{{t.species_name or '—'}}</td><td>{{t.zone_name or '—'}}</td><td><span class="badge {% if t.watering_status=='Urgent' %}danger{% else %}watch{% endif %}">{{t.watering_status}}</span></td><td>{{t.last_watered_at or 'Jamais'}}</td><td><a class="btn" href="/watering?tree_id={{t.id}}">Arroser</a> <a class="btn alt" href="/tree/{{t.id}}">Fiche</a></td></tr>{% else %}<tr><td colspan="6">Aucun arbre prioritaire actuellement.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/volunteer/scan')
@login_required
def volunteer_scan():
 if is_admin(): return redirect('/qr')
 return page('Scanner un QR',r"""<div class="scan-box"><div class="card"><h2>Scanner le QR d’un arbre</h2><p class="sub">Autorisez la caméra. Sur téléphone, utilisez HTTPS : les navigateurs peuvent bloquer caméra et GPS sur une adresse HTTP locale.</p><video id="camera" class="scan-preview" playsinline muted></video><p id="scanStatus" class="mobile-note">Caméra non démarrée.</p><div class="toolbar"><button class="btn" type="button" onclick="startScan()">Démarrer / réessayer</button><button class="btn alt" type="button" onclick="stopScan()">Arrêter</button><label class="btn alt" style="cursor:pointer">Lire une photo<input id="qrImage" type="file" accept="image/*" style="display:none" onchange="scanImage(this)"></label></div><form method="get" action="/volunteer/scan/result"><label>Code arbre ou QR<input name="code" id="manualCode" placeholder="Ex. TREE-0001" required></label><p><button class="btn">Ouvrir la fiche</button> <a class="btn alt" href="/volunteer">Annuler</a></p></form></div></div><script>
let stream=null,timer=null,detector=null;const st=document.getElementById('scanStatus');
function go(code){if(code)window.location='/volunteer/scan/result?code='+encodeURIComponent(code)}
async function getDetector(){if(!('BarcodeDetector' in window))throw new Error('BarcodeDetector indisponible');if(!detector)detector=new BarcodeDetector({formats:['qr_code']});return detector}
async function startScan(){stopScan(false);if(!window.isSecureContext&&location.hostname!=='localhost'&&location.hostname!=='127.0.0.1'){st.textContent='Connexion non sécurisée : ouvrez l’application en HTTPS pour autoriser la caméra.';return}if(!navigator.mediaDevices?.getUserMedia){st.textContent='Caméra non disponible. Utilisez une photo ou la saisie manuelle.';return}try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});const v=document.getElementById('camera');v.srcObject=stream;await v.play();st.textContent='Caméra active — placez le QR dans le cadre.';try{const d=await getDetector();timer=setInterval(async()=>{try{const codes=await d.detect(v);if(codes.length){stopScan(false);go(codes[0].rawValue)}}catch(e){}},500)}catch(e){st.textContent='Caméra active, mais lecture automatique indisponible. Utilisez « Lire une photo » ou saisissez le code.'}}catch(e){st.textContent='Impossible d’ouvrir la caméra : '+(e.name||'erreur')+'. Vérifiez l’autorisation et HTTPS.'}}
function stopScan(show=true){if(timer){clearInterval(timer);timer=null}if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}if(show)st.textContent='Caméra arrêtée.'}
async function scanImage(input){const f=input.files?.[0];if(!f)return;try{const d=await getDetector();const bmp=await createImageBitmap(f);const codes=await d.detect(bmp);if(codes.length)go(codes[0].rawValue);else st.textContent='Aucun QR détecté dans cette image.'}catch(e){st.textContent='Lecture de photo non prise en charge par ce navigateur. Utilisez la saisie manuelle.'}}
window.addEventListener('beforeunload',()=>stopScan(false));
</script>""")

@app.route('/volunteer/scan/result')
@login_required
def volunteer_scan_result():
 code=clean(request.args.get('code'))
 if not code: flash('Saisissez un code arbre ou QR.'); return redirect('/volunteer/scan')
 c=db(); t=c.execute("SELECT id FROM trees WHERE active=1 AND (upper(tree_code)=upper(?) OR upper(qr_code)=upper(?))",(code,code)).fetchone(); c.close()
 if not t: flash('Aucun arbre trouvé pour ce code.'); return redirect('/volunteer/scan')
 return redirect('/map?quick=mine&tree='+str(t['id']))

@app.route('/volunteer/profile',methods=['GET','POST'])
@login_required
def volunteer_profile():
 c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
 if request.method=='POST':
  values=user_form_values(request.form); errors=validate_user_form(c,values,user_id=session['uid'])
  current_pw=str(request.form.get('current_password') or ''); new_pw=str(request.form.get('new_password') or ''); confirm_pw=str(request.form.get('password_confirm') or '')
  if current_pw or new_pw or confirm_pw:
   if not check_password_hash(u['password_hash'],current_pw): errors.append('Le mot de passe actuel est incorrect.')
   if len(new_pw)<6: errors.append('Le nouveau mot de passe doit contenir au moins 6 caractères.')
   if new_pw!=confirm_pw: errors.append('La confirmation du nouveau mot de passe ne correspond pas.')
  if errors:
   for e in errors: flash(e)
  else:
   c.execute('UPDATE users SET first_name=?,last_name=?,name=?,sex=?,phone=?,email=?,wilaya_id=?,commune_id=?,birth_date=?,address=?,skills=?,availability=?,photo_url=? WHERE id=?',(values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],session['uid']))
   if new_pw: c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new_pw),session['uid']))
   c.commit(); session['name']=user_display_name(values['first_name'],values['last_name']); c.close(); flash('Profil mis à jour.'); return redirect('/volunteer/profile')
 opts=filter_options(c); c.close()
 return page('Mon profil',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{u.first_name or ''}}" required></label><label>Nom<input name="last_name" value="{{u.last_name or ''}}" required></label><label>Sexe<select name="sex"><option {% if u.sex=='Homme' %}selected{% endif %}>Homme</option><option {% if u.sex=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{u.phone or ''}}" required></label><label>E-mail<input type="email" name="email" value="{{u.email or ''}}"></label><label>Date de naissance<input type="date" name="birth_date" value="{{u.birth_date or ''}}"></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% for x in wilayas %}<option value="{{x.id}}" {% if u.wilaya_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% for x in communes %}<option value="{{x.id}}" {% if u.commune_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{u.address or ''}}"></label><label>Compétences<input name="skills" value="{{u.skills or ''}}"></label><label>Disponibilité<input name="availability" value="{{u.availability or ''}}"></label>{{photo|safe}}<div class="full card"><h3>🔐 Modifier le mot de passe</h3><p class="sub">Laissez ces champs vides si vous ne souhaitez pas modifier le mot de passe.</p><label>Mot de passe actuel<input type="password" name="current_password" autocomplete="current-password"></label><label>Nouveau mot de passe<input type="password" name="new_password" minlength="6" autocomplete="new-password"></label><label>Confirmer le nouveau mot de passe<input type="password" name="password_confirm" minlength="6" autocomplete="new-password"></label></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/volunteer">Annuler</a></div></form></div>""",u=u,photo=photo_fields(u['photo_url'] if u else '',prefix='profile'),**opts)

@app.route('/volunteer/team')
@login_required
@permission_required('team.view')
def volunteer_team():
 c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone(); team=None; members=[]
 if u and u['team_id']:
  team=c.execute('SELECT t.*,u.name leader_name FROM teams t LEFT JOIN users u ON u.id=t.leader_user_id WHERE t.id=?',(u['team_id'],)).fetchone()
  members=c.execute("SELECT u.id,u.name,u.phone,tm.status FROM team_members tm JOIN users u ON u.id=tm.user_id WHERE tm.team_id=? ORDER BY u.name",(u['team_id'],)).fetchall()
 c.close()
 return page('Mon équipe',"""{% if team %}<div class="card"><h2>{{team.name}}</h2><p><b>Chef :</b> {{team.leader_name or 'Non défini'}}</p><p><b>Mission :</b> {{team.mission or '—'}}</p></div><div class="card"><h3>Membres</h3><table><tr><th>Nom</th><th>Téléphone</th><th>État</th></tr>{% for m in members %}<tr><td>{{m.name}}</td><td>{{m.phone or '—'}}</td><td>{{m.status}}</td></tr>{% endfor %}</table></div>{% else %}<div class="card"><h2>Vous n’avez pas encore d’équipe</h2><p>Utilisez le bouton ci-dessous pour consulter ou envoyer une demande.</p><a class="btn" href="/team-requests">Demander à rejoindre une équipe</a></div>{% endif %}""",team=team,members=members)

# --- v1.8.0 Alpha 2 : Dons, Pépinière et Matériel ---
@app.route('/donations')
@login_required
@permission_required('donation.view')
def donations_list():
 c=db(); kind=request.args.get('type','Tous'); status_filter=request.args.get('status')
 # Legacy and mixed donations share the same detail rows. Only money is synchronized with cash.
 missing=c.execute("SELECT d.* FROM donations d WHERE d.donation_type='Argent' AND d.status='Confirmé' AND d.amount>0 AND NOT EXISTS (SELECT 1 FROM cash_movements cm WHERE cm.reference_type='donation' AND cm.reference_id=d.id AND cm.movement_type='Entrée')").fetchall()
 for d in missing: sync_donation_cash(c,d['id'])
 c.commit()
 where=""; args=[]
 clauses=[]
 scope,sp=context_condition('n'); clauses.append(scope); args.extend(sp)
 if kind in ('Argent','Arbres','Matériel'): clauses.append('n.donation_type=?'); args.append(kind)
 if status_filter=='pending': clauses.append("n.status='En attente'")
 if clauses: where=' WHERE '+' AND '.join(clauses)
 rows=c.execute("SELECT n.*,d.name donor_name,s.name_fr species_name,e.name equipment_name FROM donations n LEFT JOIN donors d ON d.id=n.donor_id LEFT JOIN species s ON s.id=n.species_id LEFT JOIN equipment e ON e.id=n.equipment_id"+where+" ORDER BY n.received_at DESC,n.group_id DESC,n.id DESC",args).fetchall()
 ts,tp=context_condition('donations'); total=c.execute("SELECT COALESCE(SUM(amount),0) v FROM donations WHERE status='Confirmé' AND donation_type='Argent' AND "+ts,tp).fetchone()['v']; c.close()
 body="""<div class='section-title'><h2>Gestion des dons</h2>{% if manage %}<a class='btn' href='/donations/new'>＋ Nouveau don mixte</a>{% endif %}</div>
 <div class='toolbar'><a class='action-btn action-view' href='/donations'>Tous</a><a class='action-btn action-view' href='/donations?type=Argent'>💶 Argent</a><a class='action-btn action-view' href='/donations?type=Matériel'>🧰 Matériel</a><a class='action-btn action-view' href='/donations?type=Arbres'>🌳 Arbres</a><a class='action-btn action-view' href='/donations/nature-summary'>📊 Totaux dons en nature</a></div>
 <div class='grid kpis'><div class='card kpi'><small>Dons d’argent en caisse</small><b>{{'%.2f'|format(total)}} DA</b></div><div class='card kpi'><small>Lignes affichées</small><b>{{rows|length}}</b></div></div>
 <div class='card'><table><tr><th>Date</th><th>Donateur</th><th>Type</th><th>Détail</th><th>État</th><th>Reçu</th><th></th></tr>{% for r in rows %}<tr><td>{{r.received_at}}</td><td>{{r.donor_name or 'Anonyme'}}</td><td>{{r.donation_type}}</td><td>{% if r.donation_type=='Argent' %}<b>{{'%.2f'|format(r.amount)}} DA</b>{% elif r.donation_type=='Arbres' %}🌳 {{r.species_name or 'Espèce'}} × {{r.quantity|int}}{% elif r.donation_type=='Matériel' %}🧰 {{r.equipment_name or 'Matériel'}} × {{r.quantity|int}}{% endif %}</td><td>{{r.status}}</td><td>{{r.receipt_number or '—'}}</td><td><div class='action-set'>{% if manage and r.status=='En attente' %}<form method='post' action='/donation-groups/{{r.group_id}}/decision/accept'><button class='action-btn action-primary'>✓ Accepter</button></form><form method='post' action='/donation-groups/{{r.group_id}}/decision/reject' onsubmit="return confirm('Refuser ce don complet ?')"><button class='action-btn action-delete'>✕ Refuser</button></form>{% endif %}<a class='action-btn action-view' href='/donations/{{r.id}}/receipt' target='_blank'>🖨 Imprimer</a>{% if manage %}<form method='post' action='/donations/{{r.id}}/delete' onsubmit="return confirm('Supprimer ou archiver ce don ?')"><button class='action-btn action-delete'>🗑 Supprimer</button></form>{% endif %}</div></td></tr>{% else %}<tr><td colspan='7'>Aucun don.</td></tr>{% endfor %}</table></div>"""
 return page('Dons',body,rows=rows,total=total,manage=has_permission('donation.manage'))

def sync_donation_cash(c, donation_id):
 d=c.execute('SELECT * FROM donations WHERE id=?',(donation_id,)).fetchone()
 if not d:return
 existing=c.execute("SELECT id FROM cash_movements WHERE reference_type='donation' AND reference_id=? AND movement_type='Entrée'",(donation_id,)).fetchone()
 if d['donation_type']=='Argent' and d['status']=='Confirmé' and float(d['amount'] or 0)>0:
  if existing:c.execute('UPDATE cash_movements SET amount=?,status=? WHERE id=?',(d['amount'],'Validé',existing['id']))
  else:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,status,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Dons','Entrée',d['amount'],'Don en argent','Don '+(d['receipt_number'] or str(donation_id)),'donation',donation_id,'Validé',d['created_by_user_id'],datetime.now().isoformat(timespec='minutes'),d['association_id']))

def _add_donation_line(c,gid,donor_id,status,receipt,dtype,amount=0,qty=0,species_id=None,equipment_id=None):
 c.execute('INSERT INTO donations(group_id,donor_id,donation_type,status,amount,currency,quantity,unit,received_at,estimated_value,species_id,equipment_id,receipt_number,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(gid,donor_id,dtype,status,amount,'DZD',qty,'DA' if dtype=='Argent' else ('plants' if dtype=='Arbres' else 'pièces'),date.today().isoformat(),0,species_id,equipment_id,receipt,session['uid'],datetime.now().isoformat(timespec='minutes'),current_association_id()))
 did=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; sync_donation_cash(c,did); return did

@app.route('/donations/new',methods=['GET','POST'])
@login_required
@permission_required('donation.manage')
def donation_new():
 c=db(); species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall(); equipment=c.execute('SELECT id,name,category FROM equipment WHERE active=1 ORDER BY category,name').fetchall()
 if request.method=='POST':
  receipt='DON-'+datetime.now().strftime('%Y%m%d-%H%M%S'); status=request.form.get('status') or 'Confirmé'; donor_name=clean(request.form.get('donor_name')); donor_id=None
  if donor_name:c.execute('INSERT INTO donors(name,donor_type,created_at) VALUES(?,?,?)',(donor_name,'Particulier',datetime.now().isoformat(timespec='minutes'))); donor_id=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
  c.execute('INSERT INTO donation_groups(donor_id,status,receipt_number,received_at,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(donor_id,status,receipt,date.today().isoformat(),session['uid'],datetime.now().isoformat(timespec='minutes'))); gid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
  count=0; amount=max(0.0,float(request.form.get('amount') or 0))
  if amount>0:_add_donation_line(c,gid,donor_id,status,receipt,'Argent',amount=amount); count+=1
  for sid,q in zip(request.form.getlist('species_id[]'),request.form.getlist('tree_quantity[]')):
   try:qv=max(0,int(q or 0))
   except:qv=0
   if sid and qv:_add_donation_line(c,gid,donor_id,status,receipt,'Arbres',qty=qv,species_id=sid); count+=1
  for eid,q in zip(request.form.getlist('equipment_id[]'),request.form.getlist('equipment_quantity[]')):
   try:qv=max(0,int(q or 0))
   except:qv=0
   if eid and qv:_add_donation_line(c,gid,donor_id,status,receipt,'Matériel',qty=qv,equipment_id=eid); count+=1
  if not count:c.rollback(); c.close(); flash('Ajoutez au moins un montant, une espèce ou un matériel.'); return redirect('/donations/new')
  c.commit(); c.close(); flash('Don mixte enregistré sous une référence unique.'); return redirect('/donations')
 c.close(); return page('Nouveau don mixte',"""<div class='card'><form method='post' class='form' id='mixedDonation'><label>Donateur<input name='donor_name' placeholder='Nom du donateur'></label><label>État<select name='status'><option>Confirmé</option><option>En attente</option></select></label>
 <div class='full card'><h3>💶 Argent <span class='sub'>(facultatif)</span></h3><label>Montant en DA<input type='number' min='0' step='0.01' name='amount' placeholder='0'></label></div>
 <div class='full card'><div class='section-title'><h3>🌳 Arbres</h3><button type='button' class='action-btn action-primary' onclick='addTree()'>＋ Ajouter une espèce</button></div><div id='treeRows'></div></div>
 <div class='full card'><div class='section-title'><h3>🧰 Matériel</h3><button type='button' class='action-btn action-primary' onclick='addEq()'>＋ Ajouter un matériel</button></div><div id='eqRows'></div></div>
 <div class='full action-set'><button class='action-btn action-primary'>✓ Enregistrer le don</button><a class='action-btn action-view' href='/donations'>Annuler</a></div></form></div>
 <template id='treeTpl'><div class='don-line'><select name='species_id[]'><option value=''>Choisir une espèce</option>{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}</option>{% endfor %}</select><input type='number' min='1' name='tree_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template>
 <template id='eqTpl'><div class='don-line'><select name='equipment_id[]'><option value=''>Choisir un matériel</option>{% for x in equipment %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select><input type='number' min='1' name='equipment_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template>
 <script>function addTree(){treeRows.append(treeTpl.content.cloneNode(true))}function addEq(){eqRows.append(eqTpl.content.cloneNode(true))}addTree();addEq();</script>""",species=species,equipment=equipment)

def sync_nature_donation_stock(c, donation_id):
 d=c.execute('SELECT * FROM donations WHERE id=?',(donation_id,)).fetchone()
 if not d or d['status']!='Confirmé' or d['donation_type'] not in ('Arbres','Matériel'): return
 if c.execute('SELECT 1 FROM donation_stock_sync WHERE donation_id=?',(donation_id,)).fetchone(): return
 qty=int(float(d['quantity'] or 0))
 if qty<=0:return
 now=datetime.now().isoformat(timespec='minutes')
 if d['donation_type']=='Arbres' and d['species_id']:
  st=c.execute("SELECT * FROM nursery_stock WHERE species_id=? AND COALESCE(location,'')=''",(d['species_id'],)).fetchone()
  if st:
   c.execute('UPDATE nursery_stock SET quantity_available=quantity_available+?,updated_at=? WHERE id=?',(qty,now,st['id'])); sid=st['id']
  else:
   c.execute('INSERT INTO nursery_stock(species_id,quantity_available,location,updated_at) VALUES(?,?,?,?)',(d['species_id'],qty,'',now)); sid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
  c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(sid,'Entrée don',qty,'Don '+(d['receipt_number'] or str(donation_id)),d['created_by_user_id'],now))
  c.execute('INSERT INTO donation_stock_sync(donation_id,sync_type,stock_id,quantity,created_at) VALUES(?,?,?,?,?)',(donation_id,'Arbres',sid,qty,now))
 elif d['donation_type']=='Matériel' and d['equipment_id']:
  c.execute('UPDATE equipment SET quantity_total=quantity_total+?,quantity_available=quantity_available+?,updated_at=? WHERE id=?',(qty,qty,now,d['equipment_id']))
  c.execute('INSERT INTO donation_stock_sync(donation_id,sync_type,stock_id,quantity,created_at) VALUES(?,?,?,?,?)',(donation_id,'Matériel',d['equipment_id'],qty,now))

@app.post('/donation-groups/<int:gid>/decision/<decision>')
@login_required
@permission_required('donation.manage')
def donation_group_decision(gid,decision):
 if decision not in ('accept','reject'): return redirect('/donations')
 c=db(); g=c.execute('SELECT * FROM donation_groups WHERE id=?',(gid,)).fetchone()
 if not g or g['status']!='En attente': c.close(); flash('Ce don a déjà été traité ou est introuvable.'); return redirect('/donations')
 new_status='Confirmé' if decision=='accept' else 'Refusé'
 c.execute('UPDATE donation_groups SET status=? WHERE id=?',(new_status,gid)); c.execute('UPDATE donations SET status=? WHERE group_id=?',(new_status,gid))
 if decision=='accept':
  for d in c.execute('SELECT id FROM donations WHERE group_id=?',(gid,)).fetchall():
   sync_donation_cash(c,d['id']); sync_nature_donation_stock(c,d['id'])
 creator=g['created_by_user_id']; now=datetime.now().isoformat(timespec='minutes')
 if creator:
  c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(creator,'Don '+('accepté' if decision=='accept' else 'refusé'),'Votre don '+(g['receipt_number'] or '')+' a été '+('accepté.' if decision=='accept' else 'refusé.'),'/volunteer/donate','Don',now))
 c.execute("UPDATE notifications SET decision=?,is_read=1 WHERE action_type='donation_group' AND action_id=?",('Acceptée' if decision=='accept' else 'Refusée',gid))
 c.commit(); c.close(); flash('Don accepté et synchronisé avec la caisse.' if decision=='accept' else 'Don refusé.'); return redirect('/donations')

@app.post('/donations/<int:did>/delete')
@login_required
@permission_required('donation.manage')
def donation_delete(did):
 c=db(); d=c.execute('SELECT * FROM donations WHERE id=?',(did,)).fetchone()
 if not d:c.close();return redirect('/donations')
 linked=c.execute("SELECT COUNT(*) n FROM cash_movements WHERE reference_type='donation' AND reference_id=?",(did,)).fetchone()['n']
 if linked or d['status']=='Confirmé':c.execute("UPDATE donations SET status='Archivé' WHERE id=?",(did,)); msg='Don archivé : historique conservé.'
 else:c.execute('DELETE FROM donations WHERE id=?',(did,)); msg='Don supprimé.'
 c.commit();c.close();flash(msg);return redirect('/donations')

@app.route('/donations/nature-summary')
@login_required
@permission_required('donation.view')
def donation_nature_summary():
 c=db(); ds,dp=context_condition('d')
 trees=c.execute("SELECT s.name_fr name,CAST(SUM(d.quantity) AS INTEGER) qty FROM donations d JOIN species s ON s.id=d.species_id WHERE d.status='Confirmé' AND d.donation_type='Arbres' AND "+ds+" GROUP BY s.id,s.name_fr ORDER BY qty DESC,s.name_fr",dp).fetchall()
 eq=c.execute("SELECT e.name name,CAST(SUM(d.quantity) AS INTEGER) qty FROM donations d JOIN equipment e ON e.id=d.equipment_id WHERE d.status='Confirmé' AND d.donation_type='Matériel' AND "+ds+" GROUP BY e.id,e.name ORDER BY qty DESC,e.name",dp).fetchall()
 tt=sum(r['qty'] for r in trees); te=sum(r['qty'] for r in eq); c.close()
 body="""<div class='section-title'><div><h2>📊 Rapport des dons en nature</h2><p class='sub'>Statistiques d’origine uniquement : ce rapport n’est pas un stock. Le stock réel est dans 📦 Stock.</p></div><a class='action-btn action-view' href='/donations'>← Dons</a></div><div class='grid kpis'><div class='card kpi'><small>🌳 Arbres reçus</small><b>{{tt}}</b></div><div class='card kpi'><small>🧰 Matériels reçus</small><b>{{te}}</b></div></div><div class='grid'><div class='card'><h3>🌳 Détail par espèce</h3><table><tr><th>Espèce</th><th>Total reçu</th></tr>{% for r in trees %}<tr><td>{{r.name}}</td><td><b>{{r.qty}}</b></td></tr>{% else %}<tr><td colspan='2'>Aucun don d’arbre accepté.</td></tr>{% endfor %}</table></div><div class='card'><h3>🧰 Détail matériel</h3><table><tr><th>Matériel</th><th>Total reçu</th></tr>{% for r in eq %}<tr><td>{{r.name}}</td><td><b>{{r.qty}}</b></td></tr>{% else %}<tr><td colspan='2'>Aucun don de matériel accepté.</td></tr>{% endfor %}</table></div></div>"""
 return page('Rapport dons en nature',body,trees=trees,eq=eq,tt=tt,te=te)

@app.route('/stock')
@login_required
def stock_dashboard():
 if not (has_permission('nursery.view') or has_permission('equipment.view')):
  return 'Accès refusé',403
 c=db()
 ns,np=context_condition('n'); es,ep=context_condition('e'); trees=c.execute("SELECT n.*,s.name_fr species_name,(n.quantity_available-n.quantity_reserved) free_qty,COALESCE((SELECT SUM(ds.quantity) FROM donation_stock_sync ds JOIN donations d ON d.id=ds.donation_id WHERE ds.sync_type='Arbres' AND ds.stock_id=n.id AND d.status='Confirmé'),0) donated_qty FROM nursery_stock n JOIN species s ON s.id=n.species_id WHERE "+ns+" ORDER BY s.name_fr",np).fetchall()
 equipment=c.execute("SELECT e.*,COALESCE((SELECT SUM(ds.quantity) FROM donation_stock_sync ds JOIN donations d ON d.id=ds.donation_id WHERE ds.sync_type='Matériel' AND ds.stock_id=e.id AND d.status='Confirmé'),0) donated_qty FROM equipment e WHERE e.active=1 AND "+es+" ORDER BY e.category,e.name",ep).fetchall()
 tree_total=sum(int(r['free_qty'] or 0) for r in trees); eq_total=sum(int(r['quantity_available'] or 0) for r in equipment)
 c.close()
 body="""<div class='section-title'><div><h2>📦 Stock unique</h2><p class='sub'>Une seule référence de stock physique. L’origine Don / Achat reste une information de traçabilité, jamais un stock séparé.</p></div><div class='action-set'><a class='action-btn action-view' href='/donations/nature-summary'>📊 Rapport dons en nature</a></div></div>
 <div class='grid kpis'><div class='card kpi'><small>🌳 Arbres disponibles</small><b>{{tree_total}}</b></div><div class='card kpi'><small>🧰 Matériels disponibles</small><b>{{eq_total}}</b></div></div>
 <div class='card'><div class='section-title'><h3>🌳 Arbres</h3><div class='action-set'>{% if nursery_manage %}<a class='action-btn action-primary' href='/nursery/new'>＋ Entrée manuelle</a><a class='action-btn action-view' href='/nursery/distribute'>🎁 Donner / distribuer</a>{% endif %}<a class='action-btn action-view' href='/nursery'>Historique arbres</a></div></div><table><tr><th>Espèce</th><th>Disponible</th><th>Réservé</th><th>Reçu par dons</th><th>Autres origines*</th><th></th></tr>{% for r in trees %}<tr><td><b>{{r.species_name}}</b></td><td>{{r.free_qty}}</td><td>{{r.quantity_reserved}}</td><td>{{r.donated_qty|int}}</td><td>{{[r.quantity_available-r.donated_qty,0]|max|int}}</td><td>{% if nursery_manage %}<a class='action-btn action-view' href='/nursery/{{r.id}}/movement'>Mouvement</a>{% endif %}</td></tr>{% else %}<tr><td colspan='6'>Aucun arbre en stock.</td></tr>{% endfor %}</table><p class='sub'>* Achats, entrées manuelles, production ou corrections. Le détail exact reste dans l’historique des mouvements.</p></div>
 <div class='card'><div class='section-title'><h3>🧰 Matériel</h3><div class='action-set'>{% if equipment_manage %}<a class='action-btn action-primary' href='/equipment/new'>＋ Ajouter</a>{% endif %}<a class='action-btn action-view' href='/equipment'>Prêts et historique</a></div></div><table><tr><th>Matériel</th><th>Catégorie</th><th>Disponible</th><th>Total inventaire</th><th>Reçu par dons</th><th>Autres origines*</th></tr>{% for r in equipment %}<tr><td><b>{{r.name}}</b></td><td>{{r.category or '—'}}</td><td>{{r.quantity_available}}</td><td>{{r.quantity_total}}</td><td>{{r.donated_qty|int}}</td><td>{{[r.quantity_total-r.donated_qty,0]|max|int}}</td></tr>{% else %}<tr><td colspan='6'>Aucun matériel en stock.</td></tr>{% endfor %}</table></div>"""
 return page('Stock unique',body,trees=trees,equipment=equipment,tree_total=tree_total,eq_total=eq_total,nursery_manage=has_permission('nursery.manage'),equipment_manage=has_permission('equipment.manage'))

@app.route('/nursery/distribute',methods=['GET','POST'])
@login_required
@permission_required('nursery.manage')
def nursery_distribute():
 c=db(); stocks=c.execute("SELECT n.id,n.quantity_available,n.quantity_reserved,s.name_fr species_name FROM nursery_stock n JOIN species s ON s.id=n.species_id WHERE n.quantity_available>0 ORDER BY s.name_fr").fetchall()
 if request.method=='POST':
  sid=int(request.form['stock_id']); qty=max(0,int(request.form.get('quantity') or 0)); st=c.execute('SELECT * FROM nursery_stock WHERE id=?',(sid,)).fetchone(); free=(st['quantity_available']-st['quantity_reserved']) if st else 0
  if not st or qty<=0: flash('Stock ou quantité invalide.')
  elif qty>free: flash('Stock insuffisant : '+str(free)+' disponible(s).')
  else:
   now=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE nursery_stock SET quantity_available=quantity_available-?,updated_at=? WHERE id=?',(qty,now,sid)); c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(sid,'Don / distribution',qty,(request.form.get('beneficiary_type') or '')+' — '+(request.form.get('beneficiary_name') or ''),session['uid'],now)); c.execute('INSERT INTO nursery_distributions(beneficiary_name,beneficiary_type,stock_id,quantity,distribution_date,project_id,notes,justification,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(request.form['beneficiary_name'],request.form['beneficiary_type'],sid,qty,request.form.get('distribution_date') or date.today().isoformat(),request.form.get('project_id') or None,clean(request.form.get('notes')) or None,clean(request.form.get('justification')) or None,session['uid'],now)); c.commit(); c.close(); flash('Don sortant enregistré et stock diminué.'); return redirect('/nursery')
 projects=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall(); c.close()
 return page('Don / distribution d’arbres',"""<div class='card'><form method='post' class='form'><label>Bénéficiaire<input name='beneficiary_name' required></label><label>Type<select name='beneficiary_type'><option>Association</option><option>Personne</option><option>École</option><option>Commune</option><option>Autre</option></select></label><label>Espèce / stock<select name='stock_id' required>{% for x in stocks %}<option value='{{x.id}}'>{{x.species_name}} — {{x.quantity_available-x.quantity_reserved}} disponible(s)</option>{% endfor %}</select></label><label>Quantité<input type='number' min='1' name='quantity' required></label><label>Date<input type='date' name='distribution_date' value='{{today}}'></label><label>Projet<select name='project_id'><option value=''>—</option>{% for p in projects %}<option value='{{p.id}}'>{{p.name}}</option>{% endfor %}</select></label><label class='full'>Justificatif / bon de sortie<input name='justification'></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full action-set'><button class='action-btn action-primary'>✓ Enregistrer la sortie</button><a class='action-btn action-view' href='/nursery'>Annuler</a></div></form></div>""",stocks=stocks,projects=projects,today=date.today().isoformat())

@app.route('/nursery')
@login_required
@permission_required('nursery.view')
def nursery_list():
 c=db(); rows=c.execute('SELECT n.*,s.name_fr species_name,(n.quantity_available-n.quantity_reserved) free_qty FROM nursery_stock n JOIN species s ON s.id=n.species_id ORDER BY s.name_fr').fetchall(); moves=c.execute('SELECT m.*,s.name_fr species_name FROM nursery_movements m JOIN nursery_stock n ON n.id=m.stock_id JOIN species s ON s.id=n.species_id ORDER BY m.id DESC LIMIT 20').fetchall(); c.close()
 body="""<div class='section-title'><div><h2>🌳 Stock arbres</h2><p class='sub'>Stock unique : dons, achats et autres entrées sont regroupés ici.</p></div>{% if manage %}<div class='action-set'><a class='action-btn action-primary' href='/nursery/new'>＋ Ajouter un stock</a><a class='action-btn action-view' href='/nursery/distribute'>🎁 Donner / distribuer des arbres</a><a class='action-btn action-view' href='/donations/nature-summary'>📊 Origine : dons reçus</a></div>{% endif %}</div><div class='card'><table><tr><th>Espèce</th><th>Lieu</th><th>Disponible</th><th>Réservé</th><th>Libre</th><th>Planté</th><th>Perdu</th><th></th></tr>{% for r in rows %}<tr><td>{{r.species_name}}</td><td>{{r.location or '—'}}</td><td>{{r.quantity_available}}</td><td>{{r.quantity_reserved}}</td><td><span class='badge {% if r.free_qty<=r.low_stock_threshold %}danger{% else %}good{% endif %}'>{{r.free_qty}}</span></td><td>{{r.quantity_planted}}</td><td>{{r.quantity_lost}}</td><td>{% if manage %}<a class='btn alt' href='/nursery/{{r.id}}/movement'>Mouvement</a>{% endif %}</td></tr>{% else %}<tr><td colspan='8'>Aucun stock.</td></tr>{% endfor %}</table></div><div class='card'><h3>Derniers mouvements</h3><table><tr><th>Date</th><th>Espèce</th><th>Type</th><th>Quantité</th><th>Note</th></tr>{% for m in moves %}<tr><td>{{m.created_at}}</td><td>{{m.species_name}}</td><td>{{m.movement_type}}</td><td>{{m.quantity}}</td><td>{{m.notes or '—'}}</td></tr>{% endfor %}</table></div>"""
 return page('Stock arbres',body,rows=rows,moves=moves,manage=has_permission('nursery.manage'))

@app.route('/nursery/new',methods=['GET','POST'])
@login_required
@permission_required('nursery.manage')
def nursery_new():
 c=db()
 if request.method=='POST':
  c.execute('INSERT INTO nursery_stock(species_id,quantity_available,quantity_reserved,quantity_planted,quantity_lost,low_stock_threshold,unit_value,location,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(request.form['species_id'],int(request.form.get('quantity_available') or 0),0,0,0,int(request.form.get('low_stock_threshold') or 10),float(request.form.get('unit_value') or 0),clean(request.form.get('location')) or None,datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close(); flash('Stock ajouté.'); return redirect('/nursery')
 species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall(); c.close()
 body="""<div class='card'><form method='post' class='form'><label>Espèce<select name='species_id'>{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}</option>{% endfor %}</select></label><label>Quantité<input type='number' min='0' name='quantity_available'></label><label>Seuil d’alerte<input type='number' min='0' name='low_stock_threshold' value='10'></label><label>Valeur unitaire (DA)<input type='number' step='0.01' name='unit_value'></label><label class='full'>Emplacement<input name='location'></label><div class='full'><button class='btn' type='submit'>Enregistrer</button> <a class='btn alt' href='/nursery'>Annuler</a></div></form></div>"""
 return page('Ajouter un stock',body,species=species)

@app.route('/nursery/<int:sid>/movement',methods=['GET','POST'])
@login_required
@permission_required('nursery.manage')
def nursery_movement(sid):
 c=db(); stock=c.execute('SELECT n.*,s.name_fr species_name FROM nursery_stock n JOIN species s ON s.id=n.species_id WHERE n.id=?',(sid,)).fetchone()
 if request.method=='POST':
  typ=request.form['movement_type']; qty=int(request.form.get('quantity') or 0); a=stock['quantity_available']; r=stock['quantity_reserved']; p=stock['quantity_planted']; l=stock['quantity_lost']
  if typ=='Entrée': a+=qty
  elif typ=='Réservation': r+=qty
  elif typ=='Libération': r=max(0,r-qty)
  elif typ=='Plantation':
   if qty>a-r: c.close(); flash('Stock insuffisant.'); return redirect('/nursery/'+str(sid)+'/movement')
   a-=qty; r=max(0,r-qty); p+=qty
  elif typ=='Don / distribution':
   if qty>a-r: c.close(); flash('Stock insuffisant.'); return redirect('/nursery/'+str(sid)+'/movement')
   a-=qty
  elif typ=='Perte': a=max(0,a-qty); l+=qty
  c.execute('UPDATE nursery_stock SET quantity_available=?,quantity_reserved=?,quantity_planted=?,quantity_lost=?,updated_at=? WHERE id=?',(a,r,p,l,datetime.now().isoformat(timespec='minutes'),sid)); c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(sid,typ,qty,clean(request.form.get('notes')) or None,session['uid'],datetime.now().isoformat(timespec='minutes'))); c.commit()
  if a-r<=stock['low_stock_threshold']: notify('Stock faible',stock['species_name']+' : '+str(a-r)+' plant(s) libres','/nursery',category='Pépinière')
  c.close(); flash('Mouvement enregistré.'); return redirect('/nursery')
 c.close(); body="""<div class='card'><h3>{{stock.species_name}}</h3><p>Disponible : {{stock.quantity_available}} — réservé : {{stock.quantity_reserved}}</p><form method='post' class='form'><label>Type<select name='movement_type'><option>Entrée</option><option>Réservation</option><option>Libération</option><option>Plantation</option><option>Don / distribution</option><option>Perte</option></select></label><label>Quantité<input type='number' min='1' name='quantity' required></label><label class='full'>Note<textarea name='notes'></textarea></label><div class='full'><button class='btn'>Enregistrer</button></div></form></div>"""; return page('Mouvement pépinière',body,stock=stock)

@app.route('/equipment')
@login_required
@permission_required('equipment.view')
def equipment_list():
 c=db(); rows=c.execute('SELECT * FROM equipment WHERE active=1 ORDER BY category,name').fetchall(); loans=c.execute("SELECT l.*,e.name equipment_name,u.name user_name FROM equipment_loans l JOIN equipment e ON e.id=l.equipment_id JOIN users u ON u.id=l.user_id WHERE l.status='En cours' ORDER BY l.due_at").fetchall(); c.close()
 body="""<div class='section-title'><div><h2>🧰 Stock matériel</h2><p class='sub'>Stock unique : matériel reçu en don ou acheté.</p></div>{% if manage %}<a class='btn' href='/equipment/new'>＋ Ajouter</a>{% endif %}</div><div class='card'><table><tr><th>Code</th><th>Nom</th><th>Catégorie</th><th>Total</th><th>Disponible</th><th>État</th><th></th></tr>{% for r in rows %}<tr><td>{{r.inventory_code}}</td><td>{{r.name}}</td><td>{{r.category or '—'}}</td><td>{{r.quantity_total}}</td><td>{{r.quantity_available}}</td><td>{{r.condition_status}}</td><td>{% if manage and r.quantity_available>0 %}<a class='btn alt' href='/equipment/{{r.id}}/loan'>Prêter</a>{% endif %}</td></tr>{% endfor %}</table></div><div class='card'><h3>Prêts en cours</h3><table><tr><th>Matériel</th><th>Bénévole</th><th>Qté</th><th>Retour prévu</th><th></th></tr>{% for l in loans %}<tr><td>{{l.equipment_name}}</td><td>{{l.user_name}}</td><td>{{l.quantity}}</td><td>{{l.due_at or '—'}}</td><td>{% if manage %}<form method='post' action='/equipment/loans/{{l.id}}/return'><button class='btn'>Retour</button></form>{% endif %}</td></tr>{% endfor %}</table></div>"""
 return page('Stock matériel',body,rows=rows,loans=loans,manage=has_permission('equipment.manage'))

@app.route('/equipment/new',methods=['GET','POST'])
@login_required
@permission_required('equipment.manage')
def equipment_new():
 if request.method=='POST':
  c=db(); qty=int(request.form.get('quantity_total') or 0); code=clean(request.form.get('inventory_code')) or 'MAT-'+datetime.now().strftime('%Y%m%d%H%M%S'); c.execute('INSERT INTO equipment(name,category,inventory_code,quantity_total,quantity_available,condition_status,location,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,1,?)',(request.form['name'],clean(request.form.get('category')) or None,code,qty,qty,request.form.get('condition_status') or 'Bon',clean(request.form.get('location')) or None,clean(request.form.get('notes')) or None,datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close(); flash('Matériel ajouté.'); return redirect('/equipment')
 return page('Ajouter du matériel',"""<div class='card'><form method='post' class='form'><label>Nom<input name='name' required></label><label>Catégorie<input name='category'></label><label>Code inventaire<input name='inventory_code'></label><label>Quantité<input type='number' min='0' name='quantity_total'></label><label>État<select name='condition_status'><option>Bon</option><option>Moyen</option><option>À réparer</option><option>Hors service</option></select></label><label>Emplacement<input name='location'></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full'><button class='btn' type='submit'>Enregistrer</button> <a class='btn alt' href='/equipment'>Annuler</a></div></form></div>""")

@app.route('/equipment/<int:eid>/loan',methods=['GET','POST'])
@login_required
@permission_required('equipment.manage')
def equipment_loan(eid):
 c=db(); e=c.execute('SELECT * FROM equipment WHERE id=?',(eid,)).fetchone()
 if request.method=='POST':
  qty=int(request.form.get('quantity') or 1)
  if qty>e['quantity_available']: flash('Quantité indisponible.')
  else:
   c.execute('INSERT INTO equipment_loans(equipment_id,user_id,quantity,loaned_at,due_at,status,notes,created_by_user_id) VALUES(?,?,?,?,?,?,?,?)',(eid,request.form['user_id'],qty,request.form.get('loaned_at') or date.today().isoformat(),request.form.get('due_at') or None,'En cours',clean(request.form.get('notes')) or None,session['uid'])); c.execute('UPDATE equipment SET quantity_available=quantity_available-? WHERE id=?',(qty,eid)); c.commit(); c.close(); flash('Prêt enregistré.'); return redirect('/equipment')
 users=c.execute("SELECT u.id,u.name FROM users u JOIN roles r ON r.id=u.role_id WHERE r.name='volunteer' AND u.active=1 ORDER BY u.name").fetchall(); c.close()
 body="""<div class='card'><h3>{{e.name}}</h3><p>Disponible : {{e.quantity_available}}</p><form method='post' class='form'><label>Bénévole<select name='user_id'>{% for u in users %}<option value='{{u.id}}'>{{u.name}}</option>{% endfor %}</select></label><label>Quantité<input type='number' min='1' max='{{e.quantity_available}}' name='quantity' value='1'></label><label>Date<input type='date' name='loaned_at' value='{{today}}'></label><label>Retour prévu<input type='date' name='due_at'></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full'><button class='btn'>Confirmer</button></div></form></div>"""
 return page('Prêt de matériel',body,e=e,users=users,today=date.today().isoformat())

@app.route('/equipment/loans/<int:lid>/return',methods=['POST'])
@login_required
@permission_required('equipment.manage')
def equipment_return(lid):
 c=db(); loan=c.execute("SELECT * FROM equipment_loans WHERE id=? AND status='En cours'",(lid,)).fetchone()
 if loan:
  c.execute("UPDATE equipment_loans SET status='Retourné',returned_at=? WHERE id=?",(date.today().isoformat(),lid)); c.execute('UPDATE equipment SET quantity_available=quantity_available+? WHERE id=?',(loan['quantity'],loan['equipment_id'])); c.commit(); flash('Retour enregistré.')
 c.close(); return redirect('/equipment')


# --- v1.8.0 Alpha 3 : Adhérents, caisse séparée et centre d'impression ---
def cash_balances(c):
 rows=c.execute("SELECT fund_type,COALESCE(SUM(CASE WHEN movement_type='Entrée' THEN amount ELSE -amount END),0) balance FROM cash_movements WHERE status='Validé' GROUP BY fund_type").fetchall()
 d={r['fund_type']:r['balance'] for r in rows}; return float(d.get('Cotisations',0)),float(d.get('Dons',0))

@app.route('/members')
@login_required
@permission_required('member.view')
def members_list():
 c=db(); rows=c.execute("SELECT m.*,COALESCE(MAX(ms.membership_year),0) last_year,COALESCE(SUM(CASE WHEN ms.status='Payée' THEN ms.amount ELSE 0 END),0) paid_total FROM members m LEFT JOIN memberships ms ON ms.member_id=m.id WHERE m.active=1 GROUP BY m.id ORDER BY m.last_name,m.first_name").fetchall(); c.close()
 body="""<div class='section-title'><h2>Adhérents</h2>{% if manage %}<a class='btn' href='/members/new'>＋ Nouvel adhérent</a>{% endif %}</div><div class='card'><table><tr><th>N°</th><th>Nom</th><th>Téléphone</th><th>Type</th><th>Dernière année</th><th>Cotisations</th><th></th></tr>{% for r in rows %}<tr><td>{{r.member_number}}</td><td>{{r.last_name}} {{r.first_name}}</td><td>{{r.phone or '—'}}</td><td>{{r.member_type}}</td><td>{{r.last_year or '—'}}</td><td>{{'%.2f'|format(r.paid_total)}} DA</td><td><a class='btn alt' href='/members/{{r.id}}'>Ouvrir</a>{% if manage %} <a class='btn' href='/members/{{r.id}}/edit'>Modifier</a> <form method='post' action='/members/{{r.id}}/delete' style='display:inline' onsubmit="return confirm('Supprimer ou désactiver cet adhérent ?');"><button class='btn red' type='submit'>Supprimer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan='7'>Aucun adhérent.</td></tr>{% endfor %}</table></div>"""
 return page('Adhérents',body,rows=rows,manage=has_permission('member.manage'))

@app.route('/members/new',methods=['GET','POST'])
@login_required
@permission_required('member.manage')
def member_new():
 c=db()
 if request.method=='POST':
  number='ADH-'+str(request.form.get('membership_year') or date.today().year)+'-'+datetime.now().strftime('%H%M%S')
  c.execute('INSERT INTO members(member_number,first_name,last_name,sex,birth_date,phone,email,address,profession,emergency_contact,member_type,membership_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(number,request.form['first_name'],request.form['last_name'],request.form.get('sex'),request.form.get('birth_date') or None,clean(request.form.get('phone')) or None,clean(request.form.get('email')) or None,clean(request.form.get('address')) or None,clean(request.form.get('profession')) or None,clean(request.form.get('emergency_contact')) or None,request.form.get('member_type') or 'Adhérent',request.form.get('membership_date') or date.today().isoformat(),datetime.now().isoformat(timespec='minutes')))
  mid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; year=int(request.form.get('membership_year') or date.today().year); amount=float(request.form.get('amount') or 0); receipt='COT-'+str(year)+'-'+datetime.now().strftime('%H%M%S')
  if amount>0:
   c.execute('INSERT INTO memberships(member_id,membership_year,amount,status,paid_at,payment_method,receipt_number,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(mid,year,amount,'Payée',request.form.get('paid_at') or date.today().isoformat(),request.form.get('payment_method') or 'Espèces',receipt,session['uid'],datetime.now().isoformat(timespec='minutes')))
   msid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',('Cotisations','Entrée',amount,'Cotisation annuelle','Cotisation '+str(year)+' - '+number,'membership',msid,'Validé',session['uid'],datetime.now().isoformat(timespec='minutes')))
  c.commit(); c.close(); flash('Adhérent créé.'); return redirect('/members/'+str(mid))
 c.close(); body="""<div class='card'><form method='post' class='form'><label>Prénom<input name='first_name' required></label><label>Nom<input name='last_name' required></label><label>Sexe<select name='sex'><option>Homme</option><option>Femme</option></select></label><label>Date de naissance<input type='date' name='birth_date'></label><label>Téléphone<input name='phone'></label><label>E-mail<input type='email' name='email'></label><label>Type<select name='member_type'><option>Adhérent</option><option>Bénévole actif</option><option>Membre du bureau</option><option>Membre bienfaiteur</option></select></label><label>Année de cotisation<input type='number' name='membership_year' value='{{year}}' required></label><label>Montant cotisation (DA)<input type='number' step='0.01' min='0' name='amount'></label><label>Date paiement<input type='date' name='paid_at' value='{{today}}'></label><label>Mode de paiement<select name='payment_method'><option>Espèces</option><option>Virement</option><option>Chèque</option><option>Autre</option></select></label><label>Date d’adhésion<input type='date' name='membership_date' value='{{today}}' required></label><label>Profession<input name='profession'></label><label class='full'>Adresse<textarea name='address'></textarea></label><label class='full'>Contact d'urgence<input name='emergency_contact'></label><div class='full'><button class='btn' type='submit'>Enregistrer</button> <a class='btn alt' href='/members'>Annuler</a></div></form></div>"""; return page('Nouvel adhérent',body,year=date.today().year,today=date.today().isoformat())

@app.route('/members/<int:mid>')
@login_required
@permission_required('member.view')
def member_detail(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone(); fees=c.execute('SELECT * FROM memberships WHERE member_id=? ORDER BY membership_year DESC',(mid,)).fetchall(); c.close()
 if not m: return 'Adhérent introuvable',404
 body="""<div class='section-title'><h2>{{m.last_name}} {{m.first_name}}</h2><div><a class='btn alt' href='/members/{{m.id}}/print-form' target='_blank'>Formulaire</a> <a class='btn alt' href='/members/{{m.id}}/card' target='_blank'>Carte PVC</a>{% if manage %} <a class='btn' href='/members/{{m.id}}/membership'>＋ Cotisation</a> <a class='btn alt' href='/members/{{m.id}}/edit'>Modifier</a> <form method='post' action='/members/{{m.id}}/delete' style='display:inline' onsubmit="return confirm('Supprimer ou désactiver cet adhérent ?');"><button class='btn red' type='submit'>Supprimer</button></form>{% endif %}</div></div><div class='grid'><div class='card'><p><b>N° :</b> {{m.member_number}}</p><p><b>Type :</b> {{m.member_type}}</p><p><b>Date d’adhésion :</b> {{m.membership_date or m.created_at[:10]}}</p><p><b>Téléphone :</b> {{m.phone or '—'}}</p><p><b>Adresse :</b> {{m.address or '—'}}</p></div><div class='card'><h3>Cotisations</h3><table><tr><th>Année</th><th>Montant</th><th>État</th><th></th></tr>{% for f in fees %}<tr><td>{{f.membership_year}}</td><td>{{'%.2f'|format(f.amount)}} DA</td><td>{{f.status}}</td><td><a href='/memberships/{{f.id}}/receipt' target='_blank'>Reçu</a></td></tr>{% else %}<tr><td colspan='4'>Aucune cotisation.</td></tr>{% endfor %}</table></div></div>"""; return page('Fiche adhérent',body,m=m,fees=fees,manage=has_permission('member.manage'))

@app.route('/members/<int:mid>/edit',methods=['GET','POST'])
@login_required
@permission_required('member.manage')
def member_edit(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone()
 if not m:
  c.close(); return 'Adhérent introuvable',404
 if request.method=='POST':
  c.execute('UPDATE members SET first_name=?,last_name=?,sex=?,birth_date=?,phone=?,email=?,address=?,profession=?,emergency_contact=?,member_type=?,membership_date=?,updated_at=? WHERE id=?',(request.form['first_name'],request.form['last_name'],request.form.get('sex'),request.form.get('birth_date') or None,clean(request.form.get('phone')) or None,clean(request.form.get('email')) or None,clean(request.form.get('address')) or None,clean(request.form.get('profession')) or None,clean(request.form.get('emergency_contact')) or None,request.form.get('member_type') or 'Adhérent',request.form.get('membership_date') or None,datetime.now().isoformat(timespec='minutes'),mid))
  c.commit(); c.close(); flash('Adhérent modifié.'); return redirect('/members/'+str(mid))
 c.close()
 body="""<div class='card'><form method='post' class='form'><label>Prénom<input name='first_name' value='{{m.first_name}}' required></label><label>Nom<input name='last_name' value='{{m.last_name}}' required></label><label>Sexe<select name='sex'><option {% if m.sex=='Homme' %}selected{% endif %}>Homme</option><option {% if m.sex=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Date de naissance<input type='date' name='birth_date' value='{{m.birth_date or ""}}'></label><label>Téléphone<input name='phone' value='{{m.phone or ""}}'></label><label>E-mail<input type='email' name='email' value='{{m.email or ""}}'></label><label>Type<select name='member_type'><option {% if m.member_type=='Adhérent' %}selected{% endif %}>Adhérent</option><option {% if m.member_type=='Bénévole actif' %}selected{% endif %}>Bénévole actif</option><option {% if m.member_type=='Membre du bureau' %}selected{% endif %}>Membre du bureau</option><option {% if m.member_type=='Membre bienfaiteur' %}selected{% endif %}>Membre bienfaiteur</option></select></label><label>Date d’adhésion<input type='date' name='membership_date' value='{{m.membership_date or m.created_at[:10]}}'></label><label>Profession<input name='profession' value='{{m.profession or ""}}'></label><label class='full'>Adresse<textarea name='address'>{{m.address or ''}}</textarea></label><label class='full'>Contact d'urgence<input name='emergency_contact' value='{{m.emergency_contact or ""}}'></label><div class='full'><button class='btn' type='submit'>Enregistrer</button> <a class='btn alt' href='/members/{{m.id}}'>Annuler</a></div></form></div>"""
 return page('Modifier un adhérent',body,m=m)

@app.post('/members/<int:mid>/delete')
@login_required
@permission_required('member.manage')
def member_delete(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone()
 if not m:
  c.close(); return 'Adhérent introuvable',404
 history_count=c.execute('SELECT COUNT(*) n FROM memberships WHERE member_id=?',(mid,)).fetchone()['n']
 if history_count:
  c.execute('UPDATE members SET active=0,updated_at=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),mid)); c.commit(); c.close(); flash("L’adhérent possède un historique : il a été désactivé, sans suppression de ses données."); return redirect('/members')
 c.execute('DELETE FROM members WHERE id=?',(mid,)); c.commit(); c.close(); flash('Adhérent supprimé définitivement.'); return redirect('/members')

@app.route('/members/<int:mid>/membership',methods=['GET','POST'])
@login_required
@permission_required('member.manage')
def member_membership(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone()
 if request.method=='POST':
  year=int(request.form['membership_year']); amount=float(request.form['amount']); receipt='COT-'+str(year)+'-'+datetime.now().strftime('%H%M%S')
  try:
   c.execute('INSERT INTO memberships(member_id,membership_year,amount,status,paid_at,payment_method,receipt_number,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(mid,year,amount,'Payée',request.form.get('paid_at') or date.today().isoformat(),request.form.get('payment_method') or 'Espèces',receipt,session['uid'],datetime.now().isoformat(timespec='minutes'))); msid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',('Cotisations','Entrée',amount,'Cotisation annuelle','Cotisation '+str(year)+' - '+m['member_number'],'membership',msid,'Validé',session['uid'],datetime.now().isoformat(timespec='minutes'))); c.commit(); flash('Cotisation enregistrée.')
  except sqlite3.IntegrityError: flash('Cette année est déjà enregistrée pour cet adhérent.')
  c.close(); return redirect('/members/'+str(mid))
 c.close(); return page('Nouvelle cotisation',"""<div class='card'><h3>{{m.last_name}} {{m.first_name}}</h3><form method='post' class='form'><label>Année<input type='number' name='membership_year' value='{{year}}' required></label><label>Montant (DA)<input type='number' step='0.01' min='0' name='amount' required></label><label>Date<input type='date' name='paid_at' value='{{today}}'></label><label>Mode<select name='payment_method'><option>Espèces</option><option>Virement</option><option>Chèque</option></select></label><div class='full'><button class='btn'>Encaisser</button></div></form></div>""",m=m,year=date.today().year,today=date.today().isoformat())

@app.route('/cash')
@login_required
@permission_required('cash.view')
def cash_dashboard():
 c=db(); cot,dons=cash_balances(c); scope,sp=context_condition('cm'); rows=c.execute('SELECT cm.*,p.name project_name,z.name zone_name FROM cash_movements cm LEFT JOIN projects p ON p.id=cm.project_id LEFT JOIN zones z ON z.id=cm.zone_id WHERE '+scope+' ORDER BY cm.id DESC LIMIT 100',sp).fetchall(); agents=c.execute('SELECT * FROM agents WHERE active=1 ORDER BY name').fetchall(); c.close()
 body="""<div class='section-title'><div><h2>💰 Caisse centrale</h2><p class='sub'>Une seule vue pour les dons, cotisations et toutes les dépenses.</p></div>{% if manage %}<div class='action-set'><a class='action-btn action-primary' href='/cash/purchase?type=Arbres'>🌳 Acheter des arbres</a><a class='action-btn action-primary' href='/cash/purchase?type=Matériel'>🧰 Acheter du matériel</a><a class='action-btn action-view' href='/agents/payment'>👷 Payer un agent</a><a class='action-btn action-view' href='/cash/expense'>🧾 Autre dépense</a></div>{% endif %}</div><div class='grid kpis'><div class='card kpi'><small>❤️ Dons disponibles</small><b>{{'%.2f'|format(dons)}} DA</b></div><div class='card kpi'><small>🤝 Cotisations disponibles</small><b>{{'%.2f'|format(cot)}} DA</b></div><div class='card kpi'><small>💰 Solde global</small><b>{{'%.2f'|format(cot+dons)}} DA</b></div></div><div class='card'><div class='section-title'><h3>Journal financier unique</h3><div><a class='action-btn action-view' href='/donations'>Dons</a><a class='action-btn action-view' href='/members'>Cotisations</a></div></div><table><tr><th>Date</th><th>Source</th><th>Mouvement</th><th>Catégorie</th><th>Montant</th><th>Utilisation / détail</th></tr>{% for r in rows %}<tr><td>{{r.created_at}}</td><td>{{r.fund_type}}</td><td>{{r.movement_type}}</td><td>{{r.category or '—'}}</td><td>{% if r.movement_type=='Entrée' %}+{% else %}-{% endif %}{{'%.2f'|format(r.amount)}} DA</td><td>{{r.description or '—'}}{% if r.justification %}<div class='sub'>{{r.justification}}</div>{% endif %}</td></tr>{% else %}<tr><td colspan='6'>Aucun mouvement.</td></tr>{% endfor %}</table></div>"""; return page('Caisse centrale',body,cot=cot,dons=dons,rows=rows,agents=agents,manage=has_permission('cash.manage'))

@app.route('/cash/expense',methods=['GET','POST'])
@login_required
@permission_required('cash.manage')
def cash_expense():
 c=db(); cot,dons=cash_balances(c)
 if request.method=='POST':
  fund=request.form['fund_type']; amount=float(request.form['amount']); justification=clean(request.form.get('justification'))
  available=cot if fund=='Cotisations' else dons
  if not justification: flash('Le justificatif est obligatoire.')
  elif amount>available: flash('Solde insuffisant dans ce fonds.')
  else:
   c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,project_id,zone_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(fund,'Sortie',amount,request.form.get('category'),clean(request.form.get('description')) or None,request.form.get('project_id') or None,request.form.get('zone_id') or None,justification,'Validé',session['uid'],datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close(); flash('Dépense enregistrée.'); return redirect('/cash')
 projects=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall(); zones=c.execute('SELECT id,name FROM zones WHERE active=1 ORDER BY name').fetchall(); c.close()
 body="""<div class='card'><p>Cotisations : <b>{{'%.2f'|format(cot)}} DA</b> — Dons : <b>{{'%.2f'|format(dons)}} DA</b></p><form method='post' class='form'><label>Fonds<select name='fund_type'><option>Cotisations</option><option>Dons</option></select></label><label>Montant (DA)<input type='number' step='0.01' min='0.01' name='amount' required></label><label>Catégorie<select name='category'><option>Achat d’arbres</option><option>Outillage</option><option>Arrosage</option><option>Transport</option><option>Entretien</option><option>Autre</option></select></label><label>Projet<select name='project_id'><option value=''>—</option>{% for p in projects %}<option value='{{p.id}}'>{{p.name}}</option>{% endfor %}</select></label><label>Zone<select name='zone_id'><option value=''>—</option>{% for z in zones %}<option value='{{z.id}}'>{{z.name}}</option>{% endfor %}</select></label><label class='full'>Description<textarea name='description'></textarea></label><label class='full'>Justificatif / référence obligatoire<input name='justification' required></label><div class='full'><button class='btn'>Valider la dépense</button></div></form></div>"""; return page('Nouvelle dépense',body,cot=cot,dons=dons,projects=projects,zones=zones)

@app.route('/cash/purchase',methods=['GET','POST'])
@login_required
@permission_required('cash.manage')
def cash_purchase():
 c=db(); cot,dons=cash_balances(c); species=c.execute('SELECT id,name_fr,name_ar,scientific_name FROM species WHERE active=1 ORDER BY name_fr').fetchall(); equipment=c.execute('SELECT id,name FROM equipment WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  tree_ids=request.form.getlist('tree_species_id[]'); tree_qty=request.form.getlist('tree_quantity[]'); tree_price=request.form.getlist('tree_price[]'); eq_ids=request.form.getlist('equipment_id[]'); eq_qty=request.form.getlist('equipment_quantity[]'); eq_price=request.form.getlist('equipment_price[]')
  items=[]
  for i,x in enumerate(tree_ids):
   if x and i<len(tree_qty) and float(tree_qty[i] or 0)>0: items.append(('Arbres',int(x),float(tree_qty[i]),float(tree_price[i] or 0)))
  for i,x in enumerate(eq_ids):
   if x and i<len(eq_qty) and float(eq_qty[i] or 0)>0: items.append(('Matériel',int(x),float(eq_qty[i]),float(eq_price[i] or 0)))
  total=sum(q*p for _,_,q,p in items); source=request.form.get('source') or 'Dons'; fm=total if source=='Cotisations' else 0; fd=total if source=='Dons' else 0
  if source=='Mixte': fm=float(request.form.get('from_memberships') or 0); fd=float(request.form.get('from_donations') or 0)
  justification=clean(request.form.get('justification'))
  if not items or total<=0: flash('Ajoutez au moins un arbre ou un matériel avec quantité et prix.')
  elif abs((fm+fd)-total)>0.01: flash('La répartition Dons + Cotisations doit correspondre au total de l’achat : %.2f DA.'%total)
  elif fm>cot or fd>dons: flash('Solde insuffisant dans le fonds choisi.')
  elif not justification: flash('Le justificatif est obligatoire.')
  else:
   now=datetime.now().isoformat(timespec='minutes'); ref=next_entity_code(c,'purchase_groups','reference','ACHAT'); cur=c.execute('INSERT INTO purchase_groups(reference,total_amount,from_memberships,from_donations,supplier,justification,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ref,total,fm,fd,clean(request.form.get('supplier')) or None,justification,clean(request.form.get('notes')) or None,session['uid'],now)); gid=cur.lastrowid
   for typ,item_id,qty,unit_price in items:
    c.execute('INSERT INTO purchase_items(group_id,item_type,item_id,quantity,line_amount) VALUES(?,?,?,?,?)',(gid,typ,item_id,qty,qty*unit_price))
    if typ=='Arbres':
     st=c.execute("SELECT * FROM nursery_stock WHERE species_id=? AND COALESCE(location,'')=''",(item_id,)).fetchone()
     if st: sid=st['id']; c.execute('UPDATE nursery_stock SET quantity_available=quantity_available+?,unit_value=?,updated_at=? WHERE id=?',(int(qty),unit_price,now,sid))
     else: cur2=c.execute('INSERT INTO nursery_stock(species_id,quantity_available,unit_value,location,updated_at) VALUES(?,?,?,?,?)',(item_id,int(qty),unit_price,'',now)); sid=cur2.lastrowid
     c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(sid,'Entrée achat',int(qty),ref,session['uid'],now))
    else:
     e=c.execute('SELECT id FROM equipment WHERE id=?',(item_id,)).fetchone()
     if e:c.execute('UPDATE equipment SET quantity_total=quantity_total+?,quantity_available=quantity_available+?,updated_at=? WHERE id=?',(int(qty),int(qty),now,item_id))
   if fm:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Cotisations','Sortie',fm,'Achat mixte','Achat '+ref,'purchase_group',gid,justification,'Validé',session['uid'],now))
   if fd:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Dons','Sortie',fd,'Achat mixte','Achat '+ref,'purchase_group',gid,justification,'Validé',session['uid'],now))
   c.commit();c.close();log_action('purchase','purchase_group',gid,ref);flash('Achat enregistré : caisse débitée et stock alimenté.');return redirect('/cash')
 c.close(); return page('Nouvel achat',"""<div class='card'><div class='grid kpis'><div class='card kpi'><small>Dons disponibles</small><b>{{'%.2f'|format(dons)}} DA</b></div><div class='card kpi'><small>Cotisations disponibles</small><b>{{'%.2f'|format(cot)}} DA</b></div></div><form method='post' id='purchaseForm'><div class='card'><div class='section-title'><h3>🌳 Arbres</h3><button type='button' class='btn' onclick='addTreePurchase()'>+ Espèce</button></div><div id='purchaseTrees'></div></div><div class='card'><div class='section-title'><h3>🧰 Matériel</h3><button type='button' class='btn' onclick='addEqPurchase()'>+ Matériel</button></div><div id='purchaseEq'></div></div><div class='form'><label>Fournisseur<input name='supplier'></label><label>Source de paiement<select name='source' id='paySource' onchange='mixBox.style.display=this.value=="Mixte"?"grid":"none"'><option>Dons</option><option>Cotisations</option><option>Mixte</option></select></label><div id='mixBox' class='full form' style='display:none'><label>Depuis cotisations<input type='number' min='0' step='0.01' name='from_memberships' value='0'></label><label>Depuis dons<input type='number' min='0' step='0.01' name='from_donations' value='0'></label></div><label class='full'>Justificatif / facture<input name='justification' required></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full action-set'><button class='btn'>✓ Enregistrer l’achat</button><a class='btn alt' href='/cash'>Annuler</a></div></div></form></div><template id='ptree'><div class='don-line'><select name='tree_species_id[]'><option value=''>Espèce</option>{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}{% if x.name_ar %} — {{x.name_ar}}{% endif %}{% if x.scientific_name %} — {{x.scientific_name}}{% endif %}</option>{% endfor %}</select><input type='number' name='tree_quantity[]' min='1' placeholder='Quantité'><input type='number' name='tree_price[]' min='0' step='0.01' placeholder='Prix unitaire DA'><button type='button' class='btn red' onclick='this.parentElement.remove()'>Retirer</button></div></template><template id='peq'><div class='don-line'><select name='equipment_id[]'><option value=''>Matériel</option>{% for x in equipment %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select><input type='number' name='equipment_quantity[]' min='1' placeholder='Quantité'><input type='number' name='equipment_price[]' min='0' step='0.01' placeholder='Prix unitaire DA'><button type='button' class='btn red' onclick='this.parentElement.remove()'>Retirer</button></div></template><script>function addTreePurchase(){purchaseTrees.append(ptree.content.cloneNode(true))}function addEqPurchase(){purchaseEq.append(peq.content.cloneNode(true))}addTreePurchase();addEqPurchase();</script>""",species=species,equipment=equipment,cot=cot,dons=dons)

@app.route('/agents/new' ,methods=['GET','POST'])
@login_required
@permission_required('cash.manage')
def agent_new():
 if request.method=='POST':
  c=db(); c.execute('INSERT INTO agents(name,phone,function_title,notes,created_at) VALUES(?,?,?,?,?)',(request.form['name'],clean(request.form.get('phone')) or None,clean(request.form.get('function_title')) or None,clean(request.form.get('notes')) or None,datetime.now().isoformat(timespec='minutes'))); c.commit(); c.close(); flash('Agent ajouté.'); return redirect('/cash')
 return page('Nouvel agent',"""<div class='card'><form method='post' class='form'><label>Nom complet<input name='name' required></label><label>Téléphone<input name='phone'></label><label>Fonction<input name='function_title' placeholder='Arrosage, plantation...'></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full'><button class='btn' type='submit'>Enregistrer</button> <a class='btn alt' href='/equipment'>Annuler</a></div></form></div>""")

@app.route('/agents/payment',methods=['GET','POST'])
@login_required
@permission_required('cash.manage')
def agent_payment():
 c=db(); cot,dons=cash_balances(c); agents=c.execute('SELECT * FROM agents WHERE active=1 ORDER BY name').fetchall(); projects=c.execute('SELECT id,name FROM projects WHERE active=1').fetchall(); zones=c.execute('SELECT id,name FROM zones WHERE active=1').fetchall()
 if request.method=='POST':
  total=float(request.form['total_amount']); source=request.form.get('source') or 'Automatique'; justification=clean(request.form.get('justification'))
  fm=fd=0
  if source=='Cotisations': fm=total
  elif source=='Dons': fd=total
  else: fm=min(cot,total); fd=total-fm
  if not justification: flash('Le justificatif est obligatoire.')
  elif fm>cot or fd>dons: flash('Solde insuffisant pour ce paiement.')
  else:
   now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO agent_payments(agent_id,work_type,period_label,project_id,zone_id,hours,days,total_amount,from_memberships,from_donations,payment_date,payment_method,justification,notes,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(request.form['agent_id'],request.form['work_type'],clean(request.form.get('period_label')) or None,request.form.get('project_id') or None,request.form.get('zone_id') or None,float(request.form.get('hours') or 0),float(request.form.get('days') or 0),total,fm,fd,request.form.get('payment_date') or date.today().isoformat(),request.form.get('payment_method') or 'Espèces',justification,clean(request.form.get('notes')) or None,'Validé',session['uid'],now)); pid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
   if fm: c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Cotisations','Sortie',fm,'Paiement agent','Paiement agent','agent_payment',pid,justification,'Validé',session['uid'],now))
   if fd: c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Dons','Sortie',fd,'Paiement agent','Complément paiement agent','agent_payment',pid,justification,'Validé',session['uid'],now))
   c.commit(); c.close(); return redirect('/agent-payments/'+str(pid)+'/print')
 c.close(); body="""<div class='card'><p>Cotisations : <b>{{'%.2f'|format(cot)}} DA</b> — Dons : <b>{{'%.2f'|format(dons)}} DA</b></p><form method='post' class='form'><label>Agent<select name='agent_id'>{% for a in agents %}<option value='{{a.id}}'>{{a.name}}</option>{% endfor %}</select></label><label>Travail<select name='work_type'><option>Plantation</option><option>Arrosage</option><option>Entretien</option><option>Nettoyage</option><option>Transport</option><option>Autre</option></select></label><label>Période<input name='period_label'></label><label>Jours<input type='number' step='0.5' name='days'></label><label>Heures<input type='number' step='0.5' name='hours'></label><label>Montant total (DA)<input type='number' step='0.01' min='0.01' name='total_amount' required></label><label>Source<select name='source'><option value='Automatique'>Mixte automatique (cotisations puis dons)</option><option>Cotisations</option><option>Dons</option></select></label><label>Date<input type='date' name='payment_date' value='{{today}}'></label><label>Mode<select name='payment_method'><option>Espèces</option><option>Virement</option><option>Chèque</option></select></label><label class='full'>Justificatif obligatoire<input name='justification' required></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full'><button class='btn'>Payer et imprimer</button></div></form></div>"""; return page('Paiement agent',body,cot=cot,dons=dons,agents=agents,projects=projects,zones=zones,today=date.today().isoformat())

PRINT_STYLE="""<style>@page{size:A4;margin:12mm}body{font-family:Arial,sans-serif;color:#111}h1,h2{text-align:center}.doc{border:1px solid #333;padding:18px}.row{display:flex;justify-content:space-between;margin:10px 0}.sign{display:flex;justify-content:space-between;margin-top:55px}.no-print{margin:12px}@media print{.no-print{display:none}}</style>"""
def print_doc(title,content): return '<!doctype html><html lang="'+current_lang()+'" dir="'+current_dir()+'"><head><meta charset="utf-8"><title>'+tr(title)+'</title>'+PRINT_STYLE+LOT11_STYLE+'</head><body><button class="no-print" onclick="window.print()">'+tr('Imprimer')+'</button>'+content+i18n_script()+'</body></html>'

@app.route('/members/<int:mid>/print-form')
@login_required
@permission_required('print.manage')
def member_print_form(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone(); f=c.execute('SELECT * FROM memberships WHERE member_id=? ORDER BY membership_year DESC LIMIT 1',(mid,)).fetchone(); c.close(); year=f['membership_year'] if f else '—'; amount=f['amount'] if f else 0
 return print_doc('Formulaire adhésion',f"<div class='doc'><h1>Formulaire d’adhésion</h1><div class='row'><b>N° adhérent</b><span>{m['member_number']}</span></div><div class='row'><b>Nom et prénom</b><span>{m['last_name']} {m['first_name']}</span></div><div class='row'><b>Année de cotisation</b><span>{year}</span></div><div class='row'><b>Montant</b><span>{amount:.2f} DA</span></div><div class='row'><b>Téléphone</b><span>{m['phone'] or '—'}</span></div><div class='row'><b>Adresse</b><span>{m['address'] or '—'}</span></div><div class='sign'><span>Signature de l’adhérent</span><span>Cachet et signature</span></div></div>")

@app.route('/members/<int:mid>/card')
@login_required
@permission_required('print.manage')
def member_card(mid):
 c=db(); m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone(); f=c.execute("SELECT * FROM memberships WHERE member_id=? AND status='Payée' ORDER BY membership_year DESC LIMIT 1",(mid,)).fetchone(); c.close(); year=f['membership_year'] if f else '—'
 return '<!doctype html><html><head><meta charset="utf-8"><style>@page{size:85.6mm 53.98mm;margin:0}body{margin:0;font-family:Arial}.card{box-sizing:border-box;width:85.6mm;height:53.98mm;padding:5mm;border:1px solid #222;background:#f5fff6}h2{margin:0 0 5mm;color:#266b3d}.year{font-size:22px;font-weight:bold}.no-print{position:fixed;top:60mm}@media print{.no-print{display:none}}</style></head><body><div class="card"><h2>Carte d’adhérent</h2><b>'+m['last_name']+' '+m['first_name']+'</b><p>N° '+m['member_number']+'</p><div class="year">Année '+str(year)+'</div><p>'+m['member_type']+'</p></div><button class="no-print" onclick="window.print()">Imprimer la carte PVC</button></body></html>'

@app.route('/memberships/<int:fid>/receipt')
@login_required
@permission_required('print.manage')
def membership_receipt(fid):
 c=db(); f=c.execute('SELECT ms.*,m.member_number,m.first_name,m.last_name FROM memberships ms JOIN members m ON m.id=ms.member_id WHERE ms.id=?',(fid,)).fetchone(); c.close()
 return print_doc('Reçu cotisation',f"<div class='doc'><h1>Reçu de cotisation</h1><div class='row'><b>Reçu</b><span>{f['receipt_number']}</span></div><div class='row'><b>Adhérent</b><span>{f['last_name']} {f['first_name']}</span></div><div class='row'><b>Année</b><span>{f['membership_year']}</span></div><div class='row'><b>Montant reçu</b><span>{f['amount']:.2f} DA</span></div><div class='row'><b>Date</b><span>{f['paid_at']}</span></div><div class='sign'><span>Adhérent</span><span>Trésorier / Cachet</span></div></div>")

@app.route('/agent-payments/<int:pid>/print')
@login_required
@permission_required('print.manage')
def agent_payment_print(pid):
 c=db(); p=c.execute('SELECT ap.*,a.name agent_name,a.function_title FROM agent_payments ap JOIN agents a ON a.id=ap.agent_id WHERE ap.id=?',(pid,)).fetchone(); c.close()
 return print_doc('Bon de paiement',f"<div class='doc'><h1>Bon de paiement</h1><div class='row'><b>Agent</b><span>{p['agent_name']}</span></div><div class='row'><b>Travail</b><span>{p['work_type']}</span></div><div class='row'><b>Période</b><span>{p['period_label'] or '—'}</span></div><div class='row'><b>Montant total</b><span>{p['total_amount']:.2f} DA</span></div><div class='row'><b>Depuis cotisations</b><span>{p['from_memberships']:.2f} DA</span></div><div class='row'><b>Depuis dons</b><span>{p['from_donations']:.2f} DA</span></div><div class='row'><b>Justificatif</b><span>{p['justification']}</span></div><div class='sign'><span>Signature agent</span><span>Signature association</span></div></div>")

@app.route('/donations/<int:did>/receipt')
@login_required
@permission_required('print.manage')
def donation_receipt(did):
 c=db(); d=c.execute('SELECT n.*,o.name donor_name FROM donations n LEFT JOIN donors o ON o.id=n.donor_id WHERE n.id=?',(did,)).fetchone(); c.close(); value=(str(round(d['amount'],2))+' '+d['currency']) if d['amount'] else (str(d['quantity'])+' '+(d['unit'] or ''))
 return print_doc('Reçu de don',f"<div class='doc'><h1>Reçu de don</h1><div class='row'><b>N° reçu</b><span>{d['receipt_number']}</span></div><div class='row'><b>Donateur</b><span>{d['donor_name'] or 'Anonyme'}</span></div><div class='row'><b>Nature</b><span>{d['donation_type']}</span></div><div class='row'><b>Montant / quantité</b><span>{value}</span></div><div class='row'><b>Date</b><span>{d['received_at']}</span></div><div class='sign'><span>Donateur</span><span>Association / Cachet</span></div></div>")

init_db()


@app.route('/tree-change-requests')
@login_required
def tree_change_requests():
 if not is_admin(): return redirect('/volunteer')
 c=db(); rows=c.execute("SELECT r.*,t.tree_code,u.name requester FROM tree_change_requests r JOIN trees t ON t.id=r.tree_id JOIN users u ON u.id=r.requested_by_user_id WHERE r.status='pending' ORDER BY r.id DESC").fetchall(); c.close()
 return page('Corrections d’arbres',"""<div class='card'><table><tr><th>Arbre</th><th>Bénévole</th><th>Motif</th><th>Date</th><th>Actions</th></tr>{% for r in rows %}<tr><td><a href='/tree/{{r.tree_id}}'>{{r.tree_code or r.tree_id}}</a></td><td>{{r.requester}}</td><td>{{r.reason}}</td><td>{{r.created_at}}</td><td><form method='post' action='/tree-change-requests/{{r.id}}/approve' style='display:inline'><button class='btn'>Accepter</button></form> <form method='post' action='/tree-change-requests/{{r.id}}/reject' style='display:inline'><button class='btn red'>Refuser</button></form></td></tr>{% else %}<tr><td colspan='6'>Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.post('/tree-change-requests/<int:rid>/approve')
@login_required
def approve_tree_change(rid):
 if not is_admin(): return redirect('/')
 c=db(); r=c.execute("SELECT * FROM tree_change_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if r:
  x=json.loads(r['changes_json']); allowed=['species_id','project_id','zone_id','health_status','watering_status','latitude','longitude','gps_accuracy','notes']; fields=[k for k in allowed if k in x];
  if fields: c.execute('UPDATE trees SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',[x[k] for k in fields]+[r['tree_id']]);
  now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE tree_change_requests SET status='approved',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid)); c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(r['requested_by_user_id'],'Correction acceptée','La correction demandée a été appliquée.','/tree/'+str(r['tree_id']),'Plantation',now)); c.commit(); flash('Correction appliquée.')
 c.close(); return redirect('/tree-change-requests')

@app.post('/tree-change-requests/<int:rid>/reject')
@login_required
def reject_tree_change(rid):
 if not is_admin(): return redirect('/')
 c=db(); r=c.execute("SELECT * FROM tree_change_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if r:
  now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE tree_change_requests SET status='rejected',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid)); c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(r['requested_by_user_id'],'Correction refusée','La correction demandée n’a pas été appliquée.','/tree/'+str(r['tree_id']),'Plantation',now)); c.commit(); flash('Correction refusée.')
 c.close(); return redirect('/tree-change-requests')

# --- v1.8.0 Alpha 4 : interface publique et encyclopédie ---
def public_page(title, body, allow_authenticated=False, **ctx):
 # Les pages publiques normales disparaissent après authentification, mais une fiche arbre
 # ouverte par QR doit rester consultable même si le navigateur possède déjà une session.
 if session.get('uid') and not allow_authenticated:
  return redirect('/' if is_admin() else '/volunteer')
 if session.get('uid'):
  account_link='/'+('' if is_admin() else 'volunteer')
  auth_desktop=f"<a class='btn alt' href='{account_link}'>🏠 Mon accueil</a><a class='btn red' href='/logout?next=/public'>Déconnexion</a>"
  auth_mobile=f"<a href='/logout?next=/public'><span>🚪</span>Déconnexion</a>"
 else:
  auth_desktop="<a class='btn alt' href='/login?next=/public'>🔐 Connexion</a>"
  auth_mobile="<a href='/login?next=/public'><span>🔐</span>Connexion</a>"
 nav="""<header class='public-header'><div class='public-shell' style='width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px'><a class='public-brand' href='/public'>🌳 <span>MyTree</span> 🇩🇿</a><nav class='public-nav'><a class='btn alt' href='/public'>Accueil</a><a class='btn alt' href='/public/associations'>Associations</a><a class='btn alt' href='/public/projects'>Projets</a><a class='btn alt' href='/public/events'>Événements</a><a class='btn alt' href='/public/map'>Carte</a><a class='btn alt' href='/public/species'>Encyclopédie</a><a class='btn' href='/public/help'>Je veux aider</a>"""+language_switcher()+auth_desktop+"""</nav></div></header>"""
 mobile="""<nav class='mobile-public-nav'><a href='/public'><span>🏠</span>Accueil</a><a href='/public/map'><span>🗺</span>Carte</a><a href='/public/species'><span>📚</span>Espèces</a><a href='/public/help'><span>🤝</span>Aider</a>"""+auth_mobile+"""</nav>"""
 footer="""<footer class='public-footer'><div class='public-shell'><b>MyTree Professional</b><p>Plateforme de suivi des plantations, des bénévoles et des actions de terrain.</p><a href='/login'>Espace sécurisé</a></div></footer>"""
 tpl="<!doctype html><html lang='"+current_lang()+"' dir='"+current_dir()+"'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='theme-color' content='#102b1c'><title>"+tr(title)+" — MyTree</title>"+STYLE+LOT11_STYLE+LOT12_MAPFIX_STYLE+LOT12_UNIFIED_FILTER_STYLE+SMART_NAV_SCRIPT+UNIVERSAL_SEARCH_SCRIPT+DEPENDENT_SELECTS_SCRIPT+i18n_script()+"<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'><script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script></head><body class='public-page-body'>"+nav+"<main class='public-shell'><div class='public-auth-banner'>"+auth_desktop+"</div>"+body+"</main>"+footer+mobile+"</body></html>"
 return render_template_string(tpl,**ctx)

@app.route('/public')
def public_home():
 if session.get('uid'): return redirect('/' if is_admin() else '/volunteer')
 c=db(); trees=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='approved'").fetchone()['n']; projects=c.execute("SELECT COUNT(*) n FROM projects WHERE active=1").fetchone()['n']; species=c.execute("SELECT COUNT(*) n FROM species WHERE active=1").fetchone()['n']; recent=c.execute("SELECT t.id,t.tree_code,t.planted_at,s.name_fr,s.name_ar,p.name project_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.active=1 AND t.approval_status='approved' ORDER BY t.id DESC LIMIT 6").fetchall(); next_events=c.execute("SELECT id,title,start_at,location,status FROM events WHERE active=1 AND status!='Annulé' ORDER BY start_at LIMIT 3").fetchall(); c.close()
 return public_page('Accueil',"""<section class='public-section hero-grid'><div class='public-hero'><div class='sub' style='color:#d9eddf'>Association • Plantation • Biodiversité</div><h1>Ensemble, faisons grandir les arbres d’Algérie</h1><p>Suivez les projets, découvrez les espèces et participez aux actions de plantation et d’arrosage.</p><a class='btn' href='/public/help'>🤝 Je veux aider</a> <a class='btn alt' href='/public/projects'>🌳 Voir les projets</a></div><div class='hero-side'><span class='sub'>Arbres suivis</span><b>{{trees}}</b><p>Chaque arbre possède un historique, un emplacement et un suivi terrain.</p><a class='btn alt' href='/public/map'>Ouvrir la carte publique</a></div></section><div class='grid public-kpis'><div class='card kpi'><small>Arbres suivis</small><b>{{trees}}</b></div><div class='card kpi'><small>Projets actifs</small><b>{{projects}}</b></div><div class='card kpi'><small>Espèces référencées</small><b>{{species}}</b></div></div><section class='public-section'><h2>Je veux aider</h2><p class='sub'>Choisissez une action concrète.</p><div class='public-actions'><a class='public-action' href='/public/action/plant'><span class='icon'>🌱</span><span>Planter un arbre</span></a><a class='public-action' href='/public/action/water'><span class='icon'>💧</span><span>Participer à l’arrosage</span></a><a class='public-action' href='/public/action/donate'><span class='icon'>🎁</span><span>Faire un don</span></a><a class='public-action' href='/public/action/member'><span class='icon'>❤️</span><span>Devenir adhérent</span></a></div></section><section class='public-section'><div class='section-title'><div><h2>Prochains événements</h2><p class='sub'>Rejoignez les activités organisées sur le terrain.</p></div><a href='/public/events'>Voir tout</a></div><div class='species-grid'>{% for e in next_events %}<a class='species-card' href='/public/events'><b>📆 {{e.title}}</b><p>{{e.start_at or 'Date à confirmer'}}</p><span class='sub'>{{e.location or 'Lieu à confirmer'}} • {{e.status}}</span></a>{% else %}<div class='card'>Aucun événement public programmé.</div>{% endfor %}</div></section><section class='public-section'><div class='section-title'><div><h2>Dernières plantations</h2><p class='sub'>Les derniers arbres validés dans la plateforme.</p></div></div><div class='species-grid'>{% for t in recent %}<a class='species-card' href='/public/tree/{{t.id}}'><b>{{t.name_fr or 'Espèce à identifier'}}</b><div class='sub'>{{t.name_ar or ''}} • {{t.project_name or 'Hors projet'}}</div><p>{{t.planted_at or 'Date non renseignée'}}</p></a>{% else %}<div class='card'>Aucune plantation publique pour le moment.</div>{% endfor %}</div></section>""",trees=trees,projects=projects,species=species,recent=recent,next_events=next_events)

@app.route('/public/species')
def public_species():
 q=clean(request.args.get('q')); c=db(); params=[]; where='active=1';
 if q: where+=" AND (name_fr LIKE ? OR name_ar LIKE ? OR name_en LIKE ? OR scientific_name LIKE ? OR family LIKE ? OR uses LIKE ?)"; params=['%'+q+'%']*6
 rows=c.execute('SELECT * FROM species WHERE '+where+' ORDER BY name_fr',params).fetchall(); c.close()
 return public_page('Encyclopédie des arbres',"""<div class='section-title'><div><h1>Encyclopédie des arbres</h1><p class='sub'>Espèces présentes ou cultivées en Algérie. Les fiches sont éducatives et peuvent être enrichies par l’administrateur.</p></div></div><div class='card'><label>Recherche intelligente<input id='publicSpeciesSearch' value='{{q}}' placeholder='Tapez en français, arabe ou nom scientifique…' oninput='filterPublicSpecies(this.value)'></label></div><div class='species-grid'>{% for s in rows %}<a class='species-card public-species-item' data-search="{{(s.name_fr~' '~(s.name_ar or '')~' '~(s.name_en or '')~' '~(s.scientific_name or '')~' '~(s.family or '')~' '~(s.uses or ''))|lower}}" href='/public/species/{{s.id}}'><b>{{s.name_fr}}</b><div dir='rtl'>{{s.name_ar or ''}}</div><div>{{s.name_en or ''}}</div><i>{{s.scientific_name or ''}}</i><p class='sub'>{{s.category or ''}} • Eau : {{s.water_need or '—'}}</p></a>{% endfor %}</div><script>function filterPublicSpecies(q){q=(q||'').toLowerCase().trim();document.querySelectorAll('.public-species-item').forEach(x=>x.style.display=!q||x.dataset.search.includes(q)?'':'none')}</script>""",rows=rows,q=q)

@app.route('/public/species/<int:sid>')
def public_species_detail(sid):
 c=db(); s=c.execute('SELECT * FROM species WHERE id=? AND active=1',(sid,)).fetchone(); c.close()
 if not s:return ('Espèce introuvable',404)
 return public_page(s['name_fr'],"""<div class='card'><h1>{{s.name_fr}}</h1><h2 dir='rtl'>{{s.name_ar or ''}}</h2><h3>{{s.name_en or ''}}</h3><p><i>{{s.scientific_name}}</i> — {{s.family or 'Famille non renseignée'}}</p><div class='grid two'><div><p><b>Présence en Algérie :</b> {{s.algeria_presence or 'Présente ou cultivée'}}</p><p><b>Régions :</b> {{s.regions or 'Selon le climat et les pratiques locales'}}</p><p><b>Sol :</b> {{s.soil_type or 'Variable'}}</p><p><b>Exposition :</b> {{s.sun_exposure or 'Soleil'}}</p><p><b>Besoins en eau :</b> {{s.water_need or '—'}}</p></div><div><p><b>Résistance à la sécheresse :</b> {{s.drought_tolerance or '—'}}</p><p><b>Distance de plantation :</b> {{s.planting_distance or 'À adapter'}}</p><p><b>Hauteur adulte :</b> {{s.adult_height or 'Variable'}}</p><p><b>Croissance :</b> {{s.growth_rate or 'Variable'}}</p><p><b>Usages :</b> {{s.uses or 'Biodiversité et paysage'}}</p></div></div><h3>Entretien</h3><p>{{s.maintenance or '—'}}</p><h3>Maladies et parasites</h3><p>{{s.diseases or '—'}}</p><h3>Compatibilité et précautions</h3><p>{{s.compatibility_note or '—'}}</p><p>{{s.description or 'Fiche de culture générale à compléter avec des observations locales.'}}</p><a class='btn alt' href='/public/species/{{s.id}}/print'>Imprimer la fiche</a> <a class='btn' href='/public/recommendations'>Recommandations</a></div>""",s=s)

@app.route('/public/recommendations')
def public_recommendations():
 region=clean(request.args.get('region')); water=clean(request.args.get('water')); usage=clean(request.args.get('usage')); soil=clean(request.args.get('soil')); c=db(); clauses=['active=1']; params=[]
 if region: clauses.append('(regions LIKE ? OR algeria_presence LIKE ?)'); params += ['%'+region+'%','%'+region+'%']
 if water: clauses.append('water_need=?'); params.append(water)
 if usage: clauses.append('(uses LIKE ? OR category LIKE ?)'); params += ['%'+usage+'%','%'+usage+'%']
 if soil: clauses.append('soil_type LIKE ?'); params.append('%'+soil+'%')
 rows=c.execute("SELECT *,CASE water_need WHEN 'Très faible' THEN 4 WHEN 'Faible' THEN 3 WHEN 'Moyen' THEN 2 ELSE 1 END score FROM species WHERE "+' AND '.join(clauses)+' ORDER BY score DESC,name_fr LIMIT 40',params).fetchall(); c.close()
 return public_page('Recommandation d’espèces',"""<h1>Recommandation d’espèces</h1><p class='sub'>Outil d’aide à la présélection. Vérifiez toujours les conditions réelles du terrain.</p><form class='card form' method='get'><label>Région / wilaya<input name='region' value='{{region}}' placeholder='Oran, littoral, Hauts Plateaux…'></label><label>Besoin en eau<select name='water'><option value=''>Tous</option>{% for x in ['Très faible','Faible','Moyen','Élevé'] %}<option {% if water==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Usage<input name='usage' value='{{usage}}' placeholder='Ombrage, fruitier, brise-vent…'></label><label>Sol<input name='soil' value='{{soil}}' placeholder='Calcaire, sableux, drainé…'></label><div class='full'><button class='btn'>Rechercher</button></div></form><div class='species-grid'>{% for s in rows %}<a class='species-card' href='/public/species/{{s.id}}'><b>{{s.name_fr}}</b><div dir='rtl'>{{s.name_ar or ''}}</div><div>{{s.name_en or ''}}</div><i>{{s.scientific_name or ''}}</i><p>{{s.category or ''}}</p><span class='sub'>Eau : {{s.water_need or '—'}} • Sol : {{s.soil_type or '—'}}</span></a>{% else %}<div class='card'>Aucune recommandation avec ces critères.</div>{% endfor %}</div>""",rows=rows,region=region,water=water,usage=usage,soil=soil)

@app.route('/public/species/<int:sid>/print')
def public_species_print(sid):
 c=db(); sp=c.execute('SELECT * FROM species WHERE id=? AND active=1',(sid,)).fetchone(); c.close()
 if not sp:return ('Espèce introuvable',404)
 return render_template_string("""<!doctype html><html lang='{{lang}}' dir='{{direction}}'><head><meta charset='utf-8'><title>{{s.name_fr}}</title><style>body{font-family:Arial;max-width:850px;margin:30px auto;line-height:1.5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.box{border:1px solid #ccc;padding:12px;border-radius:8px}@media print{button{display:none}}</style></head><body><button onclick='print()'>Imprimer</button><h1>{{s.name_fr}}</h1><h2 dir='rtl'>{{s.name_ar or ''}}</h2><p><i>{{s.scientific_name or ''}}</i> — {{s.family or ''}}</p><div class='grid'><div class='box'><b>Origine</b><br>{{s.origin or '—'}}</div><div class='box'><b>Régions</b><br>{{s.regions or '—'}}</div><div class='box'><b>Sol</b><br>{{s.soil_type or '—'}}</div><div class='box'><b>Eau</b><br>{{s.water_need or '—'}}</div><div class='box'><b>Distance</b><br>{{s.planting_distance or '—'}}</div><div class='box'><b>Hauteur adulte</b><br>{{s.adult_height or '—'}}</div></div><h3>Usages</h3><p>{{s.uses or '—'}}</p><h3>Entretien</h3><p>{{s.maintenance or '—'}}</p><h3>Maladies et précautions</h3><p>{{s.diseases or '—'}}</p><p>{{s.compatibility_note or ''}}</p><h3>Description</h3><p>{{s.description or '—'}}</p></body></html>""",s=sp,lang=current_lang(),direction=current_dir())

@app.route('/public/projects')
def public_projects():
 c=db(); rows=c.execute("SELECT p.*,(SELECT COUNT(*) FROM trees t WHERE t.project_id=p.id AND t.active=1 AND t.approval_status='approved') tree_count FROM projects p WHERE p.active=1 ORDER BY p.id DESC").fetchall(); c.close()
 return public_page('Nos projets',"""<h1>Nos projets</h1><div class='species-grid'>{% for p in rows %}<div class='species-card'><h3>{{p.name}}</h3><p>{{p.location or ''}}</p><b>{{p.tree_count}} arbres suivis</b></div>{% endfor %}</div>""",rows=rows)

@app.route('/public/tree/<int:tid>')
def public_tree(tid):
 c=db(); t=c.execute("SELECT t.*,s.name_fr,s.name_ar,s.scientific_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.id=? AND t.active=1 AND t.approval_status='approved'",(tid,)).fetchone(); c.close()
 if not t:return ('Arbre introuvable',404)
 return public_page('Fiche arbre',"""<div class='card'><h1>🌳 {{t.name_fr}} — {{t.tree_code}}</h1><p dir='rtl'>{{t.name_ar or ''}}</p><p><i>{{t.scientific_name or ''}}</i></p><div class='grid two'><div><p><b>Date de plantation :</b> {{t.planted_at or '—'}}</p><p><b>Projet :</b> {{t.project_name or 'Hors projet'}}</p><p><b>Zone :</b> {{t.zone_name or 'Hors zone'}}</p></div><div><p><b>État :</b> {{t.health_status}}</p><p><b>Dernier arrosage :</b> {{t.last_watered_at or 'Non renseigné'}}</p></div></div><a class='btn' href='/public/action/water'>💧 Arroser ou planter</a> <a class='btn alt' href='/public/species/{{t.species_id}}'>Voir la fiche de l’espèce</a></div>""",t=t,allow_authenticated=True)

@app.route('/public/register',methods=['GET','POST'])
def public_register():
 if request.method=='POST':
  c=db(); v=user_form_values(request.form); password=request.form.get('password') or ''; errors=validate_user_form(c,v,password_required=True,password=password);
  if password!=request.form.get('password_confirm',''): errors.append('Les mots de passe ne correspondent pas.')
  if not errors:
   role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']; name=user_display_name(v['first_name'],v['last_name']); now=datetime.now().isoformat(timespec='minutes'); mode_row=c.execute("SELECT value FROM settings WHERE key='volunteer_registration_mode'").fetchone(); registration_mode=(mode_row['value'] if mode_row else 'auto'); reg_active=1 if registration_mode=='auto' else 0; c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at,birth_date,address,skills,availability,photo_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(v['first_name'],v['last_name'],name,v['sex'],v['phone'],v['email'],v['phone'],generate_password_hash(password),role,'volunteer',reg_active,v['wilaya_id'],v['commune_id'],now,v['birth_date'],v['address'],v['skills'],v['availability'],v['photo_url'])); uid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; reg_lang=current_lang(); c.execute('UPDATE users SET preferred_language=? WHERE id=?',(reg_lang,uid));
   # v2.0: inscription bénévole active immédiatement mais notification informative au Super Admin.
   for a in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall():
    c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(a['id'],'Nouveau bénévole inscrit',name+' vient de créer un compte MyTree.','/volunteers','Information',now))
   c.commit(); c.close(); log_action('self_register','user',uid,'Inscription publique - '+registration_mode);
   if reg_active:
    session.clear(); session.permanent=True; session.update(uid=uid,name=name,role='volunteer',lang=reg_lang); flash('Compte créé et activé automatiquement.'); target=request.form.get('next') or request.args.get('next'); return redirect(target if target and target.startswith('/') else '/volunteer')
   flash('Compte créé. Il attend la validation administrative car le mode manuel est actif.'); return redirect('/login')
  c.close()
  for e in errors: flash(e)
 c=db(); wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); c.close()
 return public_page('Devenir bénévole',"""{% for m in get_flashed_messages() %}<div class='flash'>{{m}}</div>{% endfor %}<div class='card'><h1>Créer un compte bénévole</h1><form method='post' class='form'><input type='hidden' name='next' value='{{request.args.get("next","")}}'><label>Prénom<input name='first_name' required></label><label>Nom<input name='last_name' required></label><label>Téléphone<input name='phone' required></label><label>E-mail<input type='email' name='email'></label><label>Sexe<select name='sex'><option>Homme</option><option>Femme</option></select></label><label>Mot de passe<input type='password' name='password' minlength='6' autocomplete='new-password' required></label><label>Confirmer le mot de passe<input type='password' name='password_confirm' minlength='6' autocomplete='new-password' required></label><label>Wilaya<select name='wilaya_id'><option value=''>Choisir</option>{% for w in wilayas %}<option value='{{w.id}}'>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Choisir</option>{% for x in communes %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label class='full'>Adresse<textarea name='address'></textarea></label><div class='full'><button class='btn'>Créer mon compte</button> <a class='btn alt' href='{{request.args.get("cancel") or "/public"}}'>Annuler</a></div></form></div>""",wilayas=wilayas,communes=communes)



def decide_notification(nid, decision):
 c=db(); n=c.execute('SELECT * FROM notifications WHERE id=? AND (user_id=? OR user_id IS NULL)',(nid,session['uid'])).fetchone()
 if not n or n['decision']:
  c.close(); return False
 ok=False; label='Acceptée' if decision=='accept' else 'Refusée'
 if n['action_type']=='tree' and n['action_id']:
  t=c.execute('SELECT * FROM trees WHERE id=?',(n['action_id'],)).fetchone()
  if t and t['approval_status']=='pending':
   now=datetime.now().isoformat(timespec='minutes')
   if decision=='accept':
    stock_ok,stock_msg=deduct_tree_from_nursery(c,t['id'])
    if not stock_ok: c.close(); return False
    code=t['tree_code'] or f"TREE-{t['id']:06d}"; c.execute("UPDATE trees SET approval_status='approved',tree_code=?,qr_code=?,approved_by_user_id=?,approved_at=?,rejection_reason=NULL WHERE id=?",(code,'MYTREE:'+code,session['uid'],now,t['id']))
   else:
    c.execute("UPDATE trees SET approval_status='rejected',approved_by_user_id=?,approved_at=?,rejection_reason=? WHERE id=?",(session['uid'],now,'Refusée depuis le centre de notifications',t['id']))
   c.execute('INSERT INTO planting_reviews(tree_id,decision,reason,reviewer_user_id,created_at) VALUES(?,?,?,?,?)',(t['id'],label,'Traitement rapide depuis les notifications',session['uid'],now)); ok=True
 elif n['action_type']=='donation_group' and n['action_id']:
  g=c.execute('SELECT * FROM donation_groups WHERE id=?',(n['action_id'],)).fetchone()
  if g and g['status']=='En attente':
   new_status='Confirmé' if decision=='accept' else 'Refusé'; c.execute('UPDATE donation_groups SET status=? WHERE id=?',(new_status,g['id'])); c.execute('UPDATE donations SET status=? WHERE group_id=?',(new_status,g['id']))
   if decision=='accept':
    for d in c.execute('SELECT id FROM donations WHERE group_id=?',(g['id'],)).fetchall(): sync_donation_cash(c,d['id']); sync_nature_donation_stock(c,d['id'])
   if g['created_by_user_id']:
    c.execute('INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)',(g['created_by_user_id'],'Don '+('accepté' if decision=='accept' else 'refusé'),'Votre don '+(g['receipt_number'] or '')+' a été '+('accepté.' if decision=='accept' else 'refusé.'),'/volunteer/donate','Don',datetime.now().isoformat(timespec='minutes')))
   ok=True
 processed=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE notifications SET decision=?,is_read=1,read_at=COALESCE(read_at,?),processed_at=? WHERE id=?',(label,processed,processed,nid)); c.commit(); c.close(); return ok

@app.post('/notifications/<int:nid>/decide/<decision>')
@login_required
def notification_decide(nid,decision):
 if not is_admin() or decision not in ('accept','reject'): return redirect('/notifications')
 ok=decide_notification(nid,decision); flash('Demande traitée.' if ok else 'Cette demande ne peut plus être traitée.','success' if ok else 'warning')
 return redirect(request.referrer or '/notifications')

@app.post('/notifications/bulk')
@login_required
def notifications_bulk():
 if not is_admin(): return redirect('/notifications')
 decision=request.form.get('decision'); ids=request.form.getlist('notification_ids'); done=0
 if decision in ('accept','reject'):
  for raw in ids:
   try: done += 1 if decide_notification(int(raw),decision) else 0
   except ValueError: pass
 flash(f'{done} demande(s) traitée(s).','success' if done else 'warning')
 return redirect('/notifications')

@app.route('/action-center')
@login_required
def action_center():
 if not is_admin(): return redirect('/volunteer')
 c=db(); counts={
  'plantations':c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='pending'").fetchone()['n'],
  'dons':c.execute("SELECT COUNT(*) n FROM donations WHERE status='En attente'").fetchone()['n'],
  'modifications':c.execute("SELECT COUNT(*) n FROM tree_change_requests WHERE status='pending'").fetchone()['n'],
  'notifications':c.execute("SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0",(session['uid'],)).fetchone()['n']}
 c.close()
 return page('Centre d’actions',"""<h2>Centre d’actions</h2><p class='sub'>Toutes les demandes qui nécessitent une décision administrative.</p><div class='grid kpis' style='grid-template-columns:repeat(4,1fr)'><a class='card kpi action-card' href='/notifications?category=Plantation&unread=1'><small>Plantations à valider</small><b>{{counts.plantations}}</b></a><a class='card kpi action-card' href='/notifications?category=Don&unread=1'><small>Dons à valider</small><b>{{counts.dons}}</b></a><a class='card kpi action-card' href='/tree-change-requests'><small>Modifications d’arbres</small><b>{{counts.modifications}}</b></a><a class='card kpi' href='/notifications?unread=1'><small>Notifications non lues</small><b>{{counts.notifications}}</b></a></div><div class='card'><h3>Traitement rapide</h3><p>Utilisez les cases à cocher dans la liste des notifications pour accepter ou refuser plusieurs demandes en une seule opération.</p><a class='btn' href='/notifications'>Ouvrir les notifications</a></div>""",counts=counts)

@app.route('/volunteer/donate',methods=['GET','POST'])
@login_required
def volunteer_donate():
 if is_admin(): return redirect('/donations/new')
 c=db(); species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall(); equipment=c.execute('SELECT id,name FROM equipment WHERE active=1 ORDER BY name').fetchall(); assocs=c.execute("SELECT id,name,code,map_symbol FROM associations WHERE status='active' ORDER BY name").fetchall()
 selected=clean(request.values.get('association_id')); values={'association_id':selected,'amount':clean(request.form.get('amount'))}; error=''
 if request.method=='POST':
  try: aid=int(selected or 0)
  except: aid=0
  if not aid or not c.execute("SELECT 1 FROM associations WHERE id=? AND status='active'",(aid,)).fetchone(): error='Choisissez l’association bénéficiaire.'
  if not error:
   if 'association_id' not in columns(c,'donation_groups'):
    c.execute('ALTER TABLE donation_groups ADD COLUMN association_id INTEGER')
   receipt='PENDING-'+datetime.now().strftime('%Y%m%d-%H%M%S'); now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO donation_groups(status,receipt_number,received_at,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?)',('En attente',receipt,date.today().isoformat(),session['uid'],now,aid)); gid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; count=0
   try: amount=max(0,float(request.form.get('amount') or 0))
   except: amount=0
   if amount>0:_add_donation_line(c,gid,None,'En attente',receipt,'Argent',amount=amount); count+=1
   for sid,q in zip(request.form.getlist('species_id[]'),request.form.getlist('tree_quantity[]')):
    try:qv=max(0,int(q or 0))
    except:qv=0
    if sid and qv:_add_donation_line(c,gid,None,'En attente',receipt,'Arbres',qty=qv,species_id=sid); count+=1
   for eid,q in zip(request.form.getlist('equipment_id[]'),request.form.getlist('equipment_quantity[]')):
    try:qv=max(0,int(q or 0))
    except:qv=0
    if eid and qv:_add_donation_line(c,gid,None,'En attente',receipt,'Matériel',qty=qv,equipment_id=eid); count+=1
   if not count: c.rollback(); error='Ajoutez au moins un montant, un arbre ou un matériel.'
   else:
    # Rattache toutes les lignes du groupe à l'association choisie.
    if 'association_id' in columns(c,'donations'): c.execute('UPDATE donations SET association_id=? WHERE group_id=?',(aid,gid))
    donor=c.execute('SELECT name FROM users WHERE id=?',(session['uid'],)).fetchone(); donor_name=(donor['name'] if donor else 'Un bénévole'); an=c.execute('SELECT name FROM associations WHERE id=?',(aid,)).fetchone()['name']
    notify_admins_in_tx(c,'Nouveau don à valider',donor_name+' a envoyé un don à '+an+' ('+receipt+').','/donations?status=pending','Don','donation_group',gid)
    c.commit();c.close();flash('Don envoyé.');return redirect('/public/associations/'+str(aid))
 c.close(); return page('Faire un don',"""<div class='card'><div class='section-title'><div><h2>🎁 Faire un don</h2><p class='sub'>Choisissez d’abord l’association bénéficiaire puis indiquez votre don.</p></div></div>{% if error %}<div class='flash flash-error'>{{error}}</div>{% endif %}<form method='post' class='form'><label class='full'>Association bénéficiaire<select name='association_id' required><option value=''>Choisir une association</option>{% for a in assocs %}<option value='{{a.id}}' {% if values.association_id|string==a.id|string %}selected{% endif %}>{{a.map_symbol or '🌳'}} {{a.name}} — {{a.code}}</option>{% endfor %}</select></label><div class='full card'><h3>💶 Argent</h3><label>Montant en DA<input type='number' min='0' step='0.01' name='amount' value='{{values.amount}}' placeholder='0'></label></div><div class='full card'><div class='section-title'><h3>🌳 Arbres</h3><button type='button' class='action-btn action-primary' onclick='addTree()'>＋ Espèce</button></div><div id='treeRows'></div></div><div class='full card'><div class='section-title'><h3>🧰 Matériel</h3><button type='button' class='action-btn action-primary' onclick='addEq()'>＋ Matériel</button></div><div id='eqRows'></div></div><div class='full action-set'><a class='action-btn action-view' href='{{request.referrer or "/volunteer"}}'>← Retour / Annuler</a><button class='action-btn action-primary'>✓ Envoyer le don</button></div></form></div><template id='treeTpl'><div class='don-line'><select name='species_id[]'><option value=''>Espèce</option>{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}</option>{% endfor %}</select><input type='number' min='1' name='tree_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template><template id='eqTpl'><div class='don-line'><select name='equipment_id[]'><option value=''>Matériel</option>{% for x in equipment %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select><input type='number' min='1' name='equipment_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template><script>function addTree(){treeRows.append(treeTpl.content.cloneNode(true))}function addEq(){eqRows.append(eqTpl.content.cloneNode(true))}addTree();addEq();</script>""",species=species,equipment=equipment,assocs=assocs,values=values,error=error)

@app.route('/public/donate')
def public_donate():
 if session.get('uid'): return redirect('/volunteer/donate' if not is_admin() else '/donations/new')
 return public_page('Faire un don',"""<div class='card'><h1>Faire un don</h1><p>Les bénévoles inscrits peuvent déclarer un don en argent, arbres, matériel, eau, transport ou main-d’œuvre. La déclaration est ensuite validée par l’association.</p><a class='btn' href='/public/register?next=/volunteer/donate'>Créer un compte</a> <a class='btn alt' href='/login?next=/volunteer/donate'>Se connecter</a></div>""")

@app.get('/api/communes/<int:wilaya_id>')
def api_communes(wilaya_id):
 c=db(); rows=c.execute('SELECT id,name,name_ar FROM communes WHERE active=1 AND wilaya_id=? ORDER BY name',(wilaya_id,)).fetchall(); c.close(); return jsonify([dict(r) for r in rows])

# --- Alpha 8: pilotage opérationnel ---
@app.route('/operations', methods=['GET','POST'])
@login_required
def operations_planning():
 if request.method=='POST':
  if not is_admin(): return redirect('/operations')
  c=db(); now=datetime.now().isoformat(timespec='minutes')
  c.execute('INSERT INTO operational_tasks(title,task_type,status,priority,project_id,zone_id,team_id,assigned_user_id,start_at,end_at,description,created_by_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
   clean(request.form.get('title')),request.form.get('task_type') or 'Entretien',request.form.get('status') or 'Planifiée',request.form.get('priority') or 'Normale',request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('team_id') or None,request.form.get('assigned_user_id') or None,request.form.get('start_at'),request.form.get('end_at') or None,clean(request.form.get('description')),session['uid'],now,now))
  c.commit(); c.close(); flash('Intervention planifiée.'); return redirect('/operations')
 c=db(); q=clean(request.args.get('q')); status=clean(request.args.get('status')); project_id=request.args.get('project_id')
 sql="""SELECT t.*,p.name project_name,z.name zone_name,tm.name team_name,u.name assigned_name FROM operational_tasks t LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN teams tm ON tm.id=t.team_id LEFT JOIN users u ON u.id=t.assigned_user_id WHERE 1=1"""; args=[]
 if q: sql+=' AND (t.title LIKE ? OR t.description LIKE ?)'; args += ['%'+q+'%','%'+q+'%']
 if status: sql+=' AND t.status=?'; args.append(status)
 if project_id: sql+=' AND t.project_id=?'; args.append(project_id)
 sql+=" ORDER BY datetime(t.start_at), CASE t.priority WHEN 'Urgente' THEN 1 WHEN 'Haute' THEN 2 ELSE 3 END"
 rows=c.execute(sql,args).fetchall(); projects=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall(); zones=c.execute('SELECT id,name FROM zones WHERE active=1 ORDER BY name').fetchall(); teams=c.execute('SELECT id,name FROM teams WHERE active=1 ORDER BY name').fetchall(); users=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); c.close()
 return page('Planification opérationnelle',"""<div class='section-title'><div><h2>Calendrier opérationnel</h2><p class='sub'>Plantations, arrosages, entretiens et contrôles.</p></div><a class='btn alt' href='/operations/map'>Carte opérationnelle</a></div>{% if admin %}<details class='card'><summary><b>+ Planifier une intervention</b></summary><form method='post' class='form' style='margin-top:16px'><label>Titre<input name='title' required></label><label>Type<select name='task_type'><option>Plantation</option><option>Arrosage</option><option>Entretien</option><option>Contrôle</option><option>Mission</option></select></label><label>Statut<select name='status'><option>Planifiée</option><option>En cours</option><option>Terminée</option><option>Annulée</option></select></label><label>Priorité<select name='priority'><option>Normale</option><option>Haute</option><option>Urgente</option></select></label><label>Projet<select name='project_id'><option value=''>—</option>{% for x in projects %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name='zone_id'><option value=''>—</option>{% for x in zones %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label>Équipe<select name='team_id'><option value=''>—</option>{% for x in teams %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name='assigned_user_id'><option value=''>—</option>{% for x in users %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label>Début<input type='datetime-local' name='start_at' required></label><label>Fin<input type='datetime-local' name='end_at'></label><label class='full'>Description<textarea name='description'></textarea></label><div class='full'><button class='btn'>Enregistrer</button></div></form></details>{% endif %}<form class='card toolbar'><label>Recherche<input name='q' value='{{q}}'></label><label>Statut<select name='status'><option value=''>Tous</option>{% for x in ['Planifiée','En cours','Terminée','Annulée'] %}<option {% if status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Projet<select name='project_id'><option value=''>Tous</option>{% for x in projects %}<option value='{{x.id}}' {% if project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><button class='btn'>Filtrer</button></form><div class='card' style='overflow:auto'><table><tr><th>Date</th><th>Intervention</th><th>Projet / zone</th><th>Équipe</th><th>Responsable</th><th>État</th><th>Action</th></tr>{% for t in rows %}<tr><td>{{t.start_at}}</td><td><b>{{t.title}}</b><div class='sub'>{{t.task_type}} • {{t.priority}}</div></td><td>{{t.project_name or '—'}}<div class='sub'>{{t.zone_name or ''}}</div></td><td>{{t.team_name or '—'}}</td><td>{{t.assigned_name or '—'}}</td><td><span class='badge {% if t.status=="Terminée" %}good{% elif t.priority=="Urgente" %}danger{% else %}watch{% endif %}'>{{t.status}}</span></td><td><div class='crud-actions'>{% if admin and t.status!='Terminée' %}<form method='post' action='/operations/{{t.id}}/complete'><button class='btn alt'>Terminer</button></form>{% endif %}{% if admin %}<form method='post' action='/operations/{{t.id}}/delete' onsubmit="return confirm('Supprimer ou annuler cette planification ?')"><button class='btn red'>Supprimer</button></form>{% endif %}</div></td></tr>{% else %}<tr><td colspan='7'>Aucune intervention planifiée.</td></tr>{% endfor %}</table></div>""",rows=rows,projects=projects,zones=zones,teams=teams,users=users,q=q,status=status,project_id=project_id,admin=is_admin())

@app.post('/operations/<int:task_id>/complete')
@login_required
def operation_complete(task_id):
 if not is_admin(): return redirect('/operations')
 c=db(); now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE operational_tasks SET status='Terminée',completed_at=?,updated_at=? WHERE id=?",(now,now,task_id)); c.commit(); c.close(); log_action('complete','operational_task',task_id); flash('Intervention terminée.'); return redirect('/operations')

@app.route('/projects/<int:pid>/phases',methods=['GET','POST'])
@login_required
def project_phases(pid):
 c=db(); p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
 if not p: c.close(); return redirect('/projects')
 if request.method=='POST' and is_admin():
  now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO project_phases(project_id,name,status,start_date,end_date,progress,notes,position,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,clean(request.form.get('name')),request.form.get('status') or 'À faire',request.form.get('start_date') or None,request.form.get('end_date') or None,max(0,min(100,int(request.form.get('progress') or 0))),clean(request.form.get('notes')),int(request.form.get('position') or 0),now,now)); c.commit(); flash('Phase ajoutée.')
 rows=c.execute('SELECT * FROM project_phases WHERE project_id=? ORDER BY position,id',(pid,)).fetchall(); c.close()
 return page('Phases du projet',"""<div class='section-title'><h2>{{p.name}} — Phases</h2><a class='btn alt' href='/projects/{{p.id}}'>Retour au projet</a></div>{% if admin %}<div class='card'><form method='post' class='form'><label>Phase<input name='name' required placeholder='Préparation du terrain'></label><label>Statut<select name='status'><option>À faire</option><option>En cours</option><option>Terminée</option><option>Suspendue</option></select></label><label>Début<input type='date' name='start_date'></label><label>Fin<input type='date' name='end_date'></label><label>Progression %<input type='number' min='0' max='100' name='progress' value='0'></label><label>Ordre<input type='number' name='position' value='0'></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full'><button class='btn'>Ajouter</button></div></form></div>{% endif %}<div class='card'><table><tr><th>Phase</th><th>Période</th><th>État</th><th>Progression</th></tr>{% for x in rows %}<tr><td><b>{{x.name}}</b><div class='sub'>{{x.notes or ''}}</div></td><td>{{x.start_date or '—'}} → {{x.end_date or '—'}}</td><td>{{x.status}}</td><td><progress max='100' value='{{x.progress}}'></progress> {{x.progress}} %</td></tr>{% else %}<tr><td colspan='4'>Aucune phase définie.</td></tr>{% endfor %}</table></div>""",p=p,rows=rows,admin=is_admin())

@app.route('/operations/map')
@login_required
def operations_map():
 c=db(); tasks=c.execute("""SELECT t.*,z.name zone_name,z.latitude,z.longitude,p.name project_name FROM operational_tasks t LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.status IN ('Planifiée','En cours') AND z.latitude IS NOT NULL AND z.longitude IS NOT NULL ORDER BY t.start_at""").fetchall(); urgent=c.execute("SELECT t.id,t.tree_code,t.latitude,t.longitude,t.health_status,t.watering_status,s.name_fr species FROM trees t LEFT JOIN species s ON s.id=t.species_id WHERE t.active=1 AND t.latitude IS NOT NULL AND t.longitude IS NOT NULL AND (t.watering_status!='À jour' OR t.health_status IN ('À surveiller','Urgent','Critique'))").fetchall(); c.close()
 return page('Carte opérationnelle',"""<div class='section-title'><div><h2>Carte opérationnelle</h2><p class='sub'>Interventions planifiées et arbres prioritaires.</p></div><a class='btn alt' href='/operations'>Calendrier</a></div><div class='card'><div id='opMap' class='real-map' style='height:650px'></div></div><script>const tasks={{tasks_json|safe}},trees={{trees_json|safe}};const map=L.map('opMap').setView([35.697,-0.633],11);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(map);const bounds=[];tasks.forEach(x=>{L.marker([x.latitude,x.longitude]).addTo(map).bindPopup(`<b>${x.title}</b><br>${x.project_name||''} — ${x.zone_name||''}<br>${x.start_at}<br>${x.status}`);bounds.push([x.latitude,x.longitude])});trees.forEach(x=>{L.circleMarker([x.latitude,x.longitude],{radius:7,color:'#bd4747',fillOpacity:.85}).addTo(map).bindPopup(`<b>${x.tree_code||'Arbre'}</b><br>${x.species||''}<br>${x.health_status} • ${x.watering_status}<br><a href='/trees/${x.id}'>Ouvrir</a>`);bounds.push([x.latitude,x.longitude])});if(bounds.length)map.fitBounds(bounds,{padding:[25,25],maxZoom:16});</script>""",tasks_json=json.dumps([dict(x) for x in tasks],ensure_ascii=False),trees_json=json.dumps([dict(x) for x in urgent],ensure_ascii=False))

@app.route('/reports/operations')
@login_required
def operations_report():
 f=filters_from_request(); c=db(); guard=common_filter_guard(c,f)
 if guard: c.close(); return guard
 opts=common_filter_options(c,f); ctx=active_context(c); ids=[int(x['id']) for x in accessible_filter_projects(c,ctx)]
 w=['p.active=1']; args=[]
 if ctx.get('type')=='personal': w.append('p.association_id IS NULL')
 elif ctx.get('type')=='association':
  if ids: w.append('p.id IN ('+','.join('?'*len(ids))+')'); args.extend(ids)
  else: w.append('1=0')
 elif not is_super_admin(): w.append('1=0')
 if f['wilaya_id']: w.append('p.wilaya_id=?'); args.append(f['wilaya_id'])
 if f['commune_id']: w.append('p.commune_id=?'); args.append(f['commune_id'])
 if f['project_id']: w.append('p.id=?'); args.append(f['project_id'])
 where=' AND '.join(w)
 projects=c.execute("""SELECT p.id,p.code,p.name,p.status,p.target_trees,
 COUNT(DISTINCT CASE WHEN (?='' OR t.zone_id=?) AND (?='' OR t.species_id=?) AND (?='' OR t.planted_by_user_id=?) AND (?='' OR date(COALESCE(t.planted_at,t.created_at))>=date(?)) AND (?='' OR date(COALESCE(t.planted_at,t.created_at))<=date(?)) THEN t.id END) tree_count,
 COUNT(DISTINCT CASE WHEN (?='' OR ot.zone_id=?) AND (?='' OR date(ot.start_at)>=date(?)) AND (?='' OR date(ot.start_at)<=date(?)) THEN ot.id END) task_count,
 COUNT(DISTINCT CASE WHEN ot.status='Terminée' AND (?='' OR ot.zone_id=?) AND (?='' OR date(ot.start_at)>=date(?)) AND (?='' OR date(ot.start_at)<=date(?)) THEN ot.id END) done_count
 FROM projects p LEFT JOIN trees t ON t.project_id=p.id AND t.active=1 LEFT JOIN operational_tasks ot ON ot.project_id=p.id WHERE """+where+" GROUP BY p.id ORDER BY p.name",
 [f['zone_id'],f['zone_id'],f['species_id'],f['species_id'],f['volunteer_id'],f['volunteer_id'],f['date_from'],f['date_from'],f['date_to'],f['date_to'],f['zone_id'],f['zone_id'],f['date_from'],f['date_from'],f['date_to'],f['date_to'],f['zone_id'],f['zone_id'],f['date_from'],f['date_from'],f['date_to'],f['date_to']]+args).fetchall()
 stats={'projects':len(projects),'trees':sum(int(x['tree_count'] or 0) for x in projects),'tasks_open':0,'tasks_done':sum(int(x['done_count'] or 0) for x in projects),'priority':0,'volunteer_hours':0}
 allowed=set(ids)
 if projects:
  pids=[int(x['id']) for x in projects]; marks=','.join('?'*len(pids))
  tq=f"SELECT status,COUNT(*) n FROM operational_tasks WHERE project_id IN ({marks})"; ta=list(pids)
  if f['zone_id']: tq+=' AND zone_id=?'; ta.append(f['zone_id'])
  if f['date_from']: tq+=' AND date(start_at)>=date(?)'; ta.append(f['date_from'])
  if f['date_to']: tq+=' AND date(start_at)<=date(?)'; ta.append(f['date_to'])
  tq+=' GROUP BY status'
  for r in c.execute(tq,ta).fetchall():
   if r['status'] in ('Planifiée','En cours'): stats['tasks_open']+=r['n']
  tw=f"SELECT COUNT(*) n FROM trees WHERE active=1 AND project_id IN ({marks}) AND (watering_status!='À jour' OR health_status IN ('À surveiller','Urgent','Critique'))"; twa=list(pids)
  if f['zone_id']: tw+=' AND zone_id=?'; twa.append(f['zone_id'])
  if f['species_id']: tw+=' AND species_id=?'; twa.append(f['species_id'])
  if f['volunteer_id']: tw+=' AND planted_by_user_id=?'; twa.append(f['volunteer_id'])
  stats['priority']=c.execute(tw,twa).fetchone()['n']
  vh=f"SELECT COALESCE(SUM(hours),0) n FROM volunteer_time_logs WHERE validated=1 AND project_id IN ({marks})"; vha=list(pids)
  if f['volunteer_id']: vh+=' AND user_id=?'; vha.append(f['volunteer_id'])
  if f['date_from']: vh+=' AND date(work_date)>=date(?)'; vha.append(f['date_from'])
  if f['date_to']: vh+=' AND date(work_date)<=date(?)'; vha.append(f['date_to'])
  stats['volunteer_hours']=c.execute(vh,vha).fetchone()['n']
 c.close()
 return page('Rapports opérationnels',"""<div class='section-title'><div><h2>Rapport opérationnel</h2><p class='sub'>Les filtres utilisent le même périmètre que Carte, Arbres et Missions.</p></div><a class='btn' href='/reports/operations.csv?{{request.query_string.decode()}}'>Exporter CSV</a></div><form class='card toolbar'><label>Wilaya<select name='wilaya_id'><option value=''>Toutes</option>{% for x in wilayas %}<option value='{{x.id}}' {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Toutes</option>{% for x in communes %}<option value='{{x.id}}' {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name='project_id'><option value=''>Tous</option>{% for x in projects %}<option value='{{x.id}}' {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name='zone_id'><option value=''>Toutes</option>{% for x in zones %}<option value='{{x.id}}' {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name='species_id'><option value=''>Toutes</option>{% for x in species %}<option value='{{x.id}}' {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><label>Bénévole<select name='volunteer_id'><option value=''>Tous</option>{% for x in volunteers %}<option value='{{x.id}}' {% if f.volunteer_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Du<input type='date' name='date_from' value='{{f.date_from}}'></label><label>Au<input type='date' name='date_to' value='{{f.date_to}}'></label><button class='btn'>Filtrer</button><a class='btn alt' href='/reports/operations'>Effacer</a></form><div class='grid kpis' style='grid-template-columns:repeat(6,1fr)'>{% for label,value in [('Projets',stats.projects),('Tâches ouvertes',stats.tasks_open),('Tâches terminées',stats.tasks_done),('Arbres',stats.trees),('Arbres prioritaires',stats.priority),('Heures bénévoles',stats.volunteer_hours)] %}<div class='card kpi'><small>{{label}}</small><b>{{value}}</b></div>{% endfor %}</div><div class='card' style='overflow:auto'><table><tr><th>Projet</th><th>Statut</th><th>Arbres / objectif</th><th>Interventions</th><th>Terminées</th></tr>{% for p in report_projects %}<tr><td><a href='/projects/{{p.id}}'><b>{{p.code}} — {{p.name}}</b></a></td><td>{{p.status}}</td><td>{{p.tree_count}} / {{p.target_trees or 0}}</td><td>{{p.task_count}}</td><td>{{p.done_count or 0}}</td></tr>{% else %}<tr><td colspan='5'>Aucun projet.</td></tr>{% endfor %}</table></div>""",stats=stats,report_projects=projects,f=f,**opts)

@app.route('/reports/operations.csv')
@login_required
def operations_report_csv():
 import csv
 f=filters_from_request(); c=db(); guard=common_filter_guard(c,f)
 if guard: c.close(); return guard
 ctx=active_context(c); projects=[x for x in accessible_filter_projects(c,ctx) if (not f['project_id'] or str(x['id'])==str(f['project_id'])) and (not f['wilaya_id'] or str(x['wilaya_id'] or '')==str(f['wilaya_id'])) and (not f['commune_id'] or str(x['commune_id'] or '')==str(f['commune_id']))]
 out=io.StringIO(); w=csv.writer(out,delimiter=';'); w.writerow(['Code','Projet','Statut','Objectif arbres','Arbres suivis','Interventions','Terminées'])
 for p in projects:
  tq='SELECT COUNT(*) n FROM trees WHERE active=1 AND project_id=?'; ta=[p['id']]
  if f['zone_id']: tq+=' AND zone_id=?'; ta.append(f['zone_id'])
  if f['species_id']: tq+=' AND species_id=?'; ta.append(f['species_id'])
  if f['volunteer_id']: tq+=' AND planted_by_user_id=?'; ta.append(f['volunteer_id'])
  if f['date_from']: tq+=' AND date(COALESCE(planted_at,created_at))>=date(?)'; ta.append(f['date_from'])
  if f['date_to']: tq+=' AND date(COALESCE(planted_at,created_at))<=date(?)'; ta.append(f['date_to'])
  trees=c.execute(tq,ta).fetchone()['n']
  oq='SELECT status,COUNT(*) n FROM operational_tasks WHERE project_id=?'; oa=[p['id']]
  if f['zone_id']: oq+=' AND zone_id=?'; oa.append(f['zone_id'])
  if f['date_from']: oq+=' AND date(start_at)>=date(?)'; oa.append(f['date_from'])
  if f['date_to']: oq+=' AND date(start_at)<=date(?)'; oa.append(f['date_to'])
  oq+=' GROUP BY status'; rs=c.execute(oq,oa).fetchall(); total=sum(r['n'] for r in rs); done=sum(r['n'] for r in rs if r['status']=='Terminée')
  w.writerow([p['code'],p['name'],p['status'],p['target_trees'],trees,total,done])
 c.close(); data=io.BytesIO(('\ufeff'+out.getvalue()).encode('utf-8')); data.seek(0); return send_file(data,mimetype='text/csv',as_attachment=True,download_name='rapport-operationnel-mytree.csv')


# --- v1.8.0 Alpha 9 : suppressions contrôlées et automatisations ---
@app.post('/projects/<int:pid>/delete')
@login_required
def project_delete(pid):
 if not is_admin(): return redirect('/projects')
 c=db(); refs=sum(c.execute(f'SELECT COUNT(*) n FROM {table} WHERE project_id=?',(pid,)).fetchone()['n'] for table in ['zones','trees','teams','missions','events','operational_tasks'])
 if refs: c.execute('UPDATE projects SET active=0 WHERE id=?',(pid,)); msg='Projet archivé car il possède un historique.'
 else: c.execute('DELETE FROM projects WHERE id=?',(pid,)); msg='Projet supprimé.'
 c.commit(); c.close(); log_action('delete_or_archive','project',pid,msg); flash(msg); return redirect('/projects')

@app.post('/zones/<int:zid>/delete')
@login_required
def zone_delete(zid):
 if not is_admin(): return redirect('/zones')
 c=db(); refs=sum(c.execute(f'SELECT COUNT(*) n FROM {table} WHERE zone_id=?',(zid,)).fetchone()['n'] for table in ['trees','teams','missions','events','operational_tasks'])
 if refs: c.execute('UPDATE zones SET active=0 WHERE id=?',(zid,)); msg='Zone archivée : elle contient des arbres ou un historique lié et ne peut pas être supprimée physiquement.'
 else: c.execute('DELETE FROM zones WHERE id=?',(zid,)); msg='Zone supprimée.'
 c.commit(); c.close(); log_action('delete_or_archive','zone',zid,msg); flash(msg); return redirect('/zones')

@app.post('/users/<int:uid>/delete')
@login_required
def user_delete(uid):
 if not is_admin() or uid==session.get('uid'): flash('Suppression non autorisée.'); return redirect('/users')
 c=db(); refs=sum(c.execute(f'SELECT COUNT(*) n FROM {table} WHERE {col}=?',(uid,)).fetchone()['n'] for table,col in [('trees','planted_by_user_id'),('watering_logs','user_id'),('activity_log','user_id')])
 if refs: c.execute('UPDATE users SET active=0 WHERE id=?',(uid,)); msg='Utilisateur désactivé car il possède un historique.'
 else: c.execute('DELETE FROM users WHERE id=?',(uid,)); msg='Utilisateur supprimé.'
 c.commit(); c.close(); log_action('delete_or_deactivate','user',uid,msg); flash(msg); return redirect('/users')

@app.post('/teams/<int:tid>/delete')
@login_required
def team_delete(tid):
 if not is_admin(): return redirect('/teams')
 c=db(); refs=sum(c.execute(f'SELECT COUNT(*) n FROM {table} WHERE team_id=?',(tid,)).fetchone()['n'] for table in ['team_members','missions','events','operational_tasks'])
 if refs: c.execute('UPDATE teams SET active=0 WHERE id=?',(tid,)); msg='Équipe désactivée car elle possède un historique.'
 else: c.execute('DELETE FROM teams WHERE id=?',(tid,)); msg='Équipe supprimée.'
 c.commit(); c.close(); log_action('delete_or_archive','team',tid,msg); flash(msg); return redirect('/teams')

@app.post('/operations/<int:oid>/delete')
@login_required
def operation_delete(oid):
 if not is_admin(): return redirect('/operations')
 c=db(); row=c.execute('SELECT status FROM operational_tasks WHERE id=?',(oid,)).fetchone()
 if row:
  if row['status'] in ('Terminée','Annulée'): c.execute("UPDATE operational_tasks SET status='Annulée',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec='minutes'),oid)); msg='Planification annulée et conservée dans l’historique.'
  else: c.execute('DELETE FROM operational_tasks WHERE id=?',(oid,)); msg='Planification supprimée.'
  c.commit(); log_action('delete_or_cancel','operational_task',oid,msg); flash(msg)
 c.close(); return redirect('/operations')


@app.route('/backup')
@login_required
def backup_page():
 if not is_admin():
  flash('Accès réservé à l’administration.')
  return redirect('/')
 c=db(); check=c.execute('PRAGMA integrity_check').fetchone()[0]; tables=c.execute("SELECT COUNT(*) n FROM sqlite_master WHERE type='table'").fetchone()['n']; c.close()
 size=os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
 return page('Sauvegarde et restauration',"""<div class='grid two'><div class='card'><h2>Créer une sauvegarde</h2><p>La sauvegarde contient la base SQLite complète : arbres, utilisateurs, dons, caisse, pépinière, matériel et paramètres.</p><p><b>État :</b> {{check}}<br><b>Tables :</b> {{tables}}<br><b>Taille :</b> {{'%.2f'|format(size/1024/1024)}} Mo</p><a class='btn' href='/backup/download'>💾 Télécharger la sauvegarde</a></div><div class='card danger-zone'><h2>Restaurer une sauvegarde</h2><p>Cette opération remplace la base actuelle. Une copie de sécurité automatique est créée avant restauration.</p><form method='post' action='/backup/restore' enctype='multipart/form-data' onsubmit="return confirm('Restaurer cette base et remplacer les données actuelles ?')"><label>Fichier SQLite<input type='file' name='backup_file' accept='.db,.sqlite,.sqlite3' required></label><p><button class='btn red'>Restaurer</button></p></form></div></div>""",check=check,tables=tables,size=size)

@app.route('/backup/download')
@login_required
def backup_download():
 if not is_admin(): return redirect('/')
 if not os.path.exists(DB_PATH):
  init_db()
 stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
 tmp=os.path.join(tempfile.gettempdir(),f'mytree-backup-{stamp}.db')
 src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(tmp); src.backup(dst); dst.close(); src.close()
 log_action('backup','database',None,os.path.basename(tmp))
 return send_file(tmp,as_attachment=True,download_name=f'MyTree-backup-{stamp}.db')

@app.post('/backup/restore')
@login_required
def backup_restore():
 if not is_admin(): return redirect('/')
 f=request.files.get('backup_file')
 if not f or not f.filename:
  flash('Sélectionnez une sauvegarde SQLite.'); return redirect('/backup')
 fd,tmp=tempfile.mkstemp(suffix='.db'); os.close(fd); f.save(tmp)
 try:
  test=sqlite3.connect(tmp); result=test.execute('PRAGMA integrity_check').fetchone()[0]; required=test.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('users','trees','projects')").fetchone()[0]; test.close()
  if result!='ok' or required<3: raise ValueError('Sauvegarde invalide ou incomplète.')
  safety=DB_PATH+'.before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')
  if os.path.exists(DB_PATH): shutil.copy2(DB_PATH,safety)
  shutil.copy2(tmp,DB_PATH); init_db(); log_action('restore','database',None,os.path.basename(safety)); flash('Sauvegarde restaurée. Une copie de sécurité de l’ancienne base a été conservée.')
 except Exception as exc:
  flash('Restauration refusée : '+str(exc))
 finally:
  try: os.remove(tmp)
  except OSError: pass
 return redirect('/backup')


@app.route('/healthz')
def healthz():
 """Disponibilité + intégrité minimale pour Railway/Online Test."""
 try:
  d=database_diagnostics()
  secret_ok=bool(app.secret_key and app.secret_key!='change-this-secret' and len(str(app.secret_key))>=24)
  storage_ok=os.access(DATA_DIR,os.W_OK)
  ok=d['integrity']=='ok' and not d['missing_tables'] and d['foreign_key_errors']==0 and storage_ok and secret_ok
  payload={'status':'ok' if ok else 'degraded','version':APP_VERSION,'database':d['integrity'],'tables':d['tables'],'missing_tables':d['missing_tables'],'foreign_key_errors':d['foreign_key_errors'],'storage_writable':storage_ok,'secret_configured':secret_ok}
  return jsonify(payload), (200 if ok else 503)
 except Exception as exc:
  return jsonify({'status':'error','version':APP_VERSION,'error':str(exc)}),503

@app.route('/readyz')
def readyz():
 """Readiness stricte : utilisée avant d'ouvrir le candidat aux testeurs."""
 try:
  d=database_diagnostics(); ok=d['integrity']=='ok' and not d['missing_tables'] and d['foreign_key_errors']==0
  return jsonify({'ready':ok,'version':APP_VERSION,**d}), (200 if ok else 503)
 except Exception as exc:
  return jsonify({'ready':False,'version':APP_VERSION,'error':str(exc)}),503

@app.after_request
def lot12_security_headers(response):
 # En-têtes sûrs pour le candidat Online Test, sans casser Leaflet/caméra.
 response.headers.setdefault('X-Content-Type-Options','nosniff')
 response.headers.setdefault('X-Frame-Options','SAMEORIGIN')
 response.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
 response.headers.setdefault('Permissions-Policy','geolocation=(self), camera=(self), microphone=()')
 if request.is_secure:
  response.headers.setdefault('Strict-Transport-Security','max-age=15552000; includeSubDomains')
 return response


# --- Réglage v2.0 : activation des nouveaux bénévoles ---
@app.route('/admin/registration-settings',methods=['GET','POST'])
@login_required
def registration_settings():
 if not is_super_admin(): return redirect('/')
 c=db()
 if request.method=='POST':
  mode=request.form.get('mode') if request.form.get('mode') in ('auto','manual') else 'auto'
  c.execute("INSERT INTO settings(key,value) VALUES('volunteer_registration_mode',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(mode,)); c.commit(); c.close(); flash('Mode d’inscription mis à jour.'); return redirect('/admin/registration-settings')
 row=c.execute("SELECT value FROM settings WHERE key='volunteer_registration_mode'").fetchone(); mode=row['value'] if row else 'auto'; c.close()
 return page('Inscriptions bénévoles',"""<div class='card'><h2>⚙️ Inscriptions bénévoles</h2><p>Le mode automatique est recommandé : le compte est actif immédiatement, mais le Super Admin reçoit une notification informative.</p><form method='post'><label><input type='radio' name='mode' value='auto' {% if mode=='auto' %}checked{% endif %}> Activation automatique</label><label><input type='radio' name='mode' value='manual' {% if mode=='manual' %}checked{% endif %}> Validation manuelle</label><p class='sub'>L’adhésion à une association reste toujours soumise à acceptation, quel que soit ce réglage.</p><button class='btn'>Enregistrer</button></form></div>""",mode=mode)

# --- MyTree Professional v2.0 Alpha 1 : fondations Multi-Associations ---
def is_super_admin():
 return session.get('role')=='super_admin'

ASSOCIATION_TREE_SYMBOLS=('🌲','🌴','🌿','🌱','🪴','🎋','🍀','🌾','🌺','🌸','🍂','🍁','🫒','🌰','🍎','🍊','🍋','🍒','🥭','🥥','🌵')

def available_association_symbols(c, current_association_id=None, include_pending=True):
 used={r['map_symbol'] for r in c.execute("SELECT map_symbol FROM associations WHERE status='active' AND map_symbol IS NOT NULL AND map_symbol<>'' AND (? IS NULL OR id<>?)",(current_association_id,current_association_id)).fetchall()}
 if include_pending and 'requested_map_symbol' in columns(c,'association_creation_requests'):
  used.update(r['requested_map_symbol'] for r in c.execute("SELECT requested_map_symbol FROM association_creation_requests WHERE status='pending' AND requested_map_symbol IS NOT NULL AND requested_map_symbol<>''").fetchall())
 return [x for x in ASSOCIATION_TREE_SYMBOLS if x not in used]

def association_code(c):
 return next_entity_code(c,'associations','code','ASSOC',4)

def association_options(c, wilaya_id=None, commune_id=None):
 q="SELECT a.*,w.name wilaya_name,cm.name commune_name FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE a.status='active'"; args=[]
 if wilaya_id: q+=' AND a.wilaya_id=?'; args.append(wilaya_id)
 if commune_id: q+=' AND a.commune_id=?'; args.append(commune_id)
 q+=' ORDER BY a.name'
 return c.execute(q,args).fetchall()


def approved_associations(c,user_id):
 return c.execute("SELECT a.id,a.name,a.map_symbol,m.role_code,m.member_kind FROM association_memberships m JOIN associations a ON a.id=m.association_id WHERE m.user_id=? AND m.status='approved' AND a.status='active' ORDER BY a.name",(user_id,)).fetchall()

def active_context(c=None):
 # RC16.1: comptes totalement séparés. Aucun contexte Association n'est activable
 # depuis un compte Personnel. Le compte Association possède sa propre session.
 if session.get('account_type')=='association' and session.get('association_id'):
  return {'type':'association','association_id':int(session['association_id']),'name':session.get('name','Association'),'role_code':'association_account'}
 if not session.get('uid'): return {'type':'public','association_id':None,'name':'Public','role_code':None}
 if is_super_admin(): return {'type':'global','association_id':None,'name':'Global MyTree','role_code':'super_admin'}
 return {'type':'personal','association_id':None,'name':'Personnel','role_code':session.get('role') or 'volunteer'}

def current_association_id(): return active_context()['association_id']

def context_is_association_admin():
 ctx=active_context()
 return ctx['type']=='association' and (is_super_admin() or ctx.get('role_code') in ('association_admin','admin'))

def can_administer_association(c, association_id, user_id=None):
 user_id=user_id or session.get('uid')
 if not user_id or not association_id: return False
 if is_super_admin(): return True
 return bool(c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(association_id,user_id)).fetchone())

def context_switcher():
 return ''


def context_condition(alias=''):
 ctx=active_context(); col=(alias+'.' if alias else '')+'association_id'
 if is_super_admin() and ctx['type'] in ('global','personal'): return '1=1',[]
 if ctx['type']=='association' and ctx['association_id']: return col+'=?',[ctx['association_id']]
 return col+' IS NULL',[]

def context_user_condition(alias='u'):
 ctx=active_context(); prefix=(alias+'.' if alias else '')
 # Global et Personnel du super-admin gardent l'accès à la liste administrative.
 if is_super_admin() and ctx['type'] in ('global','personal'): return '1=1',[]
 if ctx['type']=='association' and ctx['association_id']:
  return prefix+'id IN (SELECT user_id FROM association_memberships WHERE association_id=? AND status=\'approved\')',[ctx['association_id']]
 return prefix+'id=?',[session.get('uid')]

def require_association_context():
 ctx=active_context()
 if ctx['type']!='association' or not ctx['association_id']:
  flash('Sélectionnez d’abord une association active pour cette opération.')
  return False
 return True

# redefine admin semantics for Alpha 2: global super-admin or admin of active association.
def is_admin():
 if session.get('role')=='super_admin': return True
 ctx=active_context()
 return ctx['type']=='association' and ctx.get('role_code') in ('association_admin','admin')


# Alpha 4 Lot 3 — permissions evaluated per association, never globally.
ASSOCIATION_ROLE_PERMISSIONS={
 'association_admin':{'*'}, 'admin':{'*'},
 'volunteer':{
  'dashboard.view','association.read','project.read','zone.read','tree.view','tree.create',
  'tree.request_delete','watering.view','watering.create','intervention.view','intervention.create',
  'mission.view','mission.close','team.view','event.view','event.register','map.view',
  'notification.view','donation.view','nursery.view','member.view','report.read'
 }
}

def association_membership(c,association_id,user_id=None):
 user_id=user_id or session.get('uid')
 if not user_id or not association_id: return None
 return c.execute("SELECT * FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' ORDER BY CASE role_code WHEN 'association_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END LIMIT 1",(association_id,user_id)).fetchone()

def audit_permission(c,association_id,permission_code,result,action='authorize',resource_type=None,resource_id=None,details=''):
 try:
  c.execute('INSERT INTO association_audit_logs(user_id,association_id,permission_code,action,resource_type,resource_id,result,details,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(session.get('uid'),association_id,permission_code,action,resource_type,resource_id,result,details,datetime.now().isoformat(timespec='seconds')))
  c.commit()
 except Exception:
  pass

def has_association_permission(code,association_id=None,resource_type=None,resource_id=None,audit_denied=True):
 if not session.get('uid'): return False
 c=db(); ctx=active_context(c); aid=association_id or ctx.get('association_id')
 if is_super_admin(): c.close(); return True
 if ctx.get('type')!='association' or not aid or int(ctx.get('association_id') or 0)!=int(aid):
  if audit_denied: audit_permission(c,aid,code,'denied','authorize',resource_type,resource_id,'Contexte association absent ou différent')
  c.close(); return False
 m=association_membership(c,aid)
 if not m:
  if audit_denied: audit_permission(c,aid,code,'denied','authorize',resource_type,resource_id,'Adhésion absente, inactive ou non approuvée')
  c.close(); return False
 allowed=ASSOCIATION_ROLE_PERMISSIONS.get(m['role_code'],set())
 ok='*' in allowed or code in allowed
 if not ok and audit_denied: audit_permission(c,aid,code,'denied','authorize',resource_type,resource_id,'Rôle association: '+str(m['role_code']))
 c.close(); return ok

def has_permission(code):
 # Association context: permissions are strictly membership-scoped.
 ctx=active_context()
 if ctx['type']=='association': return has_association_permission(code,ctx['association_id'])
 if ctx['type']=='global': return is_super_admin()
 # Personal context keeps legacy user/role permissions for personal data only.
 if not session.get('uid'): return False
 c=db()
 override=c.execute('SELECT up.granted FROM user_permissions up JOIN permissions p ON p.id=up.permission_id WHERE up.user_id=? AND p.code=?',(session['uid'],code)).fetchone()
 if override is not None: c.close(); return bool(override['granted'])
 row=c.execute('SELECT 1 FROM users u JOIN role_permissions rp ON rp.role_id=u.role_id JOIN permissions p ON p.id=rp.permission_id JOIN roles r ON r.id=u.role_id WHERE u.id=? AND u.active=1 AND r.active=1 AND p.code=?',(session['uid'],code)).fetchone(); c.close(); return bool(row)

def permission_required(code):
 def deco(fn):
  @wraps(fn)
  def wrapped(*a,**k):
   if not session.get('uid'): return redirect('/login')
   ctx=active_context()
   if not has_permission(code):
    if ctx['type']=='association': return ('Permission association refusée',403)
    return ('Accès non autorisé',403)
   return fn(*a,**k)
  return wrapped
 return deco

def association_permission_required(code):
 def deco(fn):
  @wraps(fn)
  def wrapped(*a,**k):
   if not session.get('uid'): return redirect('/login')
   ctx=active_context()
   if ctx['type']!='association' or not ctx.get('association_id'): return ('Contexte association requis',403)
   if not has_association_permission(code,ctx['association_id']): return ('Permission association refusée',403)
   return fn(*a,**k)
  return wrapped
 return deco

@app.route('/context/switch')
@login_required
def switch_context():
 # RC16.1: ancien switch de profils désactivé.
 flash('Les comptes Personnel et Association sont désormais totalement séparés.')
 return redirect(profile_home())


def tenant_resource_for_request():
 # Alpha 4: resolve tenant ownership from the URL rule, not from generic
 # parameter names. Alpha 3 reused tid/mid/pid across unrelated modules.
 rule=(request.url_rule.rule if request.url_rule else request.path).lower()
 mapping=(
  ('/projects/<', 'pid','projects'),
  ('/api/projects/<', 'pid','projects'),
  ('/zones/<', 'zid','zones'),
  ('/teams/<', 'tid','teams'),
  ('/api/teams/<', 'tid','teams'),
  ('/trees/<', 'tid','trees'),
  ('/tree/<', 'tid','trees'),
  ('/plantings/<', 'tid','trees'),
  ('/planting/<', 'tid','trees'),
  ('/qr/<', 'tid','trees'),
  ('/volunteer/gps-quick/<', 'tid','trees'),
  ('/missions/<', 'mid','missions'),
  ('/members/<', 'mid','members'),
  ('/events/<', 'eid','events'),
  ('/equipment/<', 'eid','equipment'),
  ('/donations/<', 'did','donations'),
  ('/agent-payments/<', 'pid','agent_payments'),
 )
 for prefix,arg,table in mapping:
  if rule.startswith(prefix): return arg,table
 return None,None

def tenant_access_allowed(ctx, association_id):
 if ctx['type']=='global' and is_super_admin(): return True
 if ctx['type']=='association': return association_id==ctx['association_id']
 return association_id is None

@app.before_request
def tenant_guard_alpha4():
 if not session.get('uid') or request.endpoint in ('switch_context','login','logout','public_home','public_associations','healthz','readyz','static'): return None
 ctx=active_context()
 if ctx['type']=='global' and is_super_admin(): return None
 arg,table=tenant_resource_for_request()
 if not arg or not request.view_args or arg not in request.view_args: return None
 ident=request.view_args[arg]; c=db(); has_assoc='association_id' in columns(c,table)
 fields='association_id,project_id' if table in ('missions','events') and 'project_id' in columns(c,table) else 'association_id'
 r=c.execute(f'SELECT {fields} FROM {table} WHERE id=?',(ident,)).fetchone() if has_assoc else None
 if r and not tenant_access_allowed(ctx,r['association_id']):
  # Lot 8: owner/partner associations may view operational resources attached to an accepted shared project.
  if table in ('missions','events') and ctx.get('type')=='association' and r['project_id'] and collaboration_access(c,r['project_id'],ctx.get('association_id'),'can_view'):
   c.close(); return None
  c.close(); return ('Accès association non autorisé',403)
 c.close(); return None

@app.route('/public/associations/<int:aid>')
def public_association_detail(aid):
 c=db()
 a=c.execute("SELECT a.*,w.name wilaya_name,cm.name commune_name FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE a.id=? AND a.status='active'",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 members=c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n']
 trees=c.execute("SELECT COUNT(*) n FROM trees WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 projects=c.execute("SELECT COUNT(*) n FROM projects WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 c.close()
 return public_page('Association',"""<section class='public-section'><div class='association-profile-hero'><div class='association-avatar'>{{a.map_symbol or '🌿'}}</div><div><h1>{{a.name}}</h1><div class='sub'>{{a.wilaya_name or '—'}} / {{a.commune_name or '—'}}</div></div></div><div class='card'><p>{{a.description or 'Présentation à compléter.'}}</p><p><b>Adresse :</b> {{a.address or '—'}}</p><p><b>Téléphone :</b> {{a.phone or '—'}}</p><p><b>E-mail :</b> {{a.email or '—'}}</p><p><b>Site :</b> {{a.website or '—'}}</p></div><div class='grid kpis'><div class='card kpi'><small>Membres</small><b>{{members}}</b></div><div class='card kpi'><small>Arbres</small><b>{{trees}}</b></div><div class='card kpi'><small>Projets</small><b>{{projects}}</b></div></div><div class='action-set'>{% if session.get('uid') %}<form method='post' action='/associations/{{a.id}}/join'><input type='hidden' name='member_kind' value='member'><button class='btn'>🤝 Devenir adhérent</button></form><a class='btn alt' href='/volunteer/donate?association_id={{a.id}}'>🎁 Faire un don</a>{% else %}<a class='btn' href='/login?account_type=personal&next=/public/associations/{{a.id}}'>🤝 Se connecter pour devenir adhérent</a><a class='btn alt' href='/login?account_type=personal&next=/volunteer/donate?association_id={{a.id}}'>🎁 Se connecter pour faire un don</a>{% endif %}</div></section>""",a=a,members=members,trees=trees,projects=projects)

@app.route('/public/associations')
def public_associations():
 wid=request.args.get('wilaya_id'); cid=request.args.get('commune_id'); q=clean(request.args.get('q')); c=db(); rows=association_options(c,wid,cid)
 if q:
  nq=q.casefold(); rows=[r for r in rows if nq in ((r['name'] or '')+' '+(r['short_name'] or '')+' '+(r['wilaya_name'] or '')+' '+(r['commune_name'] or '')).casefold()]
 wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); c.close()
 return public_page('Associations',"""<h1>🏛 Associations</h1><form class='card form' method='get'><label>Wilaya<select name='wilaya_id'><option value=''>Toutes</option>{% for w in wilayas %}<option value='{{w.id}}' {% if wid|string==w.id|string %}selected{% endif %}>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Toutes</option>{% for x in communes %}<option value='{{x.id}}' {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Recherche<input type='search' name='q' value='{{q}}' placeholder='Nom, wilaya, commune…'></label><div class='full'><button class='btn'>Rechercher</button> {% if session.get('uid') %}<a class='btn alt' href='/association-request/new'>Demander la création d’une association</a>{% endif %}</div></form><div class='species-grid'>{% for a in rows %}<div class='species-card'><h3>{{a.map_symbol or '🌳'}} {{a.name}}</h3><p>{{a.description or 'Présentation à compléter.'}}</p><div class='sub'>{{a.wilaya_name or '—'}} / {{a.commune_name or '—'}}</div><div class='action-set' style='margin-top:10px'><a class='btn alt' href='/public/associations/{{a.id}}'>Consulter</a>{% if session.get('uid') %}<a class='btn alt' href='/volunteer/donate?association_id={{a.id}}'>Faire un don</a>{% endif %}</div>{% if session.get('uid') %}<div class='action-set' style='margin-top:10px'><form method='post' action='/associations/{{a.id}}/join'><input type='hidden' name='member_kind' value='volunteer'><button class='btn'>Rejoindre comme bénévole</button></form><form method='post' action='/associations/{{a.id}}/join'><input type='hidden' name='member_kind' value='member'><button class='btn alt'>Demander adhésion</button></form></div>{% endif %}</div>{% else %}<div class='card'>Aucune association avec ces critères.</div>{% endfor %}</div>""",rows=rows,wilayas=wilayas,communes=communes,wid=wid,cid=cid,q=q)

@app.route('/my-associations')
@login_required
def my_associations():
 c=db()
 rows=c.execute("SELECT m.*,a.name,a.map_symbol,w.name wilaya_name,cm.name commune_name FROM association_memberships m JOIN associations a ON a.id=m.association_id LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE m.user_id=? ORDER BY CASE m.status WHEN 'approved' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,a.name",(session['uid'],)).fetchall()
 creation_requests=c.execute("SELECT * FROM association_creation_requests WHERE requested_by_user_id=? ORDER BY id DESC",(session['uid'],)).fetchall(); c.close()
 return page('Mes associations',"""<div class='section-title'><div><h2>🏛 Mes associations</h2><p class='sub'>Votre compte reste personnel. Les associations auxquelles vous participez sont gérées séparément.</p></div></div><div class='card association-mobile-actions'><a class='btn' href='/public/associations'>🤝 Rejoindre une association</a><a class='btn' href='/association-request/new'>➕ Demander la création d’une association</a></div>{% if creation_requests %}<div class='card'><h3>📨 Mes demandes de création</h3><div style='overflow:auto'><table><tr><th>Association</th><th>Statut</th><th>Date</th><th>Motif</th></tr>{% for r in creation_requests %}<tr><td>{{r.name}}</td><td><span class='badge'>{{r.status}}</span></td><td>{{r.requested_at}}</td><td>{{r.rejection_reason or '—'}}</td></tr>{% endfor %}</table></div></div>{% endif %}<div class='species-grid'>{% for m in rows %}<div class='species-card'><h3>{{m.map_symbol or '🌳'}} {{m.name}}</h3><p>{{m.wilaya_name or '—'}} / {{m.commune_name or '—'}}</p><span class='badge'>{{m.status}}</span> <span class='badge watch'>{{m.role_code}}</span></div>{% else %}<div class='card'>Vous n’êtes encore membre d’aucune association.</div>{% endfor %}</div>""",rows=rows,creation_requests=creation_requests)

@app.post('/associations/<int:aid>/join')
@login_required
def association_join(aid):
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); flash('Association introuvable.'); return redirect('/public/associations')
 member_kind=request.form.get('member_kind') if request.form.get('member_kind') in ('volunteer','member') else 'volunteer'; existing=c.execute("SELECT * FROM association_memberships WHERE association_id=? AND user_id=? AND member_kind=?",(aid,session['uid'],member_kind)).fetchone(); now=datetime.now().isoformat(timespec='minutes')
 if existing and existing['status'] in ('pending','approved'):
  c.close(); flash('Une demande ou adhésion existe déjà pour cette association.'); return redirect('/my-associations')
 if existing: c.execute("UPDATE association_memberships SET status='pending',requested_at=?,reviewed_by_user_id=NULL,reviewed_at=NULL,rejection_reason=NULL WHERE id=?",(now,existing['id']))
 else: c.execute("INSERT INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at) VALUES(?,?,?,?, 'pending',?)",(aid,session['uid'],member_kind,('member' if member_kind=='member' else 'volunteer'),now))
 admins=c.execute("SELECT DISTINCT u.id FROM users u WHERE u.active=1 AND (u.role='super_admin' OR u.id IN (SELECT user_id FROM association_memberships WHERE association_id=? AND status='approved' AND role_code IN ('association_admin','admin'))) ",(aid,)).fetchall()
 for x in admins: c.execute("INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)",(x['id'],'Demande d’adhésion',session.get('name','Un utilisateur')+(' demande une adhésion à ' if member_kind=='member' else ' souhaite rejoindre ')+a['name']+'.','/membership-requests','Action requise','association_membership',aid,now))
 c.commit(); c.close(); log_action('request_join','association',aid); flash('Demande d’adhésion envoyée à l’association.'); return redirect('/my-associations')

@app.route('/membership-requests')
@login_required
def membership_requests():
 if not is_admin(): return redirect('/my-associations')
 c=db(); where="m.status='pending'"; args=[]
 if not is_super_admin():
  where+=" AND m.association_id IN (SELECT association_id FROM association_memberships WHERE user_id=? AND status='approved' AND role_code IN ('association_admin','admin'))"; args.append(session['uid'])
 rows=c.execute("SELECT m.*,a.name association_name,u.name user_name,u.phone,u.email FROM association_memberships m JOIN associations a ON a.id=m.association_id JOIN users u ON u.id=m.user_id WHERE "+where+" ORDER BY m.requested_at DESC",args).fetchall(); c.close()
 return page('Demandes adhésion',"""<div class='card'><h2>🟠 Demandes d’adhésion</h2><table><tr><th>Association</th><th>Utilisateur</th><th>Type</th><th>Contact</th><th>Date</th><th>Actions</th></tr>{% for r in rows %}<tr><td>{{r.association_name}}</td><td>{{r.user_name}}</td><td>{{'Adhérent' if r.member_kind=='member' else 'Bénévole'}}</td><td>{{r.phone or r.email or '—'}}</td><td>{{r.requested_at}}</td><td><form method='post' action='/membership-requests/{{r.id}}/approve' style='display:inline'><button class='btn'>Accepter</button></form> <form method='post' action='/membership-requests/{{r.id}}/reject' style='display:inline'><input name='reason' placeholder='Motif' style='width:130px;display:inline'><button class='btn alt'>Refuser</button></form></td></tr>{% else %}<tr><td colspan='5'>Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.post('/membership-requests/<int:mid>/approve')
@login_required
def membership_approve(mid):
 if not is_admin(): return redirect('/my-associations')
 c=db(); m=c.execute('SELECT * FROM association_memberships WHERE id=?',(mid,)).fetchone()
 if not m: c.close(); return redirect('/membership-requests')
 if not is_super_admin():
  ok=c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(m['association_id'],session['uid'])).fetchone()
  if not ok: c.close(); flash('Accès non autorisé.'); return redirect('/membership-requests')
 now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE association_memberships SET status='approved',reviewed_by_user_id=?,reviewed_at=?,rejection_reason=NULL WHERE id=?",(session['uid'],now,mid)); a=c.execute('SELECT name FROM associations WHERE id=?',(m['association_id'],)).fetchone(); c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(m['user_id'],'Adhésion acceptée','Votre demande pour '+a['name']+' a été acceptée.','/my-associations','Information',now)); c.commit(); c.close(); log_action('approve_membership','association_membership',mid); flash('Adhésion acceptée.'); return redirect('/membership-requests')

@app.post('/membership-requests/<int:mid>/reject')
@login_required
def membership_reject(mid):
 if not is_admin(): return redirect('/my-associations')
 reason=clean(request.form.get('reason')); c=db(); m=c.execute('SELECT * FROM association_memberships WHERE id=?',(mid,)).fetchone()
 if not m: c.close(); return redirect('/membership-requests')
 if not is_super_admin():
  ok=c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(m['association_id'],session['uid'])).fetchone()
  if not ok: c.close(); flash('Accès non autorisé.'); return redirect('/membership-requests')
 now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE association_memberships SET status='rejected',reviewed_by_user_id=?,reviewed_at=?,rejection_reason=? WHERE id=?",(session['uid'],now,reason,mid)); a=c.execute('SELECT name FROM associations WHERE id=?',(m['association_id'],)).fetchone(); c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(m['user_id'],'Adhésion refusée','Votre demande pour '+a['name']+' a été refusée.'+((' Motif : '+reason) if reason else ''),'/my-associations','Information',now)); c.commit(); c.close(); log_action('reject_membership','association_membership',mid,reason); flash('Demande refusée.'); return redirect('/membership-requests')

@app.route('/association-request/new',methods=['GET','POST'])
@login_required
def association_request_new():
 values={k:clean(request.form.get(k)) for k in ['name','association_login_id','organization_type','approval_number','wilaya_id','commune_id','phone','email','address','description','map_symbol']}
 values['organization_type']=values.get('organization_type') or 'volunteer_group'
 errors={}
 if request.method=='POST':
  c=db(); now=datetime.now().isoformat(timespec='minutes'); assoc_password=str(request.form.get('association_password') or '')
  if not values['name']: errors['name']='Ce champ est obligatoire.'
  if not values['association_login_id'] or len(values['association_login_id'])<4: errors['association_login_id']='Choisissez un ID Association d’au moins 4 caractères.'
  elif c.execute("SELECT 1 FROM association_accounts WHERE lower(login_id)=lower(?)",(values['association_login_id'],)).fetchone() or c.execute("SELECT 1 FROM association_creation_requests WHERE status='pending' AND lower(COALESCE(requested_login_id,''))=lower(?)",(values['association_login_id'],)).fetchone(): errors['association_login_id']='Cet ID Association est déjà utilisé.'
  if len(assoc_password)<6: errors['association_password']='Le mot de passe doit contenir au moins 6 caractères.'
  if not values['map_symbol'] or values['map_symbol'] not in available_association_symbols(c): errors['map_symbol']='Choisissez un symbole disponible.'
  upload=request.files.get('approval_document_file')
  if values['organization_type']=='approved_association':
   if not values['approval_number']: errors['approval_number']='Le numéro d’agrément est obligatoire.'
   if not upload or not upload.filename: errors['approval_document_file']='Joignez l’agrément en photo (JPG/PNG) ou PDF.'
  if errors:
   wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); symbols=available_association_symbols(c); c.close()
  else:
   rel_doc=None; doc_name=None; doc_mime=None
   if upload and upload.filename:
    ext=os.path.splitext(upload.filename)[1].lower(); allowed={'.jpg','.jpeg','.png','.pdf'}
    if ext not in allowed:
     errors['approval_document_file']='Format accepté : JPG, JPEG, PNG ou PDF.'
     wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); symbols=available_association_symbols(c); c.close()
    else:
     folder=os.path.join(DATA_DIR,'uploads','association_approvals'); os.makedirs(folder,exist_ok=True); name=secrets.token_hex(12)+ext; upload.save(os.path.join(folder,name)); rel_doc='uploads/association_approvals/'+name; doc_name=os.path.basename(upload.filename); doc_mime=upload.mimetype
   if not errors:
    cur=c.execute("INSERT INTO association_creation_requests(requested_by_user_id,name,description,wilaya_id,commune_id,address,phone,email,status,requested_at,requested_map_symbol,requested_login_id,requested_password_hash,organization_type,approval_number,approval_document,approval_document_name,approval_document_mime) VALUES(?,?,?,?,?,?,?,?, 'pending',?,?,?,?,?,?,?,?,?,?)",(session['uid'],values['name'],values['description'],values['wilaya_id'] or None,values['commune_id'] or None,values['address'],values['phone'],values['email'],now,values['map_symbol'],values['association_login_id'],generate_password_hash(assoc_password),values['organization_type'],values['approval_number'],rel_doc,doc_name,doc_mime)); rid=cur.lastrowid
    for x in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall(): c.execute("INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)",(x['id'],'Nouvelle demande d’association',values['name']+' demande son enregistrement dans MyTree.','/association-requests','Action requise','association_request',rid,now))
    c.commit(); c.close(); flash('Demande d’association envoyée au Super Admin.'); return redirect('/my-associations')
 else:
  c=db(); wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); symbols=available_association_symbols(c); c.close()
 return page('Demander une association',"""<div class='card'><h2>🏛 Demander la création d’une association</h2>{% if errors %}<div class='flash flash-error'>Complétez uniquement les champs signalés. Vos autres informations sont conservées.</div>{% endif %}<form method='post' enctype='multipart/form-data' class='form' id='assocRequest'><label>Nom<input name='name' value='{{v.name}}' class='{{"field-error" if errors.get("name") else ""}}'>{% if errors.get('name') %}<small class='error-text'>{{errors.name}}</small>{% endif %}</label><label>ID Association souhaité<input name='association_login_id' value='{{v.association_login_id}}' minlength='4' placeholder='ex: AMIS-NATURE-ORAN'>{% if errors.get('association_login_id') %}<small class='error-text'>{{errors.association_login_id}}</small>{% endif %}</label><label>Mot de passe Association<input type='password' name='association_password' minlength='6'>{% if errors.get('association_password') %}<small class='error-text'>{{errors.association_password}}</small>{% endif %}</label><label>Type<select name='organization_type' id='orgType'><option value='volunteer_group' {% if v.organization_type=='volunteer_group' %}selected{% endif %}>Groupe de bénévoles</option><option value='approved_association' {% if v.organization_type=='approved_association' %}selected{% endif %}>Association agréée</option></select></label><div id='approvalFields' class='full form' style='display:contents'><label>N° d’agrément<input name='approval_number' value='{{v.approval_number}}'>{% if errors.get('approval_number') %}<small class='error-text'>{{errors.approval_number}}</small>{% endif %}</label><label>Joindre l’agrément (JPG/PNG/PDF)<input type='file' name='approval_document_file' accept='.jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf'>{% if errors.get('approval_document_file') %}<small class='error-text'>{{errors.approval_document_file}}</small>{% endif %}</label></div><div class='full'><b>Symbole de l’association sur la carte</b>{% if errors.get('map_symbol') %}<small class='error-text'>{{errors.map_symbol}}</small>{% endif %}<div class='symbol-picker'>{% for symbol in symbols %}<label class='symbol-choice'><input type='radio' name='map_symbol' value='{{symbol}}' {% if v.map_symbol==symbol %}checked{% endif %}><span>{{symbol}}</span></label>{% endfor %}</div></div><label>Wilaya<select name='wilaya_id'><option value=''>Choisir</option>{% for w in wilayas %}<option value='{{w.id}}' {% if v.wilaya_id|string==w.id|string %}selected{% endif %}>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Choisir</option>{% for c in communes %}<option value='{{c.id}}' {% if v.commune_id|string==c.id|string %}selected{% endif %}>{{c.name}}</option>{% endfor %}</select></label><label>Téléphone<input name='phone' value='{{v.phone}}'></label><label>E-mail<input name='email' type='email' value='{{v.email}}'></label><label class='full'>Adresse<input name='address' value='{{v.address}}'></label><label class='full'>Présentation<textarea name='description'>{{v.description}}</textarea></label><div class='full'><button class='btn'>Envoyer la demande</button> <a class='btn alt' href='/my-associations'>Annuler</a></div></form></div><style>.error-text{display:block;color:#b42318;font-weight:700;margin-top:5px}.field-error{border-color:#b42318!important}</style><script>(function(){const t=document.getElementById('orgType'),f=document.getElementById('approvalFields');function u(){f.style.display=t.value==='approved_association'?'contents':'none'}t.addEventListener('change',u);u();const e=document.querySelector('.error-text');if(e)e.closest('label,div')?.scrollIntoView({behavior:'smooth',block:'center'});})();</script>""",wilayas=wilayas,communes=communes,symbols=symbols,v=values,errors=errors)


@app.get('/association-requests/document/<path:name>')
@login_required
def association_request_document(name):
 if not is_super_admin(): return ('Accès refusé',403)
 return send_from_directory(os.path.join(DATA_DIR,'uploads','association_approvals'),os.path.basename(name),as_attachment=False)

@app.route('/association-requests')
@login_required
def association_requests():
 if not is_super_admin(): return redirect('/')
 c=db(); rows=c.execute("SELECT r.*,u.name requester,w.name wilaya_name,cm.name commune_name FROM association_creation_requests r LEFT JOIN users u ON u.id=r.requested_by_user_id LEFT JOIN wilayas w ON w.id=r.wilaya_id LEFT JOIN communes cm ON cm.id=r.commune_id WHERE r.status='pending' ORDER BY r.requested_at DESC").fetchall(); c.close()
 return page('Demandes associations',"""<div class='section-title'><h2>📨 Demandes de création d’association</h2><a class='btn' href='/admin/associations/new'>Créer directement</a></div><div class='card'><table><tr><th>Association</th><th>Demandeur</th><th>Localisation</th><th>Date</th><th>Actions</th></tr>{% for r in rows %}<tr><td>{{r.name}}</td><td>{{r.requester}}</td><td>{{r.wilaya_name or '—'}} / {{r.commune_name or '—'}}</td><td>{{r.requested_at}}</td><td><form method='post' action='/association-requests/{{r.id}}/approve' style='display:inline'><button class='btn'>Accepter</button></form> <form method='post' action='/association-requests/{{r.id}}/reject' style='display:inline'><input name='reason' placeholder='Motif' style='width:120px;display:inline'><button class='btn alt'>Refuser</button></form></td></tr>{% else %}<tr><td colspan='5'>Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.post('/association-requests/<int:rid>/approve')
@login_required
def association_request_approve(rid):
 if not is_super_admin(): return redirect('/')
 c=db()
 try:
  r=c.execute("SELECT * FROM association_creation_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
  if not r:
   c.close(); flash('Cette demande a déjà été traitée ou n’existe plus.'); return redirect('/association-requests')
  now=datetime.now().isoformat(timespec='minutes'); code=(r['requested_login_id'] if 'requested_login_id' in r.keys() and r['requested_login_id'] else association_code(c)); symbol=r['requested_map_symbol'] if 'requested_map_symbol' in r.keys() else None
  if not symbol or symbol not in available_association_symbols(c,include_pending=False):
   c.close(); flash('Le symbole demandé n’est plus disponible. Modifiez la demande avant validation.'); return redirect('/association-requests')
  cur=c.execute("INSERT INTO associations(code,name,description,wilaya_id,commune_id,address,phone,email,map_symbol,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?, 'active',?,?)",
                (code,r['name'],r['description'],r['wilaya_id'],r['commune_id'],r['address'],r['phone'],r['email'],symbol,session['uid'],now))
  aid=cur.lastrowid
  if 'requested_login_id' in r.keys() and r['requested_login_id'] and r['requested_password_hash']:
   c.execute("INSERT INTO association_accounts(association_id,login_id,password_hash,active,created_at) VALUES(?,?,?,?,?)",(aid,r['requested_login_id'],r['requested_password_hash'],1,now))
  c.execute("UPDATE association_creation_requests SET status='approved',reviewed_by_user_id=?,reviewed_at=?,rejection_reason=NULL WHERE id=?",
            (session['uid'],now,rid))
  c.execute("INSERT OR REPLACE INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at,reviewed_by_user_id,reviewed_at) VALUES(?,?,'volunteer','association_admin','approved',?,?,?)",
            (aid,r['requested_by_user_id'],r['requested_at'],session['uid'],now))
  c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",
            (r['requested_by_user_id'],'Association créée','Votre association '+r['name']+' a été validée.','/my-associations','Information',now))
  c.commit(); c.close()
  flash('Association créée. Le demandeur conserve son profil personnel et dispose maintenant du profil Association.')
  return redirect('/admin/associations')
 except Exception:
  try: c.rollback(); c.close()
  except Exception: pass
  raise


@app.post('/association-requests/<int:rid>/reject')
@login_required
def association_request_reject(rid):
 if not is_super_admin(): return redirect('/')
 reason=clean(request.form.get('reason')); c=db(); r=c.execute("SELECT * FROM association_creation_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if r:
  now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE association_creation_requests SET status='rejected',reviewed_by_user_id=?,reviewed_at=?,rejection_reason=? WHERE id=?",(session['uid'],now,reason,rid)); c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(r['requested_by_user_id'],'Demande d’association refusée','La demande '+r['name']+' a été refusée.'+((' Motif : '+reason) if reason else ''),'/my-associations','Information',now)); c.commit()
 c.close(); flash('Demande refusée.'); return redirect('/association-requests')

@app.route('/admin/associations')
@login_required
def admin_associations():
 if not is_super_admin(): return redirect('/')
 c=db()
 show_archived=request.args.get('archived')=='1'; status='archived' if show_archived else 'active'; rows=c.execute("SELECT a.*,w.name wilaya_name,cm.name commune_name,(SELECT COUNT(*) FROM association_memberships m WHERE m.association_id=a.id AND m.status='approved') member_count FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE a.status=? ORDER BY a.id DESC",(status,)).fetchall()
 pending=c.execute("SELECT COUNT(*) n FROM association_creation_requests WHERE status='pending'").fetchone()['n']
 archive_pending=c.execute("SELECT COUNT(*) n FROM association_archive_requests WHERE status='pending'").fetchone()['n']
 c.close()
 return page('Associations',"""<div class='section-title'><div><h2>🏛 Associations MyTree</h2><p class='sub'>Gestion globale des associations.</p></div></div><div class='card association-mobile-actions'><a class='btn' href='/association-requests'>📨 Créations en attente ({{pending}})</a><a class='btn' href='/admin/association-archive-requests'>🗄 Archivages en attente ({{archive_pending}})</a><a class='btn' href='/admin/associations/new'>➕ Nouvelle association</a><a class='btn alt' href='/admin/associations?archived=1'>🗄 Associations archivées</a><a class='btn alt' href='/admin/associations'>Actives</a></div><div class='card'><div style='overflow:auto'><table><tr><th>Code</th><th>Association</th><th>Wilaya / Commune</th><th>Membres</th><th>Statut</th><th>Gestion</th></tr>{% for a in rows %}<tr><td>{{a.code}}</td><td>{{a.map_symbol or '🌳'}} {{a.name}}</td><td>{{a.wilaya_name or '—'}} / {{a.commune_name or '—'}}</td><td>{{a.member_count}}</td><td><span class='badge'>{{a.status}}</span></td><td class='crud-actions'><a class='btn alt' href='/admin/associations/{{a.id}}'>Voir</a><a class='btn alt' href='/admin/associations/{{a.id}}/members'>Membres</a><a class='btn alt' href='/admin/associations/{{a.id}}/edit'>Modifier</a>{% if a.status=='active' %}<form method='post' action='/admin/associations/{{a.id}}/archive' onsubmit="return confirm('Archiver cette association ?')"><button class='btn amber'>Archiver</button></form>{% else %}<form method='post' action='/admin/associations/{{a.id}}/restore'><button class='btn'>Restaurer</button></form>{% endif %}</td></tr>{% endfor %}</table></div></div>""",rows=rows,pending=pending,archive_pending=archive_pending)

@app.route('/admin/associations/<int:aid>')
@login_required
def admin_association_detail(aid):
 if not is_super_admin(): return redirect('/')
 c=db()
 a=c.execute("SELECT a.*,w.name wilaya_name,cm.name commune_name FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE a.id=?",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 members=c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n']
 trees=c.execute("SELECT COUNT(*) n FROM trees WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 projects=c.execute("SELECT COUNT(*) n FROM projects WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 c.close()
 return page('Association',"""<div class='section-title'><div><h2>{{a.map_symbol or '🌿'}} {{a.name}}</h2><p class='sub'>{{a.code}} · {{a.status}}</p></div><div class='crud-actions'><a class='btn' href='/admin/associations/{{a.id}}/edit'>Modifier</a><a class='btn alt' href='/admin/associations/{{a.id}}/members'>Membres</a><a class='btn alt' href='/public/associations/{{a.id}}'>Vue publique</a></div></div><div class='card'><p><b>Description :</b> {{a.description or '—'}}</p><p><b>Localisation :</b> {{a.wilaya_name or '—'}} / {{a.commune_name or '—'}}</p><p><b>Adresse :</b> {{a.address or '—'}}</p><p><b>Téléphone :</b> {{a.phone or '—'}}</p><p><b>E-mail :</b> {{a.email or '—'}}</p><p><b>Site :</b> {{a.website or '—'}}</p></div><div class='grid kpis'><div class='card kpi'><small>Membres</small><b>{{members}}</b></div><div class='card kpi'><small>Arbres</small><b>{{trees}}</b></div><div class='card kpi'><small>Projets</small><b>{{projects}}</b></div></div>""",a=a,members=members,trees=trees,projects=projects)

def association_members_detail_page(c,a,back_url):
 rows=c.execute("SELECT m.*,u.name,u.phone,u.email FROM association_memberships m JOIN users u ON u.id=m.user_id WHERE m.association_id=? AND m.status='approved' ORDER BY CASE m.role_code WHEN 'association_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,u.name",(a['id'],)).fetchall()
 return page('Membres association',"""<div class='section-title'><div><h2>👥 Membres — {{a.name}}</h2><p class='sub'>Membres actifs de cette association uniquement.</p></div><a class='btn alt' href='{{back_url}}'>← Retour à l’association</a></div><div class='card' style='overflow:auto'><table><tr><th>Nom</th><th>Contact</th><th>Rôle</th><th>Statut</th><th>Depuis</th></tr>{% for m in rows %}<tr><td>{{m.name}}</td><td>{{m.phone or m.email or '—'}}</td><td>{{m.role_code}}</td><td>{{m.status}}</td><td>{{m.requested_at or '—'}}</td></tr>{% else %}<tr><td colspan='5'>Aucun membre actif.</td></tr>{% endfor %}</table></div>""",a=a,rows=rows,back_url=back_url)

def association_trees_detail_page(c,a,back_url):
 rows=c.execute("""SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name,u.name volunteer_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE t.association_id=? AND t.active=1 ORDER BY t.id DESC""",(a['id'],)).fetchall()
 return page('Arbres association',"""<div class='section-title'><div><h2>🌳 Arbres — {{a.name}}</h2><p class='sub'>{{rows|length}} arbre(s) rattaché(s) à cette association.</p></div><a class='btn alt' href='{{back_url}}'>← Retour à l’association</a></div><div class='card' style='overflow:auto'><table><tr><th>Code</th><th>Espèce</th><th>Projet / Zone</th><th>Planteur</th><th>Santé</th><th>Validation</th><th></th></tr>{% for t in rows %}<tr><td>{{t.tree_code or 'En attente'}}</td><td>{{t.species_name or t.species or '—'}}</td><td>{{t.project_name or '—'}} / {{t.zone_name or '—'}}</td><td>{{t.volunteer_name or t.planted_by or '—'}}</td><td>{{t.health_status}}</td><td>{{t.approval_status}}</td><td><a class='btn alt' href='/tree/{{t.id}}'>Voir</a></td></tr>{% else %}<tr><td colspan='7'>Aucun arbre.</td></tr>{% endfor %}</table></div>""",a=a,rows=rows,back_url=back_url)

def association_projects_detail_page(c,a,back_url):
 rows=c.execute("""SELECT p.*,u.name manager_name,(SELECT COUNT(*) FROM zones z WHERE z.project_id=p.id AND z.active=1) zone_count,(SELECT COUNT(*) FROM trees t WHERE t.project_id=p.id AND t.active=1) tree_count FROM projects p LEFT JOIN users u ON u.id=p.manager_user_id WHERE p.association_id=? ORDER BY p.active DESC,p.id DESC""",(a['id'],)).fetchall()
 return page('Projets association',"""<div class='section-title'><div><h2>📁 Projets — {{a.name}}</h2><p class='sub'>{{rows|length}} projet(s) rattaché(s) à cette association.</p></div><a class='btn alt' href='{{back_url}}'>← Retour à l’association</a></div><div class='card' style='overflow:auto'><table><tr><th>Code</th><th>Projet</th><th>Responsable</th><th>Statut</th><th>Zones</th><th>Arbres</th><th></th></tr>{% for p in rows %}<tr><td>{{p.code}}</td><td>{{p.name}}</td><td>{{p.manager_name or '—'}}</td><td>{{'Actif' if p.active else 'Archivé'}} · {{p.status}}</td><td>{{p.zone_count}}</td><td>{{p.tree_count}}</td><td><a class='btn alt' href='/projects/{{p.id}}'>Voir</a></td></tr>{% else %}<tr><td colspan='7'>Aucun projet.</td></tr>{% endfor %}</table></div>""",a=a,rows=rows,back_url=back_url)

@app.route('/admin/associations/<int:aid>/trees')
@login_required
def admin_association_trees(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 response=association_trees_detail_page(c,a,'/admin/associations/'+str(aid)); c.close(); return response

@app.route('/admin/associations/<int:aid>/projects')
@login_required
def admin_association_projects(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 response=association_projects_detail_page(c,a,'/admin/associations/'+str(aid)); c.close(); return response

@app.route('/association/members')
@login_required
def association_members_detail():
 ctx=active_context(); aid=ctx.get('association_id') if ctx.get('type')=='association' else None
 if not aid: return redirect('/volunteer')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return redirect('/volunteer')
 response=association_members_detail_page(c,a,'/association'); c.close(); return response

@app.route('/association/trees')
@login_required
def association_trees_detail():
 ctx=active_context(); aid=ctx.get('association_id') if ctx.get('type')=='association' else None
 if not aid: return redirect('/volunteer')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return redirect('/volunteer')
 response=association_trees_detail_page(c,a,'/association'); c.close(); return response

@app.route('/association/projects')
@login_required
def association_projects_detail():
 ctx=active_context(); aid=ctx.get('association_id') if ctx.get('type')=='association' else None
 if not aid: return redirect('/volunteer')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return redirect('/volunteer')
 response=association_projects_detail_page(c,a,'/association'); c.close(); return response

@app.route('/admin/associations/<int:aid>/members')
@login_required
def admin_association_members(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 response=association_members_detail_page(c,a,'/admin/associations/'+str(aid)); c.close(); return response

@app.route('/admin/associations/<int:aid>/edit',methods=['GET','POST'])
@login_required
def admin_association_edit(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if not a: c.close(); return ('Association introuvable',404)
 if request.method=='POST':
  symbol=clean(request.form.get('map_symbol'))
  allowed=set(available_association_symbols(c,current_association_id=aid,include_pending=True))
  if symbol!=a['map_symbol'] and symbol not in allowed:
   c.close(); flash('Ce symbole est déjà utilisé ou réservé.'); return redirect('/admin/associations/'+str(aid)+'/edit')
  c.execute("UPDATE associations SET name=?,short_name=?,description=?,wilaya_id=?,commune_id=?,address=?,phone=?,email=?,website=?,map_symbol=?,updated_at=? WHERE id=?",
            (clean(request.form.get('name')),clean(request.form.get('short_name')),clean(request.form.get('description')),request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,clean(request.form.get('address')),clean(request.form.get('phone')),clean(request.form.get('email')),clean(request.form.get('website')),symbol,datetime.now().isoformat(timespec='minutes'),aid))
  c.commit(); c.close(); flash('Association modifiée.'); return redirect('/admin/associations/'+str(aid))
 symbols=[a['map_symbol']]+[x for x in available_association_symbols(c,current_association_id=aid,include_pending=True) if x!=a['map_symbol']]
 wilayas=c.execute("SELECT * FROM wilayas WHERE active=1 ORDER BY name").fetchall(); communes=c.execute("SELECT * FROM communes WHERE active=1 ORDER BY name").fetchall(); c.close()
 return page('Modifier association',"""<div class='card'><h2>Modifier {{a.name}}</h2><form method='post' class='form'><label>Nom<input name='name' value='{{a.name}}' required></label><label>Nom court<input name='short_name' value='{{a.short_name or ''}}'></label><label>Symbole<select name='map_symbol'>{% for s in symbols %}<option value='{{s}}' {% if s==a.map_symbol %}selected{% endif %}>{{s}}</option>{% endfor %}</select></label><label>Wilaya<select name='wilaya_id'><option value=''>—</option>{% for w in wilayas %}<option value='{{w.id}}' {% if w.id==a.wilaya_id %}selected{% endif %}>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>—</option>{% for x in communes %}<option value='{{x.id}}' {% if x.id==a.commune_id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Téléphone<input name='phone' value='{{a.phone or ''}}'></label><label>E-mail<input name='email' value='{{a.email or ''}}'></label><label>Site<input name='website' value='{{a.website or ''}}'></label><label class='full'>Adresse<input name='address' value='{{a.address or ''}}'></label><label class='full'>Description<textarea name='description'>{{a.description or ''}}</textarea></label><div class='full'><button class='btn'>Enregistrer</button><a class='btn alt' href='/admin/associations/{{a.id}}'>Annuler</a></div></form></div>""",a=a,symbols=symbols,wilayas=wilayas,communes=communes)

@app.post('/admin/associations/<int:aid>/archive')
@login_required
def admin_association_archive(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if a and a['status']=='active':
  c.execute("UPDATE associations SET status='archived',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec='minutes'),aid)); c.execute("UPDATE association_accounts SET active=0 WHERE association_id=?",(aid,))
  c.execute("UPDATE association_archive_requests SET status='approved',reviewed_by_user_id=?,reviewed_at=? WHERE association_id=? AND status='pending'",(session['uid'],datetime.now().isoformat(timespec='minutes'),aid))
  c.commit(); flash('Association archivée.')
 c.close(); return redirect('/admin/associations')

@app.post('/admin/associations/<int:aid>/restore')
@login_required
def admin_association_restore(aid):
 if not is_super_admin(): return redirect('/')
 c=db(); c.execute("UPDATE associations SET status='active',updated_at=? WHERE id=? AND status='archived'",(datetime.now().isoformat(timespec='minutes'),aid)); c.execute("UPDATE association_accounts SET active=1 WHERE association_id=?",(aid,)); c.commit(); c.close(); flash('Association restaurée.'); return redirect('/admin/associations')

@app.post('/admin/associations/<int:aid>/delete')
@login_required
def admin_association_delete(aid):
 # RC16.1 : suppression = archivage logique. Les arbres et historiques restent intacts.
 return admin_association_archive(aid)

@app.post('/association/archive-request')
@login_required
def association_archive_request():
 ctx=active_context()
 if ctx.get('type')!='association' or ctx.get('role_code') not in ('association_admin','admin'): return ('Administration association requise',403)
 aid=ctx['association_id']; reason=clean(request.form.get('reason')); c=db(); now=datetime.now().isoformat(timespec='minutes')
 existing=c.execute("SELECT id FROM association_archive_requests WHERE association_id=? AND status='pending'",(aid,)).fetchone()
 if existing: c.close(); flash('Une demande d’archivage est déjà en attente.'); return redirect('/association')
 c.execute("INSERT INTO association_archive_requests(association_id,requested_by_user_id,status,reason,requested_at) VALUES(?,?,'pending',?,?)",(aid,session['uid'],reason,now))
 for u in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall():
  c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(u['id'],'Demande d’archivage association','Une association demande son archivage.','/admin/association-archive-requests','Action requise',now))
 c.commit(); c.close(); flash('Demande d’archivage envoyée au Super Admin.'); return redirect('/association')

@app.route('/admin/association-archive-requests')
@login_required
def admin_association_archive_requests():
 if not is_super_admin(): return redirect('/')
 c=db(); rows=c.execute("SELECT r.*,a.name association_name,a.map_symbol,u.name requester FROM association_archive_requests r JOIN associations a ON a.id=r.association_id JOIN users u ON u.id=r.requested_by_user_id WHERE r.status='pending' ORDER BY r.id DESC").fetchall(); c.close()
 return page('Demandes archivage',"""<div class='card'><h2>🗄 Demandes d’archivage</h2><table><tr><th>Association</th><th>Demandeur</th><th>Motif</th><th>Date</th><th>Actions</th></tr>{% for r in rows %}<tr><td>{{r.map_symbol}} {{r.association_name}}</td><td>{{r.requester}}</td><td>{{r.reason or '—'}}</td><td>{{r.requested_at}}</td><td><form method='post' action='/admin/association-archive-requests/{{r.id}}/approve' style='display:inline'><button class='btn'>Valider</button></form><form method='post' action='/admin/association-archive-requests/{{r.id}}/reject' style='display:inline'><input name='reason' placeholder='Motif'><button class='btn alt'>Refuser</button></form></td></tr>{% else %}<tr><td colspan='5'>Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.post('/admin/association-archive-requests/<int:rid>/approve')
@login_required
def admin_association_archive_request_approve(rid):
 if not is_super_admin(): return redirect('/')
 c=db(); r=c.execute("SELECT * FROM association_archive_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if not r: c.close(); return redirect('/admin/association-archive-requests')
 now=datetime.now().isoformat(timespec='minutes')
 c.execute("UPDATE associations SET status='archived',updated_at=? WHERE id=?",(now,r['association_id'])); c.execute("UPDATE association_accounts SET active=0 WHERE association_id=?",(r['association_id'],))
 c.execute("UPDATE association_archive_requests SET status='approved',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid))
 c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(r['requested_by_user_id'],'Archivage accepté','La demande d’archivage de votre association a été acceptée.','/my-associations','Information',now))
 c.commit(); c.close(); flash('Association archivée.'); return redirect('/admin/association-archive-requests')

@app.post('/admin/association-archive-requests/<int:rid>/reject')
@login_required
def admin_association_archive_request_reject(rid):
 if not is_super_admin(): return redirect('/')
 reason=clean(request.form.get('reason')); c=db(); r=c.execute("SELECT * FROM association_archive_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if r:
  now=datetime.now().isoformat(timespec='minutes')
  c.execute("UPDATE association_archive_requests SET status='rejected',reviewed_by_user_id=?,reviewed_at=?,rejection_reason=? WHERE id=?",(session['uid'],now,reason,rid))
  c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(r['requested_by_user_id'],'Archivage refusé','La demande d’archivage a été refusée.'+((' Motif : '+reason) if reason else ''),'/association','Information',now))
  c.commit()
 c.close(); return redirect('/admin/association-archive-requests')

@app.route('/admin/associations/new',methods=['GET','POST'])
@login_required
def admin_association_new():
 if not is_super_admin(): return redirect('/')
 if request.method=='POST':
  c=db(); name=clean(request.form.get('name')); now=datetime.now().isoformat(timespec='minutes')
  if not name: c.close(); flash('Nom obligatoire.'); return redirect('/admin/associations/new')
  symbol=clean(request.form.get('map_symbol'))
  if symbol not in available_association_symbols(c): c.close(); flash('Ce symbole arbre est déjà utilisé par une autre association. Choisissez-en un autre.'); return redirect('/admin/associations/new')
  c.execute("INSERT INTO associations(code,name,short_name,description,wilaya_id,commune_id,address,phone,email,map_symbol,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'active',?,?)",(association_code(c),name,clean(request.form.get('short_name')),clean(request.form.get('description')),request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,clean(request.form.get('address')),clean(request.form.get('phone')),clean(request.form.get('email')),symbol,session['uid'],now)); c.commit(); c.close(); flash('Association créée.'); return redirect('/admin/associations')
 c=db(); wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); symbols=available_association_symbols(c); c.close()
 return page('Nouvelle association',"""<div class='card'><h2>Nouvelle association</h2><form method='post' class='form'><label>Nom<input name='name' required></label><label>Nom court<input name='short_name'></label><div class='full'><b>Symbole carte</b><div class='symbol-picker'>{% for symbol in symbols %}<label class='symbol-choice'><input type='radio' name='map_symbol' value='{{symbol}}' required><span>{{symbol}}</span></label>{% endfor %}</div></div><label>Wilaya<select name='wilaya_id'><option value=''>Choisir</option>{% for w in wilayas %}<option value='{{w.id}}'>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Choisir</option>{% for c in communes %}<option value='{{c.id}}'>{{c.name}}</option>{% endfor %}</select></label><label>Téléphone<input name='phone'></label><label>E-mail<input type='email' name='email'></label><label class='full'>Adresse<input name='address'></label><label class='full'>Présentation<textarea name='description'></textarea></label><div class='full'><button class='btn'>Créer</button> <a class='btn alt' href='/admin/associations'>Annuler</a></div></form></div>""",wilayas=wilayas,communes=communes,symbols=symbols)

@app.get('/api/associations')
def api_associations():
 c=db(); rows=association_options(c,request.args.get('wilaya_id'),request.args.get('commune_id')); out=[{'id':r['id'],'name':r['name'],'symbol':r['map_symbol'],'wilaya_id':r['wilaya_id'],'commune_id':r['commune_id']} for r in rows]; c.close(); return jsonify(out)



def collaboration_history(c,cid,action,association_id=None,details=''):
 c.execute('INSERT INTO association_collaboration_history(collaboration_id,action,actor_user_id,association_id,details,created_at) VALUES(?,?,?,?,?,?)',(cid,action,session.get('uid'),association_id,details,datetime.now().isoformat(timespec='seconds')))

def collaboration_access(c,project_id,association_id,capability='can_view'):
 p=c.execute('SELECT association_id FROM projects WHERE id=? AND active=1',(project_id,)).fetchone()
 if not p: return False
 if int(p['association_id'] or 0)==int(association_id or 0): return True
 if capability not in ('can_view','can_intervene','can_add_tree','can_manage_missions'): return False
 return bool(c.execute(f"SELECT 1 FROM association_collaborations WHERE project_id=? AND invited_association_id=? AND status='accepted' AND {capability}=1",(project_id,association_id)).fetchone())

@app.route('/projects/<int:pid>/collaboration',methods=['GET','POST'])
@login_required
def project_collaboration(pid):
 c=db(); p=c.execute('SELECT * FROM projects WHERE id=? AND active=1',(pid,)).fetchone()
 if not p: c.close(); return ('Projet introuvable',404)
 owner=p['association_id']
 if not owner: c.close(); flash('La collaboration inter-associations est réservée aux projets d’association.'); return redirect('/projects/'+str(pid))
 if not can_administer_association(c,owner): c.close(); return ('Administration de l’association propriétaire requise',403)
 if request.method=='POST':
  invited=int(request.form.get('association_id') or 0); target=c.execute("SELECT id,name FROM associations WHERE id=? AND status='active'",(invited,)).fetchone() if invited else None
  if not target or invited==owner: c.close(); flash('Association invitée invalide.'); return redirect('/projects/'+str(pid)+'/collaboration')
  now=datetime.now().isoformat(timespec='minutes'); existing=c.execute("SELECT * FROM association_collaborations WHERE project_id=? AND inviting_association_id=? AND invited_association_id=?",(pid,owner,invited)).fetchone()
  if existing and existing['status'] in ('pending','accepted'): flash('Une invitation ou collaboration existe déjà avec cette association.')
  else:
   rights=(1,1,1 if request.form.get('can_add_tree') else 0,1 if request.form.get('can_manage_missions') else 0)
   if existing:
    c.execute("UPDATE association_collaborations SET status='pending',can_view=?,can_intervene=?,can_add_tree=?,can_manage_missions=?,created_by_user_id=?,created_at=?,reviewed_by_user_id=NULL,reviewed_at=NULL,ended_by_user_id=NULL,ended_at=NULL,end_reason=NULL WHERE id=?",(*rights,session['uid'],now,existing['id'])); cid=existing['id']
   else:
    cur=c.execute("INSERT INTO association_collaborations(project_id,inviting_association_id,invited_association_id,status,can_view,can_intervene,can_add_tree,can_manage_missions,created_by_user_id,created_at) VALUES(?,?,?,'pending',?,?,?,?,?,?)",(pid,owner,invited,*rights,session['uid'],now)); cid=cur.lastrowid
   collaboration_history(c,cid,'invited',owner,'Invitation envoyée à '+target['name'])
   admins=c.execute("SELECT DISTINCT user_id FROM association_memberships WHERE association_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(invited,)).fetchall()
   for admin in admins: c.execute("INSERT INTO notifications(user_id,title,message,link,category,is_read,created_at) VALUES(?,?,?,?,?,0,?)",(admin['user_id'],'Invitation de collaboration','Invitation à collaborer sur le projet '+p['name']+'.','/collaborations','Collaboration',now))
   c.commit(); flash('Invitation de collaboration envoyée.')
 rows=c.execute('SELECT ac.*,a1.name inviter_name,a2.name invited_name FROM association_collaborations ac JOIN associations a1 ON a1.id=ac.inviting_association_id JOIN associations a2 ON a2.id=ac.invited_association_id WHERE ac.project_id=? ORDER BY ac.id DESC',(pid,)).fetchall(); assocs=c.execute("SELECT id,name,map_symbol FROM associations WHERE status='active' AND id<>? ORDER BY name",(owner,)).fetchall(); c.close()
 content="""<div class='card'><h2>🤝 Collaboration — {{p.name}}</h2><p class='sub'>L’association propriétaire conserve le contrôle du projet. Les droits partenaires sont explicites.</p><form method='post'><label>Association<select name='association_id' required><option value=''>Choisir</option>{% for a in assocs %}<option value='{{a.id}}'>{{a.map_symbol}} {{a.name}}</option>{% endfor %}</select></label><label><input type='checkbox' name='can_add_tree'> Autoriser ajout d’arbres</label><label><input type='checkbox' name='can_manage_missions'> Autoriser gestion des missions</label><button class='btn'>Inviter</button> <a class='btn alt' href='/collaborations'>Centre de collaboration</a></form></div><div class='card'><table><tr><th>Partenaire</th><th>Statut</th><th>Droits</th><th>Action</th></tr>{% for x in rows %}<tr><td>{{x.invited_name}}</td><td>{{x.status}}</td><td>Voir ✓ · Intervention ✓ · Arbres {{'✓' if x.can_add_tree else '—'}} · Missions {{'✓' if x.can_manage_missions else '—'}}</td><td>{% if x.status=='accepted' %}<form method='post' action='/collaborations/{{x.id}}/end'><input name='reason' placeholder='Motif'><button class='btn alt'>Terminer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan='4'>Aucune collaboration.</td></tr>{% endfor %}</table></div>"""
 return page('Collaboration associations',content,p=p,assocs=assocs,rows=rows)

@app.route('/collaborations')
@login_required
def collaborations_center():
 ctx=active_context()
 if ctx['type']!='association' or not ctx['association_id']: flash('Sélectionnez une association pour consulter ses collaborations.'); return redirect('/my-associations')
 c=db(); aid=ctx['association_id']; rows=c.execute("SELECT ac.*,p.name project_name,a1.name inviter_name,a2.name invited_name FROM association_collaborations ac JOIN projects p ON p.id=ac.project_id JOIN associations a1 ON a1.id=ac.inviting_association_id JOIN associations a2 ON a2.id=ac.invited_association_id WHERE ac.inviting_association_id=? OR ac.invited_association_id=? ORDER BY CASE ac.status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,ac.id DESC",(aid,aid)).fetchall(); admin=can_administer_association(c,aid); c.close()
 content="""<div class='section-title'><div><h2>🤝 Centre de collaboration</h2><p class='sub'>Projets propres et partenariats de l’association active.</p></div></div><div class='card'><table><tr><th>Projet</th><th>Propriétaire</th><th>Partenaire</th><th>Statut</th><th>Droits</th><th>Action</th></tr>{% for x in rows %}<tr><td>{{x.project_name}}</td><td>{{x.inviter_name}}</td><td>{{x.invited_name}}</td><td>{{x.status}}</td><td>Voir {{'✓' if x.can_view else '—'}} · Intervention {{'✓' if x.can_intervene else '—'}} · Arbres {{'✓' if x.can_add_tree else '—'}} · Missions {{'✓' if x.can_manage_missions else '—'}}</td><td>{% if admin and x.invited_association_id==aid and x.status=='pending' %}<div class='action-set'><form method='post' action='/collaborations/{{x.id}}/accept'><button class='btn'>Accepter</button></form><form method='post' action='/collaborations/{{x.id}}/reject'><button class='btn alt'>Refuser</button></form></div>{% elif admin and x.invited_association_id==aid and x.status=='accepted' %}<form method='post' action='/collaborations/{{x.id}}/leave'><button class='btn alt'>Quitter</button></form>{% elif x.status=='accepted' %}<span class='badge ok'>Active</span>{% else %}—{% endif %}</td></tr>{% else %}<tr><td colspan='6'>Aucune collaboration.</td></tr>{% endfor %}</table></div>"""
 return page('Collaborations',content,rows=rows,aid=aid,admin=admin)

@app.post('/collaborations/<int:cid>/<decision>')
@login_required
def collaboration_decision(cid,decision):
 if decision not in ('accept','reject','leave','end'): return ('Décision invalide',400)
 c=db(); x=c.execute('SELECT * FROM association_collaborations WHERE id=?',(cid,)).fetchone()
 if not x: c.close(); return ('Collaboration introuvable',404)
 now=datetime.now().isoformat(timespec='minutes')
 if decision in ('accept','reject'):
  if x['status']!='pending': c.close(); return ('Invitation déjà traitée',409)
  if not can_administer_association(c,x['invited_association_id']): c.close(); return ('Accès refusé',403)
  status='accepted' if decision=='accept' else 'rejected'; c.execute('UPDATE association_collaborations SET status=?,reviewed_by_user_id=?,reviewed_at=? WHERE id=?',(status,session['uid'],now,cid)); collaboration_history(c,cid,status,x['invited_association_id'])
 elif decision=='leave':
  if x['status']!='accepted' or not can_administer_association(c,x['invited_association_id']): c.close(); return ('Accès refusé',403)
  c.execute("UPDATE association_collaborations SET status='left',ended_by_user_id=?,ended_at=?,end_reason=? WHERE id=?",(session['uid'],now,'Partenaire a quitté la collaboration',cid)); collaboration_history(c,cid,'left',x['invited_association_id'])
 else:
  if x['status']!='accepted' or not can_administer_association(c,x['inviting_association_id']): c.close(); return ('Accès refusé',403)
  reason=clean(request.form.get('reason')) or 'Collaboration terminée par le propriétaire'; c.execute("UPDATE association_collaborations SET status='ended',ended_by_user_id=?,ended_at=?,end_reason=? WHERE id=?",(session['uid'],now,reason,cid)); collaboration_history(c,cid,'ended',x['inviting_association_id'],reason)
 c.commit(); c.close(); flash('Collaboration mise à jour.'); return redirect(request.referrer or '/collaborations')

@app.get('/collaborations/<int:cid>/history')
@login_required
def collaboration_history_view(cid):
 c=db(); x=c.execute('SELECT * FROM association_collaborations WHERE id=?',(cid,)).fetchone()
 if not x: c.close(); return ('Collaboration introuvable',404)
 ctx=active_context(c); aid=ctx.get('association_id')
 if not is_super_admin() and int(aid or 0) not in (int(x['inviting_association_id']),int(x['invited_association_id'])): c.close(); return ('Accès refusé',403)
 rows=c.execute('SELECT h.*,u.name actor_name FROM association_collaboration_history h LEFT JOIN users u ON u.id=h.actor_user_id WHERE h.collaboration_id=? ORDER BY h.id DESC',(cid,)).fetchall(); c.close()
 return page('Historique collaboration',"""<div class='card'><h2>Historique collaboration</h2><table><tr><th>Date</th><th>Action</th><th>Utilisateur</th><th>Détails</th></tr>{% for h in rows %}<tr><td>{{h.created_at}}</td><td>{{h.action}}</td><td>{{h.actor_name or '—'}}</td><td>{{h.details or '—'}}</td></tr>{% endfor %}</table></div>""",rows=rows)


# ---------------------------------------------------------------------------
# Android API v1 — Alpha 1 Lot 4
# Token stateless signé par MYTREE_SECRET. Le rôle global et les rôles
# d'association restent strictement séparés.
# ---------------------------------------------------------------------------
def android_token_serializer():
 return URLSafeTimedSerializer(app.secret_key,salt='mytree-android-v1')

def android_issue_token(uid):
 return android_token_serializer().dumps({'uid':int(uid)})

def android_uid():
 auth=request.headers.get('Authorization','')
 if not auth.startswith('Bearer '): return None
 token=auth[7:].strip()
 try:
  data=android_token_serializer().loads(token,max_age=60*60*24*30)
  return int(data.get('uid') or 0) or None
 except (BadSignature,SignatureExpired,ValueError,TypeError):
  return None

def android_auth(fn):
 @wraps(fn)
 def wrapped(*a,**k):
  uid=android_uid()
  if not uid: return jsonify({'error':{'message':'Authentification requise'}}),401
  c=db(); u=c.execute("SELECT id FROM users WHERE id=? AND active=1",(uid,)).fetchone(); c.close()
  if not u: return jsonify({'error':{'message':'Compte inactif ou introuvable'}}),401
  request.android_uid=uid
  return fn(*a,**k)
 return wrapped

def android_assoc_id(c,uid):
 raw=request.headers.get('X-MyTree-Association-Id')
 if not raw: return None
 try: aid=int(raw)
 except (TypeError,ValueError): return None
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 if u and u['role']=='super_admin': return aid
 ok=c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
 return aid if ok else None

def android_assoc_payload(c,uid):
 rows=c.execute("""SELECT a.id,a.code,a.name,a.short_name,a.map_symbol,m.role_code
 FROM association_memberships m JOIN associations a ON a.id=m.association_id
 WHERE m.user_id=? AND m.status='approved' AND a.status='active' ORDER BY a.name""",(uid,)).fetchall()
 return [dict(id=x['id'],code=x['code'],name=x['name'],short_name=x['short_name'],
              map_symbol=x['map_symbol'] or '🌿',role_code=x['role_code']) for x in rows]

def android_context_payload(c,uid,aid=None):
 if aid:
  a=c.execute("SELECT id,name FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
  u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
  if u and u['role']=='super_admin': role='super_admin'
  else:
   m=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
   if not m: aid=None
   else: role=m['role_code']
  if aid and a:
   perms=list(ASSOCIATION_ROLE_PERMISSIONS.get(role,set()))
   return {'type':'association','association_id':aid,'association_name':a['name'],'role_code':role,'permissions':perms}
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 role=(u['role'] if u else 'volunteer') or 'volunteer'
 return {'type':'personal','association_id':None,'association_name':'Personnel','role_code':role,'permissions':[]}


@app.get('/.well-known/assetlinks.json')
def android_assetlinks():
 # SHA-256 du certificat de signature de l'APK, configurable sur Railway.
 # Exemple de valeur : AA:BB:CC:... (sans valeur, la route reste valide mais ne vérifie aucune signature).
 fingerprint=(os.environ.get('MYTREE_ANDROID_SHA256_CERT') or '').strip()
 if not fingerprint:
  return jsonify([])
 return jsonify([{
  'relation':['delegate_permission/common.handle_all_urls'],
  'target':{
   'namespace':'android_app',
   'package_name':'dz.mytree.professional',
   'sha256_cert_fingerprints':[fingerprint]
  }
 }])

@app.get('/api/v1')
def android_api_root():
 return jsonify({'ok':True,'api':'v1','service':'MyTree Professional Android API','version':APP_VERSION})


@app.get('/api/v1/app-version')
def android_app_version():
 latest=os.environ.get('MYTREE_ANDROID_LATEST_VERSION','0.1-alpha1-lot12-rc7')
 minimum=os.environ.get('MYTREE_ANDROID_MIN_VERSION','0.1-alpha1')
 maintenance=os.environ.get('MYTREE_MAINTENANCE','0').lower() in ('1','true','yes','on')
 message=os.environ.get('MYTREE_ANDROID_UPDATE_MESSAGE','')
 download=os.environ.get('MYTREE_ANDROID_DOWNLOAD_URL','')
 current=request.args.get('current','')
 def vparts(v):
  return [int(x) for x in __import__('re').findall(r'\d+',v)]
 def cmp(a,b):
  x,y=vparts(a),vparts(b); n=max(len(x),len(y)); x+=([0]*(n-len(x))); y+=([0]*(n-len(y)))
  return (x>y)-(x<y)
 required=bool(current and cmp(current,minimum)<0)
 available=bool(current and cmp(current,latest)<0)
 return jsonify({
  'api_version':'v1',
  'latest_android_version':latest,
  'minimum_android_version':minimum,
  'update_required':required,
  'update_available':available,
  'maintenance':maintenance,
  'message':message,
  'download_url':download
 })

@app.get('/api/v1/status')
def android_status():
 return jsonify({'ok':True,'version':APP_VERSION,'api':'v1'})

@app.get('/api/v1/public/projects')
def api_v1_public_projects():
 c=db(); rows=c.execute("SELECT p.*,(SELECT COUNT(*) FROM trees t WHERE t.project_id=p.id AND t.active=1 AND t.approval_status='approved') tree_count FROM projects p WHERE p.active=1 ORDER BY p.id DESC").fetchall(); c.close()
 return jsonify(projects=[dict(id=x['id'],name=x['name'],location=x['location'] or '',status=x['status'] or '',target_trees=x['target_trees'] or 0,tree_count=x['tree_count'] or 0,start_date=x['start_date'] or '',end_date=x['end_date'] or '') for x in rows])

@app.get('/api/v1/public/events')
def api_v1_public_events():
 c=db()
 rows=c.execute("""SELECT e.id,e.title,e.event_type,e.status,e.start_at,e.end_at,e.description,
 p.name project_name,z.name zone_name,
 COALESCE(e.location,'') location
 FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id
 WHERE e.active=1 ORDER BY COALESCE(e.start_at,e.created_at) DESC""").fetchall()
 c.close()
 return jsonify(events=[dict(id=x['id'],title=x['title'] or '',event_type=x['event_type'] or '',status=x['status'] or '',
  start_at=x['start_at'] or '',end_at=x['end_at'] or '',description=x['description'] or '',location=x['location'] or '',
  project_name=x['project_name'] or '',zone_name=x['zone_name'] or '') for x in rows])

@app.get('/api/v1/public/trees/<int:tid>')
def api_v1_public_tree(tid):
 c=db(); t=c.execute("SELECT t.*,s.name_fr,s.name_ar,s.scientific_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.id=? AND t.active=1 AND t.approval_status='approved'",(tid,)).fetchone(); c.close()
 if not t:return api_error('not_found','Arbre introuvable.',404)
 return jsonify(tree=dict(id=t['id'],code=t['tree_code'] or '',name_fr=t['name_fr'] or '',name_ar=t['name_ar'] or '',scientific_name=t['scientific_name'] or '',planted_at=t['planted_at'] or '',project_name=t['project_name'] or '',zone_name=t['zone_name'] or '',health_status=t['health_status'] or '',last_watered_at=t['last_watered_at'] or '',latitude=t['latitude'],longitude=t['longitude']))

@app.post('/api/v1/public/register')
def api_v1_public_register():
 data=request.get_json(silent=True) or {}; first=(data.get('first_name') or '').strip(); last=(data.get('last_name') or '').strip(); phone=(data.get('phone') or '').strip(); email=(data.get('email') or '').strip(); sex=(data.get('sex') or 'Homme').strip(); password=data.get('password') or ''; confirm=data.get('password_confirm') or ''; address=(data.get('address') or '').strip(); wid=data.get('wilaya_id') or None; cid=data.get('commune_id') or None
 errors=[]
 if not first: errors.append('Le prénom est obligatoire.')
 if not last: errors.append('Le nom est obligatoire.')
 if not phone: errors.append('Le téléphone est obligatoire.')
 if len(password)<6: errors.append('Le mot de passe doit contenir au moins 6 caractères.')
 if password!=confirm: errors.append('Les mots de passe ne correspondent pas.')
 if errors:return api_error('validation',' '.join(errors),400)
 c=db(); exists=c.execute('SELECT id FROM users WHERE phone=? OR (email<>\'\' AND email=?) OR username=?',(phone,email,phone)).fetchone()
 if exists: c.close(); return api_error('duplicate','Ce téléphone ou cet e-mail est déjà utilisé.',409)
 role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone(); now=datetime.now().isoformat(timespec='minutes'); name=user_display_name(first,last)
 try:
  cur=c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,address,created_at,preferred_language) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(first,last,name,sex,phone,email,phone,generate_password_hash(password),role['id'] if role else None,'volunteer',1,wid,cid,address,now,(data.get('preferred_language') or 'fr'))); c.commit(); uid=cur.lastrowid
 finally: c.close()
 log_action('self_register','user',uid,'Inscription Android native')
 return jsonify(ok=True,user_id=uid,message='Compte bénévole créé. Vous pouvez vous connecter immédiatement.'),201

@app.get('/api/v1/version')
def api_v1_version():
 return jsonify({'ok':True,'version':'RC16.13-Web-Map-Tree-Visibility-Fix','association_public_detail':True,'association_join':True})

@app.get('/api/v1/public/home')
def android_public_home():
 c=db()
 tree_where="active=1 AND approval_status='approved'"
 if 'visibility' in columns(c,'trees'): tree_where+=" AND COALESCE(visibility,'public')='public'"
 trees=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where).fetchone()['n']
 projects=c.execute("SELECT COUNT(*) n FROM projects WHERE active=1").fetchone()['n']
 species=c.execute("SELECT COUNT(*) n FROM species WHERE active=1").fetchone()['n']
 events=c.execute("SELECT COUNT(*) n FROM events WHERE active=1").fetchone()['n']
 c.close()
 return jsonify({'home':{'tracked_trees':trees,'active_projects':projects,'species_count':species,'upcoming_events':events}})

@app.get('/api/v1/public/associations')
def android_public_associations():
 c=db(); rows=c.execute("SELECT a.id,a.code,a.name,a.short_name,a.description,a.map_symbol,w.name wilaya_name,cm.name commune_name FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id WHERE a.status='active' ORDER BY a.name").fetchall(); c.close()
 return jsonify({'associations':[dict(x) for x in rows]})

@app.get('/api/v1/public/associations/<int:aid>')
def android_public_association_detail(aid):
 c=db()
 a=c.execute("""SELECT a.id,a.code,a.name,a.short_name,a.description,a.map_symbol,a.status,a.address,a.phone,a.email,a.website,w.name wilaya_name,cm.name commune_name
 FROM associations a LEFT JOIN wilayas w ON w.id=a.wilaya_id LEFT JOIN communes cm ON cm.id=a.commune_id
 WHERE a.id=? AND a.status='active'""",(aid,)).fetchone()
 if not a: c.close(); return jsonify({'error':{'message':'Association introuvable.'}}),404
 d=dict(a)
 d['members']=c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n']
 d['trees']=c.execute("SELECT COUNT(*) n FROM trees WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 d['projects']=c.execute("SELECT COUNT(*) n FROM projects WHERE association_id=? AND active=1",(aid,)).fetchone()['n']
 d['membership_status']='none'
 token=request.headers.get('Authorization','')
 if token.startswith('Bearer '):
  uid=android_uid()
  if uid:
   m=c.execute("SELECT status FROM association_memberships WHERE association_id=? AND user_id=? ORDER BY id DESC LIMIT 1",(aid,uid)).fetchone()
   if m: d['membership_status']=m['status']
 c.close(); return jsonify({'association':d})

@app.post('/api/v1/associations/<int:aid>/join')
@android_auth
def android_join_association(aid):
 body=request.get_json(silent=True) or {}; member_kind=body.get('member_kind') if body.get('member_kind') in ('volunteer','member') else 'member'
 c=db(); a=c.execute("SELECT id,name FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); return jsonify({'error':{'message':'Association introuvable.'}}),404
 now=datetime.now().isoformat(timespec='minutes')
 existing=c.execute("SELECT * FROM association_memberships WHERE association_id=? AND user_id=? AND member_kind=?",(aid,request.android_uid,member_kind)).fetchone()
 if existing and existing['status']=='approved': c.close(); return jsonify({'ok':True,'message':'Vous êtes déjà adhérent de cette association.','status':'approved'})
 if existing: c.execute("UPDATE association_memberships SET status='pending',requested_at=?,reviewed_by_user_id=NULL,reviewed_at=NULL,rejection_reason=NULL WHERE id=?",(now,existing['id']))
 else: c.execute("INSERT INTO association_memberships(association_id,user_id,member_kind,role_code,status,requested_at) VALUES(?,?,?,?, 'pending',?)",(aid,request.android_uid,member_kind,('member' if member_kind=='member' else 'volunteer'),now))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Demande d’adhésion envoyée.','status':'pending'})

@app.get('/api/v1/public/map')
def android_public_map():
 c=db()
 w=["t.active=1","t.approval_status='approved'","t.latitude IS NOT NULL","t.longitude IS NOT NULL"]
 params=[]
 if 'visibility' in columns(c,'trees'): w.append("COALESCE(t.visibility,'public')='public'")
 # RC16.8: optional viewport filtering and hard safety limit for mobile clients.
 # Existing clients can still omit bbox; Android requests a bounded result size.
 try:
  min_lat=float(request.args.get('min_lat')) if request.args.get('min_lat') is not None else None
  max_lat=float(request.args.get('max_lat')) if request.args.get('max_lat') is not None else None
  min_lng=float(request.args.get('min_lng')) if request.args.get('min_lng') is not None else None
  max_lng=float(request.args.get('max_lng')) if request.args.get('max_lng') is not None else None
 except (TypeError,ValueError):
  min_lat=max_lat=min_lng=max_lng=None
 if None not in (min_lat,max_lat,min_lng,max_lng):
  w.extend(["t.latitude BETWEEN ? AND ?","t.longitude BETWEEN ? AND ?"]); params.extend([min_lat,max_lat,min_lng,max_lng])
 try: limit=max(100,min(int(request.args.get('limit','5000')),10000))
 except (TypeError,ValueError): limit=5000
 total=c.execute("SELECT COUNT(*) n FROM trees t WHERE "+' AND '.join(w),params).fetchone()['n']
 rows=c.execute("""SELECT t.id,t.tree_code,t.species,t.species_id,t.latitude,t.longitude,t.association_id,
 s.name_fr species_name,a.name association_name,a.map_symbol,u.name planter_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN associations a ON a.id=t.association_id
 LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE """+' AND '.join(w)+" ORDER BY t.id DESC LIMIT ?",params+[limit]).fetchall()
 trees=[dict(id=x['id'],code=x['tree_code'] or '',species=x['species'] or '',species_name=x['species_name'] or x['species'] or 'Arbre',
             lat=x['latitude'] if x['latitude'] is not None else 0.0,lng=x['longitude'] if x['longitude'] is not None else 0.0,symbol=(x['map_symbol'] or '🌳') if x['association_id'] else '🌳',
             association_id=x['association_id'],association_name=x['association_name'],planter_name=x['planter_name']) for x in rows]
 c.close(); return jsonify({'trees':trees,'zones':[],'events':[],'total':total,'returned':len(trees),'truncated':total>len(trees)})

@app.get('/api/v1/public/species')
def android_public_species():
 c=db()
 # RC16.8: aggregate tree counts once instead of executing one COUNT sub-query per species.
 rows=c.execute("""SELECT s.id,s.name_fr,s.name_ar,s.name_en,s.scientific_name,s.category,s.water_need,
 s.watering_frequency_days,s.description,COALESCE(tc.tree_count,0) tree_count
 FROM species s
 LEFT JOIN (SELECT species_id,COUNT(*) tree_count FROM trees
            WHERE active=1 AND approval_status='approved' GROUP BY species_id) tc ON tc.species_id=s.id
 WHERE s.active=1 ORDER BY s.name_fr COLLATE NOCASE""").fetchall()
 out=[dict(id=x['id'],name_fr=x['name_fr'] or '',name_ar=x['name_ar'] or '',name_en=x['name_en'] or '',
           scientific_name=x['scientific_name'] or '',category=x['category'] or '',water_need=x['water_need'] or '',
           watering_frequency_days=x['watering_frequency_days'],description=x['description'] or '',tree_count=x['tree_count']) for x in rows]
 c.close(); response=jsonify({'species':out}); response.headers['Cache-Control']='public, max-age=300'; return response


@app.get('/api/v1/public/geography')
def android_public_geography():
 c=db()
 wilayas=[dict(id=x['id'],code=x['code'] or '',name=x['name'] or '',name_ar=x['name_ar'] or '') for x in c.execute("SELECT id,code,name,name_ar FROM wilayas WHERE active=1 ORDER BY code").fetchall()]
 communes=[dict(id=x['id'],wilaya_id=x['wilaya_id'],name=x['name'] or '',name_ar=x['name_ar'] or '') for x in c.execute("SELECT id,wilaya_id,name,name_ar FROM communes WHERE active=1 ORDER BY name").fetchall()]
 species=[dict(id=x['id'],name=x['name_fr'] or '',name_fr=x['name_fr'] or '',name_ar=x['name_ar'] or '',name_en=x['name_en'] or '',scientific_name=x['scientific_name'] or '') for x in c.execute("SELECT id,name_fr,name_ar,name_en,scientific_name FROM species WHERE active=1 ORDER BY name_fr COLLATE NOCASE").fetchall()]
 c.close(); return jsonify({'wilayas':wilayas,'communes':communes,'species':species,'projects':[],'zones':[]})

@app.route('/association/dashboard')
def association_account_dashboard():
 aid=session.get('association_id') if session.get('account_type')=='association' else None
 if not aid: return redirect('/login?account_type=association')
 c=db(); a=c.execute("SELECT * FROM associations WHERE id=? AND status='active'",(aid,)).fetchone()
 if not a: c.close(); session.clear(); return redirect('/login?account_type=association')
 counts={'members':c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n'],'pending':c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='pending'",(aid,)).fetchone()['n'],'projects':c.execute("SELECT COUNT(*) n FROM projects WHERE association_id=? AND active=1",(aid,)).fetchone()['n'],'trees':c.execute("SELECT COUNT(*) n FROM trees WHERE association_id=? AND active=1",(aid,)).fetchone()['n']}; c.close()
 return page('Association',"""<div class='section-title'><div><h2>🏛 {{a.name}}</h2><p class='sub'>Espace Association · {{a.code}}</p></div></div><div class='grid kpis'><a class='card kpi' href='/membership-requests'><small>Membres</small><b>{{counts.members}}</b><span>{{counts.pending}} demande(s)</span></a><a class='card kpi' href='/projects'><small>Projets</small><b>{{counts.projects}}</b></a><a class='card kpi' href='/trees'><small>Arbres</small><b>{{counts.trees}}</b></a></div><div class='card'><h3>Gestion de l’association</h3><div class='action-set'><a class='btn' href='/membership-requests'>Adhérents & rôles</a><a class='btn' href='/donations'>Dons</a><a class='btn' href='/projects'>Projets</a><a class='btn' href='/zones'>Zones</a><a class='btn' href='/nursery'>Stock / Pépinière</a><a class='btn' href='/equipment'>Inventaire matériel</a><a class='btn' href='/reports/operations'>Finances & rapports</a><a class='btn alt' href='/public/associations/{{a.id}}'>Fiche publique</a></div></div>""",a=a,counts=counts)

@app.post('/api/v1/auth/association-login')
def android_association_login():
 body=request.get_json(silent=True) or {}; login_id=clean(body.get('login')); password=str(body.get('password') or ''); c=db()
 acc=c.execute("SELECT aa.*,a.name association_name FROM association_accounts aa JOIN associations a ON a.id=aa.association_id WHERE lower(aa.login_id)=lower(?) AND aa.active=1 AND a.status='active'",(login_id,)).fetchone()
 if not acc or not check_password_hash(acc['password_hash'],password): c.close(); return jsonify({'error':{'message':'ID Association ou mot de passe incorrect.'}}),401
 # association account receives a scoped token through its creator/admin user for API compatibility
 u=c.execute("SELECT u.* FROM users u JOIN association_memberships m ON m.user_id=u.id WHERE m.association_id=? AND m.status='approved' AND m.role_code IN ('association_admin','admin') ORDER BY m.id LIMIT 1",(acc['association_id'],)).fetchone()
 if not u: c.close(); return jsonify({'error':{'message':'Compte Association sans administrateur actif.'}}),403
 token=android_issue_token(u['id']); c.execute('UPDATE association_accounts SET last_login=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),acc['id'])); c.commit()
 payload={'token':token,'account_type':'association','association':{'id':acc['association_id'],'name':acc['association_name'],'login_id':acc['login_id']},'user':dict(id=u['id'],name=acc['association_name'],first_name='',last_name='',phone='',email='',photo_url='',preferred_language=u['preferred_language'] or 'fr'),'associations':android_assoc_payload(c,u['id'])}; c.close(); return jsonify(payload)

@app.post('/api/v1/auth/login')
def android_login():
 body=request.get_json(silent=True) or {}
 login=clean(body.get('login')); password=str(body.get('password') or '')
 c=db()
 u=c.execute("""SELECT * FROM users WHERE active=1 AND
 phone=? LIMIT 1""",(login,)).fetchone()
 if not u or not check_password_hash(u['password_hash'],password):
  c.close(); return jsonify({'error':{'message':'Numéro de téléphone ou mot de passe incorrect.'}}),401
 payload={'token':android_issue_token(u['id']),
          'user':dict(id=u['id'],name=u['name'] or '',first_name=u['first_name'] or '',last_name=u['last_name'] or '',
                      phone=u['phone'] or '',email=u['email'] or '',photo_url=u['photo_url'] or '',preferred_language=u['preferred_language'] or 'fr'),
          'associations':android_assoc_payload(c,u['id'])}
 c.close(); return jsonify(payload)

@app.get('/api/v1/auth/me')
@android_auth
def android_me():
 c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(request.android_uid,)).fetchone()
 out={'user':dict(id=u['id'],name=u['name'] or '',first_name=u['first_name'] or '',last_name=u['last_name'] or '',
                  phone=u['phone'] or '',email=u['email'] or '',photo_url=u['photo_url'] or '',preferred_language=u['preferred_language'] or 'fr')}
 c.close(); return jsonify(out)


@app.put('/api/v1/auth/me')
@android_auth
def android_update_me():
 body=request.get_json(silent=True) or {}
 first=clean(body.get('first_name')); last=clean(body.get('last_name')); phone=clean(body.get('phone')); email=clean(body.get('email')).lower(); lang=clean(body.get('preferred_language')) or 'fr'
 if lang not in ('fr','ar','en'): lang='fr'
 name=(first+' '+last).strip()
 c=db()
 if email:
  duplicate=c.execute("SELECT id FROM users WHERE lower(COALESCE(email,''))=lower(?) AND id<>?",(email,request.android_uid)).fetchone()
  if duplicate: c.close(); return jsonify({'error':{'message':'Cette adresse e-mail est déjà utilisée.'}}),409
 if phone:
  duplicate=c.execute("SELECT id FROM users WHERE phone=? AND id<>?",(phone,request.android_uid)).fetchone()
  if duplicate: c.close(); return jsonify({'error':{'message':'Ce numéro de téléphone est déjà utilisé.'}}),409
 photo_url=None
 current=c.execute("SELECT photo_url FROM users WHERE id=?",(request.android_uid,)).fetchone(); photo_url=(current['photo_url'] if current else '') or ''
 if body.get('remove_photo'): photo_url=''
 raw_photo=str(body.get('photo_base64') or '')
 if raw_photo:
  try:
   photo_data=base64.b64decode(raw_photo,validate=True)
   if len(photo_data)>8*1024*1024: c.close(); return jsonify({'error':{'message':'La photo dépasse 8 Mo.'}}),400
   folder=os.path.join(DATA_DIR,'uploads','profiles'); os.makedirs(folder,exist_ok=True)
   filename='profile-'+str(request.android_uid)+'-'+secrets.token_hex(6)+'.jpg'
   with open(os.path.join(folder,filename),'wb') as f: f.write(photo_data)
   photo_url='/uploads/profiles/'+filename
  except Exception: c.close(); return jsonify({'error':{'message':'Photo invalide.'}}),400
 c.execute("UPDATE users SET first_name=?,last_name=?,name=?,phone=?,email=?,preferred_language=?,photo_url=? WHERE id=?",(first,last,name or first or last,phone,email,lang,photo_url,request.android_uid)); c.commit()
 u=c.execute("SELECT * FROM users WHERE id=?",(request.android_uid,)).fetchone(); c.close()
 return jsonify({'ok':True,'message':'Profil mis à jour.','user':dict(id=u['id'],name=u['name'] or '',first_name=u['first_name'] or '',last_name=u['last_name'] or '',phone=u['phone'] or '',email=u['email'] or '',photo_url=u['photo_url'] or '',preferred_language=u['preferred_language'] or 'fr')})

@app.post('/api/v1/auth/password')
@android_auth
def android_change_password():
 body=request.get_json(silent=True) or {}; current=str(body.get('current_password') or ''); new=str(body.get('new_password') or ''); confirm=str(body.get('password_confirm') or '')
 c=db(); u=c.execute('SELECT password_hash FROM users WHERE id=?',(request.android_uid,)).fetchone()
 if not u or not check_password_hash(u['password_hash'],current): c.close(); return jsonify({'error':{'message':'Mot de passe actuel incorrect.'}}),400
 if len(new)<6: c.close(); return jsonify({'error':{'message':'Le nouveau mot de passe doit contenir au moins 6 caractères.'}}),400
 if new!=confirm: c.close(); return jsonify({'error':{'message':'La confirmation du nouveau mot de passe ne correspond pas.'}}),400
 c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),request.android_uid)); c.commit(); c.close()
 return jsonify({'ok':True,'message':'Mot de passe modifié.'})

@app.post('/api/v1/auth/logout')
@android_auth
def android_logout():
 return jsonify({'ok':True})

@app.get('/api/v1/associations')
@android_auth
def android_associations():
 c=db(); rows=android_assoc_payload(c,request.android_uid); c.close()
 return jsonify({'associations':rows})

@app.post('/api/v1/context/association')
@android_auth
def android_context():
 body=request.get_json(silent=True) or {}; raw=body.get('association_id'); aid=None
 c=db()
 if raw not in (None,'',False):
  try: wanted=int(raw)
  except (TypeError,ValueError): wanted=0
  if wanted:
   u=c.execute("SELECT role FROM users WHERE id=?",(request.android_uid,)).fetchone()
   if u and u['role']=='super_admin': aid=wanted
   elif c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(wanted,request.android_uid)).fetchone(): aid=wanted
 ctx=android_context_payload(c,request.android_uid,aid); c.close()
 return jsonify({'context':ctx})

@app.get('/api/v1/home')
@android_auth
def android_home():
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid); global_scope=request.args.get('scope')=='global'
 if global_scope:
  tree_where="active=1"; tree_args=()
  tree_n=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where).fetchone()['n']
  proj_n=c.execute("SELECT COUNT(*) n FROM projects WHERE active=1").fetchone()['n']
  zone_n=c.execute("SELECT COUNT(*) n FROM zones WHERE active=1").fetchone()['n']
  miss_n=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1").fetchone()['n']
  volunteers=c.execute("SELECT COUNT(*) n FROM users WHERE active=1 AND role<>'association_account'").fetchone()['n']
 elif aid:
  tree_where="active=1 AND association_id=?"; tree_args=(aid,)
  tree_n=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where,tree_args).fetchone()['n']
  proj_n=c.execute("SELECT COUNT(*) n FROM projects WHERE active=1 AND association_id=?",(aid,)).fetchone()['n']
  zone_n=c.execute("SELECT COUNT(*) n FROM zones WHERE active=1 AND association_id=?",(aid,)).fetchone()['n'] if 'association_id' in columns(c,'zones') else 0
  miss_n=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND association_id=?",(aid,)).fetchone()['n'] if 'association_id' in columns(c,'missions') else 0
  volunteers=c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n']
 else:
  tree_where="active=1 AND planted_by_user_id=?"; tree_args=(uid,)
  tree_n=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where,tree_args).fetchone()['n']
  proj_n=zone_n=miss_n=0; volunteers=0
 to_water=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where+" AND COALESCE(watering_status,'')<>'À jour'",tree_args).fetchone()['n']
 to_watch=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where+" AND COALESCE(health_status,'Bon')<>'Bon'",tree_args).fetchone()['n']
 healthy=c.execute("SELECT COUNT(*) n FROM trees WHERE "+tree_where+" AND COALESCE(health_status,'Bon')='Bon'",tree_args).fetchone()['n']
 species_n=c.execute("SELECT COUNT(DISTINCT COALESCE(species_id,species)) n FROM trees WHERE "+tree_where,tree_args).fetchone()['n']
 if global_scope:
  intervention_n=c.execute("SELECT COUNT(*) n FROM interventions i JOIN trees t ON t.id=i.tree_id WHERE t.active=1 AND i.status='Planifiée'").fetchone()['n']
 elif aid:
  intervention_n=c.execute("SELECT COUNT(*) n FROM interventions i JOIN trees t ON t.id=i.tree_id WHERE t.active=1 AND t.association_id=? AND i.status='Planifiée'",(aid,)).fetchone()['n']
 else:
  intervention_n=c.execute("SELECT COUNT(*) n FROM interventions i JOIN trees t ON t.id=i.tree_id WHERE t.active=1 AND t.planted_by_user_id=? AND i.status='Planifiée'",(uid,)).fetchone()['n']
 unread=c.execute("SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0",(uid,)).fetchone()['n']
 counts={'trees':tree_n,'projects':proj_n,'zones':zone_n,'missions':miss_n,'to_water':to_water,'to_watch':to_watch,'interventions_pending':intervention_n,'healthy_trees':healthy,'active_volunteers':volunteers,'species':species_n}
 c.close(); return jsonify({'home':{'unread_notifications':unread,'counts':counts}})

@app.get('/api/v1/map')
@android_auth
def android_map():
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid); mine=request.args.get('mine')=='1'; for_list=request.args.get('list')=='1'; kpi=clean(request.args.get('kpi')).lower()
 w=["t.active=1","t.approval_status='approved'"]; args=[]
 if not for_list: w += ["t.latitude IS NOT NULL","t.longitude IS NOT NULL"]
 if mine:
  if aid: w.append("t.association_id=?"); args.append(aid)
  else: w.append("t.planted_by_user_id=?"); args.append(uid)
 if kpi=='watering': w.append("(t.watering_status='À arroser' OR t.watering_status='A arroser')")
 elif kpi=='watch': w.append("t.health_status IN ('À surveiller','A surveiller','Malade','Critique')")
 elif kpi=='healthy': w.append("t.health_status IN ('Bonne santé','Bon','Sain')")
 rows=c.execute("""SELECT t.id,t.tree_code,t.species,t.species_id,t.latitude,t.longitude,t.association_id,
 s.name_fr species_name,a.name association_name,a.map_symbol,u.name planter_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN associations a ON a.id=t.association_id
 LEFT JOIN users u ON u.id=t.planted_by_user_id WHERE """+' AND '.join(w)+" ORDER BY t.id DESC",args).fetchall()
 trees=[dict(id=x['id'],code=x['tree_code'] or '',species=x['species'] or '',species_name=x['species_name'] or x['species'] or 'Arbre',
             lat=x['latitude'] if x['latitude'] is not None else 0.0,lng=x['longitude'] if x['longitude'] is not None else 0.0,symbol=(x['map_symbol'] or '🌳') if x['association_id'] else '🌳',
             association_id=x['association_id'],association_name=x['association_name'],planter_name=x['planter_name']) for x in rows]
 zones=[]; events=[]
 if request.args.get('zones')=='1':
  q="SELECT z.id,z.name,z.latitude lat,z.longitude lng FROM zones z WHERE z.active=1 AND z.latitude IS NOT NULL AND z.longitude IS NOT NULL"
  args2=[]
  if aid and 'association_id' in columns(c,'zones'): q+=' AND z.association_id=?'; args2=[aid]
  zones=[dict(x) for x in c.execute(q,args2).fetchall()]
 if request.args.get('events')=='1':
  q="SELECT e.id,e.title name,e.latitude lat,e.longitude lng FROM events e WHERE e.active=1 AND e.latitude IS NOT NULL AND e.longitude IS NOT NULL"
  args3=[]
  if aid and 'association_id' in columns(c,'events'): q+=' AND e.association_id=?'; args3=[aid]
  elif aid: q+=' AND (e.project_id IN (SELECT id FROM projects WHERE association_id=?))'; args3=[aid]
  events=[dict(x) for x in c.execute(q,args3).fetchall()]
 c.close(); return jsonify({'trees':trees,'zones':zones,'events':events})

@app.get('/api/v1/trees/<int:tid>')
@android_auth
def android_tree_detail(tid):
 c=db(); x=c.execute("""SELECT t.*,s.name_fr species_name,a.name association_name,p.name project_name,z.name zone_name,u.name planter_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN associations a ON a.id=t.association_id
 LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id
 WHERE t.id=? AND t.active=1""",(tid,)).fetchone()
 if not x: c.close(); return jsonify({'error':{'message':'Arbre introuvable'}}),404
 out={'id':x['id'],'code':x['tree_code'] or '','species':x['species_name'] or x['species'] or 'Arbre',
      'health_status':x['health_status'] or '','watering_status':x['watering_status'] or '',
      'planted_at':x['planted_at'] or '','planter_name':x['planter_name'] or x['planted_by'] or '',
      'association_name':x['association_name'],'project_name':x['project_name'],'zone_name':x['zone_name'],
      'latitude':x['latitude'],'longitude':x['longitude'],'approval_status':x['approval_status'] or '',
      'last_watered_at':x['last_watered_at'],'notes':x['notes']}
 c.close(); return jsonify({'tree':out})

@app.post('/api/v1/trees/<int:tid>/water')
@android_auth
def android_tree_water(tid):
 body=request.get_json(silent=True) or {}; c=db()
 t=c.execute("SELECT * FROM trees WHERE id=? AND active=1 AND approval_status='approved'",(tid,)).fetchone()
 if not t: c.close(); return jsonify({'error':{'message':'Arbre introuvable ou non validé'}}),404
 now=datetime.now().isoformat(timespec='minutes')
 qty=body.get('quantity_liters'); notes=clean(body.get('notes'))
 c.execute("""INSERT INTO watering_logs(tree_id,watered_at,user_id,quantity_liters,notes,latitude,longitude,created_at)
 VALUES(?,?,?,?,?,?,?,?)""",(tid,now,request.android_uid,qty,notes,body.get('latitude'),body.get('longitude'),now))
 c.execute("UPDATE trees SET last_watered_at=?,watering_status='À jour' WHERE id=?",(now,tid))
 c.commit(); c.close()
 return jsonify({'ok':True,'message':'Arrosage enregistré avec succès.'})

@app.get('/api/v1/scan')
@android_auth
def android_scan():
 code=clean(request.args.get('code')); c=db()
 x=c.execute("SELECT id,tree_code FROM trees WHERE active=1 AND (upper(tree_code)=upper(?) OR upper(qr_code)=upper(?))",(code,code)).fetchone()
 c.close()
 if not x: return jsonify({'error':{'message':'Aucun arbre trouvé pour ce QR/code'}}),404
 return jsonify({'tree':{'id':x['id'],'code':x['tree_code'] or ''}})

@app.post('/api/v1/plantings')
@android_auth
def android_create_planting():
 body=request.get_json(silent=True) or {}; c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid)
 species_id=body.get('species_id'); species=clean(body.get('species')); now=datetime.now().isoformat(timespec='minutes')
 wilaya_id=body.get('wilaya_id'); commune_id=body.get('commune_id'); planted_at=clean(body.get('planted_at')) or date.today().isoformat()
 if commune_id:
  cm=c.execute('SELECT id,wilaya_id FROM communes WHERE id=? AND active=1',(commune_id,)).fetchone()
  if not cm: c.close(); return jsonify({'error':{'message':'Commune invalide'}}),400
  if wilaya_id and int(cm['wilaya_id'])!=int(wilaya_id): c.close(); return jsonify({'error':{'message':'La commune ne correspond pas à la wilaya sélectionnée'}}),400
  wilaya_id=wilaya_id or cm['wilaya_id']
 if not species_id and not species:
  c.close(); return jsonify({'error':{'message':'Espèce obligatoire'}}),400
 if species_id:
  sp=c.execute("SELECT name_fr FROM species WHERE id=? AND active=1",(species_id,)).fetchone()
  if not sp: c.close(); return jsonify({'error':{'message':'Espèce invalide'}}),400
  species=sp['name_fr']
 project_id=body.get('project_id'); zone_id=body.get('zone_id')
 if zone_id:
  z=c.execute("SELECT id,project_id,target_trees FROM zones WHERE id=? AND active=1",(zone_id,)).fetchone()
  if not z: c.close(); return jsonify({'error':{'message':'Zone invalide'}}),400
  if project_id and int(z['project_id'])!=int(project_id): c.close(); return jsonify({'error':{'message':'La zone ne correspond pas au projet sélectionné'}}),400
  if z['target_trees']:
   n=c.execute("SELECT COUNT(*) n FROM trees WHERE zone_id=? AND active=1 AND approval_status IN ('pending','approved')",(zone_id,)).fetchone()['n']
   if n>=int(z['target_trees']): c.close(); return jsonify({'error':{'message':'Objectif maximal de la zone atteint'}}),409
 if project_id:
  pr=c.execute("SELECT id,target_trees,association_id FROM projects WHERE id=? AND active=1",(project_id,)).fetchone()
  if not pr: c.close(); return jsonify({'error':{'message':'Projet invalide'}}),400
  if aid and int(pr['association_id'] or 0)!=int(aid): c.close(); return jsonify({'error':{'message':'Projet hors du périmètre de l’association active'}}),403
  if pr['target_trees']:
   n=c.execute("SELECT COUNT(*) n FROM trees WHERE project_id=? AND active=1 AND approval_status IN ('pending','approved')",(project_id,)).fetchone()['n']
   if n>=int(pr['target_trees']): c.close(); return jsonify({'error':{'message':'Objectif maximal du projet atteint'}}),409
 cur=c.execute("""INSERT INTO trees(species_id,species,project_id,zone_id,wilaya_id,commune_id,planted_at,planted_by_user_id,planted_by,
 latitude,longitude,gps_accuracy,health_status,watering_status,approval_status,association_id,notes,active,created_at)
 VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'Bon','À jour','pending',?,?,1,?)""",
 (species_id,species,body.get('project_id'),body.get('zone_id'),wilaya_id,commune_id,planted_at,uid,
  c.execute("SELECT name FROM users WHERE id=?",(uid,)).fetchone()['name'],body.get('latitude'),body.get('longitude'),body.get('gps_accuracy'),aid,clean(body.get('notes')),now))
 tid=cur.lastrowid
 # Une plantation associative est visible dans la même file pending par les admins de l'association et le Super Admin.
 if aid:
  admins=c.execute("SELECT user_id FROM association_memberships WHERE association_id=? AND status='approved' AND role_code IN ('association_admin','admin')",(aid,)).fetchall()
  notify={int(x['user_id']) for x in admins}
 else: notify=set()
 notify.update(int(x['id']) for x in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall())
 for target in notify:
  if target==uid: continue
  c.execute("INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)",
            (target,'Plantation à valider','Une nouvelle plantation Android attend une validation.','/plantings/pending','Action requise','planting_review',tid,now))
 raw_photo=str(body.get('photo_base64') or '')
 if raw_photo:
  try:
   photo_data=base64.b64decode(raw_photo,validate=True)
   if len(photo_data)<=8*1024*1024:
    folder=os.path.join(DATA_DIR,'uploads','android'); os.makedirs(folder,exist_ok=True)
    name='tree-'+str(tid)+'-'+secrets.token_hex(8)+'.jpg'; path=os.path.join(folder,name)
    with open(path,'wb') as f: f.write(photo_data)
    c.execute("INSERT INTO tree_photos(tree_id,photo_url,caption,created_by_user_id,created_at) VALUES(?,?,?,?,?)",(tid,'uploads/android/'+name,clean(body.get('photo_caption')),uid,now))
  except Exception:
   pass
 c.commit(); c.close()
 return jsonify({'ok':True,'tree_id':tid,'status':'pending','message':'Plantation envoyée pour validation.'}),201


@app.get('/api/v1/donations/options')
@android_auth
def api_v1_donation_options():
 uid=request.android_uid; c=db(); aid=android_assoc_id(c,uid)
 species=c.execute("SELECT id,name_fr,name_ar FROM species WHERE active=1 ORDER BY name_fr").fetchall()
 assocs=c.execute("SELECT id,code,name,map_symbol FROM associations WHERE status='active' ORDER BY name").fetchall()
 projects=[]
 if aid:
  projects=c.execute("SELECT id,name FROM projects WHERE active=1 AND association_id=? ORDER BY name",(aid,)).fetchall()
 c.close()
 return jsonify(ok=True,association_id=aid,associations=[dict(id=x['id'],code=x['code'] or '',name=x['name'] or '',symbol=x['map_symbol'] or '🌿') for x in assocs],species=[dict(id=x['id'],name_fr=x['name_fr'] or '',name_ar=x['name_ar'] or '') for x in species],projects=[dict(id=x['id'],name=x['name']) for x in projects])

@app.post('/api/v1/donations')
@android_auth
def api_v1_create_donation():
 uid=request.android_uid; data=request.get_json(silent=True) or {}; c=db(); aid=int(data.get('association_id') or 0)
 target=c.execute("SELECT id FROM associations WHERE id=? AND status='active'",(aid,)).fetchone() if aid else None
 if not target: c.close(); return api_error('validation','Choisissez une association bénéficiaire.',400)
 amount=max(0,float(data.get('amount') or 0)); unknown_qty=max(0,int(data.get('unknown_tree_quantity') or 0)); lines=data.get('trees') or []
 valid=[]
 for line in lines:
  try: sid=int(line.get('species_id') or 0); qty=max(0,int(line.get('quantity') or 0))
  except (TypeError,ValueError): sid=0; qty=0
  if sid and qty:
   ok=c.execute("SELECT id FROM species WHERE id=? AND active=1",(sid,)).fetchone()
   if ok: valid.append((sid,qty))
 if amount<=0 and unknown_qty<=0 and not valid:
  c.close(); return api_error('validation','Ajoutez un montant ou au moins un arbre.',400)
 if 'association_id' not in columns(c,'donation_groups'):
  c.execute('ALTER TABLE donation_groups ADD COLUMN association_id INTEGER')
 receipt='PENDING-'+datetime.now().strftime('%Y%m%d-%H%M%S'); now=datetime.now().isoformat(timespec='minutes')
 c.execute('INSERT INTO donation_groups(status,receipt_number,received_at,created_by_user_id,created_at,association_id) VALUES(?,?,?,?,?,?)',('En attente',receipt,date.today().isoformat(),uid,now,aid)); gid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
 if amount>0: _add_donation_line(c,gid,None,'En attente',receipt,'Argent',amount=amount)
 for sid,qty in valid: _add_donation_line(c,gid,None,'En attente',receipt,'Arbres',qty=qty,species_id=sid)
 if unknown_qty>0:
  c.execute('INSERT INTO donations(group_id,donor_id,donation_type,status,amount,currency,quantity,unit,description,received_at,estimated_value,species_id,equipment_id,receipt_number,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(gid,None,'Arbres','En attente',0,'DZD',unknown_qty,'arbre(s)','Espèce non précisée',date.today().isoformat(),0,None,None,receipt,uid,now))
 donor=c.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone(); donor_name=(donor['name'] if donor else 'Un bénévole')
 notify_admins_in_tx(c,'Nouveau don à valider',donor_name+' a déclaré un don ('+receipt+').','/donations?status=pending','Don','donation_group',gid)
 c.commit(); c.close(); log_action('create','donation_group',gid,'Don Android natif '+receipt)
 return jsonify(ok=True,group_id=gid,receipt=receipt,status='En attente',message='Don envoyé'),201

@app.get('/api/v1/field-options')
@android_auth
def android_field_options():
 c=db(); aid=android_assoc_id(c,request.android_uid)
 wilayas=[dict(id=x['id'],code=x['code'] or '',name=x['name'] or '',name_ar=x['name_ar'] or '') for x in c.execute("SELECT id,code,name,name_ar FROM wilayas WHERE active=1 ORDER BY code").fetchall()]
 communes=[dict(id=x['id'],wilaya_id=x['wilaya_id'],name=x['name'] or '',name_ar=x['name_ar'] or '') for x in c.execute("SELECT id,wilaya_id,name,name_ar FROM communes WHERE active=1 ORDER BY name").fetchall()]
 species=[dict(id=x['id'],name=x['name_fr'] or '',name_ar=x['name_ar'] or '',name_en=x['name_en'] or '',scientific_name=x['scientific_name'] or '') for x in c.execute("SELECT id,name_fr,name_ar,name_en,scientific_name FROM species WHERE active=1 ORDER BY name_fr").fetchall()]
 if aid:
  rows=c.execute("SELECT id,name,wilaya_id,commune_id FROM projects WHERE active=1 AND association_id=? ORDER BY name",(aid,)).fetchall()
 else:
  rows=c.execute("SELECT id,name,wilaya_id,commune_id FROM projects WHERE active=1 AND (association_id IS NULL OR association_id=0) ORDER BY name").fetchall()
 projects=[dict(id=x['id'],name=x['name'],wilaya_id=x['wilaya_id'],commune_id=x['commune_id']) for x in rows]
 pids=[x['id'] for x in projects]; zones=[]
 if pids:
  marks=','.join('?'*len(pids))
  zones=[dict(id=x['id'],project_id=x['project_id'],name=x['name'],wilaya_id=x['wilaya_id'],commune_id=x['commune_id']) for x in c.execute(f"SELECT id,project_id,name,wilaya_id,commune_id FROM zones WHERE active=1 AND project_id IN ({marks}) ORDER BY name",pids).fetchall()]
 c.close(); return jsonify({'wilayas':wilayas,'communes':communes,'species':species,'projects':projects,'zones':zones})

@app.get('/api/v1/trees/<int:tid>/history')
@android_auth
def android_tree_history(tid):
 c=db(); items=[]
 t=c.execute("SELECT id,planted_at,planted_by,approval_status,approved_at,rejection_reason FROM trees WHERE id=? AND active=1",(tid,)).fetchone()
 if not t: c.close(); return jsonify({'error':{'message':'Arbre introuvable'}}),404
 items.append({'type':'planting','date':t['planted_at'] or '','title':'Plantation','details':(t['planted_by'] or '')+' · '+(t['approval_status'] or '')})
 for x in c.execute("SELECT watered_at,quantity_liters,notes FROM watering_logs WHERE tree_id=? ORDER BY id DESC",(tid,)).fetchall():
  q=(str(x['quantity_liters'])+' L') if x['quantity_liters'] is not None else ''
  items.append({'type':'watering','date':x['watered_at'] or '','title':'Arrosage','details':' · '.join(v for v in [q,x['notes'] or ''] if v)})
 for x in c.execute("SELECT performed_at,intervention_type,notes FROM interventions WHERE tree_id=? ORDER BY id DESC",(tid,)).fetchall():
  items.append({'type':'intervention','date':x['performed_at'] or '','title':x['intervention_type'] or 'Intervention','details':x['notes'] or ''})
 for x in c.execute("SELECT created_at,caption FROM tree_photos WHERE tree_id=? ORDER BY id DESC",(tid,)).fetchall():
  items.append({'type':'photo','date':x['created_at'] or '','title':'Photo terrain','details':x['caption'] or ''})
 items.sort(key=lambda x:x.get('date') or '',reverse=True)
 c.close(); return jsonify({'items':items})

@app.post('/api/v1/trees/<int:tid>/interventions')
@android_auth
def android_tree_intervention(tid):
 body=request.get_json(silent=True) or {}; typ=clean(body.get('intervention_type')); notes=clean(body.get('notes'))
 if not typ: return jsonify({'error':{'message':'Type d’intervention obligatoire'}}),400
 c=db(); t=c.execute("SELECT id FROM trees WHERE id=? AND active=1 AND approval_status='approved'",(tid,)).fetchone()
 if not t: c.close(); return jsonify({'error':{'message':'Arbre introuvable ou non validé'}}),404
 now=datetime.now().isoformat(timespec='minutes')
 c.execute("""INSERT INTO interventions(tree_id,user_id,intervention_type,status,performed_at,notes,created_at)
 VALUES(?,?,?,'Réalisée',?,?,?)""",(tid,request.android_uid,typ,now,notes,now))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Intervention enregistrée avec succès.'})

@app.post('/api/v1/trees/<int:tid>/photos')
@android_auth
def android_tree_photo(tid):
 body=request.get_json(silent=True) or {}; raw=str(body.get('image_base64') or ''); caption=clean(body.get('caption'))
 if not raw: return jsonify({'error':{'message':'Photo obligatoire'}}),400
 try:
  data=base64.b64decode(raw,validate=True)
 except Exception:
  return jsonify({'error':{'message':'Photo invalide'}}),400
 if len(data)>8*1024*1024: return jsonify({'error':{'message':'Photo trop volumineuse (8 Mo maximum)'}}),413
 c=db(); t=c.execute("SELECT id FROM trees WHERE id=? AND active=1",(tid,)).fetchone()
 if not t: c.close(); return jsonify({'error':{'message':'Arbre introuvable'}}),404
 folder=os.path.join(DATA_DIR,'uploads','android'); os.makedirs(folder,exist_ok=True)
 name='tree-'+str(tid)+'-'+secrets.token_hex(8)+'.jpg'; path=os.path.join(folder,name)
 with open(path,'wb') as f: f.write(data)
 rel='uploads/android/'+name; now=datetime.now().isoformat(timespec='minutes')
 c.execute("INSERT INTO tree_photos(tree_id,photo_url,caption,created_by_user_id,created_at) VALUES(?,?,?,?,?)",(tid,rel,caption,request.android_uid,now))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Photo terrain enregistrée.','photo_url':'/api/v1/media/'+name}),201

@app.get('/api/v1/media/<path:name>')
@android_auth
def android_media(name):
 safe=os.path.basename(name); path=os.path.join(DATA_DIR,'uploads','android',safe)
 if not os.path.isfile(path): return jsonify({'error':{'message':'Fichier introuvable'}}),404
 return send_file(path,mimetype='image/jpeg')


@app.get('/api/v1/notifications')
@android_auth
def android_notifications():
 c=db()
 rows=c.execute("""SELECT id,title,message,category,action_type,action_id,is_read,created_at
 FROM notifications WHERE user_id=? OR user_id IS NULL ORDER BY is_read ASC,id DESC LIMIT 100""",(request.android_uid,)).fetchall()
 out=[dict(id=x['id'],title=x['title'] or '',message=x['message'] or '',category=x['category'] or '',
           action_type=x['action_type'],action_id=x['action_id'],is_read=bool(x['is_read']),created_at=x['created_at'] or '') for x in rows]
 c.close(); return jsonify({'notifications':out})

@app.post('/api/v1/notifications/<int:nid>/read')
@android_auth
def android_notification_read(nid):
 c=db()
 n=c.execute("SELECT id FROM notifications WHERE id=? AND (user_id=? OR user_id IS NULL)",(nid,request.android_uid)).fetchone()
 if not n: c.close(); return jsonify({'error':{'message':'Notification introuvable'}}),404
 c.execute("UPDATE notifications SET is_read=1 WHERE id=?",(nid,)); c.commit(); c.close()
 return jsonify({'ok':True})

@app.post('/api/v1/offline-operations/<op_type>')
@android_auth
def android_offline_operation(op_type):
 body=request.get_json(silent=True) or {}; key=clean(body.get('idempotency_key'))
 if not key: return jsonify({'error':{'message':'Clé idempotente obligatoire'}}),400
 c=db()
 c.execute("""CREATE TABLE IF NOT EXISTS android_operation_keys(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL,
  operation_type TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,idempotency_key)
 )""")
 already=c.execute("SELECT id FROM android_operation_keys WHERE user_id=? AND idempotency_key=?",(request.android_uid,key)).fetchone()
 if already: c.close(); return jsonify({'ok':True,'duplicate':True,'message':'Opération déjà synchronisée.'})
 if op_type=='intervention':
  tid=int(body.get('tree_id') or 0); typ=clean(body.get('intervention_type')); notes=clean(body.get('notes'))
  t=c.execute("SELECT id FROM trees WHERE id=? AND active=1 AND approval_status='approved'",(tid,)).fetchone()
  if not t or not typ: c.close(); return jsonify({'error':{'message':'Intervention hors ligne invalide'}}),400
  now=datetime.now().isoformat(timespec='minutes')
  c.execute("""INSERT INTO interventions(tree_id,user_id,intervention_type,status,performed_at,notes,created_at)
  VALUES(?,?,?,'Réalisée',?,?,?)""",(tid,request.android_uid,typ,now,notes,now))
 else:
  c.close(); return jsonify({'error':{'message':'Type d’opération hors ligne non pris en charge'}}),400
 c.execute("INSERT INTO android_operation_keys(user_id,idempotency_key,operation_type,created_at) VALUES(?,?,?,?)",
           (request.android_uid,key,op_type,datetime.now().isoformat(timespec='minutes')))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Opération synchronisée.'})


# Android Lot 8 — Associations: mêmes données/rôles que MyTree Web.
@app.get('/api/v1/associations/<int:aid>')
@android_auth
def android_association_details(aid):
 c=db(); uid=request.android_uid
 a=c.execute("SELECT * FROM associations WHERE id=?",(aid,)).fetchone()
 if not a: c.close(); return jsonify({'error':{'message':'Association introuvable'}}),404
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 m=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
 role='super_admin' if u and u['role']=='super_admin' else (m['role_code'] if m else '')
 if not role: c.close(); return jsonify({'error':{'message':'Accès refusé'}}),403
 counts={
  'members':c.execute("SELECT COUNT(*) n FROM association_memberships WHERE association_id=? AND status='approved'",(aid,)).fetchone()['n'],
  'trees':c.execute("SELECT COUNT(*) n FROM trees WHERE association_id=? AND active=1",(aid,)).fetchone()['n'],
  'projects':c.execute("SELECT COUNT(*) n FROM projects WHERE association_id=? AND active=1",(aid,)).fetchone()['n']}
 out={'id':a['id'],'name':a['name'],'code':a['code'],'short_name':a['short_name'] or '',
      'description':a['description'] or '','symbol':a['map_symbol'] or '🌿','status':a['status'],
      **counts,'my_role':role,'can_edit':role in ('super_admin','association_admin','admin'),
      'can_archive':role in ('super_admin','association_admin','admin')}
 c.close(); return jsonify({'association':out})

@app.get('/api/v1/associations/<int:aid>/members')
@android_auth
def android_association_members(aid):
 c=db(); uid=request.android_uid
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 mine=c.execute("SELECT 1 FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
 if not (mine or (u and u['role']=='super_admin')): c.close(); return jsonify({'error':{'message':'Accès refusé'}}),403
 rows=c.execute("""SELECT m.user_id,u.name,m.role_code,m.status FROM association_memberships m
 JOIN users u ON u.id=m.user_id WHERE m.association_id=? ORDER BY m.status,u.name""",(aid,)).fetchall()
 c.close(); return jsonify({'members':[dict(x) for x in rows]})

@app.post('/api/v1/associations/<int:aid>')
@android_auth
def android_association_update(aid):
 body=request.get_json(silent=True) or {}; c=db(); uid=request.android_uid
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 m=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
 role='super_admin' if u and u['role']=='super_admin' else (m['role_code'] if m else '')
 if role not in ('super_admin','association_admin','admin'): c.close(); return jsonify({'error':{'message':'Permission insuffisante'}}),403
 name=clean(body.get('name')); desc=clean(body.get('description')); symbol=clean(body.get('map_symbol'))
 if not name: c.close(); return jsonify({'error':{'message':'Nom obligatoire'}}),400
 if symbol:
  used=c.execute("SELECT id FROM associations WHERE map_symbol=? AND id<>? AND status='active'",(symbol,aid)).fetchone()
  if used: c.close(); return jsonify({'error':{'message':'Ce symbole est déjà utilisé par une autre association'}}),409
 c.execute("UPDATE associations SET name=?,description=?,map_symbol=? WHERE id=?",(name,desc,symbol or '🌿',aid)); c.commit(); c.close()
 return jsonify({'ok':True,'message':'Association modifiée.'})

@app.get('/api/v1/associations/<int:aid>/symbols')
@android_auth
def android_association_symbols(aid):
 symbols=['🌳','🌲','🌴','🌿','🍃','🌱','🪴','🌵','🍀','🌾','🫒','🌺']
 c=db(); used={x['map_symbol'] for x in c.execute("SELECT map_symbol FROM associations WHERE status='active' AND id<>? AND map_symbol IS NOT NULL",(aid,)).fetchall()}
 c.close(); return jsonify({'symbols':[{'symbol':x,'available':x not in used} for x in symbols]})

@app.post('/api/v1/associations/<int:aid>/archive-request')
@android_auth
def android_association_archive_request(aid):
 c=db(); uid=request.android_uid
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 if u and u['role']=='super_admin':
  c.execute("UPDATE associations SET status='archived',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec='minutes'),aid)); c.execute("UPDATE association_accounts SET active=0 WHERE association_id=?",(aid,))
  c.execute("UPDATE association_archive_requests SET status='approved',reviewed_by_user_id=?,reviewed_at=? WHERE association_id=? AND status='pending'",
            (uid,datetime.now().isoformat(timespec='minutes'),aid))
  c.commit(); c.close()
  return jsonify({'ok':True,'message':'Association archivée.'})
 m=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
 if not m or m['role_code'] not in ('association_admin','admin'): c.close(); return jsonify({'error':{'message':'Permission insuffisante'}}),403
 existing=c.execute("SELECT id FROM association_archive_requests WHERE association_id=? AND status='pending'",(aid,)).fetchone()
 if existing: c.close(); return jsonify({'ok':True,'message':'Une demande d’archivage est déjà en attente.'})
 now=datetime.now().isoformat(timespec='minutes')
 c.execute("INSERT INTO association_archive_requests(association_id,requested_by_user_id,status,reason,requested_at) VALUES(?,?,'pending','Demande depuis Android',?)",(aid,uid,now))
 for x in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall():
  c.execute("INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)",
   (x['id'],'Demande d’archivage association','Un administrateur demande l’archivage de son association.','/admin/association-archive-requests','Action requise','association_archive',aid,now))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Demande d’archivage envoyée au Super Admin.'})

# Android Lot 9 — Projets, Zones, Événements, Équipes & Missions
@app.get('/api/v1/operations')
@android_auth
def android_operations():
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid)
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 super_admin=bool(u and u['role']=='super_admin')

 def scope_sql(table_alias,project_alias=None):
  if super_admin and not aid: return ('1=1',[])
  if aid:
   col=table_alias+'.association_id' if 'association_id' in columns(c,table_alias.split('.')[-1]) else None
   if col: return (col+'=?',[aid])
   if project_alias: return (project_alias+'.association_id=?',[aid])
   return ('1=1',[])
  return ('1=0',[])

 # Projects are the primary association scope.
 pw,pp=("1=1",[]) if super_admin and not aid else (("p.association_id=?",[aid]) if aid else ("1=0",[]))
 projects=c.execute("""SELECT p.id,p.code,p.name,p.status,p.target_trees FROM projects p
 WHERE p.active=1 AND """+pw+" ORDER BY p.name",pp).fetchall()

 pids=[x['id'] for x in projects]
 if pids:
  marks=','.join('?'*len(pids))
  zones=c.execute(f"SELECT id,project_id,code,name,target_trees FROM zones WHERE active=1 AND project_id IN ({marks}) ORDER BY name",pids).fetchall()
  events=c.execute(f"""SELECT e.id,e.title,e.event_type,e.status,e.start_at,p.name project_name,z.name zone_name
   FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id
   WHERE e.active=1 AND (e.project_id IN ({marks}) OR e.project_id IS NULL) ORDER BY e.start_at DESC""",pids).fetchall()
  teams=c.execute(f"""SELECT t.id,t.code,t.name,u.name leader_name,p.name project_name,
   (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.status='active') member_count
   FROM teams t LEFT JOIN users u ON u.id=t.leader_user_id LEFT JOIN projects p ON p.id=t.project_id
   WHERE t.active=1 AND (t.project_id IN ({marks}) OR t.project_id IS NULL) ORDER BY t.name""",pids).fetchall()
  missions=c.execute(f"""SELECT m.id,m.code,m.title,m.mission_type,m.status,m.priority,m.start_at,m.target_count,m.completed_count,
   p.name project_name,z.name zone_name,t.name team_name
   FROM missions m LEFT JOIN projects p ON p.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id
   WHERE m.active=1 AND (m.project_id IN ({marks}) OR m.project_id IS NULL) ORDER BY COALESCE(m.start_at,m.created_at) DESC""",pids).fetchall()
 else:
  zones=[];events=[];teams=[];missions=[]
 c.close()
 return jsonify({
  'projects':[dict(x) for x in projects],
  'zones':[dict(x) for x in zones],
  'events':[dict(x) for x in events],
  'teams':[dict(x) for x in teams],
  'missions':[dict(x) for x in missions]
 })

@app.post('/api/v1/missions/<int:mid>/status')
@android_auth
def android_mission_status(mid):
 body=request.get_json(silent=True) or {}; status=clean(body.get('status'))
 allowed={'Planifiée','En cours','Terminée','Annulée'}
 if status not in allowed: return jsonify({'error':{'message':'Statut de mission invalide'}}),400
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid)
 m=c.execute("SELECT * FROM missions WHERE id=? AND active=1",(mid,)).fetchone()
 if not m: c.close(); return jsonify({'error':{'message':'Mission introuvable'}}),404
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 if u and u['role']=='super_admin': permitted=True
 elif aid:
  mem=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
  project=c.execute("SELECT association_id FROM projects WHERE id=?",(m['project_id'],)).fetchone() if m['project_id'] else None
  permitted=bool(mem and mem['role_code'] in ('association_admin','admin') and (not project or int(project['association_id'] or 0)==int(aid)))
 else: permitted=False
 if not permitted: c.close(); return jsonify({'error':{'message':'Permission insuffisante'}}),403
 c.execute("UPDATE missions SET status=?,updated_at=? WHERE id=?",(status,datetime.now().isoformat(timespec='minutes'),mid))
 c.commit(); c.close(); return jsonify({'ok':True,'message':'Statut de la mission mis à jour.'})


# Android Lot 10 — Plantations & validations complètes
@app.get('/api/v1/plantings/pending')
@android_auth
def android_pending_plantings():
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid)
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 super_admin=bool(u and u['role']=='super_admin')
 if super_admin and not aid:
  where="t.approval_status='pending'"; params=[]
 elif aid:
  mem=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
  if not mem or mem['role_code'] not in ('association_admin','admin'):
   c.close(); return jsonify({'error':{'message':'Permission insuffisante'}}),403
  where="t.approval_status='pending' AND t.association_id=?"; params=[aid]
 else:
  c.close(); return jsonify({'items':[]})
 rows=c.execute("""SELECT t.id,t.species,t.planted_by,t.planted_at,t.approval_status,t.notes,t.latitude,t.longitude,
 a.name association_name,p.name project_name,z.name zone_name
 FROM trees t LEFT JOIN associations a ON a.id=t.association_id
 LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id
 WHERE t.active=1 AND """+where+" ORDER BY t.id DESC",params).fetchall()
 c.close()
 return jsonify({'items':[dict(id=x['id'],species=x['species'] or '',planter=x['planted_by'] or '',
 association_name=x['association_name'],project_name=x['project_name'],zone_name=x['zone_name'],
 planted_at=x['planted_at'] or '',status=x['approval_status'],notes=x['notes'] or '',
 latitude=x['latitude'],longitude=x['longitude']) for x in rows]})

@app.post('/api/v1/plantings/<int:tid>/review')
@android_auth
def android_review_planting(tid):
 body=request.get_json(silent=True) or {}; decision=clean(body.get('decision')).lower(); reason=clean(body.get('reason'))
 if decision not in ('approve','reject'): return jsonify({'error':{'message':'Décision invalide'}}),400
 if decision=='reject' and not reason: return jsonify({'error':{'message':'Motif du refus obligatoire'}}),400
 c=db(); uid=request.android_uid; aid=android_assoc_id(c,uid)
 t=c.execute("SELECT * FROM trees WHERE id=? AND active=1",(tid,)).fetchone()
 if not t: c.close(); return jsonify({'error':{'message':'Plantation introuvable'}}),404
 if t['approval_status']!='pending':
  c.close(); return jsonify({'error':{'message':'Cette plantation a déjà été traitée'}}),409
 u=c.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
 super_admin=bool(u and u['role']=='super_admin')
 permitted=super_admin
 if not permitted and aid and t['association_id'] and int(t['association_id'])==int(aid):
  mem=c.execute("SELECT role_code FROM association_memberships WHERE association_id=? AND user_id=? AND status='approved'",(aid,uid)).fetchone()
  permitted=bool(mem and mem['role_code'] in ('association_admin','admin'))
 if not permitted: c.close(); return jsonify({'error':{'message':'Permission insuffisante'}}),403

 now=datetime.now().isoformat(timespec='minutes')
 status='approved' if decision=='approve' else 'rejected'
 c.execute("UPDATE trees SET approval_status=?,approved_by_user_id=?,approved_at=?,rejection_reason=? WHERE id=?",
           (status,uid,now,None if decision=='approve' else reason,tid))
 c.execute("INSERT INTO planting_reviews(tree_id,reviewer_user_id,decision,reason,created_at) VALUES(?,?,?,?,?)",
           (tid,uid,decision,reason,now))

 # Une seule décision centrale : toutes les notifications de validation liées à cet arbre sont traitées.
 c.execute("""UPDATE notifications SET is_read=1,decision=?,processed_at=?,read_at=COALESCE(read_at,?)
 WHERE action_type='planting_review' AND action_id=?""",(decision,now,now,tid))

 planter=t['planted_by_user_id']
 if planter:
  title='Plantation acceptée' if decision=='approve' else 'Plantation refusée'
  msg='Votre plantation a été validée.' if decision=='approve' else ('Votre plantation a été refusée : '+reason)
  c.execute("""INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at)
   VALUES(?,?,?,?,?,?,?,0,?)""",(planter,title,msg,'/trees/'+str(tid),'Plantation','tree',tid,now))
 c.commit(); c.close()
 return jsonify({'ok':True,'status':status,'message':'Plantation acceptée.' if decision=='approve' else 'Plantation refusée.'})


# Android Lot 11 — Administration centrale
def require_android_super_admin(c):
 u=c.execute("SELECT role FROM users WHERE id=?",(request.android_uid,)).fetchone()
 return bool(u and u['role']=='super_admin')

@app.get('/api/v1/admin/volunteers')
@android_auth
def android_admin_volunteers():
 c=db()
 if not require_android_super_admin(c): c.close(); return jsonify({'error':{'message':'Accès Super Admin requis'}}),403
 q=clean(request.args.get('q')).lower()
 where="u.active=1 AND u.role<>'super_admin'"; params=[]
 if q:
  where+=" AND (LOWER(COALESCE(u.name,'')) LIKE ? OR LOWER(COALESCE(u.email,'')) LIKE ? OR LOWER(COALESCE(u.phone,'')) LIKE ?)"
  like='%'+q+'%'; params=[like,like,like]
 rows=c.execute("""SELECT u.id,u.name,u.email,u.phone,u.status,u.created_at,
 (SELECT COUNT(*) FROM association_memberships am WHERE am.user_id=u.id AND am.status='approved') association_count,
 (SELECT COUNT(*) FROM trees t WHERE t.planted_by_user_id=u.id AND t.active=1) tree_count
 FROM users u WHERE """+where+" ORDER BY u.name LIMIT 250",params).fetchall()
 c.close()
 return jsonify({'items':[dict(id=x['id'],name=x['name'] or '',email=x['email'],phone=x['phone'],status=x['status'] or '',
 joined_at=x['created_at'] or '',association_count=x['association_count'],tree_count=x['tree_count']) for x in rows]})

@app.post('/api/v1/association-requests')
@android_auth
def android_create_association_request():
 body=request.get_json(silent=True) or {}; cleanv=lambda k: clean(body.get(k))
 name=cleanv('name'); login_id=cleanv('association_login_id'); password=str(body.get('association_password') or ''); org=cleanv('organization_type') or 'volunteer_group'; approval=cleanv('approval_number'); symbol=cleanv('map_symbol') or '🌳'
 if not name: return jsonify({'error':{'message':'Le nom de l’association est obligatoire.'}}),400
 if len(login_id)<4: return jsonify({'error':{'message':'Choisissez un ID Association d’au moins 4 caractères.'}}),400
 if len(password)<6: return jsonify({'error':{'message':'Le mot de passe doit contenir au moins 6 caractères.'}}),400
 if org not in ('volunteer_group','approved_association'): return jsonify({'error':{'message':'Type d’association invalide.'}}),400
 raw_doc=str(body.get('approval_document_base64') or '')
 if org=='approved_association' and (not approval or not raw_doc): return jsonify({'error':{'message':'Numéro et document d’agrément obligatoires.'}}),400
 c=db()
 if c.execute("SELECT 1 FROM association_accounts WHERE lower(login_id)=lower(?)",(login_id,)).fetchone() or c.execute("SELECT 1 FROM association_creation_requests WHERE status='pending' AND lower(COALESCE(requested_login_id,''))=lower(?)",(login_id,)).fetchone(): c.close(); return jsonify({'error':{'message':'Cet ID Association est déjà utilisé.'}}),409
 if symbol not in available_association_symbols(c):
  symbols=available_association_symbols(c); symbol=symbols[0] if symbols else '🌳'
 rel_doc=doc_name=doc_mime=None
 if raw_doc:
  try:
   data=base64.b64decode(raw_doc,validate=True)
   if len(data)>8*1024*1024: c.close(); return jsonify({'error':{'message':'Le document dépasse 8 Mo.'}}),400
   doc_name=os.path.basename(str(body.get('approval_document_name') or 'agrement'))
   doc_mime=cleanv('approval_document_mime') or 'application/octet-stream'
   ext=os.path.splitext(doc_name)[1].lower()
   if ext not in ('.jpg','.jpeg','.png','.pdf'):
    ext={ 'image/jpeg':'.jpg','image/png':'.png','application/pdf':'.pdf'}.get(doc_mime,'')
   if ext not in ('.jpg','.jpeg','.png','.pdf'): c.close(); return jsonify({'error':{'message':'Format accepté : JPG, JPEG, PNG ou PDF.'}}),400
   folder=os.path.join(DATA_DIR,'uploads','association_approvals'); os.makedirs(folder,exist_ok=True); fn=secrets.token_hex(12)+ext
   with open(os.path.join(folder,fn),'wb') as f: f.write(data)
   rel_doc='uploads/association_approvals/'+fn
  except Exception: c.close(); return jsonify({'error':{'message':'Document d’agrément invalide.'}}),400
 now=datetime.now().isoformat(timespec='minutes')
 cur=c.execute("INSERT INTO association_creation_requests(requested_by_user_id,name,description,address,phone,email,status,requested_at,requested_map_symbol,requested_login_id,requested_password_hash,organization_type,approval_number,approval_document,approval_document_name,approval_document_mime) VALUES(?,?,?,?,?,?,'pending',?,?,?,?,?,?,?,?,?)",(request.android_uid,name,cleanv('description'),cleanv('address'),cleanv('phone'),cleanv('email'),now,symbol,login_id,generate_password_hash(password),org,approval,rel_doc,doc_name,doc_mime)); rid=cur.lastrowid
 for x in c.execute("SELECT id FROM users WHERE active=1 AND role='super_admin'").fetchall(): c.execute("INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)",(x['id'],'Nouvelle demande d’association',name+' demande son enregistrement dans MyTree.','/association-requests','Action requise','association_request',rid,now))
 c.commit(); c.close(); log_action('request_association','association_request',rid)
 return jsonify({'ok':True,'request_id':rid,'status':'pending','message':'Demande envoyée – En attente de validation.'}),201

@app.get('/api/v1/admin/association-requests')
@android_auth
def android_admin_association_requests():
 c=db()
 if not require_android_super_admin(c): c.close(); return jsonify({'error':{'message':'Accès Super Admin requis'}}),403
 rows=c.execute("""SELECT r.id,r.requested_by_user_id,r.name,r.status,r.requested_at,u.name requester_name
 FROM association_creation_requests r JOIN users u ON u.id=r.requested_by_user_id
 WHERE r.status='pending' ORDER BY r.id DESC""").fetchall()
 c.close(); return jsonify({'items':[dict(id=x['id'],requester_id=x['requested_by_user_id'],requested_name=x['name'],
 requester_name=x['requester_name'] or '',status=x['status'],created_at=x['requested_at']) for x in rows]})

@app.post('/api/v1/admin/association-requests/<int:rid>/review')
@android_auth
def android_admin_association_request_review(rid):
 body=request.get_json(silent=True) or {}; decision=clean(body.get('decision')).lower(); reason=clean(body.get('reason'))
 if decision not in ('approve','reject'): return jsonify({'error':{'message':'Décision invalide'}}),400
 if decision=='reject' and not reason: return jsonify({'error':{'message':'Motif obligatoire'}}),400
 c=db()
 if not require_android_super_admin(c): c.close(); return jsonify({'error':{'message':'Accès Super Admin requis'}}),403
 r=c.execute("SELECT * FROM association_creation_requests WHERE id=? AND status='pending'",(rid,)).fetchone()
 if not r: c.close(); return jsonify({'error':{'message':'Demande introuvable ou déjà traitée'}}),409
 now=datetime.now().isoformat(timespec='minutes')
 if decision=='approve':
  code=association_code(c)
  cur=c.execute("""INSERT INTO associations(code,name,description,wilaya_id,commune_id,address,phone,email,status,created_by_user_id,created_at)
   VALUES(?,?,?,?,?,?,?,?, 'active',?,?)""",
   (code,r['name'],r['description'],r['wilaya_id'],r['commune_id'],r['address'],r['phone'],r['email'],request.android_uid,now))
  aid=cur.lastrowid
  c.execute("""INSERT OR REPLACE INTO association_memberships(
   association_id,user_id,member_kind,role_code,status,requested_at,reviewed_by_user_id,reviewed_at)
   VALUES(?,?,'volunteer','association_admin','approved',?,?,?)""",
   (aid,r['requested_by_user_id'],r['requested_at'],request.android_uid,now))
  status='approved'; msg='Votre association a été créée. Votre profil Personnel reste actif et le profil Association est maintenant disponible.'
 else:
  status='rejected'; msg='Votre demande de création d’association a été refusée : '+reason
 c.execute("UPDATE association_creation_requests SET status=?,reviewed_by_user_id=?,reviewed_at=?,rejection_reason=? WHERE id=?",
           (status,request.android_uid,now,None if decision=='approve' else reason,rid))
 c.execute("""INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at)
 VALUES(?,?,?,?,?,?,?,0,?)""",(r['requested_by_user_id'],'Demande d’association',msg,'/my-associations','Association','association_request',rid,now))
 c.commit(); c.close()
 return jsonify({'ok':True,'message':'Demande acceptée.' if decision=='approve' else 'Demande refusée.'})

@app.errorhandler(404)
def not_found(error):
 if request.path.startswith('/api/') or request.path=='/healthz':
  return jsonify({'error':'not_found','path':request.path}),404
 html="<div class='card'><h2>Page introuvable</h2><p>Le lien demandé n'existe pas ou a été déplacé.</p><p><button class='btn' type='button' onclick='history.back()'>← Retour</button> <a class='btn' href='/'>Accueil</a></p></div>"
 return page('Page introuvable',html),404

@app.errorhandler(500)
def internal_error(error):
 try:
  log_action('server_error','request',None,request.path)
 except Exception:
  pass
 html="<div class='card'><h2>Une erreur est survenue</h2><p>L'opération n'a pas pu être terminée. Aucune validation ne doit être considérée comme enregistrée sans message de confirmation.</p><p><button class='btn' type='button' onclick='history.back()'>← Retour</button> <a class='btn' href='/'>Accueil</a></p></div>"
 return page('Erreur temporaire',html),500

if __name__=='__main__': app.run(host='0.0.0.0',port=8080,debug=False)

# Alpha 2 tenant/context isolation marker
