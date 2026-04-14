"""
Startup script for Azure App Service
Runs both Telegram Bot (background) and Flask Dashboard (WSGI)
"""
import asyncio
import threading
import sys
import os
from dashboard.app import app

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

def run_telegram_bot():
    """Run Telegram bot in background thread"""
    try:
        # Import and run the bot
        from main import app as bot_app
        asyncio.run(bot_app.run_polling())
    except Exception as e:
        print(f"[startup] Telegram bot error: {e}")

# Start Telegram bot in background thread (optional - may not work on App Service)
# bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
# bot_thread.start()

# Flask application for Azure App Service
# The WSGI server will use this variable
application = app

if __name__ == "__main__":
    # Local testing
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
