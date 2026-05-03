#!/usr/bin/env python
"""
Azure WebJob Entry Point for KisanMitra Telegram Bot
=====================================================
Runs the Telegram bot as a continuous background job on Azure App Service.

Azure deploys this as a WebJob at: https://kisanmitra-ai-pro.scm.azurewebsites.net/api/continuouswebjobs

To deploy:
  az webapp webjob continuous create --name kisanmitra-ai-pro \
    --resource-group KisanMitraRG --webjob-name kisanmitra-bot \
    --webjob-type python
"""

import sys
import os

# Add parent directory to path to import kisanmitra modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    print("[WebJob] Starting KisanMitra Telegram Bot on Azure App Service...", flush=True)
    
    # Import and run main bot application
    from main import main
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        print("[WebJob] Bot stopped by user", flush=True)
    except Exception as e:
        print(f"[WebJob] Bot crashed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
