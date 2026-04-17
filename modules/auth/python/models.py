from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json

DATABASE_PATH = 'tish_data.db'

def get_db():
    """Получить соединение с базой данных"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_extended_db():
    """Инициализация расширенной базы данных"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            is_active BOOLEAN DEFAULT 1,
            is_verified BOOLEAN DEFAULT 0,
            profile_image TEXT,
            theme TEXT DEFAULT 'dark',
            language TEXT DEFAULT 'ru',
            subscription_plan TEXT DEFAULT 'basic',
            subscription_expires TEXT,
            api_key TEXT UNIQUE,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TEXT,
            main_site_id INTEGER UNIQUE,
            main_site_api_token TEXT,
            priority INTEGER DEFAULT 2,
            last_sync TEXT
        )
    """)

    # Миграция старых БД: добавляем недостающие поля интеграции с main-site.
    user_columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    user_migrations = {
        "main_site_id": "ALTER TABLE users ADD COLUMN main_site_id INTEGER",
        "main_site_api_token": "ALTER TABLE users ADD COLUMN main_site_api_token TEXT",
        "priority": "ALTER TABLE users ADD COLUMN priority INTEGER DEFAULT 2",
        "last_sync": "ALTER TABLE users ADD COLUMN last_sync TEXT",
    }
    for column_name, sql in user_migrations.items():
        if column_name not in user_columns:
            print(f"[MIGRATION] Добавляю колонку users.{column_name}...")
            cursor.execute(sql)
    
    # Таблица сессий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Таблица восстановления пароля
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Таблица подписок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payment_id TEXT,
            amount REAL,
            currency TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Таблица платежей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subscription_id INTEGER,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_method TEXT,
            transaction_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL
        )
    """)
    
    # Таблица загрузок (примеры для анализа)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            original_name TEXT,
            file_size INTEGER,
            description TEXT,
            is_good_example BOOLEAN,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Таблица активности (логирование)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    
    # Таблица поисковых запросов (для статистики)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT NOT NULL,
            query TEXT,
            city TEXT,
            results_count INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    
    # Индексы для ускорения запросов
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_main_site_id ON users(main_site_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_log(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_user_id ON search_history(user_id)")
    
    conn.commit()
    conn.close()
    print("[DB] Расширенная инициализация завершена ✓")


# Класс пользователя
class User:
    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.email = row['email']
        self.password_hash = row['password_hash']
        self.created_at = row['created_at']
        self.last_login = row['last_login']
        self.is_active = bool(row['is_active'])
        self.is_verified = bool(row['is_verified'])
        self.profile_image = row['profile_image']
        self.theme = row['theme'] or 'dark'
        self.language = row['language'] or 'ru'
        self.subscription_plan = row['subscription_plan'] or 'basic'
        self.subscription_expires = row['subscription_expires']
        self.api_key = row['api_key']
        self.failed_login_attempts = row['failed_login_attempts'] or 0
        self.locked_until = row['locked_until']
        # Новые поля с проверкой (могут отсутствовать в старых БД)
        try:
            self.main_site_id = row['main_site_id']
        except IndexError:
            self.main_site_id = None
        try:
            self.main_site_api_token = row['main_site_api_token']
        except IndexError:
            self.main_site_api_token = None
        try:
            self.priority = row['priority'] or 2
        except IndexError:
            self.priority = 2
        try:
            self.last_sync = row['last_sync']
        except IndexError:
            self.last_sync = None
    
    @staticmethod
    def create(username, email, password):
        """Создать нового пользователя"""
        conn = get_db()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        created_at = datetime.now().isoformat()
        
        try:
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
            """, (username, email, password_hash, created_at))
            conn.commit()
            user_id = cursor.lastrowid
            return User.get_by_id(user_id)
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    @staticmethod
    def get_by_id(user_id):
        """Получить пользователя по ID"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return User(row) if row else None
    
    @staticmethod
    def get_by_email(email):
        """Получить пользователя по email"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        return User(row) if row else None
    
    @staticmethod
    def get_by_username(username):
        """Получить пользователя по имени"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        return User(row) if row else None

    @staticmethod
    def get_by_main_site_id(main_site_id):
        """Получить пользователя по ID с главного сайта"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE main_site_id = ?", (main_site_id,))
        row = cursor.fetchone()
        conn.close()
        return User(row) if row else None
    
    def check_password(self, password):
        """Проверить пароль"""
        return check_password_hash(self.password_hash, password)
    
    def update_profile(self, **kwargs):
        """Обновить профиль пользователя"""
        conn = get_db()
        cursor = conn.cursor()
        
        allowed_fields = ['theme', 'language', 'profile_image']
        updates = []
        values = []
        
        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)
        
        if updates:
            values.append(self.id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
        
        conn.close()
    
    def log_activity(self, action, ip_address=None, user_agent=None, details=None):
        """Записать активность пользователя"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activity_log (user_id, action, ip_address, user_agent, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (self.id, action, ip_address, user_agent, json.dumps(details) if details else None, 
              datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def is_authenticated(self):
        return self.is_active
    
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)
    
    def to_dict(self):
        """Конвертировать в словарь (без чувствительных данных)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at,
            'last_login': self.last_login,
            'is_verified': self.is_verified,
            'profile_image': self.profile_image,
            'theme': self.theme,
            'language': self.language,
            'subscription_plan': self.subscription_plan,
            'subscription_expires': self.subscription_expires,
            'main_site_id': self.main_site_id,
            'priority': self.priority,
        }

    def has_active_subscription(self):
        """Проверить, есть ли активная подписка"""
        if not self.subscription_plan or self.subscription_plan == 'basic':
            return True  # Basic план всегда доступен

        if not self.subscription_expires:
            return self.subscription_plan == 'basic'

        try:
            expires = datetime.fromisoformat(self.subscription_expires)
            return expires > datetime.now()
        except (ValueError, TypeError):
            return False

    def get_subscription_limits(self):
        """Получить лимиты подписки"""
        limits = {
            'basic': {
                'max_cities_per_day': 3,
                'max_sites_per_city': 30,
                'max_parallel': 3,
                'max_results': 30,
                'can_export': False,
                'can_api': False,
                'priority': 1,
                'name': 'Basic',
                'name_ru': 'Базовый',
            },
            'pro': {
                'max_cities_per_day': 10,
                'max_sites_per_city': 100,
                'max_parallel': 5,
                'max_results': 100,
                'can_export': True,
                'can_api': True,
                'priority': 2,
                'name': 'Pro',
                'name_ru': 'Профессиональный',
            },
            'enterprise': {
                'max_cities_per_day': -1,  # Без ограничений
                'max_sites_per_city': -1,
                'max_parallel': 8,
                'max_results': -1,
                'can_export': True,
                'can_api': True,
                'priority': 3,
                'name': 'Enterprise',
                'name_ru': 'Корпоративный',
            }
        }
        
        base_limits = limits.get(self.subscription_plan, limits['basic'])
        
        # Если есть приоритет с главного сайта - используем его
        if hasattr(self, 'priority') and self.priority:
            base_limits['priority'] = self.priority
        
        return base_limits

    def can_run_analysis(self, cities_count=1, sites_count=30):
        """Проверить, может ли пользователь запустить анализ"""
        if not self.has_active_subscription():
            return False, "Подписка истекла. Продлите для продолжения работы."

        limits = self.get_subscription_limits()

        # Проверка количества городов
        if limits['max_cities_per_day'] > 0 and cities_count > limits['max_cities_per_day']:
            return False, f"Превышен лимит городов: {limits['max_cities_per_day']} в день для плана {limits['name_ru']}"

        # Проверка количества сайтов
        if limits['max_sites_per_city'] > 0 and sites_count > limits['max_sites_per_city']:
            return False, f"Превышен лимит сайтов: {limits['max_sites_per_city']} для плана {limits['name_ru']}"

        return True, "OK"

    def get_usage_today(self):
        """Получить использование сегодня"""
        conn = get_db()
        cursor = conn.cursor()
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        cursor.execute("""
            SELECT COUNT(DISTINCT city) as cities_count, COUNT(*) as total_sites
            FROM search_history
            WHERE user_id = ? AND created_at >= ?
        """, (self.id, today_start))

        row = cursor.fetchone()
        conn.close()

        return {
            'cities_today': row['cities_count'] if row else 0,
            'sites_today': row['total_sites'] if row else 0
        }
