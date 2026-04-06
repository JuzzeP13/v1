"""
TISH SEARCH - Security Module
Защита от мошенников, ботов и злоумышленников
"""

import re
import time
import hashlib
import secrets
import sqlite3
import html
from datetime import datetime, timedelta
from functools import wraps
from flask import request, session, abort, jsonify

DATABASE_PATH = 'tish_data.db'

# ─── Rate Limiting ───

class RateLimiter:
    """Простой rate limiter на основе памяти (для production использовать Redis)"""
    
    def __init__(self):
        self.requests = {}  # {ip: [(timestamp, count), ...]}
    
    def is_allowed(self, key, max_requests, window_seconds):
        """Проверить, разрешён ли запрос"""
        now = time.time()
        window_start = now - window_seconds
        
        if key not in self.requests:
            self.requests[key] = []
        
        # Удаляем старые записи
        self.requests[key] = [
            (ts, count) for ts, count in self.requests[key]
            if ts > window_start
        ]
        
        # Считаем запросы в текущем окне
        total = sum(count for _, count in self.requests[key])
        
        if total >= max_requests:
            return False
        
        # Добавляем текущий запрос
        self.requests[key].append((now, 1))
        return True
    
    def get_remaining(self, key, max_requests, window_seconds):
        """Получить оставшееся количество запросов"""
        now = time.time()
        window_start = now - window_seconds
        
        if key not in self.requests:
            return max_requests
        
        total = sum(
            count for ts, count in self.requests[key]
            if ts > window_start
        )
        return max(0, max_requests - total)

rate_limiter = RateLimiter()

# ─── IP Blacklist ───

class IPBlacklist:
    """Чёрный список IP адресов"""
    
    def __init__(self):
        self.blacklist = set()
        self.temporary_bans = {}  # {ip: until_timestamp}
    
    def is_blacklisted(self, ip):
        """Проверить, заблокирован ли IP"""
        if ip in self.blacklist:
            return True
        
        # Проверяем временные баны
        if ip in self.temporary_bans:
            if time.time() < self.temporary_bans[ip]:
                return True
            else:
                del self.temporary_bans[ip]
        
        return False
    
    def add_permanent(self, ip):
        """Добавить в постоянный чёрный список"""
        self.blacklist.add(ip)
        self._save_to_db(ip, 'permanent')
    
    def add_temporary(self, ip, duration_minutes=60):
        """Добавить во временный чёрный список"""
        self.temporary_bans[ip] = time.time() + duration_minutes * 60
        self._save_to_db(ip, f'temporary_{duration_minutes}')
    
    def remove(self, ip):
        """Удалить из чёрного списка"""
        self.blacklist.discard(ip)
        self.temporary_bans.pop(ip, None)
    
    def _save_to_db(self, ip, ban_type):
        """Сохранить бан в БД"""
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_blacklist (
                id INTEGER PRIMARY KEY,
                ip TEXT UNIQUE NOT NULL,
                ban_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO ip_blacklist (ip, ban_type, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (ip, ban_type, datetime.now().isoformat(),
              datetime.now().isoformat() if ban_type == 'permanent' else None))
        conn.commit()
        conn.close()

ip_blacklist = IPBlacklist()

# ─── Suspicious Activity Detection ───

class SuspiciousActivityDetector:
    """Детектор подозрительной активности"""
    
    SUSPICIOUS_PATTERNS = [
        r'(?i)(?:sql\s*(?:injection|inject))',
        r'(?i)(?:<\s*script)',
        r'(?i)(?:javascript\s*:)',
        r'(?i)(?:on\w+\s*=)',
        r'(?i)(?:union\s+select)',
        r'(?i)(?:drop\s+table)',
        r'(?i)(?:exec\s*\()',
        r'(?i)(?:eval\s*\()',
        r'(?i)(?:base64_decode)',
        r'(?i)(?:\.\.\/)',  # Directory traversal
    ]
    
    def __init__(self):
        self.failed_logins = {}  # {ip: [timestamps]}
        self.suspicious_requests = {}  # {ip: count}
    
    def check_input(self, text):
        """Проверить ввод на подозрительные паттерны"""
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    def record_failed_login(self, ip):
        """Записать неудачную попытку входа"""
        now = time.time()
        
        if ip not in self.failed_logins:
            self.failed_logins[ip] = []
        
        # Удаляем старые записи (> 15 минут)
        self.failed_logins[ip] = [
            ts for ts in self.failed_logins[ip]
            if now - ts < 900
        ]
        
        self.failed_logins[ip].append(now)
        
        return len(self.failed_logins[ip])
    
    def is_rate_limited(self, ip, max_attempts=5):
        """Проверить, превышен ли лимит попыток"""
        if ip not in self.failed_logins:
            return False
        return len(self.failed_logins[ip]) >= max_attempts
    
    def record_suspicious_request(self, ip):
        """Записать подозрительный запрос"""
        if ip not in self.suspicious_requests:
            self.suspicious_requests[ip] = 0
        self.suspicious_requests[ip] += 1
        
        # Если слишком много подозрительных запросов - бан
        if self.suspicious_requests[ip] > 10:
            ip_blacklist.add_temporary(ip, 60)
            return True
        return False

suspicious_detector = SuspiciousActivityDetector()

# ─── CSRF Protection ───

def generate_csrf_token():
    """Сгенерировать CSRF токен"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def validate_csrf_token(token):
    """Проверить CSRF токен"""
    return token and token == session.get('_csrf_token')

def csrf_protect(f):
    """Декоратор для защиты от CSRF"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        if not validate_csrf_token(token):
            abort(403, description='CSRF token validation failed')
        return f(*args, **kwargs)
    return decorated_function

# ─── Input Sanitization ───

def sanitize_input(text, max_length=1000):
    """Базовая безопасная очистка пользовательского ввода"""
    if not isinstance(text, str):
        return ''
    
    text = text[:max_length].strip()
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = html.escape(text, quote=True)
    return text

def validate_email(email):
    """Валидация email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    if len(email) > 254:
        return False
    return True

def validate_username(username):
    """Валидация имени пользователя"""
    if not username or len(username) < 3 or len(username) > 30:
        return False
    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, username):
        return False
    return True

def validate_password(password):
    """Валидация пароля"""
    if not password or len(password) < 8:
        return False, "Пароль должен быть не менее 8 символов"
    if len(password) > 128:
        return False, "Пароль слишком длинный"
    if not re.search(r'[A-Z]', password):
        return False, "Пароль должен содержать хотя бы одну заглавную букву"
    if not re.search(r'[a-z]', password):
        return False, "Пароль должен содержать хотя бы одну строчную букву"
    if not re.search(r'[0-9]', password):
        return False, "Пароль должен содержать хотя бы одну цифру"
    return True, "OK"

# ─── Security Headers ───

def add_security_headers(response):
    """Добавить заголовки безопасности"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.socket.io; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src fonts.gstatic.com; connect-src 'self' *"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response

# ─── Logging ───

def log_security_event(event_type, ip, details=None):
    """Записать событие безопасности в БД"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_log (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        INSERT INTO security_log (event_type, ip_address, user_agent, details, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (event_type, ip, request.user_agent.string[:200] if request else None,
          str(details)[:500] if details else None, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ─── Middleware ───

def security_middleware():
    """Middleware для проверки безопасности каждого запроса"""
    ip = request.remote_addr

    # Проверяем чёрный список
    if ip_blacklist.is_blacklisted(ip):
        log_security_event('blocked_ip', ip)
        abort(403, description='Access denied')

    # Проверяем rate limiting (увеличено для 20+ пользователей)
    if not rate_limiter.is_allowed(f"global_{ip}", 2000, 3600):  # 2000 запросов в час (было 1000)
        log_security_event('rate_limit', ip)
        abort(429, description='Too many requests')

    # Проверяем подозрительные паттерны в запросе
    for param in request.args.values():
        if suspicious_detector.check_input(param):
            suspicious_detector.record_suspicious_request(ip)
            log_security_event('suspicious_input', ip, {'param': param[:100]})
            abort(400, description='Suspicious input detected')

# ─── Bot Detection ───

def is_likely_bot():
    """Проверить, является ли запрос ботом"""
    user_agent = request.user_agent.string.lower() if request.user_agent else ''
    
    # Известные боты
    bot_patterns = [
        'googlebot', 'bingbot', 'yandexbot', 'baiduspider',
        'slurp', 'duckduckbot', 'facebot', 'ia_archiver',
        'alexabot', 'mj12bot', 'ahrefsbot', 'semrushbot',
        'dotbot', 'rogerbot', 'lipperhey', 'linkis',
        'curl', 'wget', 'python-requests', 'scrapy',
    ]
    
    for pattern in bot_patterns:
        if pattern in user_agent:
            return True
    
    # Пустой или подозрительно короткий user agent
    if len(user_agent) < 10:
        return True
    
    return False

# ─── Password Hashing ───

def hash_password(password):
    """Хеширование пароля"""
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password, hashed):
    """Проверка пароля"""
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False
