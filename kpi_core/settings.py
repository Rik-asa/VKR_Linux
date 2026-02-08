# kpi_core/settings.py

import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

# Используем ConfigManager
from .config import ConfigManager

IS_CONFIGURED = ConfigManager.is_configured()

# ==============================================
# ВЫВОД ИНФОРМАЦИИ В КОНСОЛЬ
# ==============================================

if IS_CONFIGURED:
    # Пытаемся загрузить БД
    try:
        DATABASES = ConfigManager.get_django_databases()
    except Exception as e:
        IS_CONFIGURED = False  # Принудительно сбрасываем

if IS_CONFIGURED:
    # ==========================================
    # РЕЖИМ РАБОТЫ СИСТЕМЫ (после настройки)
    # ==========================================
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']
    
     # Загружаем SECRET_KEY из .env
    import environ
    env = environ.Env()
    env.read_env(BASE_DIR / '.env')
    SECRET_KEY = env.str('SECRET_KEY', 'change-this-in-production')

    # Загружаем настройки БД
    DATABASES = ConfigManager.get_django_databases()
    
    # Все приложения
    INSTALLED_APPS = [
    'admin_interface',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Мои приложения
    'users.apps.UsersConfig',
    'references',
    'plans',
    'integration',
    'kpi_calc',
    'dashboard',
    'setup',  # ← ТОЛЬКО ОДИН РАЗ!
    
    # Сторонние
    'rest_framework',
    ]
    
    # Настройки аутентификации
    AUTH_USER_MODEL = 'users.User'
    LOGIN_URL = '/accounts/login/'
    LOGIN_REDIRECT_URL = '/'
    LOGOUT_REDIRECT_URL = '/accounts/login/'
    
    ROOT_URLCONF = 'kpi_core.urls'
    
else:
    # ==========================================
    # РЕЖИМ МАСТЕРА НАСТРОЙКИ (первый запуск)
    # ==========================================
    DEBUG = True
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']
    SECRET_KEY = 'temporary-key-for-setup-only'
    
    # Только минимальные приложения для мастера
    INSTALLED_APPS = [
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'setup',  # Мастер настройки
    ]
    
    # В режиме мастера БД НЕ НУЖНА!
    # Мастер работает без БД, только проверяет подключения
    DATABASES = {}

    # Специальные URL для мастера
    ROOT_URLCONF = 'setup.urls'
    
    # Отключаем всё что связано с аутентификацией
    AUTH_USER_MODEL = None

# ==============================================
# ОБЩИЕ НАСТРОЙКИ (для обоих режимов)
# ==============================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# В режиме мастера убираем AuthenticationMiddleware
if IS_CONFIGURED:
    MIDDLEWARE.insert(4, 'django.contrib.auth.middleware.AuthenticationMiddleware')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# В режиме работы добавляем auth контекст-процессор
if IS_CONFIGURED:
    TEMPLATES[0]['OPTIONS']['context_processors'].insert(
        2, 'django.contrib.auth.context_processors.auth'
    )

WSGI_APPLICATION = 'kpi_core.wsgi.application'

# Валидация паролей только в режиме работы
if IS_CONFIGURED:
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

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework только в режиме работы
if IS_CONFIGURED:
    REST_FRAMEWORK = {
        'DEFAULT_PERMISSION_CLASSES': [
            'rest_framework.permissions.IsAuthenticated',
        ]
    }