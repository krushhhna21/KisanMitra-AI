import sys
import os

# Add kisanmitra_pro to path
sys.path.insert(0, os.path.abspath('kisanmitra_pro'))

from database.db import upsert_farmer

try:
    print("Calling upsert_farmer...")
    upsert_farmer(12345, "Test", "test_user")
    print("Success!")
except Exception as e:
    print(repr(e))
