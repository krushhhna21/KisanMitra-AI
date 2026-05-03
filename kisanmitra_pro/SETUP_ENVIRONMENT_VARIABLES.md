# 🔧 Configure KisanMitra Bot - Environment Variables Setup

## Problem

Bot stopped responding because required environment variables are missing:
- ❌ `GROQ_API_KEY`
- ❌ `TELEGRAM_BOT_TOKEN`

The `validate_config()` function prevents the bot from starting without these credentials.

---

## Solution: Set Environment Variables in Azure

### Step 1: Go to Azure Portal

Navigate to: https://portal.azure.com

### Step 2: Open Your App Service

1. Search for **kisanmitra-ai-pro**
2. Click on it to open the App Service blade

### Step 3: Open Configuration Settings

1. In the left sidebar, click **Settings → Configuration**
2. Click the **Application Settings** tab
3. Click **+ New application setting**

### Step 4: Add Required Environment Variables

Add each of these settings by clicking "+ New application setting":

| Setting Name | Value | Example |
|---|---|---|
| **GROQ_API_KEY** | Your Groq API key | `gsk_...your-key...` |
| **TELEGRAM_BOT_TOKEN** | Your Telegram Bot token | `123456:ABC...` |

### Step 5: Save Configuration

1. Click the **Save** button at the top
2. Azure will confirm the save
3. The app will **automatically restart** with new settings

### Step 6: Verify Bot is Running

After ~1-2 minutes, test the bot:
1. Send `/start` to your Telegram bot
2. Bot should respond with a welcome message
3. Check Azure logs: **Monitoring → Logs** for any errors

---

## How to Get Your API Keys

### Groq API Key
1. Go to: https://console.groq.com
2. Sign up / Sign in
3. Navigate to API Keys
4. Create or copy your API key
5. Paste it in Azure Configuration

### Telegram Bot Token
1. Go to Telegram and find **@BotFather**
2. Send `/start` command
3. Send `/newbot` to create a new bot (or `/mybots` to get existing token)
4. Follow instructions to get your bot token
5. Paste it in Azure Configuration

---

## Alternative: Azure CLI Method

If you prefer command line:

```bash
# Set GROQ_API_KEY
az webapp config appsettings set --name kisanmitra-ai-pro \
  --resource-group KisanMitraRG \
  --settings GROQ_API_KEY="your-groq-key-here"

# Set TELEGRAM_BOT_TOKEN
az webapp config appsettings set --name kisanmitra-ai-pro \
  --resource-group KisanMitraRG \
  --settings TELEGRAM_BOT_TOKEN="your-telegram-token-here"
```

---

## For Local Testing

### Option 1: Create .env file

In project root directory, create `.env`:
```
GROQ_API_KEY=your-groq-key-here
TELEGRAM_BOT_TOKEN=your-telegram-token-here
DATABASE_URL=sqlite:///kisanmitra.db
```

Then run:
```bash
python main.py
```

### Option 2: Set Environment Variables

PowerShell:
```powershell
$env:GROQ_API_KEY = "your-groq-key-here"
$env:TELEGRAM_BOT_TOKEN = "your-telegram-token-here"
python main.py
```

Bash:
```bash
export GROQ_API_KEY="your-groq-key-here"
export TELEGRAM_BOT_TOKEN="your-telegram-token-here"
python main.py
```

---

## Troubleshooting

### Bot still not responding after configuration?

1. **Check if app restarted**
   - Azure Portal → kisanmitra-ai-pro → Overview
   - Look at "Status" - should be "Running"
   - If not running, click "Restart"

2. **Check application logs**
   - Go to: **Monitoring → Logs**
   - Search for: "Configuration validated successfully"
   - Should show bot startup messages

3. **Common errors:**
   - `[FATAL] Missing required environment variables` = Settings not saved or applied
   - `Groq authentication error` = GROQ_API_KEY is invalid
   - `Telegram connection error` = TELEGRAM_BOT_TOKEN is invalid

4. **Restart the app**
   - Azure Portal → kisanmitra-ai-pro → Restart button

---

## Verification Checklist

After setting environment variables:

- [ ] Azure Configuration shows both GROQ_API_KEY and TELEGRAM_BOT_TOKEN
- [ ] App Service status is "Running"
- [ ] No errors in Application logs
- [ ] Send `/start` to bot on Telegram
- [ ] Bot responds within 5 seconds
- [ ] Bot sends welcome message in correct language

---

## What These Keys Do

### GROQ_API_KEY
- Powers all AI responses (chat, vision, voice)
- Required for bot to understand and respond to farmer queries
- Free tier available: https://console.groq.com

### TELEGRAM_BOT_TOKEN
- Authenticates bot with Telegram servers
- Allows bot to receive messages from farmers
- Required to connect bot to Telegram app
- Get from @BotFather on Telegram

---

## Optional: Add More Settings

While you're configuring, consider adding:

```
DATABASE_URL           PostgreSQL connection (if using Neon)
MANDI_API_KEY          For government market prices
AGROMONITORING_API_KEY For soil monitoring
PLANTIX_API_KEY        For crop disease detection
```

---

## Questions?

If bot is still not working after following these steps:

1. Check Azure logs for error messages
2. Verify API keys are valid
3. Ensure app restarted after saving settings
4. Try sending `/help` instead of `/start`
5. Check if bot token belongs to correct bot

---

**Next Step**: Set these environment variables in Azure and restart the app. Bot should respond immediately after.
