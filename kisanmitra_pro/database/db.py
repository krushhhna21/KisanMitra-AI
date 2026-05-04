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


# ===== PHASE 1 ADDITIONS: Farmer Intelligence Engine =====

def _calculate_days_ago(created_at: str) -> int:
    """Helper: Calculate days elapsed"""
    try:
        if not created_at:
            return 0
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if isinstance(created_at, str) else created_at
        delta = datetime.now() - created.replace(tzinfo=None)
        return max(0, delta.days)
    except:
        return 0

def _calculate_hours_ago(created_at: str) -> int:
    """Helper: Calculate hours elapsed"""
    try:
        if not created_at:
            return 0
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if isinstance(created_at, str) else created_at
        delta = datetime.now() - created.replace(tzinfo=None)
        return max(0, delta.total_seconds() // 3600)
    except:
        return 0

def _compare_values(current: float, previous: float, field: str) -> str:
    """Helper: Compare trend direction"""
    if not current or not previous:
        return "→ Stable"
    diff_pct = ((current - previous) / previous) * 100 if previous != 0 else 0
    if diff_pct > 5:
        return "↑ Improving" if field in ['nitrogen', 'phosphorus', 'potassium', 'moisture_pct'] else "↑ Increasing"
    elif diff_pct < -5:
        return "↓ Declining" if field in ['nitrogen', 'phosphorus', 'potassium', 'moisture_pct'] else "↓ Decreasing"
    return "→ Stable"

def analyze_soil_trend(soil_history: list) -> str:
    """Analyze soil trend from history"""
    if not soil_history or len(soil_history) < 2:
        return "→ Stable"
    current = soil_history[0].get('nitrogen', 0)
    previous = soil_history[1].get('nitrogen', 0)
    return _compare_values(current, previous, 'nitrogen')

def analyze_sensor_trend(sensor_history: list) -> str:
    """Analyze sensor trend"""
    if not sensor_history:
        return "✅ Moisture stable"
    
    moisture_readings = [s.get('moisture', 0) for s in sensor_history[:5]]
    avg_moisture = sum(moisture_readings) / len(moisture_readings) if moisture_readings else 50
    
    if avg_moisture < 30:
        return "🔴 Dry trend"
    elif avg_moisture > 70:
        return "🟡 Wet trend"
    return "✅ Moisture stable"

def detect_community_risk(location: str, crop: str, pest_alerts: list) -> str:
    """Detect community pest risk"""
    if not pest_alerts:
        return ""
    
    high_risk = sum(1 for p in pest_alerts if p.get('severity') == 'high')
    total = len(pest_alerts)
    
    if high_risk > 0:
        return "🚨 HIGH RISK"
    elif total > 2:
        return "⚠️ MEDIUM RISK"
    return ""

def get_soil_history(user_id: int, email: str = "", limit: int = 5) -> list:
    """Get soil history with trend indicators"""
    try:
        conn = get_conn()
        cur = get_cursor(conn)
        
        if email:
            cur.execute(fmt_query("""
                SELECT id, user_id, email, ph, nitrogen, phosphorus, potassium, 
                       organic_matter, moisture_pct, ec_ds_m, recommendation, created_at
                FROM soil_reports
                WHERE email=? ORDER BY created_at DESC LIMIT ?
            """), (email, limit))
        else:
            cur.execute(fmt_query("""
                SELECT id, user_id, email, ph, nitrogen, phosphorus, potassium,
                       organic_matter, moisture_pct, ec_ds_m, recommendation, created_at
                FROM soil_reports
                WHERE user_id=? ORDER BY created_at DESC LIMIT ?
            """), (user_id, limit))
        
        reports = []
        for r in cur.fetchall():
            row = serialize_row(r)
            row['days_ago'] = _calculate_days_ago(row.get('created_at', ''))
            row['trend_direction'] = "→ Stable"
            row['recommended_action'] = row.get('recommendation', 'Monitor')
            reports.append(row)
        
        conn.close()
        return reports
    except Exception as e:
        print(f"[db] Error in get_soil_history: {e}")
        return []

def get_sensor_history(user_id: int, email: str = "", days: int = 30, limit: int = 10) -> list:
    """Get sensor history with analysis"""
    try:
        conn = get_conn()
        cur = get_cursor(conn)
        
        if email:
            cur.execute(fmt_query("""
                SELECT id, user_id, email, temperature, moisture, ph, created_at
                FROM sensor_data
                WHERE email=? AND created_at > datetime('now', '-' || ? || ' days')
                ORDER BY created_at DESC LIMIT ?
            """), (email, days, limit))
        else:
            cur.execute(fmt_query("""
                SELECT id, user_id, email, temperature, moisture, ph, created_at
                FROM sensor_data
                WHERE user_id=? AND created_at > datetime('now', '-' || ? || ' days')
                ORDER BY created_at DESC LIMIT ?
            """), (user_id, days, limit))
        
        readings = []
        for r in cur.fetchall():
            row = serialize_row(r)
            row['hours_ago'] = _calculate_hours_ago(row.get('created_at', ''))
            row['alert_flags'] = []
            readings.append(row)
        
        conn.close()
        return readings
    except Exception as e:
        print(f"[db] Error in get_sensor_history: {e}")
        return []

def get_local_pest_reports(crop: str, location: str, days: int = 30) -> list:
    """Get community pest reports"""
    try:
        return []
    except Exception as e:
        print(f"[db] Error in get_local_pest_reports: {e}")
        return []

def analyze_fertilizer_log(user_id: int, limit: int = 20) -> dict:
    """Extract fertilizer patterns"""
    return {'total_applications': 0, 'common_fertilizers': {}, 'application_frequency': 'Unknown'}

def get_farmer_intelligence(user_id: int, email: str = "") -> dict:
    """Comprehensive farmer intelligence"""
    try:
        farmer = get_farmer(user_id) if user_id else {}
        return {
            'farmer': farmer,
            'lands': get_land_details(user_id, email) if farmer else [],
            'soil_history': get_soil_history(user_id, email),
            'sensor_history': get_sensor_history(user_id, email),
            'pest_alerts': [],
            'fertilizer_log': {}
        }
    except Exception as e:
        print(f"[db] Error in get_farmer_intelligence: {e}")
        return {'farmer': {}, 'lands': [], 'soil_history': [], 'sensor_history': [], 'pest_alerts': [], 'fertilizer_log': {}}
