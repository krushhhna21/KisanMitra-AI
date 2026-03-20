import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect('postgresql://neondb_owner:npg_tTQ2cyP5SluG@ep-morning-fog-a4uzpxwr-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require')
cur = conn.cursor(cursor_factory=RealDictCursor)
try:
    cur.execute("INSERT INTO land_details (user_id) VALUES (0) RETURNING id")
    print("Inserted into land_details, returning id:", cur.fetchone())
    cur.execute("SELECT LASTVAL()")
    res = cur.fetchone()
    print('res:', res)
    print('keys:', list(res.keys()))
except Exception as e:
    print('error:', e)
finally:
    conn.rollback()
