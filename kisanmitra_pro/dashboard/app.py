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

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KisanMitra AI — The Future of Farming</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #16a34a; --primary-focus: #15803d;
      --bg: #0f172a; --surface: #1e293b; --text: #f8fafc; --muted: #94a3b8;
    }
    * { margin:0; padding:0; box-sizing:border-box; }
    body { font-family:'Outfit', sans-serif; background:var(--bg); color:var(--text); overflow-x:hidden; scroll-behavior: smooth; }
    
    /* Navigation */
    nav { position:fixed; top:0; width:100%; padding:20px 40px; display:flex; justify-content:space-between; align-items:center; z-index:100; backdrop-filter:blur(10px); background:rgba(15,23,42,0.6); border-bottom:1px solid rgba(255,255,255,0.05); }
    .logo { font-size:24px; font-weight:700; color:#fff; display:flex; align-items:center; gap:8px;}
    .nav-btn { background:var(--primary); color:#fff; padding:10px 24px; border-radius:30px; text-decoration:none; font-weight:600; font-size:14px; transition:0.3s; display:flex; align-items:center; gap:10px;}
    .nav-btn:hover { background:var(--primary-focus); transform:translateY(-2px); box-shadow:0 10px 25px rgba(22,163,74,0.4); }

    /* Sections */
    section { min-height:100vh; display:flex; flex-direction:column; justify-content:center; padding:80px 10%; position:relative; }
    
    /* Hero */
    .hero { background: radial-gradient(circle at 50% 120%, rgba(34, 197, 94, 0.15) 0%, transparent 60%), linear-gradient(135deg, #0a1628 0%, #063121 100%); align-items:flex-start; text-align:left; }
    .hero h1 { font-size:5.5rem; font-weight:700; letter-spacing:-1.5px; margin-bottom:20px; line-height:1.1; animation: slideUp 1s ease-out; }
    .hero h1 span { color:var(--primary); }
    .hero p { font-family:'Inter', sans-serif; font-size:1.25rem; color: #cbd5e1; max-width:600px; margin-bottom:40px; animation: slideUp 1s ease-out 0.2s backwards; line-height:1.6;}
    .scroll-indicator { position:absolute; bottom:40px; left:50%; transform:translateX(-50%); animation: bounce 2s infinite; opacity:0.6; }
    
    /* Story Layout */
    .story-grid { display:grid; grid-template-columns:1fr 1fr; gap:80px; align-items:center; }
    .story-text h2 { font-size:4rem; margin-bottom:24px; line-height:1.1; letter-spacing:-1px;}
    .story-text p { font-family:'Inter', sans-serif; font-size:1.15rem; color:var(--muted); line-height:1.7; margin-bottom:24px; }
    .story-img { width:100%; border-radius:24px; box-shadow:0 30px 60px rgba(0,0,0,0.5); object-fit:cover; aspect-ratio:4/3; }
    .glass-card { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); padding:40px; border-radius:24px; backdrop-filter:blur(20px); border-left:4px solid var(--primary);}
    
    /* Animations */
    .reveal { opacity:0; transform:translateY(50px); transition:all 1s cubic-bezier(0.2, 0.8, 0.2, 1); }
    .reveal.active { opacity:1; transform:translateY(0); }
    
    @keyframes slideUp { from{opacity:0; transform:translateY(30px);} to{opacity:1; transform:translateY(0);} }
    @keyframes bounce { 0%,20%,50%,80%,100%{transform:translate(-50%,0);} 40%{transform:translate(-50%,-20px);} 60%{transform:translate(-50%,-10px);} }
    
    /* Features Grid */
    .features-section { text-align:center; }
    .f-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:30px; margin-top:60px; text-align:left; }
    .f-card { background:var(--surface); padding:40px 30px; border-radius:20px; border:1px solid rgba(255,255,255,0.05); transition:0.4s; }
    .f-card:hover { transform:translateY(-10px); background:rgba(30,41,59,0.8); border-color:var(--primary); box-shadow:0 20px 40px rgba(0,0,0,0.3);}
    .f-icon { font-size:40px; margin-bottom:20px; display:inline-block; padding:15px; background:rgba(22,163,74,0.1); border-radius:16px; color:var(--primary); }
    .f-title { font-size:1.5rem; margin-bottom:15px; }
    .f-desc { font-family:'Inter', sans-serif; color:var(--muted); font-size:1rem; line-height:1.6; }

    /* Flash */
    .flash { position:absolute; top:80px; left:50%; transform:translateX(-50%); background:rgba(239,68,68,0.2); color:#fca5a5; padding:12px 24px; border-radius:30px; font-family:'Inter'; font-size:14px; border:1px solid rgba(239,68,68,0.3); z-index:200;}

    /* Footer / CTA */
    .cta-section { background: radial-gradient(circle at 50% -20%, rgba(34, 197, 94, 0.15) 0%, transparent 50%), linear-gradient(135deg, #0a1628 0%, #063121 100%); text-align:center; justify-content:center; align-items:center; }
    .cta-section h2 { font-size:4.5rem; margin-bottom:30px; letter-spacing:-1px;}
    .google-login-btn { display:inline-flex; align-items:center; gap:15px; background:#fff; color:#000; padding:15px 35px; border-radius:40px; font-size:1.2rem; font-weight:600; text-decoration:none; transition:0.3s; transform:scale(1); }
    .google-login-btn:hover { transform:scale(1.05); box-shadow:0 20px 40px rgba(255,255,255,0.2); }
    .google-login-btn img { width:24px; height:24px; }

    @media (max-width:900px) {
      .story-grid { grid-template-columns:1fr; gap:40px; }
      .hero h1 { font-size:3.5rem; }
      .story-text h2 { font-size:2.8rem;}
      .f-grid { grid-template-columns:1fr; }
    }
  </style>
</head>
<body>
  <nav>
    <div class="logo">🌾 KisanMitra AI</div>
    <a href="{{ url_for('auth_google') }}" class="nav-btn">Sign in to Dashboard</a>
  </nav>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="flash">{{ msg }}</div>
    {% endfor %}
  {% endwith %}

  <!-- HERO -->
  <section class="hero">
    <div style="max-width:800px;">
      <h1>The Future of <span>Farming</span><br>is Here.</h1>
      <p>Har Khet Ka Saathi. Empowering Indian farmers with bleeding-edge Vision AI, Voice Assistance, and NASA Satellite Intelligence.</p>
      <a href="{{ url_for('auth_google') }}" class="google-login-btn" style="margin-top:10px; animation: slideUp 1s ease-out 0.4s backwards;">
        <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G">
        Get Started with Google
      </a>
    </div>
    <div class="scroll-indicator">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
    </div>
  </section>

  <!-- STORY 1 -->
  <section class="reveal">
    <div class="story-grid">
      <div class="story-text">
        <div style="color:var(--primary); font-weight:700; letter-spacing:2px; margin-bottom:12px; font-size:0.9rem;">AGRICULTURE IS UNPREDICTABLE</div>
        <h2>Farming is hard. You shouldn't do it alone.</h2>
        <p>Pest outbreaks can destroy entire harvests overnight. Unpredictable weather washes away months of hard work. Soil degrades silently without proper nutritional balance.</p>
        <p>For decades, farmers have fought these battles relying on guesswork or delayed expert advice. Not anymore.</p>
      </div>
      <div>
        <div class="story-img" style="display:flex;align-items:center;justify-content:center;font-size:7rem;background:linear-gradient(135deg,rgba(255,100,100,0.1),rgba(15,23,42,0.8));border:1px solid rgba(255,255,255,0.05);">
          </div>
      </div>
      </div>
      <div>
        <img src="data:image/png;base64,/9j/2wCEAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSgBBwcHCggKEwoKEygaFhooKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKP/AABEIAoACgAMBIgACEQEDEQH/xAGiAAABBQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgsQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+gEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoLEQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEKFiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery8/T19vf4+fr/2gAMAwEAAhEDEQA/APA2WmFaslaYVpkWKzLTCuKtFaYyUXCxXxRT2WmkUBYQU4UynCgLDqcDTKXPFO4Eyt0qeN6qA1IrUCLyyUu6qiNUgamFiyD708NxVZWp24YoAsq1O3dDVZX5p2/IxQBaVu4qyjjArPR+cGplfFJjLoYNwaco5qsrZqwp6VLKL1py2DVornOKz4JAnU81pWzh1rORpHUZsyp4qnJGeTWuqcH3qGaLCk1KkW4GOSQalilINWGg796qyxshzjitE7mVrF+OXcBUoYYB61mRSYxV2OQHuKTQJkp600DNDYpyepoGIU46UwpUxILcUMpxmmmS0ZsgO40+PgVLMnzYFNVdtaIhiqeuaq3TfMamZwM5qJ1VyCTTEVyvc1XlX0q/t3HAqMwZagCnGCGq2sG5SWqaOzZnXA4Na0GnMY8dTSGc7LCACAKpNHg10/8AZsjMxx0qld6eYm5HBoCxiYx2pOavTw7QDUPlcZpiIgcCkJNOdefakFADD1o6CklPNAPy80ANamMaexxUTGgBpOKYxoY0wmhCFzmnCoxUgqhE8YyRWjaW4kYDvVG3XJFdFp8SBlJ600Sx39m4XNOXT1XFbbNGYMDAquTnAQc0yLkFvb/vFUDFaq26RrlsZxT7S3VFyTlu9R6rtRR8wz6Z60AZdxIDJtHTNRMu3rVYTA3BJ9anvJvkwDzTFYpzy5bilgjMrgCqZfLZrTsZFCj+9QNlw220CklURpipfNXHLVQu7kbSAcimSRSlVBOazp5S3eknnyaozS8VNykh00uO9VHkJpHbNRk0ihrmoyaceabikMaTSYzUgjJqRYuOlMVyDFOANT+VzSMmKBXIguaeFIFOXA4oZx2FMCQLxQVzSp0pwNc9zpIiuKaUqc0bc0XApulRMmKvtHULx0XAplaTFTslMKUwI6KdjFJRcVg70oNFAFFwsPDVKrVAKepp3CxODTxUCmpVNO4h5FIDinCmsKAHB+amWTPeqvenKaAsX0f3q1HIMVmI1WEekxovF8c1Ytpyjg5qgGyMVPF6VDKR0djOJlIPBFWpYty1i6e22QAtjNbaPu4rnlozqhqii0ZB9KrzqGU+orSnQEnGazZfumqiyZIzSpBpySbTUrLnmq7/AHq1TMWi8JAQOanRwVxWapwOKnifPenYVy2WG7FWNwKY71TjOTUoBzkGkMhlbDntUPmDsaS4JxVRnxVohkkxINNDmo/Mz1oJGKoksRtiplOSDVaEZ61oJt2DgUwLFvLtwR1rVsrs78cAViq6j6UonGDilYLnQpcL5hO0EmsfUZFMzF+vWoBd+/aql3OGzzmiwXKruGJHaopGGwgUwnk4qJmNMVhGXimMAo96CxJ4pj5AzQBC55qMtgUrmoWJoGOZqYTTTnNMoEKze9NBoxmgDmgBwqRB0piip4kyaaJLtmMsAK6CxgPDNn2FZuk2pkceldfa2qCIDOTj8qpEMz3D4wOlNEgjdcnpyea0riBbeIlm5xXM3UjK5HPWmKxqXWqNCcKelY9zfSTtudiarzuzdSaWO3ZkzSHYYJirdacbgvkZ61BcJ5ZIqFWIoCxaB6VJvxjB/wDrVS8zim+aRQFjS+0EDGarzz5XGaptMaiZyaLhYfJJ71AxJpTk09ImagZFtJo8s4q7Hbt3HFWY7Jn7YFArmR5WadHblj0rdWxQdaZJAkXSmK5QFsEXJpjgDgCrUjdhVWUigRETioXOac7VFnJoGIc9qTFPJppPFICwlSYFQqalVs1znULtxQKkA47UhWlcLAOaDHkUAVKh9aLjsVHiIFQPHWkwBHrVd19qLisZzLimkVbdKgZcU7gRYopxFFFxCUA0oHrRj0p3AcDUgNRCnA0XCxMGpQ1Qg07dTuA89aVaZmnKaLgTLVmLpVZDVqAZpXBIeoOatRHimRxljxVlY/LHNQ2aKJIh4461rWMjEjf2rMs9rSgNjBrTOIiCORWU30NoLqWZGOapTLkn1qRJ93BFK21mx3qE2i2rlJ1wtU2XGTWlcoq9azpDzitou5jJWIi2OKfHJgimkUw8VdzJotiT0q7E/GTWQrmp4pyo5p2BF24AZelZUwwTV0Tg1UuGDEnvTQmV880BsUx2x0pm7tVEtFuJ8VYSbA5NUEPenu2MUxWLzTjHvUXmk96qF/egPimBZaYgdaheUknNRu2eaaBk0AK0mM1HuLGpPKZjwKtW9izFfQmgCO3t2kYYqK5Ty3ZG610lnai3Vi+OeBWLexlrhj6GgDHkXFRleKuzxndVaUYGKAKrdaSnkZPSgIT0oAaEJqRYj1xU8EDsenFXY7VwBlc00S2UobctgYrRgs8LuxxVi2tiG+YcVpGIeWFAxTsTcNDjZZlPY12NpFFHbjHOa5a3YRDp0qb+0ZFIAbimSat/AJRgHgVi3FkGk+YAKKtJfF+D3qG6uMnANAjONihl68VZAjVGUYxVSefb0NVvtHfNA7BdQAkt69qzJEwxq3Nc5PBqjLJ3oGRuKjNDPmkHJpDAg0+KFmxxUkKZIyBV+NMdutMRDFak4GOa07bTlUZcU+CNU5apWut3AGBTJYvkIoxgZpk0iRjAx9KhmmxyTzWfNMTmgViaa4ycA8VFJLuXmqbSc9ajlnwMA0DsOnlAqo8mTTWYuaTbSHYT7xpSMD3oxgU7aTTAjHJpdpPapkj9alEftSEUt2KeslRGkHSuc6i7HLVgEEDFZitg1MkppDRdIx0oBqJZsjmnhgaQx4NKVzUfNOU0ARPHVeRKvEg9ajljBHFFwsUGWm4qwydabsoFYgxSEVOY800xmi4WIqUU7YaNtO4WEop2KTFFwsAp4PNNpy07hYmQ1ZhbFVFqdDSuCRo2820irUxaQBgOKzY6vQnoG5HpWbNI9h0TYat6zMU0QDMNwHNYkoVeR+VJHIV6VElzGsXymrLGFk+Q5BpwQp83es9JmHU+9WxceYpz+FS0yk0NuXNZztzk1PMxJ9KjKhgfWtI6GctRinJpHXJpjZjapUkHXPWtDOxCykU3cRVsqrioZo1X8qdyWiLzMVHI/FRSPgnFR78nk1RI4nNAprEU0tTET7wBimmTPeoGb0pm7mi4Fjfn6U4HNVwami6800xE6oStSxxkY45q1p0IlbaOTjp610+n6EJFSUjgjODQ3YLNnKBHAOBUsTyBhgdOlddLoypNtVflPeq9xpaRZ2gZoUkwaZjNKSoBqNUEhIxkmrVxCE4xiqgl2dOtUIr3luEPSsedMsa2LiXf71nsuXoArxW5fGKuQWJA+YcVatowoyRzV4MBHjHWgkqRW6qPpUvAOBSsH24UGmKCBzTFYspxSvL71Bkge1QSufWmKxO05xikV8knNUTJjrSmYYouFi+kuwE5qCWckk5NVGm96iaTIouFh00pZ6iaTiomyTxTWBNADJJCc1CzE1ZWAt2pwtT3FAylgk1PFGWPSraW4HWp44jnCigQttbDqxFaVhbGeXC9qS2tWcBelacEJt8hP0piK18kcI2hssOtZckoB96m1SXExwayXlxQFiSeb3qjLLSyPmotpNIBpYmmEEmrAi4p6QkngUAQImB704RFjwK0rfT3fkKSa0bbSmY4K4HrTEzDjtST0qylkxxkV0BskhHAFMKKD70ybmR9iwOaDAFHStKQZ4FQyhR160AcmUpuKtFeaaV9q47nbYr4pQDUpSlVadwsRgkU4ORUgSmNH6UXHYkWWplcEVSwRUiMRSYFrPpS5qNTkU8rSuVYYwBOaABQwxTaLisPC8U4IDwai34p6yc0DHGEelRvB6dKsrID1p4xilcdkZ/lUwxmtEqPakMG4cCnzBymdsxQBzWiIOCCKgeDFHMLlIFqRDSbMGlUYNO4rFuE9K0oFBUGsqLtV2GQrUM0iTXAINMhbDc0PLuHNR+YAaQ2XshgO1SL8nBqgJcU5p8iiw7l2VlIqAHB56VW83JpQ+epppWJbuS3BBFVN+KklftVN254q0Qy5HIexomfd0qqjGpRzTJsQzKcmqzEg1fdSRVd48k4pg0RFiRTcmn+WQackfPIp3JsNRCxxUjW7A9KuWsQ3DIyK2FhiKA7QTRcLHOLCQOhq3bWpfFaktuBnaBUtpDgZIAouFifTrTynSRfvLziu0S9j8gBBt46VzEA2Ac81bilpPUadjY+0Bhz+FU5pcZ9cVALhVAOcjNZeo3p3kqeOlNITYzUnVySOvtWNIpJPWrTz7sZqCWYBeKskqsDnFNIApkkhLUx2OB70xWLSyZHtUsUpLDJrO83AxQJyDwaYrG75oAqKSRevGayxde9I9xnvRcVi7LNiqUs3NQvNkGqzvmi4WLPm5NNkl4qsXNNLEmi47ExkyacpquKeGx1ouKxZBp6Lk5NV1cClMvFO4rFveqDGKTzc1UBLVMmB9KAsW4V3nnpV6IKhFZqzbelSLPzTEbEcwQZ6Ux7xuWHXtWeJS2AKnit2Yc96BWKl0/mEt3rMmBV8GugmsTkbeAOuazZ7NzLgigZnqhY9Knjix2q8lsEHNKVC9qBFdIRtJNXtJtfPlw3QVEmC3NaVrKkI+Uc96CWaqQoi7VwB60plRRhcZrKmu2boagW5IOTTFY0LlwCc1nvOATmoZ7rdVNpc0BYuSXAHSqskuc5qu8o7VBJKAKYWImGKbu9RWhLbBuhqpJbMvauBSPQcWRYBo2+lBjZaBnvTuKwhFIafRgUrhYiIpOlTbc0nl5p3CwkR5qcVEqEVKvPXrSbKSFKbqQwd6eOKcppXHYrPEQKhKkVpOARVd0APFCYnErBiDTxIfWlKikCVQrEqynNWYZRVMLUqHFIpF4ENzjmho1YEVXVsVKsgqSiCSHriqzIVNaRYVBMAR2ppicStGcVOHqHGDSE0xLQnMnvUZk561ETTcHtQJk/m0nmE1EqmpFXmmKw9ZDUgYmmqgNPCc0XCwYLCmiPJqdRgU4ACi4cpEIgKcuBjNObpxUTA5yKdwsWBgiomUCkjY5FPl5GQadxDdgIpAo4xTWbA4oWQbsmmKxowkKO1WBKAnFZizAU4y5xQBpRTbmANXFYKOvNYkUuGq4s2RQIv/aNpNOF3kVmPLkmoWnI6U0I1mue+aru6P1xWe1wahafHQ1SJLcuFzg8VSml6jNMe5yOtVZJMk0xEjv3pjy8dagd6iL0ATGQ0hkNRbs0DJp3AkWQk07zKYEJ7U7y2PrRcAL5puaeIm9KCmOtFwGUAZpStKoouA9V4prYzUgIx1pjrk8UXEN/GlAJpNh9KmjQ5yKdwsNGQcVIoPWniFmar8NuPL5PNO4milDG0jACtK3sxjBySaW2i2NnpV+Bow3NArEMVmAOBWhFGsShmXJp6zxKuBUNzcqfu9KYrBK5bOBgVUYAknFK04x1pjTKQcUCIZCN2BTBHu4Peo5JfmpVk755piLK2vcCmywlAMnFOjueACeKjuJt1AiFs+uahdsd6V5BVWSTOaAsOdzUDyYzTJJeKgeQUBYe8tQO+e9MZ80zNAG4stSCQHrVQqynpSBiPavPsejcuEIw5A5qF4FJytRiSniT3paoejI2tz2qPymzyDVxJBUvDc8UczQctynHAW6UG3de1aSKO3WpzGCOelS5lqFzEKEdRSAEGtqSBSOlUpLUjkU1O4nCxXRS1PKEdRThGy9qeFZhRcLEQFQTIytzV9I2zgirws1lQblpc9hqDexzZNNLYrV1LT/IBIBH1rHcYNaRkpbGcouLsSCSlElV6eoJpiJ/Npyy+9V9poAIoGWvM96XdmoVBJqdY6V0MYVzzSCPmrG3jmnKozRzBykSxetSiEVMyDbULbl+lLmuPlsAiWlKKKTdxTN2aLgSnGOKjJI7VJGpIp7xEjgUXCxXEhpwY0/yj6VIqDFO4rEBY0c4qcgVGQM07isMzjtSFs0rD0qMg0xNDXOKj3Gn7c8GniDiquTYiDGpFfmmsmDTOQadxWLaP61Is2BVEMcUu8+tMVi40x9ajMue9V99ML+lAWJy/rUTydqiL8UwkmmibEhamk+lNpVBNO4rCEE0CMk8VYjjJq3b24Zvmxii47GcsDMeBmp47Ryfumt22gjTJ2inSFFyQKVw5TPhtNi5cfhTjbjqKkaaoss3Q1VxWI5VVV96pMCTxVyQHOGpUKKeQDTuKxRMT46Gm7CM8VpySBhhQKpuu3NAWK/SpEHrTD1qSNSaAsSKpPapYwB1pynatRscUAWd4UZoSfnFUy+e9OUjrTEaIm4FOE4rNMuOlKJDTuKxrLOByajluFI4NZxkJHtUbOe9O4rFt58nrSeaapbqkVs9aBWJmJzmoxLz1prPmmjAOaYrFlZiBUck9QO/FQO5NFxWJZJveq7y5701jmoyKAsDOaYTSkU3FFwENJTsUYpiOjyhNK0Mbr0qDoakRiK8w9Mqyw7CairRZQ3Wong7impCcSnuxTllI71IYD2FH2dvQ07oVmPjucYzVuO6BFZzQsKWMFfWpaTKTaNL7R2p6SButUUBJqwnBqGjRMshQaliiUnpUcTDvV2HbkGs27GkUmKLPOCBmtWxjVflYDntUUOO1WUQ7wRWEpNnRGKWxU17T3aHcmCq8471wt5Ftc8d+9erLA0q44IIxg1yXiDRZEkZlQgHnitMPWt7rMsRRv7yOM21IiE1pR6ZKSBsJz04rT03QZ5pCuwg+hFdUqsV1OWNKT2RgxxseMcU8wE9BXeWXhMsSJhsI71JP4aWCTOQwrB4qFzdYaRwK27A96njXHBrtJNEQrwp/Csu70hoz904pqvGQOg4mA4FNC5PFWprcqxFLDaMSOK05lYz5XcW2iMgIxzS3VoyJnafrW1pVovmKJAQO9aV/awSAImWz1rF1rSsbqjeNzgyuMg02NfmrdutLdGPy5GeKSHSplcN5ZKj2rb2qsYeylfYrQWrYBxx2q4tr8mcc+lbMWnuY0IU4x+VPOnyDjbWDrJnQqNjnZIMZ4qrIuK6a8sHij3uuF9awLgAHg1pCfMZzhylBs03aTUjjnikXOetbpnO0N2HHSjYfSrCipFUUcw7FbyPagqF4NaMKAkVbWyjmByBnHWk523H7O+xz7pnoKiaJs9K6FdMGOByOtV57Py87u1NVEJ02YMikdqhJ61pXMecnFZ0iYNap3MpRsRMTmm5pxoC81VyBvU1IkZY1JHET0rSsrQN170nKw1G5Vt7CWZSyKSo6mpZLQw8Ec11lhp5hTPQMKV9OUnLLn61l7bU29hocpBAzjIU49auRxCPk1uSQJFHtVQBVKSEMccVSqXJdKxSkm2rhaqs7HNW540XpzVJsA1aZm42G+xo3bc00sM5qGR81VxCyymog/rTTz3puaLk2LIkwuBTGyx6U1CBTvMFO4WFEOeeBUiJiog9PDE0XCw92xx1qBmp+MnmkMZp3FYiOSaeoJowBSb/AENMVh+APrRuxUJY0gJPWmIlMlMyWNJsp4wBTuIcq0p4pN9G7NFwsITTSSafkd6YzU7iaGMKiNSMcmmbSaBEZpMVMImPaneSR1phYqkGjbxVlo8UwgCgViDbRipCRSVSJN4xc9KVYzVzYKesXqK8nmPVUSoIyenNL5bDtWlDGM8irscMLdRzUOdi1C5giM+lKEb0zXTDToGHf8Krz6Xt5j5FT7RFezZgOp7rUflg9VrYa1dRgiozbMewquYnkZk+Vg5FSKDV82jH+GhbRgeQafMgUWVAtTxMVPSr8Vl9DUn2F+yE1Dmi1BkdtcbTyK17a7jxyKyvsjg8Rn8qcFZeorOUUzWMmjo4b5BjGKsrdQyjbIqke9csrN2NTRyup5zWTpdjVVDpo/scbBkiQH1xViNoA29QA1c0lweMmrK3gUYzWbpstTR0H2xTwap3Uquc5NUIrpD1zzSM6u2B09aXIPmHyXoTgciqct4JB8wFXYdMW4bd5nBq8nh2B42Bdg3YjtVLlRLbZyE0CsxfaDVnT7QXEoUYGa1p9AuYhkEMua0NF0oxSFpU6d60c9CFHUz49PMZxkVZSz3Hpz6gVq3nlLkBcGqkTsuehFZas1VisLcK+1kB9yK0re2TA3AflUUbB2+Yc1bi2YGTUu40yRbSLqAKjvrYJaSyom5lGac77fpSG+CLgniiwXOB1PUZJI5IQNq5zya5mdmJrttY0uKZ3khc7iSSDWJd6UQqqmC2Oa7aUopaHHVjJvU57qOabnHSrsllKhO5TxVWSJgc4rpTTOZpoQOR2qRZDVbcQelSIwNUTcvQy4NalneKoGcVgF8CnLL71Mo3LjKx2dpdQbskDJp+ow208RaPAY9a5GOZgQQxq2Lttoyc1k4Wd0bKomrMh1KJUHyY+lZT2zFNxFbRmVzlgCailXcPlFaxlbQxlG5gNFjORSKnNak0JORjFNgs2kkAxitecy5NSCFCMHFaVmcyIvvV9NLWFP3nzN7dqiZVhfIHIqOdS2L9m46s6KOQEL0wBUzTxbSM1yxvmHAaj7Ycct1rLkNfaI1b2ZC2O1US0RB5xWdNc7j1qu9xgcGtVGxk5lm4Zcnbms+dhSPKWNRNz1rRaGT1I2b0qM1OcelMCbjVXIsRYyaXbU/l4HApjKadwsR0AU7aaXZTuIBgUu6gJRtpgGTTieKFU0u33oCxCQTSBCetTkAUU7k2IwgxzS7RTjxTC1O4rCkAU04o60oQmmIZQTUnl+tL5foKdxEPJ6U4Rk1MEFSIvNFwsQLEB1qZEUdqlEWenFRuAvei9wsP3oo4qvNIDTHaomyaaJY13zUZyalEbHtU0VuT1/KqJZVSFmNWYrZONxqyIce1KIwO9UQbojNPCkdq0fsbelKLRvQ14fOj3ORlBVNTIrCrYtG/u09bZh/AalyRSiyusrrgZqZZm7mrMcAzhlNTizifpkGockWospcSDkUC0Y8ryKvLpj5+Q5q1FY3CgcYqXNdC1HuUYInTG6PP4VPJHE6bWQKfUCta1t3Bw4zU80GDiSEbT6is3LUvlOWNoQ3yMMVctUljx8wP4Vs/2dbucgMh9KlFisQ+Ug/UU3O4lGxnEsFydp+orOuShOTGM10L6a8w+Rtp9KoXOh3ijdwR7URaBpnOyhSemKbnHBxWw2lXBHKA1H/ZUoODGa15kRyszVIHWpVePPIFXxpUn9w/lS/2TLz+7OB14pc0Q5WVVliA4AqVXTbkYzU6aKz45wTTn0iWL7wBFK8SrSEt7raRg1opqG0cmslrYqeVI+tV5GZD0pcqewczR0a6mDwasR367eCK4/7QfpinrdMO/FP2Yuc6Se4V3OcEVVMihuORWK1zIelIk827kU/ZhznS28kRPIqw8a7dyScelYMExIGeCO1aMMxAqXErmHSzkAjNZM90SeDmrOt3CwwpkEF8844rFiuw7ADnPtVRhfUmU7aEzTuT0NMYSP8Aw81eaCVACUyD3xTQJAPu1SsTdmFqW+NWLA8cAYrBaQlsYrrtRQSJ5cpxzwD3rAnt0Qtgcit4PQxmtTIkHJwKiPrVubJO0UxoiE5rZGDRW309CMVXlJBximq+KqxFzSjIwKlVgeKz45elWUlHFS0WmaMSIVHGTUqw59hVSGcAVMboAcVm0zRNE5twOrA1PbNFFzgfWsx7hmPWk80nvRythzpbGvdXoK8Vj3E+5jTTJnqTUEmCDVRjYmU7jGc+tN3E00j0pBuzWqMh3Jo2etPVWOMVIkLnp1p3CxD5dJ5eTgVopZStCW2k1ctNMZFEsi8Hp61DmkUqbZirAT1Ganitc53DArWnURDG0flVKSTnpihTbG4WKslrgcEVD5K7sZ5qxI+e9MDAdOtWrkOwC1XHSj7KAM5FHnEUhlJ6mnqToMkjXtUBGOlSO+TUZNUiWNNFKRmkANMkQ96SnnpSbSe1O4EZpoXJqyluTUot/QU7hyldEA+tSCNm6CrkVuo+9VlCE6dqTkNQM9bOVscUv2CbPQVpG5IphuWx0pczHyRK6aa5GWdRUn2RIvvHJp/mu3U0hyTzkmi7FZCGBSDzULWSMck1YJYDgUxge/FNXJdiL7HEBzTDBCv8IqVmx1qF39qtGbEYIOgFMLD0pkjGoSTWiM2TF6YXqPB9KaQTVIg9m0i2ttQJThWHY9a1j4UYjMMin2Nctc6deRsJJIpkK9Ch6Vr6PqV7aw+Ws8vJ438/zr5hrqmfTp9LFuTw7dpnMW4e1Vn0iaLlo2H4Vs299qFwuPNz+FXYftS4ZizH0qbsZygtCDyP0qRLQd1H5V1knzkNJAT+ABqe1hsWb97DcR575yKNRXscmluB0GDUiRSA84xXaT6VZNGXjkOMdCvNYE8dvHLsHnrk4yUoasNNMpxYXkgZ+lWRMHXaygj3FXYtFllAaOWNl+tWo9AueMhSPUGmkK6MKRgMgRge4FZs8jhsDOK7O48P4jzHL+8/umsiSzlhJWSPB9xTC9zItJJGYAda14ROQeQQetQGLDZ2BT6imvDIeRMUHtSGTTac7HcCoP1qNLO7J+4GAprajHB+7nuRuHtViHUYXwY7hPzosFyWF/L2rLbIcdyK1bO9tVbDxRkHqNorGvdVjjZEx5kjHACjNSi2lPzeQ2T6GjYNyzeafZz3HmQHy1PO0dqibTIZQwLLkDg9KZKHgXdMrIvXJFNExeFpYnDIvUjtT0Ay9Q00op2Dctc3d2mM5XGa6K+1YhnRXCbBktjP4VSvvEjS2726QROJV2mUoNw+lVG/Ql26nLvYnna2faohaSDsavqqRSjzZDuPQDiuqsbKO7t8uPlAzuVetaSqcpKhc4Qh1JHNSQuS2MV3F/o2n21obiW4CqOoI5rzvWr+OS7f7KpWIcAHr9aqEufYmceTc2oXiDbXZQ3XmrX9oWsEJO4M/OBXDteOSAOTUct0/etPZXM/anZf2jDd286ysoYrhVPIH0rn9PCtfIrEhc9utZKXDZ61espFVw7Yz2quTlRPPzM9BFyBEiyKG2jAz6VK0ELK0kXBcAkE9MVzv9rBrdEkVQyj7w71CdXQjCsQfT0rHkZtzog8Ss0dwhC4GMgjvWJJMJASeDW9cXC3UOG2ll/iNczclEkIXNb01pYwqb3KkzAMaEcMpB60y4XI4qsQV71vYwuSzQg9KrtAR34pfMOaVn4xmmiWRhdtSKxPSiPG7LVaRgB8q80MaRHECWwSc1Zl2onHX1qW1gEhLuQtFxCjHG7Iqb6l20KitxnNKrjNJMFXgHNRIjM2ApzVEE5OTSshxmpUgeNdzrirEa+ZwMVLdi1G5niPJxUohI7V0llp0RizKMtjPtVpbaAEAovtmsnWRqqByiqQfSrcThACcVe1NY1JKACsV5CW4q0+ZENcjNRb05wKm+1vjnpWNG+361KJs0OA1MtTzFs5NUZGHapCcjIp0FlPcZ8tDgdzVK0SXeRnuTmk5q6LKZnKmNsjqCKv2ukMcF8Y9qpziiFTkzIiiLdQaebZuSVwK6aKxjTAK0y4tQPuLnNR7Y19hoc39lJxgU9LHJ+Y/lW0bYgfMAKjKbTxT9oT7JIzxp4bo1RvaBeAM1pZIpjMT1pqTFyRMw2/qMU5YlB4FXSB3pmwVfMQ4pEIXjgU5UP0FTqinGaUonqaOYLEOPSkMfHWkkIX7uaj3k+tUiWyURKOpp4SMepqAMRyaN7HoKdibonYIOnFRgYOc00Ix6kClCYHLU0iWwLkVC8hp7qPWoyq1SIZE0gzTDJ6U5kyeKTYKtGbI2Oe1NzgcCpiophWrIZEc9zTT1qbavc5pMqOgqkSz1WPV7qRArzkqPTrWjBqKuoWXDj/AGhXARXrDgnFadrfLgc185KifRRq3PQIJoYyrCRVHYE1S1XxB5AjFrKS275jxjFco8ryZYPnPQVVkgndt3H51Maa6jlPsesafqtrc2sUjTR7mHPOOadqGq2tgitI24t0VSCTXj7G7iX7jEDuDUb3lxn94r/jVql5kOaPU7jxdZx25Yh9/ZOv61kf8JsS42QR8f3jmuBM5kHzZqFnUHgmqVLuT7TsejXXi+5miZYEjjDDtyay4fEWqrOCLiQYPGGNcel0ycBjirMepFf48/Wj2VilUTPT9N8TSLDm4bz5wQVLHA9810tl4gsZId867JT1X7wrxNdTOcqQDVmPWZFA+ao9m0VzRZ6frWtWTnFraB2J5YjbiuS8SayURRZxNGvdicmsMa5IeozVe9ujfJtPT2oUHfUfMraGbdarLJIS7kn3qS31JvUmqdxpU2dyHI+tNitZ42+ZDx6VvaNjG8k9TqtJuwkglcnIrdHiZ40KxsM9ia4LfIo9BVeSeTnDVm6d2ae0sdrf+IZJbXyHndkznBOazbXVnidhHIQpGCD0NcpJPLnuaas8oPQ4q1SViPa6nVXd+GG2VxzzgCp7C/09tsc6yIM4/d84965iG4ckZHPvWpZF2bd5WT7ColBJGkZNs2ZdMV9SMLzgqRujLDGV6109odLs1W3E10pKjMgY7SfTHpXCTzSpMJpN+R03U0apIxwc1m4ORamom74uljxHBADJGw3Bh7VxU8QVWLoVFb9vM8h3SAke9GoxwzxBfLJb2q6b5NCZx59TjJWUHIqBpQetb8miK+cFlqs2gtyQ5H1FdKqROV05GP5q56VLHchelXv7DweZR+VSf2dBCMsxaq54i5JIpC5ZzgZzTtsrYwCKtARD7iCpUmixhxSv2Dl7lEi4CkBuKoy7w3zZreaaGNTsUZqm0omY7sU1J9gcV3MZmdjjBqeCxeZgDnmtRLeEnJfj0q2sscKbUA4703PsSodzEn0toxkOPxqsLQ5wWFad1Izt7VAinnPeqUnbUTir6EIt1UdTmgDb0FSsCOlRMD3PFMRIJCO9OXLVXUEmrcCnvQwWoscILcryavRRIpBAGfWod2KcJDUO7LVkWJIhIAD0p1tEkL57jpioBIccU9JGzUu5d0bEE5b3Heq1zMBITnpVdZGAyDimspcH1PWoUdTRydijezGRiBWeyNnoa3YrJCctVxbdNu0DitFNR2MvZuW5zKRsxAwc1et9NmdgCpAPet5I1UD5Qce1S7sVLqvoUqK6lW10yKFBu+ZuuTWkoVRgDFV91J5hrJ3lubK0dizhO4FGB2qqZKa0p9aOUOZFhwPWq8jD1qJnPrULMatRJcx0rVA2Oc0Mc1GTWqiYuQNg03Yvf8qRiaaSfwq0iLjmjTOaaVXsKSkJqrEtihV70jY7UxmNMJqkiGwfHpURwKcxphFWkZthuHamlqUimkVViWw8yms5oP0pMZPAqkiGxhakzSQSxTlhFIrMvUDtVW6vkhiWZV3xFgucEE89Rxz/APWqrENlkk005qjJqInEaWccodmG9pIyuxfXnuccVINQiQf6SjwHOMNg8+hweD9cVV0S2WSTTGyOpAHvWdqOpRFFhgkUeYcM+4Davc5z17D8arJqoZxcuhWGP5BGGDcDjPqPy/GnzIk2SDSEVFb3Yu4fMgCJHnBeVsfp6+1XFUODtIPY4qkyTY3j0p6OOuKUW0v92lFtJ3Q14t0e1Zk0d0UHGamXUG6ZNVPs7js4pPJf3/EUrRKvJF77cxHWonmLcg1XMEuOmfpTSkgPKN+VCSC7Ffcx60xo2xnNSAP/AM82/KnhWHVD+Ip3sK1yqI5OwzTWVh1XFaSKPTBp/lF+MZo5yuQyD75FPU+rGr8tpL/DESPpVdrSXvC/5U+ZMnlaCOQA9c1aS529KqC0lxxG/wCVO+zSr/Aw+opOzKV0Xlvyo6E0Ne7u5FUtki9UOPpSfMeq1PKh8zLDXOeuCKZuifqoFReWW7U5bZj0p6BqTxrDkcCrsMVu4AK/lVOKzlY8Y/Op0tZR905PtUO3cuKfY3LCG1U5KKfqK2LZoUI2KoHsK5WK3u+CAR9Tir8CXC/fJH41hKN+pvGXkdGbWxuf+PiIOOuCak/szQ1iIW0KyY+8HyP1rCSSQDhqUTy5wTUcr7lXQt9YIrBYXGPpioo9Flf55J40H1qz5zH71NcMw4Y/lVXaFZFZ7J4h8rq3uTVGaCZgRk4HU1qi2kbBMgx71es0MLrwjj0YZo5rCsmci1pMVLgYA9az7m2myQSK9IubeKVFV0QD0AxWJqOlQsv7olW96uNXuRKkcO9pJ03gUg09iCWl/St2fSrgN8pUCqz6bcg4LD863VXzMXTfYymsR3laoWtVXo7ZrY/si4b7rGq8+m3MQJbBxVKou5DpvsZZicfdYmmtHKOSePerRgnB4FDxTAfNir5iOUpEN6mgBh3NWCje9KLd26A1XMLlKrZPc00IM96uNaSgdB+dReWy9QaakJxYxVwOBUicUgyPWnAE9j+VO4rC5zinDnFIqMexqVFPekMVFJq1EoA96iUcVOlSy0TKAetSKoFRrUi1DNESLxTgT0pgPNOBqSrkmaSkLqrBSyhj0BNLRYLhSGg+1J+NOwmxDTDTjSbSe1UkS2RsaglkWNGdzhByTjOKrx6rbTapNYRb5Joo/MfaOBzjH19qyrPXTc+ILmE4SxhhJDyfKGbj1rRRZjKaNaS5t0jDmVCp/unNYmq+JILW1aa3UT84UhsfmOtYus3wu3jhtoj84yjI2CB1OCOPTrzxXPGF49QUTx7iM/K4x24yO/8AWtYw7nPOq9kb2n393eztuLuIkztByoHX8+ep9Kvz6oyW/nzyfMJQqgcqAe/bP41jyXKWdj5djBh8kNkDJzxz3/yKzJUa5vFa6uEII3lgfvegq0kzPmaO10e9k1RX+aRIyxwV+8yjjOf4R+tbIUIoCjAHvmuV0TWLxnVI7eT7PkqFO52GPQdq6uMtLGGeJ4if4W60WNIu6IjTSTQ09vtlbz4sQgmTDD5Pr6VS/tWxNnJdCVjbpIIy4jYjdjNNITZbzSYpUkjdnVXXcoBYZ5UHkZ9KlVAy5Ugj1BzVE3IdtIV4JPQc1YK4FQywCQ/MJHVvlKqcACqSIbMXU9ahsmKeTK7ABi2MKB6+tY114kUyNHb3cojY/fMC/KPTr/8AXrSm0Rr26kiEYULkkq2QOPUjj8P/AK9Qt4SS0d3uL6G3iUbgxwSfXr/hTIZzH2yVnKLNMYwu1iGJ3KCcfQe1a9pqL4Tzt0EY+5KI1G33HfnBGKpTyRRQyRO8dxcowEcyjK7Ocg9s8jsfrVayvPsjS7Io3EqbGDrnAznj0pXJNPW7q21BhKiES4Vd3mbQPYLz+eayr2FrfYQ0n7wZO9dpPP1zj60S300twJWO1+F34xgfQdqj2xhw0wk8txkbW5+vNG4CiMfYhLlfvEY44NSWfmz/ALmIEsW3Od+BjoPyp6W863MjQSI8cZGXJyvbg8e/arGrQX0UH2qdrZRLhWETAHPYEDv/AJNFgNCS7htXaG7Y3bOQ6CL7iHvkHkn+lPPiRDJIIfItYU+6dhdpPw7fjXMQs7goWKhucE4BPvT7W8NvL5hhikf1kXOPwqk2HKe+KntUqxg9RzTQakVq8JnvJjxEuakECEdBTVbvmpFfipdy00KlrHngVMtsnoKar1Mre9S7jTQC2XPQU/7MmOVBpVb3qQGp1KuVX06F+dgH0p0WmxKemR71bBp6mi7BWI1tlHAp/wBnBHQVKpqQEVJdyuLVfQUjWat1UVcFOGKV2PQoCyjPG0flTG0q3frGv5VphaeqmjmYWRjjRoc8LVlNLtgAGt1b3rTVeamUDuaHJjSRmLpVt2gA/Gl/s2NOUXHsK11C8VLGo9KnmY7I597M90ZvwqM2pH/LJ66tIwRzUqwqe1HO0LlRxxt3H3IwPqKhaxuGbKxZ+ld2tsp6YqRbVaftWHKjhY9Mu26xkVYGk3Y6YP413EdqB0FSi1HpSdSQcqODOk3p/gB/4FQ1jfwfeif22813wtR3P5UosoycnJ+ppe0kHLE4Dyrtv+WUpP8Aumgafeuci2lz7qa9GWJE9KlSMH1NPnYvdR5t/Z2oZGbSQ+22nnR751/5B7D32816V5QHUUx/QLS52F0eWXGnXMTeW1u6k/w4qKTS5ghL28ijGeV7V6r5CswZkBI6E9qZPY2twpWeENmj2jH7p4vPpiO2UcD8KqSaUvJLk/hXt8el6dDgraR59dtQXdhp8+PMghO3oCOlX7dxJ9nGR4c9gqngH8qja2I6A/lXrE3hrTHYk+cDnJ2v/wDWqnN4b0zoonH/AG0/+tVLFoPqzex5Y8J9/wAqhaDvivSb3w1p6YK3Eyjv0Nc/qGj20IZkuXYdhtraGJjIzlhpLU5Qp7U0rWq1lknDYHvVaSAoSDXSppnPKDRS2mjbVgpR5dXczaIVWp0WlWOkuBOkJa2RHkHO1225/HBoDYlVc0SyJbhTKdqscbj0GBnmuFl8V3kGVuUkVkOGGxCr84K4x0685qj/AMJdI1jDA1rbyTRDHnvlnbk/0OKv2UjF4mKPQdRe4gxLEVWJVBdmBYdfQc/rXN3Xi5rZpraeOMXQbAC5AwffqCBzXG3Ou3LXTzxSGCR2DYiJUA/nWbNOZD83LDueTWkaPcxniW/hPRofFdlFKDBmSRid7yIQWAHA6E5J6Y9K0rDVbub/AEi+ns7dDwsanKrz/GxIweK8uisWlWM+eA7kcNkAD3P6V0uj+HrkSiC4sormItuco6nj0Bz0+nr3pypxQ4Vptno9rdQXa5gljkI/uMD+I9qnKmqGnabp+jgRxCOGSQbtrOBn3xx2703Ude0ywkEd1eRrIedi/OR9QM4/Gue2uh181l7xelOyJ3Cs+1S21ep46CvPrzxD9u1VJtJmlivInYLFJ/q5EA/iH97735V6LZzQ3MImt5o5Yv76NkVx/inwxbaljUtFmi81iQ8aHiRh2GOh4NaU7X1Mq12vdMrwdZ3/APwkF9O9u32qGEkxytjczcjc2Oh6/lXM39veX2rXpuhHaSbt0iFsAcZ49fWu91S6Y2lvq9vMVE6NFdwsuT5avwGPUEMQpPX5qNSLf2NfWlyInk8wtNISFMsrKGCAHkBV+93woHetk7O5zuOljhYtRujcxtbRFYIY9nlhztIA7nPQntUM91JNlpGbzdoU5J/zipLqVXiiVn2JGuAIhj/PP86zXUeSz7zuHHPWr3MGyQNhjsIx6jrVnT4Y5bhPtMjrtI2sCBj6ZHWqqbdq/vF64wPSus0vw+2qQtNp8YgAHAaTcX7Y/P8AyKNgSubmjafYrbQ7LuUzy5OBJtJPfheKt6xdnSbDfbQiaSPBEPJJQfePHT6mpdO0e30Oymv5kESRw5KsWB49f0HSvLtR1K4m1OW8W6m8xznIJXaM5C/Qf0otc1cuVWLDaxcvJdTRBE+0H5l68e2aqxXdzbwukM0kSSY3FGxn6jvUEEE1w25t2DzkjJNacFtGnBTevdmXPND0MlCUikt3IEkUXMpWQhnBYneR0zXReFbqB79pRZ+bduwWGC1BUDj5mIJxis4/ZwmBFGCMncAMD9Ki+0ER7IpmC5A44XPsB1NCZfs7dT0m7uLe1QvczxRqBk7mA/Sq1hq1hfymKzuFklAyFwRn6ZHNebskiylmjZT13yLyfoO1VVQs7MjOsiNw4bn61akJo9M1FNWktnNq/kKvzERqu9h+PQ+lchrF1H9ijD2SySPkm4mz5hPTJHbp6mrei+LbqyCwaqpng6ecBl1Hv60niq9tdTC3cFwroq4GVwwOe46A/wAsd6H5EM5f5du5R17EU3zO6qgP949vamM5Y/IM/hmkZHABZWXjjI60rCJQQyneyk9ABnmmSrsx1FMMcgGdrADjoRir9ppssyRkAtJMDsX0A6sfYf1p2Aqq8hh2qzYXPGeBVnZZppu+MyG7zh92MYPoPz5p9vZB7pLcSCSQFt6bgAcHoD610a6fBpb+bPDDcqeDC68jBGMcZJ6e3WmhN2Dw/pcV/aw3UMR+1Ky/cYkKoPVmJxnAIx9K1L/wurXElwoBGSwCAAqfpj5vpVN47KWXfa6bJYSDPJnaAsAOo7fXvxWzBK2k2UhuNVFxtP8Ay0zIc+g6E1asTqdcGqQNWONf0ny/M+2IFxu5BziorXxPotwrNHqEagHH7wFfx5rxXTl2PaVWPc6BWwOaer5rivF+tF9NQ6Dq8CTI58xUcBmXHYketcfp/iXW01OBp9TkaNGywd/kI9Dx/StI4aUlciWJjF2PaVapVkrlNM8YaTdWccl3eQ2lwR88TFiFPscc1aj8U6GwO3U4SFIBO1sfXp096xdKXY1VaPc6ZZKlEnPWuYHinRA4X+04eRnOGx+eK5/X/HxtL0waTBb3MactM7kq/H8IFKNCcnZIcsRCKu2elCQU8SivJ/D3j6dNQKa7KrWsoyrxxjMRz3x1X8zXXXXjDQ7dGK6gk7BdwSFSxb2zjAP1olh5xdrBDEwkr3OtEtSrKK42LxpoLBQb4oWAOGibj2Jx2px8a6ABkaipPYeWwJ/MVn7CfY0VeHc7NZcU8S1xEfjnRGGTNOq5ILGI4GKWPx54faAyi8l4z8nkNuOP057Uewn2H9Yp9zuRMB3p4mFeYyfE3T1ZfLsLt1Oc/OgI59PpVqP4k6LuHmxX8a8ZPlq2D+Df5xQ8NU7CWKpdz0YSipFm+leTp8UoDbzt/Zsnngnyl80bSM/xHqD9AauR/FDTCq5sr3dsBbGzAbuBz096HhavYaxdLueorPxUyT4715Fe/FS0R410/T55wRlzM4j2n0GM5+tXNN+KOkSQE6olzYyqOir5qsfYjBH41LwtW17DWLpN2uesJce9TpOp6mvLR8TNBMPmI9443YIEIGB69f061V074saTcardW8sNzHap/qJ1XcZB3yv8PtUrDVX9kr61S/mPZEnTHWpknHtXlg+JXh8HH2i7z6fZz/jTh8TfD4HNxdj625/xqfq9T+Uf1in/ADI9VFz6sKeLle7V5VD8T/DjruF5cA45X7OxI/KmSfFXQEB2G9kbGdohC/qTR9Xq/wArD29L+ZHra3SDvS/a1PfNeS/8LS0DaSr3ZYKDt8oA59OvapG+KPhwKMXsxP8AEBA3y/X/AOt6Uewq/wArD21L+ZHq4u0HTFB1DHQ15VP8TvDcKo39ovJuPSOByR7nIFUD8XNDaBnjjvncNgIYwCR/eznH4daFh6r2iwdakt5I9hOotnrQNQOeteTD4qeHhFC01zcRNJjKtAx2E9cnpx6ir6fELw40ZkXWbYqOejZ/LFJ0Kq3ixqrSe0kemrqHrT/7RQDpXlUfxJ8OyIrLqRKn/pi/H6VDdfEzQYondbqaXapYBIWGSO3OOaPYVf5WHtaP8yPWG1FT1AqF7xGPIFePQfFnR5LGK4eC+RmOChC/L77s4NPh+K+kOvzwXqNjkAI2PxzTeFrP7ILE0V9o9ca6iA7CqNzfwoD90/hXktz8W9KEqIlpesjZwxKLzn69PeoLr4l6YThbe7bnn5kH9aSwVV/ZH9cor7R6FqWoxvnG2ucuZFdjgCuUf4haXIm4W9zjudyf40xfG1jIisllcMG54da6KeEnHoZzxtN9TopCACBVKYhm4rzL/hPNVie8EjQzSO37oFRti55x6jHHP1rd07xtb3ECiW3ZpwBu2MAD74PSupYecTl+twlodSV61S1G/tdNSNryQp5jYUBSxJ/Cufu/HcMNwI47EsAQGzJyP0rlfG2oSX+rCSN5lgKALGzcJ9MVrClJv3jGpiIpe6eoafdwX9qtxaPviYkA4x0pl/Zy3sToHliiXqIx8z/T8a4bwhr9npNtNEbSUs+GZg45Iz61tX3jeMWzfZLYpJkYaR8jHcYH86bpyT0Eq8XH3mcv4jhuLaeOxlaPAIKRKSWIbJyeMdSelYF1bSRSuojKAfwlgcfXFX7+++038lyhkVXJIjeQvtz1GTyRUUEpLP5mCG4JAwBXRG6Rwyab0KItzj9716kDrinq6AfuSAT/AA9/zrTTSZ7qXPnxQwtwATkkewpz6Np0akfb3MvTJTAHv7/pT5kNU2dB4G/s8F7vVE2xxkBcLztA5IPfnnA+bPStDXfGNvbwvb+HbdrSEA/v5fvAf7CE/L+P5Vxkn2cWYshLLLdowJcHCL7D1pyaUu0NI7OqgkAngVm0r3ZvGUlGyKUt3NdTSNHukkY/NNIdxP4mlW04HmHcfQDAq3Eiqm0AD6UkpESF3J2r1OM1d+xFurI7S8v9KuGn025kidvvDOQ3sQeD+Na/h7XLV7tbfU2lsI5JN7yWx2KWx1b0HuOgJrLSNWjBXJDDIJqewtI59Rt0eNJFLY2ucKeD19qHbqNJ30O61+G18N6de3UCPNY6hbNGCXMoWZhkNk9nHJPqo9a4v7bLelDtKWUcflQwOcnaTksx7sTyT/QVd12G+bSLTT5L23W1tjlYFJ2kckc45PX86y4JDLCG4Un07VC2KlqyBYVjuyrZMTAklcMQPpUVtbb2knZCYoZAudh289z6dq30t4U8NC5MYWWNXKMfvYz3+tXLPSli0YxB3SWWP97Ircktyf8ACrTI5TICK671tymP93n17VPY3F1YTxTac7xzRnkMMAr6EcZFYGr+fp+oPbxXE2FA6ufSrFpbyyI+69nV1JGASafL1DnXY9C1bUk8SaIqxXItSMLc2vHmMcjABJxtPr+fSuAvdMm0nU3s7uzmNzHgsvysBkZGCMg8HrVqBpNKiDMbqW8cdQQAi56ZOef/ANVSx6lqE8Fy1xHHLJIWO64mJcgjp70r9gtd6mbI1xsY/Z3RByS0gUD9KlhS6aEPFAhVvusHzn9MVo390s+gizjtdk4AB2vkEA1o2Hkx+FrS3EiJdAEuCcbfmJqHJ22NFHXc56Wzu3j84xiKOP5m3Nu6e3Aqi0ii688ON+7IOOtdrqzxp4bneN1chRGzKc4JIzXJQkFTIrfOGATI4GepwR0x0pwba1JmrMh8zzC48wkM24nOefYGkCEkk5JI7AdPWnFkMjB345KkKPXue34UsD7mOyTyzkgMBg/iRVmYsq7doAB4w3I71CkKB0ZZkiUnndjBqZkebcFLZUAgY7fXPFRXsUaxIBukYjk8YH0oQF9JYVUD7VGB3w+Kh1F4yhUq2zHDuxPze1Z1vbJIxab5FHUDjNbb3CSqqpsK+4/KhqzK5rozCWW0MuSC6ev3ieKl0q1e6dI/mVCPmIOGYDt7CmxmN47fzIwwjUpj196tLNEtxHJEpVl6cEZoZPUs3umtDLG9uqrLGxKbeMbT3xUWq61Jcm23FxJGCVLAbgfcjr+NQyahK8hCt1Yn9az7sebcyOSPT60Rv1FJJ7GqNcvLkkOWcKpVVUcKD1NZ891dNEolZ8RgINx5Hp71HATHIShPpmm3TRGTKjj+dURyls6ewQjd+n/16hfT3UYUkkfT/GtA2o2kx73dfvAYOFz1pTDgEYOF4OexrLnNeQz/ALHvI2jYB1yw/wAaU2UwYbZkA93HFaCRLtzg5XHIxjNSNbMFZgvzqRvGORnpxR7QPZmU1i7Fd8qsM87WGcfnUptNse0Stx7ir8tuMtGvzP1GePyp/kuQhICKBxyTnH+cYpe0H7MyhA3lAGQgeuKZJa7APKXcPTPNbAt2aUxuxHGc4x70mFbeFbaykZyOG9OtHtA9mZEcTgHMPH+9SlGHzGJx6gHmtsxKdh3gSFTyRwB70nkkqmMMWG75e/8AjR7QPZGMVBOTFLkcY3c0+S2E6qcuoHPAzzWpEiyRswDM2cNkChoQxGCQhG4fSj2gKmUfLkZNp3sBw3ydfrTfJcD5Y3VSOdq9a0VJG5Gf5eFOeM0rIVlxwrdi3ap52P2aMVLfbP5jiQntkYxVsqxXPltjsRWlFEFt5ZA6HJAGDnkmm+U5J3bVVRjIOePSm6gezMxEKcCA49yaUwOz7troeuAT/hWmWwg2Y2kEg+1MEm2NEJfpgrjp+NLnYezRny27zbQSV7jaOv6UjWSsAZFeTA681pbyJQ3O7b8oZSDn0oFwfLfZkAHj8/1o52P2aKaW4iTbGronXoTSLaYcvHEdx/i2mtK6fbMQhaSJjtyVAOSP0FLcSPFbb0VsNkZByB/nH60udj9mjNFnuJMm/JHJwRUn2QiMID8vvU8bthipAZSpGRnjvnH16061juJHO4KyEnOBj6U+dhyIqJYPGD5W1SepHenCyQFmcxsT13GrirKZMKckghcYqLeSzKxUIFyeP0pc7DkRGbeMJ8yx49ASaFsISpODhgCQMnipxHJJlIkyE5zjjb/9apPmdikYxkfPz1o52PlRSGn25IUs5A7EninDTbYnOEPH8QJ/rVhVU7t5XJb7oJJwByT6U5kZmUBGdJACCMjB7DmlzsORdiq+mW7MN5D4GOjcfrSHS7faTtGO4VT/ADzVtwySlI9oPQ9P5n86aX2yskqnaBtKgHk+9HPIOVEK6fZouDuHcgqf8aX+z4D8pzs91P8AjVyBPM3yITwANrY5B7D396V1ZEQupfdnIUcj0/WlzsfIuxR/s6zVSuWA4JAXP9aPsNpkANK3/AQO/wBavZyw3bVHXpke1RIpETSAAR5wzcdaOd9w5F2K76faPy8k4A9hTU0yzx8rXDZ6jirkSedk+WwVTkBjj3/SpxbSo7zCPdj5lCkd+w9aHNrqPkXYzzpdpkArckgdARzTEhtHcmJrrIwPlNaUsnlxu06uhGOo6Dt9DUdpAN0smyQBj1IHQnr9OKOd9WJwXRFQWFg7FGS4OMZNIdP0+HJjM4yMZJ61pw5KNtdfN3ZLY4HqP6U37PFfJIoJ2r0KdSckYo533H7NdjPjsbOXBfzSOxPFXPsenhAkvm4P8O4mnW2jRXMShpJB2xvPOD61ImnwxKuFVkH8RlOf5U732YlFLoQtaaZt2+Q20jPJwaRYtJVTvilZR2Jan3Gny4DQwkKOvzE5qlc20rhld3GepQYppN9RNLsYWovEb2Q24ZUzgZ60qfLbFlLEt8uK01sYhCqrEpkXjc7kD/69TR6Q7zMZZkI4wkIJPI9+n1rbmSMfZsqfb5CyyuAI8cj+RqoL1ySm1mycYFdInh5pNoICqR913GTir8PhwhSHSJ0bkAzKv8hUc8Ua8kmceTIZVIi2hTngc8itW2uA9nK4DFFGCccDPTNTarbWtpeHKeawBR4ULbWPs/HPsK6K5htNKsIbG3VY57g7nCAsVXuvPqePwpSaY4po40EbcjpW9Y+FTfRadJf3kdrb3wLRhfmfGQAWB4AOeOp6dKtXMFrbm3LXAcOwIgOMMDxj+v4VswrZa/r7WioIrWxiiMCI3P3QDu/ED/JqosJRtuYfibwZceH7cXMV3FeWCsE8wZWRPTev6ZBIrmiQ23GGzg4z1Fen+IL22ma902+kVHntz5SM2N7hshR75AFcbpe46mmjLpkJjdir5csVLDJUHAx+HShkox5op2FrNItxHG6EwNICQyZOSPUZphs7+JiwhyuflCkHd9K9h1JtLttPtNMaGCUmQHfIm7yhnGVB6Z9PSm6tLYaewM0sT2bOgeHy1dTltoH65z1GKnmK5TyS5uL5dKaB7WQRyyDLEeuMD8cVoJe6ysQRrNRjuZFH9a3Ne0awluYdk0/2fduTywA2QxBB+hBq9Z2VgIwFgnkPq0oLflQ6iSGqbbOC1HRdUvb5rp4U+YjIEq9uPWporW8tbvfeRGG2QFxuYEM3YZFdnqEMFvGWg0+7kk6DcRt/QZrmdfa71BIkSyMFsnIRUO4n3JoU3LQTpqOpzJk82WRz8pY8kH1pwyMYIA7+/vW19la3jE0UDM5wpDR469Se35VC0lwQuIt5ORjZ/PjiruRYx2I5GefpUZzuyRjNbrm4ZNogdTwOEzj6Uhlu2lLi3lkyNuJBjI+nSndBYdp0ksvh+7soV3O8qsoHpxnj8KrjSr/ywv2N1bcMuSM8exNWrRnhkLCMpIT3THH1HFdJaXHmwEOqwtjls5zWbk47FKKluci+lXw5W3Ykjkkg5PvVaW1u484hZWz04rqJRMsjJ9pV1PRgelZd7YeacoWJzyeMmmp9xOBkQwTRIXlgl8tuAdvU0l0yq5SJGYf7Qw2Kv3UV/sRUikPljaGOTx6VURLuDzt1s5LLgEDgVadyGrFbzkXGRgd8jrRJcSCYHbgdQOmAfat3V3t7jTbSytYpFeMRq0hU4wM7uvfJ/GsfVrJTeFrZpZI2GSzrgqfSnFpikminJIdwJY5JzgUx7iTcduAPSnLaygnzAR74JqeOxkmnUQwyyDjLHgfrV6EakM0siBDkbiOo7VCXZsEkMavR2bkzLcRSA8lSELfNn27UsmkkRo8cyPuHQdqLodmVI2GPmwMcZpCyBgEGcck1K1jJjhW46jFNMGYuVfzB1yOMUaC1N+6WKGKAxIySBmInZSAxP8Jq1FcK0ojmjHl7DtwRnd7Htz+hqvNdIyBAzxASbiXwQcdvfnNQyySCeOMplwhcsjgZB7iuW1ze9mW2gWPytxC7pgAVOQ3Htzxj0qQShW3ADIOW7HPofcVnxXTtcrHE8oiVlMjsQrHHOcdj15qzqMscl00kAkzCmzbJ83B6An6Hr3pNdxp32FjV55FUxA5JZUbgsOuB0qzHC0zCESoNnOWOBk9AD61Z1IST7ZILYI24BYWYABQM4+uB+YrIBaazgELAyYfKRKQckk5Pqcf0pLVFbF2SMC4lgYqexlHKn3/mKhBQIYflaKMD5hgFeM9T1FTK81oVlidIt4CFORg45z1Hr1qobdUQ3bjbG3y4PKiTB4Y9unH1oQmS2YjSZMzYct8rg/K3HI+vt3qRoWgMRjKshbDRlwgUdcDPeqcUi/Z5UuIzFPIAEUqRht2dw9+gz71PIlze7reZB5ojyy5GeD97P1zTtqCehctoIrm15fOCWyOMgcg56ZGOtJJErKMq8UhUSHPIcAdNvbnn05pl7aiBEiicCVSM/wAIlBxhiOg9DVeaRy3lwFkwFjRCQeRkuAf89qmxV7Ed4RJETGCgON2R04zj/PapESKWyMasUdTlj13Ke+PY4qSe3vYkurcsywSbCGYAgn0J7c5qbT7C3v8AT7iVZ3W74UbCFTIGckdTwPwpt2QrXZnxgxgQoWldm3FAvPtVmdHtJpIpQJo2ULn+8RyMehHSnX9zC0TgWzBrY/NuBywyMMfTPOfqKlvZgLqBISJbYEOZFjP7xiOhHbHTH40agrCtbJeSyTkrbZ4CY4A7YqNbePz3D78jlXVTtwB6/pRc3HklFntmtklOY1HOCehOef8AGru1bSO63llhiPl7cE7mPOdw6AYwB3FTqVoUfKeSKSRHPlLJueIv8zjsRTIMyNKLsncW3Fem4c8j9KuwpEkgaMrJLdI+GwGETYGCV685x+tM03y/s9w99AjyIV3Rk/U5HtjB/Cm3oFtRkS75m82PCRhXYZ4cZCnB9eRVO7GRGYWYKuY0QjO7POO3H+FW9Rxb3kCxSq6mRJFkwSrDquR09B+FTWJdE8x44ZJ5JdoieMBVbklRzx+XoKFpqG+hEFD3NpFKgh835WkbAHbkn0B6jtzSzR7I7eOQqVRyGZOGOSM5PqOtJC6m8ktblZWdWHlIqlywIyVx+matWpR7Ysi4jkGQp/2Scrj1GDSeg1qRTKEljVWRPMdsbgSw6kD9KiumMtuJY487B045PfBGccZ49sip3iafyDHHjzi6KysM4AznjuCB+dI0cMv2q7DIuZQu0jHy44P40vMGUlFysMTvK0SNkshGc4I54/3v0pyXIA2xREh8FmVjj1H16/nV3R5HvLNY440Z2Pl/LgsrZ3Ar6dR7GpNWW7SJJpom8wv1Azk9z6ckfSnfWwW0uZSyKjCNnSNGYnLEdT047896nDtb25aV97II0x90ou7qfcHbVi5hgttWhV2822kTMqSAfLwcg564/wA9KjZWuSSYVSMFoiwXhx/ex26fmKd0JKwQ2ktvM0cvmI0pDs5Gcgn+fNWr1trNCg86TzMs5G0Kuck+2MYzTmtbqYyyxqWCEKyl/mQkbs9cEEDr7VE9q4hRURpVkyiyKc7ie+Ooxg/lUX1KtZFSTeYbcPGqytuYupDA49MdMio0k8gNFGTIc545B74/WtWAmC+i+zCSHyFPllhkjPGDkdPf3xVbTrUtFEJpMSA5kiKg9TkkkHPQj86dwsVoZ3jg+SIuVDfLuBypHA9Mjk/SpNQbfaiWMAKMLsA/DmrUVpHPFNFbRvNIrhn2LkqvTjHHHXngjPfFTSQ2m/aUWRD5LKzPt844+br2JI/KhtXuFnsZVg0k9rjyxI6DenHI6A9PxNXY7RfNMreYXcglgcED0A9uhq5LHN55uZgkTupV41GS3AwD26Y6Vi+YTKxYrGRygLgc4BH4UX5gtykky7BLG84KTNk5XkEA4HNOs5L0xI8CRSoF2bT1APQ57DtTbHjVVW+jEg8osFbqfofccU/7darbi2ilKzJlcg4CZOSqnv6c8emafkJdyNxGLhlhQpGwB2gkjPoDVxzIlsLlIRGztl1K8qvcjp1I6n61nrcobh1tppG81lCkr8+M8gY/AcVp3KR2qhjuldMrLtlJULgngdyMEdxSeg0Sb1UOInMYcI4wPujbnJ/z2qSaBor392pWKRRtJJIYjueOKogLL5VpH5q3kk4WSdsEJGANqr23Ekc+9aM1ws7tbxSSASopUORyRz1wOOPx5qdhrUWP9xG7XDq6qA4CnO1TwBj1z/OrqyCRQUAYHptjrOeaCY7JIWVgu/fu+84fsPXOParsKPHYmSR2tniG3YU3c4z17cfzp37jsPhUyqGSKB1P8TgKakVrbcVaW0Rzxw+6pLXaAltIwc7TvJGAv1H1plu0QupLTTkjQwoshAQAYbPQ/wCetO9wtYf9glcgCaAJ228/rUf2e1gbE9xlsdetOmlukfbK5CfxAAdKn03T7a/02GeI+Q0w3eW3Y5PpRfuFr7GD4le1kl0yCFjJI04JjIP3TxnmnXNjc3d/PcLhchlRs/dPQH/PrXQf2BJC28szD1yWzXKXNprV1qOotZk28Fo5Zlc5+ZRuAA9xjnpVp3VkS1bVkWp2Qil0+Fl2gMoU9c4Vsn881p6NqdlpWrpDc3EMUsKujGQ4JDnccn8qff2K3Frp+qOWUo6EIeQ28gEn6bq4zxnbSp4j1Fpoyu92eMkYDKOMj24rWn72hjV93U7TxFJaajrGl31tcQyJHdRRtIjBgN2ev5Co7a3msdburtLYpbxl2jZmyctjLflmsnwbahdNSK9tZgPPW8RyvysAuF578knFdhNcRvazKHEhY5QttUA45xjH0qJys7IuEbq5kS3UjTG5AEjEsEG7gNjg471n3UzJo8EEx2tPPGdxHU7wT+QFZs2ianHpsNxNchcyJ5cQ+YlWI5z2Iz0rodS02OW2864Vz9mRpIcNjJA5JHf6U9ELVmvdTG3NonlK4MW9y7bTuYlj/Osu6vdR3l4obIIMbVGScZ7k962bmMXknm2xV4yiMkijPAUEZ9u1VxFHMHXADhhtRiT8vrx+n0rLS5rrYzBqmp+YquYFJ44bGPwp4vtQQ5e4gwO5TdxVySCCJ5Dbb5IgNykjJfj1PHFTGySWNWESgAnK5HAxzn+lPQVmZ6ajebzta1ZFPGYyMj19v1qNtT1IY2PZrx0MZP8AM1clsVtolYSRtG/KgsBlR71WRYHfYUkKEcSOnyAehOfr/jRoDuRS3mpOB+/tY/YIKryXd6TzJbL2/wBV1/Wr0lmjOrQb5GYH5RKPXqM+1PktUV40klQg53nByoHbGP1p3Qncx2W7cDddQqx4/wBWMmmPHcAhDcpknAIjHPqT7VsrbRMTi143lVLkfMPWq8djDM0vlhMxttyQ27Poc07oXKZUtlcRy8ag20k5VUwMfWopLe6Mof7e5bGDlcVrw2IZZQYj8rbcHOD+nA/OlaKJZFX7O+HOEXIyx7kc4x3p8wuUyXgunVd2oSrtHOFwTzTWt52x/wATFhwep5/KtaRFRYztkUM2CXIBHtx6+1FykAij8siKNm9D+dFxWMeO1kJG+9ZgcEFk4/OnGzKvuMzt/unGa05IoS+5RtBACydm4z+VO8jZEDlY2AySRwDTuHKZT2yBgGnl2ryecg1FJaxu2ZJJc+natcx8gvJGRjdnbj+dMjIlj3eVlWG7dHyPz/rRcVjKTSrbAyxxyRk8n6U1NJtQT8zkjnrj8q0pEjT52XH8O7vn8KbJGoBCFt3HLH759OOlHMxcqKi6fCiqSZAG6EvyPwpn2G2QqozuOT15rSj2s7NKoG3hPmzz9KjmXa5ZlAjbAGQMD3z19qdwsjFneD7LLEzu5jG5DtOOew+hq/Yrp0iWTzho82/zOmOoO0YHdiafpMFs/mGdZ02YWQxsNyoT85TPQ9OvYmoNQCtI9npSzyxR7WjSUKHHPXjgr2qNHog8ytfBLeK1vI2IjZyjKwG5cHv69Kl1ORjYi8tZw5aYAgJwygd6t6O8DNqS6pbMzqF2Bxkrwc8dwfz9DVPR3UXc0ECtGWjd41B3BiM9M+xxR+gW/EekyyPbvCCoXL7CxwzDGf0zU+p+ULiS3EZWHOEkZ8ZYjOQQMjr70lrHaXejQutw0Vwkrkqw4yeg45x780y/hc7VeMJK3zfMwKlAuCfpml1Ktcgszdrp7vdxNNCrmMsT8ysP6fWrMY+0/ablY1ntAoSe3V8OCvRtvp7j0rLe6WOaKJEd4QwcoxJ3Z4P4VvXHh2S1tLC/gRDBeHaqwzg7xtO4cZ2n86p2Wr6kK+yM3T55N8McnlzSwtkCZjtYcHB9D71N4o1Fk1YSKCIhbsikEHkn1xzzikSG2e9tC8TCMKVYO29X9ASMY5wKW+srq8urWK2A+0CMYgzgqTzgDuPaldc2o9bWRO5uNSmt7aPELBJH8xR98BckegJx29al0+SCfSIbhmQJC2+QIvzKPu4/EE8irF066bpgtYUEl/bIn2lO0bFjuGf7w4B9M47VVstQNvp6sgAtp4jFMv8AdO48D65FQ9UWtGamu2SLpsZE2+8TeAkYDJJGrfKxPXJ5as+y0mZNIeSAxt8mGcHcY2P3gR1H19KNJk8mOEgjeCQuD0G0ilMWp3Uu1rpNpB3wylVYfTHXt1qddinbdlK+Nw9mYndghVFdUblwpyMZqa9SNLS2S3VQvlrMzngjcT8pGecdcj1qhq9reNdQQzRtHPIhKs42hyM4GenStLxVGjW8DpAIrfyIQME4BC4HHb0zV9kR3ZesrWKeyW8VH8iJQUDYbeV9fTkZxWbBcNahkuTHLHPkPsk3Bhz94Dp26elWbOd9NNo9qIluYiinGWwSDxj9c1Sv7fzJVIKyokhl2HIGCfmBI6A0ktbFN6XJ59Ot7WSNzcM/2pA8DQ8BipGVPcHFJvli+2SWqqy+WftRPPlcHDfrj8afpdob64isomVIRdiW3kYllRf40LfQAj3HvVi4gbT5buGZzNuZYnVX2jHX5j1PPWi9tw32M/Qnji06Y3QcFbbMeO/zNjHpg4PHvUl/Eq3H2q6uZREyo6y4J2bhkAfmfyqzqkzz3a2+P3ar5sUbDDIFGeg9RVm9hjGnQpG0k1sZd8UjKOVC52k+vJ68cUnLW/cajpYo3lrJCVd9rzRYO9MklD8ysPUHJHtWVDeujXDSviNnLEKcEEjH9c10Oi3c32oLImYohnPGQo5I59Dxjqa5+50sGWN0/deXEJZFlfBkBkP3B6AEflmqj2Ypd0bumW4tYb6OWBZLuKEXKRvnAYEZ2gdTgn2yMVQvp0sbiWCTc9yAFnHBRGxgRgdyPXsenStCO+mbxELqM8TL5Q9VToMfQdfes3UdXfUtSKyQuIPMOyNmOfc+oz1IHHPFJJ3CTSRG8kSlri3kMJ+VlRRsJ2n5cgcD8OtSzpc6kfKaaEL5y8gkAg5GSM8YP50+9vLnUbmATDylSQiYjHyjO1VGevHA+vtVkGX7PMtvHb2lpBkzLtAVDnaNzEZJJ/PsBQ216gtSG7l+y3UQuJUuLd4h5bhSDkN8w574Y0NJDtnhVtjlPmYszAAn+ED0PTnuavgNOqWpKqSNuSF25wMEHsvPX3pi6TcLqGn/AGaRd04WGVh86hsZT2IBGM1N11Ks+gzSdQae382UKq7drBB8wC8A/h1Ge/FMsob3TdPnuJZmdFjeNDHyNpzz9GHINWNbeKOH7VGYwhQGRY+mOclfUA5+nTsKq6NN9utYrSyWSQG581i+cJGF5ZuMYHOKLaXWw+tjO08StC4uEkUTxb4pM8EDg4H05/Cte2QXjmO3PmywJl41AU7SwGQDgHBIz0p9yZJlVoFnNr9q2M64C71HGAOo2tzWbpc6tPIFiMhT5EQHGd3AUjuDTfvaiXu6Gnpvm2iazAZUaVf3gx90fKQCDnH4VTIWJxE8kZuF2o+DxkDg9f8A9VaJmjgJ2bV2EI8kSDBYg9OOg6ZPXrVDWXHlzO6I+xV46/KR0/A85HqRUrVja0Kx1BDaSCLIKtuDr1AB4I9RkfzqS+Wdo0kVImU4j8uMbmQHO0Nj1zgdxWLHMrzRSxbVCKyFD6Hn+fNdB4VilltI5Xn8zrhCo+QAk/qeTWkoqKuQnzaFO4knttJhKlIy4Jweij+8fXtWno9ov9mWk6ybLaOQLJCeJAe0hx0yeP0qpqVv/a13bxWzO+wLPtAAV0cg5GOnTpjNXbG4+y6ncxxXNs94f3flNID8oOeexPtUv4bFL4ipqCxvctJZoIJRETG+ATnucjgdM/j2qKyilYRwuMuVDdRzlTwT9GFT7LN57m0mkeBi5MUjYKgnpuHUdfvfoRVKO9MGozwwoECPhiThuPT0I/rTs7WFdXN3S4f+JnLcbVWe3UZib7u7t659PxrK1SSeIB7cu0ZbCR5yRk42MR3HPTt+NTWP7vVLgEMAwSQKOcMSQR9M56e1bek6Zps2oWNpb2ckMrROlypYs8kkYLNjnC5wFyMdai/K9S9zKsZrRY4oZklluGYmRo8FUPTG3qRyOlW9Qn+yRyQybfNmuJCz4J2qOO3U/XjiqsYuYbiW5srcteMRsMbbvJjyM7OpyQcZGcfUmku703Xm740M8m6SCflZIXQ4x7qR1HuDRbUL6GrbPZy2sVzb/vXIEbkNlSxLDjI9APxqo00cV8Zo5Iv3kSKpWQkMMnof89Kp2U5ttPvIruG1EyvsXsdpAIPuQTwevNbNp9mntrkrchJEtmIYrjawXIxwD680fCx7ktveyFXF2okBQ44wVBHHNSW93p1nbQwgzQsFA5G4Z7niq2qRtbO0t8yxTmISMsfzb8rkEEYGCCD+dU0uSIoLeDTYpbl2IErRbpHyflHJweO460J3G9DrLWaURhoJBJB2KNmsq5jlWLX5FAJnYfebGPkAJ/L+VVLVL1d/9mR/aiilyiJh2HTKgfex+eOcVkTPqiwanghZ7l2YK2V2EjBHNVFEykXvE1jfXn2i00/ZEqva+Tk45w2c/iFP4Vm/EyynP9k3DRlZZYzbugOcOcHGR7k/lUcmr6h9stVhRnMEkSSuRkNtU5P5k1c16TU9SSzEEBURTCf33Dp/WtY3i0ZStJM6qHSvs1nbRiRX8mJY8E8ZAAqhc6fLJ5hkto0EYJVsA7hjk+1B1i8AJaE5/u5Gap6hqV9cWM0EQEbSKV8zaTtzx2rNJ3NW1Yk/smUwWchwd4j9eSFOPyqjeQ3SyTWrufIgt8/vMMWLA9SehAHUVFLPfDTLO3gRHkgaPczNgYTvTrrWpprHWJ4o5EYL5abl5IAPOCPUniqSZDaMyJ9Y0e1htnQ3dvGvyNE+wrxnBz1Ayauw3YjC3V3PtRwAYSgOz2DDH581asTNd2VvK5dZfKXcWXHOBmq15C8jqoEJcr95gMgVV7k2aJV1bzoIjHdxFVYtlg25wPXp/LHSp4btnjYxRKMHG4ScsPfgfrWatncWzZlYyehAH86hNrO026F2j7nD4JpWQXZtRXzxrKHPmLvIIxwB9P51Wlu54Yx8iMjHGR6Z9D1/GsKWKcyiMXGTwwQZBYjnG7uKfJeXqsAYbhx0ZTgBvbPanyicjatLovF9pX7QxUEES4Dn8z0pBeRrcWjzvBH5gyik8tnt/KqFlcu0CrPKLeYDDd9v5/hT7R/PUGEi5iDFXkVcMp/k34UWBM1ZponuG2BCAPlyx4+npTZro7AQiu4OG2qWGSeMdwKpiVjI8cO6aBwD5hBIB/A8fgBUczOUkSWOWTI4w55/X+tTYpsuSLJeQNE9/JFIrDmLg8e56imm4D7HaZrWMfNhWUktnvxx+BqlZtIUaNbZoYurK3y59TgHmnStNHIMQKsoXiTtj69fwp2Fcs3bW5mVWhedCu7PZW9eeM/4U2O12LFi5llQgsWkAboeASCOfwqobuORvuK6bt22Nd3zD+L2NJIxW4MsNvKSvOdhzx75p2FctsltjCI4kZhubziAfpwanlaKOWIwuzKSfmfA/Mjp+VZD37zqDceYrKflEzbce5Hf9aRpcBZbiGK4QnAKDJP4dP60WC5oJHbDzDFHMrsw3gsCT9d2c/4VLG6XCOfLiikVSQSpKN/UfSspdU+1hkFiWiBABlhyB7fWpLq9hjAG5UYfdjY8EfriizFdFyDeGEcx80ucBltygQ+n0PrViVVMCRtcRRtKcYUkEc9B3NZM0U88yTrbQzIgGG3cr9B0qWdrnPE0YIYDylRXIz79qLDuTO00cgjSNXUn5zIdqj07ZqyyxpaECRJCAQ3Rd307VRiQFJFSGYsecPKzL+WaZPIpKmO3gd1OGD5+T/gWDg/Wi1xXKFmtwL390xl327u6oM7/AGx68iplhk+2RKVmjnzt2bRvAxznPUHrS20FzpmuzmyEt1BGhYSY2lkIBDdenTmoJRcpqFzK00JnYHNsrEuq+3bgds5xU77AtC8XsUJC3cJcKEPzbRgd8ZI/I/hUGnrZIbETBGfk5V9pVjkfl7e1JHpFtfXnmqIlVmCQwxDALM2VByeeOc+1Wb3S7m21KGxiuY3eaEzFlb93GM4yrEcdOox6UtNkytexmXNvDZ3SRTiUrIokCIwAbqMjjI55xTfNnFyF1OORJWQbt6kfu+xx6d62rSwD6rZNcaily0UpiEincRx8qknnGeh+tXNRa0uL/VoJ7yQxafbb7aFhuXllV1DHnAz/AJxRzLYSi1qczqhub66iZliTyB+5lhHybeuOO38s1t219JBoMVqjSPLaLKm1fl3bySQB2780zw/pB1K8+xWtxFALuNvKMzEkEA56dRxTLmyl0O/u9OnlWeWJzEZFOMFcMCPyNDaegKNtTDimjnicCAReZ0csSF9+nSuz8Pzx2er6bBc28bvO/lR3G/kKR1DYz1x74+tcnZ/uJIorobFiJy33gQTkfhzV2x+02+pXHmMGTeJ4Nwwu4HPB7EcU5q5NJ2ZreKtPurXWFhZTAu0OzRjKyBsAOD0IOOtZE2JbuK2JLWzsWmYYyp4J6dOF/Gt3VdWmvNPs381Y0XACnsGwxXPoCDge5rF0Kxvrq9S5to5WiVcny2QvgZG3aTnn3FTHbU1lq9BYry1umIYiB3OERQVDrjjkd1I5z1/CqD6ZmeOSONsRnDtnJGRwT7ZzWsujxLqCRSpJvGZOWIkY5GeCBn1A9j3qC7WVQYoZCWc4AAyWJPGDRzWegnG61GaRd3WlQaiwd1YQbhDK29DnodpyDzWlDdWmq6Y91qUC210sLRpJECY2K8qAnueP/wBVU0Sa01JV1SJ7dlXy5RJFhgDg5IP8qt6i7aJc3tvpd5IvkKpjmji2A8DC8n689+aT1em4oR5b9iXQ1sH1dJJ2aaJz5kiRq2EO0gMW7AMe4rm0s/7Xh1S+aSRfIMZIQcMCSBn8v1rbstdv0vodStmjF3gRziPCq57hlHDBh6+9XriPS4wDpO20lvFkaeGaQ+WQP4FGOOTkemPamm4sbXMihLeWkWkW0UNijCKII5lkJ3ueTwCAMEnHU+tVbW+AREu7VkgDkjgjDY6Z/oaboFsmoym6uHG+CRQIhgKF7kfkas6YFkS58x0lLyN8yElXB5P6jAOOKGkrgrmtDb6f/YyyWDSjULhEEksrZ25OGI9vVeeOQe1ZeuXyxaa62kjNbxXCRBurFQMMT/vHJ/SqyCSO3jEBeRCVdYhwW5z+Pp+FWYAtxbRiIN+6uFNxGVywQkADHp2/GklbVjvdaF7U7e203UZrHTzcXlxLGrYKhie4yAPTH8qzb61dJYZp43e4Cb5nGXO/qwx7ArjtU/2+eHWtTUM4JkEgdH8thyu0Bh2GenTjmr2sm/nDXdpDKrxoEk+ULlwcZGPlORwQDyKFdMppMxtMuFjMgfesksgVHZPliycbuOT6Z9zwcVoaro1pDJFOyXDzGWR5ijcrkAptB6gH8Tmsm7W4jhubqYSKgeMpE64G8dFHfAzx7CuqltVOn6bNcXah50VyZFyN3QjA6g9Pqacny6olK+jOchtLTzoVjzJCZjbyhlILKwyrn0Ibj8quRWyM0gvLto0nkTzFjUAsB93Ofz49ao6xhmS4t5W8iRsx55PBwVPvn19jXYRW1o3h291CL9w1gyRxYOQ8vGVYfxLtJz7+1KTskxpXOTaSeJ2guw9uxxGfMjxgAnb14xirz6m1tBGxmMCxSK6MBuVmB3fKM5PPUe/NZ9/rWo2NwLSKeSXTwpkjR23YQ8BT7A5GKxUuW8648wjfKMK44VBnoB9cdKpU76snn5dEdKL631HS508hV/0gyWwbDbWYYOfbOPpmthGGnSwvPMwSO280wMGJiLgcu3fO5lAPQCquj6ArX5hM0KSMvn3ELDb5AbA25/vdGwBxwPWn3Fp5viKW3uJ5r2W5YKUjUxRyKPulWBP3RjqO1ZtrZGivuyvasRAbeG4jht5VZbeAdVfOcknpuPfsMZ6VaSxVSroipJa5iBAwA5iz0H3jnJ9sfSq2pxR2eoSRF3kigGRK52kKRz078nj3qvc30bpaTxCR4UO1Nz/KWbqpB6MBjnPIxRZvYNOpQkeW3txayYmkwsj7ifmORwuMdgcHvioGeNVSG6hZbaZG+zyNxjJPB9sjHtUMqu6yLEzyTM2CqjLKVJ/PoMGtCe2mvDDGqW5ihhQM077UL5LEEj3atUktzNsq6Ho6X1xFOokksgCbhEba6ADPHXI4wD7810GhPbL9tQxCN5rdniAGI0A4IHJJPPJPvTdKvWsriKfUV+0SRERyQRybI2UHBAKDgEE8CrkNpFFolzffZ5V3TrHau7KHVPm3KQPbb16kZqJzvuVGPYwfDsVxdafGltEVmWF7aZzwUTd1z65YD861LO3Flpj+bAFTzIoxEqAEL/ET69uT6GrctpdxaZJPYZWRjCIguN2Pn5/E+vvVa0N5cG5S4svMhMbzKVKo0QVSCyt3GATg8VLbld9CkuUxbyaG4usW9urwxjYSRnOKkVH1CUwWiNdNtDBVizsA9zyO3fNUIreZrmUJutoymzc8YUsPTGa0jDdJHxeK1uDvXZwSfwyT2Gfat2rKyMk9dSWGVJrGNLddtzbyecoU4JO7oT1zx39Ku6OzQahZS2Uu1xcvjb2Dq3XHXlc/jWXbXskFhexNDbhkmExMiZJyBlQ3GORmrenXapeQS27E8bjHjDPz6/UmsGrXNE7sLtHe7tJACw3DeyEAuMggk9Qe+Pate4t4ry6mllLqY8gxsyqrkry5A5yeOeKitLd/stzO9+yFXM0cAQPG0eMFGHXJP8WeKyZ7iSK2uldkleSdQ25R+7Izg47jHHPcc0t9i9txLma2u4Wm0/YLjnY4b5lCnAI/Lv6itzSJDcGGO588RygAHlsArzjPb+oqnBcCLwSIbifzJbi+EuSh3yIgwE45xuAOO1VILqdr9vImghuOBNcXJJwcfKAPTPRRyMU2rqyEnbVm3MkJvQLONwluiM7yEMzr8oUEdAMY/Wo3haS2sr+AqET5gPN3PEoJUMR94A9u3NYsF1MrzNchY/Mh2ebFlo8g5BX04zwfWtyyupZ9A0Yi3RpLRhG0kMYEpiO4FSf4hk5OenNS00O9ydw9sfN04zGVP4oEJB7kFvUgnp60wmMAhw0k4J3bmOQT6k0k9pbxXavIn73oikMgcDB5OAM985qlp8k211kiWd4JJIxvfcrFc7TnvjIPuRV20uTfoXAjy5xCpZMBmZs8ntkVcS6ijURSIUYjsdwH1qLydRm0pDHqFtaxwoFtkMpRSccgryCT/EW6561TmSDaDPNzIpZT5wQKSO34/wAqE7j2NRGtLjEbgE4z8o/L6VYjto9zIkfy4zlccfUVz8UotwsbRsuOjEEAj8OprUh1GLbIzSPCocYB+83HXg/zptCTLNxCI48BymO4UcfhWaYJZCDG8hJ7iMYJFX4NQiljJa4DLjG5h1/Cm3cE06jyJzGoPCuAyn6daSY2LBcBARLGirgcAHcfqKmhgincs8TEN0DHpxVKW1vZIGAkWOcLgPHglfoGqvLNJYeTDc3Y8wjAcuFZ/wAOmaduwX7mnc6TBLGVjaSIZz8v/wCqqMfh/jakkyrjIY4H4etVBrUsDQx+ZeAo3zGRRkDPJJxzj0rTudVumRPs0qldwYts3bl9B6fWl7yF7rMi58PvDK0zM7N/CSSwTPWq7Wdwh3SyFkx/AAxx6Y7muht74Sz+W8Nyd3fA2r+PWtN44AhMroB/tc0+drcORPY4+axzErwRTSoQCSzdPqD3rPltlgbyoUmXP8EblF565ruX02G4VjbyLvz2+Uisy8t2SRi/nSgDoIhjj3HNNTE4HHzWxiJNpcW8BAzuJPH9KkMmoxlT9oLIQNp8sHP0wOa1cwxSOWsxtHVzxkk+lWZbaUyqIHZIFyX8oAMT2X6VbkRynM3t9ciIJLDA3HIfKkfh1qMajM84gjiuEYjduIDge2T2/Gui+yw28ebmYK5Of3nzE+2axLiNJb54khAhQBy8nykk56AcinFpkyTQ24ljVFa4uQjPwPJGC2fpU32bzrZIzN5sKnLByQSe3IqpDZh2KeejxKSMCNlIPsw6+mcU6+0tpwkMcs5iHVFcAfmRk09BalmePdGds0kbHnKfMf61UP7nBNzNJMFJCSbSSfQgDjNOtrO402LbvmZvmMMaKOTjJBOf1pkJ1OeJhdRpbDHVUDHH4nFMRPA8q4kaGGKUjB2qw4+tXgzMjLGUMh/uyAH8DjNVFv2iKxtJIfXHyFj9ecj6Go7q4W8jb7NIfKOY3KpksfY9etKw7izzeVCqTmaLBz5pbzMH69KUXNuIwxYkt95l2nHuRxVWH7VNDEpM8HlnpuARh6BAM4q15zfMhW0mUnaS+QfyxTsK5Fvmjs3uJzcEglgFKr+O3JH6U6O7mbakULMhGcyY6++P5VC0cfnZFnhMZ3JKef8AgNSoiSrG85s4Qw5jlA3E/Xg0CHW+oyzi0t0Qm4tdsSgcbW34HPpyBjpWZ4gvLqG/QtFFDJIDuUoMq4Yhucccjp2q/bWkEFjNqmozzW6q/lIISN87Y6KDxwMZJ6fWq+p3cK+XdXtvLLK43K02SGY98jHp+YqI2vsN3aCyd544rNJkkmU7laPnHsRxjr1BzV/xFPH9msGEreUd0UqBMElDkAHrgk9/XNSabqel3IjtLnT2tWYFYp1mZ1Unpz94gnr1qQefaM1nLDZQiL97vmDMg6gFWySeMYx6+1J7lLYoaJLe3kMrxWNsIIBl2hURlVX5hz/F0zznpT9YtJxqDPtMcTtkSucHy25IOfQmpDKIvD+rC2/dJdyRqzfwoATu29zkgY4yM1UmnSDU71NSbdbByqyYLTAkfwevXnPFG7uhc2lmaWm3TaTc/bordxHbgGOcEBSQ2SoB74J/CtaLWrO21nUriGD7bbaijTvFMFwGJBUDuATkGuWktUijM1jN9stkALSIp3xD0dOo+vK+9dIujXk9lNp8PkFoPJc3CqAEVstsOcc85wKiSXU0i2znJmDapNNawMIyWCRSHJAI+6fXuv4Voho7TTYhFZKqkKZDK2/c3cfQegHaqU1lJZzywzmJsDI8l1b+RPPtV3WLaO2kjgVHFsIoiJVbdlyis5I/h5zTlroTBWbZI72s+nRQ2i4huXKQs8mGA7AHoCTnqPQVhRI9tqyTIx88NgswAIByCGB/Wte41CO4gee1gggWOU7YZEBQLj7uPU47UkM8WoJJqcERSTkSiTny3x/C5OMY79R+tEbpMd0yZbgGwvZnLtLGUitY3GAWLbt3Hoq4/Gn28rWPiHT72R1kUqLiN1+ZeQe/qDn8ao62yjRbK2N/GLuItPcbg5G98bU3AEcKo/FjVTTHa4SOIXMZuPN/dRnhCW4JDHGD0J+lHJpcfNrYs3O/Ur+5vdVuJI47qctv27inUBip6geg5wKi8dR3CTrCG80lg0ZiYuskYQHcvt1Ofr6U2/tm2iFpCJkmaB4mUmTzBjIAHWt+XRWsZtMiYlbm3jY3Bc7gok/gA7EA4wO5NNSUWmyWm00cvoN80tk8dzMqQx/OGEW5gB16devetKa1jvbVGt7sSXUM3llJEMQcnp16HAPXGazvDNqLeO/upfmt7SUQyuF3Bd4YAkeh2nn6DvVq8keG+uo7hTsMagoOM7cMCD3UjOPY4q5r3tBRfu6g1mYrO4aNHO8KGY/KrHdzgn05GelWTFPb2sc1skmXGWJ4DA9SM+mOv1q3cXMt1caTaNeiGwWRoz5vzRRB8EuAe3HT1qzrukWcviW6Gm3FrPp7BUVXvBvyFG4ndg9Qaz5u5py9h9wlrpp0gxwmRGyZbh2yF28lUAPGA3JOfastZtk91IZDHcFSplLljLHnAG3pnA6/hWmvh7V5bqO5+xXFzb+a8kkceGGzpn5Seqniufu9MnXVWt4mkvFOWRI1I+Tsx9Pf8amNnpcltp7FXUTtnglDtJvTaSRjdtYYz78itPS7u9u5QLqR/sq8yxgAoyEgdPXPFQatYOtvsaWMbSGDgg7RwP5rnjNJC7x2wInIVF2lFXIJ9eOuOta6OIapm1Fo8Nzod5eTSwxWNvfrEF+Ys2QSCAMjA4BqfXrd4dJ01RPFNCLaQoI2PA3Eg8gYPI+mKr2zB9BSwUsEmWS5l3DYFGFVWx2+6SPXNX9Ea21xYklRIIbWNpS77vKji43bgDn6YOc44rKV9zRJNHI3conuNiLscsHkwvfbkN9feuttmMnhWS1i+S0txDN50nyiaV2If3I+ZR74pbi00u7ls7OKS4e6Mpmg3LucRMc+USO5GT7cetZWqXMtrql1BqUbofJh86Ijaw2/MVx9SBQ3zaIle7uTaHYJdazFY3f2eSGY4aPzMbV6kDoccVFH9j1G81W5ltZbS3jdgsYx5ZzwilCOMEKSV9e1QWjmDWHkSQCSO3kFucjncCADnuCcfWs3SHAneO8eV7aPaJUDlST3Iz3HoeOOaaT1YXTsjpNPeS311XMUccskTndnfukPoepB688880y4fFwRB5iboh++HBUYA2IfUnqfoPWrmrJPDqkUMbxOnlNPBNs2tKpXaGPoR3HYg9qwLKSayea6e58q43CPdGA4iU8Hbg9enI7ZwetTbm1BvoSS2Jt/OW0WQ3QK7y+HYjOT8hHy8c5OfrUIluVa4lusBZsk7ApEgUA8YwAR19etWDFPDGDcSRXkMjE7hI3BHP3gMqfb2rHuj9mumWKZ13hZUWYbSrA9Gxx0yM+h7VpFX0E3Yks0jnkuFW3mdj8/lo/Ls3K8jsBk49qDYXciXcV2JoTHC8oilQoXIGRgHpxU9kkmnyF496wvLlCBnYME49eCSMj612XiXVpNQ1/T5Lnb509pGpZsnlgVz+BxwfWnKTT0BJNanLDT7uPSNKvXkTybx2UHPCFTty+Pzz7V2MNqkEuqaO0yahPayKHUxYjnJAZQCSGBBJ5z+FZunz+bZyafcwl0t5FkRSu0qT3OODz+eaS8u7W0ku9UW/jmNzfAy26RtvgCjkyH0x0IPJ+lYS97Q0ilHUZaTrNc6hE8cov5VzG6kHdJGRlFHY7WOPpV28in/wCESe0gAWWfy0uzGAWjiLEruHX53XHpgH1rGnGpaJeXAvrOSKEsbxPMCneGBClDzwQeQD65rZsT/Z+t3WpztHJpk1uIb4PcBWkR4wcqjHqDgrjPTtTtZjvdGbrfm36xyJZwQ3sTbJY0wsdwuOGCn7pAHI9CDWJcwPbGFzpogOG3bMAH6Nn8alsdQnvJntI705VT5dzIo3yHOMZ6qvv97+VMlaczIks5itZW2SIXO6L16/eHp6+1bRTWhi2nqWtKjs2a4kukaYqhlMWSPNYDCJx2yRkjtmoUYQz2PmwiNVd9yIuAu4DGPQEnFLFYNEiz2s6XKqrCQBiFcH7pUEc+46gjmqaNDI8imFGlTbtnY5Z3B5x/s9gB6Cpavcq9jprm4SSCCCK38uVlMLLnO/5jg8diSBQ9jDFNbLd2crLcEwSXuGSEsOQE4w67sfMT9Kz/AA3JbxW2o3F1ALm+QH7LKXOI3JCrhPXLe/0rodZtYNN020s5pJImeEKd0hOc85x/Dz+QrL4dDVe8rnOapEUspWsw0SR2ZeEhssp80Z6c56/rVPT4Y7uzgn82V7hCY7iORyxznhx3AK8fX61ettOki1JvthjWW9gIaB22lBuG0sTwAeo9uau2du/kappjRMLq1j+0wuBucAAEqrj7yspJHbIyO9XzWVkZ2u7ldbaW20+RpHeWwYDzknXg54+QAZ4x0/8A11oRLHZzxWtrHI548vO1EcFQeBk8c55PXNR6pNDYW9hplzu3D95OqDc75HYcYA7nqccDvVC0kFxPayp88cDm1ZnYkkpkrn0yuP8Avk0tWrsrROxuabbMriW4IN1IpU7txIC8bx9Riq1ujRaxfmOU/Z5nZmQj/Vvu2gA/7QGce1Jb3dq9uk7RiSco8kAI3PEvfceAvIPaq1tIEsbOAk7rc7yXHVmOWY+pO4cfSm7pArFm/mhu7IuQ2+Fwz7mH3Q3U4/2Tn8adpgksvEFvPNaI0cqurmWNXG9UJR1yPlIOAO5qvczRNO9nPtSwVzGRsxzwcN3yT/Tmr9ikkRVIIMIuPLfKsMDuMHI/KhLQHuRQG6t7CFnjllG0HDMMvnqc+orLvnitUlEun3ku0Bl2njOe+B/9etyMbbq4Nswmv/K3PaNNtU5PBbPA/T6VT3I+LbUFvhPICrRwhvLi9QW71aIepmWUcMv3I44nK7mWQknJ6E5xitiwzHCC06MiYKkNjj09OlQQW9rJBCwDSQs22NV5KseASMZqlLDJFdyQaVdsYt6xh2UHc/TYnr9TSk0HwnSRzvtVo7oFF6q4HP8AwKq8jebOEuILWaUZaMOwY/XoazNSv/7I3QWrWWo3kMhjuvPPzM3+yvGFBON3Xv0p0chFoLpdgUKWwcYGffuRSS6j5rm5NDHdRLFL5TSAc4XA/Cqr6X5MZQSlATnnnb9KqW89xcANHPDtUndsHLenXGOK1lvUMghkMgweSMZpaorRmW+jzHfsu957fKQR9SKojS3hckwW7zBslnJcfqa6tWBjDWsvmg9QwCkGoLmAbPPuImLL6Dd+op8zBxRnWutQeYElkSOYDDMO/sBSvdKLvJmaVc5QsxyD34ptzY2V2qvMJkQc70UHP1HWohbhoyumBLlwcHK7CPxo0Fdl2a5Z5MSWnl5+VZRErg/4Gi10eGeeSaS7d3IKlSqoMfQd+KjiSWMs0yyBUHzhASF/pVO+ew8yOd5Z4ih6YO0+nFHoHqacmmR7isd6yg9Mjd/OoJ9NOQ0Z84HqQADWbBBJFEZra9LY+YMXOR7YxyKu2N5dXW2S5s4pETlJY3VufbPSizFdMSSyRAMPIuOPn4I/Gqtzcz2vyrbxsh6uH5+oroReQtjzXEZI+6y9Km8iGfLQtv7EqRxSv3Hy9jgLu9slvBJdQ/6Vt3JliTz+ntU1zPCLGSWNWlU4OzkjJPYV19zYBU/eJHImcfNGDj3rNk063Z/kZEJ/hQEA/rVqSIcGc1e2ls0YZ1mQjHyoUzn1wAeazRpE8Ev7kthzkCeIuv4kcA11UuiSfaFlhnVCFKgKm7OfXJ61RmWS2coUDL0ZpCxq1LsQ49zEvbeaVvIe6Ck9Vj+XA9s00QLBGIl/0hwuBhgD69c1siWwmzlyvH3u35VHcQ2vlsDMVUHH7wjBHqKfMTYy0lmtSxntZ41+ULuyWpt1q8FtgyEykjAXaCfrz0q4iyhNpt4Z4T8qmBgWx6ktx+VRXljZSOfNtQx6Ah8EfWqVr6is+hT+y3OsafA8CSSx27v8qDp0Jp93rB/shbV0SWNX3QtLnKZ+8uPQnBq5c3Kabp/2exSS3POZFbHmAnO1h07DnrxWM9ncatqENtZxPPM/CxqCS3ftWaab8hSdlZbjBqLYT95jHI4GB9B2rV1QNHo8F1a71meQyEq33CR0A7dz+NaVz4fNpbLDbS2k9/Iu37OdrCIgcsW6NjsB+PSsS0+129ndxakMQSONzuQTkddvq3Tg01Z6opRcdGS6HDNdRy2chG+dDLDkZ3OvOM+uCfeqmszC61WQJtDqSiknrgc59Ks6ba3Ukr3FmuNkn2lNpBZVHqvUflVjVYbGK7n+3QlmkkLRtAm1lzyNx6E+2KaspBy6FDwzNdS3kYiXyyEZllTIYY7cfgMe9dOl602qoLpo4r2VfImjlbarrjHB6K+PXj6Vz1pNHBp9zFas8olCwxLtIY/NkjA5J4A49a1IGEV7bKqrbzAbTA7Bj26kZIHbnnFRNXd7FQ0ViOygkju4raK2ayktnMl0ZFJ8oJzubvgjp9eKszanFe26TTosxT7i5Ktg8HOO3TjpW1pl4zN9jupY5GXhmYAlo+wbvhSTjPY1x/iTzLK/YxKPIcfIo7KOoA9M1MfelYqS5VcsQ39qpnSCwjjhVSZYpVL7SuTk88Z4HtVfVJ7m71LTLe68v7JmNoFRQiGNiM8AAZ6g+4NUrWSS5W+UKcuuGbuAOn17Z9vpVm03XGlRyyucWsvmK5PKKev6gHFa8qjqZrVWFurufU7y8iuZCltcOMMASFwSVz9Oak0yB9NWeTULcPDC4JiznzMjG0fXI5q80OpnQ4dQ+f8Ash3aCERAFVYddw/vHnk9aPJuYcXXlLqNvaYcxupU+We5IPY5+lS30LUep0ek3EV4LW9eMvfWkqCQKctnpg9ycEe/FQXNxe31xdX8ED3Mm90toUYZj7FiM5LHIOBz0qGOx07SR9ssLmS2/tRVihM5L+Rnl3JHJI4HtmssSvBcX1pEzwTErMjZ4SRRzg+/X6Vjy3d0XdrcTStRj0bWdYtZ0L291iKRDwHGOh98nP1q/a6U19ZXF1aLFOF/1U8yHZC3GUdegbGMHleprI1xvtV6LgLFLhts2SF8zAxnnvXQ+BNS+zNdWMqSPpF2hQyMpKruG0rn1q5bcyCO9mV41S/nittaWWWGNN4Mb4c/LkuOxzipNQ0mG433LSeVNvfDfeAVjuRjn+Hp+B9qx4ZJtI1kWVyPOa3gkiiOcc/NgH2wf1p17fSSabZ7S5J/cSdMsBzhvapaldWZSatqaTRuxEto72EzLvR7ZsxyHuMDjORkYxkH1oW7guLfU7LVVllu2ERV4ZCC6qSQ2cdCG5BHUDNR6JpOpX32iLTbW4khEu792pZcN0OegI/lTNW0y6tSJtUCWU+QBOysV4PdkBAz7+9Ctewne1yvcWcCpHHaSu9wyKwikIDZB4IHcbeKy4fL/tKcTBvlxzuxl2IAHtn/ABrV1qGLyITZ2r/aAw3xkCUDcM7oz3QnuOmKgtUudSnjjRBKLbEzqELvGF6cgcdhye9aR21Ie9kQzSCWe2s2bCkmN8OW2FvunPscYqcXc2k6Vb21tnzb90yvdokOF/76csfwrKtre+/tYsbaUO0iyyKo3Mo3A5wORirGvXvl6+hwUFrKIlU8ZiGNp/z61bjd2EnZXOpultdP8PXtisajVbDyrkXsQOZoSx45PBRmxkdqi8RyrrmkxS3c8cWs20YEvHMikZUN3Dd/0qgb0/2vemVgwNmzJvHQYU4+mVps1v8AaLB70I+8uPnxlWYjBUe/Q1ha2rLbvcu3FitwqS30cstm0pDNbgGQBhuwe4+YenQ07xILONkkhfbLJhjBty6j1YHoPrzU7yNbxMQ8i3ESK0u3JWHI25GBy3YD1/TEgnVLeWVrc7iwZJHOWHbcf7xPJ/CkrsNtDXctf2kKX0Nwkixt5asuHRTnKEHqB94H3rAj02RUjWYgLIoaJh/y0RW6qfTBP5VspcXE6SXkymWRY9r4fKkc4OOuMHn0zVS7mih04NAiiCGXzkheT51UqM4bHZh+I6jiqjdaIHbc56y1CaATPC3ysPmTH3hyCR6EZrQhlkltYrqS3i/djy2EhAWRB0Zd3U9j+FZ8GmXNxPbQWANwZWIVXXbgdTu7Y685rrLPSNKsPMvpG+2yoNtv5h+TcBgfJ3UHuTzjpWs3FGcVJmVLNFJZGOW2iiAkDR7COpUjOV6HgV0moLLe3OhNCiPKLTeTnhACOQR1qst0Ln/j+gtvMZfKl2x5hkx91iv8J91PHoK7bwB41XTrCXT5ILd7NMRPKqgsoPUZ/ix6HtWE5Na2NoRucFHcm2S4sk87fGrFP3gKL82eOM+v8q6PwksF54fv7VxB9ouGYyn+IxfdUsO+CWPrzXH3sUltqt5HIS6xXcsQ6cDH8j1rp/CsYEOqz2qkNHawiMj5iCTkqcd8pzU1FpccH7w+206+u9Ls31CLzn0WR7FpHB2zRYyhHY4PHPGCM+lY9/JePLBGFdry4lQQGMZxkHPB5ORxz/Liuh1v7PcXUEmpQ3tzZ28fmJtm8mPc2eBt5dyRg9MAVhm5u7Tz4ZnuY7OTKyBnzPahugLDnHbt74oi76jlpoX00CdtOma5j331t+8Voip2gHJD4OQfRscdKwFVYb83bl4jcjH+r3ru44IHP0PFS6bqNt4d1mErZmCWNg6zCUsJFJ4x6g89q0PE9naR61NFbeYbdiJtscgTyi43Y57EHjHHX0q4tp2ZMkmroxh51vczXMNyxyQjrEm1R2A7gmpvCWkx3uuGJ03wnLsrZ2Z75YHoBubr2NMeG001VlVTJOUKCMOWYgnoR0/SrVtdPBJDMEIVraSFogdvLkAqB2YqRz6VUttBR8ydrhbXxHN/wjllFFHHHhJCpzHhciTLZCnHOe2cCrd5qMV1fNDPdiCOK1hFtcEnIkEQJx/vA9D1x61h62rR3l1cQSfLK2NySZ3YYK6/hwCKXXBCb+8EcwkMJji6cFljAZh/wIY/CocU0DZPbXF/rAe+dwJyANxUDc+QFwOnbPPGa3bBjBeS3V1eCa6toGDhRt5bHPHOcA8e9c9o1y7adppiZVXzWzFnaXI/iGeuBnj3Fa0lhJa6RcJKpYtIEALkFmJLMd3fHA98VLVtC47XOZmkma7gaZJJ8TEISSGfcOCTgHO7FJoDebNeQjaBPlhsyQJFJK8du4/Grsyw2BE06xbof3gHzZixjHGTkE+o6kVlz6hHZIRp8ZjlhmEgAYnIByCQeoI/DBroS5lZIxfuu7Ne4mE7tGWUz4KhQAA+VzuB+h/yaNPk8+/W/uTnGInKj5CF2rnP/AT1xWdCytdwyXKhI4lLLK+RgMc4Cjk4zwMjGaluJk8y2ignnit4oGZUOG+YttBIHGe9S10Gn1NPQpZrv+0JjIqSXGHUlQxUZ9O5rprO0hhMM6RQboxtZhGu4kjtt5H0rkNPS4tIEmgYRSPFuUEBlY9Aw9uDx6102k3EhEH2SztNz7sXUMmyNc9SwIBP6n6VLXYtPuZqTxRky/2dII2Yr5wVtwX0yTkfjxXQaZYpDoMM8s00W/dHE90ikSOMcKR169fzqK7is7PTTqcEMM2oXF2IpJo5W8vAG5jgnHOAuO3OK2bo6PNc2OjmB00y+k+0W7xtgW7yJjqe3ByP8Kic30ElY564KCC4WKZvOhlHmyRooDArkKO+MgDP+NZ1utze2UUcSwpaW+QIzIFLN1Z+eckgc9sD0qbxRosNtf3IisrwmE7fO3AGfDAYRV9FBqDSbywhsWSKe5iIyTHCu5xn2Kkg/lVpX1Je+pS1PSH1DVX1CXZGRbv57joZFXAPvu4/Wn6UYxoFvKrqbhWYGHnITIwenIyTkVo30U1vpc08Ms8kDRnc0j8sCMD079hVPRLiWPT4lsrmK2KKUdZFfLN1JOCMc9KauwskVJZb9PJla0sJGjcspAG5V+vQGtPTfEEdxCqz25Ex5C5BOPrVXV83Je4nS2kupSN8rsjZIA5wCM1ScWT3Yhkt0t/KXjy1LqSTyOvTjOOfrV2TQrtbHR/b0aQ7FCBck4I3H8PXpxU8GpsULrLJKgPlt8mcN3Fc1OgSIBLlIVJ5AhbPqOvSpNJSK0uJJItSeRn6pIh2KT1wOOTU8qHzM6Bb63ncoEVWKkFmBxn/AD71MqbxtDJkDlipAP0warzR295F8kyIwAyQMD296y7Y3cF1N516rRbsgA5I46c5x7dKmxVzfaTyRsnuFXgcA8D1OetV9VtncJMk84A5zHggD1xio5dRsIyDPKsTEfK0mAGPsTVSW4uHuhJZXdq9tIQGBzk+4PI/ChJjbRXM3+kbYp3eYYyGRRn8RjHHepzbzEELFcA/3s8VZmcxhW8rMsnyj5c5x17f1FFzczranzrFwuQP3chIx67aZNiq9tHL9QckZIIPrnNVZDd2YX7LfJGwyD5kROTngnFOljinQS5fypFwrBmXg+tOnWSBAUlIXAGGbIA+tNCC31vWYXjFxbQTJ1aVHxkeoHettNVteXkj8sZ67SOfqOKw7YSNKirIi9TwOvvjmpr2z1X7P+7iilU8M2QuB64oaTGmzV+1QTw/6JKy7u7DPP0PNRpBLMpLqzHnttUfgQa5xbi8tJQptHZc9YidoPpk1r2+rAgLdt9mbPTf/UUuW2wc19yHUtKnHNqhAAO7OG3VjO13A4hm04S+4Xb/ACxXSpqQWdldtzf3k9PpUjX0MxEbsjnurrjP0NNNoTSexzfksqMUjkgDAEg5NUGnnjuRHNcwguPkUZ+b6k8ZrrLhnjwY7gQx5BKMgbP49RVXUYopYyryQtn+9gg+1UpEuJxzxvPHCkkimRjsJDbhnHX8eKgt7+ey0yVLJjBO7bZ5Vb5yoONgP8Iz19eOwqCCR3jJWPCq33g2c4/rWppelLvSWBZJI5D80TrvZs9sDrT0juZJa3HXM8ti0C3AjkuBH+7k6lE/iYH1Jqe8ljudN+2rKSyALKAOWHGAw+uMGq+qKZTBH5iARwiMu7BG4b0aoVglsrxRDdoBsy4ZTJ5inqCBxt+n1pJI1bZBYXU8ExmiJSWIGZWHcgjnPXr2qTU5Zru8aRXBSf8AeJuUMVyOf14rRvEjXR3fT5QIZmBaJgcgA4OCecZ7HB6daoIYCghzNK8ZzEu3yySSM4HXAoT1uRK60EiW+E4sNOEjzsSk1wo2tn+IK38KjueCe/HFX47OLSYzulR5FUrv83y4xnr0+dj9Biq00lwlrLFYRKUUEzRwvuJc87mHVsZ+lYNhC84dW3GSQgJ3JbPSrtzIL2NmCQWlx51tFG7SHbuVGIbPUZJz/wDqrb1Gyg1d/JubtItwadHSH/VbFG8sc85H9KxrnULXTWNpaKkzplZZBjDnqQpPQA9+/wBKvW2oxf2NclxsWQra/MB35Y8dOAKiV73Raa2Zj2F6tlLezWrCQoAVyuQT0zipdKm+0wzjnDKQwwO/X+VWNO8NXdzrMsDLLbQtGCZShA9sHoc1ca0S5lmfRbXdDAvlZAZzOy9Tx0HvxTk10ISlY2/Cszr4Y1Hw5cyxvbXiNcWlzE2QJBj5T3VgQDzjvWJoc2paNapd3m3E6NGIHHzSR98+nt3OfSr0i/2ZqMd8bedLK4ty8MJTDQOPvxtwPTgnqCDUF1NLbzW0sJOyRNzYbIU9yD6Vm3v5ml7WKuuKIFjYJK0FunyRueFB5+bH1x+FVLTULe5giuPs26a1jEZUyEHbnAbjqQOOe30rf1OaC+s3v9HS6g1CGXbNHKQyTL/snGAf9g9vWsiVLfT7mBbWC2iNwRJMrnMihgQUXP3V746n8KcNrPcJKz0KU0YgSWf7Kb0wscrIflTPqAcsR+ArX07xBqE0LzS3TTWJKo1rwqoCP4VHAIIyDVa1dI3eVFbzZZG8w54IHQ49v61TaWGG5nKZSAqYWUDgE/MDx7037ytYF7upp6jreoQ62sVvqB+zyRq+6IAZGO5xnqK0LbXmm0+7bVLKxuwh/ds0YR3IxycdQP61zCL9p1G0VchmUqP7oHOOf84xV6xnUT3NuyBXjQx24YZO1uWP1PX8aUoKw1N3Oq07WDqlwwW8kns7eIARLkRq54wF6Y6npxXNa3eGK7zbyhGLs7lPlGM9x0I68dKsaBmLSrgou394M4bPAA5JH41zkjNPcNFdM0blSWJYEdc9P8KIQSloEptrU2/sU37uC1dleViyIG2okwOSB6BlOfSt7xTqb65plw2mRw2K2jefPY2wCeZuUHzCRyxHv26VjWUTTeH4JtwN4seTz820MURh+RX8qy5r1tG8ZSGNgYgFjf0ZNg/woUXKT8iFLlfkze+HOqiDxVcMhDTTW0kRfGMgYYH68Y96wtdEl34umt4kM/2mQNHGVycsAflH1z0qSxL2fiaM2dq1zHNu8mWI5yjD8uOh9MVtJI+jz21vaKjXcwEc90mHkY5+7H32jue9W/dlddivijZ9zGsEublXnltf9WsltI28Bhk8ggjqMn861mKTeSDdNFErLFCqRkpGwz7/AHsD73TPXpUFxaXOnwXKXJkt3k1KF1kdc5yCSSvftUxAV2t9Qxbx3m8F484JDHD47EHPHoTWctdSoroTaBE89zHZwt5YukaPCkMYztIyTnk5Gc/lxWJY6jc20RuYUEcsRDRpjcDt4AIPtke/Nafhy0NhqkYkYDypmXfGQ5AIwce2DnmsDUImt71rMlUUqfmXkcdG+nH61UUm7Cd4q5uW8+I01EPDHZK4jubdTnAYYPA5C4+uD+FZd6jweQGXzAxwJVAOc/dz2wQaqaaZYbe8W7L7dgYZPYHGQfxq6lwP7LkhmBjNswKSQ4yVLdx7enoarl5WTe6NSw2abZTEMUe6byo9x+4o5Yj6nj8Kgulgla3RXCJk7pVdgo46k+57VHA6TxwAylgFwMRtmRsk8D+dT2RmVB9ps3E7Du4IIzzjHI/AUlHW4XvoPsrMxy7GvGe1HIy6N+R7fjTl1D/TFmhX9wZYxsRceXg4O7HUnOfeppYWhVJ7aKK4lKgCJSFI9SSfTpTLiDYiObuEArvmjgXdtI5xkcEnpzUTs9WWro07OCG5urueeCT7ICTNIrAbzt2hE/2yVxj3z2qvdapNJNKkN0FtJCCsNuSiQgdiO75xljzkVHDIbuzubK4wkKEGIEhVRfvM5PqT3+g9KSKzW4W7ntjC88mxIkDACR2Ygbs/TvjNYtaajmm17prQ6g6aGZbiLdeopniBOSA7bcnPXHDCsu4MVnF5kaBprndGV/vMQDjPck+vrVq3t76x1C1OuW9xDdLvSRbmM5dHz+BH07Vk3wD6ldWqjdHEywxor5CoGBLsfUdAPrVxjrYpvQisp3dBBdxDfASrQyqRj/ZPcYP9a6q5vLaWCzjv7WFo7xfLcDBKqvYHuBwfbGaqwxnVoJobhmfVLVC9tcNGyG5QdYyT95gOQe/IrKudQhSzgNzOLRfmA+TLkeij8PwqmuZkp8q1IrqVbZVtFt0S5Mg2/ZwFaQoeM4xnjuCOuaoDUJrW6uSyCPzl6A+YFZSMOD3xyM/WrGpzxyW6MLUpKNqLLL80hQdM+h7fQ1mXT7b1JJoljiX5FUDt9BWiV9yGy7b3P2S2lS5gglgkYiURoEfAIwykfxYOa0LjSzO0zSXkVv5rL5aNubG7jccD5c88Hoc5rCW5khXbZxlZS4JlcgsuSAAnYcDr1+lW7O8a8nkhgkKbiXQvyoYcMCO6tx+ODQ4vcE1sb1tAbMWGnR7HndmLkgful9uvVR2PSteWaFbNob7NzBE5yyLzEMlskZB2+hXkY4PY1YprBX002yGIwFoXYqVJTjbn3PP0z7VnabHK93fXbXLbZGaHLHahkz3X7wA+X6isLX1ZrtoPW5jshPA9ttikjDxvxKjLyc7sYIPHassy+db/AGi809Io8AxhwGZ+fTHA7fhwK0tOgnuJn064Jt3cOYPMPylscqcjoGwR+PrVN7lb/SprO8kjsb1Jw7B5PlLAbTz1raOhnIytR815YJfkhgILZMinI7559jVGRmleF1jaOF3SLByPlBJ6+/Wr2n6Pc3EAktJIJUQnyySMhs4PynqfQepFQSG6sYZrGWObbHcJMPly5IBDZ/MH0rVJdDJt9TeX97qjWFvcRfYYn3p/d+bBIQk5wD9a3tHurODT2inlshzg+fgISegyAQc+p59a4SzuJJb/AGrE0pVi8GVyM49MdOOldHa3NwzQxyaaImOTKcBgOPvADgjsVNZyiaxkbN0Z7fS7iN5rW3ij3N5ECeahDfdRWOAOfX1qpqTX8pWSyb7OImCCCNtzP3CJxg+uKXQ3+0apcRT2Zu3jiEkYR1VSQMqWHfHXA6cVZ0rck1zdLD/oseSLhSMgdCvPPcHjsax2eppudLdm31bUFN/c3VqVCM8UDYkZ9pBRX5CjuTycVi3l3ci7uTZala6ZHBhpYzCGcADHLOS0g6HOcVPpElvJdzRGNI5IHO6JXUhieT8vXjH4jFU7rUDLqSfYLuOOxkjKyu8GArg/7WBg+nNEEEiW7vXuNHmgkdLcv0bb5qn0Yxnlc+meKxvs9zbx2tsbq5hZG3BgGBlyO4IwRW5pdvYadhIJImlQZQOmSA3JAIHK+g5xVOaW6N5dtZqZ2i+aKLJQZPVct07nj1q0+xLXcfaagkt3LAuTIBlQ1uELHH3l7sB3yKgtbu+liI1BXhniLDckCgSe69f1q5biyvr6yvNTke2vbdCBa8qUY8tnAy/4cVpS3FvcWaSaY7yBvuN5DOG56dB6Y60XA4uYRp5kLEXF8OZfOOG+bn0IAx0Aqs95JaeTsubeId4ihk3c9jjIPbIro7my1K2SbU7y0tIXCAywsTh1XkHfnIIz0xVmCezbIZ4HuJBuU7QRt+g/InrV8xHKc/b6vaSyokSuiKGbD5XLDjGMc9f50/z7VJC9jBBIGPzBflP15q34p0y3+wi6ijjBj2sHWdlZCeCcgHJrBiWS1jZsLLAvUq4Zm98DhR160JJ6oHdaMleCwZ0knt3Zt3DMPu56c9D6VdhigQO0TpESBuVh/Oqz6pIgUW1s6TO4RQ0qhCuOevQ+mOKdNGWZxqM8Uok6DGB24z603cSNW11G4jZVdYtpwMnn2rQk1K0jUC4UQuDjk1yzSLb2waKCAyopCkszcAc9easXNzfXWnoZLFZ2LDa8bgYHuPpU8pSlY3ftLPGTEkTsDyu8jj8qpSWsizF5JJVH/PKVfl/A1iz372c/78NjhlG7Bz78/pV7TvEk8pInOY843xHOD7rRyvoHMnuXQ0CDMiLkdCwJ/HNIb1gTi5nMfXMalsD6HrSS3DFllieOYOQdgYLj8DSzNald8kLBx0wME0gM+F2WSSaNHCynlyCjOB3I7GoZ5rRcCZpYie8vINXHL5xbTlSRnDf/AF+DVK682yINzFZzK3cptY89uMZqkSxYZoQqyxSrOiDBMRwyj0x1q0b+2nXKsWReoJzt+oPIrPL2l6i+S4t3z1KYx+NOjsJYgC91v3dHYZB/ED9KdkK5ox6rBApzBvXI6MTj3AoudX0u4YRsdo7NsDKfqe341lzpJGzJDDE6HiQjdk+3PFU7W2tnZx/qJMkhkOTz2NCigcmZ7RRxTvaQwypMTwTICrfmKtW8w/sK6DFo2QLHvGT36/gRU8+m6hLHO9rNClzZruucygYwOp9iBn65FNsb57q0jM8UTrHvd0iGPN47kewFDelxbM2PMttY0yzs/EDRNq7D/R7tWwSn8Ik45z61zuoaXcSNMlkzyXEBJe3cbZox346FfcflVKe9lvnSa4mT7RHJ5iyHK4Bxx9AQK3NWvd1xYeILeM+cHWOcg8gjj8QR/Smk4sG1JGd4e1GS11KOzmQtFIpDK+epHI9wR8v5HtVotEJ3tg6gLmNHJwxRuV2N64OMHg1X1S2SDWhNZYKJKJdpJGM9QPbrTLpE2JmUyyIcDcgGxfXHfHvQ7PUWtrMgu7Ce0nL+cdm/92VJBVu2fT8K11uDFbtM9qst4rqouAdj5IOSw6E4/HnmqMKrZMwmjju9pxEJOrE88VJDdxairW9wEWdkO2GOLYVI6KD0J7+9DuwjoJpjW0FxJC1ytvFMctI65WM9uxP8q1tSYBWihaNrdHCowKuZsjl2xxyeg7cVmR6VHqKgRT9YgokwNoC8lmyeMcZpfssli6Q213azz8BeSgkXt94AE1ElfZ6ju7WN0X1xp7JBO/2lraEgkklGAGdwX124HpxWDq2qz3EEEpZzaO6rEq/KkY/iXaOAfbFdBe2z3MPmzNDFcbZIthkGG3KcYPfn+tYuh2k1vMbW9jhFmwzKrSg4IzhwBk5H9TUwa1bKfNsaXhjUL+xh1W1snDXFtOJ44pDlZYz8rRsDwQRj8qviPRdQ1S4s5nubWGcZt4rUhkWQcuMnjHHA96qrb2WmRPcGe4b7biJPLjO8jODtyBjnjJ9OKpXF3FazWAs7NdiEyo5fceDzj360n7zuitlZnReDb+1tPCmvjy9vmOYVjk+bLEcbz0OMZP0rh5omuIRLEpleTYUI67s5J/KuhmdI4Dp0C4nuneVwTxubkD8sCubjnuIb+W3lhMM0eQVxjB/r/KnBatoJvRIstbmGTKOGE8hYEHhfUf8A16qX7SxApKykM7AKOnynr+NT3l/aGw2hQXddp2Ej5d24bVPTJ59OlULG7hhZpIEEku0keamdnuO1bJPczbWxYhlNoWaKVYopI+VY8Bjwe2emelOnkSFZJISzyQRKpfGEYHgEd+9U7+1l+zwynDFuuB681Ys5Ug0+cHbIzqFZfT5hzg/j7U7dSb62LUN2trpd1boACp3DtyRwc1iBY5JNvzM4OAWOST/WtK+gEhSGQnAGCwHXH3T+NTwRR20ZVYwXI64wB+XP50RstQersWtJuRaarCbtdsa2iQtk5G0nk/UE5/CotetIotduoruaJXXCtu4OMDBH1qt5DSFHuEDEIYweg5bP4dTXXXqLrNpFDdCFLhIg0UsrlAxB2sjN37MPrjvUOylctLmRn6K0mn+SkMgMdyCQN3Bk6EZBxgj9QKsS215p+opI73E0rwpcBooc7c8EADAGDke5FW30q30jTfNuriOdYmMgWBMBSVKhRj1JHNT2mqG8sbywljmmOwrGFG5jnrjnHPBA79uTWTlrc1S0syIrJq9zEt1ayR22fPt8rzkdjye/6YrmrxJZ3e/E0bxvcSAJKcCNl2jJ+oI/KuguLYf2ZYW9rO0jQiRI2BETPlt2F9x7H0rCklmvVuLbUU8q9hQy75Y9rSgDB3DgEjrnqRnrTi+wSXcqJcIl6VYzkQgx7xw+Mc/gDyB6VBrZ2XcDu3moIGbf/e+nrViCM3+lPJGQ1zDIm/HcAEK/PY9D7getII2voGtnGwK37pnGAPUZ9Pf1FarRmb1RFZ2kd1p1zLFeQs6xhWVlKuq7gfmHQjtxRb2jRiGWF3nMo8oBVI3n157Y/lVmSwMeoPDNEI5nThIUIGzHB3Dgg460XNtNZPFNbR3Mk7kKVyxXb3Bz+nPWqvcjY6GysY5NNNu9xNCyHDMp2lWHQ+/51Cspju4reSW6kc55B3o5A+mQcc4/nVONtYgkEqLbPAwyWYN0z1I9R6D0rXhivpj5lzdwhPlcLGnQg5DAk9f0qNi9ymYUTVRItwYbp48GJxtDjtx/gas3kOm2WjxMoEdzIu5mALKxyQyAjjjg1Hq97NbfOLncijJijRVP4tzx9Ko2q3E1vcwtBHLbRRm4Ak+8D1bAPXjn8KiaurlJ7oi1mX7NawWe/wCaXy3mIOQRj5R+mfqfaraW0U+k6iyMBNblpGhOPnwFwR9AWqqkYurXzP3aSW0e2XceBF1D++3kY68itnQNPtta0y9eJ5odUi3GGB3wJIwOT7ck/oKh6IqOrJvEWqza74e8MTSXDCeASruGctjaPx7VzLpi9d5v3U5dZD/dYgg5/T8K6Ozuo7a8hht4FupLGXaYgdoLEZRh6DdwfwrAutRjv5lvHjKFmDyFGxs3D5vXjI/IU4XWiWg52LVlMGuNPjmluI7q3uPMEoJJHzEhR65HHsKsmwiS+upYo2YiRmyMZGTng9hSW7ma9jlswpsDhmZT0Yj5j+f9alu7a1vo3a6gQNkkOTtYDPByME5q76kW0Kl8UmhkUs7sg+YO+APpxXOMrXNxbsyMYyRtRQT3wSW9hWxKNQm/cWikQDgPKSxjxwecAn2/nU9vpl3Jb+VIkUrYAV0Yjd9VPQ1a90zepz9zKls0iQSqZg3KlRjByDjP1ro9E063sdIvr7UpPs/mosVorLmRlJyZNo5AJxjOM05tJs9Ht5ri4hiuNRiwRBu3LAxPG4dGbvjoO+elUJL+Z9NmWQ7p2AnuCTl3LD5c57BemPWpk+ZWRUVyu7C+1CSaK18vctsH+7jbzjJJGTjr/Kui09rqHyGMim2uFyssc+zcQeAMZ79Qa5+0t21EWYjUyXMSCSZVHJjIHz++AMH6g1N9oJsba1DI0fmklG+7IASB+mfzqWuhSfU17qB7mddQgu2M8UokkQDg4x+vXJHB9BWHN4bvLu7fUba6VRcsXcNHuGSckHsRmth44L52gMZjhhjUtC6FQx3EDaQeO444NVrS0N5ZW7LJeWkjMQJFuDGjgHjg/L09OeKqLcRSSkZL2GpWHlRzys0szmOIK2RuHIyDV6P7TJbxvf6UkZzt823mVGz6lTxitbUIJLLUIZLqQfZpR5LZUkZxxvY8kHB6Y5xVmK4ijEPlAI86kogXC4GM4PbrTchKNjNt2hnuDAYLgNEnnDZEZRt9cAkfiCfwqlpi3GpR3NvPqV7beeXjghmt+MY7kjj8DxV/UZr+31AXEQkgUDag3AKc+2OeeefwquNXn1G5jtbmQ+XKTHJLncSoGW5PAxx0pX0DqWLG5jtYftsILSW8nkzAsc7SBgnHbgj1/OrUMEtvYzRwyxc/6yKbB2LjJcHvkHg9wR0rlob4fZ72zSUO7tyy8Bgqk5/Otf7ZNJpEcM8ZSV98iDo3l5wM+nUnH0NZyizWMkNnMdxe2d2GuIrhJd/you1FIJwzZB/Xoa3rm3Go2Msl/dSOpZ450M6RxAKeOdpbpjpVHUr6zFtLY2unXH9sJF5KrGgJIAwSx6FCP73an6X/AGlCqR3enJco20yOJFYxsBgjGRkYA5Bp62TJvqx9vLHpy7LG8muIEQNHbIVYBM4IUkHJHUA+9M1mS4vZYbCOeKa0mCu5H7uVAOQSPr7AitV9at9Ltne6huoUT+NLb5FHvgmsTXdQvrq2eay0u4uEjP8ArZIwOOpIX7xqkru4m7KxppFfxzfvbi9EYGI9soKH0+YjPvzVWybSrGeZ3uJWuLiUgxOGlO7POFxjr3pPCljBO73txc28t4wCiAAOsA7Lg859a059TvLVJUvVtptueLZjG4Hf5X4PbvR1sC2uUb83+nao9zdi7fQkiBMancFc9TsB/wDrVat5LWdba4tLwFJAdrOdwJ7rjBIxx3qD7fAZRdPZatCzlVU+QCGPtgkD9K0bmeZ7WaG10kpuGd32lIiT6/Lz9TSYGS0MNzqMrT+UIkA+eVWjLPjqpznHv+VZmup9tiV7DUJ53jdQY4vnV174464569q3IoNQuUibU4UkYAgT2cjHaOPl2nBx+dVp7VLaeCLT3ljkwX+zqjKsnqWbHy84pp2E9SBdI07AzJAAx2p5jAkse2D/AEqK/wBDkg2TRwwuy9GVcE59PQ1o20Eeq7p5ZJ4WRij27HIDg4IY4+bp61Xu9EiCzp5SRIx5EG4nHYkf4UX7jaMq4RBAgmiufNJPloyqdpx61JawPGiLuuigXgh8Akf59aztUsGVLdV1Ehg2UEgG0n3OfTjFV4bjUYrkLbSeegGTkFEA75z1/pV2ujO9mbsSWVyfMnByTyZOh9P/ANdFrBbXEZ+wsjBTtyBkD6GqenXV3fwyiW9tIixyqBvuAcD61N5M0I/0y4j3kAr5QUDj3zmlYaZLieFj8m5k6EfNz/Skjv5vPMLeYr+rKcVB5+rSMH0sJNbZ2gykHd25/wAaSV77eiG1hjZxhpBlyx9B/dosFzU8yKRSJw0ZXv1Bp7JMqbIiCucqDyKx8XsLhQ8TY+6CTz75PapVvpoXbz4ZAxGOOf0/rSt2HckuRGGUXTCCWQ7V3H7x9BVK5hkt3Yl2wOQVBwPr6fWtBb63mAHyFTwGPUH6Hip0xIqbJFkYcZX5Dj3wcUbCtczI9SuooiDL58IxnJyR+NPZbWf955wRj2cHNXpLa1ly5jjRhxuGBz7npVWbS3QEpICvYdR/9andBZkVnqMVzbvHIETUTbqG9J0PIB9/8axtKKQ3CJChVGik3FsnLc/y4qkgQal5lyzB7mIiMjgK2cf0qS5IS5XZPsdD91lOORzyPWny9Cea+4/To4/spbUDiGdwEgi+Uykd2bnCj9TWlNPGNsVhCCmMFITxweAM/wBa52WKVQHkwYym1NpyAPan2CvG0cTOfJkzl8cJ703G+oJ20LFzqJivTIXlU4H7heOe+TRK0cnmMc+am1vM9ie/0PFXI2a8iEkkqw3g6yqQRIvbJ7Gq9y8drOFMKSQPH8yjKgsOQCeuaNGD0EjEEjy2V98pIzBcHhkcdiO4PSo47OW8tXQqft6yAR7W5JGP51BfNHdMlygVmHytGPlGeoArZ8M316tzPdyqiw2cDS4KBVQkYGB3NN3SuhaN6lq+VtEgNlKbddRbbNcxqd2W9x0woOdvc5PQCuQnvGnkZ5M+ZtbcxOSTnrWg2qMl55kdvGJXO8s43u5P+0f6Yq8Lu4uHVZILJV+8XmhU5Hr0yaaXLugeuxY0aW31LRHWYMZ7Vwx28tg8Z96Nj2ps7PfEJXcebMJd5Vs/dGDgcY9Tmk05GmWX7JdhVVHYpBGsYJHODxnH1qhDZvsjmE0fl7gydzgdRjtUW1ZS0Rv6vqCXWobbfdIXO0kHIXA+UAdsY69ap6F5PmrZSjylL5MMwyVJHVW/p3qvamKAXss0ywO6gQsxHQ/exjnOBjPvTvPN74g08xyAxht5IX7u0EnHoPbpUculir63JvEcd1ayM5t5Bal94njfepOecH+E/wCFEV3bXsf2e7Ej30SH7PcsMMQf4Gx94eh96jhu7s7rjTLuWK4Ix5B5V8HJUDoeOQO/I61avLm0KJcapZlPMVS01r8jqD0JU/K3J9jTWyQ3vcybQC5yJlwwJ2uMbgT1B+lQSmK3gl8plmLMpff95AOD+Occ1tTab5AW9tHS5tLkZE0ZwuenzA/db1Fc08ksLLFLblCgIbeMbgTz17VpF82xnJcu5PpE32iSSxUsQwJjOecjn+QqnLMCWCnALYI9s81Pb2zbkntUVZEO5drEnI/DFabaZFeqJ/KKyyAu0ag9e+3157dRVOyZCTaGvJ/xMJI3HTlQxxwRn8RikeNrK3d4Z4ppgMmJ4y/H+yTV6W3laZGVRG3lqjAxEtkDGeT9KuppVzKpke5KAcszkLwPUAfXnNRexdrmZo4GoypPdXTxIh/1XmYye2Ony+tdNZR20+nzQkKTbj5huGUVuec9AcfpWTd2trPGG0q1aQrIivKuSMA5JBJ5xjr05q/pkEp0nXDIi+UI+WVBuY/MMk/7oGB9amequXBWdjNuprmGO8sZIkXT2eNBJznqvGRxU1jfNcuwjSTadqpGmWbcMYPHOeB+VEskE1h9kncuzR/u506MVYEDHqBjHtVea9dbW8ggjj01RII/lc5cd9zgZOR6ce1RKPMrFXsavi9w9vZzS24eXB8yMMBGsnAbcV75wSBjqa5+08VXqSmC6EV1a42G0kQbOnOD1U9sg1s2UMUuizWEssTyTjMToeFkHTnAAz0riord1nnjeMeeMoUc4I7HHvVUoppp9BVJNNNHT2Wkw3e+70GSWaBFKXFlOB5iKeSOMBx37Hj1FQWzwW77QsqwghsZDryOoPGRUGlahc6Ldw3FqcSsuCWHDgH7rY6dsGtfXLmxupPtdqgFldHeI1Ox4ZerpxwRnnB4IPFDTvZ7CVrXW4lvdmFnW1AltAoKAHCI/fGT346cVdgM9xIzSQpg9ASWx74AFVrG2hvVWVFZZBwyKowfrg8/lVy2tLuyWP7NdPcKWJkEg5IPTAJ4x9aegFaVNQsZFWOSCWKR2KeehUox525Hb0zTBrBhuhbXH2NgQQ3lAsAx+uMn2FXpJPtBe31AhIeAqGNhu57nnH4VAb3R7JnhsYo3mOfkhXe5I7H/APXQtegtupnahBLJq0Ntc3u63YGUxqgTG3nHFM0e7aw1S1PlDakhkBDM+c8NuJ68daSLTzd2E13dwSRXLybgh67QeAM9M1ZtpvLmE4gh2PEyKqsXYbsZZj3IGR7U5LSwR3uPm0yG3h1V43aOO2ka3kDDKlTgr+HPWo7e+j0a8tL5XUNbAuADnfk4x75A/WrXijUBpmrwGJBJBe2ym5hPR1I2j8eCc1kyW4e9SHO63e2WEOw5DEEqfzxWcVdamsnZ2Rv6/PFp/iKXW7EgWl5brKMjA3Ng4x7nH5Gsp9L/ANJ+06d9y5JkVdwJPOSoHfB9Oo/GpLhnj0XSZpYRJbeQbSdGHBKtx16H0qC0uktZWtDCGtSQVSYhyv0DAc4PSkk1sErPcr3Ea3l00N0hsr1BuVojhX9yp6/zrRinuHKvdSW7sCGCsn3GHBP8+1Vdctory/S3tBM+5BNiEgBB6jPr7YqW2isrORZdXuDcR/disLVcTyHHAkbnYPxya13RlszS0rUJtRhfybQozZ2gP97HGQNvTjrUMmsCzuEWGNy+0q85lJSPOeF46npnHHamxB54pJVhNmpUt9jhOI17KMdz9e9E9xa2yFI8TzqPlEILHj6dPxqbXZV9CnNdbn8tYbs7T86ohbLY4Oe46/nWZeL9pumvLdLjyyvlyF02gn8fYVf03UJXG9h5JVjkOpJJPPA/+vWLquoNcSiV334Yr5bDhfYdsf8A16uK1siJPS7Oh8C3LWHiDTrq6JW3UtHk8jGAB/MVm7FM19aqoWQXDxoeSASTyPwx+AqLTYGGk3Fw26FGnQiMqcblzwPc5FTy3MR1Azz3PkAztv2qTvY43dDnjgfSk17zsF9Do7Gz/s9omkuJWDx+W0jkKeuc9eRkcdx+NXLXUL+KyiSTTmmiACBN4yRj72DgYrnrdJbS5ubyO5s72MIR5RkLOpA4UBuevWmWN5qESxmzt4CzAAyzyYbryp3HIOegHUdKnluVzWOls7F0BNvLPaqeRCZBLGv0BHH0FQ6rqFzpNoWuRZSIM8hzG5+gYEGotZl1KKC1iaaCD7XL5TSqrAIccncTU76JZKkLXv8Apcu7aJLhiWb2HPtS82P0Md7+2ubS3e3stUeM5JLnjn0J6f8AAcVlXl1fSTOtrAtuoj8qOCEFRHjkYPUnPJ9c1uapcXoV/sxuIFi5MjBXX8MjOT0xVTyL+UJJFesrOp5ljUde+MAfzq1bcl3Mq1vjFPcDUIVkbYPKDRjer4GPmAyef60izsNJjnlZmcsylixyckkn8TUclzLb/MWS5eNydwOdp/hJPrk9PapfssseiQXQZlBcqkSruMvPzEj+6OB7mm0hJ2OpitdSudSiN29sGgC/PtLTohBxlgeRg/Q1Ppk09peahBLK6OCkjMIwQUI+8ODwcdMcVzNnrSuIYpAkrIwALg7lx0HPI7+tdqkhu3W4gMaldoCOmc88YbI+lZyVty4u+xVl0u01eSG5N090wx5REivH1z0Ax6Zp9jqepi8uIY3tDbxkq8lwhWQkdSEU5x7kCkvJI9LnuZFuFsp5MFlhhYbiM8lSCNxHGR+dUPD+tX2vNcq8VqZYCNkksYVtrHoQPb0o3V+g72fmT6r4eOs6hBeXFzBhcZEEGPM+p3ZPpUs19N4e0mQ3dvavErAKkbsoZT1GHzzTryG7giCpp0U7jr5dwFz7jisHxVNe6vY29tZ6NdwmOTcSQGVgB2I601eVk9hSsrtbnRzXEEcaRwWk4Dx+coSMhQOvGOM/nVe1gN1LJJe+ZKsvyoBLhkXtgDHOf/r1padqdq8SpehrZ0AJSdCm3+hFX7W5spIi8FxbtG7ZLowxn0z61OxVrmOl3r42CzNo0EPyt5sX75gPcHbu9uBU9jALom/eeadkJ/dMfKaJiOVKZ/nn64qN9Xs50eXT7e4vwcwkwwfKWxyCxI45/WqGiaaunadL/aCXH2ucFHWCYsYk7Bcnt+NPoLqSWkvl3M0uns3nXRMzWtweW9WGOVH5iqmp38lxER9jvo5kOWEcyjn65/TFWdHt9PhuoxOjW7vlYbpk2ecp6qzdmz26Ht6VpyaJHbid7e8kRnHypPhkVs8bh3B9z+NN2TFq0YukT2UswZYJYpwzf8fLqrZx821ef6Cn61PMYwl4YIYyQVG3zXA9gAACPrVLStEZLv7VqIea+Ylm3AAIccYXvx36VNplyWuRGl750IBjfdwwbsCh6HtxQ0r6CV7akclrBqDyIubCR2xFJ5GBKvryevtxUlzodpBauskzOjYEm4lifcgHitTy2WSZMNHbjhSybt/vjsM1malBcRksLpXhB3OJD5fHoCelFwsVI9ES0gd7OZzC53FPN2qMe5H86htdXv73THmiiWRlJUAYyQO//wCqpILaaSO6MjpeQyEhI2n3ge2Rxj3p2jxmCMLAixrk/wCisOevP1NV6k+hWsJZLo/Z3hdG2+aFbPHPPPar81tDPFPbSybIjgeW2OO/HfrWbqKAXBt2uSiOQ3lq2Dj0z3FUtS4cnzftEafMyqfuj2Pai1xXsacdjau6Rm4jeVBgASB2H9alayihIZZeQehPp6VzVpeXAkllYMGOCYkyu70Ax6AUn9tMjSKIghJyAOQD9KfKxcyOkC3cZWWNW8puGVgrH8qvW97ESBJF5bdgoK/p3rN0vVjPZB5gPMwAV71bjvLe5UrJv56ZyQPapa7lpnFy+WLWAPLuETEq+0855xir+p+VdMlxbna5j+YKe2Oo+hpdY0v7LZRLJOjSjpGD1/CqdvLG6iCDckojLxntu67RWm+qM9tDRskuJrEfaIMxS43DhGJHf2+vekFhHa3CvNcl4tuEWJdxP1HTisyyiWeyb7bLjc2RgEuR61dtpDJA9vaTShEGQGT7v0NJoaZGt3Ej73tHjcNgbQQjL6kdM0/WZVktA8LJLHu3ZHVceoHH48VVlkM0XlSGQ/hhj/8AWp8FtCIvlyj9Sc807Jaiu3oZUfmNDsjXG6QFSOuemP1rr/sksPhSW2dw1xLNj5iPmAODg+g24/GsXTmCzF1j+dCWWTZ39a6W/gvPKtPPQETQLJHvOcgjsBz1z7VNWT0SCMdDlYNOuwoZmRYweSTnH+FWdFWW6+0eUZWKEBTGdox6k1e8lYUeO6iknkdSUi8zyy2B93gk+tTQ3b/2ZusdPgt3IyqqxDKfXn8D2p8za1BKxPAZY5YpoY1YKWEh6ZUjBPPXFZkc7WCTADdufbtC5KKau6PDPK3kuZZZ5CWJkBIY9Tz0HSixRbtriONyJJdrhTgFsZ+X/J7VOzNEtDO1G2aCWGSSEy6b5YVZ053L6+xHcfWtHSbeC1eW4s5ondoswq2CFJIzwe2P51S+0X+ms6oHa3fJaGaPCt25BrPSSO5vJMxpAtwo+TPyqR29gSPwzVWbVibpO5cuStxfzKJIYnmIZGUhVVh0x6c1pam/2izfT7stFdAB1Mp++fTPQ/UVzVzbq00iLkNGcEd8dv8ACr9pepJaiymSS4jTLLzgqe+30/rScdmgUt0zU8Hysl5e6VLGfsl0hJifgZHp9R/Ssx7KeF5rXzGmhVsBJOmexB7HpU0Mwt/IkaZgWPyO3y4IPT2NWfPhZ2uTOrkHYQvTdj+v86SupX7jdnG3Yy47yeK4W0nDwMwH8W4Y+mO9bptb6VBJAXAJGz7oAHrjFUp4pNRuIxJbRWkZBLSOV80gfyrQs1hS132mqPDGDsxuDr+AbvVyJiXo7Kea3VJb65k2/wB7ac+3TP61Ue1uZ7kCUxNHASrRPu8vOMg4z/OkjhuJ9QEMd5dvax5M8pRYh7BTjJOetXZrGz2CR7meWM8FmuDtP1xjOKjYrcjsGaLTpLjWpoY1DErs+UFe3Hoe3tUmiTRXdvrtvpobyRafaAx+UZVuSoPXj9ay9SNlpyNPb2LSM2AJGBbntjJP+FaHhOS4Qz7xELi4jIdi33gSAVPGB8uQPSlJe7cqD96xk3Fw6F44pZDGIi0ikjDErlePrTJmtpojdru8l5QxO75opOnJ9OOD3qtewTSTXNrGo3LH5fTaSVbIGPpmohLPFqFwlmgkgjUI8WfvKOv9TxVpEuWpp2l29leTToga3cguwQMnpyBx+H5Vs6vpNlr2npqGmRGO9RdkkW7k46EHv+POKx4V/sqW0u4GL2bjJGMko38J9cHjFWNIee31RnAeKMgSGESfd3Z4Pr0/Ws3HXmiWpL4ZFTR7eV/MjcLvQAPE2VZD7mpo9PLLcsbl/tb42CJcopHQY6H6n1rZkuLS8vo7b7TZxXL8YdsE+gLDr9DVpLWOK5MU5WOZeqMwBHfp3+tPnFydjN06bUY9Tex2217DEoLzLHsMZPZgO/0rdWK/ZioFjEmep3yM34cfzqnNFbXMYCR4cE4kjyjIfUEck1TutRm0uFftN2lzE52xiRSJvoNo57c4FD97YPh3H69BqckyW9rc3B81eWiCRov1Iy2f50mn6Pb2AWQxRxzKu1phk5GOTz/OpNOW/mhjdo0sJJCd+7534PHB6fjUOqaZHNbFTdXVxOXBxJIdjexUYAWhO2gmr6kWoHS57H95PBcbPmVfNyS34flVDSI/tNxLAFNvawwPcTEcNtA5VAehJPWrMqanb2iskNmGzj92SmF9sjj86q6fqSz3c1vIpVJ4JI2VSGx8vr65HT86He2g01creMXeZbacNh3to8qP4V6HB9AahtDudhNLIqo+AUx64HHfoKWWGK4W0e3JDLtjAY5Ozpg/nVDzFmu1AzGom6r0I7HHrVRWlhSetzs9Pm863uLOcQmKfcSH+6XwM/QHhh9T6VyrqLs+TNBdwxRMUDP83lcdN2AWAPbtWvHvthuBEndQe2Oe34/ma1pZLeezbc6ltpVSxwSSOhz/ADrNPkZbXOjntOhX7IkN9HLHKh8uJlm2ZRj0z3Gf51bfS10tfPis8k9HWQuevX1qW8tdOuJHt7OEx3Oz55ypVYlPc5xn6VY0uG4awQ2+o3aJjiSaNXSVeeVB5A/GrvfUi1tDFvTcSvcDM/lyRbXBj2KmCPTOM9Dn1rWsdPn8mLEbRwKQ0iMBuGD0G31961bezuJCSL0ydm/cKMfl+VYl5c3dlrMdrrEh+wyD915C7FkPo2OePSi99EFrashffq+qzQriOygk2soPzyEZ+UHrjrUeoaVBOWRCyJuDFTxz0yM1ty6PaGNhaRPbFwDvh+U5ByOOlU5Li509Z4Z5UvIgu6GWQfMpyBh8H3Jz7U0+wmu5BLcLZ+G47KRmknaYrE7t/CMZPtjOBVDT9KiSGB5Y2kkLkmPG8H6DvWqdGvdbmzPK0Nu42pGy7WZfXPQ5IJx70reGrjTQRuuPLcYyjtgflSTS6jab6E4sXv72RptLgyx3GZHXJ46kdarajpM8AGTNLCeZIiPvHHyjPQDP5VZSDULYecWa4ULtK8JuGc9fWrEWu6lLb700vzieMGcBv91gQKWvQenUzLW/1W7RrS5m+ztGVURfZ13MOxwc5+oFXEBvHhg1WW4GDuHksQQ3Iyu0DGOpLEAD9aUttf6/OXu4Y7U2jlQDliCRnOcjjp3rT/s9bmxEJje4GTyX2Jn3x1H0odkCuyVDo9pbNDNqAYMfM4lLlmAxknqT/njpUIultdRto0iMtndEqGZgMsBkHB5HHfitmCw06LShaQwtKig/uiquSxPLdc578VjarcaVFEltetcuXQYMu4EY4yMgYNStSnoQ+ItPWCUvcF0iwNhROFwc/MfWsWezbUJYSXkFpCpFu0WSrrnJOR0POD9K2dF1CWRZLQyTX9spwvmxEso643DIP5VYsxo97K6W8EVnMMtIksjQYx6jIGPeqvy7ktcxmQaFYTN50zzfMPlZw2ePTNNtYN17aRmOeWGWdYllinG3tkgHtzyK0T5do0iWdvDIr/NvMrbTjuAelR2DTWavqBuTNcM6SSpsO0Rg5KpnuMZPqFxQ5XQKKR1HiS6FrJdP5N3I0jCSOW1I38k8D249D1FYumXM+qWyahb24jv428tJEKpxnkOM/mD+GKv37zSRTM0flWSNut7yJ8+YrHBBHUMP8Kj0eSCC0MyyqjMwM7zPwzMOCxzjnHB9iOorOOkbGktXcfdXl6t+1rdWUJUICs0hYJk/w5AIH4mnWllejIaC2jXBwscz7SexAxnNTi4eVBGt7DuJI2wMCcfyrmphcah4he0kKTW1urNK8OVy3ZSw6HpxwKpakvQdqIkufEcekXbILYqrsPOYBh+P3j2xiujn0XTUJ8kJaswG6KMDa2BwcY4PuMVSg8M6bLKxk82W4OCY5pMtH7DPbn3FaBt7+1kSCKeNrZRj95b7mHsGBHP1FJvogS7orQQSwCRbRLRhuzsHyFjjvjIz71h6lqmovd+XFJBDMn3rdkMzMPX5B0q/4uupNKso7iEQSvvAZGwpKYxkAc9ax9MvNISWS+ea9tbqZAHM+TGTxjBAxj61cV1Jk9bIu3IvvLuDq4EelEqiRvhFfPdxnI56ZxWhZ6XpFzaxCZRLjCqwkeTp0BIPNVtLuLnUNI35QzsxUxFgY8Hqcc/gKvWWn6ZAHC2axzE/fbADHPOCOB06cUmxpXE1+eWxtoWkl8m1R9omIDNGSOODXJ2FsNamS4ked1RmQXKusUsvocDsPzq/4vSPNmk/mGx88ebJ5jHy+ehXoM+vauphsbRbaH7JBEYMfKoRTkexx0696afKria5mcvqmmpaSRGfxFdxI7YjilcZJ92HT6kd6PtUVgS13YTzyF8IWXzCQf4snIFbcWgwLI6G3hkUncpYjOPRhj8KSCK3guJYYE2+WMEdApz0PX8ulLmDlKp1WyuM21vu+0RnKqz+UH4zn/IrEvkvbXU3uIvnnMeI1mlDmId8duam8VE36Qrp9vI80UhDsAF4xyKZaahpt3HEBDi/xtX5DvyOD0HSqSsrkt3diQzW+pI1veO0d3tDyAIGX8M8fkajhmtjA8AngI5w0YHzjPcdM/rWnFFbSZgA3uv3gw5471Wu7WzjfJRELYJHHzY9c0rjsZkcASRd80jQkchkPB9cirDpHbkpL5eSMJvUEjn17/jUyyxLaFCq+V/CBLk4Pr9KoRx3NtvntpTcliN0bJgEY/u0ySrdwxrMrkxtGpJf5dnTnPHWrFnLLMpcFgjfdyATnt09vWoLopdTlRawLJHgSREkKc/T0qWWbYFJiSEY6KTuHpjt+dUIqrGjoIjLcAtyZGBC59+MVkSTIvnJgbo1ypzjDA9q0L29ihG6NWnkHA3KcKPrVK2sHv1M8h8sOc/KuQfoKtLqyG+iCBEuSSki72B/dNwxPseh/nQi3NvgyKI2AxjJBA+nSrcenw24bETzHsGwKsoJSipLGksPeJwSF+h6ihsEipbyywR4cSFBx86hh+XUVKlzpAbdcb5HHYKa0ra0MKko7SJ37n6D1q0NFtZ5UuTEFkJDMSTkfgeKm6Ks+hQ0mJ9Q1W3ElisFq5+aSXLOV9s9PrU+s6zdXrStE0aFWPkqXChU6Y5PoBW/DFBbyiZFyF4Yg5JHOR/nvXO6l5envI80UMsyrlHZRl1P3SPXIrO/NIbTSKmjX4txPPMX+0qvzzhw5GTwFGOKtJfRRImyO7EzDOPKOSPftTdAsPsTedGrzSEESBOFUHkgeprW1HTJJNNE8ErqwkaOZAoLex9s8fnVScUxxTaMRtXkinARhGjDDI3LsfYDp+NZyTCOOULHlkG3djqpOR+RFX59PS3D5G0kYLk81nxXAW5NuMP+7ILIM/NnINUknsS2+pYs9Vmjga1uj50TgqSWG5B04z/KoTpRVuAt1A4+SSNvmX6jtRa6TNI/my5jUnJaUhRn8attpsXnpsnLsM4MMZI/M4H5U3ZPQSu1qZtxaTEJKquXJ2syjOSO5qe0tJWY8RFxyFi5IPYk1ry2l4RAlooMSrjyZEbk55O4d6twWty2Att9mLcM7MG5+gpc2g+XUo2xnjkKX6B7eXoiruMbY6496v2qiNxAtlIyOSUAjI2t7HqP5U+8t7mzsJLoXFtKYQXB8sjP4k9a0dJt7m+06JtT88TYOV37Bg+y47etQ+5ouxWQwtO1vPIBtwXCKGdR/tdh+JqO70KG4tisJW38w4VUG4gdyfVm4HoBwOtaP2P+zxI0MNtFEDlcttA9SxPWg39vd2siWPnYI2m5jAUD1wzcH8KV30Cye5iG61KzmjsNNnhupEXBhWD/AFY9znGanvlLHyryVIpHQjP3+2ckAAAfjUvh8XWn20sQgheNnZk+f5iPcgcmqurokky39ygtlyN779wft8o6/Xiq6i6E9vZRxwRyieaUKDtkZj+QX/61ZU73EL3MsaPBI0ZjDgFWPI/WrrX8SqoF2BEiqFSNQMHt1/CmxXUd7LJHcufL8klE3bmc5GMY5J60ah6FC7hmvNNt762Je+tv9btJLMuSFf36VWZRPGbtSIctvnj2Hg/3h6Kf0PtV7TtMurCRJIpGjmXdlQ3AB5A96ku5bqJS9xuDjnzIlA/EginfoifUbpF3ZvmwkmRoWy6swJKMB1PYDtVm10SORGlik86CQqSPMOwn6D+tVBC0sX75o4wDkIqKCf8AewACfan2EFxHcxyQZDYK/L8pIP5g/Sk9Nik76NGtp+iQ2029Iod5OSdnAHt6Ve0iS2utWu1HkzxLGoO4bgrgkELntis69l1CxtUm1BbU2ittIdirHPsOCasaWl28ouLV7aCykGY4GiO7HrkY5qWm9WUmk7Iu6ra6dEjTXFlbrEoy0jYTGPpzXHQ6de3V+l1YWLGx3LIFU9BngqWPUjmumm0KK+fGoalcyx53eU0qqox9BWnbRQWFmsUS5iTAQREuWx6gZNNS5UJx5mUYNXgEskd5b3lsQOGmgOD6AEZqnNrX2u/isNKAMhJMsk0Z+UD0X1+vtU15rYknhttPljnuXOcFvlQDu3v7VXj0CG1lkvIru5junBYvGQBknOApBz9M0JLqDb2Qt3p++dY5o7iVwP8AWuQyn8M4H4Cs7ULeDThmVgoJGwjoMDO3PY561u21/q0tukkenJMvK+aXCPIOzBf6Vmags0cn2i8tbyZUBZlKqq4xnBxQr7A7boxpJvsms6cPLAa5RJHZhztbOAPwxWfbPOJo3+6oJKuVzjPWtS4s7vUj9vupY4Xk2yQKgzgfwhR14wK0rPT7b5Uuw8M037wwqfuH+Ij2PX26Vd0kRq2VtOngtpti3MbyfeIIIOD+h+lXJLdp7v7I5i+zTAzRsxww9x6HrmpRpdpCTuMyl2C5kXBK559sYzUWsaYNyhJMWgO5CDzCeMj1KHr7dah2bLV0izBZIkTRSNHK8IKFpCWB9Pf9cVB4dS41CxllCxJtlZNgJ2tj+6DkCs+/tgbkBLm8Mk7ASPH8/oOg9R3HSuo0/Q4baMlbq7tolGSvnBFA/L9aWyDdmpAvmWyCSLCnGVxjB+g6iuP8SM2sXKnToppprLDLKhwhYkcAHr0/DFaep2H2+FbfS0u2bI3XbTyCJQfqfm9MAfjS6e+rRhrbUrEyrBlYrqJ1XcOg4J5GKUdNRy10KN/eaiII2aAJd45UHKH6etSaFDHcQul9bw7ySSrqDgk9Dn+dXp9WsfPWDUHms7jCt+/iGCD6EZGKvQ3mntKn2ImVTkNJEmV4HdiOv0zQ3psNJX3K2t289pbpfW82TaAlY5JPkkUj5lx2OBwR6VPY6ncy2SXB0+8MTgMRuVmUdsAnJzTL1LPz11DULSeRolPPlMyRgdyMYJ98Vf8Atku6M/Yrx0/hxGOB2qeg+pzlxrD3V08enafM130YSkQsue+CckfQcVvx2FxcwRxyXaWxI+7b9Tjrgt1/KsrxNJczrbtp+m3P9pxSDZL5Lfu175OOVPTFX4dYgWSCG/WW1uGAVWuIGjDnHUHp+FU9tBLfUkuPDYIQpeXQlV9wZsEbscFhjDfSo47xtMhdNYgeNkU5niUtC49QRkj6Grcmt29i8duZmnupX2JDFy7Hpj0H44pmpzaodPlFtpkewqRiW4XJP0HXvxmp16lO3Qxtl9qv2XVbsQ21jFmSCIEliCMbnIxgY7Vq3VqBYtc3qrAqJ5hMTuGVcZyM96xfDNpcWyS6fqepS22R+5skkUsqc85IOfoK27jTLrULWSO41y6ksZPleMQIrMP7pYD+lVLcmOqIrVFWK0vhDIwniyHuRhgvrtAJx74/Gqk9rbSulzfXjSyD/VhUHlxHPRVbP5tV7UdKlFpFFZ6veRou35JNso+XoegPFc9/bE6W0NxdXsN1C5ZZVW3C46jJPXg4zx0pLXYbdtyWTSJLjUfOWRLtZgGkQABkXO3cF6Hng46Vn+IjFZq+m2TMLdmWaOV3yr8HChvYd84zmmSSjUp08x5vs5j2tFb4QSqGLfiO+APete10q0Nst3pumtJZHMc0r3GEKgcr39RwKG+XViS5ti3a6taWGgXVxMtwbzzYlkTI2B1X5vL7EHjP1p2kTmWzgDWpDw5jlhlQiO7s5GzsPsHPynGQWB7Vh3F3PE1ve6akCQW4KRIoDKXPVsN3B798Z9Ks+Grqa91yP+1Qrb4JY2uGyWckAIW9MMVxip5dLlc2tjXPhezfTYbNJJUjjdp7ZygLFWJwGX25Uj1WlsTPpt5JYXTx2jsMw3FuDEk/4fdDD0Oc9q0dKuo722+xLIBfrukhG8bnYD94n44yPQr71j6jqVk8F6bi4kuoohtltwoO05/iGM8flQm3owaS1RpX2nRXdsg1KeWSRByzIqgnthgAfyNYOlPLeaneW+nXt1DZ2oAWcqZWJPDDLEgdOwqPS9OXUoUutMnuLKxJI8nLMzEem4lQKdfJqOkzm6hku7uxP+tjyPMi/wBpTjnH0q0uhDfU1YdEtrWVnnaS9kkbJluSJO3BA+7irbSwXyfYZ4Y50CYkQsFHsQp/pWdpK217b/aodcu7iPqRvVNv+8oH86s/YvNlO6CNwDkNKm4n1+ZTwT9Kl76lLbQoXfhzSdNeS5ilutO28+Ys+AP55FZ+i6xreoajc29m0M0UGdk1ymMjOBkrxk8mr/jSBx4WcwWwyjKxeORjtXucHB9PzpPBN5ZTaOsMCspjAMqqckE9z+VWn7t3qS171loUdVbxVM4gb7J5bghvLAIPqDu5qXTdIXS7ZTaanN5y8tDOv7tz6AdV+ozXVPbSXCuVmkJX1VckenpWPJDJcao62szssKgSRsNjRnt1HOfxpKWlgcdblp9WsvNYLIn2h2DMh+Rj24OOaS41BJFMP2xbFlON86ZLficDH51n3OmSTWxjmiHm4O1yAQD2+lQaQl1qOlwQzXMxlUsrwzhZI1dTj5lI5Hbr70rK1x3exIdJm1Ftg1OCa13ZdUUb29BnJAH9KpX0H9nX1vFGiR+axVJU+UA9duPU1vWL2CEQXem29jdtwQIv3b+6uB+hway5/D9ncZC3E0sW8sN07EqR6HOOPzqk9dRNdiPUftEkRklESmPOTkAsOpU9s+9ZQkint0eCF7qJz91Mbl/AnNTyWy6VcK9xZJcRFs/aFj3ke7L+P3h+Vbjxx3JiuLKKCdehUjcG+uOVP+cU9idznlnS22mTTrhRjqyAn8wSRUV1fXN9shijFv1w27cWA9uoPrXUakJEkCxwKitgFy4K5984wK5S40+6lvwbqJ7aTPyNGAyOfc54oi0wkrEDaRdPIJBGsrrhg8TAbvZu1U7uUxCRohLHMONhycZ9R0xW5Ncy2U6TlcMOCCCc/UDGatrqVrfw7mIWX+IBcZP0qrk2XQ5DfcXUrImDEx2llxnHtmtqxa2t7FQhwi8YHzFz7Y6nNWJ4YSgDqqQ55G77w/ujHUn0q1HBcu2YYFhTGAZjjA9do5/Wm3clKxRiDlSzWs6sRwpA4/Wpkcgfvo2t0A4aSQAE+4q21lO7Mgkd3HJYyeWo+irz+ZpsPh+1+Z7tFdic72Ytx+JNTdFWZUguIEuRBp8S3JHJKH5R9WPBq7J/asiHa1pbL6BTIR+PAqO51i0sgINPjN5cDgRxDIX6kVElpd6jP5mrFFhQZW3iY7T/AL1MPIS1nUXEMaX09zdBvmKD91GMc5xx/PrVb7XDJGINShUpG7bHj5eFsngZ6j1H4iuhNpLhFtVSELwqgAL04+Ws+a2s7YtFduvmSHJOOufTHAqNGyraGeYzH81vfzbG53KCdvpzTo5JZ4DDHfXUu98ELjg+hbtn19qlW2s4yEtbSadT1whVfxLYpskS20D/AGuTYjHDRQfIo/3m6t/9aqtcV7FBJVvJJYIZmjRWx++YuzY9AeAK0xZWzQuVQ2+3G4r8hIx1wKoLo8GpM0lhI1spODI/EbfTua2zpMlnp6r/AGjGWA4/dBiT+JP8qbaWwkmzMt7PEiSwSRiRm48w4J+hNaEguDKu4wRgAlt5ztFQCG61BY45raaGVOCVQkSds56CmaXENUgmje5+zRb2iaMcynHUFjwPwpbjNXTJpbiMSWkAmh5USu+wPj+6ME4q/Ct8ZQbiG1iiA6LIzMT+QFWNNht7SBIbZHZIxtAx1/Oppnt7dD5siKuThASSM+3U1DepoloYuq6UdXtZLdZgE+8Cvygfh3qKzl1jRtNkF5FazQwx5UpLhzj6jpV2/wBSe3QLY6fLuYhVaRfLUk9MD7xP4VhTXt4v2iC8ETLKS0siy5ZVIwAe2Bjpxn9apXasS7J3IPDoGvXktzqMhuJYxlYnGVQZ+8R0HsK6RStxdLEsUjRIucgfLn0rndJiutCBuBFbTadIwJZQQT2yM8nHPHNbo14zqp0yxkmjyAuRtAHrk8dO1E1roKG2pHGskckkG2UyM7A7mwuO2P8ACodQ0ZJLdC8CyTE/3/u++TWlLqlvt8ySO6iRejG1fOfrjiodR1i3tdM+0xiWUAZG75CT6ZYfyzU6lNIzG0OztozNK4CKcsZc7UH41W06x26v9u0qIXAbKkSnYhz1KZ5P6iug0m3t78C+kmW7cqGUyjEUef7qevueasXk0FoNgOJZDnd1Oe5J7CnzdBci3KN3HIg3SJbRzMMIu8tz+QqpKb4AkWFvKnfc+zn6Gm2/mLLcTXEqLCJC8LSDjBUZOfr0qWzsNQu2DXLqkLDKurnJ/A0bD3Mm3iM/mfaFNs2fmVMMTj0VetX7K8exYM6QosrbY/tTmMkD8DXSTLYaRa+bMY7aMYBYnGT/AFrjtbuv7Vu0ku4Zf7DiIYTxxn5m6ck9BzzTXvCa5TW1TSr/AF/yUvPslvbRtuURszsfXngdKbHpd3aLtW8up4M5WOLhkHoM/eH6it/TJbaSzE9uzeSehcFePxHT0rRClBu4bjoB1qOZrQrkT1OY0jUNHhlW1BZbhjlhOCGJPTOQOfb2rS8lZAYo1j9RKEzkHr0xVTWzpM+owQ3sCXk5QjB58seuB6/0rm/F9ymm2ttBp0bWsUxO2SJ2GAMZ4zVKPMJy5VqbGqR6at3bpj7RfQMxS2skVSD0+bHQfU0200a+iSSa7aOd5VZTiQ74VIwAOzdevBrY0azs9NizptncSfaQJC3d+OpLkdeuKnmW/lP7uKG0Qn70h81z9FXgfnS5uiHy9WVLBpIIggaSd4+CNuCDj9Kg1mU/2XLPIyxJtJxKvLHGAOe5PbrSXllZearaje3DSp8qoZPKGPX5MZycdzVSaRNE1GOe4GLCQBFaTLtC2OxOSoP86EuoN9B2i/bI9GtUnsLkmOJf3kGx+B7Z47ZFZglE2tML7NksMW9JJUK79rckDtwT0rZ1GdpdWiuHSVLK3QuoSUASsRwevIx61o6BeWRifz7mBrpzuYjk467eOw6cUN21C3QpWtzavbpDFI11lcqHyS4J6e+KgurFLyfcfMcSNgpGcBMDk/hjGP5UazZ6VdSFY7OeeXBYrZqEKL/tYPc+v9KTTNM1aEAS6iiICRDE0YkKgdiRjnHp70abhrexbGnGGBTG9zDvBwFiUlfQkev16Vi61Bc21vb3F0s2o6VGSXt5PlkVuzEj7348VvC81aCRhdWtrLwVVo59pJ7ZDDrVWylvdatGuBI9sN5SRIgB5QUkNhj1J9f0oV1qwaT0RrQX0Nza2kuTMkuPKaMHcPYkcDHepW01fmUo3lOcs2/5SfUj+vtXLwaFe6fqYu9Fv9kGd00c7Erz1Pof5+9av/CSXdppn2m8todRtd+xJbbcofnABUjpnjPTNS4/ylKX8xsJDYtA1veRwSxIvzeYmR7jkcmuR1G21G01OG/8P2jx24TZLEqHsc8xnHbHStO8aee3jkhtLWxnLncWuPM8tc537cYLfSrE9tqV5Ftg1gxRcAM8OWB9mGB+NNaCepUtvER1mRra0ighYqVkNwCzZ/iAT0574rWsbEWNpHExluYk4TA2suPYHkfTpXNeIdI1O0Rbq0upLm7gXLzJt8x19MDrg8jr3q94b8RW19pyQajdBbvJT5cow69D0zQ46XiEXraR0uneRdxRXFmNkEikiUSHrnB4PXp6VU16xk1WKSzHEK7JIpgg4kU8DGcn3I9aZpN/bWdjHZW9hqhhhUjL2xJ6kk845JrC1bUtR1yBrexgl0+ycpmedXDyDPO0KDgcdO9Sou5TasdBaa5af2q+nagkNvdSjesscqtHIw6nd1U+zVpapDPcWsqWrxiRo2CyMcKMj72KyV0GwFjHZLpMDQOgediRuJ7Hd97P40h0l9Otlh0i+ubN1yEilfzoz7bWz+hFDt0BXtqadrZ28ttFbTWakxgENPhiTj727uawNbnPhqKS5iDXFu0gVld+Ys9w3OV9iOM1ImvXOmzx2+r28k1xMNqPbjcrMP4Qv8Jpmpa5JLHIo8L6hKXGMSRrtOex601F31E2raD4py5EkyPtkUERA7h9Qw4II7VS17Snu4ZF0q2mFw4yI1jUCQnjsetVdKs/FKs72NhBY2a/dtJmyOuTtzkjP4D2rRuNXlthFLFcR29wHJjDNgh17YPYHqfy60PR6AmmtTE1DRrnTtNto7+aO3v1jQ+RGvmSIB0J2/dPArJ1LV76S2+y3KT+RGNgeVcYzk7to46/jXZ3Mss6/abqaNS7bpJZHGHPck9/wrkNT1m1n+0WwZUBO391ltx9QSOn4VUE3uRPTYgsLp7TT5IUYbZArKd2Sj5zjJ4KkD9frWhYW9zc2ymNHWfUbyKytY92eFcM5z6ZCD86m8NeF/7StmnvluLDS4hu8yRypk55CqRzn8PxrZ8MXwk8a2sv2dINPsYZFtIz8xiVVY5P+0eST60TkruwRi9LmXr0MmneK9Q1TSt17Gl1IAvVoXVieMdBkZB6EZHY1d1VdMm1CDVp7YEqiyMhwPlKjAYDrtJxz/s+tc5JCWvJzHeMi3ZYhcZ+Y5bk9u9WpdQ/sG8tItQt8CWNZFCgFWQ5XaQfbINFnpbcV97m7cazBeKLWwR4bp8Krgf6te7Eeg9O5rWbS57l4mhvZGtwpDBiF3fXjP5VlR2bWtvFdaDPFNpsx3QpIm3Zxu2Mw789xzViPULjaJJbG4CqDuS3kSRT68cH8qn0LXmO1DwyhmS6tStldAf663fYT7MMYIqhJHqg1CG0mvY1tmBCs7+U0jem5Op/Lir6+ItH8h5re78yZuMmJ8n0HSsLw5C+rsLjWWu2vbeT93HIuwL/AHWxjk9evpTV7XYna9kWr7SbwzRQpqWoSW0m5Ztrq3lAj1bkisi2gXwzOYmQtayPuS+XnaD0DgdD/wDrrrb6O4MZZ44rlsHOSY2x+HH51xutrcPOsFzE9tpZdQbhYwx3YyB155qou+hM1bU7vTrmJNokjWSQ9ZQTk1l+In/fwy2dtcNdKCqzxzhWi/2SG4K+x4os/D2nSQW8sN9e3ATlGM52k/h0ovtNW6huY7aR4ZM7ZGhyG6enf61KsmU7tGFY3NzqsslpqGtS2Mqjc8UcSjI9nB/wrQbwxaaa8dzDdz7w2TJ5hyD6g5/pWhaaRbQ6atvDaCONuG3kEyN0+bPOahtLK5sLaRZEENugLiIncFA54NU5diVHuPlg1CO0Z57uEwohyWXk56EkYxmstV1REuFNxakoRjehBH1b1+uaks9f03WIjHcTgORjyLjC55zw3Q/zrWtri2Nw8MksBnKhiGPLr60ax3Q9HszlrnVdSRZEc6eXRcoQ5ZhyOgPetKK3mbc1zEz3OQ3mm4+Yn0AAGBTNR01tR1EmZVW0hOIvLI3Mx6tkeh6CrV1fNp1kkGrM08HQytGD9N2Oh9+Kbd9iUrbmXcxx3OqtHqU8gSVA8dtK77C2eTnv06e9aM2nwXMSm3EMEi88khQPWi0vbe5t9kUkKxuCHhEgIAx2pt/a/ZoEaC6eAMMgNJ5i49t39KL9A8yVVilXyLmy+ZRjzI2+UcdGU/z6e9YOp2H2O4D258lCOF3jLj2JHH0pmk39zql3LBNdzr5XP7pUAYA/n+Vbl4Le3UkLcsDkHyjn81bOcUW5WK90c4mntYgxK8wj3bwzQspB6cMD0pnh2a8n1KVRMxiUnJ3Fl/D/APXW5Hp8l5iW9nac4+VcbY0+i9/qazk0+60K2KwzKzTSYBWLkcdzV30sTy6ms9tdS7xDqbxn/ZhT+fU1nvpE0jAXbNfk/wAcs7KB9FAq3ZfbFjXz5lMp6HrirK2lxMf9I1CYKe0aLGD+Jyam9irXMy2c2d4lnFZbHf5x5BBXb0yScH862F8wBo4oGJz80kzhVP4DJ/lXM67DcaNOLmzuZHjlUKzvguvPTPvXR6bdLeWaSKd6leRjA9xiiS0uEexNH592C8l2wjdcKsI2D+pP1p1vHaQsqRp5ki8mRhkk+9R3l/BZsBcyBFIwE27mb2CjtVGO+YFvsGkXe88F5sRL9eamzZV0bBXI847FjTI+c4IP8q5HWLK/1bWEWNWksVIO7BVFHfk9T9K0L2yv9WkkVrq3RYQCsag/Kx6Z/LrTZLLxFbWrHz4ptvRVYszewyKqOhMtTYtrKVYRBG4EaALk8k+uatxRxw26xtCrt0JI/rWAbnxDFChktbXAA3u8mMfXnAqHTL/VtaupEhaO0t4yVknjG/J9FJ4pcr3GpJaHT3t5Hp9q8s7YjiTI5+YtXL+E5LT7dc6ldS21tJNny4jIAAD1PPr/AI10EGi2Az56tcsSN7TMXLf0o1KzihtdulxWsV4GHlYiU59QM/jzSTS0Kab1HS39lICzXyTAYG2ObjJ7HGP85qxDcDyWMHl+UOR5bAA/jWRLcTKF/tTQY5sKP3sCK4z649Kl1TxNa6bDGptZ0eQfKCmAB6UuXsF+5qNZi+uI5pGzGikJGmQAx4Zvc44H/wBeua1LS9Mne4jhnnuJlJCxW3zEMB34x6daqwa1ca5fQWNqGt7Z+GMPyttHUk9vwrqdO06204JHAscMJyTz8zH1JPWqs47iup7GZo+hXRWF9Q8pXiBEUCnIjOOp9TW5b2bywj5VQYx8o9KsSMZFEauyjHVFzj8ap3aXLuYbWbY0nLPnPkr7D1POPz7VDk2WopFuV44EEP2hY5ipK7m+YjucdaranZx6hpktsGZvOG0MecHtgVW8m3srlYMBWcFvmyXI9T1J/Grq3MYZo1kREA+8W+Y/UY4+tLbVBvucRh9GvodFuZhJE43mY5XbwSOO4GK6rTTYz6d50QF1CcjzGGdxB9KfeNA9uRKiG3UHcZ+QF/H+dcPpOoR6XrV8ok/0WRS0fkcDGcjHpxkVpbmXmRfkZ097dS3MvlRxysG4aMAAY9M9hTm1G6tbRisCxOAQDPKNo/xFZ6Xmq3FkFtxb2gl+60srNKqnqTx1x61Yt9MhvJOYJJ2JwZJlJLY6Hcf5Ci1twvfYd4etrbULaO/1IS3tzubmbJUYP8K9AOOK2r6xXWrJ7e6DwwyccEBhg8H+XFPVp4VigmsjLg4ysn69K0Y1CxJGsKoAAAuOM1DlrctR0scjp51nw9tgaD+0bBcqskJ5X6+mPyq1D4qsbqCRw15GFI3nysge+egH64rZ1OZLSHzZrlYoF+8oAC5/mT7CuK1S41XxDJ9m0q0uFtQQN7KVBHYuTx3yB/OqjaWrJb5djVu/EejQGR7KDzpWU7pFTbn6k80zTNButVvYr7XGjeMLmG1HQZ6Z9McHHfvVqy8IWFtYtBPvnn++ZehyOwx0qne6Ve6VGJ9B1TYvVoppPvfTPH50XW0WJp7yR2JLiTYEDcHJU9KaIWuG8wyMhU4CKf5VyVvrviaK2Rp9HilTbuLltpx26Hr+FR/8JfqsEga50xHQtkCMOrAfQjmp9my/aROhGnSvdkKAIvvyPKiuWPbYO2Mc0aw66faz3Fwgkhjj3so6ntjmqtv4yhvSkVvY3csrAkRlMZx3zmuc8SeJTqtlNY/YpI5HBJ/jwB6YHqBTjGTeonKKWgnhDTv7Y1C9unZ44cGOEqvyjPp9ABx05rr7PTIdJjxbopl2kPIP+Wn4dq5r4fy6imihIbaN4DI2CZdp9x0PcV0M91q6yk2mkRNKeGeS5G0Y46DmnO/NYULctzR0Roj5gj3yTynznZ4ivXjBOO2OntVu8SMiI3M6xKGyMkIC3bGeTXH6reeI5ZN0trLYW8KkSSWgV3I/2cnJA6461Folrod1KlzJqr6hcEkjz32EE+invzU8nUrm6F7xXY3xhjaz3qYd0rCaQbSMHBz3+lXNA0jbp4tyGeNlwBL93B5Jx6k5PPTpVTV9EtLPUtNmt7d3Hm7HiUF8qQcnk9q35LdWEce6YKCThpGxj0Izz2pN6WGlrcz9c0V79Irae+mWyjGWhXG5j0+ZvQelZfhDxDNqcd3biGJBaqqgqTh+SB9OB2roHtVlEhmkcQ4+ZBxjjk+vrXAfDxo7XXbuG3lZ8AshC4LKDj+R6VUVeLJk7SR6GscU6xyTRIjxsDGxXODzyKkjtp4nkEbqMkMWYE8H0HtVm1RGiGTIsh6t5pB789aqqyXUZFlqF2VBxuEgbp1GSOtZGpYuZ1s7dpGKhgDkhcZrkNW0Cy16Nbq3L2t9uIcmLbvA9Vz+vX1rRn0lYkeO5vLqWJ5AWmaXhDnjcv3dueK1rG3PmtHcwu0KrlHyNsn4Dn86pPl1QmubRnHpreoaNdDTJit0vBFyMhox7j0rZ0W6jk/dLIu4Z3MHG5cdFPc/XmtPU9B0/UIyxQwzR8pIhwye2e4rifEurjTbe0g0+5kuj5haSYrkLgcKCR+NUvf0RDvDV7HotqBJG75Yc5J/x9q5ibxRax6uLKRXu5o23wyQR793HK4HQjpnpj0rGtrXWfEOlI9zqUCWMhyJADlgDzwAOeOhNb2kaPpGkNK1s0huQoV5NxLHPTA9D9KXKo7j5nLYTU7uTUIpVm0+O3KfMvnzASZ6gjbnBHYmo/D2rXsqGLXonsjIVW3Z02eaPQnpu6ce9W5pLncLmxhimYj5HnbayknGBhc/UcGqd7quoz4tn0mOZZBtdWcFQR65H69aejVg2dzpxB8u6UbQPvKRnPt7CuR8ULp8dq39qGFpG+VTIQCR2xgcVTs7XXnvIvP1D7PboSVitiZAn+yQeo+uas+KfCEmo6fG9tdNLdwg8OABIT1Ax0ojFJq7FKTktEcLaxzXt4sNvKY7AbijSnoO49eprsrOLSdFIucxTuwyVRxvc4yAD2HrjH51X0bUNPnjis7uzitbiOPa0soAJYcEEnkU/UtHnRWexELBwD+8QMG9CDzVyd3bYzirK+5JqWvy6g32i6kkCIThYpiEQcdExj61antbiG0u5k24MJhilHBLPx+J27jWFaremTdNp9o5U/MY8nn3A7/hWtbPMsv75Q5Ixl0ZAnsMjH41DVtEWnfc5XTnuZb/AOyyKfMjYMXI6Dvn2rpPHsVtdaPpzIS724ERLckg9Rx6H+tRGBT4kIiw8dywmJUZMZVcHPHI/Go5rN5JZkhywtXUSL0Jzn+Qwfxqm/eTRKXutMl+H07w2usaZcybrZbc3kYJ6FDz+nWungu7CS32G4t0dhkbpAD+HeuZ0sLY6g08gTZJbTW8nzdVdcc1oaBdQalYNY74rprf93vYZOBkA/l3FTJXbZUXZJFya3urVml027EUbks42eZEScclRyPdl/Kqdn4oa6uBC1k8wU83FsS0YPtnB/CrjaPBDHI7sIlwSsgcoVyMdf6Go/CMBbRbVAyMkS7HATcQVJ75ourahrfQ1YLi1uYtyTR+YvDKTgg+hB5FNn06CdHR4onif7yumd3Pes7V59Ptif7UksgrcLvAZh+FZjaho0cTgTqFUFo1VnDcddvTj8aSi+g3JdSRNCksJJn0i+mt0GS1s48xCcds9Mn/APXVPSPGcbyJHrEP2cg4MqjcoI9VPI/DNczb3V9q+sLZ2091Pbs4IWWTcVXuSfauu0nwpa2t0lzeXL3cit8gA2qv19a1kkviM02/hN0arZ3sLPBdWkj4wPn4H171neJNUbS9Ga7gCPKWCfMTg+34VPcaDpTEyf2fBJKM8YAz+XFY994Tt7oSrA1xbp1+Vg6fgDzx9aiPLcuXNYd4Z0maGC6lv4oZpLkrJ5QRcKD2xj36DitePRbPZsigSHdz/q1GDn0waxNO0vVtP1GLT7TUjJF9nacLPFuU4bBUYJNWZtR1ezLJfaPLLngNbcg/hz/SqldvRkxslqjO8V2st+wFiJDPCQj8iJWA9B61Xtkt4bgJGpt5j9+CckMw9m7/AJmtKTxNbkxrcxS2hzj/AEmJtpH61Dqms6J5QE8dtdEjP7slv0I4/Omr2tYl23uXI4oLkbZId5A4JGDXO6i0Gma4Hu4UvLSTI8h2/wBWeMkDpVHU74S2RTS7W6toM9fmIYHtn0ro/CVvYy6L5V5aIspOC1wgy5+pHSnblV2K/NojdFvp8MGLO2VI5Bu/cRjp/vD61V1CzadI/sdwi44kbb834isARav4bd/KXz7LcPmU8Ae4P3fTNdNYaxZ3jhfPiWcjOwMD/wDWP1qGmtUWmnoY41HU3YeVp6JH03TShSPqBmql1rl5ayItxp7bCSDIh3g/TH9a1LRZp4lJRQM5bjAP51Jf3H2MAkr5jMNif3iTjtycVWnYnXuZcmp3jQvNDYTIkali7x449AD1rKj8Ri4kjW53yHIATAVSfc+ldVK/+jukjbC6kGRvpzXm2nxiXVLZcAgyAY9cVcUncmTasd1Kl9LGY47OyhRsZyryHn8hUtnpksFstu19MkKjhIEEf1GeT+tX4BLI6F2+Vc8E4z+FJNqNvCdvnK87HAiT53P0HWs7vZF2W42xsLOKJRFGVyfvA/Mee5PNNu7qO2keK3RJrnqyF8Ki/wB52PT6d6UWd1fQl7xmsrYcssb7pW+rDhR7DmqYeysbSR7OxeTbyAsRcufXn+dAE+kyR77i6jlRnncMQvAJAwODz0q9falBptqbq7yz/wACY5PsK44eJTJL+7gldm/1kpQFkUdlHoPeuksLWC7mW7dTdEruilfK4B7AZ/pzRKNtWEZX0Q2204ayyXurSCQEZjtlf93GPfH3mqxe2KRwrFZzywBeUjjxhsc4wKz7/TbdL+N7dlgDKQ+xyN2enyL1NbkFt5duGt4XG4fxja3Hc55pNlJFXT4nigZYrMb1ztaR+/t60fZXi1CCae7JkIIWNMBRxVXUdZWBJVtZ/MkU4AigMir6gEcFvqcViPqF5LfRp/Z+LiSMmKS8k59yBwoPtihRb1E5JaHU6hrFnYoDcz/vGHAHJxXKeKvENrqFmtvYRs0mdxkYdB3xW9p+jBI/OmtFur5uZJJjkZ7kZ6Y6dK0ltbiQqYUW2APzZUEsPT2ppxi7g1KSsec6JqV3pMcs0cZEjjaHePIA+p9/5Vv6Z4mlexCy7TcSNtHyF+/J257+ldk0J8pkuBEVIOVb5lI79eK4S0t5x4lub7SLN/syMyW7InyMcbcg9MdTVcynfQmzhbU6aeDWFjEsN3auirgqqmM/nz+mKSws7qO7LyTXLKBgsxVQ/HpjIH51mOfFCgzSlVy2CcJuH41RvNe1u2nie5gX96QFdYVO72B559qlRbG5JGxJqyh/s9vZXsly25OCGRsc8SHqOprJn1bUheFI9Gf7YAGBJMm3Pf0rW+wajqGuRvMWsrCFcRtKQCXI5wueevfGK17y0vbRneO8tpkOGO/5CPU+houkFmzlYNC1XWJmk1a4McYAIjiYMfpgcD61oXfhzSt0NnHbXqTLyZVBIP8AvPjB/Ctf7VI7xBUkIXPmMi7Rkeuecj0FXtOmkuHZSXWNTzuTHbtn0/nUymylBHI6RoU/9tXtub+WOSIq6BVVnZT/ABHPTH51vWlzq0WtyWs0a3VmseRcKnlnJ6Kc8FvpWj5Ol6M5uWWOGaUbck/PJz09SfpWdr2s3SWry2Fus0SDcVkJRiPVR14Prj6UXcgsokz+KdJjWYNPIjxHDBozndnGAPwqo93quqmMWVr9ltySRNNhpMeyf41xWg3jx6zNqktu7WjvtdlQsq7uf0xXZv4m0W4hMbyTbMfMDEyh6bhyvRCjPmWrJrfQ7e8vY7ua7uL+VeFFxho0YdyAAOOeOlW/Eup/2RB9rtzzC6pJHg4dDwcjpkev4VDbeKNHS32C+jCKAApBU4A6AVBLe3mtW6R6ZbLb2kqY+13G0kITztjGc/jU2d9dirq2hvuItySmRVQLvVmbaOf0PWqX9uaUrv5l5BLJGpZ/LO8gDr06VHpXh/T4o3jlVZVD/Ks4Eu0e2fu/SreoaVC9vLDDHGsUq+WxUBMDB9OtToVqVDf3WoqU0uwmiGPlnuk8tBn+6vVjWhp1qthCEmkNzdyZzO64Ln3x0A9K5+11C8tprLS9SEkt06/uTauMMqj7zMe/HPpWu9nqV8T9rvDYwdEitWy2B3ZyOfwwKpqwk7li/wDsTmKOeKN7lSHijU/Pu9gOn14GOtcD4hi1LwjqrXtpITZ3THb3CnrtP649a9AsLW3sbIrbwybnHzOFy5PqSTkn61l+L7M3Ol3IeGSWJQGbLZbbjJZQe4ohKzt0FON1csaHq639oskcTxoyg5wCM981fW8MbuwD5bgKU6EZz+J4rjfhrcf8Si7hY+YocjHC4BHr6murvbgiGM2qBNoODG/3R0zjo30NKSs2ioO8bl7e0sUXmRn5+SocZBrl7vw9aahMy2EH2TbLmW6hXbk91Xs2fpgfWt64guLq3AiieNG2ZeZ9jlc8gAeoz1x1rRjKSWxXaWixjYUI+n1FJNrYbSlucidG1u0GLLX5VhAAUTIHwfQms2bXta02aG31OCNppDhXVc+aAcfLtP0966HVNat9OklN29u0kEZZY0Pzk+/pxxXM6Fcy+J9TGpTu0UFk6uLeNujEnaAfTAye9WrtXaM5aOyepozJruo6lLZTh7C0UDzmRAS+R0U9/f0q1qfgrThA8tlJdQXhxiSOQuWPuD6/hXSNJGnyu0ibzhfJDHv171jSjUIL6aMXuoSwSwgwlkRtrknJPAyBgdT3qVJ9NC+VddTnbPVdU0b/AEXXrS6ngQ/JcxKZMj0z/k1v6Z4o0EWcQEosxjAilQpj6cfj+NLpl3rDTkX9jbxkcB1uMAj12jJHbvWd4quY7vTrq0mERbYfKy2MSduSPUYFN2k7WJV4q9zZutS0+0sfMaa3+zMOHVw2fTK9TXKXHjy3hyljZbNgIRncjHuVHFcx4asm128NkcxRIpeSVVywGen4mvRrHRNP0qIwW0LRhvvyyDcZOPX69sYqnGMNHqSpSnqtDlTq3iW5iF15V+Yj93yY9qtn2qTRdBu9bthJqF0Y7d/9VDCwJIGc5+nT1Ga7u3djGtvIsiO2AAw3Yx6HuKw/P/4RzxFho5H07VJPk5A8qbow+hz/AJxSU76RRXJb4ncJdE1PSEL+G7hWjVcfY52LRnnPyE9Cff1NUpfEVzdfu59LuY9SjYoYhFk7iOzY4H1/+vXXpL5NnEWRY03dCQDnPtkc1iaxcKtvPeZEojA86FSVLR57H+8B3HX8qlSvuU422Ymj2975kjXtw8U8+PkgCiNQowOSDknuapSXeq2OrQadKYLiC7DtHcOmxiwHOQOCR+Ga2v7RsoYkAjkliGF/cxmQqPfv7VW1ZdJ1uwkhtL+3W6iO+As+1kkHTryPQihPXVA1poyxDDZxhRM4JI/1knVvf2qO71m2sIVa/d5FT/lokZ2qe2SPWqMlhd6nFDDeRpb3JXrL8+SOu3HB+mc1i+L9M2wW9nLqb7gAioyDqTj5sfXFNRTdmKUmldDtf8S2Gq/6NZ2X2tn4UNHlsnuoHNZVpd3HhzTbxL6OX7R5gEKmQlM45PBwCOK7u1jSx0+MWMse5Y1RDgAkAYBz1/CseXSriXzvtABjkOZHU8yD/aUjqOeRzVKSWnQlxb16mTo7atNNFc3E1pblxuCGMszZ6Z5+nepr+TxYiLFEkbSK2DJBtIYe4PSqTWsul3IWf/SNImcCOXO7yCcfe9q6VJNTtn2JbrPagZWUv144/wA802+okr6GTD4WuZGjuNUvZXmz83lyEBPYH/CoP+EcdSZLS7uYpyScu5J9i3r/APXrp4L5p28u4t5YXxu3Kwb/AArL1eWHTVaUzTybyMs+VVMe2KlSlcbikjBawnukmtrm6mS5AAmQED8cY5BrI02wSz16O2uZJkRiPmXCq46gE54HBrsoZ5tVsVvbSxgVlX91PPLyOeegz1zx3rNubTVLjXPtsMMUZgjAKyjcjEg8rjqOTz1FaRluiJR2aNXVPDFpPEWimuY4mwHjjlOxsexzir9r4a0yODbJA0rHlmMrLn6gHHSs7SvFVqZjBq8IsbxflOATGw7fQf5zXSNJmMSxNHJCQGRozw3vnOKybktGaRUXqipaaHptsfNs7S2B/v7dzD8TTNb06K/tpFeFJJIwTExPIbH8qvXSzXcXmQZhk65x+eR3rL1CZrfSrptQkkiiUY82BckAnjikm7lNJI5jwl4hW1uI7C9t1jjUYBjj+cdiGAHPc5610l/rNgLlYreRWWbkhhtwR2OeP5fWuT8JaXJe622oZLWcGV81lOZDjAwP5+ldXc2tveMIp7aOVEkx8xBAOPf+VaT5eYzhzWLXnskAZbefLZJCbGPt0PIqCDWraGA/bfOto8HPm27rj2zg1i65ot3psaXujSyRojB5LTf8mPYf0rRt/EOn3MKrqEMtg7cbJCQp9Sp6EVPKrXQ1J3swsNSTU9Ws5rCGSCOCMt5lwdh2NwQq87hwDnoK6GWZmtt4ckqep/wHas6SCC6ih8qUJJG2YnXlh7Y7gjt3FQrqUbXhtZM212pJbzI/lcf7LdCO9J67FLTcddPZXZKSRxPJgnyn6/UZ6frXLa74b+2XaSweVbKrANGEUAj1BHf2Ndi6xzqjOw3pysgXgGqU8M4uizsjwj5k7MM9cnuKcZNbEyV9zlNG1O502+NnfTPCo+7v6NzgY9BXWu4mjCyoHUnHzLn9K871RzqOutGzlAkpVUxuCKDknPeuovJkCB4LubOBgA5X8VIxWklsZxe6NS4jtY1EhuFjRBh4ZGzFIPQhulM1W1ttVs0D26MuMRyx4+T6Fe3tWPp2rxQu/wBpXzM/N5yAkEHqCvVf1FalteWMhf7G0MZfHzpjax9Tjv8AXFTZoq6ZRsjf3kIKz/ZkJwVhjwff5m5P4CpmuNMsGEfmqZz947i7k+55JNTW7W6iQi8aUlssQ3yr7A/4VFL5aSp9ktlMYPSOPk+tADdQSa9t9lruhw2QXXr+FcT9h1HT79JHt3LFuowQefUcCu1vNUt7OIteho5R92HcC5P0HT8a5y4XVNcveYJbe2VgQrZUKP6mtINoiaQ631x7mWW2vVk8sjbsjyWLA88iultUZYFGm6bMmQPn2LCAPTLcn8qg0OK1sVBht3RWJ3SkZ6e55P4Vs/bW2qka7JHJw857eu3+nFRJ9iop9StcrN9k8zULhLeFVPmKrcfUtxk/Ssy0WbUMqGuU0tMBVlJ3TH1JPIX+dFxFqSTedHHb6kucgyDY4+gzgD6Vp6LdR31m1xJHLCFLAhzn7vU5FLZXHuxxt7R4jbNt2ONhVRtz7cViXOgXEcztp1/cW8IAIVnJVeOnXOK1YMOTHp9qYy+SJ5lPfvgnJpbi9trOJleVI41G2SRh1b0APehNrYGk9ynaaffRxvc6rrUkUSjnyDsAHbJI/pWVMClubpp76XS5ZQrmRypYf3sDt296Zq17/bF7BaQTSTQ7wZEt4+Nv17n9K7OAQXMS208O2Mx/LAygjaDwDjim9NWJLm0RSa5sILKNom3KB8kcZAAGOmO3FR2+mLqdgJL9I33PvWJM/IOwz64rQa2SC62pE8rOuURiBgjqN3X8Dmq+szNaWE7qv2UsBulLhimTgnHrioT7F27lmO0060tSJpZUESliVnkyo/Oq3h6a/u7dniuvLtZGP2bzl8yXYDyScgfnWNfa5ayW7WNtJFCsi+WJbgN90jG7pznnk10ehQRWmnRRW04uEQBFcENke2KbTS1BNN6EUmlvLJPHfyyXcbsu3zT2HbauBjNXhFsTDsh2jHAwAPbFNvrlbazeS4uVtkAPzkgYPb6n2rIttWJRpNMhvtTYAbiPkTOPUgc98Cps2PRF7Vrr7LaPLAVMhGArrwT24rn/AAjJHeK1/q1y01w8hEUZJwhH8WOmcnj0rQltdX1wAXTQ6fAQSIceZITgjLdMdelY7x33hVYFkt7e+slJYyhDwT2Oen8qtJWt1IlvfodjHIIR84aNG5DswA56Yzz+lVNZsxqloYCEj+Yfvwu6QEc/KOw9yfwqvoGtWl/Yy3czRGRDhl28oOwH/wBaqiyajrV5GNP3wwrkS3Y4jXthB/F/jUqLTK5k0QyPrFpqwt7C4bVTt/fRsm0R5+7uYcA1uW2mXtwxa+1K4W5P3YrR/Ljj+hxlvqal0bTV0hGtrcSugbzJp5DlmcjrgVrwOyJg/fzwzAbjn2olLsOMe5jr4csbQia7lkkmZ/8AWyvud++Mn+naszxFdkS2+laZLm8uzmWXB/dp1/l+g963LzWY9PjL3lxDHFt3DePnPso71n+HtJFzdXGq3RInuiXWJ2GYo8/KD7kY/lQn1YNdEWNOtJNI0pLeDEvlL8uAFYknknPHf3rQzYXMJjuYFdvvATJnc31PX8KtiyAw0cm9OxPI+oNUriVbS4jjlTAClhIRlcDGfx5qL3LtYqalptm+nXezTLNFELZPlhSeCSRxwfTFc98NZC9jPE0+/wAqQeWo7KR+fP6V1t5qVtFYTSTSKAUICOQCwx6GuD8DabK6XN1aXU1nmQxB1jWQMvXAB7j1rSOsXczlpJWPQFgkAdkxjnCglR+JrK1XWpZZJNO0KA3N3GP3jn/Vwn3J7+1MuPDs1x/rdUvJNw3ZkuCCc/7K4AqlomhXGlagxjuCLWZivkOx5cfxe4xmpSW9ym3sLpWj6ja619uuR9tuDEFctIoEeeflHfp/nNdPFPcmF38qOJIwcCU55926AfTNTkyCMfMhQdcDoKxrzXdLg3tcT28juQoj3Bi/bGO1S25MaSiiymqFTbtcXdkjSkIIYyHLk9ACDn9KXW7mBNMuGmLRvKjRDeQD90474rJXXdPlvkssRWzbflkdBtGB0BHfr1rI1R4tV8Q2tuVnudPETPJKFIWTj+EjtwBkVSjrqJy00MP4eXkNnfXv2qRUjaMAkjI616G2oQRzwIyGa2lICSR8r+PauW1nwhLJOLnRzHb5UfuSu0EjjOR39ay9P8P6087x3Ectuo6OGG0n161pJRm+a5nHmh7tj0q5uBva3hibayffLsBu/pgU19Lhlt8S3t00fUxxy+XG/wBQOQPxrhRq+q+HpNmoCW6gZtke4jB46gk5/DpWh/wlllLp7y28P+l5+7LyufUkfjWfs5LY09onua1/a6dbh4jBawW3lknKAlicD645A9Tmua0bTY9G33DapNZpIzBkhAJIz8oyc4I57e1P0K1uvE08l7qpc2qDEcCgxo349x9OvrWk/hy289DJIy2asBHDnhfxzk881V+XRsm3NqkamnyT3lw8Q1q6KwMCF8hFLZGfmYckVJLY6ndSx3KXSwGAFUiVQwkB7k9BnHFT2N7Yi3ijhcosq5jLoVGOfX6VctmyFHnRsvXdvU4A+nUVm2aJHMxyanE8k2o6gY0h+UqjiMD8AMn6ZrmviCl8ZYmaXzrUjegRRmLgcsB69QTXdavYJeQNHbeRCZDuMvl5JPcgd/qahsbBLeMIk5mj5ADjnPfce/5VUZWdyJQurFLwdqWkzQRWsCx2t02BuKgeeRnnOMk9+a1oEuC8jC6RRuIkA52jPv8AnXEeNbDS4IhPpFzCk8Zy8MTZDc9QRwCPStPwXqWr6pYyLJeWwWMn9/cIZG+gAwD1705RuuZCjKz5Wdc1s6b5xqE+zbkRhhsHryP8azprCS4hmRp4PsjgFYnUPgY+8P8A63SnRyS23lpc3FqfM+68SFFf2ZT0NX082KMynylY4ACAdOmAaz2NdGc3qGsan4cjRLq1N1p2FjFwGAdfY9ifrV3Rdd0zWWe3S4jCyLxBOmx14wQOzA8+9Up3/tPxrb2uSsVnCZtrkMrOcAEDpnnrV3VNPttQt1S9gjLKSBt4KYPJVhyKt20vuQr9NjoYLc29vFFtysQCrx8xHYGsbVNKsr+YSajaQOWGEypLAdyWFVdF0uygm8ywvLsSk/6l7jJJA54PB9jWldW88c8UhuYw6AhlK5JBIwQeOeO9Ts9Ct1qcpqOg2NqkokuNRihRfMRBMQgfHy7cg9/euU06L+0/EFrZ6gkiBnxOEbk8cH+X512vi/VkfRfKt5Y5CZPLlwckY6fTkVyPhHSbq61CSWO7MCkMElBw0hyOnf05reDfK2znmveSR6d5CfZ44nEa7QPLEfDLjtmkMhWf97dlUAG0vtAz3z6/zrndStPEMV3mz1ATeXHu8uUfe9venaXfR+Ioo0uYLZooTunRm+dWHbaffvn2rHl6m3N0NXVbeEWogjli2Sna0IQPu7/KB09azIp/IWTTbi9gjMYV4nkbqn933x/Kkn0HSry9tzHaJHBsYtJE5jy2eFwPxpY/DGhtNNELNi6Y372YnB6MOeQapWW4ne+hZj1jS5neJ722Ljg/NkD6Edqbr17p6aPNFO6fZ5UMY8o78Ej19uv4VFb6LpVlcfZfs0SFkLqZGBL9j78Vj+J/CYuv9I0doxx80I4Dn1HbNNKNxNysXvAN3v0gW7LNG9ucq20hZFJ6jPU5Nb6qGuHLYIHBA4YZ9hXN+HPEaMRZ6nb+U0IEbNkhkxx0/IE/jXR6hcLFYG4itmuChAAjlGQM8nIqZp8w4Nco+a2t7yNY7m1ilT7rBlB/HPXP0rATR5LUldNvbiyXdkKG3xMc/wB1q0zqllb2kc0rTQq3yrFImWJ74/DvWQniWG9kaCKw1G5RuPkUHn8+PzoipdAk4mg1/qNhayS38Mc1ug3Ge3OMjuShP8s1yeoaqupRzaTpNrPcRsN6bmIKEckgen1NXr3V7y+srnTxpU6SSqY8EnI9zkYql8PruCxa8a9khiiOAGfht3p64rSMbJvqZyldpdDpvCcepWFhDbXEFvBtUkIVJZ/fjjP0Oatm/uZnAOkPKXG4SQzKUb6lsEH2PNWI9RjncJaXVu4XqFbLZ7H3q5DGRafvGfIxyDjPPvWTet2apaWRQNzK9o7XtrPGpG1kKCT/ANBNZ+r3Vpf2JtXs787yNvl2+NpHT73GK0Zba286ZvNLK7+YVYnCsf6ZzVKeaKxm8sl5Vf5YkXByfY9vxpoTOZiutY8PbfOhFxp6nCOQMxg8YyM7fp0rQPiyzyJFeTco5jdeD79cVS8VXD3bxafA3zzOoMIxlRyc/wCfStO30jTbEQwzWcDE/dlkGSx+prV2tdmSveyLen+IrC/jVVmiibdtZZW29e6nGD9KTVLxbG3uPKvojMFJjjaQNz/Oq2q2tv8AYzGwgVGxtRlyoP4VxlvYS3moSWsssdrKSQF2/e/3e1KMU9Ryk1oR2xafWBdSJO0DSZd40LH3xiuyGiwhEuNOu2RZSPldht5/nVnw/pa6PZSJG4aV2yHI68dCO1P1Dy2sWa4jZoZNoYICep5JFEpXegoxstSle6AzoM3RiuCN3QYOKwn0jUUuWZEWTao/eIOCD0wf/r1tR29wkX/Eq1C4VVx8ko3qD9G6D6GnjUtTs4mk1C1gaOPgm2bkD129MU02gaTLM6ecAZlxEnQfdVfwrEvdWmuLn7LovzHHzSjgJ+Pr7/lXOXWpJIB8rzH+IzOx/rWlYeIWtI1SGzto8YPGR+NVyWJ50zY0rRTb3ImnAlmwSryDhT64POfc10EUQbCSpuAOcscBj/hXO23iXzYwkNvJNdt0iQcfUnsKtQxavfLuuZVs4v4hDy59tx4H4VDT6lJroaF5dRWckaGVWct/x7Qp8zDsAB/M1IGLKst2ipn5VjVwSvtnufpUthplvZwsIVVCesjHLMfUnqaSUwrKf3YkdON2cc46VOhYly/mK9vAjhipUsxyVz34/lXDpFqkF9HBbPNM0R8uL5SvHfg9veuj1rVzplnvEADudoVTgD6msvw5OZBdXcgEaSHDTMx3AZyQoH4c5q4ppXIk03Y259Nv7iygU3k63Q5kkR/k57AY7etQWvhS0Uh5GkuZh1MgyAfoTj+dXf7cs44V3SCNyPukglR2yBUFlfvdvL9jaRztBzIuF3H0I9qm8kXaLNA2a2lj5kYgkKjOBEBnnnABxU1o7So9x5LqzgBS/J9wB2zVWW9tbOEfb7qINjdtJx+Sjms55NR1yGKKxSWzsOd1w+A7j/ZA7UrN7julsX7/AFTTrGdhI4a6UYEceXf6YHSqMkdxrN1G+pp9ns4/3kNkzZkkPqwHOK2NO0u3sIgkIWJem8cux9WY9avxumWRJJJnQfOqoPwDHilzJbBZvcx77RbbWo4prqFtyAgAZVyP7tZVp4TFvAPtd5cxq7EiGFuFz0B45wMZNdZb225HMsEsDMevmBiR6Dk4FLFPDHM0HmK82CzKPmbHvRzvZByJ6s56Pw9/ZmowXcMM+oWiglo2cM6v2YKRhvp1rZsdQju7x1MgjLfLHDIhRiep4PX3q/PLdNH/AKPCo5+7ITx+Xeub1jU7m3cxzX1jarGQwjQFmb2POQPpzRrIekToZEVNzyHK9SuOBnsMVj61r2n29rJDdBJlPymALkEehHb8ayLW61PxFldO2W0Ma7XnZi3zEdF/znmrtn4bs4PKW4/0iZCMFiTlupOM4x70+VLcTk38JwWuXX+ny/ZYTZxOoHlKNnHUZHeu68E2L22nCS2Kndgu5k4Df1xmqPjrSLq7j+2Rssnkgho0i6fRure+a53Q9bn0yOHyXPyscr2PPcVq/fhoYr3JanrVxK0Nsy2cWZWbLAHYSfc4JrORNUvzuW/tIIOVJgQuw9gW4z+FP0i5S/tzcDzBKMIy7iACeuRWg0ix7VjAVF6jP8hXPsdO5hRaJbafJHcyCS/vnlCpJP8AMcn07KB16Vs/2Lp0soknjzdA/M8LGL8PlIyPrk1lXchuNZsY47xYFQu7IOS5A/8ArmrZu7ZZjHar5kx9Dnp6k8U22JWRYu9I+0jfY393YsP+eUhYY91YkflVB2udNiaPUdUhO7CibZtfOeg5I5+lM1bxPFYL5E0+yYjJihG58f0NZMmj6hqoF6tmkL5BRrt8yEA8cAfKD6nmmk+oNroaOtW0IsLkw2onuNhwz/MxPf5jz3rkvCmvjRtN2gec/m5aEtggdCRn8K6WG01u7cC7uobWHO3y7dBJuH+8elVtd8NWt6oaGMW18SXDKc5/3vU59KuLSVpESTvzI6SyOm3kRuYCQpJdgny4PuPXNLqr3ZUtYxQbURiBLJhT054BPb2rzGGXVrbUmsooJTcpkkQE/Nx97jqK6a1h8VNFE4mjAIObef8AhHvx/wDqqXTtrcaqX0sSPpzaj5bahqVxJPt3rBCPLRRwSAOpPua2rKy0i0WRraxiV4sBm8vcxJ5wCe/0rlL3VtRlQKdLZLuJt25AduemT+frzXRaXbarPDDLf6nNG2MlY4kUD2zgmiV7asItX0RFezPeajp0E9iyWjXAVxKoKthTt457/ga3ri3QOhhRkCDaAgwB7Y6YrPg0y2lnmEkuoFgctJ9oIDccdP8ACntZXdrEFt9Vl+zjLAzxLIR3xv4z+NS2noWlbU1EhVgZLuSJSBlQhO0Y9Sax/EOsQaNbBn2zTOMqikAAf3j3Arn4vEWr6hDeR6RG100UmFnWEL8uOTjOM5rR8O+GPs5N/q8vm3MvKxfwqT1zn7x/QUcvLrInn5tIjND0EaiF1TXA011KNyxvwsSnp8vr/Lisjxrof2S8t7nT7ZmWU7ZIY0yCRyDgdM967R9RaKORZraRuwYDr+FMu9R8mNDOiwM44DHPHvTU3e4OEWrFTR9aNzaEzq1tPC/lyRNGx2tj0A446CtG1htLhHRZY7iQEh17gnsV6iuV1nUrvSNXi1a3T/RJQIbhUOQ2M4J98Hg+1dChtdajju5rJLhZBmKQqFkwOxJwRznvSceo1LoattPbsJbdoQ0duQoAQMv3QenbANQtFaw3LSxW1tC2R5bBQDjHOeOOazZ9Bt5dn7qa2UnEkdpKYo29CfX61lXnhy4ij83R9RuI2jJ/cXb7lwOp56fjUpJ9RttdDqGk8uNjhS4J2MRzXGeLvEytBJZ2jfMTtmkAAyOhUf41nwtrviC9ktfOWK0iwskkZ2xL78dSfSrOoaNceG7m21WEDUbe3OZvNUcZ4yAOw9exrSMFF67mcpuS02NHwj4eWNYrrVVXzGH7q3dfug92B/i/l9a29X0BZhnTp5bGTAG6BioAXjG0cHilh16y1CyWezZiZRtwAQynpg+hrVtJnkjPnRvHIo6MOD9D3+tRKUr3ZpGMbWRwd+PEWiO3n41K0LgLKVywPuByP1FaWl+K9Ou1khvI5bZmG0hvmGPr1H5V0LXkO8Rr5iSH5VDAnac85+ucViaz4Yg1fUGkd3trkAZmTG1x6H3/AFp8yfxIVmvhMe2vLIa/ef2NbT3cs7qAQdoDDJJU9VXnvxXXwRTz2KjU7e3FwhxtjbcpHr7Vwtt4b1URTTW9xBC3nMoGWBYA7c7h06Vqwr4m0xIhdia/tHGxxatmaL0w2M/jzVSSezJi2t0dCLKJLsSQBoJEPDjkOD2PasPxLcahozNdWlxA9rJIWeKYco56kHuO+O1NXRdUnjaSz1e9RXGdl4rB0P4EZ/Kud8V6drFja41K9a5tG/1cmOWPBwR1GKIRV9wnJpbFPS7W68S6pPHLcRwFgGkYry3PRQOP/wBVd3YaXb6JG7Ro4QD95KyliwHT3/AVi/Di+s4bUR3a4uXYxxSvwMdlB+vrXfsS6MdpGRkBun6Uqsne3QKUVa/Ux7cwJNjzlZzySpx16AjP+eKy9R0qO/xdR28kUgLIZQpSQj19/WrF5o6JqI+xhITJkSSoOGB7c8Zq813Fp8ttbOkgaQlfOkO1SRznPIqb21Re+jOe0UapI6SLLbXcGCNp3IW5PzdCM10n2m3t8B8RTMPlyDgn0LdM1Uubj/SRbWlzsaQZBT5tgHOcjp+NLE9xLePBdEGJEUqgHD5z8zZ+nShu4LQztGupNS1C51c2W4AeRCRIAVUdTz3J4yKj1vUr171dM0gIlwyeZJM7ZES/X1pizf8ACLtKsryf2ZcSnyGABMTH7ysPT0rSa0jtrf8AeSQW7upZyzr8/uT361WidyVdqxiP4RWW7FxealcSyEKGOwKW7Hn0qxNojaVp93Joj3UVwE3CTfkSY527fp7Vf0yHUygjmmtLi2jYBJc5Lpj1HfHrWjcgbo8P5W3hWY8H/GhzdwUVY8x02S21e/iOs3chbGPmGA3opbtXolrALC2EVuqeTGNuzOMD1FcX4/sZYdRhvWRfIlQRsUGPmHPP1Fdnot3BqGmQzRR/cAQqTkqR/PiqqO6TWxFNWbTKUsVpqbu0tvDcSHCqxOQvsew/rVC58MwNI09kot51AMZB4DD26dcdK1b+CATpOA8Sj78icHA7e9ao8toAYt0kZUc5xxUczWxpyp7mNbLaarGLW/hSO9CBpIyNrxn1BHbuCKGtJ7QEWGo3czKDw5Eg/HP+NZ95NHc675tlEsyxQ+XKzLlVYHKYPc9a0rUxLIs0jhZ9xG1SQee+0+ntTd0TdGXLeXNy0UmpQSCNQyukPIYjocHkfQZqC+8S2ltARp8a/a4RtBljJOM8qM8iulkt2LSgkKASBjpz39axtS0yN7YfYLQRaknzrMMYJ/unPUGmmnuJprYl0G3tdQ04XtxbW0c8uWfZAowc+nWrE9rF9ka3uIYmtSM7w5IU++Tx9QapaFfx6ojrKXttRh+V4lwDgDkYPUex5HrT7aW4S88x1drSXhXjHyjPY45Uj3BFDvcFaxVTT7bSZxO00jxcMkb8En2/vfhUWr/Z9SMVtb27GJsnftKiM/3h/hVTWYrV2lge4miIfeYhtKnjgqO2fQYqzbRaZqUCS2EhiuouQrDaQfQ9qvzJv0Jlt9T0m2RrG6a92AmSGXHI/wBk/wBK07mGRkhuIQ2XGSd5Kjj16detZFlDLLIzygwSLgq4YjzPqM4ou3uobyOe33mdAVeAHAceoPQmk9QTsW7WZ7CR4mtlTzW+WSJNyk98jPH4VdkSNiFYhpO+G7eoFU8Q6tAFWe6imx/qnkKlSPY9f5UyKKaBVhvVMxHRsqeD3weQfpSGENjYxYwlqEH8BjB5rnvENpFNbpJpcYmVHId0XnP9fwrSvpRc3bWluNjkZnlA5RPQe57VeS4is7cCCICNFwCBnAFUm1qQ7PQ5zwvqP2YG2S2eaRiWIQhSPqf/ANVasniSTzDb2mnTu6nBG7gH6iq1ol1rE8lxGFtYRwgCYMnrk10FtE6pGgHlgf7Oc/QU5WvqEU7GWttq2pbjd3RtYjwI4cZHpljXOXX9p6RdOkUshTJPmKCQ3qa6281KOxlCSuZZQTthjwzv6ZA6d6W2aSSISagCTJkrbRIWAHoexP6Uk7dAaT6nFSXcmq3CNdj93H1Ctj8Bnua6bTdDhktiXgkhhcg4eQ5H4dqsXPh6G82SQ2cVjsbdkNkn6joKm03TpIbsTNqU8ijJCMgOAfT0pykmtAUWnqV72GHTLdltNLllUrt3qvH/ANesGa91nT7WMSB7aJjhHCAkn0PpXcTyfvNixlyRk56t/hSS6a2pWjw3p27+MIRlPxqVJLcpxb2OU8NX8c1wEuxE0jMXEjICzN6E/wCfSu1EwljRIl3HqAGwAB/OvNdR0y50ibdIJIyGzHxkEDuGHH9a0tO8Si3Rnki81yBhi5BzVShzaomM+XRndSi4cMvnIo9U/h+pNQ6bcIuFtXMiA/M/8K/4k+tYVl4ht7qBzeQOsJPIV8jHvnmrl34ms47eOHSoHndvlRQmAD7Duaz5Xsacy3OleQTJJGr+ShGCwGT+Gf51zsmu2ulMbdWXULlmwkdqoGPRTjP9apw6ZqGqzmbWpWEJOEtY34H1xW/aWNvp9uVsbZGAPIQY79SevFKyW47uWxnx2usaqCb++axi/wCeFp1wfV6q3uk6RpjW0QtRPcSNw0oLlvcnp+GK6JRLcPG0AMcSsd4ZcH8jUkjyxxs0sYZzkKFz+X5dTRzMOVGXHdPYQeaYYoYEXdLsxg9hgDHPQVas18oCWVw91ccso+7GAPuj2H6muZuorvXPEESRqosrWT94VPyM45wB3PSujt7Dy5gUEyuOCxYEkHrxjA/CnJWCLbJoAXhaZXVoxkgk7cDPv2rkfGdrpkqWl5E/lvMr4ZAMPjpn3zxmuuu0tIbNheyL9nUgnzTwf8a4T4gXUM81obZ4pIjH8jI+fl917c06fxaCqaRL2g6zeWvh2K3tLQykF5HlJ7E/dHqeKrJPr2q7jHIbKFVP3sjd/WtvRpIbHT7KC4ktIlZFC/vhljjk8detb8dnCpV/OPGPlC8EnpQ5JPYSi2tzhbbSNcUBIPsjcZ3s2SPzHFaVla61qE8dr59nZx4zJLA4Zz2+UdR+GK6o2pDSBVRVmi2Hux79OgFcdOJNMkEgtZop2JVYlVm3HoDv9PahT5gcOU6exsbGyEYtoVBViRII8vIR1+brn3zWvdLFc2hiuCwSQAMEyCeenFY0V3eRw2wMEsgICMFQbV6ZYt/StCO4D26uYnUjJZWIGOeSazdzVWJJpYre0OGWOONBjHYDtXB3XiCbV5kttHhmS7L7d7j7i+pqXWb+TxHdjT9LRiiZfdnaG7bj/sjt65rr/DenpZaYsMcZI6GTZgyN1Zm9u3NUrQV3uQ25uy2INCtZoY1S5Q+bgGWXH3uO5x78AdBWhPE9wzRmSZIyflOAAvt/WlaTczs6hxgKAVxj8a5y81z7OTaW0ElxebyscIOccZyfQA1CvJl3UUdHf2dvPpzWyOsKIh+cLyh/ve3rWfpd+bnTbaZ4zE7rudRwPTPsO/41z0lnrRdftOsoksnLgREhPQL2P/1qmk8N6nOkinW5ZEYYO5D83t16VXKluyeZvZG1PrWmxqzSXUDGNckAgn/69YOqeJXubS4Sy0+5kgmVoxcMCyjjkjA9P5Vo6N4b0u1jCvardXETbWkkXPzAdcdMdOK3poH8tAjNtVudpG3AHTaOMe1F4ph7zXY5H4e3Vs2mtawki7DNNsYfKe3HrxjrXYW4kFpi6ZGJGXA5UA9vwrz67juPDHiKO4hSUWcgZgqnaCM5Kfh1rsLS9W/t4prAZgkXJI4wewPv2oqK75kFN6crNYogQKo3DuS2D7fX+lZHiOAXUOxgUz1b19/bv+FIi3ssrhJBHESVLZBdSOoX0/Hp6U06WzRqsjCcqfk87Lce5zgn8KlaFvUI9MhGmiBkM6yIVJzlACMj9a5fwXrJsre+t9VkYLC24A/eBJIZfz5rSumj0S2kmeaQICfLtzIQuf8AZX071zeiW7a94rEiv5K4Es2wYzgjgfU4/WtYq6d9jKT1Vtzrb3xVpdvbDypp3mwSIx1B988CubNzq+u27x22xLQsN8uNm8k8knvjuBXdXmn2xlM8tmkr5Jd9i7sdxnGW4qlc2P2+BksbgW0xGEi4HHtjipTitinGT3LGl6dBYaZ9jgWUqeWlx8zMe/X2H0q4FhnhdJAGyPm38k9iCP6Vg20GpQ+XG8szkP8AOWXA/D19M1pyW0EB+0XV0/mE5LZIz+A/Koe5Semxyd/pl74WuGvNOzc6aX3SRFcFMHIz9PXt3rqtC8Q22qWwlhyJI/vRbvmUH+Y96l+2fbArWBLYJVw3bjjI9c1xF/psdjqMl7pd+LZlfa5MbBY37gMOOf7v4VppPfcjWD02O3ubqJbiOGB9pkfLkxk4A9+31rM8RamNKnimcRvK7ERp5eSQOvJ9KTTDLLvmsdRS6nAAkaZSxkPof7o9McfWq1hYXF34mvL68hVTDKkccaPvWNSmdw/T8zUqKW5Tbew7w/fXCyBFgufLZ3Yl4jtAZieCM+vOa6mN3wqrGFAwQVYcev1FIWWBG8v5goyFBwc1nC8jLLcwPHmTgkqSx/HoPQ1L1KWmhaN5I87qqKsZ5z5mQPw+vasvxdof9s2MNvDcOs8I3RuzZSQk87gOh9DV+3062WSaWEyb5DuePdwWzk4B+tLqV2lvBIs7xKXQrHGvBBAPr17fSmnZ3QnqtTyaOK5OpRabCuJUl8vaGyCwPPPp1rpYdUutElNlLvtpQctDId0behX6+orB8MRtP4rtWjBYRvvc/wB0DrXo9/JbX9wLC8EdzlDLtKg7R7nt17VvUaTszCnFtXRFpet2V2scF1MsMrceXNjY47AE/wAjg1rapbfaI4wsgjcMHi3KCAw/oRXIap4QgniaXSG2SjrBK+Ub255U1W0HxJc6FvsNWRmhjJXY3LIfY9x/kVk4p6xNOdrSZ3SRkQo/keRcc5ELcH6njP5VnzSJauZBDLJvf94SORgcH6fSsS48aWzTItjBK8mOEkwM/wDAgeMc0s/i6EoM7lkCFZIQoYBscEMKShLqPnj3KHi7UtO1XSpfs1wBLEwlRdpUOehx6nB/StPR/EmkwWNmtxvFwFUMVhDEnGPx6CuK8OWMGteIDb3kzrE4Z/kIGT6D/wCtXo1holhpT+dp9qiSkYLOSxx7E9K0moxXKyIOUnzI0bWexvFLWMiRyx43Yj2sB3DLwRVODUY5ZXVvKKqSPlcMrDt9PoanurC01C3Vb+FXkwRvHDL7AjmuTn8LaZIf9EvLpAx/i+YDHY8Dmskos0k5LYueNJ0GkTCRAd2FUN9RWL8P4J3uZ7gKVtRkBm/iPHApdd8LtLEW0q6kl8r71vM/zD0wf8aytN1fUNFf7NO0qeUcCGTov0HatkvcsjFv37s9KvFBTDAuoyDzyPestNMsprnEzXUZY9TO22QHsTVO18VWNxDEbt3hmDZLbMj659K0Y5La7RZY5I50Q/KytuU5/l+PSsrNGt0xl3CmmQJbiEtaZ2jYuWQ9e/55qy4S+tgIxbtJnKhwCPyPQH2qZY3uECzbTz8rIc4H400W6RjDSKJjyvGM0rhYj0d4rnSpLgNJCctu3ZPlEH7pz1A5waja4f7QY/NgIxuGVwSfp2+tVbZ5o7oTT3GIpQUAHZxxnPoffvUtxCkhdwsrXBGPkfaQfUZp21C+hmapYLqE4udPc2+rQAYydocDqCeman0bXEukax1RQt8u5XVxtDD+XNWNPtriGJ47qdZHI4Jj2kj0JH86ydd1HSz+5u41uHTo0JB2e+4Va10IempsR6Tbva7fLEhI+7Ick/8AAu9c5qmlQwarCNk8Ni52yFTtVGPQ5pmm+MHtkMNzB9oVDhZN21yvvxjNXW8UWgikxbzup4dHKsMfXv8AjTSlFkuUZI1rTS4oEMUTXDBcMvzbgPoT0B9Kn8kpI6OSNx+UdfxzXHp4ghhnDQQzR25OdnmH5T/skHge1aI8ZwFF8y2lUZ4ZWBz+FHLIalEg8bmS2trcxzOCzkFc9MDr6isjTLG4vII5ZLuOLeSieYnDe2aua54gW/sp7dYopImIKMzfMD9PWr+h2jS6efPMTg/L5Qi+Ue2e5q9okby0GWzFo2S2dbiUkl5OSGb14xmrtnZzNBIbydY8fLthwoX8axbC81C6i8vSbSK2t16yHp+LHrTm0+a+RDfalIxPVI1+UD9OfwpNdxpmncatZWNobS0lMjqNpZWztHru9aoWT6nfwp9g8uG2GUEjNuP4Z5/lVg6DYfZXQRFOMeZyzZ9v/rVzttdXejXwCMGB7H7rD39/5U0k9hNtbnbaZo1rYwuN4aZwS0jH5iasNJfNLsTy0gGBux1+grM/tIXllvjQ4bCkLklc+471dU7RHCHKjaFCscEj0z3rN36lq3QuTm1YyK7sDjax3n6/So7na8DAttRgOY+GYdgPTNMu7iO1iADRx7eRI+AB9KbZvPDAHMZlQfdkcYLHrwMZOfpSsUTpOVSMRWzKZCc7sHAHr/hRqWopYQme6mAUDGAMFj6AVT1zXlsVjiSESXp/5YK2dv8AvEfyFU7LSTPcrd6pme6xu2H/AFcPoAO9NR6sTfREUNlca4hutWeVY5P9VArYCL6mrb+H9LMCwG2C4PMisdw/GtWEoWI+YjPzHHQUsjo8wjOP7wB5/GjmfQOVdTlrzw5a2djdzJczS7E3BDhcHPr3rL8KXCrrCGRmyVZVRQT29K7XV44JLKSKbcI5FK7tuQCen45xXnmmyy6fdb1XbcxvwHHTGcgitItyTuZySi1Y9NSBmI3zMAedq9Bx0PrU9rGIlfkhiOWDYwP61nnWbaK1imaWNPOUMC5wffir9rdJNFujlUx4yZFI4/wrFpmyaGQXnk/uUDFycgAFv06n9B709nuryCVmWS1iUEbVwZm/oufbJ+lPto0AkMcIj3YbdjGR6nufxqNtVt9zFp0kgXqxQhR7ZH3jml6D9TF8KtBE8iCcsqcRB/l8tec7h6g5+taMniG1tYzsvVvZAcBLePLMfr0FStYWV6Eku7OHB+6hiwQPU/4Vl+LLz+ztMihtoYViZssqrt2qMYIHrmq0kydYoZaxSX6Tza7ZzO8jfu0HWNfQAfd9z1NXrTRrNSJo7WCNQMjfFhsd85qLRdca6gfykV3UgLH5gXGfUnufbNTTWV1qMgg1K4hhtR8zQ27lmf8A3nIGB7DrQ7grNdznr3wsLgPeaHMACSUi6BvXa3pwcCo9F1nU7C3ZZ7aaVASqmVG+Rh1wf6V3LPHa224ANDEAEBTCjsAoqZbrftw2M+p5A+lHO2rMPZq90ZWl+KbK9fajPBMQF2yMAD7A9Kk1vUks4W82bYxG6MBM+Y39361ia4+iSalLLe2MjeXgPOhKLI3p7n6VYsrRJnivYYGmiiwLa3R8CL/abnlv5UcqWo+Z7GVf+LrhIhElrLA5GP3oOf6ZqlJ4lnmjNtcvGLcrsKxjbgV2WsXBgXzpomZFK5LnOD7epzU82m2t/b2o1S2heaMb3zkFSex9fpVc0V0JcZN7nE+D9eh024mDISZDzJjJwOg+nU13mm38kyfdIjJJG5uSOozXI6l4VS6nkuNJukAyTsZMLx/dI7VzD6jdW8dzZTs8Q5V0Uc7gensPpTcVPWJKk6ejO21DxBeajdSafoh82VWwbk42IO/69/yrT0TSo9Jme4mE13dOB5k7LuJz97HPQVD4ehhGlQXEMKB9vlyBFxkjjH175PrWt5UxmdhhMjBP8XB7eg+lZydtEapX1ZZvXgeCQyyIqYwSTjbXKXOvSWl7tiBlhC7UAXgn/aPUGuhVJJIkSXyXQNuG5A3HoM9/c1lJZO2qXNuoVYXAk3bQAecEjHtge9TG3UcrvYNHuJ7jUT5YAV28yVmz+Jx09BXRebIZHaUvjgYPFJHFE8Qxhh2OcDj0pIBbXB86Eq4ZeqnIPvSbuUlYjvlgu43iubbzoGXJDcq2PauVg0TU9EkefRpfNt5DlrSRsNj2bpx68V2LosceB5e3kEYxk+1QIFAYcgMANp420KTWgnFPU5eWxu9SuPtNi82kzsuJIypAb3PPJ9/pWbeahrPh6dYri9WcTxllZgW284zg967OK1SKXMs/7oncImP3T6g1zvxAs/Pt47xZApiPltvHBDHj9a0jK7syJxaV1uYOjRnxF4iH2+QzQxL5khY43AcADHbPb613ulaZp+jtJJZQCF5fv5YsOO30+leV6DfnSryaQr+9xsx1xyM/yx+Nei2f9n3F8r2txHvI6sxG4HngdCRVVU16E0mn6nS24lMIE88Rd87GAxz7A1TjngsXWCSWPzQmVY8k443Efw5p9xa201pGzSSRDdwwyjKemPb8aqR2Frp8cro3lFmBkklk5cj1JPP41jobO5XstZtp9Se2tLhpWTLPuG1QfbPf6VJqemyakFjhcQCPJOed3ufQfrVqaZLhHkgtZJzNGPmAChj2yT0AzRan7MHaRpA7vwjdQT0HHbjrR6C30ZjwaRewzGG7uXWHHLWfyceh74+nPNaV1Z2Is5LZIwluRt8srgH1OTzyTnJ71JdXckzMArRyRFWO5SFDZBGD3/CnPcpLbSSXKoix5EgccY9807sLI890J20LXTbXBxE/TLdUP+GK1R4ssRfSXKp5e9RFIJGPzbT8rKAOCBxyelc3rkiapqqRacoCRoRG27A2DJ5z0xXU+F7VYtGtZY7W1uGkyWlaMFiecjJz06ZreSVrswi3eyNWLxVpl1IIjdwKjYJMgZcfjjFXLcWE+82EguIFPy+XHlEPcbhx74+tMt9PsSivcadawS87sRggDnvioLnSY2keXR7v7DIqkgQR5MmfbOD+HSsHbobLm6lmbcl1vi8sbFwU6kZ/l9K4vxvrEqalFF5ajy4uCeTzzj2HSugttLutPhV7N/7RYuWeO5XY+T3B/oa8/wBSkn1jWSbl4oHY7cyHYEAPT8K1pxV7mdWTtY7PwBpT2lu945BmuEDqMfdTPH4nr+VdYkA+c4BX7wUnv35qpbRG20yOOyYTLDEEVTz5mB1Bp0NyZMx3FnJgYxKvzjPXGQe3espNydzWKUVYI3jt4C8zKQx3b2GGOOx98VjeKoft9pbBrdFZ7hIkkB5VTn73tjp71t3zGK2+QeYU+ZYgcs3sKxdbvlTQbgbooJpJU8sk553g9D1I9KcN7iltYqXng/Tha+dAsoMeN2x/mbHp79KwIvCmoyy4ilgFqWwJi/b3HXNdRFavADNqNxcXTAHIJ2jnqQo9Kl2W9rIbhLmEb9rMxO3J9h2q+eS6kOnF9Dl9W8KT6baJPYSvNPF88m0YYjsyj2rX0bxSl3bxRXhIusBSxxtkPr7H1zXSSSXD2sc8SlZ2+by1wQQOoBPtzXNeM9LV7FNQtYQk8fMiBQCy98juR/LNClz6SE48msTW1KSfy1JEqk4Gx/l247j3ohIfMcTSTxty/mfKd3rjoR9KzfDerHVNDkgnSOa7thiEOOvHHPt0ra0qYPZfvYykyf6xWGBu78VLTWhad9UT+Qoi3syq6jCknP4N61kXsVjq8Elvfw/voUYq44YY5+U+nsa2/Ptplk8rA2kbgUIUn1zVG5tRB5iW4CeflXbGeSOv/wCqpTsNo5qx8LWDWn+kXEpkKBy+4LsyBwByDVaTR9S0ScS6NcG4gYZUx4OfYr3+orrZPs0ds0jYgEZCHeSRjjHPYdOap6hAYTFeQsWVFJ2Z+Vh65Fac7ZnyJGH/AMJJqlo6/wBpWUaD/pojJv8A6VeXXdP1aHylV4bg8JvfntwrevtWpaX11dFDc+WUPQBtwAx1GeR/KsLUvC4vLnzrKZIPMOWXGFP4U1yvfQHzLbU07eNoyySF5ech2OSR/dPSpJtRhs7ofaJE2GIyB3PJwcYHqa5q50zWNNiaNZY7qDZuKBs8eynnj2rOuNTbUdG+yyqWmgfzUfOflxgg5/CmoXJc7FnUdamlluvLknFmzDCNg49s9cH0rGt47m8nSO3iZmbIUY4x9ataPpraheLFNJ+5GNzKc4z0FdtYQJp0L23lERKSUK5OR/PNW2o6IhJz1ZkWnhO2gAlvZXkbqUxgD645rQutLspHhVYYXCIQF747fWr6nzGjePbIo5BPBxipVePAdSFL9i3X6e9ZOTZqoop2mmWkaF4bSJWxx8vf8elIbKAJuS0twXHzptHP6VbadI42807XzwAc59KyL2YSrOEWSMgEhohkNgchqFdg7Ij1nS7S4tfKASG4ALRAKFOfTjqKp6TrdtLax2mpr5bR/KJMkDI6Zxyp9602RZI0EUzklAwLEkN+PrzUN9pVpf248yNYLnoJFbLZ9+BmqTVrMhrW6GJa3U0haaVkgzhIgABj3/wFaaLLGiqdqsOegGB+P/6/pWPp893LdSTSOPIP3QpJqe4W4mfcpZF6EsMfkO9JjTItVvZ7e4Aa4T7OwyFUfMfr7Vm6hYG+iZ4CFdQGWIDn/wCtWtbwO5BuGjWdgfmbGR7CnxRRSTPCmJUXhyOBn69zTTsJq5y+j31zptxLE2V3cMrjofxrf067u9WmLuClrGdokRMufYE9PrWJ4plgkuo0tipSFdnHY5z+Na+gma20mMNKoD/OFUZIU9z2B/Orlqrkx3saF8lhauJBFJLdHBVE+eQ+5Jzj9Kz73VL2dMlmiB4WOJsyN25foPwrVsbSNYtyOCr87ccn3J6k+9Pe0tIbeSa6YwRjlgnT2A+tQmi2mVNOWC3iRY4GM0mPMK9j9TyfxNac8VyWAhWQA4LsGAJx069B9BVCDUIJmQ2kLRp90NKudo9/UmtcXJDBLb5y3OdvyoPUnual3KiVsSvcCIecI415bkAk9h6+5pmqXy2NzFZWcQnv5uFUklVHq3f3qOfUb3U5pLTRiqInyyXjdFPonr9an0zSrXS5WkEn2i9cfNJI3Pvj2otbcN9izbWvl5nvHe5uivXGAg/2VHT69TWTqehR6iZrmINBcHHlyMcdPUe/qauy3F5JdzNbsI4yu3ft4z6+pI9aqaTbEfK8jFkO1gqnJPqPr1zQm1qDs9CvYaM8tn9j1dkPkHEbxgDK+zdSevFc7q0TaLqZhhM3kggqXON68E9PevQ4oUgCByIi34vWd4sXSjatHqLIoVcxlDmRWPoP8aqM9SZQ0J7W7tNVsld7h9pG50DgAezfSqF/4ksLVWNsGuFXAVNoWMEd89Sa4jT5JzOYbYuyTHbsHVvTNdvpXhyCLy5tQYTyj5gg/wBWn4d/xolFR3CMnLYw7vxZqdw7JbtGu/oIUJYfj1q5pfhqS4kF1rsrEv8AN5Rfn/gZ7fQVvyQwW8EjabGkcshzmJRukJ7VQXU4pQbbUYRKc/PtXKk/Xvj1o5v5UPl195jdD0S0QzTxbwdzxGNXyMhj3+mK6Cxt/ssSIVCuT0LFsD6muFsZP7E8US25eRbOVscNjg8qfwrtXu0aeOOEgHqX3ZyM8gf41M07lQasXbgsMbpGfeeCVBCflWTq08ULeVCVkuX4QKcH3YnsPetNghRmZ1VSMnPAA9TWC1hc6n9okeUW8G/EMm3b8o/iIP8AWpj5lvyKcCGfWYJdYlWTZHiCJEPlRv2znr3wfauwtiJF3iYmMKScjC475rnrfR47WCPyTPcEthmCj+p/Cqly7aww0fSwYrCEgXFwCSBj+FfX/PaqfvEJ8ppWMi63rDXjSL9gtZdtrGWwrsOrkd+enpWldWczRMsbqTnJlfpzwQB6elPhis9MslRQiRRpt5Azgdz79asEoUDBgI1wwOeD6Vm32LS7kNvHJBAyTssikZ3H5T9MDjFeb+Nkt31cm2XExADqBwx6ZHv2r0G5njhjeeV8RoNzk9AP89q8+0Afa/F9uZHJUO0g8wcngkCtaWjcjOrraJ1Gk+H73T7VZ47krebg7oWbyumMEd/rUt2NVWUlNVmjaLDYa2UxHPoRzj61uAM8oj/ePEgwC7DDn1/Cs/W7qKNvJG3zNuMrwOegqOZtlcqSOfGr61CSgsre5MmT5kRKg/4U7UdQ1W1EU17FAsSKXZbVyH54wT+Wans2VLl0S4ea7blnYHYgHX9f1qvBHc3N7uWXzGY53H5VH1Iq9OxOvcvaJ4hXVGaOYOZtwEURHJGPUf1pbnQ4HZ7pbq4tXJziFgF3ewx+tOW2MVxGDPHv3ln5OS2Og9q0VhjciW9kVtj7hukyCcYxUN2ehS1WpnzWusW0YfTr8XjIvEdwgyR6K3vU+ka5bagpEmYrpeXicnK460r3kNtHIULJBGpLO3Yenv6AVwmuasL+6Ro7dIWAwNoy7dvmPf6VUY8+5Mpcmx3Gpa/plmJpbVkubmRVG0HKjHcmuRub288QXRjMMl0SCBtyqx+47Crug+Erm93S6iPJtuoQMNzH0J/hH612E8cWn2KpaxeTFEuNiqcKT2J/rT92G2rC0p6vRHCWOiW0vlQzee88vym4QHbG3bjuODk1BFcXui3q2yLKtzCxxtySfdR3BGa7DTr2+iuvJmtC28/fQYUD1P8AhWzfWkICzrtSdUKhtvzKD2z1HNDqO+oez00OT0rxjfSym3uPIkaUbQ0vygH0OOx6c100Fu1xbZuFj3EDJZdygei+g+lY91BZeI9JtpBFKkj5AlUZZG6EN6jPaqfguK8steurK6dw0URyobI6jBHtik0mrrQcW07PU6S98vRInvkZlRfvpner56DHY+mKx3m8TXMyXgiSCHkpBIQpYHsRjOPrit75tS1RJJVVLWzOYkP/AC0kx98+w6D35q9eTeRDJLJMNvUZXB96hOxbV/Q5OXVNdaCOG5srKKYn78kuD19M4rF1XUdRvL2007UgbdJJgNwXAfnBbPeu/umgkiPmrHKoA6gYHvWLruj22p2U6RE+eD5kLltxRvT2BqoyV9UTKLtuP0/w/aaQ7TJE2XO0zFi52ntjHH5dqfGsltrM0cCiKF4BJsIG2QhtrfTgr+lUPC3iRtsVhqbLHcoNuGUofQKffvXSTIhdTsLTlSU2cuPcD/IpSunqONmtDMsGkivBYt5iAJvCsMgD6/jWo4+z4KrIxTJAjUEAnrVdr6K2RBfyxwMBnDSD8RWBceLo/NEGkQSajOScYUhR/WlyuWw+ZR3OoM8xtWd1LfLlQFwfxzXnvjvTV+1JeQsQZMtLCf4T1JH19K1tQvPFEmkF3gSOQu2UhxuC44PfvmsFtA1q5aJrll2sCctLu2j1OOufarprld7mdSXMrWNvwjqYmgFqH2oigxqWxjHVffrXUR3IZmAxnGCM44rzDXNGm0u6iNsHltpSFQdTu/u/X0q7Drs8Nu8Esojkh4RXQ71P93Pp9acqd9YhGpy6SO7vDYRyJdzpH5icK+MuPTGOSfas2SJzcrql7A3mZIjt9oxGvv8A7Zx17dKjsNWsJIbYB1jVtuJQMKH7qR/Dn8jXSPGkiHLZRhwMVlrE10kUzJNOFZIfMjwSN4289veny2byLaiWOJUK4lCngHsR3qNbmOzkhtphgTMQEJ46df5VLdXEVreRxM6ruGCGyA4PYe+cUgGwWRt8hJWODlYT9xee3eqd8A2+SQSKVBCrjOfpViV5GmdHGE2jBThv51U1e9ZY8JZXTsP7g24H401e4nscRpIXRvEfkXYHls2FkbjAP3XH+fWvRIRDeZaYASpjcU6H0PuK5PWtS0eWJIb6CWZl5BDfvI8/7XH5Vzen6lfWm5dPmlEIOchc4+vpWzi56mKkoaHpTTX8V15M8Uf2bgJJGxGfqO1SX07RkLCjBW6SKQdh+hrlrXxabjyhdOIQp+dSMh/cGtZfEMMl4j29xFLan5XjK7Wj4xkZ6j3rNxaNFNPqaM9jNNHFIsqLKB82U+WQejDt3/OmcJa7WhJiGRsx9w9xx+lZ3iDXo9P8s28iySN/ywX5sj19vxrKTUfEF7F51japbRZwueXI74z1H4U1BtXE5JM3li07z4WKYdznKkg1PNHAhdxMwQkZaWTGPoDx+NZ8lpPJGpuriSRyPmR0AjY9jtA47d6ynv7uEyi509zt4LoQ4/L096LXC9jdnUiL5ZRvAxvAAz/TFeX38L2tzIFEioxIUsMbhnBrvJbebUIrcyzGzgXqkcmS+f8AaxgfrUsmn2EEIgksojtztkdd2WPc9zVwlykSXMcp4Ua9WbNlbRyjcC29tu7HYH1rspbgFsOzwksu5ZFGB7FulcXeTi0uCsBMKtwwQ/KrA8lfT6V02jahHeWxS4ZGuYwVbpl19SKc1fUUHbQs3Ec1tvdAM4+UM+3dz69KXTZN+0zHLA7gDwc9CPQ1kXGmXFrMX0+dthORDJ8yj1Az/hUwTVkgKMbG5XOfKdSh/A1NvMq5q6hDNJJiN40U9gOW/pWBeTxafDM0ZaO4YgFS2ec8lex4qyuuWoUW2oQSWj/ddHQsv4d6fex2d9FG0LW7shDxSbxgkfwkdeaaVtxN32J1sRaES2yllHzAAk7c9sVchaG4g8xkULjJGDkf1pml6gLq0M8RLo/VG6oR1FT3cQMXmKMHORg9PoRUvzKXkYsMslvgxjMI/hA6n0yf51FdTXNwVaR1jQHkDgfiatzKLVVa6uPnY9SML+XWqmoKLzyo0AMROeTgZ/3R1/GqRAtqs1yAVcLCOrnG5ue3tWqkDJbhERfL75OAB6CsyztwjYQtIqt0xhR6806+iuLqymKzeVuBwc9h1/Clux7I5DUYkEjSRFQpJ4HT8K63TYnjs4IS6mJUG9eB78ntXFeWXmSJWwWYDLHgV1cViYkSKS7TyEPKKcbvr61rPaxnDc1PLe6hMln5iyHgMvyrj/D3qNLG+lXbOpKZBy5yfrVyw1BZrnyQcYX7ucnNTXOoMHMdlD5zp9+Rm2xqfQnqT7CsddjXQy5LaB2JjyzL1bHyj3NLEbnVYGtLQlLP7slx6/7KevuaYbSe7kSTUbgSL18lV2xqe3Hf8a1Ldp2UrtigRTgEEkAe/v7CnewrXLunRJp9okShVRBgHHFSpHEAzJhlOSWXv/jVee5tgwgOJJG7EcdO9RW0TwIV37o2OYztA2ewH+NQWX7U/aEEnLRv8wcrtGOe3X86bcXMccpPmCKOMkAAZAPp9ayL3V7awBit/MubwA/ug5IXvlj0Fc5Jc6lrUgS2DNt6+X8qR59TVKFyXO2iNTVfE0ttvEaqt0wwnOTGPXHr6CsPSdIuNcnaWR2S2DEzXEjA5PXA9TV2LwnhPOvrsIg5bykLfXk/zrqbO0t9Nt47S3QnCmTe315YmrclFe6SouT94q6Rp1tpcLNbx7jz+8b7zfj6VbuUMturXMMGSynYxPI/DrVu7Nt5G95WVOgI+8SemKxruaBZhbxwzqVxiRnJBYjj61nds0skjVtpIUtC6pFJKvyoqAcVT320bqZIRJP1Z2XCr3p9gxaRUZI02qNoVeR6+34VU1aJrmXy4ZvMYNh1C5xjtn0pWHfQw/FtnI7JcoFbCHJU4O31wef/ANdTeEdbt44pIrtR5hwAVXJwBWvYWblna42SZ+82OBjtn0FcnrNtY2N9CdIn+0MxO6MNu+g4/lWsbSXKzKV4vmR0d/4lWD5LeJDGcYycA+xJ6/h+dU7jxbqE4EESRK8hC5jQk/h61Po2lR28BvNYgMl7KcohBbYAM9OgNdNY7mhWWRlWNhkLswfp7VD5V0LXNLqcI41q5nlt1N7M5O1iGIQ+5PSr1nrd34bkWxv7RVgRcAKoBP8AtBv4ua7JWi3LxIQvGd3ArlPHrma2tnRlLIWJHcA8Z/OnGXM7NCceVXTIp7651nUVeK2nhhCguWU5PoK6A3Vz5CIttdTKq/LnYCT+JzWb4d1izmsoY7i5Vbwpht+QOPfpmq114gVtUa2tmMiHjcD99uyjHRc9TQ1d2sNSSV7hc6bqur2k80135fzkLap8yqQcYJHU1HoektFd3K3HmRnYiI5GCQOSQfqBzW1p8zxxwWsNvlZs/d4x6/QVsSrZ20pEzcqMlj79vp0pOb2DkT1MW5tNWYultqAFsSBGZI8yHjJ5/riqC2I0jUFfU7ouNhYSuuRv4wM9OhroLa4W/QT20bkKcJM3Ax7DuO1c9q/n3U0ySw/MrbAzEhPwH5c0J9watqTTxnUkd4JkjgYgyRhfm29QM+/XHpioZrjyilvZTtHMg3ncuOOm0e3U8e1S2VjLp8bKziNWOTuwgXHU+gqG+PnyxNZQTTXCkvG5G0bcYOSeoPpx60IGQ2siTStNdszMhIWPkc+pNaOk28NxNDEJppLYA5ycHPYCqEVve3VxGs0Ma/L80gypX1+U9frWrHaMjqweQlWDAo2QCKJAjA8byzrcfZ84hiAITOdrepPc9Oa0vCWiQ2+mR6hdxE3coJUuchV7EenFc54ouYb26h+zzGWVhhwOhJ6fjXfWMsf2GKGVo5riNVQg9FPA5qpNxgkKKTk2XrbcsbSxjds4Cqcb/wD69WY7gMRJJJ5QUYPfH1psLx4CF9iN8qr0z9KoapqMY8xVhRJoWwGb5QxOMMPUfWsNza9hjapCutfYnDBQAd3J3scYx6ADtVnUI4b1XhukPlvwUBPT8KhSTlGMMRuNh3SI4IX2BPPNMiunmujlZGVQSY0PJPuegH1p+gr9zk9Qsb3wx5dzYXE8lq7tuUjhPTP1HfirOk+J4JLzzL8fvvK8sSxjkgc4I/rXXIiwF/Nl3yyg/LnKIoH3VH48nvXJa94QEytdaQBFIOWizhT/ALvofbpWqlGWkjNxlHWJ2UUqXMSSQ+WyMny7ecn61R1HWIbJYze3UceCRt6k9unX0rzWDV73TxNbpJLBIcrIAe4/kfcV1um+F4omS81OT7TIse8xMBs3Yzz3b8aTpqO7BVHLZDbeW61FTcv/AKForsMxgZeVQf0BrrZ5R9n822wS+CBjCtnp0qNpUkCxMCBj5eODmpY4SElUxmOLGAN3UelZt3NErHG+NrWY2cd8qlbqJv3m3qq49R2HH51v6Le2+raVCw8l3aMeZGWG4OOOe/vWZq5gsZoEjiknubt2zGWPC4+Yntjp+tVToWksiJbM9ndL9yZXJ+b3z7/StNHFXM9VJ2Ohk8P2QkLz2VqWPCkx5J47k96tRwQQIVVEgH8JRQo//XVDQ768gtZItcRJAq5WWJi7H6j196j1PXIg9ta6fD9suLjOMnaqjuWNRaTdjS8UrkfijVUs9KkEMyyXMy+XEijJJPBxWnpqxw6XADlJEjRWDdQcDrWLpGiJZ3puJpYbidBsiRQUSIHk4znnnrXQtDmMvnOBg4olZKyFG7d2V/LdboErn5CNoHHXrn1rP8TaZb3tncK0SGcJuVwo3ggdcjr9K0I7j94yuxAXCnGMMTzkf1pL+ONnG0YkXoxGMfSkm0ymk0eZeGJLdNRh+2H90X2tuPyr6Ejvz616PBamzb9w7mLH+q3fKD2xXnniLTrjS9TllZVaCdiVfHHPOD6Gtnw14lFvbLa3f79FYLHg4dRxgc8EfjxW9SPMuZHPTlyvlZ1tzBHL5cs0sm8tuXIBKHHQe3tUt4sM1ni4likhPUucDPbk9KoXOuWUIkijkSaUNtManGD9TXD6rq/22YNPkR5JWLsv196yjByNZTUTu7+5j06yeSYGRYkBJDje+O3JzmuW13xVHdWwS0eZQeGJIViPT/69cwRcXsjLaxSyNj5go3Y/Guk8LeHF85LnUlBxykJPfsW/wrXkjFXZlzylohPDulIZWu9Ts5XkchoIW/iB78/1rrVjFnC32W3VA38CjaG+uO9TKrtKG3knBGCcNz/Oq9oIUvZEhdllznynJAz3+nas5ScjRR5dDn5NCt7u+nmspPJYBcwNGCEJGeQe1c3rVneWLMk8OEB4kTlT+Pb8a7vVJTBqNjIU8uOXdA755DHBXn6g057ZzLKsqGSBlCncowwPWqjJrchwT2MrwxcWNzGPsNssN5HGC6gACTHXnrXQWl69xbnfAsbqQCGPJ/wrhtc0mbQ7oXWnySLBnIIzmL2z6V0Wla5a3sCfvma42fPG3B9z7+1Eo31Q4ytozVuJY5MgPgLwRyOKgL7GRlZGJ4z2x36VOqbSjglgQRgngUwWUaqTGqKCc8E1BRRle5tJ1khRntZSSyofuH1A/mK1PMN1YpJLGI2PGSwYE5rFt7e6spZViMssRbcoJwR3xurQm3uGAlypGSGAI9xxTYkeda3E0F9OoJK+YRkjBrc8Lxw2dncXkynaxC5Ayce1UvFixC7Vo5ldm/1iA52sBVrRLoNDLFJGZLcgb2XkoexIHb3rZ6xMlpI6dbqKVIzGWMbLnJXr/gaRwxifypd8ecgg/MpHY1Np0KLCFj2NHjKlWzmormAQrstgoU8mPHH1GOlYmpn3aGWH99GZoWGCHAOPy/pWBd+HcNmBmQNjaJMEH2zXUvDPtZXdkZTuSRSDnPYipI45ngRZgrqeozj8apSa2JcU9zi7O/u9HAjZB5bZIB9e+GFdNp+sx3KKA53t/wAs3xk/Q96kmgtZA0UsSuZDuK+/TNcxf6M0bu+mStIq8mM5Dr9PWr0luTrHY0rWNc+ddLJNcMcLvOT+XQVooqxzDzVLSsMjjIQfWmxoLVWmnZEQdGasa98QE7jbRgHoHk5/ED/GlZsd0tzd1G7h06Bd7ZkbhFHU/wCH1rBaS+1HeuVVE58rdt/P1/GqCNeXCS3TvhW+UzynH4L/APWrZ0e2/wBCi8vd853M7cE/QfyzTtyom/Mc9qFi0LAh43dsllRs7arwTOjltxz7967C7sLSC1ka3tbdpMZ3S5NcvqcIhaNXhMUpUEhTwauMr6EyjY19Iu4fIJuJ0hhXO5FJLyE+p9KvL4gt97rEu1E6FhgdfTtXMWNpdySAQwtjrlhtH5mk1CyuLQobhVw/IKnIpcibGpNI7DT9TjvJXIMbSR8+wH1q7dyO2xbRojcEYXeMBf8Aa964Ozn2fu0ysbkb8dSB2ra1/WZgPKhJjzwWXgkVLhroUp6am29za6XsF3dCSdRggDLE+uBWRqniG71G4+yWKsiudo2cu/49qm8KWELRC9nKyOwYCNgCAOgP14Nbtva2kTtLb28cDOMblX5se3pU6RY7OSMOy8MShd95cJHDjJWE7mP1Y10kKpa2/wBltoVSHjATn6knmnRRW5gKLIGjftn1rJ1jdHGogkKxxkHavygY6Z7mk25blJKJqb2kR4tzSBsqSFwOR0ArLivzo0hsb6UBQMwTNzuT+6fQjpViweZgssKERbep6yE9+egrRmto7qzaKSKNA64ZtoJyR2zU7aMe+xRNzIzqs6BocblQHls/Sn2+nSzXZmnUbR91SMAfhWE1tqejQ7rS+85gf9QyZBHQY/D6VFJ4rvJlWCxhZbh+CQNzZ9F9Krkb2FzJbnVahKlrJGbm6ggiH3d+A2fasC48V2lnvjtImuDn77Hap/DqRVHT9DgvpyLq/eS6PLpF82znkM570tzYRaZM0VvGXafbsdwDtPcEn8801GOzE5S6FyCDUtXXfqV09paOMCKPgsD7dh9at+GtKt7e9uJLeKT92wRHkwWz3we1VRb3bhIon8pSeWkbOP8A69b9tcx2EVtbx5lBUl5GPPWpk3ayKiluy2rxxiVFbcV/g3Z25qpFeGWYp9llWBODK2Nufb1600QxPM8kMEcO7Jkkc/MQapSwsJJFSRirnlVb5m7DjovFSkimzb82MIwLIrBc4B/HNV76OA2vlzRrOkgBIY53Z/p9KqTadayrHHeOxG/ewBIBOMYJ7iojPJdX5EAEdtGNpf6Dt6Ciw7mJ4j0q0s9OWWKI28xyAqsTuHvn+lYnh2a4hvPMhieZIsSMqjJ4yAf1q5rs66pqMCwO7B28tMZI25xkCuq0fSrLS1njimLMdpdzyT7ACtubljqYcvNLQTw5d/bLlbsXDqy7keIYDAk8D+X41qX28wSxW8CzYAABPr65rM1BEGoWroUIkwjEgBgAcg8c+oqG1u9S055lhQXVrvIUsfnUZ6ZPUVla+qNb20Zu2lm0Ft5by/6QwyQP4PwNUb/Tb2V0XcBApBZkOHb36YFOtZEjkN0I2a7L7ipOOD6E0TXlzJIHadUtoySWU9T7j0pa3Ho0E+nwTzW0E7TCNH3bUJIfuC2alniiWLdbsInDHnruB9P8+tZTapJLM7QFmLnoB0x3py3Fkk4i1CZVmxuy54XJ6fWizFdFmL7TehZCBCqv5fmqf4O59/QUzW5M6LfLaxPEu0ndnhj34PrTNU1uC2iSOwljnm44XlB+Ncbqer3F7NvvJSSmdsY4UewFXGDbuTKSWhc8C2iS6k9xLGrpEh2gjJ3HuB7c16THAkkUq48tSMEqMH868z0nTdVhsPtduFjVyCmWKseeo7fnW9ofiidrr7PqwRVGSxZQp+nvTqJt3QU5JKzN64ivb26RIHEMMYysh79s1Fe2RlRbWb944b727nHqeOKT+3lnvRFFGyqQQrbOCBz0q0HSZYYZTOWZc8fnzjj8Ky1RpozOvbX+z7CeSxje3wmQ0Z2knPUjvTLSYQApbW5DRx586MfNIM/r+NWr/wD0l7ZBIvlRkuAG67RwDjvkg/hWjaRR2sW1EUrjAwTTb0C2pDDJJPagXpdQMNgEblGeM4FZ3inxDDp0MUUa7riRSynP+rHTPuT2pZtTMbS/aY5cSMQkaj5QB7+9cz4wtGms47+OOQAP5bhuSB2z9OlOEU3qTOTS0NfwrokF0f7VvfKupp1EiJjhD3Jz1P8A9eusltPtSHzHZSCdjx9s8H2NcD4N1M+RHaBwJI2PDNjeD0A9Mcmu3aeS2G9N0sXH3BuPvgd6Kl+YdO1iaGKO2ttl04SRf4ucN7j6jtVe+nimspfLuhGsaltyNz05yKmhPLGdmc5zhhg4x0xVbUEtLuGRJIgwdcE7eQMdc1C3L6FWxsHupYtSnkfzmt9iR44jQ8j6k9zWXeaXOI3b+0GEiMG3H+DtyPxrU0TWLu6iUx2cslvgAS/cBxxnnjt2q8q+a0zm2WNmAyu4EsB3PaqbaZNk0YGnXU6kwFt5A3LKxJwM4wD1P0PI9xWXKt3BdXeoaOGa3jl2yRqxzLg5fBx93PYVt69djTbMzW1oVnkdYwmeM9PxqfQbZrGwitJFXcqku27J3E5Jqk7K5FruxZ0nVbXVIBJZuFl2BzGx5XnH6dKtSlo4JvMA2qpfaDnHrXNvb3FlA1xb2RhvLZmcSxgFJQeoIHOCPbg10VhqMN/Zi4sh5glUZAxwf7pqJLqjSL6MqpHKLKFZVUyBVwVPI9OenSoltUgu/O3TGTcWKO2QAeOPark1vPHAqpcDysAEPGCPw6UoWRAoL78DBJA+b3pXAijVrpWW5t1Ea8BXwd/HUrXDeKNGXTlW6trfyk3FXTfvGD0PPau9lZZIWbOw5wWPpWVqTWtyhtmBbzAY12gv14z7f/Wq4SaZM4po88+04TdC23HVDW7B4UluFilnu1G9dzhIy232z3NYNrGkF/5dwFOGKk544yDXYabr4jsAHXhWA8wY+QHpn1reba2OeCT3Nez0mG1tIVs3ZUHUkZDnuSPWrILiIIgCNghC3Kg9s0QX8IjZlkO0HDNsIVc9yfx61JJJHNCHZcg84BweO4rnd+p0adB8TKp2yfezlT6euDVe4lKTp5MitMzgYc5BAGSfb61QnumhuTEAZVYEp8wBPI4J7fXNaFnbgO0mVM7dcchfYZ6f1osBQ8SSzf2NdfaLV1K4kjkjcNtYEEE9DWhaTGayjdNqB4xkk5IJHanTAvbmG4WORGGCvZhWLbyppuoy6a8oFrMm63Dc7Dnlfp3qlqrCejNebypLQpIqsMEMjjgjuPrXEatoRgie/wBNZ1jX5tnoO5B9q7Ly2lc+bGNvGArbue9QapHutPLhc7W4IHGBnkE9sjinGViZK5z1n4uu4YoxcWIkYDmQZBb36VPH4zidyLmzcKcYKNyPzq5e6khkURQTdOHA4A9CPao9izhRcQmZD6DI5p+6+gte5fXVoZrdrq2bdHjDkAkj6iqd3fSwx+cjjbjIRcFXHbBrJ1CzbQnF5YysiscGMt1B7DvWI093qdyBGGd3bgA8ZP6CmoX1QnNrQh1S4e5vGmk+83JFdT4Ii3QXEpx5eAhUjqeuc1zepWVzBcRLdxCHICk5yPqT+tbWnaxJaOqIFmsh8u0DBA9R/gauesbIiOkrs6dbe4jmZ7dwu45KEfKx9x2PuPxqrdXbh1ibEdyTlUWNnyR6EDkfrVq0nF8Fnsp8KGIYEEgn6HpU1wf4ljUlTnB7fSsfU29Cnb38txEYwm11BB/2T64NJpc13EJV1LZnHyugxuH0qSYR38eJUaG4CkJKhw3+fY1hyw6n9pVLi4MVvtwrocBz7nsaaVyW7Fq/vLBLkBrhxcDBAjUsSPQgU19XtViYNNv4yq+Wwb6dKTTrJbR5lkWTzGO5XbBP4GtKORHIV157HFPQWpwjPearcE5aRvXoq/4V0emaLawhWuB502M/N0H0H+NFnOUi+S2iWJDyA3ftxio73UHKSEeZEyjcWCnA9Bmrbb0RKSWrNK5s7adkWWHzAh+8x+UVaIRI/kXAA64xisaHUJZbISPFlsfIucsx9SB0FVVv7lZFQhJZWOFK5wpHt3qOVlcyNe/LoFjjXfI+OD0A789qillEah5WjBY8E9/p3x71Ta6Nv5hLia5x+8bqFxzjjipLO2u7mFpppER5cYOzJUUWsF7lxJBMGWNw5YcMeij1qtfxw6hbx220+bjKs/HPr/8AWpZDHaI0UIPIyzE5Zj/ntU1nEu1JdzF2GTvBBP4dqNtR+RzFxol9btLhA6RrvLqeCP8AH2rNmleZ98hy2MV1HiO+aBEgQEbsu2D+ArB03Tp9QkKwJkD7znhV+praL0uzKSV7I6nQIjZ6UglIV5MuQewPT9Kls907Eq8ix7uWP8X0qe0sIkt1iDtNtHVz1NPQqcyMXMm3adoOAB2WsG9TZKyLs91DHC2ZNpUEcpz+A6mswwT3MTS3CFLdRgJ/y0k9M+1XdOVXV2dEBzxjkj6n1pl3M0dwolmlVU52g8fQmkhsWCQWMGbl5MueDJ0HsMVYmkY2qtExEROFDL81VYbk3fljzBI4O7IHAPov06ZrI8UX8oeCytCTM5/hPIzxgfrQld2E3ZFHXb83MwtbUkknDspzu9s+g/Kuj0fT7SC1lkt4DEGXaGL5lk4/8dBpmkaba6dHHBhDdyry7HJJ749vatiOGK1M7Bizud7EjGPp7U5S6IIx6sr6XbtZWky26wpubJHUr7Y71NeWFtfLEb0kKnfOM+1EMv2hd+zbCOSD95/TPoP1qnqD3TzBpAqxZ7Dmo6ldCrd2sqXCSaIxjdTzE/8Aq3H9KibWSt6yXlqYXxgtGnmgjvgjp+VSifa4lV3eNuCxGSecfKo9ela2mWqyF3lyWIzgcbfaqbVtRJdijpqQ3d5cmKQhsjIbPyjHoefXFWFsYUDTHHkDJ+bqfw7mmX1pcRajJfWvkyyeUElhb5cqOeG9aJb21MDyzzBIyPuHAHI6VL8il5kkzu9p+5RG3rjYFzk1hzm4lgn+y/OgVkOTxnBzj/PFVpdbgg3rC01w23CSP8uPYD0xVFZdUvFja1hkSzjOAE+VPXk960jFmbkmY9rMUvUkJKFDkAHGMdq7M3+qzB2t7UbpRkSrHkgDggdsDpzXG6jG0V4+9NjE5I967Tw9eSSWUMc6eSrkiNycBlFXU2uRT3sYN9rF428tIsEibQYlTb93pVyy8VzKIw8EJReNvIP51evvDMV48kyXMn2gnkkDafb1/GududFu7a6EP2ZpSRw0fKn8aFyNWB88WbF7r9u/y29vIwJyQZMDNQprismye3Rcjhlb+dCeHJEXdcXcMYPGI1LnJ7dh+NYdzYXUNw6GGYqrEBth5pKMWDclua15rJjUx2jbGcfPIq4bp09qZBpepzR/aGVURfuiVtrN9B/jV3w/4eImjudQPQ7hEe3oWP8ASumcpPMQ3zKeOnUUnJR0RSi5as4O1g1Oa6MEEDo5bklcBfqT0FBs3stRP2xozOhD46j1yf8ACu0JKxmJFKpuG75ugJ4qa50u01LLXGGRcgdtuPej2gezILjVrP8AszdMHOAPMRTgrk/X9Kr2tpDfWplESyRyOZIzMORnj+QrA8UaJHp8cE9mZGt2JDFjnB7fhUvh3WGtbcW8zFoDyO+w5/lS5dLxHza2kdbZR7rb7Myn7Sm5d5bHvwfp0rRjX7LbXMjP5tzIATg98ADFZcE9vNbuLKCKTcc5RiBuHXPpVqBILZnlVxkkFmY9OOgzWbNUU10e7adLi6uA4wCuFAZTn26itmVIYkjklcKgODz96s3VdWktXtVto3dpXESqwxknvz2pJ7icuRqJFvAuTuUjcf7uPSlZvcLpbFq6eC4WUbeSMLgAnPsKjSKSO2EF03no/wC7I2cYx2/xrPe50+yaIxBpJHH+tI3s2e24/wBKvpL9oiUwYOD8pycA+lO1hXPMfKWDWjCpZkSbaMHkjNepyPFZxRW8OIw2RGucDgZx/wDXrzLU45oPEUgHyy+cGXJ6EnIr0G61TSo0CtcLI+0E+WC/15rWrrYzpaXLDTXp8sbrcM4zlmJAI7A+9LfXDzxpYt+7crm4kUZ8uM9cY7t09hk1VTUdNuVS3S4UzMPlDArk9hk8Vo2UcNvGYUJ3E5MjHLSN3YmsdjW9x4uni2LbpGI0G3aeAQB8uD+lQaZcTTXMzyM0ahiBGeQKnnkGGiyQwGAw5x7/AFrL04vCsvzFfLbkuevGSSfU0kO43UoYrrxFp1u/3YkkuWj6hiMBePrmtSIK0A2nO3POecehrlJ9YVNYW6+zSJJEPLRXQgspzn+YrotL1yyvD5S+XE7DBRlwwI9CauSdkTFq7LBcRwSq/wAzAZAHfvXPxSjR7954Yimn3W3ew48iT1I7A10eECAxx5DYKlMc+9RX8C3drLbEMFlQrvXqM8YqYu242rk6FpIyFUvGRuV19PagnzWUDeFVcdOtZdrNqVrAYD5d20QwrA7HIHY9jV62nSe1WSJiA+DyPmHsffrSaGncc9vGYtrNvXHQniufv4rxCstrFGqjLNh8ZH9a15GcwySLDlcH5OATjvmsjXbtYLIpbqd90hLMW+6MdcVUdyZPQ4bVCjTrcRnPm5cjHGc1t+DRNJcvtH7gj97lAenQc+tc03OFAORXceEi0OlxRsmFldm3kjHpjH4V0T0ic8NZHQRSiCPeUyjZGfSqJtYZ5ZWsbqW3DYO2PDR5/wB09PwxVlplB+zvwGUkH+H8/WqumW6K7xxxeXwTjeSQe2KwRuQ/Z76xumllZbm0cDzGRMEHtleeOP8AGtaCeN1DIwdT0eM9Paq0c0sJkVZcc8rIOlPt9Mt7iJiGfz2O4TRvsYexI4P4ii/cNti4V82NiGVhjofl/XtXHavcRPFMxgkfbnEijO1uxz2/ka39UupdNtw1zbNdqpH7wFVyP9oev4YPtUH9sJDHb3EqxxxSPgFct+HSnHTUmTvoY2hXV/eyebBOkOV2MHG4HjrjtW9NbzlRJf6oscbKF3QxAKPc7veqFta3NxeXF3ZwQ21vIxIQkr5g7Er2z6/pV21dLi2azuYGTapjYNgsAehHYiqYkVbizkikML4GF4lU5Rx2I9PpWdeX506NRIUkcHaQDkH3+tQbrvT7oaddNGo2/u58cFe1ZltH9ruMTb7mY5CqnQYHH4VSj3JcuxXu7i41S/OzfKznagPYenoK6bQdKksYw86EXB4BJyFB/rVnSQ0mGkt9kI+UYwdre47davbtjv5RLb8ZIPpSlK6sgjHqwu7RL23aK5jHzDB/xHvXJ3ei3FlNi1lWTOdqNwT7ehNdVHdFX2uRhuQ3cfUUt2jXEIEcmG6gjmlGTRTSZxWnajPa3G+Jgr5wyHow9xXT2PiOKeUR3IEMjjbvHK59+4rH1CIX2sR2rRp8ih5nXAZuPWnal4e8qGOfT2eWJhlozgsB6g96t8r3IV1sdc0iPI48tg6YzgY/EetVLu7X5o/MXGOBjPPoQev0rldK124sAIpczwjjaxwyj0H+FdDFqunXigtKqFuCsgxj8azcWi1NMqC5urb5pICLUkbH3Z2Z7H2/lVi2mmnIfcAo+UqRj9a0AEZXUOGBGCGwQwrFSKGzv9qbjHKSqkNkqRzg/wBKe4bBtkXnpx0zgkVDARe3RhuFKwxgM6LzvOeF/qalmnitxH50hA/u4yWP9arWz3ctwYnj8nzN0gYn7wz/AD6VViDTvY4RAwDJED1jQ4z6AkfyFc7BI0kqmKJmdQUCJxnPWtoR+X5dtaANcuCxkznYO7H+lXIYILRdrFPMI5Y4y1JOw2rlGw08SWwa7bykJy0anBOD0qzeYkmVUDqoXg4OBSwndM7SNIRj5flOAKrX19tlMJGcj/VqOT9fT8aWrY9kWreMWv8AqI9x9T29yTVW9luArzSzLEmDkKNzH6VJHc3V0oSCMKg+9I33R7e5+lYmtXDLM6ookwdpk69O1OKuxSdkU9QuVubpiA+xVChm68dz+NdPoLwppVqqyE5DFgBjBzzn+VcW0hOAwwPTpVyK/uUgTbM3loNu0cBfwrSUbqyIjKzudzF5SsWEgVQOfQ/nTpm84eWGGCMk55x9K5a01yQyg3I3R4xlFAK1bi1e3kdY5Y5ip+87Yz+IHasnBo050zYsSTC24BmjO0Hov4VL5UV0pDpuBbDF+AwHXHtUbSRSLGyN5ke0MqL90+9Zl5fvaI0l1JuLZ2xqMBfb3pWuVexLqmrLY4SzbzLiX27dvoPTFUtLgkTUGvb9oxM/CDP3fy/Knabpvn4v9QwrMdyo3RR2JrWtzavNsi/esOS3YU20tESk3qy/ZQMSxwpYn5MDgD2q1JEJEkMxHlL/AAr/ABY9T/SorYKkrYyD3Ld6Wa7Z4nW1Ksc/fYjaKzZoLbXDCVgylYz90EdTVO/vIpJhCpkKHJlcAjI6YB+vpUkUQRYzM4aRDnC9Dk8fnRMDDiR3VpSQGbOAB2A/z1oAbGrNsS0jXZsG3PG0Z44q8JHhLqWzx0A4zTLWaNVGFVSQTgHOPqa5bxJr4l32mnkBOjOvVvZfb3ppOTBtRVy7rWtQ2gaIsZpcZMeeB6bj/SuXsrafWdQcW6KgJ3HJO1B/ntWtpnhkyKkmoM4dsHyU+8M9Mn1PpXRLFDptsDptuny5JjOTuPc/WtLqOi3M7OW5Q0rw/aWxDznz5OqtKuEGO4H+Nbc06IsUBUFB24HA7msq7vZLnKKGYFAwdzgDPQAVYhjWNI2k5kUAAjqTWbu9y1ZbHLeMrRbeaJ1WQLLlkLkHd/e/DOK6K2Yrb2zyAGNFACEZzxwfwrC1kf2t4ggto3IijX5jjO3uf6Vu3lrNPIGQvGgUAFSQR6k+varlskyVu2hYJGlu5FjwisMA9SD3NSybriMRqSqocZHO7/8AXVXS7WNbpv3hZ8fvG3f1qzAAmqSeWJGWRdzkjhSOB+Y/lUMoj1C1mRgY5wN4wwYZxx1HtWLoButRkZ7qZpYoDiMA4DN6n8K6W7tgI5BCSHmGC4GTzxxXH39rLoE0F3p0spibg7x39D6g1cNVYmWjudZNeSWgAlhXyW+XcnzFD7juD60sJlnHmC4ULnHyDOfzqGxeC4hhu2lcrw6juWI9PbkVq+RGsYdULOeVHeoeha1IreJHhMe0tnOcj7341X1E+XC7wrJNJgBVUdfqKnLeVOGUh8rghTyKVriOIZL4UgALjLHjnjrmkBVkxqFoYLyIjenKnqfp9DXF6vo1xpkkkkQMtqpA3n1x3H9a7jVrxINPeVVR5zhYwerMeABVC20qOOycXADzTL++fJ5J6irhLlJnHmOa8NakbCdppAZI3++gPWuztLmy1FEaJwz8kqfvA9eRXBahpF5psjsULwqeJF6EfSqy3UsO5CrI/Rskg/jWkoKWqM4zcdGel3K21xsNygaRWyhPY06VPLu/NkRrmZuEUj7ox0ArhtI1Z7SSL53aLcCYyeD9PcV2+mXiXNsssc3m7vmdsY2+3sfaspRcTWMlIg1aNQiKdOdmLBCycr1ycenpWJc6rc6bqE1vaPBMm7IXbkJ/s5zyai1vVmnupNk8pts/KueOO9czNLLvDYALcjA65q4Q7kTnroWNduJ59QE1yQZtozgDt0qNnbBeEsycZwpwv1rVtfC11cW6TTzrCSM7GUkgV0Og28lrZvbSwJC6vgFTxIMfePrVuaS0IUG3qcfBP5yKpG5wcjHrXW6R4lS4ZIbqPy5WPDj7rH39Ko+J9LSeD7VYpiZMlkVcF1z978K5gPKkvlXAZMHDAjBH1pWU0O7gz1wErgkZU9OM/hVd4o5pY5ZxlF6L6se5+mOPrXK6FrzJGlvdXBVcfu5GGduP4T7VuSapayhf31tIQQpHI+mKwcWmbqSaNa7ELBkYISR93uRWXb6ZZybpby2DytjlsngDAX2pRdw/JDIGSRQQGLZ8zvkVBPfWtptdpmUgYQH6+lJJoG0y3ptounlmhmleDOVhl5Cf7p6ir0p3fdJ5zzWdbapFetsjbcVODgYPPrVg3UcKMS4CKRliemaHfqNW6Fa9uo4YHaRXjROC+Mc+g9T9K5x9di+0MrW0klpkFAzYO71x/wDXqp4pvxe6oy798USgLg8D1/GsOWcqW2MVOeV/rW0KemphKprodnceI42gdLaFxIeF3gYH1wa5fUtQuJGbfIWO7589c9B+GKqx3bIM7ySeMCqwDzTBUUs7nAA7k1pGCREpuRLYxpcXiLLIIoycs3oK9NSCM28cMQTyFUbAO2OmCK4CWxl0m5QzhGRv4h09xj1q3pWrPY3hjkmZovuj5soBn0qZrm2Kg1HRnYTKcFbZQ791JwcYqJQ8ZyYxEW4UqeAabC9rd3YvLSUElCsm0/eA6fiP61ZmeJ1QNuD4LDYeo/yaxNht+lw8SyRnLx8kA43j/Gqsl5ubdCw+QZkUD+VNu4/PBUTSRuuUZexz0INY8t1LATFPIomA+SQfxD0IppXJbsareI4IpFt5YTJIxA2oo5BFV/D+n3Jjgmnk2iKQnyyvIIyBz9DWPbTK2pyyyoGYRDAUZxW9BczJtMLK2QMo/Rx2wexq2raIlO+rNe4SXcNjKM8fNnr7msm8juI547gFSOVZASdv+TWlEVuUJlidSnYnp+tRW7B2lQFkZWzhlxketRsW9StPAmr6ZsaQedEd3TlG/wAP51zMd3LpepRecAP+WcoHcZ6++PWuptrX7PNKIZgQxJAI5X29xXOeMUHnW8xKrJyhT6dDVw1djOXc7K0nWWEPyOM5B61WmUE5gXcD0btXN2mui202GBot5BK8tj5e386u6frMKgfvgY8ZZG4K1Li0VzJmhcSw+Z+9CsVGTgdM1R1a4js7ZpIJlV3QlVJ+8apy6v8AaZStlaPOzjcAy42+9QDTru+uVfUWSJU4RFwQD1qlG25LfYt+H7ANa/bHkZribqSegzWskbQIApUwk5wnY1VtPluZEXaCwDEDjJ9cVLIxi3srA5IHPYk1L1ZS0KmpRW80R+0RJMc8Oo2tjPqO4rBbT2UlIpkcnojfKT7Z6V10ziaNhGB5oOM+hqjab0leOe3K85DL90j/ABqlJolq5y9pe3GmXGIyV55Rxx+Vacms28iMXt2RiQ2Ubv6g1f1LSoLtDIpZMc8DJHr+FYr6DLlhHPCxHOORkflV3i9ybNFuxkV5VkmwJpWOzPVU7YrWneJwIo9rNGNzOekY9T/hVGCWC0heVyPM/jlbnJ9APT2qG91m2Ni0FnE3zdyMZPr6mptcd7GjZN5ULyk8SYJk3DIQdAMdPpRbaktwzw2lsJJc8IpwAvqzViaTYG7RjdyyCNWx5K8Gt+PybO3KxQBQeiLyT9aJJIabZBL9t3ZdgVPymOD7v0LdTSoDMQ0gGeT5Y/ixxyan5nTGSsa/wrxn2qprzItgyl/LJwoVe/t9KQeZV1DUpVURwzJHGvBdeM+y+wqpZBbrIjVlto8Bj3cnoM9qr6XYC/ugrs3kxjLkenoPrXSukEEIGBFbx8gKcc1TstESrvVkI0y0MboIQGfq3U/gTWJqujPbt5luC0B7dSK6a1cTqHUHyz0Y8ZFDrF9p3uwLRgcN0T/69SpNMpxTRwgLRkqQQe4qVLkru2kgniu3KiQBJERtxJyygkCuX1jS0td0tvKrRZ+4fvCtFNPchwtqOtLvFkytMQu/PljvipdPVLh5r+9fMaNtQNyM/T2rBGRxkjNbXh5POFxFyw+Uj60SVlcIu7sak16dRVYIo5PLYgF24z9Kv4ht7dorE7SeOD8zE+9RO8NuoSIhnzgKvVj/AICrsNtHAokYbnxnA7VizVIsiPyrZFmZ3kIwQnOfYUfuY8LxuCbwnoKc06CIyt8qgYHHI9qov5d4N8qnYp3bWOAMetSWSpISUPmBiPmIBB5rNudTtozILqVmZGwUHJH0rJuJnvdTlXTGEce3YXUYDfl69BWjZeGoIZdt83nOcH5SQv09TWnKluZ8zexSe61HWd8NjGy23ClVwox23H+lbekaNHp0Ymys94RwTwq+uM9PrUtpG2nXr2tvGFjmTzY+PukcMP5GtGNYPlEiYdlOMnk1MpdEOMerK63I+1l3Kh8Ybbk847VZW7iJ8pEOV56Y4+tPgihgWRhEEPXceQOKrTXEJUMoZk9MYJNSXsVZt1tdRRybtspwhXG1OOhqG+1DyiLnftiVThNvLj1J7c4wKr+J5rn7HJJGxUIyg5A5Hrn61ShuDqKm5nQPbxyLti/vsSBlvp6VajpchvWxP4cWK1Mt7qD4ubjkKeMKTnP4/wAhW3HdDUDhd3khsA5+/wC/0pZI45jFG6BmPUnqtFrAsLS5QJED8pz+eBUt31KStoXJook2xRKFPsOKZMkUSKqyFSSdznnBqmzBod8TMhYkDd9aSUCKM+Y25QPmJ4B+n8qkZcuJ47c/NJ90cBRmsbV2N9ZyooDwMpKsQdwYcjFTz273S742SFCh2kckZ7/zqWxiRrOEwOVjTuy8svpVLTUT10M7wLIstlNEQGkifIyeAp//AFGt5pZBd+XHKpAQblVCSCc8k1yuiQzWWq30kKNJa7GDOvHfOB711Wm3cMwwjNIw+Y8Y+lOe9xQ2sSxQiOHeFG4naA3Rayddv5LW3RYlY3E77UIx261p6pf21pbkzSIrD5toPJPpiuY0159S1FNQvV220YIjVznJPHA9KUV1Y5PoiXTNHe4jEk8jPdE7jMGz5RHQL6+9W3e5iCCV5PKX9052Yy/YjuRWvGY4wVjAWMj5ccA+1Y8l463VyTIpKBfLRRk5YHJP4D9aLthZI0LBnmhjd8FsYYEY5+lJeQ2rMsv2eN51bDNsBbpUXl+dHGJZpUViN2zhm9s9hUo/0aZY4EJRRwAPz/GkM5LxBojWmLu0VpLR/mIxyn/1qrWF48askM00aMpD7T698V31xcGQkBSpAycHqK8/15I7XUZPszcOSSuPunPI+lbQlzaMynHl1RUuAZNoDZfoEHUeua6fwzo/2Mm6vNrSsmUj67R6/Ws7RNJ/cHUb2QJAOQvVmrqvto/s7z4wMgDjHze5pTl0QQj1ZchleVndHWMgYIYYz70M6oEZSEkYYBxnH4VnW95KrvHPYeZk8MuCCO3BqwYVEz3CoUllxvXrgDj8PwrGxtcnYs4jmJIYZG0EEfUVh6/o7X6F4GVrmMegBcehP8q0VuQ+8MyoqfMCCMADrz6U+0uXljP7kxlj8xc8n2H4U02tUS0nozzdzJE5VgyMp5U9jVi3um+6SB9ehrt7u0tprlWuLeJ1xtyVyc9uRz60yPRdKiG5rUnBz82f1rb2i6mXs2cfb+e9yzQK7iEb8oM7AK6nTnTUoluZGjNwo2Ng4x6HFS3aRaVKl3Y26tE2IpIoxtyc8EevpXLa2nlzRzCJYPO3Zjxgrg9x2pfGHwHUX9v1SOdVMYBLAgZ56HHQ5rGvr9bpUhcB1iUjcDxj29aw47srHKhHySdVFNEwCEDOT1qlTsJzvsJvyXfdtPQAc102heHo3SC7vXLEjeIuMEds/wCFZvh/TUuFa4nUyIp2rGO59T7Cu8EMccY8sKdowFAwMen0pVJ20Q4RvqzMudJ0m6lYyQIsmOdhK498Dimy20FhcW5itoFY5XfjG0fh/OrhZDIItvyYPz55X6j0rL1H7XLcCKyOPLHIbkMCMdKzTexo0ty7q9lFfWrKyncOVYDJUiuT1PS76Pc8sAcJ1mj5BHuK6m0hlayKXMjJODkEdR/iKtwtJKpVo+UAAJP+s46/0pxk4icVI4jRtQFlfL5wxDu+bHb3/rXZLErwb4JV8txuXaMrXJeINLkt5DdQofs7ckf3D6H2p/h3VXtnWGaTFqcjkZ25/pVSipLmREXyuzN+C3nvbZ4lvBG7sTIWj5/4DzxTdS8OWSBpmecE7RuWTPJIHfnvReX+mwODLNmZDnMQ5PscVUn119T/ANDsQyPIyjzX4wAc54/KpXN0LfL1IW8NGOR1gumSQH/lovDfiKrTrc6c229td8APEsLHGK6xlP3iykEBWzwcio5HKI25PwHORRzvqLlXQraVqlndlI4ZgJtuMOMMfar7RjJLuQT93A6e1c9qOkxyr5kMaW8uTgr8uG7cVc0XVWuo2trrMd3Bww/vD1/xoa6oafRl5LhoSocFVYjBYHr/AErnvGmxjAwI3qSCO+P8ium3iNjglvYcnFcr4zU+dbuOAykfXmnD4hT2KHh5I5bxhOqyKFJCMM7jXVfYLO9t442gWNOu0LtYH8K5zw5by3DSOuFWPAzjrmuht47m3/du5bJ+WRR932NOb1JgtCvG8+hsqzFp9P6B8fNH7Eelar29vcJvjCvDL82Q2efWk8+OVmjlCsffuD7elYyk6PMzwMZNPZvmQHLQnufpU7+pWwlzZXFsVkgZ9qnI3nkeqmpp5o2QNKyOD8pK5HWrM0rBGcS7oHHXAZeehHpUP9nuBEY5s2xOGiccD3B9c0eovQWG6CNtmz5T8pLjg/X0NSWMkk1mzo4k/eOBuPKgHgZqrdRrawNEpyDleWGR+dUNHnmiUpDJw0hO5xhcetO2gX1Npp/K5KkjuAen1qpc3Mex2ZJkKY2lOpFIzySzsZ1ymQpK8bD3yPSo2juIJHXdujzlSRQkNsgTSBMxkvJzIOigDaKmtrCysCZXOWzwW5x7CpG3SHEYOeu5hS2qSXF0XZspHwuBxn1+tO7JsiK8mNtcm5iRmhKbZO2COhxViK7hljBtz5hbg7f61LLAhbYVLKBk7ug/+vWTqEKaWRc248t24EfJB+tG4PQvTzraLumkCDqB1J+grnb68NzMWclUAwidcD/Gkjju9Tkdx8xB5ZuAPatrSdJS1xNdKJJT0HXH096qyjuLWRHYRNZ6aG24kl+Y7jj6U1pxNgTbcDHGOPyrSuIzNIwDEMRnA9Kr29t+82gYCcs2Km/UdjTgY8KI8KFzz1x/Sont0adp58bFOcHp9TVZZ/8ATPJhLkDLPnoPT8aihjle+aGaRzbKN2w8556Z9KVirl2JC2+8eXbG+AoIwdvb8+v41BeC1tonKorSyAhFznr3qzJ5k0gWSM7R91ewHqaie3t5bxmKO7oBz0VfpSA5G92vIzjcH/iUjpV7w7e/ZJZQ6M8ZXJAOOnf3qlfOzzOHyWViN2OoptqJ1YCKJmMo2r8vX6Vva6sZJ2ZtNrJEzS2dpGjkAb3549hWvZ6ot1EgcfvmOzb2z6/SuQvIruNszxPGBx04/OnWGoTWc4kTB9Qe49Kh001oUptPU7px+6DSAORz6DNZF7JJetLYxypGEQPLIOmO4qhe661wSVXbHngd6qtqE72VwsVuEjkP7yRV/rUxg0U5o6O1ksbG0t0t2WQf60AAEsemSaLzWgnlNEqyHnOOBn0FYFvqIdI4GVYUA27wuSBWqljCYleNVfA4YnII70nGz1GpX2NSxmke2+2XbYBxsA64Pb8aAshvRLM7M5/1ajjA+lV7OTaQ8rH0Cj09KsXerW0SuRjzUAJwMkA9BUlXLF1O0Q5Gdx4APpWVeXMwmhKBMFiG+b7vtxUIvDOTKV245yw6fQVPbIGtWllyqAbl+XBPvRawr3KOqs8FlPGwdi+SSBkAGm+FY5JIG2HKiToPpUeuXirCFiBxIpHP86veEUMWnSEqT5r5JPAwOP8AGr2iTvI6BUMJDk4LcHA5FSSqZGBiAyfvH1xVNpFhclyxUDCADOP/AK9XLcvIQMsBjOWGMVkajBChuF6SLjDemc9hSzQxXCvFOiSIWyQecVXVGgvY0jV2ibJLk+pyc1ICJZ3HIWM7eO5xn9KAG3cfmxmO3Pkt0DMuRj0plsZIY2TLOoHLZAwe9XDtK7884zk1Q1K9trSzaUlc8lFH8T/Sha6A9NTE0fUH0meW0nRZE3M2c9W9efpUNxrk7ObfTEaNpGx8vzO/49vwrGu7hriIMxzKSQx9e+a7XQLW2sLONkjSScj5pAPmYnqAfStZJR1ZjFt6IzrDw8kw3anJK9wWBaNGGB7E9zW3BDJBaq74AVs4A4A7DFW1VGQliVeQdR1X3zVSbzwrKmXZj1Pas3Js1SSJpAZ4BuJjU8cDnNV7S1tII3MS4Y/LuYfMxHc5q3GZUQLIqvx0BwSao61KFVNgIdjgsDkr6UvIfmS2+xmwjsVB5OaXypE3yHJccDkD86h01ZXhLzIoyRxjNF39oZWWCIEluWY45oAljujLE+yHjGATwa4bX4tl9JIPuu7d/euu1i8+w6WUkKm6dMfL0z3riJW8yJIkUlt2R+Pataa6mVR9De0B5J4RApVUKjJPOAPQeprpJHig+Z4x9mT5GfHKZ7/TnrWTpVk1jZxxlS07sGcg9PatpZguE5OeCCOCKiW5cdtR2nQpBEVU5XOAWbO49qn3+XHIWJ9TWJYEWbXUPT7PJlc/3DyuPwJH4VNd38kkSbcoG5ZcenY/lUtajT0GTKs7G2hhjEgAaV84WJCc/iTjpWmiMvDp759vWs6ws4bWzSeaQuXHmM/OMkDt3A6fhWr5qiJNzA7iACooYIozP5E1q5f92JtpLdsjAz+dWiojY7lU465qrrRBtJIhxIQSnGckDNVxcJc2UNxK6oJAD05yaLaBci8Q3C29rGq7SrSBj9BzXOuF1jVIkLFUO53cDJUdf8/Wr+o2d7fkP8ijbjy+SVH19aj0KyaGSSNpSsrY3x7ewPrWsbRXmZu7ZYn8NWiOpWaQIVBAJHzH2OKfoml2USSPPF5s6k/JJyAM8YH9a2XZZkXz0XYgyWPb0NZlxBINTiaORhCe6/xexqeZvRsrlS1I7mRbHWIpAP8ARL0BZFBwFccZ9u1bdpLEFEP+rPIC5yWqjrlkLnSpREpLDEi/7w9P1FR6QY7hI5QSr7MgYyff9c0nqrjWjsWRFLPM0iOpZcblIxj0+o96ddzi2Hmbz5v3ef6VFqTy2UcNztI8tgr7Omw9f1wakvbZ7pUYHLBgenSkBat5UuIxPasJQM/LnB/Co45opjmRWVumDxUdhby2zlncsoGAMYxz096W4KTP5pT5Tj2bNAx97DFHE000iCE4BLcg54ri9c05tOmWSE5tpSdo6lT6GuudI9yhkHXKg9Mis3xXbNLpfnKGQRkMUPI9P69aqDs7EzV0UPDEFhc7vtUW6UZI3n5T+FdNDb26FDFAg2KQuABj1FcRot6LR3MkXmKo3AY967y2lcwCQo20qG2gckdadS6YoWsNAjuFaOXbnOPQ02TbAwAQvkY5PIpt5bfaQjJJJExAKyKM59iKLiNdh2ja/QkVBbEJ32wYncQcfXmszU7NpQ1zaoY7qLlHBwTjt71Z3vDA5jUlTxgD7tI00kSBpCNm4AsF+6aa0Jeo7TZINQgWWF8PgA4OCD3BrO8W2srWSSF8+Uc4I6g8cU660stcCe0ke3lk6+WeCfeqN6+rITDdL50TKRuUAZq0tbol7WY7wi5/eqCASM46ZroZWZkwAMjtXE2c0lhfReYpiZGG7I7f/qrf1C/CXTBgHiOCjoen40SjqKL0sWjbxum9TtCZZWBPQ8kfSn2s0DQthFWPjDddxNUEmM0TmFivlnOR3Hrj1pY/Jh2JOjqsnAIztPvSsO5K9vPYF3sohcWbcmHuM9dv+FTaZe26gxxn90TwJDgr/snPpTkkeAFVbKjseo+hqC/tEvyJFVUlU/xLkN7NRvuHoQeIFjlIZGUPjy29s9Dj86tRRJPaRwzBSy8blOMGs2HT4riTAikimhPzKG6H1BPatiGJ1RldWLYwRt5/+vQwXcqvLPFMI3G8fcBbjI9PTmrLSA25aEFuuMdvY1Sgt5pLs+a7SQjop6Mp/rmp0haC4kuYxKoP+sQ8/iR/hQCP/9k=" class="story-img" alt="Struggling crops" style="object-fit:cover;border-radius:24px;width:100%;">
      </div
    </div>
  </section>

  <!-- STORY 2 -->
  <section class="reveal">
    <div class="story-grid" style="direction:rtl;">
      <div class="story-text" style="direction:ltr;">
        <div style="color:var(--primary); font-weight:700; letter-spacing:2px; margin-bottom:12px; font-size:0.9rem;">THE SOLUTION</div>
        <h2>Meet KisanMitra AI.</h2>
        <p>A personalized agricultural operating system in your pocket. We merged powerful language models, vision models, and real-time NASA data into a simple Telegram Bot that anyone can use.</p>
        <div class="glass-card" style="margin-top:30px;">
          <h3 style="margin-bottom:10px; font-size:1.4rem; color:#fff;">"Urea kitna daalna hai?"</h3>
          <p style="margin:0; font-style:italic; font-size:1.05rem;">"Tumhare khet ka Nitrogen 140kg/ha hai (low). 2.5 acre zameen ke mutabiq, 50kg Urea aaj daalo." <br><span style="color:var(--primary); margin-top:8px; display:inline-block; font-weight:600; font-style:normal; font-size:0.9rem;">— KisanMitra AI</span></p>
        </div>
      </div>
      <div style="direction:ltr;">
        <img src="https://images.pexels.com/photos/2255933/pexels-photo-2255933.jpeg?auto=compress&cs=tinysrgb&w=800" class="story-img" alt="Farmer with smartphone" style="width:100%;object-fit:cover;border-radius:24px;box-shadow:0 30px 80px rgba(0,0,0,0.6);" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
        <div style="display:none;align-items:center;justify-content:center;font-size:5rem;background:linear-gradient(135deg,rgba(34,197,94,0.15),rgba(15,23,42,0.8));border-radius:24px;width:100%;aspect-ratio:4/3;">📱🌾</div>
      </div>
    </div>
  </section>

  <!-- FEATURES -->
  <section class="features-section reveal">
    <h2 style="font-size:3.5rem; margin-bottom:20px; letter-spacing:-1px;">Built for the Fields</h2>
    <p style="color:var(--muted); font-family:'Inter'; max-width:600px; margin:0 auto; font-size:1.15rem;">Advanced AI technologies distilled into simple, highly-accessible tools meant for practical use.</p>
    
    <div class="f-grid">
      <div class="f-card">
        <div class="f-icon">📸</div>
        <h3 class="f-title">Vision Diagnosis</h3>
        <p class="f-desc">Snap a photo of a sick leaf. The Llama Vision model instantly detects the disease, assesses severity, and provides a treatment plan in your local language.</p>
      </div>
      <div class="f-card">
        <div class="f-icon">🗣️</div>
        <h3 class="f-title">Voice-First Chat</h3>
        <p class="f-desc">No typing required. Speak your query in Marathi or Hindi. Our Whisper model transcribes it flawlessly, and the AI responds naturally.</p>
      </div>
      <div class="f-card">
        <div class="f-icon">🛰️</div>
        <h3 class="f-title">Space Intelligence</h3>
        <p class="f-desc">Using your field's GPS coordinates, we fetch daily radiation, temperature, and humidity from NASA to estimate Crop Stress levels instantly.</p>
      </div>
    </div>
  </section>

  <!-- CTA -->
  <section class="cta-section reveal">
    <h2>Join the Revolution.</h2>
    <p style="font-family:'Inter'; font-size:1.25rem; margin-bottom:40px; color:#cbd5e1; max-width:600px; margin-left:auto; margin-right:auto; line-height:1.6;">Sign in to the Web Dashboard to register your land parcels, upload lab soil reports, and unlock heavily personalized AI advice.</p>
    <a href="{{ url_for('auth_google') }}" class="google-login-btn">
      <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G">
      Login with Google
    </a>
  </section>

  <script>
    // Scroll Reveal Animation (Intersection Observer)
    const reveals = document.querySelectorAll('.reveal');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if(entry.isIntersecting) {
          entry.target.classList.add('active');
        }
      });
    }, { threshold: 0.15 });
    
    reveals.forEach(reveal => observer.observe(reveal));
  </script>
</body>
</html>"""

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
