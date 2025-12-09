# Azure App Service Deployment Setup

## Files Created/Modified

### Created Files:
1. **`requirements.txt`** (at repo root) - Copy of dependencies for Oryx detection
2. **`runtime.txt`** (at repo root) - Specifies Python 3.10
3. **`manage.py`** (at repo root) - Wrapper to handle subdirectory structure
4. **`.deployment`** (in django-postgres-backend/) - Ensures build runs during deployment
5. **`startup.sh`** (in django-postgres-backend/) - Startup script (optional, if needed)
6. **`AZURE_DEPLOYMENT_SETUP.md`** - This file

### Modified Files:
1. **`.github/workflows/azure-webapp-backend.yml`** - Updated for Python 3.10, app name "Pharma", and correct secret name

## Azure Portal Configuration Required

### 1. Startup Command
In Azure Portal → App Service "Pharma" → Configuration → General settings → Startup Command, set:

```
gunicorn pharmacy_backend.wsgi --bind=0.0.0.0 --timeout 600
```

### 2. Environment Variables
In Azure Portal → App Service "Pharma" → Configuration → Application settings, configure:

- `DJANGO_SETTINGS_MODULE` = `pharmacy_backend.settings`
- `SECRET_KEY` = (your Django secret key)
- `DEBUG` = `false` (for production)
- `ALLOWED_HOSTS` = `pharma.azurewebsites.net,your-domain.com` (comma-separated)
- `DATABASE_URL` = (your Azure PostgreSQL connection string)

### 3. Python Version
Ensure Python 3.10 is selected in:
Azure Portal → App Service "Pharma" → Configuration → General settings → Stack settings → Python version

## How This Fixes the ModuleNotFoundError

1. **`.deployment` file**: Ensures `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, which tells Azure to run `pip install -r requirements.txt` during deployment.

2. **`requirements.txt` at deployment root**: When GitHub Actions deploys the `django-postgres-backend` directory, Azure receives it with `requirements.txt` at the root, which Oryx can detect and use to install dependencies.

3. **`runtime.txt`**: Specifies Python 3.10, ensuring Azure uses the correct Python version.

4. **Startup command**: The gunicorn command must be set in Azure Portal to run from the deployment root where `pharmacy_backend/wsgi.py` is located.

## Deployment Structure

When deployed, Azure receives:
```
/home/site/wwwroot/
  manage.py
  requirements.txt
  pharmacy_backend/
    settings.py
    wsgi.py
    urls.py
  apps/
  core/
  ...
```

Oryx detects:
- `requirements.txt` → Installs Python dependencies
- `manage.py` → Detects Django app
- `pharmacy_backend/wsgi.py` → WSGI application

## GitHub Actions Secret

Ensure this secret is configured in GitHub:
- `AZUREAPPSERVICE_PUBLISHPROFILE_PHARMA` - Download the publish profile from Azure Portal → App Service "Pharma" → Get publish profile

