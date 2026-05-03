# ⚡ Deploy Telegram Bot on Azure App Service

## Problem Identified

✅ Environment variables are configured correctly
✅ Dashboard (Flask) is running on Azure
❌ **Bot process is NOT running** - This is why bot isn't responding!

---

## Solution: Deploy Bot as WebJob

Azure App Service allows running background processes via **WebJobs**. We need to deploy the bot as a continuous WebJob.

---

## Option 1: Deploy via Azure Portal (Easiest)

### Step 1: Create WebJob Package

In your local project, create a ZIP file:
```bash
# From project root
zip -r KisanMitra-Bot-WebJob.zip bot_webjob/
```

### Step 2: Go to Azure Portal

1. Navigate to: https://portal.azure.com
2. Open: **kisanmitra-ai-pro** App Service
3. Go to: **Development tools → WebJobs** (or search "WebJobs")

### Step 3: Add New WebJob

1. Click **+ Add**
2. Enter Name: `kisanmitra-bot`
3. Upload the ZIP file: `KisanMitra-Bot-WebJob.zip`
4. Type: **Continuous** (keeps running forever)
5. Click **OK**

### Step 4: Monitor

1. WebJob will start automatically
2. Click on it to see logs
3. Should see: `[WebJob] Starting KisanMitra Telegram Bot...`

---

## Option 2: Deploy via Azure CLI

```bash
# Create WebJob
az webapp webjob continuous create \
  --name kisanmitra-ai-pro \
  --resource-group KisanMitraRG \
  --webjob-name kisanmitra-bot \
  --webjob-type python

# Check status
az webapp webjob list \
  --name kisanmitra-ai-pro \
  --resource-group KisanMitraRG

# View logs
az webapp webjob log \
  --name kisanmitra-ai-pro \
  --resource-group KisanMitraRG \
  --webjob-name kisanmitra-bot
```

---

## Option 3: Deploy via GitHub Actions (Automated)

Update `.github/workflows/deploy-azure.yml` to also deploy the WebJob:

```yaml
- name: Deploy Bot WebJob
  uses: azure/webapps-deploy@v2
  with:
    app-name: kisanmitra-ai-pro
    package: bot_webjob/
    clean: true
```

Then commit and push - bot will deploy automatically.

---

## Option 4: Alternative - Modify startup.py to Run Both

Instead of WebJob, run both dashboard and bot in the same process:

```python
# In startup.py
async def run_bot():
    from main import main
    await main()

# Start bot in background thread when app initializes
def start_bot_background():
    import threading
    bot_thread = threading.Thread(target=lambda: asyncio.run(run_bot()), daemon=True)
    bot_thread.start()

# In Flask app startup
@application.before_first_request
def startup():
    start_bot_background()
```

⚠️ **Note**: This is riskier as bot crash could crash the dashboard.

---

## Verification Checklist

After deploying WebJob:

- [ ] Bot WebJob appears in Azure Portal → WebJobs
- [ ] Status shows "Running" (green)
- [ ] WebJob logs show: `[WebJob] Starting KisanMitra Telegram Bot...`
- [ ] No errors in WebJob output logs
- [ ] Send `/start` to bot on Telegram → Should get response within 5 seconds
- [ ] Check Azure Application Insights logs for bot messages

---

## Monitor Bot Status

### From Azure Portal

1. Go to: **kisanmitra-ai-pro** → **WebJobs**
2. Click on **kisanmitra-bot**
3. View real-time logs

### From Azure CLI

```bash
# Get WebJob details
az webapp webjob list --name kisanmitra-ai-pro --resource-group KisanMitraRG

# Get logs
az webapp webjob log --name kisanmitra-ai-pro --resource-group KisanMitraRG \
  --webjob-name kisanmitra-bot --tail 50
```

### From Application Insights

1. Go to: **kisanmitra-ai-pro** → **Monitoring → Logs**
2. Search for: `kisanmitra-bot` or `[WebJob]`
3. View bot activity

---

## Troubleshooting

### WebJob Not Running

1. Check status: `State = Running`
2. Restart: Click "Restart" button in Azure Portal
3. Check logs for errors
4. Verify `GROQ_API_KEY` and `TELEGRAM_BOT_TOKEN` are set

### Bot Still Not Responding

1. Check WebJob is running: Azure Portal → WebJobs → kisanmitra-bot (should be green)
2. Check logs for errors
3. Verify API keys are valid (try manually calling Groq API)
4. Restart WebJob: Click "Restart" button
5. Try `/help` command (sometimes safer than `/start`)

### WebJob Keeps Stopping

1. Check logs for crash messages
2. Could be:
   - Out of memory (upgrade App Service plan)
   - API key invalid
   - Database connection failing
   - Telegram API timeout

### How to Restart Bot

If bot stops responding:

```bash
# Option 1: Azure Portal
1. Go to WebJobs
2. Click kisanmitra-bot
3. Click "Restart"

# Option 2: Azure CLI
az webapp webjob stop --name kisanmitra-ai-pro --resource-group KisanMitraRG --webjob-name kisanmitra-bot
az webapp webjob start --name kisanmitra-ai-pro --resource-group KisanMitraRG --webjob-name kisanmitra-bot
```

---

## Files Created

- `bot_webjob/run.py` - Entry point for WebJob
- `bot_webjob/settings.job` - WebJob configuration

---

## Next Steps

1. **Deploy WebJob**: Use Option 1 (Azure Portal) - easiest
2. **Verify**: Check Azure Portal for running WebJob
3. **Test**: Send `/start` to bot
4. **Monitor**: Watch logs for any issues

---

## Summary

The bot wasn't responding because **it wasn't actually running on Azure**. The WebJob deployment ensures the bot process stays running continuously in the background, separate from the web server (dashboard).

After deploying this, the bot will respond immediately to messages.

---

**Estimated Time to Fix**: 5 minutes  
**Difficulty**: Low (just deploy files to Azure)
