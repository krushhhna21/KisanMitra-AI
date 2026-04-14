"""
Startup script for Azure App Service (WSGI Entry Point)
Runs the Flask Dashboard application for Azure deployment.
The Telegram bot (main.py) runs separately (locally or via worker role).
"""
import sys
import os
import traceback

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print(f"[startup] Python path: {sys.path[0]}")
print(f"[startup] Current directory: {os.getcwd()}")
print(f"[startup] Project root: {project_root}")

# Try to load the Flask app
try:
    print("[startup] Importing dashboard.app...")
    from dashboard.app import app as application
    print("[startup] ✅ Flask app loaded successfully!")
    
except Exception as e:
    print(f"[startup] ❌ ERROR loading Flask app: {e}")
    print(f"[startup] Error details:")
    traceback.print_exc()
    
    # Fallback minimal WSGI app that returns error details
    def application(environ, start_response):
        status = '500 Internal Server Error'
        response_headers = [('Content-type', 'text/html; charset=utf-8')]
        start_response(status, response_headers)
        error_msg = f"""
        <html><body>
        <h1>500 - Server Error</h1>
        <p>Failed to load KisanMitra Flask app</p>
        <pre>{str(e)}</pre>
        <p>Check Azure logs for details.</p>
        </body></html>
        """.encode('utf-8')
        return [error_msg]

print("[startup] Startup complete. WSGI app ready.")

if __name__ == "__main__":
    # Local development only (not used on Azure)
    port = int(os.environ.get("PORT", 8080))
    print(f"[startup] Starting Flask app on localhost:{port}")
    application.run(host="0.0.0.0", port=port, debug=False)
