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
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  *{margin:0;padding:0;box-sizing:border-box;}
  :root{
    --bg:#0a1628; --surface:#111f38; --card:#162235;
    --border:#1e3352; --accent:#22c55e; --accent2:#16a34a;
    --text:#e2e8f0; --muted:#64748b; --danger:#ef4444;
    --warn:#f59e0b; --info:#3b82f6;
  }
  body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;}
  /* Sidebar */
  .sidebar{width:240px;min-height:100vh;background:var(--surface);border-right:1px solid var(--border);
    display:flex;flex-direction:column;padding:0;flex-shrink:0;}
  .sidebar-logo{padding:24px 20px;border-bottom:1px solid var(--border);}
  .sidebar-logo h2{font-size:18px;font-weight:700;color:var(--accent);}
  .sidebar-logo p{font-size:11px;color:var(--muted);margin-top:2px;}
  .sidebar-nav{flex:1;padding:16px 0;}
  .nav-link{display:flex;align-items:center;gap:10px;padding:11px 20px;color:var(--muted);
    text-decoration:none;font-size:14px;transition:.2s;border-left:3px solid transparent;}
  .nav-link:hover,.nav-link.active{color:var(--accent);background:rgba(34,197,94,.08);border-left-color:var(--accent);}
  .nav-link span{font-size:16px;}
  .sidebar-user{padding:16px 20px;border-top:1px solid var(--border);display:flex;align-items:center;gap:10px;}
  .sidebar-user img{width:34px;height:34px;border-radius:50%;border:2px solid var(--accent);}
  .sidebar-user .uname{font-size:13px;font-weight:500;}
  .sidebar-user .uemail{font-size:11px;color:var(--muted);}
  /* Main */
  .main{flex:1;overflow-y:auto;}
  .topbar{padding:20px 32px;border-bottom:1px solid var(--border);background:var(--surface);
    display:flex;align-items:center;justify-content:space-between;}
  .topbar h1{font-size:20px;font-weight:600;}
  .topbar .subtitle{color:var(--muted);font-size:13px;margin-top:2px;}
  .content{padding:28px 32px;}
  /* Cards */
  .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px;}
  .grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;margin-bottom:24px;}
  .card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;}
  .card-title{font-size:13px;color:var(--muted);font-weight:500;margin-bottom:8px;}
  .card-num{font-size:36px;font-weight:700;color:var(--accent);}
  .section{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:24px;}
  .section h2{font-size:15px;font-weight:600;color:var(--accent);margin-bottom:16px;}
  /* Table */
  table{width:100%;border-collapse:collapse;}
  th{font-size:12px;color:var(--muted);padding:8px 12px;text-align:left;border-bottom:1px solid var(--border);}
  td{font-size:13px;padding:10px 12px;border-bottom:1px solid rgba(30,51,82,.5);}
  tr:last-child td{border-bottom:none;}
  /* Badges */
  .badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:500;}
  .badge-green{background:rgba(34,197,94,.15);color:#22c55e;}
  .badge-red{background:rgba(239,68,68,.15);color:#ef4444;}
  .badge-yellow{background:rgba(245,158,11,.15);color:#f59e0b;}
  .badge-blue{background:rgba(59,130,246,.15);color:#60a5fa;}
  /* Forms */
  .form-group{margin-bottom:18px;}
  .form-group label{display:block;font-size:13px;font-weight:500;margin-bottom:6px;color:var(--text);}
  .form-group input,.form-group select,.form-group textarea{
    width:100%;padding:10px 14px;background:rgba(255,255,255,.05);border:1px solid var(--border);
    border-radius:8px;color:var(--text);font-size:14px;outline:none;transition:.2s;font-family:inherit;}
  .form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--accent);background:rgba(34,197,94,.05);}
  .form-group select option{background:var(--card);}
  .btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:8px;
    font-size:14px;font-weight:500;cursor:pointer;border:none;transition:.2s;text-decoration:none;}
  .btn-primary{background:var(--accent);color:#000;}
  .btn-primary:hover{background:var(--accent2);}
  .btn-secondary{background:rgba(255,255,255,.07);color:var(--text);border:1px solid var(--border);}
  .btn-secondary:hover{background:rgba(255,255,255,.12);}
  .btn-danger{background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.3);}
  /* Map */
  #map{height:220px;border-radius:10px;border:1px solid var(--border);margin-top:8px;z-index:1;}
  /* Result box */
  .result-box{background:rgba(34,197,94,.07);border:1px solid rgba(34,197,94,.2);
    border-radius:12px;padding:20px;margin-top:20px;white-space:pre-wrap;line-height:1.7;font-size:14px;}
  .result-box.warn{background:rgba(245,158,11,.07);border-color:rgba(245,158,11,.2);}
  /* Alert flash */
  .flash{padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;}
  .flash-success{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.25);color:#4ade80;}
  .flash-error{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.25);color:#f87171;}
  /* Soil health indicator */
  .soil-meter{display:flex;gap:8px;margin-bottom:16px;}
  .soil-meter .pill{flex:1;text-align:center;padding:8px 4px;border-radius:8px;font-size:11px;font-weight:600;}
  /* Responsive tweaks */
  @media(max-width:768px){.grid3,.grid2{grid-template-columns:1fr;}
    .sidebar{display:none;}.main{width:100%;}}
</style>
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra — Sign In</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box;}
    body{font-family:'Inter',sans-serif;min-height:100vh;display:flex;align-items:center;
      justify-content:center;background:#0a1628;overflow:hidden;position:relative;}
    /* Animated blobs */
    .blob{position:absolute;border-radius:50%;filter:blur(80px);opacity:.25;animation:float 8s ease-in-out infinite;}
    .blob1{width:400px;height:400px;background:#22c55e;top:-100px;left:-100px;animation-delay:0s;}
    .blob2{width:300px;height:300px;background:#16a34a;bottom:-80px;right:-80px;animation-delay:3s;}
    .blob3{width:250px;height:250px;background:#15803d;top:40%;left:60%;animation-delay:5s;}
    @keyframes float{0%,100%{transform:translateY(0) scale(1);}50%{transform:translateY(-30px) scale(1.05);}}
    /* Card */
    .card{position:relative;z-index:10;background:rgba(17,31,56,.85);backdrop-filter:blur(24px);
      border:1px solid rgba(34,197,94,.2);border-radius:24px;padding:48px 40px;width:420px;
      text-align:center;box-shadow:0 25px 60px rgba(0,0,0,.5);}
    .logo{font-size:48px;margin-bottom:8px;}
    h1{font-size:26px;font-weight:700;color:#22c55e;margin-bottom:4px;}
    .tagline{font-size:13px;color:#64748b;margin-bottom:32px;}
    .divider{display:flex;align-items:center;gap:12px;margin:28px 0;color:#334155;font-size:12px;}
    .divider::before,.divider::after{content:'';flex:1;height:1px;background:#1e3352;}
    /* Google button */
    .btn-google{display:flex;align-items:center;justify-content:center;gap:12px;
      background:#fff;color:#111;padding:13px 24px;border-radius:10px;font-size:15px;
      font-weight:600;cursor:pointer;border:none;width:100%;transition:.2s;text-decoration:none;}
    .btn-google:hover{background:#f0fdf4;transform:translateY(-1px);box-shadow:0 8px 20px rgba(34,197,94,.2);}
    .btn-google img{width:20px;height:20px;}
    .footer{margin-top:28px;font-size:11px;color:#334155;}
    .features{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:24px 0;text-align:left;}
    .feat{display:flex;align-items:center;gap:8px;font-size:12px;color:#94a3b8;}
    .feat span{font-size:14px;}
  </style>
</head>
<body>
  <div class="blob blob1"></div>
  <div class="blob blob2"></div>
  <div class="blob blob3"></div>
  <div class="card">
    <div class="logo">🌾</div>
    <h1>KisanMitra AI</h1>
    <p class="tagline">Har khet ka saathi — Every farm's companion</p>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <div style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#f87171;
          padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;">{{ msg }}</div>
      {% endfor %}
    {% endwith %}
    <div class="features">
      <div class="feat"><span>📊</span> Analytics</div>
      <div class="feat"><span>🧪</span> Soil Reports</div>
      <div class="feat"><span>🌍</span> Land Details</div>
      <div class="feat"><span>🤖</span> AI Insights</div>
    </div>
    <div class="divider">Sign in to continue</div>
    <a href="{{ url_for('auth_google') }}" class="btn-google">
      <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google">
      Sign in with Google
    </a>
    <p class="footer">Secure login via Google. Your data stays private.</p>
  </div>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra — Dashboard</title>""" + BASE_CSS + """
</head>
<body>
  {{ sidebar|safe }}
  <div class="main">
    <div class="topbar">
      <div>
        <h1>📊 Analytics Dashboard</h1>
        <div class="subtitle">Real-time farming intelligence overview</div>
      </div>
    </div>
    <div class="content">
      <div class="grid3">
        <div class="card"><div class="card-title">👨‍🌾 Farmers Helped</div><div class="card-num">{{ stats.total_farmers }}</div></div>
        <div class="card"><div class="card-title">💬 Queries Answered</div><div class="card-num">{{ stats.total_queries }}</div></div>
        <div class="card"><div class="card-title">🐛 Pest Reports</div><div class="card-num">{{ stats.total_pest_reports }}</div></div>
      </div>
      <div class="section">
        <h2>📅 Last 7 Days Activity</h2>
        <table>
          <tr><th>Date</th><th>Total</th><th>Voice</th><th>Photos</th><th>Mandi</th><th>Pest Reports</th></tr>
          {% for d in stats.weekly_stats %}
          <tr>
            <td>{{ d.date }}</td>
            <td><span class="badge badge-green">{{ d.total_queries }}</span></td>
            <td>{{ d.voice_queries }}</td><td>{{ d.photo_queries }}</td>
            <td>{{ d.mandi_queries }}</td><td>{{ d.pest_reports }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
      <div class="grid2">
        <div class="section">
          <h2>🔍 Top Query Intents</h2>
          <table>
            <tr><th>Intent</th><th>Count</th></tr>
            {% for i in stats.top_intents %}
            <tr><td>{{ i.intent }}</td><td><span class="badge badge-blue">{{ i.count }}</span></td></tr>
            {% endfor %}
          </table>
        </div>
        <div class="section">
          <h2>🐛 Recent Pest Reports</h2>
          <table>
            <tr><th>Location</th><th>Crop</th><th>Pest</th><th>Severity</th></tr>
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
            {% if not pest_reports %}
            <tr><td colspan="4" style="color:var(--muted);text-align:center;">No pest reports yet</td></tr>
            {% endif %}
          </table>
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
    stats       = get_analytics()
    pest_reports = get_recent_pest_reports(10)
    return render_template_string(
        DASHBOARD_HTML,
        stats=stats, pest_reports=pest_reports,
        sidebar=make_sidebar("dashboard"),
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
