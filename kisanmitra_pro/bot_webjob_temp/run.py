#!/usr/bin/env python
import subprocess
import sys
import os

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Install requirements
print("Installing dependencies...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=False)

# Run main bot
print("Starting KisanMitra Bot...")
sys.exit(subprocess.call([sys.executable, "main.py"]))
