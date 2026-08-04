"""
Django settings for the ShineHub Car Wash Management System.
Developed by BRENDA KANINI.
"""

from pathlib import Path
from decimal import Decimal
import sys

from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = 'test' in sys.argv or 'pytest' in sys.modules

SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-CHANGE-ME')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = ['*']
DJANGO_ENV = config('DJANGO_ENV', default='production')

SITE_NAME = config('SITE_NAME', default='ShineHub')
COMPANY_NAME = config('COMPANY_NAME', default='BRENDA KANINI')
SITE_DOMAIN = config('SITE_DOMAIN', default='localhost:8000')


DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'channels',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.customers',
    'apps.vehicles',
    'apps.services',
    'apps.bookings',
    'apps.payments',
    'apps.inventory',
    'apps.employees',
    'apps.reports',
    'apps.notifications',
    'apps.dashboard',
    'apps.site_settings',
    'apps.audit_logs',
    'apps.feedback',
    'apps.loyalty',
    'apps.analytics',
]


INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'apps.core.middleware.SecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.accounts.middleware.SessionSecurityMiddleware',
    'apps.accounts.middleware.ForcePasswordChangeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.audit_logs.middleware.AuditLogMiddleware',
    'apps.core.middleware.RatelimitMiddleware',
]

ROOT_URLCONF = 'shinehub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'shinehub.wsgi.application'
ASGI_APPLICATION = 'shinehub.asgi.application'




DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# CHANNELS (WebSockets / real-time notifications)

REDIS_HOST = config('REDIS_HOST', default='127.0.0.1')
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)


# if config('USE_INMEMORY_CHANNEL_LAYER', default=False, cast=bool):
CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
# else:
#     CHANNEL_LAYERS = {
#         'default': {
#             'BACKEND': 'channels_redis.core.RedisChannelLayer',
#             'CONFIG': {
#                 'hosts': [(REDIS_HOST, REDIS_PORT)],
#             },
#         },
#     }


REDIS_CACHE_DB = config('REDIS_CACHE_DB', default=1, cast=int)

# if config('USE_INMEMORY_CHANNEL_LAYER', default=False, cast=bool):
CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        },
    }
# else:
#     CACHES = {
#         'default': {
#             'BACKEND': 'django_redis.cache.RedisCache',
#             'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CACHE_DB}',
#             'OPTIONS': {
#                 'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#             },
#         },
#     }

# RATE LIMITING (django-ratelimit)

RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', default=True, cast=bool) and not TESTING
RATELIMIT_USE_CACHE = 'default'

RATELIMIT_LOGIN = config('RATELIMIT_LOGIN', default='10/5m')
RATELIMIT_REGISTER = config('RATELIMIT_REGISTER', default='5/h')
RATELIMIT_PASSWORD_RESET_REQUEST_IP = config('RATELIMIT_PASSWORD_RESET_REQUEST_IP', default='5/h')
RATELIMIT_PASSWORD_RESET_REQUEST_EMAIL = config('RATELIMIT_PASSWORD_RESET_REQUEST_EMAIL', default='3/h')
RATELIMIT_PASSWORD_RESET_CONFIRM = config('RATELIMIT_PASSWORD_RESET_CONFIRM', default='10/h')
RATELIMIT_RESEND_VERIFICATION = config('RATELIMIT_RESEND_VERIFICATION', default='3/h')
RATELIMIT_MPESA_CALLBACK = config('RATELIMIT_MPESA_CALLBACK', default='60/m')
RATELIMIT_MPESA_INITIATE = config('RATELIMIT_MPESA_INITIATE', default='10/m')
RATELIMIT_PAYMENT_ACTION = config('RATELIMIT_PAYMENT_ACTION', default='20/h')
RATELIMIT_PAYMENT_POLL = config('RATELIMIT_PAYMENT_POLL', default='60/m')
RATELIMIT_FEEDBACK_SUBMIT = config('RATELIMIT_FEEDBACK_SUBMIT', default='10/h')
RATELIMIT_NOTIFICATIONS_POLL = config('RATELIMIT_NOTIFICATIONS_POLL', default='120/m')
RATELIMIT_CONTACT = config('RATELIMIT_CONTACT', default='5/h')

# AUTHENTICATION

AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'core:landing'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'apps.accounts.validators.ComplexPasswordValidator'},
    {'NAME': 'apps.accounts.validators.PasswordReuseValidator'},
]


PASSWORD_HISTORY_COUNT = config('PASSWORD_HISTORY_COUNT', default=5, cast=int)

ACCOUNT_LOCKOUT_ATTEMPTS = 5
ACCOUNT_LOCKOUT_MINUTES = 15

PASSWORD_RESET_TIMEOUT = 60 * 60 * 2  # 2 hours, in seconds



SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days ("remember me" baseline)


SESSION_INACTIVITY_TIMEOUT_MINUTES = config('SESSION_INACTIVITY_TIMEOUT_MINUTES', default=60, cast=int)

CSRF_COOKIE_HTTPONLY = False 
CSRF_COOKIE_SAMESITE = 'Lax'


SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


CONTENT_SECURITY_POLICY = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", 'https://cdn.tailwindcss.com', 'https://cdnjs.cloudflare.com'],
    'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com', 'https://cdnjs.cloudflare.com'],
    'font-src': ["'self'", 'https://fonts.gstatic.com', 'https://cdnjs.cloudflare.com'],
    'img-src': ["'self'", 'data:', 'https://images.unsplash.com'],
    'connect-src': ["'self'", 'ws:', 'wss:'],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
}


PERMISSIONS_POLICY = {
    'camera': [], 'microphone': [], 'geolocation': [], 'payment': [],
    'usb': [], 'magnetometer': [], 'gyroscope': [], 'accelerometer': [],
}



LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True



STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



_email_creds_present = bool(config('EMAIL_HOST_USER', default='')) and bool(config('EMAIL_HOST_PASSWORD', default=''))

if DEBUG and not _email_creds_present:

    EMAIL_BACKEND = 'django.core.mail.backends.smtpp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='ShineHub <brendakanini01@gmail.com>')


DARAJA_ENV = config('DARAJA_ENV', default='sandbox')
DARAJA_BASE_URL = (
    'https://sandbox.safaricom.co.ke' if DARAJA_ENV == 'sandbox'
    else 'https://api.safaricom.co.ke'
)
DARAJA_CONSUMER_KEY = config('DARAJA_CONSUMER_KEY', default='')
DARAJA_CONSUMER_SECRET = config('DARAJA_CONSUMER_SECRET', default='')
DARAJA_SHORTCODE = config('DARAJA_SHORTCODE', default='174379')
DARAJA_PASSKEY = config('DARAJA_PASSKEY', default='')
DARAJA_CALLBACK_URL = config('DARAJA_CALLBACK_URL', default='')


MPESA_CALLBACK_ALLOWED_IPS = config('MPESA_CALLBACK_ALLOWED_IPS', default='', cast=Csv())


INVOICE_TAX_RATE = Decimal(config('INVOICE_TAX_RATE', default='0'))


LOYALTY_POINTS_PER_100_KSH = config('LOYALTY_POINTS_PER_100_KSH', default=1, cast=int)


LOYALTY_REFERRAL_BONUS_POINTS = config('LOYALTY_REFERRAL_BONUS_POINTS', default=500, cast=int)
LOYALTY_REFERRAL_BONUS_WALLET = Decimal(config('LOYALTY_REFERRAL_BONUS_WALLET', default='100.00'))

LOYALTY_BIRTHDAY_BONUS_POINTS = config('LOYALTY_BIRTHDAY_BONUS_POINTS', default=200, cast=int)



BUSINESS_HOURS_START_HOUR = config('BUSINESS_HOURS_START_HOUR', default=8, cast=int)
BUSINESS_HOURS_END_HOUR = config('BUSINESS_HOURS_END_HOUR', default=18, cast=int)



(BASE_DIR / 'logs').mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'shinehub.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'shinehub': {'handlers': ['console', 'file'], 'level': 'DEBUG', 'propagate': False},
    },
}



from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG: 'debug',
    messages_constants.INFO: 'info',
    messages_constants.SUCCESS: 'success',
    messages_constants.WARNING: 'warning',
    messages_constants.ERROR: 'error',
}
