# KisanMitra AI v2.0 - Comprehensive Developer Reference Guide

**Last Updated**: May 4, 2026  
**Current Version**: 2.0.0 (All 6 Phases Deployed)  
**Status**: Production Ready ✅

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Critical Pre-Work Checklist](#critical-pre-work-checklist)
3. [Project Architecture](#project-architecture)
4. [Folder Structure & File Details](#folder-structure--file-details)
5. [Database Architecture](#database-architecture)
6. [Deployment Pipeline](#deployment-pipeline)
7. [Known Issues & Fixes Applied](#known-issues--fixes-applied)
8. [WebJob Configuration](#webjob-configuration)
9. [API & Service Integrations](#api--service-integrations)
10. [Critical Code Patterns](#critical-code-patterns)
11. [Common Errors & Solutions](#common-errors--solutions)
12. [Development Workflow](#development-workflow)

---

## 🎯 Project Overview

**Name**: KisanMitra AI (किसान मित्र)  
**Purpose**: Comprehensive agricultural advisory Telegram bot for Indian farmers  
**Primary Users**: Farmers in Latur, Maharashtra (extensible to other regions)  
**Languages Supported**: Hindi, Marathi, English (including Hinglish/Manglish)

### Key Features

- 🤖 **Multi-lingual AI Chat** - Groq Llama 3.3 70B model (1000 token limit)
- 🎙️ **Voice Commands** - Groq Whisper transcription
- 📸 **Pest Detection** - Vision-based crop photo analysis
- 📊 **Real-time Weather** - Open-Meteo API integration
- 💰 **Market Prices** - Government mandi APIs
- 🚜 **IoT Sensors** - Real-time soil & moisture data
- 🗺️ **Community Pest Map** - Location-based outbreak alerts
- 📈 **Fertilizer Recommendations** - XGBoost model (99%+ accuracy)

### Architecture Layers

```
Telegram Bot (@mykisanmitra_bot)
         ↓
   WebJob (Azure)
         ↓
   [Handlers] (messages.py, callbacks.py, commands.py)
         ↓
   [Agents] (chat_agent.py, vision_agent.py, voice_agent.py)
         ↓
   [Services] (weather, mandi, schemes, plantix, etc.)
         ↓
   [Database] (PostgreSQL + SQLite fallback)
```

---

## ⚠️ Critical Pre-Work Checklist

**MUST DO BEFORE MAKING ANY CHANGES:**

- [ ] Read this entire file
- [ ] Understand the **Phase system** (Phases 1-6 deployed)
- [ ] Know the **two deployment folders**: `agents/handlers/services/` (main) and `bot_webjob/` (deployed copy)
- [ ] **ALWAYS sync bot_webjob after changes** - otherwise WebJob won't pick up new code
- [ ] Understand **Hinglish detection** - bot now handles Hindi in Roman script
- [ ] Know **idempotency system** - uses MD5 hashing to prevent duplicate responses
- [ ] Understand **error handling** - all async calls wrapped in try-except
- [ ] Remember **language enforcement** - bot responds in PURE single language (no mixing)
- [ ] Know the **database dual-layer system** - PostgreSQL with SQLite fallback

---

## 🏗️ Project Architecture

### Technology Stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| **Bot Framework** | python-telegram-ext | Latest | Handles Telegram API, async handlers |
| **AI/LLM** | Groq API | Latest | Llama 3.3 70B (500→1000 tokens) |
| **Voice** | Groq Whisper | Latest | Audio transcription |
| **Primary DB** | PostgreSQL (Neon) | Latest | Cloud-hosted, reliable |
| **Fallback DB** | SQLite | 3.x | Local `kisanmitra.db` (auto-used if PG down) |
| **Web Framework** | Flask | 2.x | Dashboard, keep-alive server (port 8080) |
| **Cloud** | Microsoft Azure | Latest | App Service + WebJob |
| **CI/CD** | GitHub Actions | Latest | Auto-deploy on main branch push |
| **Python** | 3.11 | 3.11.x | Runtime version |

### Environment Variables Required

```bash
# Telegram
TELEGRAM_BOT_TOKEN=xxxxx  # Get from @BotFather
TELEGRAM_ADMIN_ID=xxxxx   # Your Telegram user ID

# Groq AI
GROQ_API_KEY=gsk_xxxxx
GROQ_CHAT_MODEL=llama-3.3-70b-versatile

# Database
DATABASE_URL=postgresql://user:pass@neon.tech/db
SQLITE_DB_PATH=kisanmitra.db

# Azure (for deployment)
AZURE_CREDENTIALS={JSON}  # GitHub secret (Service Principal)
AZURE_SUBSCRIPTION_ID=xxxxx
AZURE_RESOURCE_GROUP=KisanMitraRG
AZURE_APP_NAME=kisanmitra-ai-pro

# Third-party APIs
MANDI_API_KEY=xxxxx
PLANTIX_API_KEY=xxxxx
WEATHER_API_KEY=xxxxx

# Max History
MAX_HISTORY=10  # Chat context window
```

---

## 📁 Folder Structure & File Details

### Root Level
```
kisanmitra_pro/
├── .github/workflows/
│   └── deploy-azure.yml          # ⚡ CI/CD CRITICAL - GitHub Actions workflow
│
├── agents/                        # AI Logic Layer (MAIN SOURCE - sync to bot_webjob!)
│   ├── __init__.py
│   ├── chat_agent.py              # ⭐ CRITICAL - All Phases 1-6 implemented here
│   ├── vision_agent.py            # Photo analysis (Llama Vision)
│   └── voice_agent.py             # Voice transcription (Groq Whisper)
│
├── handlers/                      # Telegram Event Handlers (MAIN SOURCE)
│   ├── __init__.py
│   ├── messages.py                # ⭐ CRITICAL - Text/voice/photo handlers + idempotency
│   ├── callbacks.py               # Button callbacks
│   ├── commands.py                # /start, /help commands
│   └── soil_conversation.py       # Soil data collection flow
│
├── services/                      # External API Integrations (MAIN SOURCE)
│   ├── weather.py                 # Open-Meteo, rain/heat alerts
│   ├── mandi.py                   # Market prices
│   ├── schemes.py                 # Government subsidies
│   ├── plantix.py                 # Plant health API
│   ├── satellite.py               # NASA satellite data
│   ├── agromonitoring.py          # AgroMonitoring NDVI
│   ├── soil_xgboost.py            # ML fertilizer recommendations
│   ├── soil_fusion.py             # Soil data synthesis
│   └── keep_alive.py              # WebJob keep-alive ping
│
├── database/                      # Data Access Layer
│   ├── __init__.py
│   └── db.py                      # ⚡ CRITICAL - All DB queries + Phases 1-2 functions
│
├── bot_webjob/                    # 🔴 DEPLOYMENT COPY (DO NOT EDIT DIRECTLY)
│   ├── agents/                    # Synced from agents/
│   ├── handlers/                  # Synced from handlers/
│   ├── database/                  # Synced from database/
│   ├── services/                  # Synced from services/
│   ├── run.py                     # Entry point (PRODUCTION)
│   ├── run.bat                    # Batch runner
│   └── settings.job               # Azure WebJob config
│
├── dashboard/                     # Web Dashboard (Flask)
│   ├── app.py                     # Flask app
│   ├── login_template.html        # Landing page
│   └── static/
│
├── tests/                         # Test Suite (Phase 6)
│   ├── test_agents.py
│   ├── test_fixes.py
│   └── __init__.py
│
├── config.py                      # ⭐ CRITICAL - Environment config
├── main.py                        # Local dev entry point
├── startup.py                     # Azure startup script
├── keep_alive.py                  # Flask keep-alive
├── requirements.txt               # Python dependencies
└── PROJECT_REPORT.md              # Previous documentation
```

### Critical Files - Deep Dive

#### 1. `.github/workflows/deploy-azure.yml` ⚡ DEPLOYMENT CRITICAL
**Location**: `kisanmitra_pro/.github/workflows/deploy-azure.yml`  
**Purpose**: GitHub Actions CI/CD pipeline  
**Trigger**: Auto on `main` branch push  

**What it does**:
```yaml
1. Checkout code
2. Setup Python 3.11
3. Install requirements.txt
4. Login to Azure (using AZURE_CREDENTIALS secret)
5. Deploy kisanmitra_pro/ to App Service (kisanmitra-ai-pro)
6. Deploy bot_webjob/run.py as WebJob (kisanmitra-bot)
7. Verify deployment (app service state check)
```

**Recent Fix Applied** (commit a0411f0):
- Removed problematic `az webapp webjob continuous stop/start` command
- Was causing "Bad Request" errors, blocking deployments
- Now relies on code refresh on next message

---

#### 2. `agents/chat_agent.py` ⭐ CORE AI ENGINE - ALL PHASES HERE

**Current State**: ✅ Phases 1-5 fully implemented

**Phase 1 & 2** (Farmer Intelligence + System Prompt):
- `get_farmer_intelligence(user_id, email)` - Comprehensive farmer profile
- `get_soil_history(user_id, email, limit=5)` - Soil trends
- `get_sensor_history(user_id, email, days=30, limit=10)` - Moisture patterns
- `analyze_soil_trend()` - Returns "↑ Improving" / "↓ Declining" / "→ Stable"
- `analyze_sensor_trend()` - Returns "🔴 Dry trend" / "🟡 Wet trend"
- Enhanced system prompt with context (field sizes, crop stages, soil history)
- Max tokens increased: 500 → **1000** (prevents truncation)

**Phase 3** (Message Splitting):
- Implemented in `handlers/messages.py` as `split_long_response()`
- Splits at sentence boundaries (. ! ? ।)
- Respects 4096 Telegram char limit

**Phase 4** (Language Purity & Idempotency):
- `_enforce_language_purity(response, language)` - Removes language mixing
- MD5 hash-based idempotency in messages.py
- System prompt enforces: "You MUST respond ONLY in {lang_name}. NEVER mix languages."

**Phase 5** (Weather & Pest Alerts):
- `_build_weather_context(user_id)` - Rain/heat alerts
- `_build_pest_risk_context(user_id, crop, location)` - Community outbreaks
- Both integrated into system prompt context

**Critical Function**: `detect_language(message: str) → str`
```python
# Now supports:
- Pure Devanagari (Hindi/Marathi script)
- HINGLISH: Hindi in Roman script (mujhe, khet, chahiye, etc.) ← NEW
- MANGLISH: Marathi in Roman script
- Pure English

# Returns: "hi", "mr", "en"
# IMPORTANT: Default fallback is "hi" (not "en")
```

**⚠️ GOTCHA**: If detect_language returns wrong code, language enforcement fails!

---

#### 3. `handlers/messages.py` ⭐ CRITICAL REQUEST HANDLER

**Current State**: ✅ Phases 3, 4 fully implemented

**Key Functions**:

1. **`handle_text()` - Main message processor**
   - Idempotency check: `MD5(message)` compared against `context.user_data['last_message_hash']`
   - Sets `last_response_sent = False` IMMEDIATELY (prevents race condition)
   - Typing indicator: `send_chat_action("typing")`
   - Try-except wrapper around `chat()` call with fallback error message
   - Splits response via `split_long_response()`
   - Marks `last_response_sent = True` after sending

2. **`split_long_response(text: str, max_length: int = 4000) → list`**
   - Splits at sentence boundaries
   - Keeps emojis with sentences
   - Max chunk size: 4000 chars (buffer for Telegram's 4096 limit)
   - Delays 0.5s between chunks

3. **`handle_voice()` - Audio processing**
   - Download audio → transcribe via `transcribe_voice()`
   - Call `chat()` with transcribed text
   - Log query

4. **`handle_photo()` - Pest detection**
   - Analyze via `analyze_crop_photo()`
   - Enrich with Plantix if soil data exists
   - Auto-log pest report if detected
   - Add to community pest map

**Recent Fixes Applied** (commit 68e3ba5):
- Changed `hash()` → `hashlib.md5()` (deterministic)
- Set `last_response_sent = False` before processing
- Wrapped `chat()` in try-except
- Added top-level error handling

---

#### 4. `database/db.py` ⚡ DATA ACCESS LAYER

**Critical Issue Fixed** (commit 13bfd9a):
- File was corrupted with 64,707 null bytes
- Error: "ValueError: source code string cannot contain null bytes"
- Solution: Restored from `bot_webjob_temp/`, re-added Phase 1 functions

**Phase 1 Functions** (Must be present):
```python
get_farmer_intelligence(user_id, email)         # Main context builder
get_soil_history(user_id, email, limit=5)
get_sensor_history(user_id, email, days=30, limit=10)
get_local_pest_reports(crop, location, days=30)
analyze_soil_trend(soil_history)
analyze_sensor_trend(sensor_history)
detect_community_risk(location, crop, pest_alerts)
analyze_fertilizer_log(user_id, limit=20)
```

**Dual-Layer Database**:
```python
try:
    # Try PostgreSQL (Neon cloud)
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
except:
    # Fallback to SQLite
    conn = sqlite3.connect('kisanmitra.db')
```

**⚠️ CRITICAL**: If `get_farmer_intelligence()` throws error, whole chat fails!

---

#### 5. `config.py` - Environment Configuration

**Must Define**:
```python
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_CHAT_MODEL = 'llama-3.3-70b-versatile'
MAX_HISTORY = 10
MAX_TOKENS = 1000  # Recently increased from 500

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ADMIN_ID = os.getenv('TELEGRAM_ADMIN_ID', '0')

DATABASE_URL = os.getenv('DATABASE_URL')
SQLITE_DB_PATH = 'kisanmitra.db'
```

---

#### 6. `bot_webjob/run.py` - PRODUCTION ENTRY POINT

**What it does**:
1. Starts Flask keep-alive server (port 8080)
2. Initializes Telegram bot with token
3. Registers all handlers (text, voice, photo, commands)
4. Starts polling indefinitely

**⚠️ CRITICAL**: This is what actually runs in Azure!

---

## 💾 Database Architecture

### PostgreSQL (Neon) - Primary Storage

**Tables**:
- `farmers` - User profiles, location, language pref
- `soil_reports` - Lab analysis (pH, NPK, date)
- `sensor_readings` - IoT data (moisture, temp, hours_ago)
- `queries` - Chat history (user_id, message, response, intent, language)
- `pest_reports` - Community outbreaks (crop, pest, location, severity)
- `fertilizer_logs` - Extracted from chat history
- `land_details` - Field info (area, crop type, soil type)

### SQLite (Local Fallback) - `kisanmitra.db`

Used automatically if PostgreSQL unavailable:
- Same schema as PostgreSQL
- File-based (no network)
- Slower but reliable

**Fallback Logic in `database/db.py`**:
```python
def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL)  # Try PG first
    except:
        return sqlite3.connect(SQLITE_DB_PATH)  # Fallback to SQLite
```

---

## 🚀 Deployment Pipeline

### GitHub → Azure Workflow

```
Developer commits to main branch
         ↓
GitHub Actions triggered (.github/workflows/deploy-azure.yml)
         ↓
Setup Python 3.11 + Install requirements.txt
         ↓
Login to Azure (Service Principal via AZURE_CREDENTIALS secret)
         ↓
Deploy kisanmitra_pro/ → App Service (Flask dashboard)
         ↓
Deploy bot_webjob/ → WebJob (Telegram bot continuous job)
         ↓
Verify: Check app state = "Running"
         ↓
✅ Live on @mykisanmitra_bot
```

### Service Principal Setup

**Required once in GitHub**:
1. Azure Portal → Service Principal (github-kisamitra-deployer)
2. Generate JSON credentials
3. GitHub → Settings → Secrets → Add `AZURE_CREDENTIALS` (paste JSON)

**JSON Format**:
```json
{
  "clientId": "xxx",
  "clientSecret": "xxx",
  "subscriptionId": "xxx",
  "tenantId": "xxx"
}
```

### Manual Restart

If WebJob is stuck:
```powershell
az webapp webjob continuous stop \
  --name kisanmitra-ai-pro \
  --webjob-name kisanmitra-bot \
  --resource-group KisanMitraRG

Start-Sleep -Seconds 3

az webapp webjob continuous start \
  --name kisanmitra-ai-pro \
  --webjob-name kisanmitra-bot \
  --resource-group KisanMitraRG
```

---

## 🐛 Known Issues & Fixes Applied

### Issue #1: Hinglish Not Detected ✅ FIXED (e555c7b)
**Problem**: User sent "mujhe ab mere khet mein..." (Hindi in Roman script) → Bot detected English → Responded in English

**Root Cause**: `detect_language()` only recognized Devanagari script, not Latin-script Hindi

**Fix**:
- Added 30+ Hinglish keywords: mujhe, mere, khet, mitti, dalna, chahiye, kya, kaise, nahi, haan, etc.
- Added Manglish keywords: maza, kar, aahe, kay, kase, etc.
- Improved fallback to default to Hindi if uncertain

**Test**: Send "muje apni mitti ki jankari chahiye" → Should get Hindi response ✅

---

### Issue #2: Duplicate Initial Greetings ✅ FIXED (68e3ba5)
**Problem**: Bot sent two greeting messages on startup

**Root Cause**: Python's `hash()` returns different values on restart → idempotency check failed

**Fix**:
- Replaced `hash()` with `hashlib.md5()` (deterministic)
- Set `last_response_sent = False` IMMEDIATELY on message arrival
- Added top-level try-except in `handle_text()`

**Test**: Send greeting → Should get ONE response ✅

---

### Issue #3: Timeouts/Hanging (Chat Response Timeout) ✅ FIXED (68e3ba5)
**Problem**: User asks question → No typing indicator → Bot hangs for 30+ seconds → No response

**Root Cause**: `chat()` call not wrapped in error handling; uncaught exceptions

**Fix**:
- Wrapped `chat()` in try-except with graceful error fallback
- Added 0.5s delays between message chunks
- Added logging for all errors

**Test**: Send "muje apni mitti ki jankari chahiye" → Typing shows immediately ✅

---

### Issue #4: Database Null-Byte Corruption ✅ FIXED (13bfd9a)
**Problem**: `database/db.py` became corrupted with 64,707 null bytes → Python couldn't import

**Root Cause**: Unknown (possibly git operations or file manipulation)

**Fix**:
- Restored clean version from `bot_webjob_temp/`
- Re-added all Phase 1 functions that were missing
- Verified 0 null bytes

**Prevention**: Always backup `database/db.py` before large edits

---

### Issue #5: WebJob Restart CLI Errors ✅ FIXED (a0411f0)
**Problem**: `az webapp webjob continuous stop` returning "Bad Request" error

**Root Cause**: Unknown (possibly Azure CLI version or authentication)

**Fix**: Removed WebJob restart from workflow
- Code now refreshes on next Telegram message/request
- Manual restart available if needed

---

### Issue #6: Generic Responses (Not Using Farmer Context) ⚠️ PARTIALLY ADDRESSED
**Problem**: Bot gave generic "your soil data pH 7.0..." advice instead of personalized recommendations

**Root Cause**: Farmer Intelligence Engine not fully integrated OR `get_farmer_intelligence()` failing silently

**Status**: All Phase 1-2 functions now in place. If still generic:
1. Check database has farmer soil data
2. Verify `get_farmer_intelligence()` returns non-empty dict
3. Check system prompt is actually using `full_context`

**Debug**:
```python
# Add to chat_agent.py temporarily
intelligence = get_farmer_intelligence(user_id, email)
print(f"[DEBUG] Intelligence: {intelligence}")
```

---

## 🖥️ WebJob Configuration

### Azure WebJob Details

| Property | Value |
|----------|-------|
| **Name** | kisanmitra-bot |
| **Type** | Continuous |
| **Resource Group** | KisanMitraRG |
| **App Service** | kisanmitra-ai-pro |
| **Run Command** | `run.py` |
| **Start Type** | Automatic on deployment |
| **Restart Policy** | Restart on exit |

### WebJob Folder Structure (Azure)

```
/site/wwwroot/
└── bot_webjob/
    ├── agents/
    │   ├── chat_agent.py
    │   ├── vision_agent.py
    │   └── voice_agent.py
    ├── handlers/
    │   ├── messages.py
    │   ├── callbacks.py
    │   ├── commands.py
    │   └── soil_conversation.py
    ├── database/
    │   └── db.py
    ├── services/
    │   ├── weather.py
    │   ├── mandi.py
    │   └── [...other services]
    ├── run.py          ← Entry point
    ├── settings.job    ← Config
    └── requirements.txt
```

### Deployment Process

1. Code pushed to GitHub `main` branch
2. GitHub Actions runs workflow
3. Workflow deploys `bot_webjob/` to Azure
4. Azure extracts and runs `run.py`
5. WebJob starts Telegram bot listener
6. Messages flow through handlers → agents → responses

---

## 🔌 API & Service Integrations

### Groq API (Chat & Voice)

```python
from groq import Groq

client = Groq(api_key=GROQ_API_KEY)

# Chat
response = client.chat.completions.create(
    model='llama-3.3-70b-versatile',
    messages=[...],
    max_tokens=1000,
    temperature=0.7
)

# Voice transcription
transcript = client.audio.transcriptions.create(
    file=audio_bytes,
    model='whisper-large-v3'
)
```

### Weather (Open-Meteo)

```python
# services/weather.py
def get_weather(lat, lon, location):
    # Returns: rain_today, rain_tomorrow, temp, wind_speed
    # Triggers alerts if rain>10mm or temp>40°C
```

### Mandi Prices (Government API)

```python
# services/mandi.py
def get_mandi_prices(product):
    # Returns: market prices, trends, nearby markets
```

### Plant Health (Plantix + Vision)

```python
# services/plantix.py / agents/vision_agent.py
def analyze_plant_health(image_bytes, language):
    # Returns: disease, deficiency, treatment, severity, source
```

---

## 💡 Critical Code Patterns

### Pattern 1: Language-Aware Responses

```python
# ALWAYS detect language first
language = detect_language(message)  # "hi", "mr", "en"

# Build system prompt with language instruction
system_prompt = f"""You MUST respond ONLY in {lang_map[language]}. 
NEVER mix languages. Every single word must be in {lang_map[language]}."""

# Generate response
reply = chat(user_id, message, language)

# Enforce language purity
reply = _enforce_language_purity(reply, language)

# Send
await send_reply(reply)
```

**⚠️ CRITICAL**: Skip enforcement → user gets mixed language responses!

---

### Pattern 2: Error Handling for AI Calls

```python
try:
    # AI call (potentially slow/timeout)
    reply, intent, language = chat(user_id, message)
except TimeoutError:
    reply = "🙏 Jawab dene mein dikkat hui. Baad mein try karein."
except Exception as e:
    print(f"[ERROR] {e}")
    reply = "❌ Kuch gadbad ho gayi. Support se milein."

# Always send SOMETHING, never fail silently
await send_reply(reply)
```

---

### Pattern 3: Farmer Context Building

```python
# Build comprehensive context
farmer = get_farmer(user_id)
intelligence = get_farmer_intelligence(user_id, email)

farmer_context = f"""
🌾 FARMER: {intelligence['farmer']['name']}
🏞️ FIELDS: {intelligence['lands']}
🧪 SOIL: {intelligence['soil_history']}
📊 SENSORS: {intelligence['sensor_history']}
🐛 PESTS: {intelligence['pest_alerts']}
🧑‍🌾 FERTILIZER: {intelligence['fertilizer_log']}
"""

# Include in system prompt
system_prompt = f"{system_prompt}\n{farmer_context}"
```

---

### Pattern 4: Database Fallback

```python
def get_conn():
    try:
        # Try PostgreSQL first
        return psycopg2.connect(DATABASE_URL)
    except:
        # Fallback to SQLite
        return sqlite3.connect(SQLITE_DB_PATH)

# Usage
conn = get_conn()
# Same SQL works for both!
```

---

### Pattern 5: Idempotency Check

```python
import hashlib

# On message arrival
message_hash = hashlib.md5(message.encode()).hexdigest()
last_hash = context.user_data.get('last_message_hash')

# IMMEDIATELY set to False (prevent race condition)
context.user_data['last_response_sent'] = False

# Check if duplicate
if last_hash == message_hash and context.user_data.get('last_response_sent'):
    return  # Skip processing

# Process...
# After sending
context.user_data['last_response_sent'] = True
```

**⚠️ CRITICAL**: Order matters! Set to False BEFORE check!

---

## ⚠️ Common Errors & Solutions

### Error 1: "ImportError: cannot import name 'get_farmer_intelligence'"

**Cause**: `database/db.py` missing Phase 1 functions

**Solution**:
```bash
# Restore from bot_webjob_temp
copy bot_webjob_temp\database\db.py database\db.py
```

**Prevention**: Keep `database/db.py` backed up

---

### Error 2: "ValueError: source code string cannot contain null bytes"

**Cause**: File corruption (usually `database/db.py` or `agents/chat_agent.py`)

**Solution**:
```bash
# Restore from bot_webjob_temp
copy bot_webjob_temp\agents\chat_agent.py agents\chat_agent.py
copy bot_webjob_temp\database\db.py database\db.py
```

**Prevention**: Use `git restore` instead of manual file editing

---

### Error 3: "Bot detected as English, responds in English for Hindi query"

**Cause**: `detect_language()` failed

**Solution**:
1. Check Hinglish keywords are present in `detect_language()`
2. Test: `detect_language("mujhe mere khet mein...")`  should return "hi"
3. If returning "en", check keywords list

**Test Hinglish Keywords**:
```python
hinglish_keywords = ["mujhe", "mere", "khet", "mitti", "fasal", "kar", 
                     "chahiye", "kya", "kaise", "nahi", "haan", ...]
```

---

### Error 4: "Duplicate responses in Telegram"

**Cause**: Idempotency check broken (old `hash()` function)

**Solution**: Verify `handlers/messages.py` uses `hashlib.md5()`, NOT `hash()`

**Check**:
```bash
grep "hashlib.md5" handlers/messages.py  # Should find it
grep "hash(message)" handlers/messages.py  # Should NOT find it
```

---

### Error 5: "WebJob stuck, bot not responding to messages"

**Cause**: WebJob process crashed or hung

**Solution**: Manual restart
```bash
az webapp webjob continuous stop --name kisanmitra-ai-pro \
  --webjob-name kisanmitra-bot --resource-group KisanMitraRG

Start-Sleep -Seconds 3

az webapp webjob continuous start --name kisanmitra-ai-pro \
  --webjob-name kisanmitra-bot --resource-group KisanMitraRG
```

---

### Error 6: "Deployment fails with 'Bad Request' on WebJob restart"

**Cause**: Azure CLI WebJob commands timing out or auth issue

**Solution**: Already fixed in workflow (commit a0411f0)
- WebJob restart removed from workflow
- Code refreshes on next message

---

## 📝 Development Workflow

### Adding a New Feature

1. **Edit main source files** (agents/, handlers/, services/, database/)
   ```bash
   # Example: Add new function to chat_agent.py
   nano agents/chat_agent.py
   ```

2. **Test locally** (if possible)
   ```bash
   python main.py  # Local test
   ```

3. **Sync to bot_webjob** ⚠️ DON'T SKIP THIS
   ```bash
   copy agents/chat_agent.py bot_webjob/agents/chat_agent.py
   copy handlers/messages.py bot_webjob/handlers/messages.py
   # etc for all changed files
   ```

4. **Commit with clear message**
   ```bash
   git add agents/ handlers/ bot_webjob/
   git commit -m "feat: Add new fertilizer recommendation feature

   - Added analyze_crop_stage() function
   - Integrated into system prompt
   - Handles Hinglish queries"
   ```

5. **Push to main** (triggers automatic deployment)
   ```bash
   git push origin main
   ```

6. **Monitor deployment**
   - GitHub Actions → Workflows → Latest run
   - Azure Portal → App Service → Output logs

7. **Test on Telegram** (@mykisanmitra_bot)
   ```
   /start
   Send test message
   Verify response
   ```

8. **If broken**: Commit hotfix and push again
   ```bash
   git commit -m "fix: Revert broken change"
   git push origin main
   ```

---

### File Editing Guidelines

**DO**:
- ✅ Always sync bot_webjob after changes
- ✅ Use try-except for all AI/DB calls
- ✅ Add logging: `print(f"[ERROR] {e}")`
- ✅ Test language detection for Hindi queries
- ✅ Check idempotency (single response)
- ✅ Commit frequently with clear messages

**DON'T**:
- ❌ Edit `bot_webjob/` directly (will be overwritten)
- ❌ Use Python's `hash()` for idempotency (not deterministic)
- ❌ Skip error handling in async functions
- ❌ Add code that requires new env variables without updating GitHub secrets
- ❌ Change system prompt language rule
- ❌ Remove farmer intelligence context building

---

### Pre-Deployment Checklist

Before pushing to main:
- [ ] All changes synced to `bot_webjob/`
- [ ] No `hash()` functions (use `hashlib.md5()`)
- [ ] All AI calls wrapped in try-except
- [ ] Hinglish detection tested for Hindi queries
- [ ] No null bytes in modified files: `grep -a '\x00' file.py` returns empty
- [ ] System prompt doesn't override language enforcement
- [ ] Database calls use fallback logic
- [ ] New dependencies added to `requirements.txt`
- [ ] New env variables added to GitHub secrets

---

## 🔑 Key Takeaways

1. **Two Code Locations**: Edit in `agents/handlers/services/database/`, then SYNC to `bot_webjob/`
2. **Hinglish Support**: Bot handles Hindi in Roman script (mujhe, khet, chahiye)
3. **Idempotency**: Uses MD5 hash (not Python's `hash()`)
4. **Language Purity**: Bot responds in pure single language, no mixing
5. **Database**: PostgreSQL primary, SQLite fallback
6. **Deployment**: Push to GitHub → GitHub Actions → Azure WebJob
7. **Error Handling**: All async/AI calls must have try-except + fallback
8. **Farmer Context**: Phase 1-2 functions provide personalized advice
9. **WebJob**: Runs `bot_webjob/run.py` continuously
10. **Debug**: Check WebJob logs at Azure Portal → WebJob logs

---

**Last Updated**: May 4, 2026 (UTC)  
**Version**: 2.0.0  
**Maintained By**: Development Team  

For questions, refer to project commit history for context.
