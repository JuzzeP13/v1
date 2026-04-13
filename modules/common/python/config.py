import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    # Basic
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'dev-salt'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///tish_data.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Upload
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE') or 16 * 1024 * 1024)  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@tishsearch.com'
    
    # Ollama
    OLLAMA_URL = os.environ.get('OLLAMA_URL') or 'http://localhost:11434'
    VISION_MODEL = os.environ.get('VISION_MODEL') or 'qwen3-vl:latest'
    PRODUCT_SEARCH_USE_OLLAMA = os.environ.get('PRODUCT_SEARCH_USE_OLLAMA', 'False').lower() in ('true', '1', 'yes')
    PRODUCT_SEARCH_OLLAMA_MODEL = os.environ.get('PRODUCT_SEARCH_OLLAMA_MODEL') or ''
    PRODUCT_SEARCH_MAX_QUERIES = _env_int('PRODUCT_SEARCH_MAX_QUERIES', 60)
    PRODUCT_SEARCH_MAX_OLLAMA_VARIANTS = _env_int('PRODUCT_SEARCH_MAX_OLLAMA_VARIANTS', 6)
    
    # Security
    RATELIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT') or '100/hour'
    RATELIMIT_AUTH = os.environ.get('RATE_LIMIT_AUTH') or '10/minute'
    
    # Support
    SUPPORT_CHANNEL = os.environ.get('SUPPORT_CHANNEL') or 'https://t.me/tishteam_support'

    # Team official site — redirect target for registration
    TEAM_SITE_URL = os.environ.get('TEAM_SITE_URL') or 'https://tishteam.space/'
    
    # Main site API integration
    MAIN_SITE_URL = os.environ.get('MAIN_SITE_URL') or 'https://tishteam.space'
    MAIN_SITE_API_URL = os.environ.get('MAIN_SITE_API_URL') or f"{MAIN_SITE_URL}/api"
    MAIN_SITE_API_TOKEN = os.environ.get('MAIN_SITE_API_TOKEN')  # Серверный токен для API запросв
    
    # Subscription plans
    SUBSCRIPTION_PLANS = {
        'basic': {
            'name': 'Basic',
            'price_rub': 990,
            'price_usd': 12,
            'features': [
                'Поиск до 30 сайтов за раз',
                'Базовый AI-анализ',
                '1 пользователь',
                'Email поддержка'
            ]
        },
        'pro': {
            'name': 'Pro',
            'price_rub': 2990,
            'price_usd': 35,
            'features': [
                'Поиск до 100 сайтов за раз',
                'Расширенный AI-анализ',
                'До 5 пользователей',
                'Приоритетная поддержка',
                'API доступ',
                'Экспорт в Excel/PDF'
            ]
        },
        'enterprise': {
            'name': 'Enterprise',
            'price_rub': 9990,
            'price_usd': 120,
            'features': [
                'Безлимитный поиск',
                'Полный AI-анализ',
                'Безлимитные пользователи',
                '24/7 поддержка',
                'Полный API доступ',
                'Индивидуальные отчёты',
                'Белая метка',
                'Персональный менеджер'
            ]
        }
    }
    
    # Search categories
    SEARCH_CATEGORIES = {
        'websites': 'Сайты',
        'youtube': 'YouTube',
        'instagram': 'Instagram',
        'twitter': 'X (Twitter)'
    }
    
    # Languages
    LANGUAGES = {
        'ru': 'Русский',
        'en': 'English'
    }
    
    # Default language
    DEFAULT_LANGUAGE = 'ru'
