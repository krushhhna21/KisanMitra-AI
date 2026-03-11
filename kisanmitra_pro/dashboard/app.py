"""
KisanMitra AI — Analytics Dashboard
Run: python dashboard/app.py  (from inside kisanmitra_pro/)
Open: http://localhost:8080
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template_string
from database.db import get_analytics, get_recent_pest_reports, init_db

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>KisanMitra AI — Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; }
        .header { background: linear-gradient(135deg, #1a6b3c, #2d9e5e); padding: 24px 32px; }
        .header h1 { font-size: 28px; color: white; }
        .header p { color: #a8f0c0; margin-top: 4px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 32px; }
        .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 32px; }
        .card { background: #1e2d3d; border-radius: 12px; padding: 24px; border: 1px solid #2a3f55; }
        .card .number { font-size: 42px; font-weight: 700; color: #2d9e5e; }
        .card .label { color: #8899aa; margin-top: 4px; font-size: 14px; }
        .section { background: #1e2d3d; border-radius: 12px; padding: 24px; margin-bottom: 24px; border: 1px solid #2a3f55; }
        .section h2 { font-size: 18px; color: #2d9e5e; margin-bottom: 16px; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 10px; color: #8899aa; font-size: 13px; border-bottom: 1px solid #2a3f55; }
        td { padding: 10px; border-bottom: 1px solid #1a2535; font-size: 14px; }
        tr:last-child td { border-bottom: none; }
        .badge { padding: 3px 10px; border-radius: 20px; font-size: 12px; background: #1a6b3c; color: #a8f0c0; }
        .badge.red { background: #6b1a1a; color: #f0a8a8; }
        .badge.yellow { background: #5c4f00; color: #f0e0a8; }
        .footer { text-align: center; padding: 24px; color: #4a6070; font-size: 13px; }
    </style>
</head>
<body>
<div class="header">
    <h1>🌾 KisanMitra AI — Impact Dashboard</h1>
    <p>Har khet ka saathi — Real-time farming intelligence</p>
</div>
<div class="container">

    <div class="grid">
        <div class="card">
            <div class="number">{{ stats.total_farmers }}</div>
            <div class="label">👨‍🌾 Total Farmers Helped</div>
        </div>
        <div class="card">
            <div class="number">{{ stats.total_queries }}</div>
            <div class="label">💬 Total Queries Answered</div>
        </div>
        <div class="card">
            <div class="number">{{ stats.total_pest_reports }}</div>
            <div class="label">🐛 Pest Reports Mapped</div>
        </div>
    </div>

    <div class="section">
        <h2>📅 Last 7 Days Activity</h2>
        <table>
            <tr>
                <th>Date</th><th>Total Queries</th><th>Voice</th><th>Photos</th><th>Mandi</th><th>Pest Reports</th>
            </tr>
            {% for day in stats.weekly_stats %}
            <tr>
                <td>{{ day.date }}</td>
                <td><span class="badge">{{ day.total_queries }}</span></td>
                <td>{{ day.voice_queries }}</td>
                <td>{{ day.photo_queries }}</td>
                <td>{{ day.mandi_queries }}</td>
                <td>{{ day.pest_reports }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>🔍 Top Query Intents</h2>
        <table>
            <tr><th>Intent</th><th>Count</th></tr>
            {% for intent in stats.top_intents %}
            <tr>
                <td>{{ intent.intent }}</td>
                <td><span class="badge">{{ intent.count }}</span></td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>🐛 Recent Pest Reports (Community Map)</h2>
        <table>
            <tr><th>Location</th><th>Crop</th><th>Pest</th><th>Severity</th><th>Time</th></tr>
            {% for r in pest_reports %}
            <tr>
                <td>{{ r.location }}</td>
                <td>{{ r.crop }}</td>
                <td>{{ r.pest }}</td>
                <td>
                    {% if r.severity == 'high' %}
                    <span class="badge red">High</span>
                    {% elif r.severity == 'medium' %}
                    <span class="badge yellow">Medium</span>
                    {% else %}
                    <span class="badge">Low</span>
                    {% endif %}
                </td>
                <td>{{ r.created_at[:16] }}</td>
            </tr>
            {% endfor %}
            {% if not pest_reports %}
            <tr><td colspan="5" style="color:#4a6070; text-align:center;">No pest reports yet</td></tr>
            {% endif %}
        </table>
    </div>

</div>
<div class="footer">KisanMitra AI v2.0 — Built for Indian Farmers 🌾 | Powered by Groq + NASA + Open-Meteo</div>
</body>
</html>
"""

@app.route("/")
def dashboard():
    stats = get_analytics()
    pest_reports = get_recent_pest_reports(10)
    return render_template_string(TEMPLATE, stats=stats, pest_reports=pest_reports)

@app.route("/api/stats")
def api_stats():
    from flask import jsonify
    return jsonify(get_analytics())

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080, debug=False)
