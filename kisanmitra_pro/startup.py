"""
Startup script for Azure App Service (WSGI Entry Point)
=======================================================
Runs ONLY the Flask Dashboard application for Azure deployment.
The Telegram bot (main.py) must run separately via a WebJob or worker role
to prevent Gunicorn timeouts and Port 8000 starvation on Azure!

Startup command on Azure:
  gunicorn --bind=0.0.0.0:8000 --workers=1 --threads=4 --timeout=120 startup:application
"""

import sys
import os
import traceback
from flask import Flask

# Add project root to path (since we are already in kisanmitra_pro)
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ── Import dashboard app safely so Gunicorn always gets a valid app ─────────
application = None

try:
    from dashboard.app import app as application
    print("[startup] [OK] KisanMitra AI Flask Dashboard imported successfully!", flush=True)
except Exception as e:
    import_error = str(e)
    print(f"[startup] [ERROR] Dashboard import failed: {e}", flush=True)
    traceback.print_exc()

    # Keep container alive with a minimal fallback app.
    application = Flask(__name__)

    @application.route("/")
    def fallback_index():
        return f"KisanMitra dashboard fallback | import_error: {import_error}", 200

# Initialize DB schemas safely (with fallback handled in database layer).
try:
    from database.db import init_db
    init_db()
    print("[startup] [OK] DB init complete", flush=True)
except Exception as e:
    # Non-fatal: app can still serve login/static routes while DB recovers.
    print(f"[startup] [WARN] DB init skipped: {e}", flush=True)

# Add a simple health check endpoint
@application.route('/api/health')
def health():
    return {'status': 'ok', 'message': 'KisanMitra Dashboard is running!'}, 200

if __name__ == "__main__":
    # Local development only (not used on Azure)
    port = int(os.environ.get("PORT", 8080))
    print(f"[startup] [OK] Starting Flask app on localhost:{port}")
    application.run(host="0.0.0.0", port=port, debug=False)
