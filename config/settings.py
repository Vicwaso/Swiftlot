import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
LOCAL_ONLY = os.getenv('LOCAL_ONLY', 'false').lower() == 'true'
DEBUG = LOCAL_ONLY or os.getenv('DEBUG', 'false').lower() == 'true'
SECRET_KEY = '' if LOCAL_ONLY else os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set SECRET_KEY and DATABASE_URL, or use start-local.ps1.')
    secret_file = BASE_DIR / '.local-secret'
    if not secret_file.exists():
        from django.core.management.utils import get_random_secret_key
        secret_file.write_text(get_random_secret_key(), encoding='utf-8')
    SECRET_KEY = secret_file.read_text(encoding='utf-8').strip()
render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME', '').strip()
ALLOWED_HOSTS = ['localhost','127.0.0.1'] if LOCAL_ONLY else [s for s in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if s]
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
CSRF_TRUSTED_ORIGINS = [s for s in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if s]
if render_hostname:
    render_origin = f'https://{render_hostname}'
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.messages', 'django.contrib.staticfiles', 'django.contrib.humanize',
    'brokerage.apps.BrokerageConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'brokerage.middleware.ResponsePolicyMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'],
 'APP_DIRS': True, 'OPTIONS': {'context_processors': [
 'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
 'django.contrib.messages.context_processors.messages', 'brokerage.context_processors.site_context']}}]
WSGI_APPLICATION = 'config.wsgi.application'
database_url = '' if LOCAL_ONLY else os.getenv('DATABASE_URL', '')
if database_url:
    DATABASES = {'default': dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True)}
elif DEBUG:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.getenv('LOCAL_DATABASE_PATH', str(BASE_DIR / 'local.sqlite3')), 'OPTIONS': {'timeout': 20}}}
else:
    raise ImproperlyConfigured('Production requires DATABASE_URL pointing to PostgreSQL.')
if not DEBUG and DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('PostgreSQL is required in production.')
AUTH_PASSWORD_VALIDATORS = [
 {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
 {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
 {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
 {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = os.getenv('TIME_ZONE', 'Africa/Nairobi')
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
if os.getenv('S3_BUCKET') and not LOCAL_ONLY:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
        'bucket_name': os.environ['S3_BUCKET'], 'default_acl': 'private',
        'region_name': os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
        'endpoint_url': os.getenv('S3_ENDPOINT_URL') or None,
        'file_overwrite': False, 'querystring_auth': True,
    }}
MEDIA_ROOT = BASE_DIR/'storage' if LOCAL_ONLY else Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'storage')))
# Never expose MEDIA_ROOT through a web server: all files pass availability/access checks.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 30
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755
LOGIN_URL = '/staff/login/'
LOGIN_REDIRECT_URL = '/staff/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if os.getenv('TRUST_PROXY', 'false') == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = '' if LOCAL_ONLY else os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true') == 'true'
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '')
MFA_REQUIRED = os.getenv('MFA_REQUIRED', 'true').lower() == 'true'
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN') or (f'https://{render_hostname}' if render_hostname else 'http://127.0.0.1:8000')
PUBLIC_ORIGIN = PUBLIC_ORIGIN.rstrip('/')
CLAMAV_HOST = os.getenv('CLAMAV_HOST', '')
CLAMAV_PORT = int(os.getenv('CLAMAV_PORT', '3310'))
LOGGING = {'version': 1, 'disable_existing_loggers': False,
 'handlers': {'console': {'class': 'logging.StreamHandler'}},
 'root': {'handlers': ['console'], 'level': 'INFO'}}
