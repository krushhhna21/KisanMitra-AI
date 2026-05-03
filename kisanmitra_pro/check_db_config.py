#!/usr/bin/env python3
"""Check database configuration"""
import os
import sys

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgres")

print("=" * 60)
print("📊 DATABASE CONFIGURATION CHECK")
print("=" * 60)

if DATABASE_URL:
    print("\n✅ DATABASE_URL is SET")
    
    if IS_POSTGRES:
        print(f"✅ Type: PostgreSQL (Neon or similar)")
        # Mask password
        masked_url = DATABASE_URL.replace("postgresql://", "postgresql://[USER]:[PASS]@")
        if "@" in masked_url:
            parts = masked_url.split("@")
            masked_url = parts[0] + "@" + parts[1][:40] + "..."
        print(f"   URL: {masked_url}")
        print("\n📡 Using Remote PostgreSQL Database (Neon)")
        print("   - All systems share same database")
        print("   - Data synced across dashboard + bot")
    else:
        print(f"❌ Type: Not recognized as PostgreSQL")
        print(f"   URL: {DATABASE_URL[:50]}...")
else:
    print("\n❌ DATABASE_URL NOT SET")
    print("⚠️  Type: SQLite (local file: kisanmitra.db)")
    print("   - Dashboard uses local database")
    print("   - WebJob may use different database")
    print("\n🔧 TO FIX: Set DATABASE_URL environment variable in Azure App Service")
    print("   Example: postgresql://[user]:[password]@[neon-host]/[dbname]")

print("\n" + "=" * 60)

# Check both dashboard and bot can import db
try:
    from database.db import get_conn, get_latest_sensor_data
    print("✅ Database module imports successfully")
    
    # Try to connect
    try:
        conn = get_conn()
        print("✅ Database connection successful")
        
        # Check sensor data table
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sensor_data" if IS_POSTGRES else "SELECT COUNT(*) as count FROM sensor_data")
        result = cur.fetchone()
        count = result[0] if isinstance(result, tuple) else result['count']
        print(f"✅ Sensor data table: {count} readings found")
        conn.close()
    except Exception as e:
        print(f"⚠️  Database connection error: {e}")
except ImportError as e:
    print(f"❌ Failed to import database module: {e}")

print("=" * 60)

sys.exit(0 if DATABASE_URL and IS_POSTGRES else 1)
