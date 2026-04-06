"""
TISH SEARCH v4 - SQLite to PostgreSQL Migration Script
Миграция базы данных из SQLite в PostgreSQL
Запуск: python migrate_to_postgres.py
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════

SQLITE_DB = os.environ.get('SQLITE_DB', 'tish_data.db')
PG_HOST = os.environ.get('PG_HOST', 'localhost')
PG_PORT = os.environ.get('PG_PORT', '5432')
PG_DATABASE = os.environ.get('PG_DATABASE', 'tish_db')
PG_USER = os.environ.get('PG_USER', 'tish_user')
PG_PASSWORD = os.environ.get('PG_PASSWORD', 'change_me')

# ═══════════════════════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════════════════════

def get_sqlite_tables():
    """Получить список таблиц из SQLite"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def get_sqlite_schema(table):
    """Получить схему таблицы из SQLite"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    columns = cursor.fetchall()
    conn.close()
    return columns

def get_sqlite_data(table):
    """Получить все данные из таблицы SQLite"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table};")
    data = cursor.fetchall()
    conn.close()
    return data

def create_postgres_connection():
    """Создать подключение к PostgreSQL"""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )

def create_postgres_tables():
    """Создать таблицы в PostgreSQL"""
    conn = create_postgres_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            is_verified BOOLEAN DEFAULT FALSE,
            profile_image VARCHAR(500),
            theme VARCHAR(50) DEFAULT 'dark',
            language VARCHAR(10) DEFAULT 'ru',
            subscription_plan VARCHAR(50) DEFAULT 'basic',
            subscription_expires TIMESTAMP,
            api_key VARCHAR(255) UNIQUE,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            main_site_id INTEGER UNIQUE,
            main_site_api_token VARCHAR(500),
            priority INTEGER DEFAULT 2,
            last_sync TIMESTAMP
        );
    """)

    # Таблица сайтов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            domain VARCHAR(500) PRIMARY KEY,
            url VARCHAR(1000),
            city VARCHAR(255),
            type VARCHAR(100),
            category VARCHAR(255),
            design TEXT,
            ux TEXT,
            design_score INTEGER DEFAULT 0,
            ux_score INTEGER DEFAULT 0,
            checked_at TIMESTAMP,
            rating INTEGER DEFAULT 0,
            needs_redesign BOOLEAN DEFAULT TRUE
        );
    """)

    # Таблица примеров
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS examples (
            id SERIAL PRIMARY KEY,
            url VARCHAR(1000),
            design TEXT,
            ux TEXT,
            is_good BOOLEAN,
            reason TEXT,
            added_at TIMESTAMP
        );
    """)

    # Таблица результатов товаров
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_results (
            id SERIAL PRIMARY KEY,
            url VARCHAR(1000) NOT NULL,
            title VARCHAR(500),
            description TEXT,
            query VARCHAR(500),
            city VARCHAR(255),
            category VARCHAR(255),
            found_at TIMESTAMP,
            analyzed_at TIMESTAMP
        );
    """)

    # Таблица результатов соцсетей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS social_results (
            id SERIAL PRIMARY KEY,
            url VARCHAR(1000) NOT NULL,
            platform VARCHAR(100) NOT NULL,
            title VARCHAR(500),
            description TEXT,
            username VARCHAR(255),
            city VARCHAR(255),
            query VARCHAR(500),
            found_at TIMESTAMP,
            analyzed_at TIMESTAMP,
            design_score INTEGER,
            ux_score INTEGER,
            design_text TEXT,
            ux_text TEXT,
            UNIQUE(url, platform)
        );
    """)

    # Таблица сессий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            session_token VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            ip_address VARCHAR(50),
            user_agent VARCHAR(500)
        );
    """)

    # Таблица восстановлений пароля
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        );
    """)

    # Таблица подписок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            plan VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'active',
            started_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            payment_id VARCHAR(255),
            amount REAL,
            currency VARCHAR(10)
        );
    """)

    # Таблица платежей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
            amount REAL NOT NULL,
            currency VARCHAR(10) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            payment_method VARCHAR(100),
            transaction_id VARCHAR(255),
            created_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP
        );
    """)

    # Таблица загрузок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            file_path VARCHAR(500) NOT NULL,
            file_type VARCHAR(100) NOT NULL,
            original_name VARCHAR(500),
            file_size BIGINT,
            description TEXT,
            is_good_example BOOLEAN,
            created_at TIMESTAMP NOT NULL
        );
    """)

    # Таблица активности
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(255) NOT NULL,
            ip_address VARCHAR(50),
            user_agent VARCHAR(500),
            details TEXT,
            created_at TIMESTAMP NOT NULL
        );
    """)

    # Таблица истории поиска
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            category VARCHAR(255) NOT NULL,
            query VARCHAR(500),
            city VARCHAR(255),
            results_count INTEGER,
            created_at TIMESTAMP NOT NULL
        );
    """)

    # Индексы
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity_log(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_log(created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_user_id ON search_history(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_city ON sites(city);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_url ON social_results(url);")

    conn.commit()
    conn.close()
    print("✅ Таблицы PostgreSQL созданы")

def migrate_table(table_name):
    """Мигрировать таблицу из SQLite в PostgreSQL"""
    print(f"\n📦 Миграция таблицы: {table_name}")
    
    # Получаем данные из SQLite
    sqlite_data = get_sqlite_data(table_name)
    if not sqlite_data:
        print(f"   ⏭ Таблица пуста, пропускаем")
        return 0
    
    print(f"   Найдено {len(sqlite_data)} записей")
    
    # Подключаемся к PostgreSQL
    pg_conn = create_postgres_connection()
    pg_cursor = pg_conn.cursor()
    
    # Получаем схему SQLite
    schema = get_sqlite_schema(table_name)
    columns = [col[1] for col in schema]
    
    # Вставляем данные
    try:
        placeholders = ','.join(['%s'] * len(columns))
        columns_str = ','.join(columns)
        
        query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING;
        """
        
        execute_batch(pg_cursor, query, sqlite_data, page_size=100)
        pg_conn.commit()
        
        print(f"   ✅ Мигрировано {len(sqlite_data)} записей")
        return len(sqlite_data)
        
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        pg_conn.rollback()
        return 0
    finally:
        pg_conn.close()

def verify_migration():
    """Проверить что миграция прошла успешно"""
    print("\n🔍 Проверка миграции...")
    
    # Подключаемся к PostgreSQL
    pg_conn = create_postgres_connection()
    pg_cursor = pg_conn.cursor()
    
    # Проверяем количество записей в каждой таблице
    tables = ['users', 'sites', 'examples', 'product_results', 'social_results']
    
    for table in tables:
        try:
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table};")
            pg_count = pg_cursor.fetchone()[0]
            
            sqlite_data = get_sqlite_data(table)
            sqlite_count = len(sqlite_data) if sqlite_data else 0
            
            status = "✅" if pg_count == sqlite_count else "⚠️"
            print(f"   {status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
            
        except Exception as e:
            print(f"   ❌ {table}: Ошибка проверки - {e}")
    
    pg_conn.close()

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  TISH SEARCH v4 - SQLite to PostgreSQL Migration")
    print("=" * 60)
    print()
    
    # Проверяем что SQLite файл существует
    if not os.path.exists(SQLITE_DB):
        print(f"❌ SQLite база данных не найдена: {SQLITE_DB}")
        return
    
    print(f"📂 SQLite: {SQLITE_DB}")
    print(f"🌐 PostgreSQL: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")
    print()
    
    # Создаём таблицы в PostgreSQL
    create_postgres_tables()
    
    # Получаем список таблиц
    tables = get_sqlite_tables()
    
    # Мигрируем каждую таблицу
    total_migrated = 0
    for table in tables:
        migrated = migrate_table(table)
        total_migrated += migrated
    
    print()
    print(f"🎉 Миграция завершена! Всего перенесено: {total_migrated} записей")
    
    # Проверяем миграцию
    verify_migration()
    
    print()
    print("=" * 60)
    print("  ✅ Готово!")
    print("  Теперь измените DATABASE_URL в .env на PostgreSQL")
    print("=" * 60)

if __name__ == "__main__":
    main()
