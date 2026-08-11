from flask import Flask, request, redirect, session, flash, render_template_string, send_file, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import sqlite3, os, io, json, shutil, tempfile
from db_compat import connect_db, DBIntegrityError, using_postgres, database_label, table_count, export_database_json
from data_catalogs import SPECIES_CATALOG, EQUIPMENT_CATALOG
import qrcode

BASE_DIR=os.path.abspath(os.path.dirname(__file__))
# Sous Vercel/Neon, aucune base n'est écrite dans /var/task. SQLite reste disponible en local.
DATA_DIR=os.environ.get('MYTREE_DATA_DIR', '/tmp' if using_postgres() else BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH=os.path.join(DATA_DIR,'mytree.db')
app=Flask(__name__)
app.secret_key=os.environ.get('MYTREE_SECRET','change-this-secret')
app.permanent_session_lifetime=timedelta(days=30)
APP_VERSION='v1.8.0 RC1 Rev.12 — Correctif verrou initialisation Neon'

SCHEMA='''
CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,label TEXT NOT NULL,description TEXT,color TEXT DEFAULT '#2e7b47',level INTEGER DEFAULT 10,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS permissions(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS role_permissions(role_id INTEGER,permission_id INTEGER,PRIMARY KEY(role_id,permission_id));
CREATE TABLE IF NOT EXISTS user_permissions(user_id INTEGER,permission_id INTEGER,granted INTEGER DEFAULT 1,PRIMARY KEY(user_id,permission_id));
CREATE TABLE IF NOT EXISTS wilayas(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS communes(id INTEGER PRIMARY KEY AUTOINCREMENT,wilaya_id INTEGER NOT NULL,name TEXT NOT NULL,active INTEGER DEFAULT 1,UNIQUE(wilaya_id,name));
CREATE TABLE IF NOT EXISTS species(id INTEGER PRIMARY KEY AUTOINCREMENT,name_fr TEXT UNIQUE NOT NULL,name_ar TEXT,name_en TEXT,scientific_name TEXT,category TEXT,water_need TEXT,watering_frequency_days INTEGER,color TEXT DEFAULT '#2e7b47',description TEXT,photo_url TEXT,active INTEGER DEFAULT 1,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,first_name TEXT,last_name TEXT,name TEXT,sex TEXT,phone TEXT UNIQUE,email TEXT,username TEXT UNIQUE,password_hash TEXT NOT NULL,role_id INTEGER,role TEXT,active INTEGER DEFAULT 1,wilaya_id INTEGER,commune_id INTEGER,team_id INTEGER,created_at TEXT,last_login TEXT,birth_date TEXT,address TEXT,skills TEXT,availability TEXT,photo_url TEXT,preferred_language TEXT DEFAULT 'fr');
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,status TEXT DEFAULT 'Brouillon',target_trees INTEGER DEFAULT 0,budget REAL DEFAULT 0,wilaya_id INTEGER,commune_id INTEGER,location TEXT,manager_user_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS zones(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,wilaya_id INTEGER,commune_id INTEGER,code TEXT,name TEXT NOT NULL,area REAL DEFAULT 0,target_trees INTEGER DEFAULT 0,color TEXT DEFAULT '#3a7d44',manager_user_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sectors(id INTEGER PRIMARY KEY AUTOINCREMENT,zone_id INTEGER NOT NULL,code TEXT,name TEXT NOT NULL,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,leader_user_id INTEGER,project_id INTEGER,zone_id INTEGER,phone TEXT,mission TEXT,active INTEGER DEFAULT 1);
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

CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT NOT NULL,message TEXT,link TEXT,category TEXT DEFAULT 'Général',action_type TEXT,action_id INTEGER,decision TEXT,is_read INTEGER DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_user_id INTEGER NOT NULL,recipient_user_id INTEGER,team_id INTEGER,project_id INTEGER,zone_id INTEGER,subject TEXT,body TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,login_value TEXT,success INTEGER DEFAULT 0,ip_address TEXT,created_at TEXT NOT NULL);
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

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
'''

def db():
 return connect_db(DB_PATH)

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
 for d in ['action_type TEXT','action_id INTEGER','decision TEXT']:
  add_column(c,'notifications',d)
 add_column(c,'members','membership_date TEXT')
 for d in ['species_id INTEGER','equipment_id INTEGER']:
  add_column(c,'donations',d)
 for d in ['user_id INTEGER','quantity_range TEXT','latitude REAL','longitude REAL','photo_url TEXT','tree_condition TEXT','batch_id INTEGER','created_at TEXT']:
  add_column(c,'watering_logs',d)
 for d in ['created_by_user_id INTEGER','created_at TEXT','updated_at TEXT']:
  add_column(c,'teams',d)
 if 'tree_observations' in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}: add_column(c,'tree_observations','photo_url TEXT')
 for d in ["description TEXT","color TEXT DEFAULT '#2e7b47'","active INTEGER DEFAULT 1"]:
  add_column(c,'roles',d)
 if 'missions' in {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
  for d in ['actual_start_at TEXT','actual_end_at TEXT','completion_notes TEXT']:
   add_column(c,'missions',d)
  for d in ["priority TEXT DEFAULT 'Normale'",'completed_count INTEGER DEFAULT 0','report TEXT']:
   add_column(c,'missions',d)

def seed(c):
 roles=[('super_admin','Super administrateur',100),('admin','Administrateur',80),('coordinator','Coordinateur',60),('project_manager','Responsable de projet',50),('zone_manager','Responsable de zone',40),('team_leader','Chef d’équipe',30),('volunteer','Bénévole',10),('visitor','Visiteur',1)]
 for x in roles:c.execute('INSERT OR IGNORE INTO roles(name,label,level) VALUES(?,?,?)',x)
 perms=[('dashboard.view','Voir le tableau de bord'),('tree.view','Voir les arbres'),('tree.create','Créer une plantation'),('tree.approve','Valider une plantation'),('tree.edit','Modifier un arbre'),('tree.delete','Supprimer un arbre'),('watering.view','Voir les arrosages'),('watering.create','Enregistrer un arrosage'),('mission.view','Voir les missions'),('event.view','Voir les événements'),('event.register','S’inscrire aux événements'),('event.manage','Gérer les événements'),('intervention.view','Voir les interventions'),('intervention.create','Créer une intervention'),('intervention.manage','Gérer et planifier les interventions'),('team.view','Voir son équipe'),('map.view','Voir la carte'),('notification.view','Voir les notifications'),('volunteer.manage','Gérer les bénévoles'),('project.manage','Gérer les projets'),('zone.manage','Gérer les zones'),('geo.manage','Gérer la géographie'),('species.manage','Gérer les espèces'),('role.manage','Gérer les rôles et droits'),('user.manage','Gérer les utilisateurs'),('donation.view','Voir les dons'),('donation.manage','Gérer les dons'),('nursery.view','Voir la pépinière'),('nursery.manage','Gérer la pépinière'),('equipment.view','Voir le matériel'),('equipment.manage','Gérer le matériel'),('member.view','Voir les adhérents'),('member.manage','Gérer les adhérents'),('cash.view','Voir la caisse'),('cash.manage','Gérer la caisse'),('print.manage','Imprimer les documents')]
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

# Verrou PostgreSQL stable et propre à l'initialisation MyTree.
# Le verrou est de niveau session : il reste détenu après COMMIT et est
# automatiquement libéré si la connexion disparaît.
MYTREE_INIT_LOCK_KEY=62872431529701

def init_db():
 c=db()
 init_lock=False
 try:
  if using_postgres():
   # Vercel peut démarrer plusieurs fonctions Flask en parallèle. Sans ce
   # verrou, deux instances peuvent exécuter CREATE TABLE simultanément et
   # PostgreSQL peut lever pg_type_typname_nsp_index / UniqueViolation.
   c.execute('SELECT pg_advisory_lock(?)',(MYTREE_INIT_LOCK_KEY,))
   c.commit()
   init_lock=True

  c.executescript(SCHEMA)
  migrate_legacy(c)
  seed(c)
  # RC1: indexation des recherches et listes les plus utilisées.
  c.executescript("""
  CREATE INDEX IF NOT EXISTS idx_trees_project_zone ON trees(project_id,zone_id);
  CREATE INDEX IF NOT EXISTS idx_trees_approval_active ON trees(approval_status,active);
  CREATE INDEX IF NOT EXISTS idx_trees_gps ON trees(latitude,longitude);
  CREATE INDEX IF NOT EXISTS idx_trees_species ON trees(species_id,species);
  CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role,active);
  CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id,is_read,created_at);
  CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
  CREATE INDEX IF NOT EXISTS idx_events_start_status ON events(start_at,status,active);
  CREATE INDEX IF NOT EXISTS idx_tasks_start_status ON operational_tasks(start_at,status);
  """)
  c.commit()
 except Exception:
  # Une erreur PostgreSQL laisse la transaction en état aborted : rollback
  # avant toute tentative de libération du verrou.
  try:
   c.rollback()
  except Exception:
   pass
  raise
 finally:
  if init_lock:
   try:
    c.execute('SELECT pg_advisory_unlock(?)',(MYTREE_INIT_LOCK_KEY,))
    c.commit()
   except Exception:
    try:
     c.rollback()
    except Exception:
     pass
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
 'Arbres personnels / apportés directement (aucun mouvement de stock)':{'ar':'أشجار شخصية / جلبها المتطوع مباشرة (بدون حركة مخزون)','en':'Personal / directly supplied trees (no inventory movement)'},'Stock de l’association (déduire automatiquement)':{'ar':'مخزون الجمعية (خصم تلقائي)','en':'Association inventory (deduct automatically)'}
}

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
 lang=current_lang(); trans={} if lang=='fr' else {k:v.get(lang,k) for k,v in I18N.items()}
 return '''<script id="mytree-i18n">window.MYTREE_LANG=%s;window.MYTREE_I18N=%s;
(function(){function ex(s){return (s||'').replace(/\\s+/g,' ').trim()}function tv(k){if(window.MYTREE_I18N[k])return window.MYTREE_I18N[k];const keys=Object.keys(window.MYTREE_I18N).sort((a,b)=>b.length-a.length);for(const x of keys){if(k.endsWith(x)){const pre=k.slice(0,k.length-x.length);if(!pre||/[^A-Za-zÀ-ÿ\u0600-\u06FF]$/.test(pre))return pre+window.MYTREE_I18N[x]}}return null}function go(root){if(!window.MYTREE_I18N)return;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),a=[];while(w.nextNode())a.push(w.currentNode);a.forEach(n=>{if(n.parentElement&&['SCRIPT','STYLE','TEXTAREA'].includes(n.parentElement.tagName))return;let raw=n.nodeValue,k=ex(raw),v=tv(k);if(v){let l=(raw.match(/^\\s*/)||[''])[0],r=(raw.match(/\\s*$/)||[''])[0];n.nodeValue=l+v+r}});document.querySelectorAll('[placeholder]').forEach(e=>{let k=ex(e.placeholder);if(window.MYTREE_I18N[k])e.placeholder=window.MYTREE_I18N[k]})}document.addEventListener('DOMContentLoaded',()=>go(document.body));})();</script>'''%(json.dumps(lang),json.dumps(trans,ensure_ascii=False))

@app.route('/language/<lang>')
def set_language(lang):
 if lang not in SUPPORTED_LANGS:lang='fr'
 session['lang']=lang
 if session.get('uid'):
  c=db(); c.execute('UPDATE users SET preferred_language=? WHERE id=?',(lang,session['uid'])); c.commit(); c.close()
 target=request.args.get('next') or request.referrer or '/public'
 if not target.startswith('/'):target='/public'
 resp=redirect(target); resp.set_cookie('mytree_lang',lang,max_age=365*24*3600,samesite='Lax'); return resp

UNIVERSAL_SEARCH_SCRIPT='''<script id="mytree-smart-search">(function(){function n(v){return (v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim()}function ph(){return window.MYTREE_LANG==='ar'?'بحث ذكي في القائمة…':window.MYTREE_LANG==='en'?'Smart search in list…':'Recherche intelligente dans la liste…'}function enhance(s){if(!s||s.dataset.smartSearch==='1'||s.dataset.noSmartSearch==='1'||s.multiple||s.options.length<4)return;s.dataset.smartSearch='1';const q=document.createElement('input');q.type='search';q.className='smart-list-search';q.placeholder=ph();q.autocomplete='off';s.parentNode.insertBefore(q,s);let src=[];function snap(){src=[...s.options].map(o=>({v:o.value,t:o.text,d:o.disabled}))}snap();q.addEventListener('focus',snap);q.addEventListener('input',()=>{const z=n(q.value),cur=s.value,base=src.length?src:[...s.options].map(o=>({v:o.value,t:o.text,d:o.disabled}));const m=base.filter((o,i)=>i===0||!z||n(o.t).includes(z));s.innerHTML='';m.forEach(o=>{const x=document.createElement('option');x.value=o.v;x.textContent=o.t;x.disabled=o.d;if(o.v===cur)x.selected=true;s.appendChild(x)});if(z&&m.length>1&&!s.value)s.selectedIndex=1});s.addEventListener('change',()=>{const o=s.options[s.selectedIndex];if(o&&o.value)q.value=o.text})}function scan(r){(r||document).querySelectorAll('select').forEach(enhance)}document.addEventListener('DOMContentLoaded',()=>scan(document));new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(x=>{if(x.nodeType===1){if(x.matches&&x.matches('select'))enhance(x);scan(x)}}))).observe(document.documentElement,{childList:true,subtree:true});})();</script>'''

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
  if not session.get('uid'): return redirect('/login')
  return fn(*a,**k)
 return w

def is_admin(): return session.get('role') in ('super_admin','admin')

def has_permission(code):
 if is_admin(): return True
 if not session.get('uid'): return False
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

STYLE='''<style>:root{--bg:#f3f6f1;--card:#fff;--text:#223129;--muted:#748079;--line:#dfe7df;--deep:#102b1c;--green:#2e7b47;--red:#bd4747;--amber:#bd8120;--blue:#2c68b8}*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}header{height:64px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px}.layout{display:grid;grid-template-columns:250px 1fr;min-height:calc(100vh - 64px)}aside{background:linear-gradient(180deg,#102b1c,#0b2015);padding:18px 13px;color:#fff}.brand{font-size:23px;font-weight:800}.slogan{font-size:12px;color:#b9cabf;margin:4px 0 18px}aside a{display:block;color:#dce9df;text-decoration:none;padding:10px 13px;border-radius:9px;margin:3px 0}aside a:hover{background:#205837}main{padding:20px}.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(5,1fr)}.two{grid-template-columns:2fr 1fr}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px}.kpi{cursor:pointer;text-decoration:none;color:inherit}.kpi small{color:var(--muted)}.kpi b{font-size:28px;display:block;margin:8px 0}.btn{display:inline-block;border:0;background:var(--green);color:#fff;padding:9px 13px;border-radius:8px;text-decoration:none;cursor:pointer}.btn.alt{background:#edf2ed;color:#24352b}.btn.red{background:#fff;color:#8b3434;border:1px solid #e4caca}.btn.red:hover{background:#fff6f6;border-color:#c98f8f}.btn.amber{background:var(--amber)}.toolbar{display:flex;gap:9px;flex-wrap:wrap;align-items:end;margin-bottom:12px}.toolbar label{min-width:145px;flex:1}input,select,textarea{width:100%;padding:9px;border:1px solid #cbd6ce;border-radius:8px;background:#fff}textarea{min-height:75px}.form{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.full{grid-column:1/-1}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}th{background:#f8faf7}.badge{padding:4px 8px;border-radius:20px;font-size:11px;font-weight:bold}.good{background:#e1f1e4;color:#28643b}.watch{background:#fff0d4;color:#885800}.danger{background:#fbe1e1;color:#983636}.pending{background:#e7edfa;color:#315fa2}.flash{background:#fff0d4;padding:10px;border-radius:8px;margin-bottom:12px}.section-title{display:flex;align-items:center;justify-content:space-between}.sub{font-size:12px;color:var(--muted)}@media(max-width:1050px){.layout{grid-template-columns:1fr}aside{display:flex;overflow:auto;padding:8px}.brand,.slogan{display:none}aside a{min-width:max-content}.kpis{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}@media(max-width:600px){main{padding:10px}.form,.kpis{grid-template-columns:1fr}.full{grid-column:auto}}.real-map{height:560px;border-radius:12px;border:1px solid var(--line)}.leaflet-popup-content{min-width:230px}.qr-grid{display:grid;grid-template-columns:repeat(var(--qr-cols,3),1fr);gap:14px}.qr-grid.qr-1{--qr-cols:1}.qr-grid.qr-6{--qr-cols:2}.qr-grid.qr-12{--qr-cols:3}.qr-grid.qr-24{--qr-cols:4}.qr-grid.qr-thermal{--qr-cols:1;max-width:80mm;margin:auto}.qr-grid.qr-1 .qr-label img{width:360px;height:360px}.qr-grid.qr-24 .qr-label{padding:6px;font-size:10px}.qr-grid.qr-24 .qr-label img{width:105px;height:105px}.qr-grid.qr-thermal .qr-label{border:0;border-bottom:1px dashed #777;border-radius:0}.photo-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.photo-preview{max-width:280px;max-height:240px;border-radius:10px;object-fit:cover;cursor:pointer}.gps-quality{font-weight:700}.gps-good{color:#2e7b47}.gps-medium{color:#bd8120}.gps-bad{color:#bd4747}.qr-label{border:1px dashed #78867d;border-radius:10px;padding:12px;text-align:center;background:#fff;break-inside:avoid}.qr-label img{width:180px;height:180px;max-width:100%}.nearby{background:#eaf4ff;color:#275c91;padding:8px;border-radius:8px}.compact-table{max-height:310px;overflow:auto}.priority{padding:10px;border-bottom:1px solid var(--line)}.priority b,.priority span{display:block}@media print{header,aside,.noprint{display:none!important}.layout{display:block}.qr-grid{grid-template-columns:repeat(var(--qr-cols,3),1fr)!important}main{padding:0}.qr-label{page-break-inside:avoid}}@media(max-width:700px){.qr-grid{grid-template-columns:1fr}.real-map{height:65vh}}.vol-hero{background:linear-gradient(135deg,#174d2d,#2e7b47);color:#fff;border-radius:18px;padding:20px;margin-bottom:14px}.vol-actions{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.vol-action{display:flex;min-height:105px;flex-direction:column;align-items:center;justify-content:center;text-align:center;font-weight:700;font-size:15px;background:#fff;border:1px solid var(--line);border-radius:16px;text-decoration:none;color:var(--text);box-shadow:0 5px 18px rgba(16,43,28,.06)}.vol-action span{font-size:30px;margin-bottom:8px}.mobile-note{background:#eaf4ee;border-left:4px solid var(--green);padding:10px 12px;border-radius:8px}.scan-box{max-width:620px;margin:auto}.scan-preview{width:100%;min-height:260px;background:#102b1c;border-radius:14px;object-fit:cover}.bottom-space{height:20px}@media(max-width:700px){header{height:auto;padding:12px 14px;align-items:flex-start}.vol-actions{grid-template-columns:repeat(2,1fr)}.vol-action{min-height:112px}.layout{padding-bottom:68px}.vol-nav{position:fixed;bottom:0;left:0;right:0;z-index:1200;display:flex!important;overflow-x:auto;background:#102b1c;padding:5px 6px}.vol-nav a{font-size:11px;text-align:center;min-width:74px;padding:7px 6px;margin:0}.vol-nav .brand,.vol-nav .slogan{display:none}.card{border-radius:12px}.kpi b{font-size:24px}}.header-actions{display:flex;align-items:center;gap:8px}.notif-bell{position:relative;text-decoration:none;font-size:23px}.notif-bell span{position:absolute;top:-7px;right:-10px;background:#d92727;color:#fff;border-radius:999px;min-width:19px;height:19px;padding:2px 5px;font-size:11px;text-align:center;font-weight:800;border:2px solid #fff}.public-hero{background:linear-gradient(135deg,#0e3b25,#3c8d55);color:#fff;border-radius:22px;padding:42px 28px}.public-actions{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.public-action{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;text-decoration:none;color:var(--text);text-align:center;font-weight:700}.species-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.species-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;text-decoration:none;color:inherit}.map-picker{height:420px;border-radius:12px;border:1px solid var(--line)}@media(max-width:800px){.public-actions,.species-grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.public-actions,.species-grid{grid-template-columns:1fr}}
.public-shell{max-width:1240px;margin:auto;padding:0 18px}.public-header{position:sticky;top:0;z-index:1100;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);min-height:72px}.public-brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--deep);font-size:21px;font-weight:800}.public-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.hero-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:18px;align-items:stretch}.hero-side{background:#fff;border:1px solid var(--line);border-radius:22px;padding:24px;display:flex;flex-direction:column;justify-content:center}.hero-side b{font-size:34px}.public-section{margin:28px 0}.public-section h2{margin-bottom:8px}.public-action{min-height:132px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:17px;box-shadow:0 8px 24px rgba(16,43,28,.06);transition:.18s transform,.18s box-shadow}.public-action:hover,.species-card:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(16,43,28,.10)}.public-action .icon{font-size:34px;margin-bottom:8px}.public-kpis{grid-template-columns:repeat(4,1fr)}.public-kpis .kpi{cursor:default}.public-footer{margin-top:36px;background:var(--deep);color:#dce9df;padding:28px 18px}.public-footer a{color:#fff}.mobile-public-nav{display:none}.field-hero{background:linear-gradient(135deg,#102b1c,#2e7b47);color:#fff;border-radius:20px;padding:22px}.field-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:16px}.field-action{min-height:132px;background:#fff;border:1px solid var(--line);border-radius:18px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-decoration:none;color:var(--text);font-size:17px;font-weight:800}.field-action span{font-size:38px;margin-bottom:8px}.home-shortcut{font-weight:700;text-decoration:none;color:var(--green)}
@media(max-width:900px){.hero-grid{grid-template-columns:1fr}.public-kpis{grid-template-columns:repeat(2,1fr)}.public-header{position:relative}.public-nav{display:none}.mobile-public-nav{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;bottom:0;left:0;right:0;z-index:1300;background:#fff;border-top:1px solid var(--line);padding:5px 4px}.mobile-public-nav a{text-align:center;text-decoration:none;color:var(--text);font-size:10px;padding:6px 2px}.mobile-public-nav span{display:block;font-size:21px}.public-page-body{padding-bottom:68px}.field-actions{grid-template-columns:repeat(2,1fr)}}
.vertical-actions{display:flex;flex-direction:column;gap:12px}.vertical-action{display:flex;align-items:center;gap:14px;width:100%;min-height:68px;padding:14px 18px;border-radius:14px;background:#fff;border:1px solid var(--line);text-decoration:none;color:var(--text);font-weight:800;font-size:17px;box-shadow:0 5px 18px rgba(16,43,28,.06)}.vertical-action .icon{font-size:30px;min-width:38px;text-align:center}.nav-return-highlight{outline:3px solid #65a97b!important;background:#e8f6ec!important;transition:background .4s,outline .4s}.quick-actions{display:flex;gap:6px;flex-wrap:wrap}.quick-actions form{display:inline}.bulk-bar{position:sticky;top:0;z-index:10;background:#fff;border:1px solid var(--line);padding:12px;border-radius:12px;margin-bottom:10px}.action-card{border-left:5px solid var(--amber)}@media(max-width:700px){.vol-actions,.public-actions,.field-actions{display:flex;flex-direction:column}.vol-action,.public-action,.field-action{min-height:72px;flex-direction:row;justify-content:flex-start;padding:14px 18px;text-align:left}.vol-action span,.public-action .icon,.field-action span{font-size:30px;margin:0 14px 0 0}.header-actions .btn{min-height:44px;padding:12px 14px}.btn{min-height:44px;padding:12px 14px}.quick-actions .btn{min-height:38px;padding:8px 10px}.mobile-login{display:block!important;width:100%;margin-top:8px;text-align:center}}@media(max-width:560px){.public-shell{padding:0 10px}.public-hero{padding:28px 20px;border-radius:18px}.public-hero h1{font-size:28px;line-height:1.15}.public-hero .btn{display:block;width:100%;margin:8px 0;padding:14px}.public-kpis{grid-template-columns:1fr 1fr}.public-kpis .card{padding:13px}.public-actions{grid-template-columns:1fr}.public-action{min-height:96px;flex-direction:row;justify-content:flex-start;text-align:left;padding:18px;gap:14px}.public-action .icon{margin:0;font-size:30px}.species-grid{grid-template-columns:1fr}.field-actions{grid-template-columns:1fr}.field-action{min-height:94px;flex-direction:row;gap:14px}.field-action span{margin:0}.header-actions b{display:none}}

.don-line{display:grid;grid-template-columns:2fr 1fr auto;gap:8px;align-items:center;margin:9px 0}.action-set{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.action-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:10px;border:1px solid transparent;text-decoration:none;font-weight:700;cursor:pointer}.action-view{background:#eef5ff;color:#23558b}.action-map{background:#f1f0ff;color:#5848a5}.action-edit{background:#fff6df;color:#8a6113}.action-delete{background:#fff;color:#8b3434;border-color:#e4caca}.action-delete:hover{background:#fff6f6;border-color:#c98f8f}.action-primary{background:var(--green);color:#fff}.don-type-panel{display:none}.don-type-panel.active{display:contents}.mobile-only,.mobile-back{display:none}.private-section-label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#9fb5a7;padding:10px 13px 3px}.danger-zone{border:1px solid #efc4c4;background:#fff8f8}.crud-actions{display:flex;gap:7px;flex-wrap:wrap}.public-login-cta{display:inline-block}.public-auth-banner{display:none;gap:8px;justify-content:flex-end;padding-top:12px}.public-auth-banner .btn{display:inline-block}
@media(max-width:700px){
 header{height:auto;min-height:66px;position:sticky;top:0;z-index:1150;padding:10px 12px;flex-direction:row;align-items:center;gap:8px}.mobile-title-row{display:flex;align-items:center;gap:9px;min-width:0}.mobile-title-row b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:55vw}.mobile-back{display:inline-flex!important;width:42px;height:42px;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:24px;color:var(--deep)}.header-actions{margin-left:auto;width:auto;gap:10px}.header-actions>a:not(.notif-bell),.header-actions>b{display:none}.layout{display:block!important;padding-bottom:72px}.layout>aside.vol-nav{position:fixed!important;bottom:0;left:0;right:0;z-index:1200;height:66px;width:100%;display:grid!important;grid-template-columns:repeat(5,1fr)!important;background:#fff!important;border-top:1px solid var(--line);padding:4px!important;overflow:visible!important}.vol-nav .brand,.vol-nav .slogan,.vol-nav .desktop-only,.vol-nav .private-section-label{display:none!important}.vol-nav a{display:none!important}.vol-nav a.mobile-primary{display:flex!important;min-width:0!important;width:auto!important;margin:0!important;padding:5px 2px!important;border:0!important;border-radius:9px!important;background:transparent!important;color:var(--deep)!important;font-size:10px!important;line-height:1.15;text-align:center!important;align-items:center;justify-content:center;white-space:normal}.vol-nav a.mobile-primary:hover{background:#edf5ef!important}.layout>aside:not(.vol-nav){display:none!important}main{padding:12px 10px}.section-title{align-items:flex-start;gap:10px;flex-direction:column}.section-title>div,.section-title>.crud-actions{width:100%}.section-title .btn,.crud-actions .btn,.crud-actions form{width:100%}.crud-actions form .btn{width:100%}.toolbar{display:flex;flex-direction:column;align-items:stretch}.toolbar label,.toolbar .btn{width:100%;min-width:0}.form{grid-template-columns:1fr}.card{overflow-x:auto}.vertical-actions{width:100%}.vertical-action{min-height:64px;padding:13px 15px}.vertical-action .icon{font-size:28px}.secondary-action{background:#eef5f0}.desktop-dashboard-details{display:none}.mobile-only{display:block}.public-header .public-shell{flex-direction:column;align-items:stretch!important}.public-auth-banner{display:flex!important}.public-brand{text-align:center}.public-login-cta{display:block!important;width:100%;text-align:center}.mobile-public-nav{position:fixed!important;bottom:0!important;display:grid!important;grid-template-columns:repeat(5,1fr)!important;background:#fff!important;border-top:1px solid var(--line)!important;padding:4px!important;gap:0!important}.mobile-public-nav a{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;background:transparent!important;border:0!important;border-radius:9px!important;padding:5px 2px!important;font-size:10px!important;font-weight:700!important;text-align:center!important}.mobile-public-nav a:nth-child(n+6){display:none!important}.mobile-public-nav span{display:block!important;font-size:21px!important}.public-page-body{padding-bottom:68px!important}.vol-actions,.public-actions,.field-actions{display:flex!important;flex-direction:column!important}.vol-action,.public-action,.field-action{width:100%;min-height:68px!important}table{min-width:680px}
}
</style>'''
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

NAV_ADMIN='''<aside class="admin-nav"><div class="brand">🌳 My Tree</div><div class="slogan">Administration</div>
<div class="admin-nav-block"><div class="admin-nav-title">🌳 Terrain</div><a href="/trees">🌳 Arbres</a><a href="/plantings/pending">🌱 Plantations</a><a href="/watering">💧 Arrosages</a><a href="/map">🗺 Carte</a><a href="/volunteer/gps-quick">📍 GPS rapide</a><a href="/qr">▣ QR Code</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">📂 Organisation</div><a href="/projects">📁 Projets</a><a href="/zones">📍 Zones</a><a href="/teams">👥 Équipes</a><a href="/missions">🎯 Missions</a><a href="/operations">🗓 Planifications</a><a href="/events">📆 Événements</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">👥 Personnes</div><a href="/volunteers">🙋 Bénévoles</a><a href="/members">🪪 Adhérents</a><a href="/users">🔐 Utilisateurs</a><a href="/roles">🛡 Rôles et droits</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">💰 Gestion</div><a href="/cash">💰 Caisse</a><a href="/donations">🎁 Dons</a><a href="/members">🤝 Cotisations</a><a href="/stock">📦 Stock</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">📊 Administration</div><a href="/action-center">✅ Centre d’actions</a><a href="/notifications">🔔 Notifications</a><a href="/reports/operations">📊 Rapports</a><a href="/activity">🕘 Journal d’activité</a><a href="/backup">💾 Sauvegarde</a><a href="/species">🍃 Espèces</a><a href="/geography">📍 Géographie</a><a href="/search">🔎 Recherche</a></div>
<div class="admin-nav-block"><div class="admin-nav-title">🌍 Public</div><a href="/public">🌍 Accueil public</a></div></aside>'''
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
 links=[('/volunteer','🏠 Accueil',None,'mobile-primary'),('/volunteer/field','🚜 Mode Terrain',None,'desktop-only'),('/volunteer/trees','🌳 Mes arbres','tree.view','desktop-only'),('/volunteer/trees/no-gps','📍 Arbres sans GPS','tree.view','desktop-only'),('/volunteer/gps-quick','⚡ GPS rapide','tree.view','desktop-only'),('/planting/new','🌱 Planter','tree.create','desktop-only'),('/volunteer/watering','💧 Arroser','watering.view','desktop-only'),('/volunteer/scan','▣ Scanner QR','tree.view','mobile-primary'),('/map','📍 Carte','map.view','mobile-primary'),('/volunteer/donate','🎁 Faire un don',None,'desktop-only'),('/volunteer/events','📆 Événements','event.view','desktop-only'),('/volunteer/missions','📋 Missions','mission.view','desktop-only'),('/interventions','🛠 Interventions','intervention.view','desktop-only'),('/volunteer/team','👥 Mon équipe','team.view','desktop-only'),('/notifications','🔔 Alertes','notification.view','mobile-primary'),('/volunteer/profile','👤 Profil',None,'mobile-primary')]
 body='<aside class="vol-nav"><div class="brand">🌳 My Tree</div><div class="slogan">Espace bénévole privé</div>'
 for href,label,perm,css in links:
  if not perm or has_permission(perm): body+=f'<a class="{css}" href="{href}">{label}</a>'
 body+='<div class="private-section-label desktop-only">Espace public</div><a class="desktop-only" href="/public">🌍 Accueil public</a>'
 return body+'</aside>'


def page(title,body,**ctx):
 content=render_template_string(body,tr=tr,lang=current_lang(),**ctx)
 if session.get('uid'):
  nav=NAV_ADMIN if is_admin() else volunteer_nav()
  c=db(); unread=c.execute('SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0',(session['uid'],)).fetchone()['n']; c.close()
  bell=f'<a class="notif-bell" href="/notifications" title="Notifications">🔔<span>{unread}</span></a>' if unread else '<a class="notif-bell" href="/notifications" title="Notifications">🔔</a>'
  tpl='<!doctype html><html lang="'+current_lang()+'" dir="'+current_dir()+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+tr(title)+'</title>'+STYLE+PHOTO_SCRIPT+SMART_NAV_SCRIPT+ACTION_UI_SCRIPT+UNIVERSAL_SEARCH_SCRIPT+i18n_script()+'<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script></head><body><header><div class="mobile-title-row"><button type="button" class="mobile-back" onclick="history.back()">←</button><div><b>'+tr(title)+'</b><div class="sub">My Tree Professional — '+APP_VERSION+'</div></div></div><div class="header-actions">'+language_switcher()+bell+' <a class="account-home" href="'+('/' if is_admin() else '/volunteer')+'">🏠 '+tr('Mon accueil')+'</a> <b>'+str(session.get('name') or '')+'</b> • <a href="/logout">'+tr('Déconnexion')+'</a></div></header><div class="layout">'+nav+'<main>{% for m in get_flashed_messages() %}<div class="flash">{{m}}</div>{% endfor %}{{content|safe}}</main></div></body></html>'
  return render_template_string(tpl,content=content)
 return render_template_string('<!doctype html><html lang="'+current_lang()+'" dir="'+current_dir()+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+STYLE+UNIVERSAL_SEARCH_SCRIPT+i18n_script()+'</head><body><main style="max-width:680px;margin:28px auto;padding:0 14px">'+language_switcher()+'{{content|safe}}</main></body></html>',content=content)

def filters_from_request():
 return {k:request.args.get(k,'') for k in ['wilaya_id','commune_id','project_id','zone_id','species_id','sex','health_status','watering_status','approval_status','gps_status','q']}
def tree_where(f):
 w=['t.active=1']; p=[]
 mapping={'wilaya_id':'p.wilaya_id','commune_id':'p.commune_id','project_id':'t.project_id','zone_id':'t.zone_id','species_id':'t.species_id','health_status':'t.health_status','watering_status':'t.watering_status','approval_status':'t.approval_status'}
 for k,col in mapping.items():
  if f.get(k): w.append(col+'=?'); p.append(f[k])
 if f.get('gps_status')=='missing': w.append('(t.latitude IS NULL OR t.longitude IS NULL)')
 if f.get('gps_status')=='mapped': w.append('(t.latitude IS NOT NULL AND t.longitude IS NOT NULL)')
 if f.get('gps_status')=='verify': w.append("COALESCE(t.gps_review_status,'ok')='to_verify'")
 if f.get('q'): w.append('(t.tree_code LIKE ? OR s.name_fr LIKE ? OR u.name LIKE ?)'); p += ['%'+f['q']+'%']*3
 return ' AND '.join(w),p

def filter_options(c):
 return dict(wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(),communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(),projects=c.execute('SELECT * FROM projects WHERE active=1 ORDER BY name').fetchall(),zones=c.execute('SELECT * FROM zones WHERE active=1 ORDER BY name').fetchall(),species=c.execute('SELECT * FROM species WHERE active=1 ORDER BY name_fr').fetchall())

@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  login_value=clean(request.form.get('login')); c=db(); u=c.execute('SELECT u.*,r.name role_name FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE (u.username=? OR u.phone=?) AND u.active=1',(login_value,login_value)).fetchone(); success=bool(u and check_password_hash(u['password_hash'],request.form.get('password','')))
  c.execute('INSERT INTO login_history(user_id,login_value,success,ip_address,created_at) VALUES(?,?,?,?,?)',(u['id'] if u else None,login_value,1 if success else 0,request.headers.get('X-Forwarded-For',request.remote_addr),datetime.now().isoformat(timespec='seconds')))
  if success:
   saved_lang=u['preferred_language'] if 'preferred_language' in u.keys() and u['preferred_language'] in SUPPORTED_LANGS else current_lang(); session.clear(); session.permanent=request.form.get('remember')=='1'; session.update(uid=u['id'],name=u['name'] or user_display_name(u['first_name'],u['last_name']),role=u['role_name'] or u['role'] or 'volunteer',lang=saved_lang); c.execute('UPDATE users SET last_login=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),u['id'])); c.commit(); c.close(); log_action('login','user',u['id'],'Connexion mémorisée' if session.permanent else 'Connexion standard'); target=request.form.get('next') or request.args.get('next'); return redirect(target if target and target.startswith('/') else ('/' if is_admin() else '/volunteer'))
  c.commit(); c.close(); flash('Identifiants incorrects ou compte désactivé.')
 return page('Connexion','''<div class="card login-card"><div style="text-align:center;margin-bottom:18px"><div style="font-size:44px">🌳</div><h2>Connexion MyTree</h2><p class="sub">Connectez-vous pour retrouver votre espace et poursuivre l’action demandée.</p></div><form method="post"><label>Téléphone ou utilisateur<input name="login" autocomplete="username" placeholder="Votre téléphone ou identifiant" required></label><label style="display:block;margin-top:14px">Mot de passe<input type="password" name="password" placeholder="Votre mot de passe" autocomplete="current-password" required></label><input type="hidden" name="next" value="{{request.args.get('next','')}}"><p><label style="display:flex;align-items:center;gap:8px"><input type="checkbox" name="remember" value="1" style="width:auto"> Se souvenir de moi pendant 30 jours</label></p><div class="login-actions"><button class="btn">🔐 Se connecter</button><a class="btn alt" href="/public/register?next={{request.args.get('next','')}}&cancel={{request.args.get('cancel','/public')}}">👤 Créer un compte</a><a class="btn alt" href="{{request.args.get('cancel') or '/public'}}">← Annuler / Retour</a></div></form></div>''')

@app.route('/public/events')
def public_events():
 c=db(); rows=c.execute("SELECT e.*,p.name project_name,z.name zone_name FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id WHERE e.active=1 ORDER BY e.start_at DESC").fetchall(); c.close()
 return public_page('Événements',"""<section class='public-section'><h1>Événements et actions terrain</h1><p class='sub'>Plantations, arrosages, formations et rencontres de l’association.</p><div class='species-grid'>{% for e in rows %}<article class='species-card'><div class='sub'>{{e.event_type}} • {{e.status}}</div><h3>{{e.title}}</h3><p><b>{{e.start_at or 'Date à confirmer'}}</b></p><p>{{e.location or e.zone_name or 'Lieu à confirmer'}}</p><p>{{e.description or ''}}</p><a class='btn' href='/public/action/event'>Participer</a></article>{% else %}<div class='card'>Aucun événement enregistré.</div>{% endfor %}</div></section>""",rows=rows)

@app.route('/public/map')
def public_map():
 c=db(); rows=c.execute("SELECT t.id,t.tree_code,t.latitude,t.longitude,t.health_status,s.name_fr,p.name project_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.active=1 AND t.approval_status='approved' AND t.latitude IS NOT NULL AND t.longitude IS NOT NULL").fetchall(); c.close()
 data=[dict(id=r['id'],code=r['tree_code'],lat=r['latitude'],lon=r['longitude'],health=r['health_status'],species=r['name_fr'],project=r['project_name']) for r in rows]
 return public_page('Carte publique',"""<section class='public-section'><h1>Carte publique des arbres</h1><p class='sub'>Seuls les arbres validés et géolocalisés sont affichés.</p><div id='publicMap' class='real-map'></div></section><script>const trees={{data|tojson}};const m=L.map('publicMap').setView([35.70,-0.64],11);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(m);const pts=[];trees.forEach(t=>{const p=[t.lat,t.lon];pts.push(p);L.marker(p).addTo(m).bindPopup('<b>'+(t.species||'Arbre')+'</b><br>'+(t.code||'')+'<br>'+(t.project||'')+'<br><a href="/public/tree/'+t.id+'">Voir la fiche</a>')});if(pts.length)m.fitBounds(pts,{padding:[30,30],maxZoom:16});</script>""",data=data)

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
  password=request.form.get('password',''); errors=validate_user_form(c,values,password_required=True,password=password)
  if not errors:
   role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']; name=user_display_name(values['first_name'],values['last_name'])
   try:
    cur=c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,birth_date,address,skills,availability,photo_url,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(values['first_name'],values['last_name'],name,values['sex'],values['phone'],values['email'],values['phone'],generate_password_hash(password),role,'volunteer',1,values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],datetime.now().isoformat(timespec='minutes'))); c.commit(); uid=cur.lastrowid; c.close(); log_action('self_register','user',uid); flash('Compte créé. Vous pouvez vous connecter immédiatement.'); return redirect('/login')
   except DBIntegrityError: errors=['Ce téléphone, cet e-mail ou ce nom d’utilisateur est déjà utilisé.']
  for error in errors: flash(error)
 c.close(); return page('Inscription bénévole','''<div class="card"><h2>Nouveau bénévole</h2><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{request.form.get('first_name','')}}" required></label><label>Nom<input name="last_name" value="{{request.form.get('last_name','')}}" required></label><label>Sexe<select name="sex"><option {% if request.form.get('sex')=='Homme' %}selected{% endif %}>Homme</option><option {% if request.form.get('sex')=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone','')}}" required></label><label>Email facultatif<input type="email" name="email" value="{{request.form.get('email','')}}"></label><label>Mot de passe<input type="password" name="password" minlength="6" required></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% for x in wilayas %}<option value="{{x.id}}" {% if request.form.get('wilaya_id')|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% for x in communes %}<option value="{{x.id}}" {% if request.form.get('commune_id')|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{request.form.get('address','')}}"></label><div class="full"><button class="btn">Créer mon compte</button> <a class="btn alt" href="/login">Annuler</a></div></form></div>''',**opts)

@app.route('/logout')
def logout():
 target=request.args.get('next') or '/login'; session.clear(); return redirect(target if target.startswith('/') else '/login')

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
 mission_planned=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='Planifiée'").fetchone()['n']; mission_active=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='En cours'").fetchone()['n']; mission_done=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status='Terminée'").fetchone()['n']; overdue=c.execute("SELECT COUNT(*) n FROM missions WHERE active=1 AND status NOT IN ('Terminée','Annulée') AND end_at IS NOT NULL AND end_at < ?",(datetime.now().isoformat(timespec='minutes'),)).fetchone()['n']; approved_today=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='approved' AND substr(approved_at,1,10)=?",(date.today().isoformat(),)).fetchone()['n']; rejected=c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND approval_status='rejected'").fetchone()['n']; new_volunteers=c.execute("SELECT COUNT(*) n FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE COALESCE(r.name,u.role)='volunteer' AND u.active=1 AND datetime(u.created_at)>=datetime('now','-7 days')").fetchone()['n']; unread=c.execute('SELECT COUNT(*) n FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0',(session['uid'],)).fetchone()['n']; c.close()
 qs='&'.join(k+'='+str(v) for k,v in f.items() if v)
 return page('Tableau de bord','''<div class="admin-home-blocks">
<div class="admin-home-block"><h3>🌳 Terrain</h3><div class="admin-home-links"><a href="/trees">🌳 Arbres</a><a href="/plantings/pending">🌱 Plantations</a><a href="/watering">💧 Arrosages</a><a href="/map">🗺 Carte</a><a href="/volunteer/gps-quick">📍 GPS rapide</a><a href="/qr">▣ QR Code</a></div></div>
<div class="admin-home-block"><h3>📂 Organisation</h3><div class="admin-home-links"><a href="/projects">📁 Projets</a><a href="/zones">📍 Zones</a><a href="/teams">👥 Équipes</a><a href="/missions">🎯 Missions</a><a href="/operations">🗓 Planifications</a><a href="/events">📆 Événements</a></div></div>
<div class="admin-home-block"><h3>👥 Personnes</h3><div class="admin-home-links"><a href="/volunteers">🙋 Bénévoles</a><a href="/members">🪪 Adhérents</a><a href="/users">🔐 Utilisateurs</a><a href="/roles">🛡 Droits d’accès</a></div></div>
<div class="admin-home-block"><h3>💰 Gestion</h3><div class="admin-home-links"><a href="/cash">💰 Caisse centrale</a><a href="/donations">🎁 Dons</a><a href="/members">🤝 Cotisations</a><a href="/stock">📦 Stock unique</a></div></div>
<div class="admin-home-block"><h3>📊 Administration</h3><div class="admin-home-links"><a href="/action-center">✅ Centre d’actions</a><a href="/notifications">🔔 Notifications</a><a href="/reports/operations">📊 Rapports</a><a href="/activity">🕘 Journal</a><a href="/backup">💾 Sauvegarde</a><a href="/species">🍃 Espèces</a></div></div></div><script>document.querySelectorAll('.admin-home-block h3').forEach(h=>h.addEventListener('click',()=>{if(innerWidth>700)return;const b=h.parentElement;document.querySelectorAll('.admin-home-block').forEach(x=>{if(x!==b)x.classList.remove('open')});b.classList.toggle('open')}));</script><div style='display:none'>
</div><form class="card toolbar" method="get">{% include 'filters' ignore missing %}<label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/">Effacer</a></form>
 <div class="grid kpis"><a class="card kpi" href="/trees?{{qs}}"><small>Arbres</small><b>{{total}}</b></a><a class="card kpi" href="/trees?watering_status=À+arroser&{{qs}}"><small>À arroser</small><b>{{watering}}</b></a><a class="card kpi" href="/trees?health_status=À+surveiller&{{qs}}"><small>Alertes santé</small><b>{{alerts}}</b></a><a class="card kpi" href="/plantings/pending"><small>Plantations en attente</small><b>{{pending}}</b></a><a class="card kpi" href="/volunteers"><small>Bénévoles</small><b>{{vols}}</b><span class="sub">{{men}} hommes • {{women}} femmes</span></a></div>
 <div class="grid kpis"><a class="card kpi" href="/trees?approval_status=approved"><small>Validées aujourd’hui</small><b>{{approved_today}}</b></a><a class="card kpi" href="/trees?approval_status=rejected"><small>Plantations refusées</small><b>{{rejected}}</b></a><a class="card kpi" href="/volunteers"><small>Nouveaux bénévoles (7 j)</small><b>{{new_volunteers}}</b></a><a class="card kpi" href="/missions"><small>Missions en retard</small><b>{{overdue}}</b></a><a class="card kpi" href="/notifications"><small>Notifications non lues</small><b>{{unread}}</b></a></div>
 <div class="grid two"><div class="card"><div class="section-title"><h3>Derniers arbres</h3><a href="/trees">Voir tout</a></div><table><tr><th>Code</th><th>Espèce</th><th>Zone</th><th>Bénévole</th><th>Statut</th></tr>{% for t in recent %}<tr><td>{{t.tree_code or 'Génération après validation'}}</td><td>{{t.species_name or t.species}}</td><td>{{t.zone_name}}</td><td>{{t.volunteer_name or t.planted_by}}</td><td><span class="badge {% if t.approval_status=='pending' %}pending{% else %}good{% endif %}">{{t.approval_status}}</span></td></tr>{% endfor %}</table></div><div class="card"><h3>Répartition bénévoles</h3><p><b>{{men}}</b> hommes</p><p><b>{{women}}</b> femmes</p><p><b>{{vols}}</b> total</p></div></div>''',f=f,qs=qs,total=total,watering=watering,alerts=alerts,pending=pending,vols=vols,men=men,women=women,recent=recent,mission_planned=mission_planned,mission_active=mission_active,mission_done=mission_done,overdue=overdue,approved_today=approved_today,rejected=rejected,new_volunteers=new_volunteers,unread=unread,**opts)

@app.route('/trees')
@login_required
def trees():
 f=filters_from_request(); c=db(); where,params=tree_where(f); opts=filter_options(c)
 rows=c.execute('''SELECT t.*,s.name_fr species_name,p.name project_name,z.name zone_name,u.name volunteer_name,c.name commune_name,w.name wilaya_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN communes c ON c.id=p.commune_id LEFT JOIN wilayas w ON w.id=p.wilaya_id WHERE '''+where+' ORDER BY t.id DESC',params).fetchall(); c.close()
 return page('Arbres','''<div class="section-title"><div><h2>Liste des arbres</h2><p class="sub">Filtrez les arbres sans GPS puis lancez le positionnement rapide.</p></div><div class="action-set"><a class="action-btn action-primary" href="/planting/new">＋ Nouvel arbre</a><a class="action-btn action-map" href="/trees?gps_status=missing">📍 Sans GPS</a><a class="action-btn action-view" href="/volunteer/gps-quick">⚡ Position GPS rapide</a></div></div><form class="card toolbar"><label>Recherche<input name="q" value="{{f.q}}"></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label><label>Position carte<select name="gps_status"><option value="">Toutes</option><option value="mapped" {% if f.gps_status=='mapped' %}selected{% endif %}>Avec GPS</option><option value="missing" {% if f.gps_status=='missing' %}selected{% endif %}>Sans GPS</option><option value="verify" {% if f.gps_status=='verify' %}selected{% endif %}>À vérifier</option></select></label><label>Santé<select name="health_status"><option value="">Toutes</option>{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if f.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Arrosage<select name="watering_status"><option value="">Tous</option>{% for x in ['À jour','À arroser','Urgent'] %}<option {% if f.watering_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/trees">Effacer</a></form><div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Espèce</th><th>Wilaya / Commune</th><th>Projet / Zone</th><th>Bénévole</th><th>GPS</th><th>Santé</th><th>Arrosage</th><th>Validation</th><th>Actions</th></tr>{% for t in rows %}<tr data-nav-key="tree-{{t.id}}"><td>{{t.tree_code or 'En attente'}}</td><td>{{t.species_name or t.species}}</td><td>{{t.wilaya_name}} / {{t.commune_name}}</td><td>{{t.project_name}} / {{t.zone_name}}</td><td>{{t.volunteer_name or t.planted_by}}</td><td>{% if t.latitude is not none and t.longitude is not none %}<span class="badge good">Positionné</span>{% else %}<span class="badge danger">Sans GPS</span>{% endif %}</td><td>{{t.health_status}}</td><td>{{t.watering_status}}</td><td>{{t.approval_status}}</td><td><div class="action-set"><a class="action-btn action-view" href="/tree/{{t.id}}">👁 Fiche</a><a class="action-btn action-map" href="/trees/{{t.id}}/map">🗺 Carte</a><a class="action-btn action-edit" href="/trees/{{t.id}}/edit">✏ Modifier</a>{% if admin %}<form method="post" action="/trees/{{t.id}}/delete" onsubmit="return confirm('Supprimer ou archiver cet arbre ?')"><button class="action-btn action-delete">🗑 Supprimer</button></form>{% endif %}</div></td></tr>{% else %}<tr><td colspan="10">Aucun arbre correspondant.</td></tr>{% endfor %}</table></div>''',rows=rows,f=f,admin=is_admin(),**opts)

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
  if errors:
   for e in errors: flash(e)
  else:
   pending=not is_admin(); status='pending' if pending else 'approved'; now=datetime.now().isoformat(timespec='minutes'); species=c.execute('SELECT name_fr FROM species WHERE id=?',(request.form['species_id'],)).fetchone()
   cur=c.execute('''INSERT INTO trees(species_id,species,project_id,zone_id,wilaya_id,commune_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,gps_accuracy,health_status,watering_status,approval_status,approved_by_user_id,approved_at,planting_type,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(request.form['species_id'],species['name_fr'] if species else None,project_id,zone_id,wilaya_id,commune_id,request.form.get('planted_at') or date.today().isoformat(),session['uid'],session['name'],request.form.get('latitude') or None,request.form.get('longitude') or None,request.form.get('gps_accuracy') or None,'Bon','À jour',status,session['uid'] if is_admin() else None,now if is_admin() else None,'free' if not project_id else ('outside_zone' if not zone_id else 'simple'),request.form.get('notes'),1,now)); tid=cur.lastrowid
   stock_source=(request.form.get('stock_source') if is_admin() else 'personal') or 'personal'; c.execute('UPDATE trees SET stock_source=? WHERE id=?',(stock_source,tid))
   if request.form.get('photo_url'): c.execute('INSERT INTO tree_photos(tree_id,photo_url,caption,created_by_user_id,created_at) VALUES(?,?,?,?,?)',(tid,request.form.get('photo_url'),'Photo de plantation',session['uid'],now))
   if status=='approved':
    code=f'TREE-{tid:06d}'; c.execute('UPDATE trees SET tree_code=?,qr_code=? WHERE id=?',(code,'MYTREE:'+code,tid))
    ok,msg=deduct_tree_from_nursery(c,tid)
    if not ok: c.rollback(); c.close(); flash(msg); return redirect('/planting/new')
   else:
    c.execute('UPDATE trees SET qr_code=? WHERE id=?',(f'MYTREE:PENDING:{tid}',tid))
    admins=c.execute("SELECT u.id FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND COALESCE(r.name,u.role) IN ('super_admin','admin')").fetchall()
    for a in admins: c.execute('INSERT INTO notifications(user_id,title,message,link,category,action_type,action_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)',(a['id'],'Nouvelle plantation à valider',f'Plantation #{tid} créée par {session.get("name")}.',f'/tree/{tid}','Plantation','tree',tid,now))
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
 if not is_admin(): return redirect('/')
 c=db(); ok,msg=deduct_tree_from_nursery(c,tid)
 if not ok: c.close(); flash(msg); return redirect('/tree/'+str(tid))
 code=f'TREE-{tid:06d}'; now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE trees SET approval_status='approved',tree_code=?,qr_code=?,approved_by_user_id=?,approved_at=?,rejection_reason=NULL WHERE id=?",(code,'MYTREE:'+code,session['uid'],now,tid)); c.execute("INSERT INTO planting_reviews(tree_id,reviewer_user_id,decision,reason,created_at) VALUES(?,?,'approved',NULL,?)",(tid,session['uid'],now)); vol=c.execute('SELECT planted_by_user_id FROM trees WHERE id=?',(tid,)).fetchone();
 if vol and vol['planted_by_user_id']: c.execute('INSERT INTO notifications(user_id,title,message,link,is_read,created_at) VALUES(?,?,?,?,0,?)',(vol['planted_by_user_id'],'Plantation acceptée',f'Votre plantation {code} a été acceptée.',f'/tree/{tid}',now))
 c.commit(); c.close(); log_action('approve','tree',tid); flash('Plantation acceptée.'); return redirect('/tree/'+str(tid))
@app.post('/plantings/<int:tid>/reject')
@login_required
def reject(tid):
 if not is_admin(): return redirect('/')
 c=db(); now=datetime.now().isoformat(timespec='minutes'); reason=clean(request.form.get('reason'));
 if not reason: c.close(); flash('Le motif du refus est obligatoire.'); return redirect('/tree/'+str(tid))
 c.execute("UPDATE trees SET approval_status='rejected',rejection_reason=? WHERE id=?",(reason,tid)); c.execute("INSERT INTO planting_reviews(tree_id,reviewer_user_id,decision,reason,created_at) VALUES(?,?,'rejected',?,?)",(tid,session['uid'],reason,now)); vol=c.execute('SELECT planted_by_user_id FROM trees WHERE id=?',(tid,)).fetchone();
 if vol and vol['planted_by_user_id']: c.execute('INSERT INTO notifications(user_id,title,message,link,is_read,created_at) VALUES(?,?,?,?,0,?)',(vol['planted_by_user_id'],'Plantation refusée',reason or 'Aucun motif indiqué.',f'/tree/{tid}',now))
 c.commit(); c.close(); log_action('reject','tree',tid,request.form.get('reason','')); flash('Plantation refusée.'); return redirect('/tree/'+str(tid))

@app.route('/trees/<int:tid>/edit',methods=['GET','POST'])
@login_required
def tree_edit(tid):
 c=db(); opts=filter_options(c); t=c.execute('SELECT * FROM trees WHERE id=?',(tid,)).fetchone()
 if not t: c.close(); return redirect('/trees')
 if request.method=='POST':
  changes={'species_id':request.form['species_id'],'project_id':request.form.get('project_id') or None,'zone_id':request.form.get('zone_id') or None,'health_status':request.form['health_status'],'watering_status':request.form['watering_status'],'latitude':request.form.get('latitude') or None,'longitude':request.form.get('longitude') or None,'notes':request.form.get('notes')}
  if is_admin() or t['approval_status']!='approved':
   c.execute('UPDATE trees SET species_id=?,project_id=?,zone_id=?,health_status=?,watering_status=?,latitude=?,longitude=?,notes=? WHERE id=?',(changes['species_id'],changes['project_id'],changes['zone_id'],changes['health_status'],changes['watering_status'],changes['latitude'],changes['longitude'],changes['notes'],tid)); c.commit(); c.close(); log_action('edit','tree',tid); flash('Fiche arbre modifiée.'); return redirect('/tree/'+str(tid))
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
   c.commit(); c.close(); log_action('water','tree',result['id'],str(liters or request.form.get('quantity_range'))); flash('Arrosage enregistré avec succès.'); return redirect('/tree/'+str(result['id']))
  c.close(); flash('Arbre approuvé introuvable.')
 return page('Arrosage rapide',"""<div class="section-title"><h2>Arrosage terrain</h2><div><a class="btn alt" href="/watering/needs">Arbres à arroser</a> <a class="btn alt" href="/watering/history">Historique</a></div></div><div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label class="full">QR ou code arbre<input name="scan" value="{{prefill}}" autofocus required></label><label>Quantité<select name="quantity_range"><option>1–5 L</option><option>5–10 L</option><option>10–15 L</option><option>15–25 L</option></select></label><label>Litres exacts<input type="number" min="0" step="0.1" name="quantity_liters"></label><label>Source<select name="source"><option>Bidon</option><option>Camion</option><option>Réservoir</option><option>Goutte-à-goutte</option><option>Autre</option></select></label><label>État observé<select name="tree_condition"><option>Bon</option><option>À surveiller</option><option>En danger</option><option>Mort</option></select></label><label>Photo facultative (URL)<input type="url" name="photo_url"></label><label class="full">Observation<textarea name="notes"></textarea></label><input type="hidden" name="latitude" id="lat"><input type="hidden" name="longitude" id="lon"><div class="full"><span id="gpsWater" class="sub">Position GPS facultative.</span></div><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/">Annuler</a></div></form></div><script>if(navigator.geolocation){navigator.geolocation.getCurrentPosition(p=>{lat.value=p.coords.latitude;lon.value=p.coords.longitude;gpsWater.textContent='Position GPS ajoutée.'},()=>gpsWater.textContent='Arrosage possible sans GPS.',{enableHighAccuracy:true,timeout:8000})}</script>""",prefill=prefill)

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
 f=filters_from_request(); include_inactive=request.args.get('inactive')=='1'; c=db(); w=["COALESCE(r.name,u.role)='volunteer'"];p=[]
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
   except DBIntegrityError: errors=['Impossible d’enregistrer : le téléphone, l’e-mail ou le nom d’utilisateur existe déjà.']
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

@app.route('/volunteers/<int:uid>')
@login_required
def volunteer_detail(uid):
 c=db(); u=c.execute('SELECT u.*,r.label role_label,w.name wilaya_name,cm.name commune_name,t.name team_name FROM users u LEFT JOIN roles r ON r.id=u.role_id LEFT JOIN wilayas w ON w.id=u.wilaya_id LEFT JOIN communes cm ON cm.id=u.commune_id LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=?',(uid,)).fetchone()
 if not u: c.close(); return ('Introuvable',404)
 stats=dict(plantings=c.execute('SELECT COUNT(*) n FROM trees WHERE planted_by_user_id=? AND active=1',(uid,)).fetchone()['n'],waterings=c.execute('SELECT COUNT(*) n FROM watering_logs WHERE user_id=?',(uid,)).fetchone()['n'],missions=c.execute('SELECT COUNT(*) n FROM mission_participants WHERE user_id=?',(uid,)).fetchone()['n'])
 recent_trees=c.execute('SELECT id,tree_code,planted_at,approval_status FROM trees WHERE planted_by_user_id=? ORDER BY id DESC LIMIT 8',(uid,)).fetchall(); recent_water=c.execute('SELECT wl.watered_at,t.tree_code,wl.quantity_range FROM watering_logs wl LEFT JOIN trees t ON t.id=wl.tree_id WHERE wl.user_id=? ORDER BY wl.id DESC LIMIT 8',(uid,)).fetchall(); c.close()
 return page('Fiche bénévole','''<div class="section-title"><h2>{{u.name}}</h2><div>{% if admin %}<a class="btn" href="/volunteers/{{u.id}}/edit">Modifier</a> <a class="btn amber" href="/volunteers/{{u.id}}/permissions">Droits d’accès</a>{% endif %} <a class="btn alt" href="/volunteers">Retour</a></div></div><div class="grid kpis" style="grid-template-columns:repeat(3,1fr)"><div class="card kpi"><small>Plantations</small><b>{{stats.plantings}}</b></div><div class="card kpi"><small>Arrosages</small><b>{{stats.waterings}}</b></div><div class="card kpi"><small>Missions</small><b>{{stats.missions}}</b></div></div><div class="grid two"><div class="card"><h3>Profil</h3>{% if u.photo_url %}<img src="{{u.photo_url}}" alt="Photo" style="max-width:130px;border-radius:12px">{% endif %}<p><b>État :</b> {{'Actif' if u.active else 'Inactif'}}</p><p><b>Téléphone :</b> {{u.phone}}</p><p><b>E-mail :</b> {{u.email or '—'}}</p><p><b>Sexe :</b> {{u.sex or '—'}}</p><p><b>Naissance :</b> {{u.birth_date or '—'}}</p><p><b>Wilaya / Commune :</b> {{u.wilaya_name or '—'}} / {{u.commune_name or '—'}}</p><p><b>Adresse :</b> {{u.address or '—'}}</p><p><b>Équipe :</b> {{u.team_name or '—'}}</p><p><b>Compétences :</b> {{u.skills or '—'}}</p><p><b>Disponibilités :</b> {{u.availability or '—'}}</p><p><b>Dernière connexion :</b> {{u.last_login or 'Jamais'}}</p></div><div><div class="card"><h3>Dernières plantations</h3>{% for x in recent_trees %}<div class="priority"><b><a href="/tree/{{x.id}}">{{x.tree_code or 'En attente'}}</a></b><span>{{x.planted_at or '—'}} • {{'Acceptée' if x.approval_status=='approved' else ('En attente' if x.approval_status=='pending' else 'Refusée')}}</span>{% if admin and x.approval_status=='pending' %}<span><a href="/tree/{{x.id}}">Traiter</a> · <a href="/trees/{{x.id}}/map">Carte</a></span>{% endif %}</div>{% else %}<p class="sub">Aucune plantation.</p>{% endfor %}</div><div class="card"><h3>Derniers arrosages</h3>{% for x in recent_water %}<div class="priority"><b>{{x.tree_code or 'Arbre'}}</b><span>{{x.watered_at}} • {{x.quantity_range}}</span></div>{% else %}<p class="sub">Aucun arrosage.</p>{% endfor %}</div></div></div>''',u=u,stats=stats,recent_trees=recent_trees,recent_water=recent_water,admin=is_admin())

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
 c=db(); q=request.args.get('q','').strip(); status=request.args.get('status',''); active=request.args.get('active','1'); w=['1=1']; params=[]
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

PROJECT_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Code<input name="code" value="{{request.form.get('code',p.code if p else '')}}" required></label><label>Nom<input name="name" value="{{request.form.get('name',p.name if p else '')}}" required></label><label>Statut<select name="status">{% set st=request.form.get('status',p.status if p else 'Brouillon') %}{% for x in ['Brouillon','Étude et préparation','Validé','En cours','Terminé'] %}<option {% if st==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Responsable<select name="manager_user_id"><option value="">—</option>{% set mid=request.form.get('manager_user_id',p.manager_user_id if p else '') %}{% for x in managers %}<option value="{{x.id}}" {% if mid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Objectif arbres<input type="number" min="0" name="target_trees" value="{{request.form.get('target_trees',p.target_trees if p else 0)}}"></label><label>Budget<input type="number" min="0" step="0.01" name="budget" value="{{request.form.get('budget',p.budget if p else 0)}}"></label><label>Date début<input type="date" name="start_date" value="{{request.form.get('start_date',p.start_date if p and p.start_date else '')}}"></label><label>Date fin<input type="date" name="end_date" value="{{request.form.get('end_date',p.end_date if p and p.end_date else '')}}"></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% set wid=request.form.get('wilaya_id',p.wilaya_id if p else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% set cid=request.form.get('commune_id',p.commune_id if p else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Lieu<input name="location" value="{{request.form.get('location',p.location if p and p.location else '')}}"></label>{% if p %}<label>État<select name="active"><option value="1" {% if request.form.get('active',p.active)|string=='1' %}selected{% endif %}>Actif</option><option value="0" {% if request.form.get('active',p.active)|string=='0' %}selected{% endif %}>Archivé</option></select></label>{% endif %}<label class="full">Description<textarea name="description">{{request.form.get('description',p.description if p and p.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>"""

@app.route('/projects/new',methods=['GET','POST'])
@login_required
def project_new():
 if not is_admin(): return redirect('/projects')
 c=db(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  code=request.form['code'].strip(); name=request.form['name'].strip(); errors=[]
  if c.execute('SELECT id FROM projects WHERE code=?',(code,)).fetchone(): errors.append('Ce code projet existe déjà.')
  if not errors:
   now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,manager_user_id,active,description,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)',(code,name,request.form.get('status') or 'Brouillon',request.form.get('target_trees') or 0,request.form.get('budget') or 0,request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,request.form.get('location'),request.form.get('manager_user_id') or None,request.form.get('description'),request.form.get('start_date') or None,request.form.get('end_date') or None,now,now)); c.commit(); pid=cur.lastrowid; c.close(); log_action('create','project',pid,name); flash('Projet créé.'); return redirect('/projects/'+str(pid))
  for e in errors: flash(e)
 c.close(); return page('Nouveau projet',PROJECT_FORM,p=None,managers=managers,cancel_url='/projects',**opts)

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
  code=request.form['code'].strip(); duplicate=c.execute('SELECT id FROM projects WHERE code=? AND id<>?',(code,pid)).fetchone()
  if duplicate: flash('Ce code projet existe déjà.')
  else:
   c.execute('UPDATE projects SET code=?,name=?,status=?,target_trees=?,budget=?,wilaya_id=?,commune_id=?,location=?,manager_user_id=?,active=?,description=?,start_date=?,end_date=?,updated_at=? WHERE id=?',(code,request.form['name'].strip(),request.form.get('status'),request.form.get('target_trees') or 0,request.form.get('budget') or 0,request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,request.form.get('location'),request.form.get('manager_user_id') or None,request.form.get('active',1),request.form.get('description'),request.form.get('start_date') or None,request.form.get('end_date') or None,datetime.now().isoformat(timespec='minutes'),pid)); c.commit(); c.close(); log_action('edit','project',pid); flash('Projet modifié.'); return redirect('/projects/'+str(pid))
 c.close(); return page('Modifier projet',PROJECT_FORM,p=p,managers=managers,cancel_url='/projects/'+str(pid),**opts)

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
 now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO projects(code,name,status,target_trees,budget,wilaya_id,commune_id,location,manager_user_id,active,description,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)',(code,p['name']+' (copie)','Brouillon',p['target_trees'],p['budget'],p['wilaya_id'],p['commune_id'],p['location'],p['manager_user_id'],p['description'],p['start_date'],p['end_date'],now,now)); c.commit(); nid=cur.lastrowid; c.close(); log_action('duplicate','project',nid); flash('Projet dupliqué.'); return redirect('/projects/'+str(nid))

@app.route('/zones')
@login_required
def zones_page():
 c=db(); q=request.args.get('q','').strip(); project_id=request.args.get('project_id',''); wilaya_id=request.args.get('wilaya_id',''); commune_id=request.args.get('commune_id',''); manager_id=request.args.get('manager_id',''); active=request.args.get('active','1'); w=['1=1']; params=[]
 if q: w.append('(z.code LIKE ? OR z.name LIKE ? OR z.description LIKE ?)'); params += ['%'+q+'%']*3
 if project_id: w.append('z.project_id=?'); params.append(project_id)
 if wilaya_id: w.append('z.wilaya_id=?'); params.append(wilaya_id)
 if commune_id: w.append('z.commune_id=?'); params.append(commune_id)
 if manager_id: w.append('z.manager_user_id=?'); params.append(manager_id)
 if active!='': w.append('z.active=?'); params.append(active)
 rows=c.execute("""SELECT z.*,p.name project_name,u.name manager_name,w.name wilaya_name,cm.name commune_name,(SELECT COUNT(*) FROM trees t WHERE t.zone_id=z.id AND t.active=1) tree_count,(SELECT COUNT(*) FROM teams tm WHERE tm.zone_id=z.id AND tm.active=1) team_count,(SELECT COUNT(*) FROM trees t WHERE t.zone_id=z.id AND t.active=1 AND (t.watering_status!='À jour' OR t.health_status IN ('À surveiller','Urgent','Critique'))) priority_count FROM zones z LEFT JOIN projects p ON p.id=z.project_id LEFT JOIN users u ON u.id=z.manager_user_id LEFT JOIN wilayas w ON w.id=z.wilaya_id LEFT JOIN communes cm ON cm.id=z.commune_id WHERE """+' AND '.join(w)+' ORDER BY z.active DESC,z.name',params).fetchall()
 projects=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall(); wilayas=c.execute('SELECT id,name FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT id,name FROM communes WHERE active=1 ORDER BY name').fetchall(); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); c.close()
 return page('Zones',"""<div class="section-title"><h2>Zones</h2>{% if admin %}<a class="btn" href="/zones/new">+ Nouvelle zone</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}" placeholder="Nom, code ou description"></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="manager_id"><option value="">Tous</option>{% for x in managers %}<option value="{{x.id}}" {% if manager_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>État<select name="active"><option value="">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actives</option><option value="0" {% if active=='0' %}selected{% endif %}>Archivées</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/zones">Annuler les filtres</a></form><div class="card" style="overflow:auto"><table><tr><th>Zone</th><th>Projet</th><th>Responsable</th><th>Wilaya / Commune</th><th>Superficie</th><th>Arbres</th><th>Priorités</th><th>Équipes</th><th>État</th><th>Actions</th></tr>{% for z in rows %}<tr><td><a href="/zones/{{z.id}}"><b>{{z.name}}</b></a><div class="sub">{{z.code or 'Sans code'}}</div></td><td>{{z.project_name or '—'}}</td><td>{{z.manager_name or '—'}}</td><td>{{z.wilaya_name or '—'}} / {{z.commune_name or '—'}}</td><td>{{z.area or 0}} ha</td><td>{{z.tree_count}} / {{z.target_trees or 0}}</td><td><span class="badge {% if z.priority_count %}danger{% else %}good{% endif %}">{{z.priority_count}}</span></td><td>{{z.team_count}}</td><td><span class="badge {% if z.active %}good{% else %}danger{% endif %}">{{'Active' if z.active else 'Archivée'}}</span></td><td><a class="btn alt" href="/zones/{{z.id}}">Fiche</a>{% if admin %} <a class="btn alt" href="/zones/{{z.id}}/edit">Modifier</a> <form method="post" action="/zones/{{z.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cette zone ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="10">Aucune zone ne correspond aux filtres.</td></tr>{% endfor %}</table></div>""",rows=rows,projects=projects,wilayas=wilayas,communes=communes,managers=managers,q=q,project_id=project_id,wilaya_id=wilaya_id,commune_id=commune_id,manager_id=manager_id,active=active,admin=is_admin())

ZONE_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Projet<select name="project_id" required>{% set pid=request.form.get('project_id',z.project_id if z else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Code<input name="code" value="{{request.form.get('code',z.code if z and z.code else '')}}"></label><label>Nom<input name="name" value="{{request.form.get('name',z.name if z else '')}}" required></label><label>Responsable<select name="manager_user_id"><option value="">—</option>{% set mid=request.form.get('manager_user_id',z.manager_user_id if z else '') %}{% for x in managers %}<option value="{{x.id}}" {% if mid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% set wid=request.form.get('wilaya_id',z.wilaya_id if z else '') %}{% for x in wilayas %}<option value="{{x.id}}" {% if wid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% set cid=request.form.get('commune_id',z.commune_id if z else '') %}{% for x in communes %}<option value="{{x.id}}" {% if cid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Superficie (ha)<input type="number" step="0.01" min="0" name="area" value="{{request.form.get('area',z.area if z else 0)}}"></label><label>Objectif arbres<input type="number" min="0" name="target_trees" value="{{request.form.get('target_trees',z.target_trees if z else 0)}}"></label><label>Latitude<input type="number" step="any" name="latitude" value="{{request.form.get('latitude',z.latitude if z and z.latitude is not none else '')}}"></label><label>Longitude<input type="number" step="any" name="longitude" value="{{request.form.get('longitude',z.longitude if z and z.longitude is not none else '')}}"></label><label>Couleur<input type="color" name="color" value="{{request.form.get('color',z.color if z and z.color else '#3a7d44')}}"></label>{% if z %}<label>État<select name="active"><option value="1" {% if request.form.get('active',z.active)|string=='1' %}selected{% endif %}>Active</option><option value="0" {% if request.form.get('active',z.active)|string=='0' %}selected{% endif %}>Archivée</option></select></label>{% endif %}<label class="full">Description<textarea name="description">{{request.form.get('description',z.description if z and z.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>"""

@app.route('/zones/new',methods=['GET','POST'])
@login_required
def zone_new():
 if not is_admin(): return redirect('/zones')
 c=db(); opts=filter_options(c); managers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO zones(project_id,wilaya_id,commune_id,code,name,area,target_trees,color,manager_user_id,active,description,latitude,longitude,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)',(request.form['project_id'],request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,request.form.get('code'),request.form['name'].strip(),request.form.get('area') or 0,request.form.get('target_trees') or 0,request.form.get('color') or '#3a7d44',request.form.get('manager_user_id') or None,request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,now,now)); c.commit(); zid=cur.lastrowid; c.close(); log_action('create','zone',zid); flash('Zone créée.'); return redirect('/zones/'+str(zid))
 c.close(); return page('Nouvelle zone',ZONE_FORM,z=None,managers=managers,cancel_url='/zones',**opts)

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
  c.execute('UPDATE zones SET project_id=?,wilaya_id=?,commune_id=?,code=?,name=?,area=?,target_trees=?,color=?,manager_user_id=?,active=?,description=?,latitude=?,longitude=?,updated_at=? WHERE id=?',(request.form['project_id'],request.form.get('wilaya_id') or None,request.form.get('commune_id') or None,request.form.get('code'),request.form['name'].strip(),request.form.get('area') or 0,request.form.get('target_trees') or 0,request.form.get('color') or '#3a7d44',request.form.get('manager_user_id') or None,request.form.get('active',1),request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,datetime.now().isoformat(timespec='minutes'),zid)); c.commit(); c.close(); log_action('edit','zone',zid); flash('Zone modifiée.'); return redirect('/zones/'+str(zid))
 c.close(); return page('Modifier zone',ZONE_FORM,z=z,managers=managers,cancel_url='/zones/'+str(zid),**opts)

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
   except DBIntegrityError: errors=['Impossible d’enregistrer cet utilisateur : donnée déjà utilisée.']
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
 rows=c.execute("""SELECT t.id,t.tree_code,t.qr_code,t.latitude,t.longitude,t.gps_accuracy,t.health_status,t.watering_status,t.last_watered_at,t.approval_status,t.planted_at,t.notes,s.name_fr species_name,p.name project_name,z.name zone_name,cm.name commune_name,w.name wilaya_name,u.name volunteer_name
 FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id LEFT JOIN users u ON u.id=t.planted_by_user_id LEFT JOIN communes cm ON cm.id=COALESCE(t.commune_id,z.commune_id,p.commune_id) LEFT JOIN wilayas w ON w.id=COALESCE(t.wilaya_id,z.wilaya_id,p.wilaya_id)
 WHERE """+where+(" AND t.approval_status='approved'" if not is_admin() else "")+" AND t.latitude IS NOT NULL AND t.longitude IS NOT NULL ORDER BY t.id DESC",params).fetchall(); c.close()
 return jsonify([dict(x) for x in rows])

@app.route('/map')
@login_required
def real_map():
 f=filters_from_request(); c=db(); opts=filter_options(c); c.close()
 return page('Carte réelle des arbres',"""<form class="card toolbar noprint" method="get">
 <label>Wilaya<select name="wilaya_id"><option value="">Toutes</option>{% for x in wilayas %}<option value="{{x.id}}" {% if f.wilaya_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>
 <label>Commune<select name="commune_id"><option value="">Toutes</option>{% for x in communes %}<option value="{{x.id}}" {% if f.commune_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>
 <label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if f.project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>
 <label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if f.zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>
 <label>Espèce<select name="species_id"><option value="">Toutes</option>{% for x in species %}<option value="{{x.id}}" {% if f.species_id|string==x.id|string %}selected{% endif %}>{{x.name_fr}}</option>{% endfor %}</select></label>
 <label>Santé<select name="health_status"><option value="">Toutes</option>{% for x in ['Bon','À surveiller','En danger','Mort'] %}<option {% if f.health_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>
 <label>Arrosage<select name="watering_status"><option value="">Tous</option>{% for x in ['À jour','À arroser','Urgent'] %}<option {% if f.watering_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>
 <button class="btn">Appliquer</button><a class="btn alt" href="/map">Effacer</a><button type="button" class="btn" id="locateBtn">📍 Ma position</button></form>
 <div class="grid two"><div class="card"><div id="map" class="real-map"></div></div><div class="card"><h3>Arbres proches de moi</h3><div id="locationStatus" class="sub">Appuyez sur « Ma position » pour calculer les distances.</div><div id="nearbyList"></div></div></div>
 <script>
 const params=new URLSearchParams(window.location.search); let treeData=[]; let userMarker=null; let userLatLng=null;
 const map=L.map('map').setView([35.697,-0.633],11);
 L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'&copy; OpenStreetMap'}).addTo(map);
 const group=L.featureGroup().addTo(map);
 function esc(v){return String(v??'—').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));}
 function color(t){if(t.health_status==='En danger'||t.health_status==='Mort')return '#c43d3d';if(t.health_status==='À surveiller')return '#d89a19';if(t.watering_status==='Urgent')return '#7e3fc3';if(t.watering_status==='À arroser')return '#2878c7';return '#2f8b4b';}
 function popup(t){return `<b>${esc(t.tree_code)}</b><br>Espèce : ${esc(t.species_name)}<br>Wilaya : ${esc(t.wilaya_name)}<br>Commune : ${esc(t.commune_name)}<br>Projet : ${esc(t.project_name)}<br>Zone : ${esc(t.zone_name)}<br>Santé : ${esc(t.health_status)}<br>Arrosage : ${esc(t.watering_status)}<br>Planté par : ${esc(t.volunteer_name)}<br>Dernier arrosage : ${esc(t.last_watered_at)}<br><a href="/tree/${t.id}">Ouvrir la fiche</a> • <a target="_blank" href="https://www.google.com/maps/dir/?api=1&destination=${t.latitude},${t.longitude}">Itinéraire</a>${t.approval_status==='pending'?'<br><b style="color:#bd8120">En attente — valider depuis la fiche</b>':''}`;}
 fetch('/api/trees?'+params.toString()).then(r=>r.json()).then(data=>{treeData=data;data.forEach(t=>{const marker=L.circleMarker([t.latitude,t.longitude],{radius:9,color:'#fff',weight:3,fillColor:color(t),fillOpacity:1}).bindTooltip(`${t.tree_code} — ${t.species_name||''}`,{sticky:true}).bindPopup(popup(t));marker.addTo(group);});if(data.length){map.fitBounds(group.getBounds().pad(.18));}});
 function distanceKm(a,b,c,d){const R=6371,rad=x=>x*Math.PI/180;const x=rad(c-a),y=rad(d-b);const q=Math.sin(x/2)**2+Math.cos(rad(a))*Math.cos(rad(c))*Math.sin(y/2)**2;return 2*R*Math.asin(Math.sqrt(q));}
 function showNearby(){if(!userLatLng)return;const sorted=treeData.map(t=>({...t,d:distanceKm(userLatLng.lat,userLatLng.lng,t.latitude,t.longitude)})).sort((a,b)=>a.d-b.d).slice(0,15);document.getElementById('nearbyList').innerHTML=sorted.length?sorted.map(t=>`<div class="priority"><b>${esc(t.tree_code)} — ${esc(t.species_name)}</b><span>${t.d<1?Math.round(t.d*1000)+' m':t.d.toFixed(2)+' km'} • ${esc(t.zone_name)} • ${esc(t.watering_status)}</span></div>`).join(''):'<p>Aucun arbre géolocalisé.</p>';}
 document.getElementById('locateBtn').onclick=()=>{const st=document.getElementById('locationStatus');if(!navigator.geolocation){st.textContent='GPS non pris en charge.';return;}st.textContent='Recherche de votre position…';navigator.geolocation.getCurrentPosition(pos=>{userLatLng={lat:pos.coords.latitude,lng:pos.coords.longitude};if(userMarker)map.removeLayer(userMarker);userMarker=L.marker(userLatLng).addTo(map).bindPopup('Votre position actuelle<br>Précision : '+Math.round(pos.coords.accuracy)+' m').openPopup();map.setView(userLatLng,17);st.textContent='Position trouvée. Précision : '+Math.round(pos.coords.accuracy)+' m.';showNearby();},err=>{st.textContent='Localisation refusée ou indisponible : '+err.message;},{enableHighAccuracy:true,timeout:15000,maximumAge:0});};
 </script>""",f=f,**opts)

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
 payload=request.url_root.rstrip('/')+'/tree/'+str(tid)+'?token='+str(token); img=qrcode.make(payload); b=io.BytesIO(); img.save(b,format='PNG'); b.seek(0); return send_file(b,mimetype='image/png',download_name=(t['tree_code'] or f'plantation-{tid}')+'.png')


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

@app.route('/teams')
@login_required
def teams_page():
 c=db(); q=request.args.get('q','').strip(); project_id=request.args.get('project_id',''); zone_id=request.args.get('zone_id',''); active=request.args.get('active','1'); w=['1=1'];p=[]
 if q:w.append('(tm.name LIKE ? OR tm.mission LIKE ? OR tm.phone LIKE ?)');p += ['%'+q+'%']*3
 if project_id:w.append('tm.project_id=?');p.append(project_id)
 if zone_id:w.append('tm.zone_id=?');p.append(zone_id)
 if active!='':w.append('tm.active=?');p.append(active)
 rows=c.execute("""SELECT tm.*,p.name project_name,z.name zone_name,u.name leader_name,(SELECT COUNT(*) FROM team_members m WHERE m.team_id=tm.id AND m.status='active') member_count,(SELECT COUNT(*) FROM team_join_requests r WHERE r.team_id=tm.id AND r.status='pending') pending_count,(SELECT COUNT(*) FROM missions ms WHERE ms.team_id=tm.id AND ms.active=1) mission_count,(SELECT COUNT(*) FROM events ev WHERE ev.team_id=tm.id AND ev.active=1) event_count FROM teams tm LEFT JOIN projects p ON p.id=tm.project_id LEFT JOIN zones z ON z.id=tm.zone_id LEFT JOIN users u ON u.id=tm.leader_user_id WHERE """+' AND '.join(w)+' ORDER BY tm.active DESC,tm.id DESC',p).fetchall(); opts=filter_options(c); c.close()
 return page('Équipes',"""<div class="section-title"><h2>Liste des équipes</h2>{% if admin %}<a class="btn" href="/teams/new">+ Nouvelle équipe</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}"></label><label>Projet<select name="project_id"><option value="">Tous</option>{% for x in projects %}<option value="{{x.id}}" {% if project_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">Toutes</option>{% for x in zones %}<option value="{{x.id}}" {% if zone_id|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>État<select name="active"><option value="">Tous</option><option value="1" {% if active=='1' %}selected{% endif %}>Actives</option><option value="0" {% if active=='0' %}selected{% endif %}>Inactives</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/teams">Effacer</a></form><div class="card"><table><tr><th>Équipe</th><th>Chef</th><th>Projet / Zone</th><th>Membres</th><th>Demandes</th><th>Missions</th><th>Événements</th><th>État</th><th>Actions</th></tr>{% for t in rows %}<tr><td><a href="/teams/{{t.id}}"><b>{{t.name}}</b></a><div class="sub">{{t.phone or ''}}</div></td><td>{{t.leader_name or '—'}}</td><td>{{t.project_name or '—'}} / {{t.zone_name or '—'}}</td><td>{{t.member_count}}</td><td>{{t.pending_count}}</td><td>{{t.mission_count}}</td><td>{{t.event_count}}</td><td><span class="badge {% if t.active %}good{% else %}danger{% endif %}">{{'Active' if t.active else 'Inactive'}}</span></td><td><a class="btn alt" href="/teams/{{t.id}}">Ouvrir</a>{% if admin %} <a class="btn alt" href="/teams/{{t.id}}/edit">Modifier</a> <form method="post" action="/teams/{{t.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou désactiver cette équipe ?')"><button class="btn red">Supprimer</button></form>{% endif %}</td></tr>{% endfor %}</table></div>""",rows=rows,q=q,project_id=project_id,zone_id=zone_id,active=active,admin=is_admin(),**opts)

TEAM_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Nom<input name="name" value="{{request.form.get('name',t.name if t else '')}}" required></label><label>Chef d’équipe<select name="leader_user_id"><option value="">—</option>{% set lid=request.form.get('leader_user_id',t.leader_user_id if t else '') %}{% for x in leaders %}<option value="{{x.id}}" {% if lid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">—</option>{% set pid=request.form.get('project_id',t.project_id if t else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">—</option>{% set zid=request.form.get('zone_id',t.zone_id if t else '') %}{% for x in zones %}<option value="{{x.id}}" {% if zid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Téléphone<input name="phone" value="{{request.form.get('phone',t.phone if t and t.phone else '')}}"></label>{% if t %}<label>État<select name="active"><option value="1" {% if request.form.get('active',t.active)|string=='1' %}selected{% endif %}>Active</option><option value="0" {% if request.form.get('active',t.active)|string=='0' %}selected{% endif %}>Inactive</option></select></label>{% endif %}<label class="full">Mission / rôle de l’équipe<textarea name="mission">{{request.form.get('mission',t.mission if t and t.mission else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>"""

@app.route('/teams/new',methods=['GET','POST'])
@login_required
def team_new():
 if not is_admin():return redirect('/teams')
 c=db(); opts=filter_options(c); leaders=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes'); cur=c.execute('INSERT INTO teams(name,leader_user_id,project_id,zone_id,phone,mission,active,created_by_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?,?)',(request.form['name'].strip(),request.form.get('leader_user_id') or None,request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('phone'),request.form.get('mission'),session['uid'],now,now)); tid=cur.lastrowid
  if request.form.get('leader_user_id'): c.execute("INSERT OR IGNORE INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?)",(tid,request.form['leader_user_id'],now,session['uid'],now)); c.execute('UPDATE users SET team_id=? WHERE id=?',(tid,request.form['leader_user_id']))
  c.commit(); c.close(); log_action('create','team',tid); flash('Équipe créée.'); return redirect('/teams/'+str(tid))
 c.close(); return page('Nouvelle équipe',TEAM_FORM,t=None,leaders=leaders,cancel_url='/teams',**opts)

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
 if not is_admin():return redirect('/teams')
 c=db();t=c.execute('SELECT * FROM teams WHERE id=?',(tid,)).fetchone();opts=filter_options(c);leaders=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
 if not t:c.close();return ('Introuvable',404)
 if request.method=='POST':
  old=t['leader_user_id']; new=request.form.get('leader_user_id') or None; now=datetime.now().isoformat(timespec='minutes'); c.execute('UPDATE teams SET name=?,leader_user_id=?,project_id=?,zone_id=?,phone=?,mission=?,active=?,updated_at=? WHERE id=?',(request.form['name'].strip(),new,request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('phone'),request.form.get('mission'),request.form.get('active',1),now,tid))
  if new: c.execute("INSERT OR IGNORE INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?)",(tid,new,now,session['uid'],now)); c.execute('UPDATE team_members SET status=\'active\' WHERE team_id=? AND user_id=?',(tid,new)); c.execute('UPDATE users SET team_id=? WHERE id=?',(tid,new))
  if old and str(old)!=str(new): c.execute('UPDATE users SET team_id=NULL WHERE id=? AND team_id=?',(old,tid))
  c.commit();c.close();log_action('edit','team',tid);flash('Équipe modifiée.');return redirect('/teams/'+str(tid))
 c.close();return page('Modifier équipe',TEAM_FORM,t=t,leaders=leaders,cancel_url='/teams/'+str(tid),**opts)

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
 c=db(); now=datetime.now().isoformat(timespec='minutes'); existing=c.execute("SELECT id,status FROM team_join_requests WHERE team_id=? AND user_id=? ORDER BY id DESC LIMIT 1",(tid,session['uid'])).fetchone()
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
 if r and r['status']=='pending': c.execute("UPDATE team_join_requests SET status='accepted',reviewed_by_user_id=?,reviewed_at=? WHERE id=?",(session['uid'],now,rid)); c.execute("INSERT INTO team_members(team_id,user_id,status,joined_at,approved_by_user_id,approved_at) VALUES(?,?,'active',?,?,?) ON CONFLICT(team_id,user_id) DO UPDATE SET status=excluded.status,joined_at=excluded.joined_at,approved_by_user_id=excluded.approved_by_user_id,approved_at=excluded.approved_at",(r['team_id'],r['user_id'],now,session['uid'],now)); c.execute('UPDATE users SET team_id=? WHERE id=?',(r['team_id'],r['user_id'])); c.commit()
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
 c=db(); q=clean(request.args.get('q')); status=clean(request.args.get('status')); event_type=clean(request.args.get('event_type')); w=['e.active=1']; p=[]
 if q: w.append('(e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)'); p += ['%'+q+'%']*3
 if status: w.append('e.status=?'); p.append(status)
 if event_type: w.append('e.event_type=?'); p.append(event_type)
 rows=c.execute("SELECT e.*,p.name project_name,z.name zone_name,tm.name team_name,(SELECT COUNT(*) FROM event_participants ep WHERE ep.event_id=e.id AND ep.status='Inscrit') participant_count FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id LEFT JOIN teams tm ON tm.id=e.team_id WHERE "+' AND '.join(w)+' ORDER BY e.start_at ASC',p).fetchall(); c.close()
 return page('Événements',"""<div class="section-title"><h2>Calendrier des événements</h2>{% if admin %}<a class="btn" href="/events/new">+ Nouvel événement</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}"></label><label>Type<select name="event_type"><option value="">Tous</option>{% for x in ['Plantation','Arrosage','Nettoyage','Réunion','Formation'] %}<option {% if event_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>État<select name="status"><option value="">Tous</option>{% for x in ['Planifié','Ouvert','Complet','Terminé','Annulé'] %}<option {% if status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/events">Effacer</a></form><div class="grid two">{% for e in rows %}<div class="card"><div class="section-title"><div><span class="badge watch">{{e.event_type}}</span><h3><a href="/events/{{e.id}}">{{e.title}}</a></h3></div><span class="badge {% if e.status=='Annulé' %}danger{% elif e.status=='Terminé' %}good{% else %}watch{% endif %}">{{e.status}}</span></div><p><b>Début :</b> {{e.start_at}}</p><p><b>Lieu :</b> {{e.location or e.zone_name or e.project_name or '—'}}</p><p><b>Participants :</b> {{e.participant_count}}{% if e.max_participants %} / {{e.max_participants}}{% endif %}</p><a class="btn alt" href="/events/{{e.id}}">Ouvrir</a>{% if admin %} <form method="post" action="/events/{{e.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cet événement ?')"><button class="btn red">Supprimer</button></form>{% endif %}</div>{% else %}<div class="card">Aucun événement.</div>{% endfor %}</div>""",rows=rows,q=q,status=status,event_type=event_type,admin=is_admin())

EVENT_FORM="""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Titre<input name="title" value="{{request.form.get('title',e.title if e else '')}}" required></label><label>Type<select name="event_type">{% set et=request.form.get('event_type',e.event_type if e else 'Plantation') %}{% for x in ['Plantation','Arrosage','Nettoyage','Réunion','Formation'] %}<option {% if et==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at" value="{{request.form.get('start_at',e.start_at if e else '')}}" required></label><label>Fin<input type="datetime-local" name="end_at" value="{{request.form.get('end_at',e.end_at if e and e.end_at else '')}}"></label><label>Lieu<input name="location" value="{{request.form.get('location',e.location if e and e.location else '')}}"></label><label>Places maximum <span class="sub">(facultatif — vide = illimité)</span><input type="number" min="1" name="max_participants" placeholder="Laisser vide = illimité" value="{{request.form.get('max_participants',(e.max_participants if e and e.max_participants else ''))}}"></label><label>Projet<select name="project_id"><option value="">—</option>{% set pid=request.form.get('project_id',e.project_id if e else '') %}{% for x in projects %}<option value="{{x.id}}" {% if pid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">—</option>{% set zid=request.form.get('zone_id',e.zone_id if e else '') %}{% for x in zones %}<option value="{{x.id}}" {% if zid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Équipe<select name="team_id"><option value="">—</option>{% set tid=request.form.get('team_id',e.team_id if e else '') %}{% for x in teams %}<option value="{{x.id}}" {% if tid|string==x.id|string %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label>{% if e %}<label>État<select name="status">{% for x in ['Planifié','Ouvert','Complet','Terminé','Annulé'] %}<option {% if request.form.get('status',e.status)==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>{% endif %}<label>Latitude<input name="latitude" value="{{request.form.get('latitude',e.latitude if e and e.latitude is not none else '')}}"></label><label>Longitude<input name="longitude" value="{{request.form.get('longitude',e.longitude if e and e.longitude is not none else '')}}"></label><label class="full">Description<textarea name="description">{{request.form.get('description',e.description if e and e.description else '')}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="{{cancel_url}}">Annuler</a></div></form></div>"""

def event_form_context(c):
 return dict(projects=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall(),zones=c.execute('SELECT id,name FROM zones WHERE active=1 ORDER BY name').fetchall(),teams=c.execute('SELECT id,name FROM teams WHERE active=1 ORDER BY name').fetchall())

@app.route('/events/new',methods=['GET','POST'])
@login_required
@permission_required('event.manage')
def event_new():
 c=db(); ctx=event_form_context(c)
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes'); sql="INSERT INTO events(title,event_type,status,start_at,end_at,location,project_id,zone_id,team_id,max_participants,description,latitude,longitude,active,created_by_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)"; cur=c.execute(sql,(clean(request.form.get('title')),request.form.get('event_type'),request.form.get('status','Planifié'),request.form.get('start_at'),request.form.get('end_at') or None,clean(request.form.get('location')) or None,request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('team_id') or None,int(request.form.get('max_participants') or 0),clean(request.form.get('description')) or None,request.form.get('latitude') or None,request.form.get('longitude') or None,session['uid'],now,now)); eid=cur.lastrowid; c.commit(); c.close(); log_action('create','event',eid); notify('Nouvel événement',clean(request.form.get('title')),'/events/'+str(eid)); flash('Événement créé.'); return redirect('/events/'+str(eid))
 c.close(); return page('Nouvel événement',EVENT_FORM,e=None,cancel_url='/events',**ctx)

@app.route('/events/<int:eid>')
@login_required
@permission_required('event.view')
def event_detail(eid):
 c=db(); e=c.execute('SELECT e.*,p.name project_name,z.name zone_name,tm.name team_name FROM events e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN zones z ON z.id=e.zone_id LEFT JOIN teams tm ON tm.id=e.team_id WHERE e.id=?',(eid,)).fetchone()
 if not e: c.close(); return ('Événement introuvable',404)
 participants=c.execute("SELECT ep.*,u.name,u.phone FROM event_participants ep JOIN users u ON u.id=ep.user_id WHERE ep.event_id=? ORDER BY ep.registered_at",(eid,)).fetchall(); mine=c.execute('SELECT * FROM event_participants WHERE event_id=? AND user_id=?',(eid,session['uid'])).fetchone(); c.close()
 full=bool(e['max_participants'] and sum(1 for x in participants if x['status']=='Inscrit')>=e['max_participants']); maps='' if e['latitude'] is None or e['longitude'] is None else f'https://www.google.com/maps/dir/?api=1&destination={e["latitude"]},{e["longitude"]}'
 return page('Fiche événement',"""<div class="section-title"><div><h2>{{e.title}}</h2><span class="badge watch">{{e.event_type}}</span> <span class="badge">{{e.status}}</span></div><div>{% if admin %}<a class="btn" href="/events/{{e.id}}/edit">Modifier</a> <form method="post" action="/events/{{e.id}}/delete" style="display:inline" onsubmit="return confirm('Supprimer ou archiver cet événement ?')"><button class="btn red">Supprimer</button></form>{% endif %} <a class="btn alt" href="/events">Retour</a></div></div><div class="grid two"><div class="card"><p><b>Début :</b> {{e.start_at}}</p><p><b>Fin :</b> {{e.end_at or '—'}}</p><p><b>Lieu :</b> {{e.location or '—'}}</p><p><b>Projet / Zone :</b> {{e.project_name or '—'}} / {{e.zone_name or '—'}}</p><p><b>Équipe :</b> {{e.team_name or '—'}}</p><p>{{e.description or ''}}</p>{% if maps %}<a class="btn alt" target="_blank" href="{{maps}}">🧭 Itinéraire Google Maps</a>{% endif %}</div><div class="card"><h3>Inscription</h3><p><b>{{participants|selectattr('status','equalto','Inscrit')|list|length}}</b>{% if e.max_participants %} / {{e.max_participants}}{% endif %} participants</p>{% if not admin %}{% if mine and mine.status=='Inscrit' %}<form method="post" action="/events/{{e.id}}/cancel"><button class="btn red">Annuler mon inscription</button></form>{% elif not full and e.status not in ['Terminé','Annulé'] %}<form method="post" action="/events/{{e.id}}/register"><button class="btn">M’inscrire</button></form>{% else %}<span class="badge danger">Inscriptions fermées</span>{% endif %}{% endif %}</div></div><div class="card"><h3>Participants</h3><table><tr><th>Nom</th><th>Téléphone</th><th>Inscription</th><th>Présence</th>{% if admin %}<th>Action</th>{% endif %}</tr>{% for p in participants %}<tr><td>{{p.name}}</td><td>{{p.phone or '—'}}</td><td>{{p.status}}</td><td>{{p.attendance_status}}</td>{% if admin %}<td><form method="post" action="/events/{{e.id}}/participants/{{p.user_id}}/attendance"><button class="btn alt">{{'Annuler présence' if p.attendance_status=='Présent' else 'Marquer présent'}}</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="5">Aucun participant.</td></tr>{% endfor %}</table></div>""",e=e,participants=participants,mine=mine,full=full,maps=maps,admin=is_admin())

@app.route('/events/<int:eid>/edit',methods=['GET','POST'])
@login_required
@permission_required('event.manage')
def event_edit(eid):
 c=db(); e=c.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone(); ctx=event_form_context(c)
 if not e: c.close(); return ('Événement introuvable',404)
 if request.method=='POST':
  sql='UPDATE events SET title=?,event_type=?,status=?,start_at=?,end_at=?,location=?,project_id=?,zone_id=?,team_id=?,max_participants=?,description=?,latitude=?,longitude=?,updated_at=? WHERE id=?'; c.execute(sql,(clean(request.form.get('title')),request.form.get('event_type'),request.form.get('status'),request.form.get('start_at'),request.form.get('end_at') or None,clean(request.form.get('location')) or None,request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('team_id') or None,int(request.form.get('max_participants') or 0),clean(request.form.get('description')) or None,request.form.get('latitude') or None,request.form.get('longitude') or None,datetime.now().isoformat(timespec='minutes'),eid)); c.commit(); c.close(); log_action('edit','event',eid); flash('Événement modifié.'); return redirect('/events/'+str(eid))
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
 c=db(); q=request.args.get('q','').strip(); status=request.args.get('status',''); priority=request.args.get('priority',''); w=['m.active=1']; p=[]
 if q: w.append('(m.code LIKE ? OR m.title LIKE ? OR m.description LIKE ?)'); p += ['%'+q+'%']*3
 if status: w.append('m.status=?'); p.append(status)
 if priority: w.append('m.priority=?'); p.append(priority)
 rows=c.execute("SELECT m.*,p.name project_name,z.name zone_name,t.name team_name,u.name leader_name,(SELECT COUNT(*) FROM mission_participants mp WHERE mp.mission_id=m.id) participant_count FROM missions m LEFT JOIN projects p ON p.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id LEFT JOIN users u ON u.id=m.leader_user_id WHERE "+' AND '.join(w)+' ORDER BY CASE m.status WHEN \'En cours\' THEN 1 WHEN \'Planifiée\' THEN 2 ELSE 3 END,m.start_at DESC,m.id DESC',p).fetchall(); c.close()
 return page('Missions',"""<div class="section-title"><h2>Liste des missions</h2>{% if admin %}<a class="btn" href="/missions/new">+ Nouvelle mission</a>{% endif %}</div><form class="card toolbar"><label>Recherche<input name="q" value="{{q}}"></label><label>Statut<select name="status"><option value="">Tous</option>{% for s in ['Planifiée','En cours','Terminée','Annulée'] %}<option {% if status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></label><label>Priorité<select name="priority"><option value="">Toutes</option>{% for s in ['Basse','Normale','Haute','Urgente'] %}<option {% if priority==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></label><button class="btn">Filtrer</button><a class="btn alt" href="/missions">Effacer</a></form><div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Mission</th><th>Date</th><th>Projet / Zone</th><th>Équipe</th><th>Participants</th><th>Priorité</th><th>Progression</th><th>Statut</th><th></th></tr>{% for m in rows %}<tr><td>{{m.code}}</td><td><a href="/missions/{{m.id}}"><b>{{m.title}}</b></a><div class="sub">{{m.mission_type or ''}}</div></td><td>{{m.start_at or '—'}}</td><td>{{m.project_name or '—'}} / {{m.zone_name or '—'}}</td><td>{{m.team_name or '—'}}</td><td>{{m.participant_count}}</td><td>{{m.priority or 'Normale'}}</td><td>{{m.completed_count or 0}} / {{m.target_count or 0}}</td><td><span class="badge {% if m.status=='Terminée' %}good{% elif m.status=='En cours' %}pending{% elif m.status=='Annulée' %}danger{% else %}watch{% endif %}">{{m.status}}</span></td><td><a class="btn alt" href="/missions/{{m.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="10">Aucune mission.</td></tr>{% endfor %}</table></div>""",rows=rows,q=q,status=status,priority=priority,admin=is_admin())

@app.route('/missions/new',methods=['GET','POST'])
@login_required
def mission_new():
 if not is_admin(): return redirect('/missions')
 c=db(); opts=filter_options(c); teams=c.execute('SELECT * FROM teams WHERE active=1 ORDER BY name').fetchall(); leaders=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); volunteers=c.execute("SELECT u.id,u.name FROM users u LEFT JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND COALESCE(r.name,u.role) IN ('volunteer','team_leader','coordinator') ORDER BY u.name").fetchall()
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes')
  try:
   cur=c.execute("INSERT INTO missions(code,title,mission_type,status,priority,project_id,zone_id,team_id,leader_user_id,start_at,end_at,target_count,completed_count,description,report,latitude,longitude,active,created_by_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,NULL,?,?,1,?,?,?)",(request.form['code'].strip(),request.form['title'].strip(),request.form.get('mission_type'),request.form.get('status') or 'Planifiée',request.form.get('priority') or 'Normale',request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('team_id') or None,request.form.get('leader_user_id') or None,request.form.get('start_at'),request.form.get('end_at'),request.form.get('target_count') or 0,request.form.get('description'),request.form.get('latitude') or None,request.form.get('longitude') or None,session['uid'],now,now)); mid=cur.lastrowid
   for uid in request.form.getlist('participant_ids'): c.execute("INSERT OR IGNORE INTO mission_participants(mission_id,user_id,attendance_status,created_at) VALUES(?,?,'Invité',?)",(mid,uid,now))
   c.commit()
  except DBIntegrityError:
   c.close(); flash('Le code de mission existe déjà.'); return redirect('/missions/new')
  c.close(); log_action('create','mission',mid,request.form['title']); notify('Nouvelle mission',request.form['title'],'/missions/'+str(mid),request.form.get('leader_user_id') or None); flash('Mission créée.'); return redirect('/missions/'+str(mid))
 c.close(); return page('Nouvelle mission',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Code<input name="code" required></label><label>Titre<input name="title" required></label><label>Type<select name="mission_type"><option>Plantation</option><option>Arrosage</option><option>Entretien</option><option>Inventaire</option><option>Nettoyage</option></select></label><label>Statut<select name="status"><option>Planifiée</option><option>En cours</option><option>Terminée</option><option>Annulée</option></select></label><label>Priorité<select name="priority"><option>Basse</option><option selected>Normale</option><option>Haute</option><option>Urgente</option></select></label><label>Projet<select name="project_id"><option value="">—</option>{% for x in projects %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">—</option>{% for x in zones %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Équipe<select name="team_id"><option value="">—</option>{% for x in teams %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="leader_user_id"><option value="">—</option>{% for x in leaders %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at"></label><label>Fin<input type="datetime-local" name="end_at"></label><label>Objectif<input type="number" min="0" name="target_count"></label><label>Latitude<input type="number" step="any" name="latitude"></label><label>Longitude<input type="number" step="any" name="longitude"></label><label class="full">Participants<select name="participant_ids" multiple size="7">{% for x in volunteers %}<option value="{{x.id}}">{{x.name}}</option>{% endfor %}</select><span class="sub">Maintenir Ctrl pour sélectionner plusieurs bénévoles.</span></label><label class="full">Description<textarea name="description"></textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/missions">Annuler</a></div></form></div>""",teams=teams,leaders=leaders,**opts)

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
<div class="card"><h3>Participants ({{participants|length}})</h3><table><tr><th>Nom</th><th>Téléphone</th><th>Présence</th>{% if admin %}<th>Action</th>{% endif %}</tr>{% for p in participants %}<tr><td>{{p.name}}</td><td>{{p.phone}}</td><td>{{p.attendance_status}}</td>{% if admin %}<td><form method="post" action="/missions/{{m.id}}/participants/{{p.user_id}}"><select name="attendance_status"><option {% if p.attendance_status=='Invité' %}selected{% endif %}>Invité</option><option {% if p.attendance_status=='Confirmé' %}selected{% endif %}>Confirmé</option><option {% if p.attendance_status=='Présent' %}selected{% endif %}>Présent</option><option {% if p.attendance_status=='Absent' %}selected{% endif %}>Absent</option></select><button class="btn alt">Enregistrer</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="4">Aucun participant affecté.</td></tr>{% endfor %}</table></div>""",m=m,participants=participants,actions=actions,photos=photos,admin=is_admin(),can_execute=can_execute)

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
 if not is_admin(): return redirect('/missions/'+str(mid))
 c=db(); m=c.execute('SELECT * FROM missions WHERE id=?',(mid,)).fetchone(); opts=filter_options(c); teams=c.execute('SELECT * FROM teams WHERE active=1 ORDER BY name').fetchall(); leaders=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); volunteers=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall(); selected={r['user_id'] for r in c.execute('SELECT user_id FROM mission_participants WHERE mission_id=?',(mid,))}
 if not m: c.close(); return ('Mission introuvable',404)
 if request.method=='POST':
  now=datetime.now().isoformat(timespec='minutes'); c.execute("UPDATE missions SET code=?,title=?,mission_type=?,status=?,priority=?,project_id=?,zone_id=?,team_id=?,leader_user_id=?,start_at=?,end_at=?,target_count=?,completed_count=?,description=?,report=?,latitude=?,longitude=?,updated_at=? WHERE id=?",(request.form['code'].strip(),request.form['title'].strip(),request.form.get('mission_type'),request.form.get('status'),request.form.get('priority'),request.form.get('project_id') or None,request.form.get('zone_id') or None,request.form.get('team_id') or None,request.form.get('leader_user_id') or None,request.form.get('start_at'),request.form.get('end_at'),request.form.get('target_count') or 0,request.form.get('completed_count') or 0,request.form.get('description'),request.form.get('report'),request.form.get('latitude') or None,request.form.get('longitude') or None,now,mid)); c.execute('DELETE FROM mission_participants WHERE mission_id=?',(mid,));
  for uid in request.form.getlist('participant_ids'): c.execute("INSERT INTO mission_participants(mission_id,user_id,attendance_status,created_at) VALUES(?,?,'Invité',?)",(mid,uid,now))
  c.commit(); c.close(); log_action('edit','mission',mid,request.form['status']);
  if request.form.get('status')=='Terminée': notify('Mission terminée',request.form['title'],'/missions/'+str(mid),None)
  flash('Mission modifiée.'); return redirect('/missions/'+str(mid))
 c.close(); return page('Modifier mission',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Code<input name="code" value="{{m.code}}" required></label><label>Titre<input name="title" value="{{m.title}}" required></label><label>Type<select name="mission_type">{% for x in ['Plantation','Arrosage','Entretien','Inventaire','Nettoyage'] %}<option {% if m.mission_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Statut<select name="status">{% for x in ['Planifiée','En cours','Terminée','Annulée'] %}<option {% if m.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Priorité<select name="priority">{% for x in ['Basse','Normale','Haute','Urgente'] %}<option {% if m.priority==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Projet<select name="project_id"><option value="">—</option>{% for x in projects %}<option value="{{x.id}}" {% if m.project_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Zone<select name="zone_id"><option value="">—</option>{% for x in zones %}<option value="{{x.id}}" {% if m.zone_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Équipe<select name="team_id"><option value="">—</option>{% for x in teams %}<option value="{{x.id}}" {% if m.team_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Responsable<select name="leader_user_id"><option value="">—</option>{% for x in leaders %}<option value="{{x.id}}" {% if m.leader_user_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Début<input type="datetime-local" name="start_at" value="{{m.start_at or ''}}"></label><label>Fin<input type="datetime-local" name="end_at" value="{{m.end_at or ''}}"></label><label>Objectif<input type="number" min="0" name="target_count" value="{{m.target_count or 0}}"></label><label>Réalisé<input type="number" min="0" name="completed_count" value="{{m.completed_count or 0}}"></label><label>Latitude<input name="latitude" value="{{m.latitude or ''}}"></label><label>Longitude<input name="longitude" value="{{m.longitude or ''}}"></label><label class="full">Participants<select name="participant_ids" multiple size="7">{% for x in volunteers %}<option value="{{x.id}}" {% if x.id in selected %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Description<textarea name="description">{{m.description or ''}}</textarea></label><label class="full">Rapport de mission<textarea name="report">{{m.report or ''}}</textarea></label><div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/missions/{{m.id}}">Annuler</a></div></form></div>""",m=m,teams=teams,leaders=leaders,selected=selected,**opts)

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
 return page('Notifications',"""<div class="section-title"><h2>Centre de notifications <span class="badge pending">{{unread}} non lues</span></h2><a class="btn" href="/action-center">Centre d’actions</a></div><form class="card toolbar"><label>Catégorie<select name="category"><option value="">Toutes</option>{% for c in categories %}<option {% if category==c.category %}selected{% endif %}>{{c.category}}</option>{% endfor %}</select></label><label>État<select name="unread"><option value="0">Toutes</option><option value="1" {% if unread_only %}selected{% endif %}>Non lues seulement</option></select></label><button class="btn">Filtrer</button><a class="btn alt" href="/notifications">Effacer</a></form><form method="post" action="/notifications/bulk" class="card"><div class="bulk-bar"><label><input type="checkbox" id="selectAll" onclick="toggleAll(this)"> Tout sélectionner</label> <button class="btn" name="decision" value="accept">✓ Accepter la sélection</button> <button class="btn red" name="decision" value="reject">✕ Refuser la sélection</button></div><div style="overflow:auto"><table><tr><th></th><th>État</th><th>Catégorie</th><th>Date</th><th>Titre</th><th>Message</th><th>Actions</th></tr>{% for n in rows %}<tr><td><input class="notif-check" type="checkbox" name="notification_ids" value="{{n.id}}" {% if not n.action_type %}disabled{% endif %}></td><td>{% if n.is_read %}<span class="badge good">Lue</span>{% else %}<span class="badge pending">Nouvelle</span>{% endif %}</td><td><span class="badge watch">{{n.category or 'Général'}}</span></td><td>{{n.created_at}}</td><td><b>{{n.title}}</b>{% if n.decision %}<div class="sub">Décision : {{n.decision}}</div>{% endif %}</td><td>{{n.message or ''}}</td><td><div class="quick-actions">{% if n.action_type and not n.decision %}<button class="btn" formaction="/notifications/{{n.id}}/decide/accept" formmethod="post">Accepter</button><button class="btn red" formaction="/notifications/{{n.id}}/decide/reject" formmethod="post">Refuser</button>{% endif %}{% if n.link %}<a class="btn alt" href="/notifications/{{n.id}}/open">Ouvrir</a>{% else %}<button class="btn alt" formaction="/notifications/{{n.id}}/read" formmethod="post">Marquer lue</button>{% endif %}</div></td></tr>{% else %}<tr><td colspan="7">Aucune notification.</td></tr>{% endfor %}</table></div></form><script>function toggleAll(x){document.querySelectorAll('.notif-check:not(:disabled)').forEach(c=>c.checked=x.checked)}</script>""",rows=rows,unread=unread,categories=categories,category=category,unread_only=unread_only)

@app.post('/notifications/read-all')
@login_required
def notifications_read_all():
 c=db(); c.execute('UPDATE notifications SET is_read=1 WHERE user_id=? OR user_id IS NULL',(session['uid'],)); c.commit(); c.close(); return redirect('/notifications')

@app.post('/notifications/<int:nid>/read')
@login_required
def notification_read(nid):
 c=db(); c.execute('UPDATE notifications SET is_read=1 WHERE id=? AND (user_id=? OR user_id IS NULL)',(nid,session['uid'])); c.commit(); c.close(); return redirect('/notifications')

@app.route('/notifications/<int:nid>/open')
@login_required
def notification_open(nid):
 c=db(); n=c.execute('SELECT * FROM notifications WHERE id=? AND (user_id=? OR user_id IS NULL)',(nid,session['uid'])).fetchone()
 if not n: c.close(); return redirect('/notifications')
 c.execute('UPDATE notifications SET is_read=1 WHERE id=?',(nid,)); c.commit(); link=n['link']; c.close(); return redirect(link or '/notifications')

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
  now=datetime.now().isoformat(timespec='minutes'); approval='approved' if is_admin() else 'pending'; code=None; qr=None
  cur=c.execute('INSERT INTO trees(species_id,project_id,zone_id,planted_at,planted_by_user_id,planted_by,latitude,longitude,gps_accuracy,health_status,watering_status,approval_status,approved_by_user_id,approved_at,planting_type,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',(request.form['species_id'],z['project_id'],zid,request.form.get('planted_at') or date.today().isoformat(),session['uid'],session['name'],request.form.get('latitude') or None,request.form.get('longitude') or None,request.form.get('gps_accuracy') or None,'Bon','À jour',approval,session['uid'] if approval=='approved' else None,now if approval=='approved' else None,'série',request.form.get('notes'),now)); tid=cur.lastrowid
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
 return page('Accueil bénévole',"""<div class="vol-hero"><div class="sub" style="color:#d6e9dc">Espace bénévole privé</div><h2 style="margin:5px 0">Bonjour {{session.get('name')}} 👋</h2><div>{{my_trees}} arbre(s) suivi(s) • {{need_water}} à arroser • {{unread}} notification(s)</div></div><div class="vertical-actions volunteer-home-actions"><a class="vertical-action" href="/volunteer/trees"><span class="icon">🌳</span><span>Mes arbres</span></a><a class="vertical-action" href="/volunteer/gps-quick"><span class="icon">📍</span><span>Position GPS rapide</span></a><a class="vertical-action" href="/planting/new"><span class="icon">🌱</span><span>Planter un arbre</span></a><a class="vertical-action" href="/volunteer/watering"><span class="icon">💧</span><span>Arroser</span></a><a class="vertical-action" href="/volunteer/scan"><span class="icon">📷</span><span>Scanner un QR code</span></a><a class="vertical-action" href="/map"><span class="icon">🗺️</span><span>Carte</span></a><a class="vertical-action" href="/volunteer/donate"><span class="icon">🎁</span><span>Faire un don</span></a><a class="vertical-action" href="/volunteer/events"><span class="icon">📆</span><span>Événements</span></a>{% if can_missions %}<a class="vertical-action" href="/volunteer/missions"><span class="icon">📋</span><span>Mes missions</span></a>{% endif %}{% if can_interventions %}<a class="vertical-action" href="/interventions"><span class="icon">🛠</span><span>Interventions</span></a>{% endif %}{% if can_team %}<a class="vertical-action" href="/volunteer/team"><span class="icon">👥</span><span>Mon équipe</span></a>{% endif %}<a class="vertical-action" href="/notifications"><span class="icon">🔔</span><span>Notifications</span></a><a class="vertical-action" href="/volunteer/profile"><span class="icon">👤</span><span>Mon profil</span></a><a class="vertical-action secondary-action" href="/public"><span class="icon">🌍</span><span>Accueil public</span></a></div><div class="card desktop-dashboard-details" style="margin-top:16px"><h3>Priorités terrain</h3><table><tr><th>Arbre</th><th>Zone</th><th>État</th><th></th></tr>{% for t in priority %}<tr><td>{{t.tree_code or 'En attente'}}<div class="sub">{{t.species_name}}</div></td><td>{{t.zone_name or '—'}}</td><td>{{t.watering_status}} / {{t.health_status}}</td><td><a class="btn alt" href="/tree/{{t.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="4">Aucune priorité actuellement.</td></tr>{% endfor %}</table></div><div class="bottom-space"></div>""",missions=missions,my_trees=my_trees,need_water=need_water,unread=unread,priority=priority,recent_missions=recent_missions,can_missions=can_missions,can_interventions=can_interventions,can_team=can_team)

@app.route('/volunteer/missions')
@login_required
@permission_required('mission.view')
def volunteer_missions():
 c=db(); rows=c.execute("SELECT m.*,p.name project_name,z.name zone_name,t.name team_name,mp.attendance_status FROM mission_participants mp JOIN missions m ON m.id=mp.mission_id LEFT JOIN projects p ON p.id=m.project_id LEFT JOIN zones z ON z.id=m.zone_id LEFT JOIN teams t ON t.id=m.team_id WHERE mp.user_id=? AND m.active=1 ORDER BY COALESCE(m.start_at,m.created_at) DESC",(session['uid'],)).fetchall(); c.close()
 return page('Mes missions',"""<div class="card" style="overflow:auto"><table><tr><th>Mission</th><th>Projet / Zone</th><th>Date</th><th>État</th><th>Participation</th><th></th></tr>{% for m in rows %}<tr><td><a href="/missions/{{m.id}}"><b>{{m.title}}</b></a><div class="sub">{{m.mission_type}} • {{m.priority}}</div></td><td>{{m.project_name or '—'}} / {{m.zone_name or '—'}}</td><td>{{m.start_at or 'À confirmer'}}</td><td>{{m.status}}</td><td>{{m.attendance_status}}</td><td><a class="btn" href="/missions/{{m.id}}">Ouvrir</a></td></tr>{% else %}<tr><td colspan="6">Aucune mission assignée.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/volunteer/trees')
@login_required
def volunteer_trees():
 c=db(); where="t.active=1 AND t.planted_by_user_id=?"; params=[session['uid']]
 if request.args.get('priority'): where+=" AND (t.watering_status IN ('À arroser','Urgent') OR t.health_status IN ('À surveiller','En danger'))"
 rows=c.execute("SELECT t.*,s.name_fr species_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN zones z ON z.id=t.zone_id WHERE "+where+" ORDER BY t.id DESC",params).fetchall(); c.close()
 return page('Mes arbres',"""<div class="section-title"><h2>Mes arbres</h2><div><a class="btn alt" href="/volunteer/trees/no-gps">📍 Sans GPS</a> <a class="btn" href="/planting/new">+ Planter</a></div></div><div class="card" style="overflow:auto"><table><tr><th>Code</th><th>Espèce</th><th>Zone</th><th>Santé</th><th>Arrosage</th><th>Statut</th><th></th></tr>{% for t in rows %}<tr><td>{{t.tree_code or 'En attente'}}</td><td>{{t.species_name}}</td><td>{{t.zone_name or '—'}}</td><td>{{t.health_status}}</td><td>{{t.watering_status}}</td><td><a href="/tree/{{t.id}}"><span class="badge {% if t.approval_status=='approved' %}good{% elif t.approval_status=='pending' %}watch{% else %}danger{% endif %}">{{'Acceptée' if t.approval_status=='approved' else ('En attente' if t.approval_status=='pending' else 'Refusée')}}</span></a></td><td><a class="btn alt" href="/tree/{{t.id}}">Fiche</a></td></tr>{% else %}<tr><td colspan="6">Aucun arbre enregistré.</td></tr>{% endfor %}</table></div>""",rows=rows)



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
 return redirect('/tree/'+str(t['id']))

@app.route('/volunteer/profile',methods=['GET','POST'])
@login_required
def volunteer_profile():
 c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
 if request.method=='POST':
  values=user_form_values(request.form); errors=validate_user_form(c,values,user_id=session['uid'])
  if errors:
   for e in errors: flash(e)
  else:
   c.execute('UPDATE users SET first_name=?,last_name=?,name=?,sex=?,phone=?,email=?,wilaya_id=?,commune_id=?,birth_date=?,address=?,skills=?,availability=?,photo_url=? WHERE id=?',(values['first_name'],values['last_name'],user_display_name(values['first_name'],values['last_name']),values['sex'],values['phone'],values['email'],values['wilaya_id'],values['commune_id'],values['birth_date'],values['address'],values['skills'],values['availability'],values['photo_url'],session['uid']))
   c.commit(); session['name']=user_display_name(values['first_name'],values['last_name']); c.close(); flash('Profil mis à jour.'); return redirect('/volunteer/profile')
 opts=filter_options(c); c.close()
 return page('Mon profil',"""<div class="card"><form method="post" class="form" id="plantingForm" onkeydown="if(event.key==='Enter' && event.target.tagName!=='TEXTAREA' && event.target.type!=='submit'){event.preventDefault()}"><label>Prénom<input name="first_name" value="{{u.first_name or ''}}" required></label><label>Nom<input name="last_name" value="{{u.last_name or ''}}" required></label><label>Sexe<select name="sex"><option {% if u.sex=='Homme' %}selected{% endif %}>Homme</option><option {% if u.sex=='Femme' %}selected{% endif %}>Femme</option></select></label><label>Téléphone<input name="phone" value="{{u.phone or ''}}" required></label><label>E-mail<input type="email" name="email" value="{{u.email or ''}}"></label><label>Date de naissance<input type="date" name="birth_date" value="{{u.birth_date or ''}}"></label><label>Wilaya<select name="wilaya_id"><option value="">—</option>{% for x in wilayas %}<option value="{{x.id}}" {% if u.wilaya_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label>Commune<select name="commune_id"><option value="">—</option>{% for x in communes %}<option value="{{x.id}}" {% if u.commune_id==x.id %}selected{% endif %}>{{x.name}}</option>{% endfor %}</select></label><label class="full">Adresse<input name="address" value="{{u.address or ''}}"></label><label>Compétences<input name="skills" value="{{u.skills or ''}}"></label><label>Disponibilité<input name="availability" value="{{u.availability or ''}}"></label>{{photo|safe}}<div class="full"><button class="btn">Enregistrer</button> <a class="btn alt" href="/volunteer">Annuler</a></div></form></div>""",u=u,photo=photo_fields(u['photo_url'] if u else '',prefix='profile'),**opts)

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
 if kind in ('Argent','Arbres','Matériel'): clauses.append('n.donation_type=?'); args.append(kind)
 if status_filter=='pending': clauses.append("n.status='En attente'")
 if clauses: where=' WHERE '+' AND '.join(clauses)
 rows=c.execute("SELECT n.*,d.name donor_name,s.name_fr species_name,e.name equipment_name FROM donations n LEFT JOIN donors d ON d.id=n.donor_id LEFT JOIN species s ON s.id=n.species_id LEFT JOIN equipment e ON e.id=n.equipment_id"+where+" ORDER BY n.received_at DESC,n.group_id DESC,n.id DESC",args).fetchall()
 total=c.execute("SELECT COALESCE(SUM(amount),0) v FROM donations WHERE status='Confirmé' AND donation_type='Argent'").fetchone()['v']; c.close()
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
  else:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',('Dons','Entrée',d['amount'],'Don en argent','Don '+(d['receipt_number'] or str(donation_id)),'donation',donation_id,'Validé',d['created_by_user_id'],datetime.now().isoformat(timespec='minutes')))

def _add_donation_line(c,gid,donor_id,status,receipt,dtype,amount=0,qty=0,species_id=None,equipment_id=None):
 c.execute('INSERT INTO donations(group_id,donor_id,donation_type,status,amount,currency,quantity,unit,received_at,estimated_value,species_id,equipment_id,receipt_number,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(gid,donor_id,dtype,status,amount,'DZD',qty,'DA' if dtype=='Argent' else ('plants' if dtype=='Arbres' else 'pièces'),date.today().isoformat(),0,species_id,equipment_id,receipt,session['uid'],datetime.now().isoformat(timespec='minutes')))
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
 c=db()
 trees=c.execute("SELECT s.name_fr name,CAST(SUM(d.quantity) AS INTEGER) qty FROM donations d JOIN species s ON s.id=d.species_id WHERE d.status='Confirmé' AND d.donation_type='Arbres' GROUP BY s.id,s.name_fr ORDER BY qty DESC,s.name_fr").fetchall()
 eq=c.execute("SELECT e.name name,CAST(SUM(d.quantity) AS INTEGER) qty FROM donations d JOIN equipment e ON e.id=d.equipment_id WHERE d.status='Confirmé' AND d.donation_type='Matériel' GROUP BY e.id,e.name ORDER BY qty DESC,e.name").fetchall()
 tt=sum(r['qty'] for r in trees); te=sum(r['qty'] for r in eq); c.close()
 body="""<div class='section-title'><div><h2>📊 Rapport des dons en nature</h2><p class='sub'>Statistiques d’origine uniquement : ce rapport n’est pas un stock. Le stock réel est dans 📦 Stock.</p></div><a class='action-btn action-view' href='/donations'>← Dons</a></div><div class='grid kpis'><div class='card kpi'><small>🌳 Arbres reçus</small><b>{{tt}}</b></div><div class='card kpi'><small>🧰 Matériels reçus</small><b>{{te}}</b></div></div><div class='grid'><div class='card'><h3>🌳 Détail par espèce</h3><table><tr><th>Espèce</th><th>Total reçu</th></tr>{% for r in trees %}<tr><td>{{r.name}}</td><td><b>{{r.qty}}</b></td></tr>{% else %}<tr><td colspan='2'>Aucun don d’arbre accepté.</td></tr>{% endfor %}</table></div><div class='card'><h3>🧰 Détail matériel</h3><table><tr><th>Matériel</th><th>Total reçu</th></tr>{% for r in eq %}<tr><td>{{r.name}}</td><td><b>{{r.qty}}</b></td></tr>{% else %}<tr><td colspan='2'>Aucun don de matériel accepté.</td></tr>{% endfor %}</table></div></div>"""
 return page('Rapport dons en nature',body,trees=trees,eq=eq,tt=tt,te=te)

@app.route('/stock')
@login_required
def stock_dashboard():
 if not (has_permission('nursery.view') or has_permission('equipment.view')):
  return 'Accès refusé',403
 c=db()
 trees=c.execute("SELECT n.*,s.name_fr species_name,(n.quantity_available-n.quantity_reserved) free_qty,COALESCE((SELECT SUM(ds.quantity) FROM donation_stock_sync ds JOIN donations d ON d.id=ds.donation_id WHERE ds.sync_type='Arbres' AND ds.stock_id=n.id AND d.status='Confirmé'),0) donated_qty FROM nursery_stock n JOIN species s ON s.id=n.species_id ORDER BY s.name_fr").fetchall()
 equipment=c.execute("SELECT e.*,COALESCE((SELECT SUM(ds.quantity) FROM donation_stock_sync ds JOIN donations d ON d.id=ds.donation_id WHERE ds.sync_type='Matériel' AND ds.stock_id=e.id AND d.status='Confirmé'),0) donated_qty FROM equipment e WHERE e.active=1 ORDER BY e.category,e.name").fetchall()
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
  except DBIntegrityError: flash('Cette année est déjà enregistrée pour cet adhérent.')
  c.close(); return redirect('/members/'+str(mid))
 c.close(); return page('Nouvelle cotisation',"""<div class='card'><h3>{{m.last_name}} {{m.first_name}}</h3><form method='post' class='form'><label>Année<input type='number' name='membership_year' value='{{year}}' required></label><label>Montant (DA)<input type='number' step='0.01' min='0' name='amount' required></label><label>Date<input type='date' name='paid_at' value='{{today}}'></label><label>Mode<select name='payment_method'><option>Espèces</option><option>Virement</option><option>Chèque</option></select></label><div class='full'><button class='btn'>Encaisser</button></div></form></div>""",m=m,year=date.today().year,today=date.today().isoformat())

@app.route('/cash')
@login_required
@permission_required('cash.view')
def cash_dashboard():
 c=db(); cot,dons=cash_balances(c); rows=c.execute('SELECT cm.*,p.name project_name,z.name zone_name FROM cash_movements cm LEFT JOIN projects p ON p.id=cm.project_id LEFT JOIN zones z ON z.id=cm.zone_id ORDER BY cm.id DESC LIMIT 100').fetchall(); agents=c.execute('SELECT * FROM agents WHERE active=1 ORDER BY name').fetchall(); c.close()
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
 c=db(); cot,dons=cash_balances(c); ptype=request.args.get('type') or request.form.get('purchase_type') or 'Arbres'
 species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall(); equipment=c.execute('SELECT id,name FROM equipment WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  total=max(0,float(request.form.get('total_amount') or 0)); source=request.form.get('source') or 'Dons'; qty=max(0,float(request.form.get('quantity') or 0)); justification=clean(request.form.get('justification')); item_id=request.form.get('item_id') or None
  fm=fd=0.0
  if source=='Cotisations': fm=total
  elif source=='Dons': fd=total
  else:
   fm=max(0,float(request.form.get('from_memberships') or 0)); fd=max(0,float(request.form.get('from_donations') or 0))
  if total<=0 or qty<=0 or not item_id: flash('Article, quantité et montant sont obligatoires.')
  elif abs((fm+fd)-total)>0.01: flash('La répartition Dons + Cotisations doit être égale au montant total.')
  elif fm>cot or fd>dons: flash('Solde insuffisant dans le fonds choisi.')
  elif not justification: flash('Le justificatif est obligatoire.')
  else:
   now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO purchase_records(purchase_type,item_id,quantity,total_amount,from_memberships,from_donations,supplier,justification,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ptype,item_id,qty,total,fm,fd,clean(request.form.get('supplier')) or None,justification,clean(request.form.get('notes')) or None,session['uid'],now)); pid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
   desc=('Achat arbres' if ptype=='Arbres' else 'Achat matériel')+' — '+str(int(qty) if qty.is_integer() else qty)+' unité(s)'
   if fm:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Cotisations','Sortie',fm,'Achat '+ptype,desc,'purchase',pid,justification,'Validé',session['uid'],now))
   if fd:c.execute('INSERT INTO cash_movements(fund_type,movement_type,amount,category,description,reference_type,reference_id,justification,status,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('Dons','Sortie',fd,'Achat '+ptype,desc,'purchase',pid,justification,'Validé',session['uid'],now))
   if ptype=='Arbres':
    stock=c.execute("SELECT * FROM nursery_stock WHERE species_id=? AND COALESCE(location,'')=''",(item_id,)).fetchone()
    if stock: c.execute('UPDATE nursery_stock SET quantity_available=quantity_available+?,unit_value=?,updated_at=? WHERE id=?',(int(qty),total/qty,now,stock['id'])); sid=stock['id']
    else: c.execute('INSERT INTO nursery_stock(species_id,quantity_available,unit_value,location,updated_at) VALUES(?,?,?,?,?)',(item_id,int(qty),total/qty,'',now)); sid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
    c.execute('INSERT INTO nursery_movements(stock_id,movement_type,quantity,notes,created_by_user_id,created_at) VALUES(?,?,?,?,?,?)',(sid,'Entrée achat',int(qty),'Achat caisse #'+str(pid),session['uid'],now))
   else:
    e=c.execute('SELECT * FROM equipment WHERE id=?',(item_id,)).fetchone()
    if e:c.execute('UPDATE equipment SET quantity_total=quantity_total+?,quantity_available=quantity_available+?,updated_at=? WHERE id=?',(int(qty),int(qty),now,item_id))
   c.commit(); c.close(); flash('Achat enregistré : caisse débitée et stock alimenté automatiquement.'); return redirect('/cash')
 c.close()
 return page('Achat '+ptype,"""<div class='card'><div class='grid kpis'><div class='card kpi'><small>Dons disponibles</small><b>{{'%.2f'|format(dons)}} DA</b></div><div class='card kpi'><small>Cotisations disponibles</small><b>{{'%.2f'|format(cot)}} DA</b></div></div><form method='post' class='form'><input type='hidden' name='purchase_type' value='{{ptype}}'><label>{{'Espèce' if ptype=='Arbres' else 'Matériel'}}<select name='item_id' required><option value=''>Choisir</option>{% if ptype=='Arbres' %}{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}</option>{% endfor %}{% else %}{% for x in equipment %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}{% endif %}</select></label><label>Quantité<input type='number' min='1' step='1' name='quantity' required></label><label>Prix total (DA)<input type='number' min='0.01' step='0.01' name='total_amount' required></label><label>Fournisseur<input name='supplier'></label><label>Source de paiement<select name='source' id='paySource' onchange='mixBox.style.display=this.value=="Mixte"?"grid":"none"'><option>Dons</option><option>Cotisations</option><option>Mixte</option></select></label><div id='mixBox' class='full form' style='display:none'><label>Depuis cotisations<input type='number' min='0' step='0.01' name='from_memberships' value='0'></label><label>Depuis dons<input type='number' min='0' step='0.01' name='from_donations' value='0'></label></div><label class='full'>Justificatif / facture<input name='justification' required></label><label class='full'>Notes<textarea name='notes'></textarea></label><div class='full action-set'><button class='action-btn action-primary'>✓ Acheter et alimenter le stock</button><a class='action-btn action-view' href='/cash'>Annuler</a></div></form></div>""",ptype=ptype,species=species,equipment=equipment,cot=cot,dons=dons)

@app.route('/agents/new',methods=['GET','POST'])
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
def print_doc(title,content): return '<!doctype html><html><head><meta charset="utf-8"><title>'+title+'</title>'+PRINT_STYLE+'</head><body><button class="no-print" onclick="window.print()">Imprimer</button>'+content+'</body></html>'

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
 return page('Corrections d’arbres',"""<div class='card'><table><tr><th>Arbre</th><th>Bénévole</th><th>Motif</th><th>Date</th><th>Actions</th></tr>{% for r in rows %}<tr><td><a href='/tree/{{r.tree_id}}'>{{r.tree_code or r.tree_id}}</a></td><td>{{r.requester}}</td><td>{{r.reason}}</td><td>{{r.created_at}}</td><td><form method='post' action='/tree-change-requests/{{r.id}}/approve' style='display:inline'><button class='btn'>Accepter</button></form> <form method='post' action='/tree-change-requests/{{r.id}}/reject' style='display:inline'><button class='btn red'>Refuser</button></form></td></tr>{% else %}<tr><td colspan='5'>Aucune demande.</td></tr>{% endfor %}</table></div>""",rows=rows)

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
def public_page(title, body, **ctx):
 if session.get('uid'):
  account_link='/'+('' if is_admin() else 'volunteer')
  auth_desktop=f"<a class='btn alt' href='{account_link}'>🏠 Mon accueil</a><a class='btn red' href='/logout?next=/public'>Déconnexion</a>"
  auth_mobile=f"<a href='/logout?next=/public'><span>🚪</span>Déconnexion</a>"
 else:
  auth_desktop="<a class='btn alt' href='/login?next=/public'>🔐 Connexion</a>"
  auth_mobile="<a href='/login?next=/public'><span>🔐</span>Connexion</a>"
 nav="""<header class='public-header'><div class='public-shell' style='width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px'><a class='public-brand' href='/public'>🌳 <span>MyTree</span></a><nav class='public-nav'><a class='btn alt' href='/public'>Accueil</a><a class='btn alt' href='/public/projects'>Projets</a><a class='btn alt' href='/public/events'>Événements</a><a class='btn alt' href='/public/map'>Carte</a><a class='btn alt' href='/public/species'>Encyclopédie</a><a class='btn' href='/public/help'>Je veux aider</a>"""+language_switcher()+auth_desktop+"""</nav></div></header>"""
 mobile="""<nav class='mobile-public-nav'><a href='/public'><span>🏠</span>Accueil</a><a href='/public/map'><span>🗺</span>Carte</a><a href='/public/species'><span>📚</span>Espèces</a><a href='/public/help'><span>🤝</span>Aider</a>"""+auth_mobile+"""</nav>"""
 footer="""<footer class='public-footer'><div class='public-shell'><b>MyTree Professional</b><p>Plateforme de suivi des plantations, des bénévoles et des actions de terrain.</p><a href='/login'>Espace sécurisé</a></div></footer>"""
 tpl="<!doctype html><html lang='"+current_lang()+"' dir='"+current_dir()+"'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='theme-color' content='#102b1c'><title>"+tr(title)+" — MyTree</title>"+STYLE+SMART_NAV_SCRIPT+UNIVERSAL_SEARCH_SCRIPT+i18n_script()+"<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'><script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script></head><body class='public-page-body'>"+nav+"<main class='public-shell'><div class='public-auth-banner'>"+auth_desktop+"</div>"+body+"</main>"+footer+mobile+"</body></html>"
 return render_template_string(tpl,**ctx)

@app.route('/public')
def public_home():
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
 return render_template_string("""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{{s.name_fr}}</title><style>body{font-family:Arial;max-width:850px;margin:30px auto;line-height:1.5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.box{border:1px solid #ccc;padding:12px;border-radius:8px}@media print{button{display:none}}</style></head><body><button onclick='print()'>Imprimer</button><h1>{{s.name_fr}}</h1><h2 dir='rtl'>{{s.name_ar or ''}}</h2><p><i>{{s.scientific_name or ''}}</i> — {{s.family or ''}}</p><div class='grid'><div class='box'><b>Origine</b><br>{{s.origin or '—'}}</div><div class='box'><b>Régions</b><br>{{s.regions or '—'}}</div><div class='box'><b>Sol</b><br>{{s.soil_type or '—'}}</div><div class='box'><b>Eau</b><br>{{s.water_need or '—'}}</div><div class='box'><b>Distance</b><br>{{s.planting_distance or '—'}}</div><div class='box'><b>Hauteur adulte</b><br>{{s.adult_height or '—'}}</div></div><h3>Usages</h3><p>{{s.uses or '—'}}</p><h3>Entretien</h3><p>{{s.maintenance or '—'}}</p><h3>Maladies et précautions</h3><p>{{s.diseases or '—'}}</p><p>{{s.compatibility_note or ''}}</p><h3>Description</h3><p>{{s.description or '—'}}</p></body></html>""",s=sp)

@app.route('/public/projects')
def public_projects():
 c=db(); rows=c.execute("SELECT p.*,(SELECT COUNT(*) FROM trees t WHERE t.project_id=p.id AND t.active=1 AND t.approval_status='approved') tree_count FROM projects p WHERE p.active=1 ORDER BY p.id DESC").fetchall(); c.close()
 return public_page('Nos projets',"""<h1>Nos projets</h1><div class='species-grid'>{% for p in rows %}<div class='species-card'><h3>{{p.name}}</h3><p>{{p.location or ''}}</p><b>{{p.tree_count}} arbres suivis</b></div>{% endfor %}</div>""",rows=rows)

@app.route('/public/tree/<int:tid>')
def public_tree(tid):
 c=db(); t=c.execute("SELECT t.*,s.name_fr,s.name_ar,s.scientific_name,p.name project_name,z.name zone_name FROM trees t LEFT JOIN species s ON s.id=t.species_id LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN zones z ON z.id=t.zone_id WHERE t.id=? AND t.active=1 AND t.approval_status='approved'",(tid,)).fetchone(); c.close()
 if not t:return ('Arbre introuvable',404)
 return public_page('Fiche arbre',"""<div class='card'><h1>🌳 {{t.name_fr}} — {{t.tree_code}}</h1><p dir='rtl'>{{t.name_ar or ''}}</p><p><i>{{t.scientific_name or ''}}</i></p><div class='grid two'><div><p><b>Date de plantation :</b> {{t.planted_at or '—'}}</p><p><b>Projet :</b> {{t.project_name or 'Hors projet'}}</p><p><b>Zone :</b> {{t.zone_name or 'Hors zone'}}</p></div><div><p><b>État :</b> {{t.health_status}}</p><p><b>Dernier arrosage :</b> {{t.last_watered_at or 'Non renseigné'}}</p></div></div><a class='btn' href='/public/action/water'>💧 Arroser ou planter</a> <a class='btn alt' href='/public/species/{{t.species_id}}'>Voir la fiche de l’espèce</a></div>""",t=t)

@app.route('/public/register',methods=['GET','POST'])
def public_register():
 if request.method=='POST':
  c=db(); v=user_form_values(request.form); password=request.form.get('password') or ''; errors=validate_user_form(c,v,password_required=True,password=password)
  if not errors:
   role=c.execute("SELECT id FROM roles WHERE name='volunteer'").fetchone()['id']; name=user_display_name(v['first_name'],v['last_name']); now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO users(first_name,last_name,name,sex,phone,email,username,password_hash,role_id,role,active,wilaya_id,commune_id,created_at,birth_date,address,skills,availability,photo_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(v['first_name'],v['last_name'],name,v['sex'],v['phone'],v['email'],v['phone'],generate_password_hash(password),role,'volunteer',1,v['wilaya_id'],v['commune_id'],now,v['birth_date'],v['address'],v['skills'],v['availability'],v['photo_url'])); uid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; reg_lang=current_lang(); c.execute('UPDATE users SET preferred_language=? WHERE id=?',(reg_lang,uid)); c.commit(); c.close(); session.clear(); session.permanent=True; session.update(uid=uid,name=name,role='volunteer',lang=reg_lang); log_action('self_register','user',uid,'Inscription publique'); flash('Compte créé et connexion effectuée.'); target=request.form.get('next') or request.args.get('next'); return redirect(target if target and target.startswith('/') else '/volunteer')
  c.close()
  for e in errors: flash(e)
 c=db(); wilayas=c.execute('SELECT * FROM wilayas WHERE active=1 ORDER BY name').fetchall(); communes=c.execute('SELECT * FROM communes WHERE active=1 ORDER BY name').fetchall(); c.close()
 return public_page('Devenir bénévole',"""{% for m in get_flashed_messages() %}<div class='flash'>{{m}}</div>{% endfor %}<div class='card'><h1>Créer un compte bénévole</h1><form method='post' class='form'><input type='hidden' name='next' value='{{request.args.get("next","")}}'><label>Prénom<input name='first_name' required></label><label>Nom<input name='last_name' required></label><label>Téléphone<input name='phone' required></label><label>E-mail<input type='email' name='email'></label><label>Sexe<select name='sex'><option>Homme</option><option>Femme</option></select></label><label>Mot de passe<input type='password' name='password' minlength='6' required></label><label>Wilaya<select name='wilaya_id'><option value=''>Choisir</option>{% for w in wilayas %}<option value='{{w.id}}'>{{w.name}}</option>{% endfor %}</select></label><label>Commune<select name='commune_id'><option value=''>Choisir</option>{% for x in communes %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select></label><label class='full'>Adresse<textarea name='address'></textarea></label><div class='full'><button class='btn'>Créer mon compte</button> <a class='btn alt' href='{{request.args.get("cancel") or "/public"}}'>Annuler</a></div></form></div>""",wilayas=wilayas,communes=communes)



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
 c.execute('UPDATE notifications SET decision=?,is_read=1 WHERE id=?',(label,nid)); c.commit(); c.close(); return ok

@app.post('/notifications/<int:nid>/decide/<decision>')
@login_required
def notification_decide(nid,decision):
 if not is_admin() or decision not in ('accept','reject'): return redirect('/notifications')
 flash('Demande traitée.' if decide_notification(nid,decision) else 'Cette demande ne peut plus être traitée.')
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
 flash(f'{done} demande(s) traitée(s).')
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
 c=db(); species=c.execute('SELECT id,name_fr FROM species WHERE active=1 ORDER BY name_fr').fetchall(); equipment=c.execute('SELECT id,name FROM equipment WHERE active=1 ORDER BY name').fetchall()
 if request.method=='POST':
  receipt='PENDING-'+datetime.now().strftime('%Y%m%d-%H%M%S'); now=datetime.now().isoformat(timespec='minutes'); c.execute('INSERT INTO donation_groups(status,receipt_number,received_at,created_by_user_id,created_at) VALUES(?,?,?,?,?)',('En attente',receipt,date.today().isoformat(),session['uid'],now)); gid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; count=0
  amount=max(0,float(request.form.get('amount') or 0))
  if amount>0:_add_donation_line(c,gid,None,'En attente',receipt,'Argent',amount=amount); count+=1
  for sid,q in zip(request.form.getlist('species_id[]'),request.form.getlist('tree_quantity[]')):
   try:qv=max(0,int(q or 0))
   except:qv=0
   if sid and qv:_add_donation_line(c,gid,None,'En attente',receipt,'Arbres',qty=qv,species_id=sid); count+=1
  for eid,q in zip(request.form.getlist('equipment_id[]'),request.form.getlist('equipment_quantity[]')):
   try:qv=max(0,int(q or 0))
   except:qv=0
   if eid and qv:_add_donation_line(c,gid,None,'En attente',receipt,'Matériel',qty=qv,equipment_id=eid); count+=1
  if not count:c.rollback();c.close();flash('Ajoutez au moins un montant, un arbre ou un matériel.');return redirect('/volunteer/donate')
  donor=c.execute('SELECT name FROM users WHERE id=?',(session['uid'],)).fetchone(); donor_name=(donor['name'] if donor else 'Un bénévole')
  notify_admins_in_tx(c,'Nouveau don à valider',donor_name+' a déclaré un don ('+receipt+').','/donations?status=pending','Don','donation_group',gid)
  c.commit();c.close();flash('Don envoyé pour validation. Les administrateurs ont été notifiés.');return redirect('/volunteer')
 c.close(); return page('Faire un don',"""<div class='card'><h2>🎁 Faire un don</h2><p class='sub'>Vous pouvez réunir argent, plusieurs espèces et plusieurs matériels dans un seul don.</p><form method='post' class='form'><div class='full card'><h3>💶 Argent</h3><label>Montant en DA<input type='number' min='0' step='0.01' name='amount' placeholder='0'></label></div><div class='full card'><div class='section-title'><h3>🌳 Arbres</h3><button type='button' class='action-btn action-primary' onclick='addTree()'>＋ Espèce</button></div><div id='treeRows'></div></div><div class='full card'><div class='section-title'><h3>🧰 Matériel</h3><button type='button' class='action-btn action-primary' onclick='addEq()'>＋ Matériel</button></div><div id='eqRows'></div></div><div class='full action-set'><button class='action-btn action-primary'>✓ Envoyer le don</button><a class='action-btn action-view' href='/volunteer'>🏠 Mon accueil</a></div></form></div><template id='treeTpl'><div class='don-line'><select name='species_id[]'><option value=''>Espèce</option>{% for x in species %}<option value='{{x.id}}'>{{x.name_fr}}</option>{% endfor %}</select><input type='number' min='1' name='tree_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template><template id='eqTpl'><div class='don-line'><select name='equipment_id[]'><option value=''>Matériel</option>{% for x in equipment %}<option value='{{x.id}}'>{{x.name}}</option>{% endfor %}</select><input type='number' min='1' name='equipment_quantity[]' placeholder='Quantité'><button type='button' class='action-btn action-delete' onclick='this.parentElement.remove()'>🗑 Retirer</button></div></template><script>function addTree(){treeRows.append(treeTpl.content.cloneNode(true))}function addEq(){eqRows.append(eqTpl.content.cloneNode(true))}addTree();addEq();</script>""",species=species,equipment=equipment)

@app.route('/public/donate')
def public_donate():
 if session.get('uid'): return redirect('/volunteer/donate' if not is_admin() else '/donations/new')
 return public_page('Faire un don',"""<div class='card'><h1>Faire un don</h1><p>Les bénévoles inscrits peuvent déclarer un don en argent, arbres, matériel, eau, transport ou main-d’œuvre. La déclaration est ensuite validée par l’association.</p><a class='btn' href='/public/register?next=/volunteer/donate'>Créer un compte</a> <a class='btn alt' href='/login?next=/volunteer/donate'>Se connecter</a></div>""")

@app.get('/api/communes/<int:wilaya_id>')
def api_communes(wilaya_id):
 c=db(); rows=c.execute('SELECT id,name FROM communes WHERE active=1 AND wilaya_id=? ORDER BY name',(wilaya_id,)).fetchall(); c.close(); return jsonify([dict(r) for r in rows])

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
 c=db(); stats={'projects':c.execute('SELECT COUNT(*) n FROM projects WHERE active=1').fetchone()['n'],'tasks_open':c.execute("SELECT COUNT(*) n FROM operational_tasks WHERE status IN ('Planifiée','En cours')").fetchone()['n'],'tasks_done':c.execute("SELECT COUNT(*) n FROM operational_tasks WHERE status='Terminée'").fetchone()['n'],'trees':c.execute('SELECT COUNT(*) n FROM trees WHERE active=1').fetchone()['n'],'priority':c.execute("SELECT COUNT(*) n FROM trees WHERE active=1 AND (watering_status!='À jour' OR health_status IN ('À surveiller','Urgent','Critique'))").fetchone()['n'],'volunteer_hours':c.execute('SELECT COALESCE(SUM(hours),0) n FROM volunteer_time_logs WHERE validated=1').fetchone()['n']}
 projects=c.execute("""SELECT p.id,p.code,p.name,p.status,p.target_trees,COUNT(DISTINCT t.id) tree_count,COUNT(DISTINCT ot.id) task_count,SUM(CASE WHEN ot.status='Terminée' THEN 1 ELSE 0 END) done_count FROM projects p LEFT JOIN trees t ON t.project_id=p.id AND t.active=1 LEFT JOIN operational_tasks ot ON ot.project_id=p.id WHERE p.active=1 GROUP BY p.id ORDER BY p.name""").fetchall(); c.close()
 return page('Rapports opérationnels',"""<div class='section-title'><div><h2>Rapport opérationnel</h2><p class='sub'>Vue consolidée des projets et interventions.</p></div><a class='btn' href='/reports/operations.csv'>Exporter CSV</a></div><div class='grid kpis' style='grid-template-columns:repeat(6,1fr)'>{% for label,value in [('Projets',stats.projects),('Tâches ouvertes',stats.tasks_open),('Tâches terminées',stats.tasks_done),('Arbres',stats.trees),('Arbres prioritaires',stats.priority),('Heures bénévoles',stats.volunteer_hours)] %}<div class='card kpi'><small>{{label}}</small><b>{{value}}</b></div>{% endfor %}</div><div class='card' style='overflow:auto'><table><tr><th>Projet</th><th>Statut</th><th>Arbres / objectif</th><th>Interventions</th><th>Terminées</th></tr>{% for p in projects %}<tr><td><a href='/projects/{{p.id}}'><b>{{p.code}} — {{p.name}}</b></a></td><td>{{p.status}}</td><td>{{p.tree_count}} / {{p.target_trees or 0}}</td><td>{{p.task_count}}</td><td>{{p.done_count or 0}}</td></tr>{% else %}<tr><td colspan='5'>Aucun projet.</td></tr>{% endfor %}</table></div>""",stats=stats,projects=projects)

@app.route('/reports/operations.csv')
@login_required
def operations_report_csv():
 import csv
 c=db(); rows=c.execute("""SELECT p.code,p.name,p.status,p.target_trees,COUNT(DISTINCT t.id) tree_count,COUNT(DISTINCT ot.id) task_count,SUM(CASE WHEN ot.status='Terminée' THEN 1 ELSE 0 END) done_count FROM projects p LEFT JOIN trees t ON t.project_id=p.id AND t.active=1 LEFT JOIN operational_tasks ot ON ot.project_id=p.id WHERE p.active=1 GROUP BY p.id ORDER BY p.name""").fetchall(); c.close()
 out=io.StringIO(); w=csv.writer(out,delimiter=';'); w.writerow(['Code','Projet','Statut','Objectif arbres','Arbres suivis','Interventions','Terminées'])
 for r in rows: w.writerow([r['code'],r['name'],r['status'],r['target_trees'],r['tree_count'],r['task_count'],r['done_count'] or 0])
 data=io.BytesIO(('\ufeff'+out.getvalue()).encode('utf-8')); data.seek(0); return send_file(data,mimetype='text/csv',as_attachment=True,download_name='rapport-operationnel-mytree.csv')



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
 if refs: c.execute('UPDATE zones SET active=0 WHERE id=?',(zid,)); msg='Zone archivée car elle possède un historique.'
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
 c=db(); tables=table_count(c); c.close()
 if using_postgres():
  return page('Sauvegarde et restauration',"""<div class='grid two'><div class='card'><h2>Créer une sauvegarde logique</h2><p>La version Online utilise PostgreSQL / Neon. MyTree peut exporter les données applicatives au format JSON.</p><p><b>Base :</b> PostgreSQL / Neon<br><b>Tables :</b> {{tables}}</p><a class='btn' href='/backup/download'>💾 Télécharger l’export JSON</a></div><div class='card danger-zone'><h2>Restauration</h2><p>La restauration automatique d’un ancien fichier SQLite est désactivée sur la version Online afin d’éviter d’écraser ou d’incohérer la base Neon.</p><p class='sub'>La migration d’une ancienne base SQLite vers Neon doit être faite par un outil de migration contrôlé.</p></div></div>""",tables=tables)
 check='ok'; size=os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
 return page('Sauvegarde et restauration',"""<div class='grid two'><div class='card'><h2>Créer une sauvegarde</h2><p>La sauvegarde contient la base SQLite complète : arbres, utilisateurs, dons, caisse, pépinière, matériel et paramètres.</p><p><b>État :</b> {{check}}<br><b>Tables :</b> {{tables}}<br><b>Taille :</b> {{'%.2f'|format(size/1024/1024)}} Mo</p><a class='btn' href='/backup/download'>💾 Télécharger la sauvegarde</a></div><div class='card danger-zone'><h2>Restaurer une sauvegarde</h2><p>Cette opération remplace la base actuelle. Une copie de sécurité automatique est créée avant restauration.</p><form method='post' action='/backup/restore' enctype='multipart/form-data' onsubmit="return confirm('Restaurer cette base et remplacer les données actuelles ?')"><label>Fichier SQLite<input type='file' name='backup_file' accept='.db,.sqlite,.sqlite3' required></label><p><button class='btn red'>Restaurer</button></p></form></div></div>""",check=check,tables=tables,size=size)

@app.route('/backup/download')
@login_required
def backup_download():
 if not is_admin(): return redirect('/')
 stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
 if using_postgres():
  c=db(); payload={'generated_at':datetime.now().isoformat(timespec='seconds'),'version':APP_VERSION,'database':'PostgreSQL/Neon','tables':export_database_json(c)}; c.close()
  raw=json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode('utf-8')
  return send_file(io.BytesIO(raw),as_attachment=True,download_name=f'MyTree-backup-{stamp}.json',mimetype='application/json')
 if not os.path.exists(DB_PATH): init_db()
 tmp=os.path.join(tempfile.gettempdir(),f'mytree-backup-{stamp}.db')
 src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(tmp); src.backup(dst); dst.close(); src.close()
 log_action('backup','database',None,os.path.basename(tmp))
 return send_file(tmp,as_attachment=True,download_name=f'MyTree-backup-{stamp}.db')

@app.post('/backup/restore')
@login_required
def backup_restore():
 if not is_admin(): return redirect('/')
 if using_postgres():
  flash('La restauration SQLite directe est désactivée sur PostgreSQL / Neon. Utilisez l’outil de migration dédié.'); return redirect('/backup')
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
 """Contrôle de disponibilité compatible SQLite local et PostgreSQL / Neon."""
 try:
  c=db(); c.execute('SELECT 1').fetchone(); tables=table_count(c); c.close()
  return jsonify({'status':'ok','version':APP_VERSION,'database':database_label(),'tables':tables}),200
 except Exception as exc:
  return jsonify({'status':'error','version':APP_VERSION,'database':database_label(),'error':str(exc)}),503


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
