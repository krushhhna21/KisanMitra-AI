"""
KisanMitra AI — Dashboard v3.0
Google OAuth login + Land Details + Soil Report + Analytics
Run: python server.py (from project root, where bot + dashboard run combined)
Or standalone: cd kisanmitra_pro && python dashboard/app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functools import wraps
from flask import (
    Flask, redirect, url_for, session, request,
    render_template_string, jsonify, flash
)
from authlib.integrations.flask_client import OAuth
from groq import Groq

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, FLASK_SECRET_KEY,
    GROQ_API_KEY, GROQ_CHAT_MODEL
)
from database.db import (
    init_db, get_analytics, get_recent_pest_reports,
    upsert_dashboard_user, get_land_details, save_land_details,
    get_soil_reports, save_soil_report
)

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Tell Flask it is behind a reverse proxy (Render) so url_for generates HTTPS links
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ── Google OAuth ──────────────────────────────────────────────────────────────
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

groq_client = Groq(api_key=GROQ_API_KEY)

# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user():
    return session.get("user", {})

# ── Groq soil AI ──────────────────────────────────────────────────────────────
def generate_soil_recommendation(ph, n, p, k, om, moisture, ec, crop_type=""):
    crop_ctx = f" for growing {crop_type}" if crop_type else ""
    prompt = f"""You are an expert soil scientist and agronomist advising an Indian farmer{crop_ctx}.

Soil test results:
- pH: {ph}
- Nitrogen (N): {n} kg/ha
- Phosphorus (P): {p} kg/ha
- Potassium (K): {k} kg/ha
- Organic Matter: {om}%
- Moisture: {moisture}%
- Electrical Conductivity (EC): {ec} dS/m

Give a detailed soil health report with:
1. Overall soil health rating (Poor / Fair / Good / Excellent)
2. Key deficiencies and what they mean for the crop
3. Specific fertiliser recommendations (amounts and timing)
4. Organic amendments recommended (FYM, compost, vermicompost, etc.)
5. Irrigation advice based on moisture
6. One action the farmer should do FIRST this week

Format: concise bullet points. Use simple language that can be understood by a village farmer.
Max 300 words. Include emoji for each section."""

    try:
        res = groq_client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.5
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI recommendation unavailable: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

BASE_CSS = """
<link rel="icon" type="image/jpeg" href="/static/favicon.jpg">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');
  *{margin:0;padding:0;box-sizing:border-box;}
  :root{
    --bg:#0f172a; --surface:#1e293b; --card:rgba(30,41,59,0.7);
    --border:rgba(255,255,255,0.08); --accent:#16a34a; --accent2:#15803d;
    --text:#f8fafc; --muted:#94a3b8; --danger:#ef4444;
    --warn:#f59e0b; --info:#3b82f6;
  }
  body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;}
  h1,h2,h3,h4{font-family:'Outfit',sans-serif;}
  /* Sidebar / Bottom Nav */
  .sidebar{width:240px;height:100vh;background:rgba(15,23,42,0.8);backdrop-filter:blur(20px);border-right:1px solid var(--border);
    display:flex;flex-direction:column;padding:0;flex-shrink:0;position:sticky;top:0;z-index:100;}
  .sidebar-logo{padding:24px 20px;border-bottom:1px solid var(--border);}
  .sidebar-logo h2{font-size:20px;font-weight:700;color:var(--text);display:flex;align-items:center;gap:8px;}
  .sidebar-logo p{font-size:12px;color:var(--accent);margin-top:4px;font-weight:500;}
  .sidebar-nav{flex:1;padding:16px 0;display:flex;flex-direction:column;}
  .nav-link{display:flex;align-items:center;gap:12px;padding:14px 24px;color:var(--muted);
    text-decoration:none;font-size:15px;transition:.2s;border-left:3px solid transparent;}
  .nav-link:hover,.nav-link.active{color:var(--text);background:rgba(34,197,94,.1);border-left-color:var(--accent);}
  .nav-link span{font-size:18px;}
  .sidebar-user{padding:16px 20px;border-top:1px solid var(--border);display:flex;align-items:center;gap:12px;background:rgba(255,255,255,0.02);}
  .sidebar-user img{width:38px;height:38px;border-radius:50%;border:2px solid var(--accent);object-fit:cover;}
  .sidebar-user .uname{font-size:14px;font-weight:600;color:var(--text);}
  .sidebar-user .uemail{font-size:12px;color:var(--muted);}
  /* Main */
  .main{flex:1;overflow-y:auto;display:flex;flex-direction:column;min-height:100vh;}
  .topbar{padding:24px 32px;border-bottom:1px solid var(--border);background:rgba(30,41,59,0.5);backdrop-filter:blur(12px);
    display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:90;}
  .topbar h1{font-size:24px;font-weight:600;letter-spacing:-0.5px;}
  .topbar .subtitle{color:var(--muted);font-size:14px;margin-top:4px;}
  .content{padding:32px;flex:1;}
  /* Cards */
  .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:28px;}
  .grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:24px;margin-bottom:28px;}
  .card, .section{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:20px;padding:24px;box-shadow:0 10px 30px rgba(0,0,0,0.2);}
  .section{margin-bottom:28px;}
  .card-title{font-size:14px;color:var(--muted);font-weight:500;margin-bottom:12px;display:flex;align-items:center;gap:8px;}
  .card-num{font-size:42px;font-weight:700;color:var(--text);font-family:'Outfit',sans-serif;}
  .section h2{font-size:18px;font-weight:600;color:var(--text);margin-bottom:20px;display:flex;align-items:center;gap:8px;}
  /* Table */
  table{width:100%;border-collapse:separate;border-spacing:0;}
  th{font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);padding:12px 16px;text-align:left;border-bottom:1px solid var(--border);background:rgba(255,255,255,0.02);}
  td{font-size:14px;padding:16px;border-bottom:1px solid rgba(255,255,255,.03);}
  tr:last-child td{border-bottom:none;}
  /* Badges */
  .badge{display:inline-flex;align-items:center;padding:4px 12px;border-radius:30px;font-size:12px;font-weight:600;letter-spacing:0.2px;}
  .badge-green{background:rgba(34,197,94,.15);color:#4ade80;border:1px solid rgba(34,197,94,.2);}
  .badge-red{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.2);}
  .badge-yellow{background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
  .badge-blue{background:rgba(59,130,246,.15);color:#60a5fa;border:1px solid rgba(59,130,246,.2);}
  /* Forms */
  .form-group{margin-bottom:20px;}
  .form-group label{display:block;font-size:13px;font-weight:500;margin-bottom:8px;color:var(--muted);}
  .form-group input,.form-group select,.form-group textarea{
    width:100%;padding:12px 16px;background:rgba(15,23,42,0.5);border:1px solid var(--border);
    border-radius:12px;color:var(--text);font-size:15px;outline:none;transition:.3s;font-family:inherit;}
  .form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--accent);background:rgba(15,23,42,0.8);box-shadow:0 0 0 3px rgba(34,197,94,.15);}
  .form-group select option{background:var(--surface);color:#fff;}
  .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:12px 24px;border-radius:12px;
    font-size:15px;font-weight:600;cursor:pointer;border:none;transition:.3s;text-decoration:none;}
  .btn-primary{background:var(--accent);color:#fff;}
  .btn-primary:hover{background:var(--accent2);transform:translateY(-1px);box-shadow:0 8px 15px rgba(22,163,74,.3);}
  .btn-secondary{background:rgba(255,255,255,.05);color:var(--text);border:1px solid var(--border);}
  .btn-secondary:hover{background:rgba(255,255,255,.1);}
  /* Map & Results */
  #map{height:250px;border-radius:12px;border:1px solid var(--border);margin-top:12px;z-index:1;}
  .result-box{background:rgba(34,197,94,.05);border:1px solid rgba(34,197,94,.2);
    border-radius:16px;padding:24px;margin-top:20px;white-space:pre-wrap;line-height:1.7;font-size:15px;}
  /* Alert flash */
  .flash{padding:16px 20px;border-radius:12px;margin-bottom:24px;font-size:14px;display:flex;align-items:center;gap:12px;font-weight:500;}
  .flash-success{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.2);color:#4ade80;}
  .flash-error{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.2);color:#f87171;}
  /* Responsive Mobile UI */
  @media(max-width:768px){
    .grid3,.grid2{grid-template-columns:1fr;}
    .sidebar{
      width:100%; height:80px; min-height:80px; border-right:none; border-top:1px solid var(--border);
      position:fixed; bottom:0; left:0; z-index:999; flex-direction:row; justify-content:space-around;
      padding:0; align-items:center; background:rgba(15,23,42,0.85); backdrop-filter:blur(20px);
    }
    .sidebar-logo, .sidebar-user { display:none; }
    .sidebar-nav { flex-direction:row; width:100%; justify-content:space-around; align-items:center; padding:0;}
    .nav-link { flex-direction:column; gap:6px; padding:12px 0; border-left:none; border-bottom:3px solid transparent; border-top:3px solid transparent; justify-content:center; align-items:center; flex:1; font-size:12px; font-weight:500;}
    .nav-link span { font-size:22px; }
    .nav-link:hover, .nav-link.active { background:transparent; border-left:none; border-bottom-color:transparent; border-top-color:var(--accent); color:var(--accent);}
    .main { padding-bottom:100px; width:100%; min-height:100vh;}
    .topbar { padding:20px; }
    .content { padding:20px; }
    .section, .card { padding:20px; border-radius:16px; }
  }
</style>
"""

import os
LOGIN_HTML = open(os.path.join(os.path.dirname(__file__), 'login_template.html'), 'r', encoding='utf-8').read()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra — Dashboard</title>""" + BASE_CSS + """
  <style>
    /* Dashboard-specific premium styles */
    .welcome-banner {
      background: linear-gradient(135deg, rgba(22,163,74,0.2) 0%, rgba(15,23,42,0.5) 100%);
      border: 1px solid rgba(22,163,74,0.3); border-radius: 24px;
      padding: 32px 36px; margin-bottom: 28px;
      display: flex; align-items: center; justify-content: space-between;
      position: relative; overflow: hidden;
    }
    .welcome-banner::before {
      content: '';
      position: absolute; top: 0; left: 0; right: 0; bottom: 0;
      background: radial-gradient(circle at 80% 50%, rgba(22,163,74,0.15) 0%, transparent 60%);
    }
    .welcome-banner h2 { font-size: 26px; font-weight: 700; margin-bottom: 8px; font-family: 'Outfit', sans-serif; }
    .welcome-banner p { color: var(--muted); font-size: 15px; }
    .welcome-icon { font-size: 80px; position: relative; z-index: 1; line-height: 1; }
    .stat-card {
      border-radius: 20px; padding: 28px; 
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
      min-height: 160px; border: 1px solid rgba(255,255,255,0.05);
    }
    .stat-card::before {
      content: '';
      position: absolute; top: -50%; right: -20%;
      width: 180px; height: 180px; border-radius: 50%;
      opacity: 0.15;
    }
    .stat-card-1 { background: linear-gradient(135deg, #065f46 0%, #0f172a 100%); }
    .stat-card-1::before { background: #10b981; }
    .stat-card-2 { background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%); }
    .stat-card-2::before { background: #3b82f6; }
    .stat-card-3 { background: linear-gradient(135deg, #78350f 0%, #0f172a 100%); }
    .stat-card-3::before { background: #f59e0b; }
    .stat-label { font-size: 13px; color: rgba(255,255,255,0.7); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
    .stat-value { font-size: 52px; font-weight: 700; color: #fff; font-family: 'Outfit', sans-serif; line-height: 1; }
    .stat-sub { margin-top: 10px; font-size: 12px; color: rgba(255,255,255,0.5); }
    .activity-row td:first-child { font-weight: 600; color: var(--muted); font-size: 13px; }
    .progress-bar { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); margin-top: 4px; overflow: hidden; }
    .progress-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #16a34a, #4ade80); transition: width 1s ease; }
    .quick-links { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 28px; }
    .quick-link-card { background: rgba(30,41,59,0.8); border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 22px; text-decoration: none; color: var(--text); display: flex; align-items: center; gap: 16px; transition: 0.3s; }
    .quick-link-card:hover { background: rgba(30,41,59,0.95); border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0,0,0,0.3);}
    .quick-link-icon { width: 48px; height: 48px; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; }
    .ql-green { background: rgba(22,163,74,0.15); }
    .ql-blue { background: rgba(59,130,246,0.15); }
    .quick-link-text h3 { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
    .quick-link-text p { font-size: 13px; color: var(--muted); }
    @media(max-width:768px){.welcome-banner{padding:20px;flex-direction:column;gap:12px;text-align:center;}.welcome-icon{font-size:50px;}.quick-links{grid-template-columns:1fr;}}
  </style>
</head>
<body>
  {{ sidebar|safe }}
  <div class="main">
    <div class="topbar">
      <div>
        <h1>Dashboard</h1>
        <div class="subtitle">Welcome back, {{ farmer_name }} · {{ today_date }}</div>
      </div>
      <a href="/land" class="btn btn-primary" style="text-decoration:none;">+ Add Field</a>
    </div>
    <div class="content">

      <!-- Welcome Banner -->
      <div class="welcome-banner">
        <div style="position:relative;z-index:1;">
          <h2>Good to see you, {{ farmer_name }}! 👋</h2>
          <p>Your AI farming companion is ready. Here's what's happening across your fields today.</p>
        </div>
        <div class="welcome-icon">🌾</div>
      </div>

      <!-- Stat Cards -->
      <div class="grid3">
        <div class="stat-card stat-card-1">
          <div class="stat-label">🌱 Farmers Helped</div>
          <div class="stat-value">{{ stats.total_farmers }}</div>
          <div class="stat-sub">Active users on platform</div>
        </div>
        <div class="stat-card stat-card-2">
          <div class="stat-label">💬 AI Queries</div>
          <div class="stat-value">{{ stats.total_queries }}</div>
          <div class="stat-sub">Questions answered by AI</div>
        </div>
        <div class="stat-card stat-card-3">
          <div class="stat-label">🐛 Pest Reports</div>
          <div class="stat-value">{{ stats.total_pest_reports }}</div>
          <div class="stat-sub">Crop diseases detected</div>
        </div>
      </div>

      <!-- Quick Action Links -->
      <div class="quick-links">
        <a href="/land" class="quick-link-card">
          <div class="quick-link-icon ql-green">🌍</div>
          <div class="quick-link-text">
            <h3>My Land</h3>
            <p>Register &amp; manage your field parcels</p>
          </div>
        </a>
        <a href="/soil" class="quick-link-card">
          <div class="quick-link-icon ql-blue">🧪</div>
          <div class="quick-link-text">
            <h3>Soil Reports</h3>
            <p>Upload soil tests &amp; get AI fertilizer advice</p>
          </div>
        </a>
      </div>

      <!-- Weekly Activity -->
      <div class="section">
        <h2>📅 Last 7 Days Activity</h2>
        <div style="overflow-x:auto;">
          <table>
            <thead><tr><th>Date</th><th>Total</th><th>Voice</th><th>Photos</th><th>Mandi</th><th>Pest Reports</th></tr></thead>
            <tbody>
              {% for d in stats.weekly_stats %}
              <tr class="activity-row">
                <td>{{ d.date }}</td>
                <td><span class="badge badge-green">{{ d.total_queries }}</span></td>
                <td>{{ d.voice_queries }}</td>
                <td>{{ d.photo_queries }}</td>
                <td>{{ d.mandi_queries }}</td>
                <td>{{ d.pest_reports }}</td>
              </tr>
              {% endfor %}
              {% if not stats.weekly_stats %}
              <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:32px;">No activity yet — start chatting with the Telegram bot!</td></tr>
              {% endif %}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Bottom Grid -->
      <div class="grid2">
        <div class="section">
          <h2>🔍 Top Query Intents</h2>
          {% if stats.top_intents %}
          <table>
            <thead><tr><th>Intent</th><th>Count</th></tr></thead>
            <tbody>
              {% for i in stats.top_intents %}
              <tr><td style="font-weight:500;">{{ i.intent }}</td><td><span class="badge badge-blue">{{ i.count }}</span></td></tr>
              {% endfor %}
            </tbody>
          </table>
          {% else %}
          <div style="text-align:center;color:var(--muted);padding:40px 0;">
            <div style="font-size:40px;margin-bottom:12px;">🤖</div>
            <p>No queries logged yet.</p>
          </div>
          {% endif %}
        </div>
        <div class="section">
          <h2>🐛 Recent Pest Reports</h2>
          {% if pest_reports %}
          <table>
            <thead><tr><th>Location</th><th>Crop</th><th>Pest</th><th>Severity</th></tr></thead>
            <tbody>
              {% for r in pest_reports %}
              <tr>
                <td>{{ r.location }}</td><td>{{ r.crop }}</td><td>{{ r.pest }}</td>
                <td>
                  {% if r.severity=='high' %}<span class="badge badge-red">High</span>
                  {% elif r.severity=='medium' %}<span class="badge badge-yellow">Medium</span>
                  {% else %}<span class="badge badge-green">Low</span>{% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
          {% else %}
          <div style="text-align:center;color:var(--muted);padding:40px 0;">
            <div style="font-size:40px;margin-bottom:12px;">✅</div>
            <p>No pest reports yet — fields are clean!</p>
          </div>
          {% endif %}
        </div>
      </div>

    </div>
  </div>
</body>
</html>"""

LAND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra — My Land</title>""" + BASE_CSS + """
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
  {{ sidebar|safe }}
  <div class="main">
    <div class="topbar">
      <div><h1>🌍 My Land Details</h1>
        <div class="subtitle">Register your field — powers personalised AI advice</div>
      </div>
    </div>
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat,msg in messages %}
          <div class="flash flash-{{ cat }}">{{ msg }}</div>
        {% endfor %}
      {% endwith %}
      <div class="grid2">
        <div class="section">
          <h2>➕ Add Field</h2>
          <form method="POST" action="/api/land" id="landForm">
            <div class="form-group">
              <label>Village / Gaon</label>
              <input name="village" placeholder="e.g. Nandur" required>
            </div>
            <div class="form-group">
              <label>District</label>
              <input name="district" placeholder="e.g. Latur" required>
            </div>
            <div class="form-group">
              <label>State</label>
              <select name="state">
                <option>Maharashtra</option><option>Karnataka</option>
                <option>Madhya Pradesh</option><option>Rajasthan</option>
                <option>Uttar Pradesh</option><option>Punjab</option>
                <option>Haryana</option><option>Gujarat</option><option>Other</option>
              </select>
            </div>
            <div class="form-group">
              <label>Area (Acres)</label>
              <input name="area_acres" type="number" step="0.1" min="0.1" placeholder="e.g. 3.5" required>
            </div>
            <div class="form-group">
              <label>Primary Crop</label>
              <select name="crop_type">
                <option>Wheat (Gehu)</option><option>Rice (Dhan)</option>
                <option>Soybean</option><option>Cotton (Kapas)</option>
                <option>Sugarcane (Ganna)</option><option>Onion (Pyaaz)</option>
                <option>Tomato (Tamatar)</option><option>Chickpea (Chana)</option>
                <option>Jowar</option><option>Bajra</option><option>Maize (Makka)</option>
                <option>Other</option>
              </select>
            </div>
            <div class="form-group">
              <label>Soil Type</label>
              <select name="soil_type">
                <option>Black (Kali Mitti)</option><option>Red (Lal Mitti)</option>
                <option>Alluvial (Domat)</option><option>Sandy (Retili)</option>
                <option>Loamy</option><option>Clay</option><option>Laterite</option>
              </select>
            </div>
            <div class="form-group">
              <label>Location</label>
              <button type="button" class="btn btn-secondary" onclick="getLocation()" id="locBtn">
                📍 Share My Location
              </button>
              <div id="map" style="display:none;margin-top:8px;"></div>
              <input type="hidden" name="lat" id="lat" value="0">
              <input type="hidden" name="lon" id="lon" value="0">
              <div id="locStatus" style="font-size:12px;color:var(--muted);margin-top:6px;"></div>
            </div>
            <button type="submit" class="btn btn-primary">💾 Save Field</button>
          </form>
        </div>
        <div class="section">
          <h2>📋 Registered Fields</h2>
          {% if lands %}
            {% for land in lands %}
            <div style="background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;
              padding:14px;margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;align-items:start;">
                <div>
                  <div style="font-weight:600;font-size:14px;">{{ land.village }}, {{ land.district }}</div>
                  <div style="color:var(--muted);font-size:12px;margin-top:3px;">{{ land.state }}</div>
                </div>
                <span class="badge badge-green">{{ land.area_acres }} acres</span>
              </div>
              <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
                <span class="badge badge-blue">🌾 {{ land.crop_type }}</span>
                <span class="badge badge-yellow">🪨 {{ land.soil_type }}</span>
                {% if land.lat %}<span class="badge" style="background:rgba(139,92,246,.15);color:#a78bfa;">
                  📍 {{ "%.4f"|format(land.lat) }}, {{ "%.4f"|format(land.lon) }}</span>{% endif %}
              </div>
              <div style="font-size:11px;color:var(--muted);margin-top:8px;">Added: {{ land.created_at[:10] }}</div>
            </div>
            {% endfor %}
          {% else %}
            <div style="color:var(--muted);font-size:13px;text-align:center;padding:40px 0;">
              No fields registered yet.<br>Add your first field →
            </div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  <script>
    var map, marker;
    function getLocation() {
      if (!navigator.geolocation) {
        document.getElementById('locStatus').textContent = '⚠️ Geolocation not supported.'; return;
      }
      document.getElementById('locBtn').textContent = '⏳ Getting location...';
      navigator.geolocation.getCurrentPosition(function(pos) {
        var lat = pos.coords.latitude, lon = pos.coords.longitude;
        document.getElementById('lat').value = lat;
        document.getElementById('lon').value = lon;
        document.getElementById('locStatus').textContent = '✅ Location captured: ' + lat.toFixed(5) + ', ' + lon.toFixed(5);
        document.getElementById('locBtn').textContent = '✅ Location Set';
        var mapDiv = document.getElementById('map');
        mapDiv.style.display = 'block';
        if (!map) {
          map = L.map('map').setView([lat, lon], 14);
          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OSM'}).addTo(map);
          marker = L.marker([lat, lon], {draggable:true}).addTo(map);
          marker.on('dragend', function(e) {
            var p = e.target.getLatLng();
            document.getElementById('lat').value = p.lat;
            document.getElementById('lon').value = p.lng;
          });
        } else { map.setView([lat,lon],14); marker.setLatLng([lat,lon]); }
      }, function(err) {
        document.getElementById('locStatus').textContent = '⚠️ Could not get location: ' + err.message;
        document.getElementById('locBtn').textContent = '📍 Share My Location';
      });
    }
  </script>
</body>
</html>"""

SOIL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra — Soil Report</title>""" + BASE_CSS + """
</head>
<body>
  {{ sidebar|safe }}
  <div class="main">
    <div class="topbar">
      <div><h1>🧪 Soil Report Analysis</h1>
        <div class="subtitle">Enter soil test data — get AI-powered crop recommendations</div>
      </div>
    </div>
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat,msg in messages %}
          <div class="flash flash-{{ cat }}">{{ msg }}</div>
        {% endfor %}
      {% endwith %}
      <div class="grid2">
        <div class="section">
          <h2>📋 Enter Soil Test Values</h2>
          <form method="POST" action="/api/soil">
            <div class="form-group">
              <label>Select Field (optional)</label>
              <select name="land_id">
                <option value="0">— No specific field —</option>
                {% for land in lands %}
                <option value="{{ land.id }}">{{ land.village }}, {{ land.district }} ({{ land.crop_type }})</option>
                {% endfor %}
              </select>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
              <div class="form-group">
                <label>pH <span style="color:var(--muted);font-size:11px;">(4.0 – 9.0)</span></label>
                <input name="ph" type="number" step="0.1" min="3" max="10" placeholder="e.g. 6.5" required>
              </div>
              <div class="form-group">
                <label>Nitrogen (kg/ha)</label>
                <input name="nitrogen" type="number" step="1" min="0" placeholder="e.g. 240" required>
              </div>
              <div class="form-group">
                <label>Phosphorus (kg/ha)</label>
                <input name="phosphorus" type="number" step="0.1" min="0" placeholder="e.g. 15" required>
              </div>
              <div class="form-group">
                <label>Potassium (kg/ha)</label>
                <input name="potassium" type="number" step="1" min="0" placeholder="e.g. 180" required>
              </div>
              <div class="form-group">
                <label>Organic Matter (%)</label>
                <input name="organic_matter" type="number" step="0.1" min="0" max="20" placeholder="e.g. 1.2">
              </div>
              <div class="form-group">
                <label>Moisture (%)</label>
                <input name="moisture" type="number" step="0.1" min="0" max="100" placeholder="e.g. 35">
              </div>
            </div>
            <div class="form-group">
              <label>EC – Electrical Conductivity (dS/m)</label>
              <input name="ec" type="number" step="0.01" min="0" placeholder="e.g. 0.8">
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;margin-top:4px;">
              🤖 Analyse & Get AI Recommendation
            </button>
          </form>
        </div>
        <div class="section">
          <h2>📈 Recent Soil Reports</h2>
          {% if reports %}
            {% for r in reports %}
            <div style="background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;
              padding:14px;margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <div style="font-size:13px;font-weight:500;">
                  {% if r.village %}{{ r.village }}, {{ r.district }}{% else %}Unassigned Field{% endif %}
                </div>
                <span style="font-size:11px;color:var(--muted);">{{ r.created_at[:10] }}</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
                <span class="badge badge-blue">pH {{ r.ph }}</span>
                <span class="badge badge-green">N: {{ r.nitrogen_kg_ha }}</span>
                <span class="badge badge-yellow">P: {{ r.phosphorus_kg_ha }}</span>
                <span class="badge" style="background:rgba(239,68,68,.1);color:#f87171;">K: {{ r.potassium_kg_ha }}</span>
                {% if r.organic_matter_pct %}<span class="badge" style="background:rgba(139,92,246,.1);color:#a78bfa;">OM: {{ r.organic_matter_pct }}%</span>{% endif %}
              </div>
              {% if r.recommendation %}
              <details>
                <summary style="cursor:pointer;font-size:12px;color:var(--accent);">View AI Recommendation</summary>
                <div style="margin-top:8px;font-size:12px;color:var(--muted);white-space:pre-wrap;line-height:1.6;">{{ r.recommendation[:400] }}{% if r.recommendation|length > 400 %}...{% endif %}</div>
              </details>{% endif %}
            </div>
            {% endfor %}
          {% else %}
            <div style="color:var(--muted);font-size:13px;text-align:center;padding:40px 0;">
              No soil reports yet.<br>Submit your first test →
            </div>
          {% endif %}
        </div>
      </div>
      {% if recommendation %}
      <div class="section">
        <h2>🤖 AI Soil Analysis Report</h2>
        <div class="result-box">{{ recommendation }}</div>
      </div>
      {% endif %}
    </div>
  </div>
</body>
</html>"""

SIDEBAR_HTML = """
<div class="sidebar">
  <div class="sidebar-logo">
    <h2>🌾 KisanMitra</h2>
    <p>AI Farming Dashboard</p>
  </div>
  <nav class="sidebar-nav">
    <a href="/" class="nav-link {dashboard_active}"><span>📊</span> Dashboard</a>
    <a href="/land" class="nav-link {land_active}"><span>🌍</span> My Land</a>
    <a href="/soil" class="nav-link {soil_active}"><span>🧪</span> Soil Reports</a>
    <a href="/logout" class="nav-link"><span>🚪</span> Logout</a>
  </nav>
  <div class="sidebar-user">
    {avatar}
    <div>
      <div class="uname">{name}</div>
      <div class="uemail">{email}</div>
    </div>
  </div>
</div>"""

def make_sidebar(active="dashboard"):
    user = current_user()
    avatar_url = user.get("picture", "")
    avatar_html = (f'<img src="{avatar_url}" alt="avatar">' if avatar_url
                   else '<div style="width:34px;height:34px;background:var(--accent);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;">👤</div>')
    return SIDEBAR_HTML.format(
        dashboard_active="active" if active == "dashboard" else "",
        land_active="active" if active == "land" else "",
        soil_active="active" if active == "soil" else "",
        avatar=avatar_html,
        name=user.get("name", "Admin"),
        email=user.get("email", ""),
    )

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/login")
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template_string(LOGIN_HTML)

@app.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        userinfo = token.get("userinfo") or google.userinfo()
        session["user"] = {
            "google_id": userinfo["sub"],
            "email":     userinfo["email"],
            "name":      userinfo.get("name", "Farmer"),
            "picture":   userinfo.get("picture", ""),
        }
        upsert_dashboard_user(
            google_id  = userinfo["sub"],
            email      = userinfo["email"],
            name       = userinfo.get("name", ""),
            avatar_url = userinfo.get("picture", ""),
        )
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Login failed: {e}", "error")
        return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    stats        = get_analytics()
    pest_reports = get_recent_pest_reports(10)
    user         = current_user()
    farmer_name  = user.get("name", "Farmer").split()[0]
    today_date   = __import__("datetime").date.today().strftime("%B %d, %Y")
    return render_template_string(
        DASHBOARD_HTML,
        stats=stats, pest_reports=pest_reports,
        sidebar=make_sidebar("dashboard"),
        farmer_name=farmer_name,
        today_date=today_date,
    )

@app.route("/land")
@login_required
def land_page():
    email = current_user().get("email", "")
    lands = get_land_details(email=email)
    return render_template_string(LAND_HTML, lands=lands, sidebar=make_sidebar("land"))

@app.route("/api/land", methods=["POST"])
@login_required
def api_land():
    user  = current_user()
    email = user.get("email", "")
    try:
        save_land_details(
            user_id    = 0,
            email      = email,
            area_acres = float(request.form.get("area_acres", 0)),
            crop_type  = request.form.get("crop_type", ""),
            soil_type  = request.form.get("soil_type", ""),
            village    = request.form.get("village", ""),
            district   = request.form.get("district", ""),
            state      = request.form.get("state", "Maharashtra"),
            lat        = float(request.form.get("lat", 0) or 0),
            lon        = float(request.form.get("lon", 0) or 0),
        )
        flash("✅ Field saved successfully! KisanMitra bot will now use this data.", "success")
    except Exception as e:
        flash(f"❌ Error saving field: {e}", "error")
    return redirect(url_for("land_page"))

@app.route("/soil")
@login_required
def soil_page():
    email       = current_user().get("email", "")
    lands       = get_land_details(email=email)
    reports     = get_soil_reports(email=email, limit=5)
    recommendation = request.args.get("rec", None)
    return render_template_string(
        SOIL_HTML,
        lands=lands, reports=reports,
        recommendation=recommendation,
        sidebar=make_sidebar("soil"),
    )

@app.route("/api/soil", methods=["POST"])
@login_required
def api_soil():
    user  = current_user()
    email = user.get("email", "")
    try:
        land_id  = int(request.form.get("land_id", 0) or 0)
        ph       = float(request.form.get("ph", 7))
        n        = float(request.form.get("nitrogen", 0) or 0)
        p        = float(request.form.get("phosphorus", 0) or 0)
        k        = float(request.form.get("potassium", 0) or 0)
        om       = float(request.form.get("organic_matter", 0) or 0)
        moisture = float(request.form.get("moisture", 0) or 0)
        ec       = float(request.form.get("ec", 0) or 0)

        # Fetch crop type for better recommendation
        crop_type = ""
        if land_id:
            lands = get_land_details(email=email)
            for land in lands:
                if land.get("id") == land_id:
                    crop_type = land.get("crop_type", "")
                    break

        rec = generate_soil_recommendation(ph, n, p, k, om, moisture, ec, crop_type)
        save_soil_report(
            land_id=land_id, user_id=0, email=email,
            ph=ph, nitrogen=n, phosphorus=p, potassium=k,
            organic_matter=om, moisture=moisture, ec=ec,
            recommendation=rec,
        )
        flash("✅ Soil report saved! AI recommendation generated below.", "success")
        return redirect(url_for("soil_page", rec=rec))
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
        return redirect(url_for("soil_page"))

@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(get_analytics())

# ══ Standalone runner ───────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    print(f"📊 Dashboard: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
