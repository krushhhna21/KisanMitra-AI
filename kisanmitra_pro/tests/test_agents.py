"""
KisanMitra AI — Tests
Run from kisanmitra_pro/:  python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from config import DB_PATH
from services.weather import get_weather
from services.mandi import get_mandi_prices, CROP_MAP
from services.schemes import get_crop_calendar
from services.satellite import get_crop_health
from database.db import init_db, upsert_farmer, get_farmer, log_query, get_analytics


# === SETUP ===
@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use a temporary DB for tests"""
    test_db = str(tmp_path / "test_kisanmitra.db")
    import config
    monkeypatch.setattr(config, "DB_PATH", test_db)
    init_db()


# === DATABASE TESTS ===
def test_farmer_upsert_and_get():
    upsert_farmer(99999, "Test Farmer", "testuser")
    farmer = get_farmer(99999)
    assert farmer["user_id"] == 99999
    assert farmer["name"] == "Test Farmer"

def test_farmer_default_location():
    upsert_farmer(99998, "Location Test", "loctest")
    farmer = get_farmer(99998)
    assert farmer["lat"] == 18.4088
    assert farmer["lon"] == 76.5604

def test_query_logging():
    upsert_farmer(99997, "Log Test", "logtest")
    log_query(99997, "text", "test message", "test reply", "crop", "hi")
    analytics = get_analytics()
    assert analytics["total_queries"] >= 1

def test_analytics_structure():
    analytics = get_analytics()
    assert "total_farmers" in analytics
    assert "total_queries" in analytics
    assert "total_pest_reports" in analytics
    assert "weekly_stats" in analytics
    assert "top_intents" in analytics


# === WEATHER TESTS ===
def test_weather_returns_dict():
    w = get_weather()
    assert isinstance(w, dict)
    assert "summary" in w
    assert "temp" in w

def test_weather_custom_location():
    w = get_weather(19.0760, 72.8777, "Mumbai")
    assert "Mumbai" in w["summary"]

def test_weather_has_required_fields():
    w = get_weather()
    for field in ["summary", "temp", "humidity", "rain_today", "rain_tomorrow", "alert"]:
        assert field in w


# === MANDI TESTS ===
def test_crop_map_has_common_crops():
    assert "pyaaz" in CROP_MAP
    assert "gehu" in CROP_MAP
    assert "tamatar" in CROP_MAP

def test_mandi_returns_string():
    result = get_mandi_prices("pyaaz ka bhav kya hai")
    assert isinstance(result, str)
    assert len(result) > 10

def test_mandi_detects_crop():
    result = get_mandi_prices("aaj gehu ka rate kya hai")
    assert isinstance(result, str)


# === CALENDAR TESTS ===
def test_crop_calendar_returns_string():
    cal = get_crop_calendar()
    assert isinstance(cal, str)
    assert len(cal) > 50

def test_crop_calendar_has_tasks():
    cal = get_crop_calendar()
    assert "✅" in cal


# === SATELLITE TESTS ===
def test_satellite_returns_string():
    result = get_crop_health(18.4088, 76.5604, "Latur")
    assert isinstance(result, str)
    assert len(result) > 50

def test_satellite_handles_invalid_coords():
    result = get_crop_health(0.0, 0.0, "Test Location")
    assert isinstance(result, str)


if __name__ == "__main__":
    print("Running KisanMitra AI tests...")
    pytest.main([__file__, "-v"])
