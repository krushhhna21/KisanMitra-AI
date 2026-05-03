#!/usr/bin/env python3
"""
Import IoT sensor data from CSV file into database
Usage: python import_sensor_data.py [csv_file]
"""

import sys
import csv
from pathlib import Path
from database.db import init_db, get_conn, get_cursor, fmt_query, serialize_row
from config import IS_POSTGRES

def import_sensor_csv(csv_file: str) -> int:
    """
    Import sensor data from CSV file into sensor_data table
    
    Expected CSV columns:
    id, email, moisture, ph, temperature, created_at, ec, nitrogen, phosphorus, potassium
    """
    
    if not Path(csv_file).exists():
        print(f"❌ File not found: {csv_file}")
        return 0
    
    # Initialize database (creates tables if they don't exist)
    init_db()
    
    imported = 0
    errors = 0
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # start=2 because header is row 1
                try:
                    # Extract values
                    email = row.get('email', '').strip()
                    moisture = float(row.get('moisture', 0) or 0)
                    ph = float(row.get('ph', 0) or 0)
                    temperature = float(row.get('temperature', 0) or 0)
                    ec = float(row.get('ec', 0) or 0)
                    nitrogen = float(row.get('nitrogen', 0) or 0)
                    phosphorus = float(row.get('phosphorus', 0) or 0)
                    potassium = float(row.get('potassium', 0) or 0)
                    
                    # Insert into database
                    conn = get_conn()
                    cur = get_cursor(conn)
                    
                    cur.execute(fmt_query("""
                        INSERT INTO sensor_data (email, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """), (email, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium))
                    
                    conn.commit()
                    conn.close()
                    
                    print(f"✅ Row {row_num}: Imported sensor reading for {email}")
                    imported += 1
                    
                except ValueError as e:
                    print(f"❌ Row {row_num}: Invalid data - {e}")
                    errors += 1
                except Exception as e:
                    print(f"❌ Row {row_num}: {e}")
                    errors += 1
    
    except Exception as e:
        print(f"❌ Failed to read CSV: {e}")
        return 0
    
    print(f"\n📊 Import Summary:")
    print(f"  ✅ Imported: {imported} readings")
    print(f"  ❌ Errors: {errors} rows")
    
    # Show sample
    if imported > 0:
        print(f"\n📡 Latest sensor reading in database:")
        try:
            conn = get_conn()
            cur = get_cursor(conn)
            cur.execute(fmt_query("SELECT * FROM sensor_data ORDER BY created_at DESC LIMIT 1"))
            latest = cur.fetchone()
            conn.close()
            
            if latest:
                s = serialize_row(latest)
                print(f"  Email: {s.get('email')}")
                print(f"  Moisture: {s.get('moisture')}%")
                print(f"  pH: {s.get('ph')}")
                print(f"  Temperature: {s.get('temperature')}°C")
                print(f"  EC: {s.get('ec')}")
                print(f"  N/P/K: {s.get('nitrogen')} / {s.get('phosphorus')} / {s.get('potassium')}")
                print(f"  Recorded: {s.get('created_at')}")
        except Exception as e:
            print(f"  (Could not fetch sample: {e})")
    
    return imported


def show_sensor_stats():
    """Show statistics about sensor data in database"""
    conn = get_conn()
    cur = get_cursor(conn)
    
    try:
        # Total readings
        cur.execute("SELECT COUNT(*) as count FROM sensor_data")
        result = cur.fetchone()
        total = result['count'] if isinstance(result, dict) else result[0]
        
        # Unique farmers
        cur.execute("SELECT COUNT(DISTINCT email) as count FROM sensor_data WHERE email != ''")
        result = cur.fetchone()
        farmers = result['count'] if isinstance(result, dict) else result[0]
        
        # Most recent reading
        cur.execute(fmt_query("""
            SELECT email, moisture, ph, temperature, created_at 
            FROM sensor_data 
            ORDER BY created_at DESC LIMIT 1
        """))
        latest = cur.fetchone()
        
        print(f"\n📊 Sensor Data Statistics:")
        print(f"  Total readings: {total}")
        print(f"  Unique farmers: {farmers}")
        
        if latest:
            latest_dict = serialize_row(latest)
            print(f"\n📡 Most recent reading:")
            print(f"  Farmer: {latest_dict['email']}")
            print(f"  Moisture: {latest_dict['moisture']}% | pH: {latest_dict['ph']} | Temp: {latest_dict['temperature']}°C")
            print(f"  Time: {latest_dict['created_at']}")
    
    except Exception as e:
        print(f"❌ Error querying statistics: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default to the sensor_data CSV file
        csv_file = "sensor_data (1).csv"
    else:
        csv_file = sys.argv[1]
    
    print(f"🚀 Importing sensor data from: {csv_file}")
    print("=" * 50)
    
    count = import_sensor_csv(csv_file)
    
    if count > 0:
        show_sensor_stats()
        print("\n✅ Import complete!")
    else:
        print("\n❌ No data imported.")
