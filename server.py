"""
KisanMitra AI — Combined Server for Render / Cloud Deployment
Runs both: Flask Dashboard (web) + Telegram Bot (background thread)

Usage:
  Local:  cd kisanmitra_pro && python ../server.py
  Render: startCommand = cd kisanmitra_pro && python ../server.py
"""
import os
import sys
import threading

# Ensure kisanmitra_pro modules are importable
pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kisanmitra_pro")
if os.path.isdir(pkg_dir) and pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from database.db import init_db
from dashboard.app import app as flask_app


def start_bot():
    """Run Telegram bot in a separate thread with its own event loop"""
    import asyncio
    import traceback
    try:
        from main import main
        asyncio.run(main())
    except Exception as e:
        print(f"❌ BOT THREAD CRASHED: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # Change working directory to kisanmitra_pro so .env is found
    os.chdir(pkg_dir)

    init_db()

    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    print("🤖 Telegram bot started in background thread")

    # Start Flask dashboard on Render's PORT (or 8080 locally)
    port = int(os.environ.get("PORT", 8080))
    print(f"📊 Dashboard starting on port {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False)
