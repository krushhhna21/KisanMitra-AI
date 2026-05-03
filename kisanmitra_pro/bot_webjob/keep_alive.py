"""
Keep-alive server for Render free tier.
Prevents the service from sleeping by running a tiny web server.
Add this to main.py imports and call keep_alive() before app.run_polling()
"""
from flask import Flask
from threading import Thread

keep_alive_app = Flask(__name__)

@keep_alive_app.route("/")
def home():
    return "🌾 KisanMitra AI is running!"

@keep_alive_app.route("/health")
def health():
    return {"status": "ok", "bot": "KisanMitra AI", "version": "2.0"}

def run_server():
    keep_alive_app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()
    print("✅ Keep-alive server running on port 8080")
