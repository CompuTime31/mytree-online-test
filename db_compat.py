import os
import re
import sqlite3
from collections.abc import Mapping

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("STORAGE_URL")
)

try:
    import psycopg
    from psycopg import IntegrityError as PsycopgIntegrityError
except Exception:  # psycopg n'est requis que lorsque PostgreSQL est utilisé
    psycopg = None
    PsycopgIntegrityError = ()

DBIntegrityError = (sqlite3.IntegrityError, PsycopgIntegrityError) if PsycopgIntegrityError else (sqlite3.IntegrityError,)


def using_postgres():
    return bool(DATABASE_URL)


def database_label():
    return "PostgreSQL / Neon" if using_postgres() else "SQLite local"


class HybridRow(Mapping):
    """Ligne compatible avec sqlite3.Row: accès par nom ET par index."""
    def __init__(self, names, values):
        self._names = list(names)
        self._values = tuple(values)
        self._data = dict(zip(self._names, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __repr__(self):
        return repr(self._data)


class EmptyCursor:
    lastrowid = None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class PGCursor:
    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection
        self._names = [d.name for d in cursor.description] if cursor.description else []

    @property
    def lastrowid(self):
        # Équivalent de sqlite3 Cursor.lastrowid pour les tables SERIAL.
        try:
            with self._connection._conn.cursor() as c:
                c.execute("SELECT lastval()")
                return c.fetchone()[0]
        except Exception:
            return None

    def _row(self, values):
        if values is None:
            return None
        return HybridRow(self._names, values)

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(v) for v in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor:
            yield self._row(row)


class PGConnection:
    def __init__(self, url):
        if psycopg is None:
            raise RuntimeError("PostgreSQL est configuré mais psycopg n'est pas installé. Ajoutez psycopg[binary] à requirements.txt.")
        self._conn = psycopg.connect(url, autocommit=False)

    def execute(self, sql, params=()):
        translated = translate_sql(sql)
        if translated is None:
            return EmptyCursor()
        cur = self._conn.cursor()
        cur.execute(translated, tuple(params or ()))
        return PGCursor(cur, self)

    def executescript(self, script):
        for statement in split_sql_script(script):
            translated = translate_sql(statement)
            if translated:
                cur = self._conn.cursor()
                cur.execute(translated)
                cur.close()
        return EmptyCursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()



def connect_db(sqlite_path):
    if using_postgres():
        return PGConnection(DATABASE_URL)
    c = sqlite3.connect(sqlite_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def split_sql_script(script):
    """Découpe les scripts DDL simples utilisés par MyTree sans casser les chaînes SQL."""
    out, buf = [], []
    quote = None
    i = 0
    while i < len(script):
        ch = script[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                # SQL échappe une quote en la doublant.
                if i + 1 < len(script) and script[i + 1] == quote:
                    buf.append(script[i + 1])
                    i += 1
                else:
                    quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
                buf.append(ch)
            elif ch == ';':
                stmt = ''.join(buf).strip()
                if stmt:
                    out.append(stmt)
                buf = []
            else:
                buf.append(ch)
        i += 1
    stmt = ''.join(buf).strip()
    if stmt:
        out.append(stmt)
    return out


def replace_qmarks(sql):
    """Convertit les placeholders SQLite ? en placeholders psycopg %s, hors chaînes."""
    out = []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
                out.append(ch)
            elif ch == '?':
                out.append('%s')
            else:
                out.append(ch)
        i += 1
    return ''.join(out)


def translate_sql(sql):
    s = str(sql).strip()
    if not s:
        return None

    # PRAGMA SQLite sans équivalent nécessaire sous PostgreSQL.
    if re.match(r"(?is)^PRAGMA\s+foreign_keys\s*=", s):
        return None
    if re.match(r"(?is)^PRAGMA\s+(integrity_check|quick_check)\b", s):
        return "SELECT 'ok' AS integrity"

    m = re.match(r"(?is)^PRAGMA\s+table_info\(([^)]+)\)", s)
    if m:
        table = m.group(1).strip().strip('"\'')
        return (
            "SELECT column_name AS name FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}' ORDER BY ordinal_position"
        )

    # sqlite_master -> catalogue PostgreSQL.
    if re.search(r"(?i)\bsqlite_master\b", s):
        # Cas MyTree: SELECT name ... / SELECT COUNT(*) ... avec filtre name.
        s = re.sub(
            r"(?i)\bFROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'",
            "FROM information_schema.tables WHERE table_schema='public'",
            s,
        )
        s = re.sub(r"(?i)\bname\s+IN\s*\(", "table_name IN (", s)
        s = re.sub(r"(?i)^SELECT\s+name\s+FROM\s+information_schema\.tables", "SELECT table_name AS name FROM information_schema.tables", s)

    # DDL SQLite -> PostgreSQL.
    s = re.sub(r"(?i)\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY", s)

    # INSERT OR IGNORE -> ON CONFLICT DO NOTHING.
    if re.match(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", s):
        s = re.sub(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, count=1)
        if not re.search(r"(?i)\bON\s+CONFLICT\b", s):
            s += " ON CONFLICT DO NOTHING"

    # Équivalent SQLite de la dernière clé SERIAL de la session.
    if re.match(r"(?is)^SELECT\s+last_insert_rowid\(\)\s+(?:AS\s+)?id\s*$", s):
        s = "SELECT lastval() AS id"

    # Fonctions date SQLite utilisées par MyTree.
    s = s.replace(
        "CAST(julianday('now')-julianday(COALESCE(t.last_watered_at,t.planted_at,t.created_at)) AS INTEGER)",
        "CAST(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - CAST(COALESCE(t.last_watered_at,t.planted_at,t.created_at) AS timestamp)))/86400 AS INTEGER)",
    )
    s = re.sub(
        r"(?i)datetime\('now'\s*,\s*'-7 days'\)",
        "(CURRENT_TIMESTAMP - INTERVAL '7 days')",
        s,
    )
    s = re.sub(
        r"(?i)datetime\(([A-Za-z_][A-Za-z0-9_.]*)\)",
        r"CAST(NULLIF(\1,'') AS timestamp)",
        s,
    )

    return replace_qmarks(s)


def table_count(conn):
    if using_postgres():
        return conn.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='public'").fetchone()['n']
    return conn.execute("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'").fetchone()['n']


def table_names(conn):
    if using_postgres():
        rows = conn.execute("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name").fetchall()
    else:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [r['name'] for r in rows]


def export_database_json(conn):
    data = {}
    for table in table_names(conn):
        # Les noms viennent du catalogue DB, pas d'une entrée utilisateur.
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        data[table] = [dict(r) for r in rows]
    return data
