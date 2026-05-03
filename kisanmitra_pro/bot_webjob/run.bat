@echo off
REM WebJob entry point for KisanMitra bot
cd /d "%~dp0"
echo Starting KisanMitra Bot >> webjob.log
python -m pip install -q -r requirements.txt >> webjob.log 2>&1
python main.py
