"""
KisanMitra AI — Azure App Service Entry Point
=============================================
Gunicorn-compatible launcher that:
  1. Initialises the PostgreSQL database
  2. Starts the Telegram bot in a background daemon thread
  3. Exposes the Flask dashboard as 'application' for Gunicorn

Startup command on Azure:
  gunicorn --bind=0.0.0.0:8000 --workers=1 --threads=4 --timeout=120 startup:application
"""

import os
import sys
import threading
import traceback

# ── Path setup ──────────────────────────────────────────────────────────────
pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kisanmitra_pro")
if os.path.isdir(pkg_dir) and pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

# Change CWD so .env + relative DB paths resolve correctly
os.chdir(pkg_dir)

# ── Imports (after path is set) ──────────────────────────────────────────────
from database.db import init_db
from dashboard.app import app as application   # Gunicorn targets 'application'


# ── Telegram bot (background thread) ────────────────────────────────────────
def start_bot():
    """Run the Telegram polling bot in a dedicated asyncio event loop."""
    import asyncio
    try:
        from main import main
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        loop.run_forever()          # Keep polling indefinitely
    except Exception as exc:
        print(f"❌ BOT THREAD CRASHED: {exc}", flush=True)
        traceback.print_exc()


# ── Startup sequence ─────────────────────────────────────────────────────────
print("🌱 KisanMitra AI — Azure startup initiated", flush=True)

init_db()
print("🗄️  Database initialised", flush=True)

_bot_thread = threading.Thread(target=start_bot, daemon=True, name="TelegramBot")
_bot_thread.start()
print("🤖 Telegram bot started in background thread", flush=True)
