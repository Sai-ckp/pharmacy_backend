#!/bin/bash
# Azure App Service startup script for Django
# This ensures dependencies are installed and the app starts correctly

cd /home/site/wwwroot

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# Start Gunicorn
gunicorn pharmacy_backend.wsgi --bind=0.0.0.0 --timeout 600

