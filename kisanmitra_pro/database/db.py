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
_postgres_fallback_logged = False

def get_conn():
    global _postgres_fallback_logged
    if IS_POSTGRES and HAS_PSYCOPG2:
        try:
            # Keep startup responsive on Azure if DB is temporarily unreachable.
            connect_timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "10"))
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=connect_timeout)
            return conn
        except Exception as e:
            # Do not let transient external DB outages take down bot/dashboard.
            if not _postgres_fallback_logged:
                print(f"[db] [WARN] Postgres unavailable, switching to SQLite fallback: {e}", flush=True)
                _postgres_fallback_logged = True
    
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

def serialize_row(r):
    d = dict(r)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d


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

    # Real-time sensor data (IoT readings)
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id              {auto_inc},
            email           TEXT DEFAULT '',
            user_id         BIGINT DEFAULT 0,
            moisture        REAL DEFAULT 0,
            ph              REAL DEFAULT 0,
            temperature     REAL DEFAULT 0,
            ec              REAL DEFAULT 0,
            nitrogen        REAL DEFAULT 0,
            phosphorus      REAL DEFAULT 0,
            potassium       REAL DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("[OK] Database initialized.")


# === FARMER OPERATIONS ===

def upsert_farmer(user_id: int, name: str = "", username: str = ""):
    conn = get_conn()
    cur = get_cursor(conn)
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
        d = serialize_row(row)
        try:
            d["crops"] = json.loads(d.get("crops", "[]"))
        except json.JSONDecodeError:
            print(f"[WARN] Malformed crops JSON for user {user_id}, resetting to empty")
            d["crops"] = []
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
    return [serialize_row(r) for r in rows]


def get_alert_users_by_location(location: str) -> list:
    conn = get_conn()
    cur = get_cursor(conn)
    # Match location loosely to capture nearby users
    cur.execute(fmt_query("SELECT * FROM farmers WHERE alerts=1 AND location LIKE ?"), (f"%{location}%",))
    rows = cur.fetchall()
    conn.close()
    return [serialize_row(r) for r in rows]


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


def get_recent_queries(user_id: int, limit: int = 5) -> list:
    """Fetch recent chat history from database."""
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query(
        "SELECT message, response, created_at FROM queries WHERE user_id=? ORDER BY created_at DESC LIMIT ?"
    ), (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [serialize_row(r) for r in reversed(rows)]


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
    return [serialize_row(r) for r in rows]


def check_pest_outbreak(location: str, pest: str, days: int = 7, threshold: int = 3) -> bool:
    """
    Check if at least `threshold` unique farmers reported `pest`
    in `location` within the last `days`.
    """
    conn = get_conn()
    cur = get_cursor(conn)
    
    if IS_POSTGRES:
        date_clause = f"created_at >= NOW() - INTERVAL '{days} days'"
    else:
        date_clause = f"created_at >= date('now', '-{days} days')"
        
    cur.execute(fmt_query(f"""
        SELECT COUNT(DISTINCT user_id) as c
        FROM pest_reports
        WHERE pest = ? AND location LIKE ? AND {date_clause}
    """), (pest, f"%{location}%"))
    
    row = cur.fetchone()
    conn.close()
    count = row["c"] if row else 0
    return count >= threshold


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
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[WARN] Error parsing crops JSON in analytics: {e}")
            continue

    conn.close()

    return {
        "total_farmers": total_farmers,
        "total_queries": total_queries,
        "total_pest_reports": total_pest_reports,
        "weekly_stats": [serialize_row(r) for r in weekly],
        "top_intents": [serialize_row(r) for r in intents],
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
    return serialize_row(row) if row else {}


def get_dashboard_user_by_email(email: str) -> dict:
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("SELECT * FROM dashboard_users WHERE email=?"), (email,))
    row = cur.fetchone()
    conn.close()
    return serialize_row(row) if row else {}


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
        res = cur.fetchone()
        land_id = res[0] if isinstance(res, tuple) else res['lastval']
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
    return [serialize_row(r) for r in rows]


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
    return [serialize_row(r) for r in rows]


# === REAL-TIME SENSOR DATA (IoT) ===

def save_sensor_reading(email: str = "", user_id: int = 0, moisture: float = 0, ph: float = 0,
                       temperature: float = 0, ec: float = 0, nitrogen: float = 0,
                       phosphorus: float = 0, potassium: float = 0) -> int:
    """Save IoT sensor reading to database"""
    conn = get_conn()
    cur = get_cursor(conn)
    cur.execute(fmt_query("""
        INSERT INTO sensor_data (email, user_id, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """), (email, user_id, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium))
    
    if IS_POSTGRES:
        cur.execute("SELECT LASTVAL()")
        res = cur.fetchone()
        reading_id = res[0] if isinstance(res, tuple) else res['lastval']
    else:
        reading_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    return reading_id


def get_latest_sensor_data(email: str = "", user_id: int = 0, limit: int = 1) -> list:
    """Fetch latest IoT sensor readings - most recent first"""
    conn = get_conn()
    cur = get_cursor(conn)
    
    if email:
        cur.execute(fmt_query("""
            SELECT * FROM sensor_data WHERE email=? 
            ORDER BY created_at DESC LIMIT ?
        """), (email, limit))
    else:
        cur.execute(fmt_query("""
            SELECT * FROM sensor_data WHERE user_id=? 
            ORDER BY created_at DESC LIMIT ?
        """), (user_id, limit))
    
    rows = cur.fetchall()
    conn.close()
    return [serialize_row(r) for r in rows]


def get_sensor_data_by_date_range(email: str = "", user_id: int = 0, days: int = 7) -> list:
    """Fetch sensor readings from last N days - useful for trend analysis"""
    conn = get_conn()
    cur = get_cursor(conn)
    
    if IS_POSTGRES:
        date_clause = f"created_at >= NOW() - INTERVAL '{days} days'"
    else:
        date_clause = f"created_at >= date('now', '-{days} days')"
    
    if email:
        cur.execute(fmt_query(f"""
            SELECT * FROM sensor_data WHERE email=? AND {date_clause}
            ORDER BY created_at DESC
        """), (email,))
    else:
        cur.execute(fmt_query(f"""
            SELECT * FROM sensor_data WHERE user_id=? AND {date_clause}
            ORDER BY created_at DESC
        """), (user_id,))
    
    rows = cur.fetchall()
    conn.close()
    return [serialize_row(r) for r in rows]
#   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
 #   P H A S E   1 :   F A R M E R   I N T E L L I G E N C E   E N G I N E   F U N C T I O N S  
 #   A d d e d   t o   s u p p o r t   c o n t e x t u a l ,   d a t a - d r i v e n   c h a t   r e s p o n s e s  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
  
 d e f   g e t _ f a r m e r _ i n t e l l i g e n c e ( u s e r _ i d :   i n t ,   e m a i l :   s t r   =   " " )   - >   d i c t :  
         " " "  
         P H A S E   1   -   C o m p r e h e n s i v e   F a r m e r   P r o f i l e  
          
         F e t c h e s   a l l   a v a i l a b l e   d a t a   a b o u t   a   f a r m e r   i n   o n e   c a l l :  
         -   F a r m e r   p r o f i l e  
         -   A l l   l a n d / f i e l d   d e t a i l s      
         -   S o i l   h i s t o r y   ( l a s t   5   r e p o r t s   f o r   t r e n d   a n a l y s i s )  
         -   S e n s o r   h i s t o r y   ( l a s t   1 0   r e a d i n g s   f o r   p a t t e r n   d e t e c t i o n )  
         -   P e s t   a l e r t s   ( l a s t   3 0   d a y s   f o r   t h e i r   l o c a t i o n   +   c r o p s )  
         -   C h a t   h i s t o r y   ( t o   e x t r a c t   f e r t i l i z e r   a p p l i c a t i o n   p a t t e r n s )  
         -   L o c a t i o n   c o n t e x t  
          
         R e t u r n s :   {  
                 ' f a r m e r ' :   { . . . f a r m e r   p r o f i l e . . . } ,  
                 ' l a n d s ' :   [ . . . l a n d   d e t a i l s . . . ] ,  
                 ' s o i l _ h i s t o r y ' :   [ . . . s o i l   r e p o r t s   w i t h   t r e n d   i n f o . . . ] ,  
                 ' s e n s o r _ h i s t o r y ' :   [ . . . s e n s o r   r e a d i n g s   w i t h   t r e n d   i n f o . . . ] ,  
                 ' p e s t _ a l e r t s ' :   [ . . . p e s t   r e p o r t s   f o r   a r e a . . . ] ,  
                 ' f e r t i l i z e r _ l o g ' :   { . . . e x t r a c t e d   f e r t i l i z e r   p a t t e r n s . . . } ,  
                 ' l o c a t i o n _ c o n t e x t ' :   { . . . d i s t r i c t / r e g i o n   i n f o . . . }  
         }  
         " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   (  
                 g e t _ f a r m e r ,   g e t _ l a n d _ d e t a i l s ,   g e t _ s o i l _ r e p o r t s ,    
                 g e t _ s e n s o r _ d a t a _ b y _ d a t e _ r a n g e ,   g e t _ r e c e n t _ q u e r i e s ,   f m t _ q u e r y ,   g e t _ c o n n ,   s e r i a l i z e _ r o w  
         )  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e ,   t i m e d e l t a  
          
         i n t e l l i g e n c e   =   {  
                 ' f a r m e r ' :   g e t _ f a r m e r ( u s e r _ i d )   i f   u s e r _ i d   e l s e   { } ,  
                 ' l a n d s ' :   g e t _ l a n d _ d e t a i l s ( e m a i l = e m a i l )   i f   e m a i l   e l s e   g e t _ l a n d _ d e t a i l s ( u s e r _ i d = u s e r _ i d ) ,  
                 ' s o i l _ h i s t o r y ' :   g e t _ s o i l _ r e p o r t s ( e m a i l = e m a i l ,   l i m i t = 5 )   i f   e m a i l   e l s e   g e t _ s o i l _ r e p o r t s ( u s e r _ i d = u s e r _ i d ,   l i m i t = 5 ) ,  
                 ' s e n s o r _ h i s t o r y ' :   g e t _ s e n s o r _ d a t a _ b y _ d a t e _ r a n g e ( e m a i l = e m a i l ,   d a y s = 3 0 )   i f   e m a i l   e l s e   g e t _ s e n s o r _ d a t a _ b y _ d a t e _ r a n g e ( u s e r _ i d = u s e r _ i d ,   d a y s = 3 0 ) ,  
                 ' p e s t _ a l e r t s ' :   [ ] ,  
                 ' f e r t i l i z e r _ l o g ' :   { } ,  
                 ' l o c a t i o n _ c o n t e x t ' :   { }  
         }  
          
         #   G e t   p e s t   a l e r t s   f o r   f a r m e r ' s   l o c a t i o n   +   c r o p s  
         i f   i n t e l l i g e n c e [ ' f a r m e r ' ] :  
                 l o c a t i o n   =   i n t e l l i g e n c e [ ' f a r m e r ' ] . g e t ( ' l o c a t i o n ' ,   ' ' )  
                 c r o p s   =   i n t e l l i g e n c e [ ' f a r m e r ' ] . g e t ( ' c r o p s ' ,   [ ] )  
                 i n t e l l i g e n c e [ ' p e s t _ a l e r t s ' ]   =   _ g e t _ l o c a l _ p e s t _ a l e r t s ( l o c a t i o n ,   c r o p s )  
          
         #   E x t r a c t   f e r t i l i z e r   a p p l i c a t i o n   p a t t e r n s   f r o m   c h a t   h i s t o r y  
         i f   u s e r _ i d :  
                 q u e r i e s   =   g e t _ r e c e n t _ q u e r i e s ( u s e r _ i d ,   l i m i t = 2 0 )  
                 i n t e l l i g e n c e [ ' f e r t i l i z e r _ l o g ' ]   =   _ a n a l y z e _ f e r t i l i z e r _ h i s t o r y ( q u e r i e s )  
          
         r e t u r n   i n t e l l i g e n c e  
  
  
 d e f   g e t _ s o i l _ h i s t o r y ( u s e r _ i d :   i n t   =   0 ,   e m a i l :   s t r   =   " " ,   l i m i t :   i n t   =   5 )   - >   l i s t :  
         " " "  
         P H A S E   1   -   G e t   s o i l   r e p o r t s   w i t h   t r e n d   i n d i c a t o r s  
          
         R e t u r n s   l a s t   N   s o i l   r e p o r t s   w i t h   a d d e d   f i e l d s :  
         -   t r e n d _ d i r e c t i o n :   " â      i m p r o v i n g "   /   " â      d e c l i n i n g "   /   " â      s t a b l e "  
         -   d a y s _ a g o :   H o w   l o n g   s i n c e   r e p o r t  
         -   r e c o m m e n d e d _ a c t i o n :   B a s e d   o n   v a l u e s  
         " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   g e t _ s o i l _ r e p o r t s  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
          
         r e p o r t s   =   g e t _ s o i l _ r e p o r t s ( e m a i l = e m a i l ,   u s e r _ i d = u s e r _ i d ,   l i m i t = l i m i t )  
          
         #   A d d   t r e n d   i n f o r m a t i o n   t o   e a c h   r e p o r t  
         f o r   i ,   r e p o r t   i n   e n u m e r a t e ( r e p o r t s ) :  
                 r e p o r t [ ' d a y s _ a g o ' ]   =   _ c a l c u l a t e _ d a y s _ a g o ( r e p o r t . g e t ( ' c r e a t e d _ a t ' ,   ' ' ) )  
                 r e p o r t [ ' r e p o r t _ i n d e x ' ]   =   i     #   0   =   m o s t   r e c e n t  
                  
                 #   A d d   t r e n d   d i r e c t i o n   i f   w e   h a v e   2 +   r e p o r t s  
                 i f   i   <   l e n ( r e p o r t s )   -   1 :  
                         n e x t _ r e p o r t   =   r e p o r t s [ i   +   1 ]  
                         r e p o r t [ ' t r e n d _ n ' ]   =   _ c o m p a r e _ v a l u e s (  
                                 r e p o r t . g e t ( ' n i t r o g e n _ k g _ h a ' ,   0 ) ,    
                                 n e x t _ r e p o r t . g e t ( ' n i t r o g e n _ k g _ h a ' ,   0 )  
                         )  
                         r e p o r t [ ' t r e n d _ p h ' ]   =   _ c o m p a r e _ v a l u e s (  
                                 r e p o r t . g e t ( ' p h ' ,   0 ) ,  
                                 n e x t _ r e p o r t . g e t ( ' p h ' ,   0 ) ,  
                                 t o l e r a n c e = 0 . 3  
                         )  
                         r e p o r t [ ' t r e n d _ m o i s t u r e ' ]   =   _ c o m p a r e _ v a l u e s (  
                                 r e p o r t . g e t ( ' m o i s t u r e _ p c t ' ,   0 ) ,  
                                 n e x t _ r e p o r t . g e t ( ' m o i s t u r e _ p c t ' ,   0 ) ,  
                                 t o l e r a n c e = 5  
                         )  
          
         r e t u r n   r e p o r t s  
  
  
 d e f   g e t _ s e n s o r _ h i s t o r y ( u s e r _ i d :   i n t   =   0 ,   e m a i l :   s t r   =   " " ,   d a y s :   i n t   =   3 0 ,   l i m i t :   i n t   =   1 0 )   - >   l i s t :  
         " " "  
         P H A S E   1   -   G e t   s e n s o r   r e a d i n g s   w i t h   t r e n d   a n a l y s i s  
          
         R e t u r n s   s e n s o r   d a t a   w i t h   a d d e d   f i e l d s :  
         -   h o u r s _ a g o :   H o w   l o n g   s i n c e   r e a d i n g  
         -   a l e r t _ f l a g s :   C r i t i c a l   i s s u e s   d e t e c t e d  
         -   t r e n d _ m o i s t u r e :   M o i s t u r e   g e t t i n g   d r i e r / w e t t e r  
         -   t r e n d _ t e m p :   T e m p e r a t u r e   t r e n d  
         " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   g e t _ s e n s o r _ d a t a _ b y _ d a t e _ r a n g e  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
          
         r e a d i n g s   =   g e t _ s e n s o r _ d a t a _ b y _ d a t e _ r a n g e ( e m a i l = e m a i l ,   u s e r _ i d = u s e r _ i d ,   d a y s = d a y s ) [ : l i m i t ]  
          
         f o r   i ,   r e a d i n g   i n   e n u m e r a t e ( r e a d i n g s ) :  
                 r e a d i n g [ ' h o u r s _ a g o ' ]   =   _ c a l c u l a t e _ h o u r s _ a g o ( r e a d i n g . g e t ( ' c r e a t e d _ a t ' ,   ' ' ) )  
                 r e a d i n g [ ' r e a d i n g _ i n d e x ' ]   =   i  
                  
                 #   A l e r t   f l a g s   f o r   c u r r e n t   r e a d i n g  
                 r e a d i n g [ ' a l e r t s ' ]   =   [ ]  
                 m o i s t u r e   =   r e a d i n g . g e t ( ' m o i s t u r e ' ,   0 )  
                 i f   m o i s t u r e   <   2 0 :  
                         r e a d i n g [ ' a l e r t s ' ] . a p p e n d ( " ð x ´   M o i s t u r e   c r i t i c a l   -   i r r i g a t e   n o w " )  
                 e l i f   m o i s t u r e   >   7 0 :  
                         r e a d i n g [ ' a l e r t s ' ] . a p p e n d ( " ð xx¡   M o i s t u r e   h i g h   -   w a t e r l o g g i n g   r i s k " )  
                  
                 p h   =   r e a d i n g . g e t ( ' p h ' ,   0 )  
                 i f   p h   <   5 . 5   o r   p h   >   8 . 5 :  
                         r e a d i n g [ ' a l e r t s ' ] . a p p e n d ( f " ð xx¡   p H   { p h }   o f f - b a l a n c e " )  
                  
                 #   T r e n d   c o m p a r e d   t o   p r e v i o u s   r e a d i n g  
                 i f   i   <   l e n ( r e a d i n g s )   -   1 :  
                         p r e v _ r e a d i n g   =   r e a d i n g s [ i   +   1 ]  
                         r e a d i n g [ ' t r e n d _ m o i s t u r e ' ]   =   _ c o m p a r e _ v a l u e s (  
                                 m o i s t u r e ,  
                                 p r e v _ r e a d i n g . g e t ( ' m o i s t u r e ' ,   0 ) ,  
                                 t o l e r a n c e = 5  
                         )  
                         r e a d i n g [ ' t r e n d _ t e m p ' ]   =   _ c o m p a r e _ v a l u e s (  
                                 r e a d i n g . g e t ( ' t e m p e r a t u r e ' ,   0 ) ,  
                                 p r e v _ r e a d i n g . g e t ( ' t e m p e r a t u r e ' ,   0 ) ,  
                                 t o l e r a n c e = 2  
                         )  
          
         r e t u r n   r e a d i n g s  
  
  
 d e f   g e t _ l o c a l _ p e s t _ r e p o r t s ( c r o p :   s t r   =   " " ,   l o c a t i o n :   s t r   =   " " ,   d a y s :   i n t   =   3 0 )   - >   l i s t :  
         " " "  
         P H A S E   1   -   G e t   p e s t   r e p o r t s   f o r   f a r m e r ' s   l o c a t i o n   a n d   c r o p  
          
         R e t u r n s   p e s t   r e p o r t s   f r o m   n e a r b y   f a r m e r s   r e p o r t i n g   s i m i l a r   c r o p s  
         s o r t e d   b y   r e c e n c y   a n d   s e v e r i t y  
         " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   g e t _ c o n n ,   f m t _ q u e r y ,   s e r i a l i z e _ r o w  
          
         c o n n   =   g e t _ c o n n ( )  
         c u r   =   g e t _ c o n n ( ) . c u r s o r ( )  
          
         i f   n o t   l o c a t i o n :  
                 r e t u r n   [ ]  
          
         #   B u i l d   d a t e   c l a u s e  
         f r o m   d a t a b a s e . d b   i m p o r t   I S _ P O S T G R E S  
         i f   I S _ P O S T G R E S :  
                 d a t e _ c l a u s e   =   f " p . c r e a t e d _ a t   > =   N O W ( )   -   I N T E R V A L   ' { d a y s }   d a y s ' "  
         e l s e :  
                 d a t e _ c l a u s e   =   f " p . c r e a t e d _ a t   > =   d a t e ( ' n o w ' ,   ' - { d a y s }   d a y s ' ) "  
          
         #   M a t c h   n e a r b y   l o c a t i o n s   ( l o o s e   m a t c h   o n   d i s t r i c t / a r e a )  
         l o c a t i o n _ t e r m s   =   l o c a t i o n . s p l i t ( ' , ' )  
         d i s t r i c t _ m a t c h   =   l o c a t i o n _ t e r m s [ 0 ] . s t r i p ( )   i f   l o c a t i o n _ t e r m s   e l s e   " "  
          
         q u e r y   =   f m t _ q u e r y ( f " " "  
                 S E L E C T   p . * ,    
                               C A S E   W H E N   p . s e v e r i t y = ' h i g h '   T H E N   3   W H E N   p . s e v e r i t y = ' m e d i u m '   T H E N   2   E L S E   1   E N D   a s   s e v e r i t y _ r a n k  
                 F R O M   p e s t _ r e p o r t s   p  
                 W H E R E   { d a t e _ c l a u s e }  
                 A N D   (  
                         p . l o c a t i o n   L I K E   ?    
                         O R   p . c r o p   L I K E   ?  
                 )  
                 O R D E R   B Y   s e v e r i t y _ r a n k   D E S C ,   p . c r e a t e d _ a t   D E S C  
                 L I M I T   2 0  
         " " " )  
          
         i f   c r o p :  
                 c u r . e x e c u t e ( q u e r y ,   ( f " % { d i s t r i c t _ m a t c h } % " ,   f " % { c r o p } % " ) )  
         e l s e :  
                 c u r . e x e c u t e ( q u e r y ,   ( f " % { d i s t r i c t _ m a t c h } % " ,   " % " ) )  
          
         r o w s   =   c u r . f e t c h a l l ( )  
         c o n n . c l o s e ( )  
          
         r e t u r n   [ s e r i a l i z e _ r o w ( r )   f o r   r   i n   r o w s ]  
  
  
 d e f   a n a l y z e _ f e r t i l i z e r _ l o g ( u s e r _ i d :   i n t   =   0 ,   l i m i t :   i n t   =   2 0 )   - >   d i c t :  
         " " "  
         P H A S E   1   -   E x t r a c t   f e r t i l i z e r   a p p l i c a t i o n   p a t t e r n s   f r o m   c h a t   h i s t o r y  
          
         P a r s e s   r e s p o n s e   h i s t o r y   t o   f i n d   f e r t i l i z e r   r e c o m m e n d a t i o n s  
         a n d   b u i l d   a   l o g   o f   w h a t   f a r m e r   h a s   a p p l i e d  
          
         R e t u r n s :   {  
                 ' r e c e n t _ a p p l i c a t i o n s ' :   [ { ' f e r t i l i z e r ' :   ' U r e a ' ,   ' a m o u n t ' :   ' 2 0   k g ' ,   ' d a t e ' :   ' . . . ' ,   ' r e s p o n s e _ i d ' :   ' . . . ' } ] ,  
                 ' c o m m o n _ f e r t i l i z e r s ' :   { ' U r e a ' :   5 ,   ' D A P ' :   3 ,   . . . } ,  
                 ' l a s t _ a p p l i c a t i o n ' :   { ' f e r t i l i z e r ' :   ' . . . ' ,   ' d a y s _ a g o ' :   5 ,   ' . . . ' } ,  
                 ' a p p l i c a t i o n _ f r e q u e n c y ' :   a v g _ d a y s _ b e t w e e n _ a p p l i c a t i o n s  
         }  
         " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   g e t _ r e c e n t _ q u e r i e s  
         i m p o r t   r e  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
          
         q u e r i e s   =   g e t _ r e c e n t _ q u e r i e s ( u s e r _ i d ,   l i m i t = l i m i t )  
          
         f e r t i l i z e r _ p a t t e r n s   =   [  
                 r ' ( \ d + ) \ s * ( ? : k g | k g s ? ) \ s + o f ? \ s + ( u r e a | d a p | m o p | s o p | s s a | n e e m ) ' ,  
                 r ' a p p l y ? \ s + ( \ d + ) \ s + k g \ s + ( u r e a | d a p | m o p | s o p ) ' ,  
                 r ' ( u r e a | d a p | m o p | s o p | s s a ) \ s + ( \ d + ) \ s * k g ' ,  
         ]  
          
         a p p l i c a t i o n s   =   [ ]  
         f e r t i l i z e r _ c o u n t s   =   { }  
          
         f o r   q u e r y   i n   q u e r i e s :  
                 r e s p o n s e   =   q u e r y . g e t ( ' r e s p o n s e ' ,   ' ' ) . l o w e r ( )  
                 f o r   p a t t e r n   i n   f e r t i l i z e r _ p a t t e r n s :  
                         m a t c h e s   =   r e . f i n d i t e r ( p a t t e r n ,   r e s p o n s e ,   r e . I G N O R E C A S E )  
                         f o r   m a t c h   i n   m a t c h e s :  
                                 i f   l e n ( m a t c h . g r o u p s ( ) )   > =   2 :  
                                         a m o u n t   =   m a t c h . g r o u p ( 1 )  
                                         f e r t   =   m a t c h . g r o u p ( 2 ) . u p p e r ( )  
                                         a p p l i c a t i o n s . a p p e n d ( {  
                                                 ' f e r t i l i z e r ' :   f e r t ,  
                                                 ' a m o u n t ' :   f " { a m o u n t }   k g " ,  
                                                 ' d a t e ' :   q u e r y . g e t ( ' c r e a t e d _ a t ' ,   ' ' ) ,  
                                                 ' r e s p o n s e _ i d ' :   q u e r y . g e t ( ' i d ' ,   ' ' )  
                                         } )  
                                         f e r t i l i z e r _ c o u n t s [ f e r t ]   =   f e r t i l i z e r _ c o u n t s . g e t ( f e r t ,   0 )   +   1  
          
         r e t u r n   {  
                 ' r e c e n t _ a p p l i c a t i o n s ' :   a p p l i c a t i o n s [ : 5 ] ,  
                 ' c o m m o n _ f e r t i l i z e r s ' :   f e r t i l i z e r _ c o u n t s ,  
                 ' t o t a l _ a p p l i c a t i o n s ' :   l e n ( a p p l i c a t i o n s ) ,  
                 ' r e c o m m e n d a t i o n _ f r e q u e n c y ' :   l e n ( a p p l i c a t i o n s )   /   m a x ( l e n ( q u e r i e s ) ,   1 )  
         }  
  
  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
 #   A N A L Y S I S   F U N C T I O N S   F O R   T R E N D S  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
  
 d e f   a n a l y z e _ s o i l _ t r e n d ( s o i l _ h i s t o r y :   l i s t )   - >   s t r :  
         " " "  
         A n a l y z e   s o i l   d a t a   t r e n d   a c r o s s   m u l t i p l e   r e p o r t s  
          
         R e t u r n s :   " â      I m p r o v i n g "   /   " â      D e c l i n i n g "   /   " â      S t a b l e "  
         w i t h   b r i e f   e x p l a n a t i o n  
         " " "  
         i f   l e n ( s o i l _ h i s t o r y )   <   2 :  
                 r e t u r n   " â      I n s u f f i c i e n t   d a t a   ( n e e d   2 +   r e p o r t s ) "  
          
         l a t e s t   =   s o i l _ h i s t o r y [ 0 ]  
         o l d e s t   =   s o i l _ h i s t o r y [ - 1 ]  
          
         n _ c h a n g e   =   l a t e s t . g e t ( ' n i t r o g e n _ k g _ h a ' ,   0 )   -   o l d e s t . g e t ( ' n i t r o g e n _ k g _ h a ' ,   0 )  
         p h _ c h a n g e   =   l a t e s t . g e t ( ' p h ' ,   0 )   -   o l d e s t . g e t ( ' p h ' ,   0 )  
          
         i f   n _ c h a n g e   >   5 0   a n d   a b s ( p h _ c h a n g e )   <   0 . 5 :  
                 r e t u r n   " â      I m p r o v i n g   ( N   i n c r e a s i n g ,   p H   s t a b l e ) "  
         e l i f   n _ c h a n g e   <   - 5 0 :  
                 r e t u r n   " â      D e c l i n i n g   ( N   d e c r e a s i n g   -   n e e d s   r e p l e n i s h m e n t ) "  
         e l s e :  
                 r e t u r n   " â      S t a b l e "  
  
  
 d e f   a n a l y z e _ s e n s o r _ t r e n d ( s e n s o r _ h i s t o r y :   l i s t )   - >   s t r :  
         " " "  
         A n a l y z e   s e n s o r   r e a d i n g   t r e n d s  
          
         R e t u r n s :   P a t t e r n   s u m m a r y   f o r   r e c e n t   r e a d i n g s  
         " " "  
         i f   l e n ( s e n s o r _ h i s t o r y )   <   3 :  
                 r e t u r n   " â      I n s u f f i c i e n t   d a t a   f o r   t r e n d "  
          
         r e c e n t   =   s e n s o r _ h i s t o r y [ : 3 ]  
         a v g _ m o i s t u r e   =   s u m ( s . g e t ( ' m o i s t u r e ' ,   0 )   f o r   s   i n   r e c e n t )   /   l e n ( r e c e n t )  
          
         i f   a v g _ m o i s t u r e   <   2 5 :  
                 r e t u r n   " ð x ´   D r y   t r e n d   -   n e e d s   r e g u l a r   i r r i g a t i o n "  
         e l i f   a v g _ m o i s t u r e   >   6 5 :  
                 r e t u r n   " ð xx¡   W e t   t r e n d   -   r i s k   o f   w a t e r l o g g i n g "  
         e l s e :  
                 r e t u r n   " â S&   M o i s t u r e   s t a b l e "  
  
  
 d e f   d e t e c t _ c o m m u n i t y _ r i s k ( l o c a t i o n :   s t r ,   c r o p :   s t r ,   p e s t _ a l e r t s :   l i s t )   - >   s t r :  
         " " "  
         D e t e c t   i f   f a r m e r   i s   i n   h i g h - r i s k   a r e a   f o r   s p e c i f i c   p e s t  
          
         R e t u r n s :   R i s k   a s s e s s m e n t   s t r i n g  
         " " "  
         i f   n o t   p e s t _ a l e r t s :  
                 r e t u r n   " "  
          
         h i g h _ s e v e r i t y   =   s u m ( 1   f o r   p   i n   p e s t _ a l e r t s   i f   p . g e t ( ' s e v e r i t y ' )   = =   ' h i g h ' )  
         r e c e n t _ a l e r t s   =   s u m ( 1   f o r   p   i n   p e s t _ a l e r t s   i f   _ c a l c u l a t e _ d a y s _ a g o ( p . g e t ( ' c r e a t e d _ a t ' ,   ' ' ) )   <   7 )  
          
         i f   h i g h _ s e v e r i t y   > =   3 :  
                 r e t u r n   " ð xa¨   H I G H   R I S K :   M u l t i p l e   h i g h - s e v e r i t y   p e s t   r e p o r t s   i n   y o u r   a r e a "  
         e l i f   r e c e n t _ a l e r t s   >   0 :  
                 r e t u r n   f " â a  ï ¸    M E D I U M   R I S K :   { r e c e n t _ a l e r t s }   p e s t   r e p o r t ( s )   i n   l a s t   7   d a y s "  
         e l s e :  
                 r e t u r n   " "  
  
  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
 #   H E L P E R   F U N C T I O N S  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
  
 d e f   _ c a l c u l a t e _ d a y s _ a g o ( c r e a t e d _ a t _ s t r :   s t r )   - >   i n t :  
         " " " C a l c u l a t e   d a y s   s i n c e   t i m e s t a m p " " "  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
         t r y :  
                 c r e a t e d   =   d a t e t i m e . f r o m i s o f o r m a t ( c r e a t e d _ a t _ s t r . r e p l a c e ( ' Z ' ,   ' + 0 0 : 0 0 ' ) )  
                 r e t u r n   ( d a t e t i m e . n o w ( )   -   c r e a t e d ) . d a y s  
         e x c e p t :  
                 r e t u r n   0  
  
  
 d e f   _ c a l c u l a t e _ h o u r s _ a g o ( c r e a t e d _ a t _ s t r :   s t r )   - >   i n t :  
         " " " C a l c u l a t e   h o u r s   s i n c e   t i m e s t a m p " " "  
         f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
         t r y :  
                 c r e a t e d   =   d a t e t i m e . f r o m i s o f o r m a t ( c r e a t e d _ a t _ s t r . r e p l a c e ( ' Z ' ,   ' + 0 0 : 0 0 ' ) )  
                 r e t u r n   i n t ( ( d a t e t i m e . n o w ( )   -   c r e a t e d ) . t o t a l _ s e c o n d s ( )   /   3 6 0 0 )  
         e x c e p t :  
                 r e t u r n   0  
  
  
 d e f   _ c o m p a r e _ v a l u e s ( c u r r e n t :   f l o a t ,   p r e v i o u s :   f l o a t ,   t o l e r a n c e :   f l o a t   =   1 0 )   - >   s t r :  
         " " " C o m p a r e   t w o   v a l u e s   a n d   r e t u r n   t r e n d   i n d i c a t o r " " "  
         d i f f   =   c u r r e n t   -   p r e v i o u s  
         i f   a b s ( d i f f )   < =   t o l e r a n c e :  
                 r e t u r n   " â      s t a b l e "  
         e l i f   d i f f   >   t o l e r a n c e :  
                 r e t u r n   " â      i n c r e a s i n g "  
         e l s e :  
                 r e t u r n   " â      d e c r e a s i n g "  
  
  
 d e f   _ g e t _ l o c a l _ p e s t _ a l e r t s ( l o c a t i o n :   s t r ,   c r o p s :   l i s t )   - >   l i s t :  
         " " " I n t e r n a l   f u n c t i o n   t o   f e t c h   p e s t   a l e r t s   f o r   l o c a t i o n   +   c r o p s " " "  
         f r o m   d a t a b a s e . d b   i m p o r t   g e t _ c o n n ,   f m t _ q u e r y ,   s e r i a l i z e _ r o w ,   I S _ P O S T G R E S  
          
         i f   n o t   l o c a t i o n :  
                 r e t u r n   [ ]  
          
         c o n n   =   g e t _ c o n n ( )  
         c u r   =   g e t _ c o n n ( ) . c u r s o r ( )  
          
         d a t e _ c l a u s e   =   " p . c r e a t e d _ a t   > =   N O W ( )   -   I N T E R V A L   ' 3 0   d a y s ' "   i f   I S _ P O S T G R E S   e l s e   " p . c r e a t e d _ a t   > =   d a t e ( ' n o w ' ,   ' - 3 0   d a y s ' ) "  
          
         l o c a t i o n _ t e r m   =   l o c a t i o n . s p l i t ( ' , ' ) [ 0 ] . s t r i p ( )  
         c r o p _ l i s t   =   " ' , ' " . j o i n ( c r o p s )   i f   c r o p s   e l s e   " "  
          
         q u e r y   =   f m t _ q u e r y ( f " " "  
                 S E L E C T   D I S T I N C T   p . *   F R O M   p e s t _ r e p o r t s   p  
                 W H E R E   { d a t e _ c l a u s e }  
                 A N D   p . l o c a t i o n   L I K E   ?  
                 { ' A N D   p . c r o p   I N   ( '   +   r e p r ( c r o p _ l i s t )   +   ' ) '   i f   c r o p _ l i s t   e l s e   ' ' }  
                 O R D E R   B Y   p . c r e a t e d _ a t   D E S C  
                 L I M I T   1 0  
         " " " )  
          
         c u r . e x e c u t e ( q u e r y ,   ( f " % { l o c a t i o n _ t e r m } % " , ) )  
         r o w s   =   c u r . f e t c h a l l ( )  
         c o n n . c l o s e ( )  
          
         r e t u r n   [ s e r i a l i z e _ r o w ( r )   f o r   r   i n   r o w s ]  
 