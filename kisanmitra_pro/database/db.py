import sqlite3
import json
import os
from datetime import datetime
from config import DB_PATH, DATABASE_URL, IS_POSTGRES

# Optional Postgres support
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    HAS_PSYCOPG2 = False

def get_conn():
    if IS_POSTGRES and HAS_PSYCOPG2:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_cursor(conn):
    if IS_POSTGRES and HAS_PSYCOPG2:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()

def fmt_query(query):
    """Replace ? with %s if using Postgres"""
    if IS_POSTGRES:
        return query.replace("?", "%s")
    return query


def init_db():
    """Initialize all tables"""
    conn = get_conn()
    c = get_cursor(conn)

    # Postgres uses SERIAL, SQLite uses AUTOINCREMENT
    auto_inc = "SERIAL" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    pk_user = "INTEGER PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY" # same

    # Farmers table
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS farmers (
            user_id     BIGINT PRIMARY KEY,
            name        TEXT DEFAULT '',
            username    TEXT DEFAULT '',
            lat         REAL DEFAULT 18.4088,
            lon         REAL DEFAULT 76.5604,
            location    TEXT DEFAULT 'Latur, Maharashtra',
            crops       TEXT DEFAULT '[]',
            language    TEXT DEFAULT 'hi',
            alerts      INTEGER DEFAULT 1,
            email       TEXT DEFAULT '',
            joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Queries table
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS queries (
            id          {auto_inc},
            user_id     BIGINT,
            query_type  TEXT,
            message     TEXT,
            response    TEXT,
            intent      TEXT,
            language    TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Pest reports
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS pest_reports (
            id          {auto_inc},
            user_id     BIGINT,
            lat         REAL,
            lon         REAL,
            location    TEXT,
            crop        TEXT,
            pest        TEXT,
            severity    TEXT,
            photo_id    TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Mandi price cache
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS mandi_cache (
            id          {auto_inc},
            crop        TEXT,
            market      TEXT,
            price       REAL,
            date        TEXT,
            cached_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Daily stats
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date            TEXT PRIMARY KEY,
            total_queries   INTEGER DEFAULT 0,
            unique_users    INTEGER DEFAULT 0,
            voice_queries   INTEGER DEFAULT 0,
            photo_queries   INTEGER DEFAULT 0,
            mandi_queries   INTEGER DEFAULT 0,
            pest_reports    INTEGER DEFAULT 0
        )
    """)

    # Dashboard users
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS dashboard_users (
            id          {auto_inc},
            google_id   TEXT UNIQUE,
            email       TEXT UNIQUE,
            name        TEXT,
            avatar_url  TEXT DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Land details
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS land_details (
            id           {auto_inc},
            user_id      BIGINT DEFAULT 0,
            email        TEXT DEFAULT '',
            area_acres   REAL DEFAULT 0,
            crop_type    TEXT DEFAULT '',
            soil_type    TEXT DEFAULT '',
            village      TEXT DEFAULT '',
            district     TEXT DEFAULT '',
            state        TEXT DEFAULT 'Maharashtra',
            lat          REAL DEFAULT 0,
            lon          REAL DEFAULT 0,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Soil reports
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS soil_reports (
            id                  {auto_inc},
            land_id             INTEGER DEFAULT 0,
            user_id             BIGINT DEFAULT 0,
            email               TEXT DEFAULT '',
            ph                  REAL DEFAULT 0,
            nitrogen_kg_ha      REAL DEFAULT 0,
            phosphorus_kg_ha    REAL DEFAULT 0,
            potassium_kg_ha     REAL DEFAULT 0,
            organic_matter_pct  REAL DEFAULT 0,
            moisture_pct        REAL DEFAULT 0,
            ec_ds_m             REAL DEFAULT 0,
            recommendation      TEXT DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized.")


# === FARMER OPERATIONS ===

def upsert_farmer(user_id: int, name: str = "", username: str = ""):
    conn = get_conn()
    cur = get_cursor(conn)
    # Migration: Add email column if it doesn't exist
    try:
        cur.execute("ALTER TABLE farmers ADD COLUMN email TEXT DEFAULT ''")
    except Exception:
        pass # Column already exists
        
    cur.execute(fmt_query("""
        INSERT INTO farmers (user_id, name, username)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            name = COALESCE(NULLIF(excluded.name, ''), farmers.name),
            username = COALESCE(NULLIF(excluded.username, ''), farmers.username)
    """), (user_id, name, username))
    conn.commit()
    conn.close()

def update_farmer_email(user_id: int, email: str):
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("UPDATE farmers SET email=? WHERE user_id=?"), (email, user_id))
    conn.commit()
    conn.close()


def get_farmer(user_id: int) -> dict:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("SELECT * FROM farmers WHERE user_id = ?"), (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["crops"] = json.loads(d.get("crops", "[]"))
        return d
    return {}


def update_farmer_location(user_id: int, lat: float, lon: float, location: str):
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        UPDATE farmers SET lat=?, lon=?, location=? WHERE user_id=?
    """), (lat, lon, location, user_id))
    conn.commit()
    conn.close()


def update_farmer_language(user_id: int, language: str):
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("UPDATE farmers SET language=? WHERE user_id=?"), (language, user_id))
    conn.commit()
    conn.close()


def toggle_alerts(user_id: int) -> bool:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("SELECT alerts FROM farmers WHERE user_id=?"), (user_id,))
    current = cur.fetchone()
    new_val = 0 if (current and current["alerts"]) else 1
    cur.execute(fmt_query("UPDATE farmers SET alerts=? WHERE user_id=?"), (new_val, user_id))
    conn.commit()
    conn.close()
    return bool(new_val)


def get_alert_users() -> list:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute("SELECT * FROM farmers WHERE alerts=1")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === QUERY LOGGING ===

def log_query(user_id: int, query_type: str, message: str,
              response: str, intent: str = "other", language: str = "hi"):
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO queries (user_id, query_type, message, response, intent, language)
        VALUES (?, ?, ?, ?, ?, ?)
    """), (user_id, query_type, message[:500], response[:1000], intent, language))

    # Update daily stats
    today = datetime.now().strftime("%Y-%m-%d")
    if IS_POSTGRES:
        cur.execute("""
            INSERT INTO daily_stats (date, total_queries) VALUES (%s, 1)
            ON CONFLICT(date) DO UPDATE SET total_queries = daily_stats.total_queries + 1
        """, (today,))
    else:
        cur.execute("""
            INSERT INTO daily_stats (date, total_queries) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET total_queries = total_queries + 1
        """, (today,))

    if query_type == "voice":
        cur.execute(fmt_query("UPDATE daily_stats SET voice_queries = voice_queries + 1 WHERE date=?"), (today,))
    elif query_type == "photo":
        cur.execute(fmt_query("UPDATE daily_stats SET photo_queries = photo_queries + 1 WHERE date=?"), (today,))
    elif query_type == "mandi":
        cur.execute(fmt_query("UPDATE daily_stats SET mandi_queries = mandi_queries + 1 WHERE date=?"), (today,))

    conn.commit()
    conn.close()


# === PEST REPORTS ===

def add_pest_report(user_id: int, lat: float, lon: float, location: str,
                    crop: str, pest: str, severity: str = "medium", photo_id: str = ""):
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO pest_reports (user_id, lat, lon, location, crop, pest, severity, photo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """), (user_id, lat, lon, location, crop, pest, severity, photo_id))

    today = datetime.now().strftime("%Y-%m-%d")
    if IS_POSTGRES:
        cur.execute("""
            INSERT INTO daily_stats (date, pest_reports) VALUES (%s, 1)
            ON CONFLICT(date) DO UPDATE SET pest_reports = daily_stats.pest_reports + 1
        """, (today,))
    else:
        cur.execute("""
            INSERT INTO daily_stats (date, pest_reports) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET pest_reports = pest_reports + 1
        """, (today,))

    conn.commit()
    conn.close()


def get_recent_pest_reports(limit: int = 20) -> list:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        SELECT p.*, f.location as farmer_location
        FROM pest_reports p
        LEFT JOIN farmers f ON p.user_id = f.user_id
        ORDER BY p.created_at DESC LIMIT ?
    """), (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === ANALYTICS ===

def get_analytics() -> dict:
    conn = get_conn()
    cur = get_cursor(conn)
    
    cur.execute("SELECT COUNT(*) as c FROM farmers")
    total_farmers = cur.fetchone()["c"]
    
    cur.execute("SELECT COUNT(*) as c FROM queries")
    total_queries = cur.fetchone()["c"]
    
    cur.execute("SELECT COUNT(*) as c FROM pest_reports")
    total_pest_reports = cur.fetchone()["c"]

    # Last 7 days stats
    cur.execute("""
        SELECT date, total_queries, unique_users, voice_queries, photo_queries,
               mandi_queries, pest_reports
        FROM daily_stats
        ORDER BY date DESC LIMIT 7
    """)
    weekly = cur.fetchall()

    # Top intents
    cur.execute("""
        SELECT intent, COUNT(*) as count FROM queries
        GROUP BY intent ORDER BY count DESC
    """)
    intents = cur.fetchall()

    # Top crops mentioned
    cur.execute("SELECT crops FROM farmers WHERE crops != '[]'")
    crops_raw = cur.fetchall()
    crop_count = {}
    for row in crops_raw:
        try:
            for crop in json.loads(row["crops"]):
                crop_count[crop] = crop_count.get(crop, 0) + 1
        except Exception:
            pass

    conn.close()

    return {
        "total_farmers": total_farmers,
        "total_queries": total_queries,
        "total_pest_reports": total_pest_reports,
        "weekly_stats": [dict(r) for r in weekly],
        "top_intents": [dict(r) for r in intents],
        "top_crops": sorted(crop_count.items(), key=lambda x: x[1], reverse=True)[:5]
    }


# === DASHBOARD USER OPERATIONS ===

def upsert_dashboard_user(google_id: str, email: str, name: str, avatar_url: str = "") -> dict:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO dashboard_users (google_id, email, name, avatar_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(google_id) DO UPDATE SET
            name = EXCLUDED.name,
            avatar_url = EXCLUDED.avatar_url,
            last_login = CURRENT_TIMESTAMP
    """), (google_id, email, name, avatar_url))
    conn.commit()
    cur.execute(fmt_query("SELECT * FROM dashboard_users WHERE google_id=?"), (google_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def get_dashboard_user_by_email(email: str) -> dict:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("SELECT * FROM dashboard_users WHERE email=?"), (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


# === LAND DETAILS ===

def save_land_details(user_id: int, email: str, area_acres: float, crop_type: str,
                      soil_type: str, village: str, district: str, state: str,
                      lat: float, lon: float) -> int:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO land_details (user_id, email, area_acres, crop_type, soil_type,
                                  village, district, state, lat, lon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """), (user_id, email, area_acres, crop_type, soil_type, village, district, state, lat, lon))
    
    # Handle lastrowid for both drivers
    if IS_POSTGRES:
        cur.execute("SELECT LASTVAL()")
        land_id = cur.fetchone()[0] if not hasattr(cur.fetchone(), 'get') else cur.fetchone()['lastval']
        # Actually in psycopg2 it's better to use RETURNING id
        # But let's try a simple RETURNING for future edits
    else:
        land_id = cur.lastrowid
        
    conn.commit()
    conn.close()
    return land_id


def get_land_details(email: str = "", user_id: int = 0) -> list:
    conn = get_conn()
    cur = get_cursor(conn)
    if email:
        cur.execute(fmt_query(
            "SELECT * FROM land_details WHERE email=? ORDER BY created_at DESC"), (email,)
        )
    else:
        cur.execute(fmt_query(
            "SELECT * FROM land_details WHERE user_id=? ORDER BY created_at DESC"), (user_id,)
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === SOIL REPORTS ===

def save_soil_report(land_id: int, user_id: int, email: str, ph: float,
                     nitrogen: float, phosphorus: float, potassium: float,
                     organic_matter: float, moisture: float, ec: float,
                     recommendation: str) -> int:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO soil_reports (land_id, user_id, email, ph, nitrogen_kg_ha,
                                  phosphorus_kg_ha, potassium_kg_ha, organic_matter_pct,
                                  moisture_pct, ec_ds_m, recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """), (land_id, user_id, email, ph, nitrogen, phosphorus, potassium,
           organic_matter, moisture, ec, recommendation))
    
    if IS_POSTGRES:
        cur.execute("SELECT LASTVAL()")
        res = cur.fetchone()
        report_id = res[0] if isinstance(res, tuple) else res['lastval']
    else:
        report_id = cur.lastrowid

    conn.commit()
    conn.close()
    return report_id


def get_soil_reports(email: str = "", user_id: int = 0, limit: int = 10) -> list:
    conn = get_conn()
    cur = get_cursor(conn)
    if email:
        cur.execute(fmt_query("""
            SELECT s.*, l.village, l.district, l.crop_type, l.area_acres
            FROM soil_reports s
            LEFT JOIN land_details l ON s.land_id = l.id
            WHERE s.email=? ORDER BY s.created_at DESC LIMIT ?
        """), (email, limit))
    else:
        cur.execute(fmt_query("""
            SELECT s.*, l.village, l.district, l.crop_type, l.area_acres
            FROM soil_reports s
            LEFT JOIN land_details l ON s.land_id = l.id
            WHERE s.user_id=? ORDER BY s.created_at DESC LIMIT ?
        """), (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
