import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize all tables"""
    conn = get_conn()
    c = conn.cursor()

    # Farmers table
    c.execute("""
        CREATE TABLE IF NOT EXISTS farmers (
            user_id     INTEGER PRIMARY KEY,
            name        TEXT DEFAULT '',
            username    TEXT DEFAULT '',
            lat         REAL DEFAULT 18.4088,
            lon         REAL DEFAULT 76.5604,
            location    TEXT DEFAULT 'Latur, Maharashtra',
            crops       TEXT DEFAULT '[]',
            language    TEXT DEFAULT 'hi',
            alerts      INTEGER DEFAULT 1,
            joined_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Queries table — every message logged
    c.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            query_type  TEXT,  -- text/voice/photo/mandi/scheme/weather
            message     TEXT,
            response    TEXT,
            intent      TEXT,  -- crop/pest/weather/mandi/scheme/other
            language    TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES farmers(user_id)
        )
    """)

    # Pest reports table — crowd-sourced outbreak map
    c.execute("""
        CREATE TABLE IF NOT EXISTS pest_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            lat         REAL,
            lon         REAL,
            location    TEXT,
            crop        TEXT,
            pest        TEXT,
            severity    TEXT,  -- low/medium/high
            photo_id    TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Mandi price cache
    c.execute("""
        CREATE TABLE IF NOT EXISTS mandi_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            crop        TEXT,
            market      TEXT,
            price       REAL,
            date        TEXT,
            cached_at   TEXT DEFAULT CURRENT_TIMESTAMP
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

    conn.commit()
    conn.close()
    print("✅ Database initialized.")


# === FARMER OPERATIONS ===

def upsert_farmer(user_id: int, name: str = "", username: str = ""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO farmers (user_id, name, username)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            name = COALESCE(NULLIF(excluded.name, ''), farmers.name),
            username = COALESCE(NULLIF(excluded.username, ''), farmers.username)
    """, (user_id, name, username))
    conn.commit()
    conn.close()


def get_farmer(user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM farmers WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["crops"] = json.loads(d.get("crops", "[]"))
        return d
    return {}


def update_farmer_location(user_id: int, lat: float, lon: float, location: str):
    conn = get_conn()
    conn.execute("""
        UPDATE farmers SET lat=?, lon=?, location=? WHERE user_id=?
    """, (lat, lon, location, user_id))
    conn.commit()
    conn.close()


def update_farmer_language(user_id: int, language: str):
    conn = get_conn()
    conn.execute("UPDATE farmers SET language=? WHERE user_id=?", (language, user_id))
    conn.commit()
    conn.close()


def toggle_alerts(user_id: int) -> bool:
    conn = get_conn()
    current = conn.execute("SELECT alerts FROM farmers WHERE user_id=?", (user_id,)).fetchone()
    new_val = 0 if (current and current["alerts"]) else 1
    conn.execute("UPDATE farmers SET alerts=? WHERE user_id=?", (new_val, user_id))
    conn.commit()
    conn.close()
    return bool(new_val)


def get_alert_users() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM farmers WHERE alerts=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === QUERY LOGGING ===

def log_query(user_id: int, query_type: str, message: str,
              response: str, intent: str = "other", language: str = "hi"):
    conn = get_conn()
    conn.execute("""
        INSERT INTO queries (user_id, query_type, message, response, intent, language)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, query_type, message[:500], response[:1000], intent, language))

    # Update daily stats
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute("""
        INSERT INTO daily_stats (date, total_queries) VALUES (?, 1)
        ON CONFLICT(date) DO UPDATE SET total_queries = total_queries + 1
    """, (today,))

    if query_type == "voice":
        conn.execute("UPDATE daily_stats SET voice_queries = voice_queries + 1 WHERE date=?", (today,))
    elif query_type == "photo":
        conn.execute("UPDATE daily_stats SET photo_queries = photo_queries + 1 WHERE date=?", (today,))
    elif query_type == "mandi":
        conn.execute("UPDATE daily_stats SET mandi_queries = mandi_queries + 1 WHERE date=?", (today,))

    conn.commit()
    conn.close()


# === PEST REPORTS ===

def add_pest_report(user_id: int, lat: float, lon: float, location: str,
                    crop: str, pest: str, severity: str = "medium", photo_id: str = ""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO pest_reports (user_id, lat, lon, location, crop, pest, severity, photo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, lat, lon, location, crop, pest, severity, photo_id))

    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute("""
        INSERT INTO daily_stats (date, pest_reports) VALUES (?, 1)
        ON CONFLICT(date) DO UPDATE SET pest_reports = pest_reports + 1
    """, (today,))

    conn.commit()
    conn.close()


def get_recent_pest_reports(limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.*, f.location as farmer_location
        FROM pest_reports p
        LEFT JOIN farmers f ON p.user_id = f.user_id
        ORDER BY p.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === ANALYTICS ===

def get_analytics() -> dict:
    conn = get_conn()

    total_farmers = conn.execute("SELECT COUNT(*) as c FROM farmers").fetchone()["c"]
    total_queries = conn.execute("SELECT COUNT(*) as c FROM queries").fetchone()["c"]
    total_pest_reports = conn.execute("SELECT COUNT(*) as c FROM pest_reports").fetchone()["c"]

    # Last 7 days stats
    weekly = conn.execute("""
        SELECT date, total_queries, unique_users, voice_queries, photo_queries,
               mandi_queries, pest_reports
        FROM daily_stats
        ORDER BY date DESC LIMIT 7
    """).fetchall()

    # Top intents
    intents = conn.execute("""
        SELECT intent, COUNT(*) as count FROM queries
        GROUP BY intent ORDER BY count DESC
    """).fetchall()

    # Top crops mentioned
    crops_raw = conn.execute("SELECT crops FROM farmers WHERE crops != '[]'").fetchall()
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
