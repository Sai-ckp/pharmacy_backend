from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file (for local development)
# This is safe - if .env doesn't exist, no error is thrown
load_dotenv(BASE_DIR / ".env")

# Database configuration using dj-database-url
# Azure-friendly: supports both DATABASE_URL and fallback DB_* env vars
db_url = os.environ.get("DATABASE_URL")

# Fallback: build URL from individual DB_* environment variables if DATABASE_URL is not set
if not db_url:
    db_host = os.environ.get("DB_HOST")
    db_name = os.environ.get("DB_NAME")
    
    # Only build fallback URL if we have at least DB_HOST and DB_NAME
    if db_host and db_name:
        db_user = os.environ.get("DB_USER", "")
        db_password = os.environ.get("DB_PASSWORD", "")
        db_port = os.environ.get("DB_PORT", "5432")
        
        # Build PostgreSQL connection URL
        if db_user and db_password:
            db_url = f"postgres://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        elif db_user:
            db_url = f"postgres://{db_user}@{db_host}:{db_port}/{db_name}"
        else:
            db_url = f"postgres://{db_host}:{db_port}/{db_name}"

# Fail fast if no database URL is available
if not db_url:
    raise ValueError(
        "Database configuration error: "
        "Either DATABASE_URL or DB_HOST+DB_NAME environment variables must be set. "
        "For Azure, use DATABASE_URL from the connection string."
    )

DATABASES = {
    "default": dj_database_url.config(
        default=db_url,
        conn_max_age=600,
        ssl_require=True,  # Required for Azure Database for PostgreSQL
    )
}

# Read SECRET_KEY from environment variable
# For local dev, it's okay to have a fallback, but document that it must be overridden in production
SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-default-change-me")

# Read DEBUG from environment variable
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# Read ALLOWED_HOSTS from environment variable
# Default includes localhost and Azure health probe IP
default_hosts = "localhost,127.0.0.1,169.254.130.3"
allowed_hosts_str = os.environ.get("ALLOWED_HOSTS", default_hosts)
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]

# Add Azure website hostname if available (Azure sets WEBSITE_HOSTNAME)
azure_hostname = os.environ.get("WEBSITE_HOSTNAME")
if azure_hostname and azure_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(azure_hostname)
    # Also add the plain hostname without region suffix if it exists
    if ".azurewebsites.net" in azure_hostname:
        plain_hostname = azure_hostname.split(".")[0] + ".azurewebsites.net"
        if plain_hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(plain_hostname)

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
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

#media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Global date formats (DD-MM-YYYY)
DATE_FORMAT = 'd-m-Y'
DATETIME_FORMAT = 'd-m-Y H:i'

# CORS configuration
# Read CORS_ALLOWED_ORIGINS from environment variable (comma-separated)
cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS")
if cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in cors_origins.split(",") if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://pharmafrontend.z29.web.core.windows.net",
    ]

# CSRF configuration
# Read CSRF_TRUSTED_ORIGINS from environment variable (comma-separated)
csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS")
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins.split(",") if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        "https://pharmafrontend.z29.web.core.windows.net",
    ]

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
