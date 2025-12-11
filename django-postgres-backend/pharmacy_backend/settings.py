from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file (for local development)
# This is safe - if .env doesn't exist, no error is thrown
load_dotenv(BASE_DIR / ".env")

# Detect if we're running on Azure (Azure sets WEBSITE_HOSTNAME)
IS_AZURE = bool(os.environ.get("WEBSITE_HOSTNAME"))

# Database configuration using dj-database-url
# Azure-friendly: supports both DATABASE_URL and fallback DB_* env vars
# Local-friendly: falls back to SQLite if no database config is found
db_url = os.environ.get("DATABASE_URL")

# Fallback: build URL from individual DB_* environment variables if DATABASE_URL is not set
if not db_url:
    db_host = os.environ.get("DB_HOST", "localhost")  # Default to localhost for local dev
    db_name = os.environ.get("DB_NAME", "pharmacy_inventorydb")  # Default database name
    
    # Only build fallback URL if we have at least DB_HOST and DB_NAME
    if db_host and db_name:
        db_user = os.environ.get("DB_USER", "postgres")  # Default user
        db_password = os.environ.get("DB_PASSWORD", "root")  # No default password - user must set it
        db_port = os.environ.get("DB_PORT", "5432")  # Default port
        
        # Build PostgreSQL connection URL
        if db_user and db_password:
            db_url = f"postgres://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        elif db_user:
            db_url = f"postgres://{db_user}@{db_host}:{db_port}/{db_name}"
        else:
            db_url = f"postgres://{db_host}:{db_port}/{db_name}"

# Configure database
if db_url:
    # PostgreSQL database (Azure or local PostgreSQL)
    # SSL is required for Azure, optional for local PostgreSQL
    ssl_require = IS_AZURE  # Only require SSL on Azure
    
    DATABASES = {
        "default": dj_database_url.config(
            default=db_url,
            conn_max_age=600,
            ssl_require=ssl_require,
        )
    }
    
    # For local PostgreSQL, if SSL fails, try without SSL requirement
    if not IS_AZURE:
        # Override sslmode in the database config for local development
        # This allows local PostgreSQL databases without SSL certificates
        if "OPTIONS" not in DATABASES["default"]:
            DATABASES["default"]["OPTIONS"] = {}
        # Only set sslmode if not already set
        if "sslmode" not in DATABASES["default"]["OPTIONS"]:
            DATABASES["default"]["OPTIONS"]["sslmode"] = "prefer"  # prefer SSL but don't require
else:
    # No database URL found - use SQLite for local development
    if IS_AZURE:
        # On Azure, we must have a database configured
        raise ValueError(
            "Database configuration error: "
            "Either DATABASE_URL or DB_HOST+DB_NAME environment variables must be set. "
            "For Azure, use DATABASE_URL from the connection string."
        )
    else:
        # Local development: fall back to SQLite
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }
        print("⚠️  WARNING: No database configuration found. Using SQLite for local development.")
        print("   To use PostgreSQL locally, set DATABASE_URL or DB_HOST+DB_NAME environment variables.")

# Read SECRET_KEY from environment variable
# For local dev, it's okay to have a fallback, but document that it must be overridden in production
SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-default-change-me")

# Read DEBUG from environment variable
# Default: True for local development, False for Azure (production)
DEBUG = os.environ.get("DEBUG", "True" if not IS_AZURE else "False").lower() == "true"

# Read ALLOWED_HOSTS from environment variable
# Detect Azure more reliably (check multiple indicators)
azure_indicators = [
    os.environ.get("WEBSITE_HOSTNAME"),  # Azure App Service sets this
    os.environ.get("WEBSITE_SITE_NAME"),  # Azure App Service
    os.environ.get("WEBSITE_RESOURCE_GROUP"),  # Azure App Service
    os.environ.get("WEBSITE_INSTANCE_ID"),  # Azure App Service
]

IS_AZURE = IS_AZURE or any(azure_indicators)

if IS_AZURE:
    # Azure: Default includes localhost and Azure internal IP ranges
    # Azure uses 169.254.x.x for internal health probes and load balancer checks
    default_hosts = "localhost,127.0.0.1,*.azurewebsites.net"
    
    # Get ALLOWED_HOSTS from environment variable or use defaults
    allowed_hosts_str = os.environ.get("ALLOWED_HOSTS", default_hosts)
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]
    
    # Add Azure website hostname if available (Azure sets WEBSITE_HOSTNAME)
    azure_hostname = os.environ.get("WEBSITE_HOSTNAME")
    if azure_hostname:
        # Remove port if present (Azure sometimes includes port)
        hostname_without_port = azure_hostname.split(":")[0]
        if hostname_without_port not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(hostname_without_port)
        
        # Also add the plain hostname without region suffix if it exists
        if ".azurewebsites.net" in hostname_without_port:
            plain_hostname = hostname_without_port.split(".")[0] + ".azurewebsites.net"
            if plain_hostname not in ALLOWED_HOSTS:
                ALLOWED_HOSTS.append(plain_hostname)
    
    # Allow Azure internal IPs (169.254.x.x range for health probes)
    # Note: Django doesn't support wildcards in IPs, so we'll use a middleware workaround
    # But for now, add common Azure probe IPs
    azure_probe_ips = [
        "169.254.130.1", "169.254.130.2", "169.254.130.3", "169.254.130.4",
        "169.254.129.1", "169.254.129.2", "169.254.129.3", "169.254.129.4",
    ]
    for ip in azure_probe_ips:
        if ip not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(ip)
    
    # In Azure, if DEBUG is True and no explicit ALLOWED_HOSTS is set, allow all for easier debugging
    if DEBUG and not os.environ.get("ALLOWED_HOSTS"):
        ALLOWED_HOSTS = ["*"]
else:
    # Local development: Allow all hosts when DEBUG is True, otherwise use environment variable
    if DEBUG:
        ALLOWED_HOSTS = ["*"]  # Allow all hosts in local development
    else:
        default_hosts = "localhost,127.0.0.1"
        allowed_hosts_str = os.environ.get("ALLOWED_HOSTS", default_hosts)
        ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles', 
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
    # Local apps
    'core',
    'apps.customers',
    'apps.sales',
    'apps.transfers',
    'apps.compliance',
    'apps.reports',
    'apps.notifications',
    # Dev A apps
    'apps.accounts',
    'apps.locations',
    'apps.catalog',
    'apps.inventory',
    'apps.procurement',
    'apps.settingsx',
    'apps.governance',
    'apps.dashboard',
    
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.AzureInternalIPMiddleware',  # Handle Azure internal IPs before CommonMiddleware
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.governance.middleware.RequestIdMiddleware',
]

ROOT_URLCONF = 'pharmacy_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pharmacy_backend.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# Static files storage
# Use WhiteNoise for production (Azure), Django's default for local development
if IS_AZURE:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
else:
    # Local development: use default storage (no compression/manifest needed)
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

#media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Global date formats (DD-MM-YYYY)
DATE_FORMAT = 'd-m-Y'
DATETIME_FORMAT = 'd-m-Y H:i'

# CORS configuration
# For local development with DEBUG=True, allow all origins (useful for development)
if DEBUG and not IS_AZURE:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOWED_ORIGINS = []  # Not used when CORS_ALLOW_ALL_ORIGINS is True
else:
    # Read CORS_ALLOWED_ORIGINS from environment variable (comma-separated)
    cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS")
    if cors_origins:
        CORS_ALLOWED_ORIGINS = [o.strip() for o in cors_origins.split(",") if o.strip()]
    else:
        # Default CORS origins
        CORS_ALLOWED_ORIGINS = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",  # Vite default port
            "http://127.0.0.1:5173",
        ]
        # Add Azure frontend URL if on Azure
        if IS_AZURE:
            CORS_ALLOWED_ORIGINS.append("https://pharmafrontend.z29.web.core.windows.net")

# CSRF configuration
# Read CSRF_TRUSTED_ORIGINS from environment variable (comma-separated)
csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS")
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins.split(",") if o.strip()]
else:
    # Default CSRF trusted origins
    CSRF_TRUSTED_ORIGINS = []
    # Add Azure frontend URL if on Azure
    if IS_AZURE:
        CSRF_TRUSTED_ORIGINS.append("https://pharmafrontend.z29.web.core.windows.net")
    # For local development, add common localhost URLs
    if not IS_AZURE:
        CSRF_TRUSTED_ORIGINS.extend([
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ])

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'core.permissions.HasActiveSystemLicense',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    # API date formats (DD-MM-YYYY)
    'DATE_FORMAT': '%d-%m-%Y',
    'DATETIME_FORMAT': '%d-%m-%Y %H:%M',
    # Accept both new DD-MM-YYYY and old ISO inputs
    'DATE_INPUT_FORMATS': ['%d-%m-%Y', '%Y-%m-%d'],
    'DATETIME_INPUT_FORMATS': [
        '%d-%m-%Y %H:%M',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%d %H:%M:%S',
    ],
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Pharmacy ERP API',
    'VERSION': 'v1',
    'SERVE_INCLUDE_SCHEMA': False,
    'DEFAULT_GENERATOR_CLASS': 'core.schema.CustomSchemaGenerator',
}



EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'ckpsoftwarekeshavmedical@gmail.com'  # your Gmail ID
EMAIL_HOST_PASSWORD = 'ippe lryh zpcb xfav'          # 16-char App Password
DEFAULT_FROM_EMAIL = 'saishashank0143@gmail.com'
