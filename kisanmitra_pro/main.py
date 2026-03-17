"""
🌾 KisanMitra AI v2.0
Har khet ka saathi — Every farm's companion

Run:       python main.py
Dashboard: python dashboard/app.py
Tests:     python -m pytest tests/ -v
"""
import asyncio
from keep_alive import keep_alive
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
from telegram.request import HTTPXRequest
from groq import Groq

from config import TELEGRAM_BOT_TOKEN, GROQ_API_KEY, GROQ_CHAT_MODEL, MORNING_ALERT_HOUR, VERSION
from database.db import init_db, get_alert_users, get_analytics
from services.weather import get_weather
from services.schemes import get_crop_calendar
from handlers.commands import (
    start, help_cmd, weather_cmd, calendar_cmd,
    mandi_cmd, schemes_cmd, satellite_cmd, alerts_cmd, setlocation_cmd,
    myfield_cmd, linkemail_cmd
)
from handlers.messages import handle_text, handle_voice, handle_photo, handle_location
from handlers.callbacks import handle_callback
from handlers.soil_conversation import soil_conversation_handler

groq_client = Groq(api_key=GROQ_API_KEY)


# === DAILY MORNING ALERT ===
async def send_morning_alerts(app):
    print("🌅 Sending morning alerts...")
    users = get_alert_users()
    print(f"   → {len(users)} users to notify")

    for farmer in users:
        try:
            uid = farmer["user_id"]
            w = get_weather(farmer["lat"], farmer["lon"], farmer["location"])

            tip_res = groq_client.chat.completions.create(
                model=GROQ_CHAT_MODEL,
                messages=[{"role": "user", "content": f"""One practical farming tip for today.
Season: March, Rabi harvest, Maharashtra.
Weather: {w['temp']}°C, Rain {w['rain_today']}mm.
2 lines max. Hindi. Start with 🌾."""}],
                max_tokens=80,
                temperature=0.8
            )
            tip = tip_res.choices[0].message.content.strip()

            await app.bot.send_message(
                chat_id=uid,
                text=f"🌅 *Suprabhat, Kisan Bhai!* 🙏\n\n{w['summary']}\n\n💡 *Aaj ka Tip:*\n{tip}\n\n_/help — Koi bhi sawaal poochein_",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"   Alert error for {farmer.get('user_id')}: {e}")

    print(f"✅ Morning alerts sent to {len(users)} farmers")


async def schedule_morning_alerts(app):
    while True:
        now = datetime.now()
        target = now.replace(hour=MORNING_ALERT_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        wait = (target - now).total_seconds()
        print(f"⏰ Next morning alert in {wait/3600:.1f} hours")
        await asyncio.sleep(wait)
        await send_morning_alerts(app)


# === STARTUP BANNER ===
def print_banner():
    stats = get_analytics()
    print(f"""
╔══════════════════════════════════════════════╗
║        🌾 KisanMitra AI v{VERSION}               ║
║     Har khet ka saathi                       ║
╠══════════════════════════════════════════════╣
║  Features:                                   ║
║  ✅ Multi-language (Hindi/Marathi/English)   ║
║  ✅ Voice (Groq Whisper)                     ║
║  ✅ Photo pest detection (Llama 4 Vision)    ║
║  ✅ Live mandi prices (Govt API)             ║
║  ✅ Location-based weather (Open-Meteo)      ║
║  ✅ Satellite crop health (NASA POWER)       ║
║  ✅ Daily 7 AM alerts                        ║
║  ✅ SQLite data pipeline                     ║
║  ✅ Analytics dashboard                      ║
║  ✅ Community pest outbreak map              ║
╠══════════════════════════════════════════════╣
║  Stats: {stats['total_farmers']} farmers | {stats['total_queries']} queries | {stats['total_pest_reports']} reports
╚══════════════════════════════════════════════╝
""")


# === MAIN ===
async def main():
    init_db()
    print_banner()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(
        HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
    ).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("weather", weather_cmd))
    app.add_handler(CommandHandler("calendar", calendar_cmd))
    app.add_handler(CommandHandler("mandi", mandi_cmd))
    app.add_handler(CommandHandler("schemes", schemes_cmd))
    app.add_handler(CommandHandler("satellite", satellite_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("setlocation", setlocation_cmd))
    app.add_handler(CommandHandler("myfield", myfield_cmd))
    app.add_handler(CommandHandler("linkemail", linkemail_cmd))

    # Soil ConversationHandler (must be before generic message handler)
    app.add_handler(soil_conversation_handler)

    # Messages
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Morning alerts
    async def post_init(application):
        asyncio.create_task(schedule_morning_alerts(application))
    app.post_init = post_init

    print("✅ Bot is LIVE! Press Ctrl+C to stop.\n", flush=True)

    # Initialize and start polling natively async
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    keep_alive()   # 🌐 Only start keep-alive when running standalone
    
    # Run the async main func
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
    # Keep the loop running for the polling
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
