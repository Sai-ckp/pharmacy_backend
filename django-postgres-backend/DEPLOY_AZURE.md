# Azure App Service Deployment Guide

This document describes how to deploy the Django backend to Azure App Service (Linux) with PostgreSQL.

## Prerequisites

- Azure account with App Service and PostgreSQL database
- GitHub repository with the code
- GitHub Actions configured with required secrets

## Django Project Configuration

- **Django Settings Module**: `pharmacy_backend.settings`
- **Startup Command**: `gunicorn pharmacy_backend.wsgi --bind=0.0.0.0 --timeout 600`
- **Frontend URL**: `https://pharmafrontend.z29.web.core.windows.net/`

## Environment Files

### .env.example

The `.env.example` file is a template committed to the repository that shows all required environment variables. It serves as a reference for:
- Local development setup
- Understanding what environment variables are needed
- Azure App Service configuration reference

### .env (Local Development Only)

The `.env` file is used for **local development only** and **must not be committed** to version control. 

To set up local development:
1. Copy `.env.example` to `.env`
2. Update the values in `.env` with your local configuration
3. Ensure `.env` is listed in `.gitignore` (it should be by default)

**Important:** On Azure App Service, we do **NOT** use `.env` files. All environment variables are configured in the Azure App Service Configuration blade (Settings → Configuration → Application settings).

### Environment Variables in Azure

Configure the following environment variables in Azure App Service Configuration:

- `DJANGO_SETTINGS_MODULE` = `pharmacy_backend.settings`
- `SECRET_KEY` - Django secret key (generate a secure random string)
- `DEBUG` = `"false"` (for production)
- `ALLOWED_HOSTS` - Comma-separated list (e.g., `your-app.azurewebsites.net`)
- `DATABASE_URL` - PostgreSQL connection string with SSL
- `CORS_ALLOWED_ORIGINS` - Optional, comma-separated (defaults include localhost and production frontend)
- `CSRF_TRUSTED_ORIGINS` - Optional, comma-separated (defaults to production frontend)


## CORS / Frontend URL

### Deployed Frontend

The deployed frontend URL is: **https://pharmafrontend.z29.web.core.windows.net/**

### Default Configuration

By default, the following origins are allowed:

**CORS_ALLOWED_ORIGINS:**
- `http://localhost:3000` (local development)
- `http://127.0.0.1:3000` (local development)
- `https://pharmafrontend.z29.web.core.windows.net` (production frontend)

**CSRF_TRUSTED_ORIGINS:**
- `https://pharmafrontend.z29.web.core.windows.net` (production frontend)

### Overriding Origins

To override or extend the allowed origins, set the following environment variables in Azure App Service:

- `CORS_ALLOWED_ORIGINS` - Comma-separated list of URLs (e.g., `https://example.com,https://app.example.com`)
- `CSRF_TRUSTED_ORIGINS` - Comma-separated list of URLs (e.g., `https://example.com,https://app.example.com`)

If these environment variables are not set, the defaults listed above will be used.

**Note**: The CORS and CSRF configuration reads from environment variables. In Azure App Service, configure these in the Configuration blade (Settings → Configuration → Application settings), not in `.env` files.

## GitHub Actions Deployment

The project includes a GitHub Actions workflow (`.github/workflows/azure-webapp-backend.yml`) that automatically deploys to Azure App Service on push to the `main` branch.

### Required GitHub Secrets

Configure the following secrets in your GitHub repository (Settings → Secrets and variables → Actions):

- `AZURE_WEBAPP_NAME` - Name of your Azure App Service
- `AZURE_WEBAPP_PUBLISH_PROFILE` - Publish profile from Azure App Service (download from Azure Portal)
- `DJANGO_SECRET_KEY` - Django secret key
- `DJANGO_DEBUG` - Set to `"false"` for production
- `DJANGO_ALLOWED_HOSTS` - Comma-separated list of allowed hosts
- `DATABASE_URL` - PostgreSQL connection string

### Workflow Steps

1. Checkout code
2. Set up Python 3.11
3. Install dependencies from `requirements.txt`
4. Collect static files (`python manage.py collectstatic --noinput`)
5. (Optional) Run tests
6. Deploy to Azure Web App

## Static Files

Static files are handled by WhiteNoise middleware and collected during deployment. The `collectstatic` command runs automatically in the GitHub Actions workflow.

## Database

The project uses PostgreSQL with `dj-database-url` for database configuration. The `DATABASE_URL` environment variable must be set in Azure App Service with SSL required.

## Health Check Endpoint

A health check endpoint is available at `/api/health/` that returns `{"status": "ok"}`. This can be used for Azure App Service health checks and monitoring.

## Troubleshooting

### Common Issues

1. **Static files not loading**: Ensure `collectstatic` runs during deployment and `STATIC_ROOT` is configured correctly.

2. **CORS errors**: Verify `CORS_ALLOWED_ORIGINS` includes your frontend URL and the CorsMiddleware is properly configured.

3. **Database connection errors**: Check that `DATABASE_URL` is correctly formatted and includes SSL parameters.

4. **Environment variables not working**: Ensure variables are set in Azure App Service Configuration, not just in GitHub Secrets (GitHub Secrets are only used during build/deploy).

