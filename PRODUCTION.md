# 🚀 TISH SEARCH v4 - Production Deployment Guide

Полное руководство по развёртыванию в продакшене для 20+ пользователей.

---

## 📋 Что было сделано

### ✅ Решённые проблемы:

1. **Секреты вынесены в .env**
   - Админский пароль больше не в коде
   - SECRET_KEY генерируется отдельно
   - Все настройки в одном месте

2. **Утечка памяти исправлена**
   - `online_users_store` теперь очищается автоматически
   - Фоновый поток удаляет stale записи каждую минуту

3. **Production сервер настроен**
   - Waitress WSGI server вместо Flask dev
   - Gunicorn для Linux
   - Eventlet для WebSocket

4. **PostgreSQL поддержка добавлена**
   - Скрипт миграции `migrate_to_postgres.py`
   - Все таблицы с индексами
   - Поддержка в docker-compose

5. **Система очереди задач**
   - Celery + Redis для фоновых задач
   - Периодическая очистка
   - Синхронизация с главным сайтом

6. **Docker контейнеризация**
   - docker-compose.yml для всего стека
   - Nginx reverse proxy
   - Healthchecks для всех сервисов

---

## 🚀 Быстрый старт (Development)

### Windows:

```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Скопируйте .env и настройте
cp .env.example .env
# Измените SECRET_KEY и ADMIN_PASSWORD

# 3. Инициализируйте приложение
python init_app.py

# 4. Запустите сервер
python server.py
```

Или используйте батник:
```bash
start.bat
```

---

## 🏭 Production Deployment

### Вариант A: Docker (Рекомендуется)

```bash
# 1. Скопируйте .env.production
cp .env.production .env

# 2. Измените обязательные переменные:
# - SECRET_KEY
# - ADMIN_PASSWORD
# - DATABASE_URL (PostgreSQL)

# 3. Запустите через docker-compose
docker-compose up -d

# 4. Проверьте логи
docker-compose logs -f web
```

**Сервисы:**
- `http://localhost:5000` - Приложение
- `http://localhost:5432` - PostgreSQL
- `http://localhost:6379` - Redis

### Вариант B: Manual Setup (Windows)

```bash
# 1. Установите PostgreSQL
# Скачайте с: https://www.postgresql.org/download/windows/

# 2. Создайте базу данных
psql -U postgres
CREATE DATABASE tish_db;
CREATE USER tish_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tish_db TO tish_user;

# 3. Настройте .env
cp .env.production .env
# Измените DATABASE_URL на PostgreSQL

# 4. Мигрируйте данные (если есть SQLite)
python migrate_to_postgres.py

# 5. Установите зависимости
pip install -r requirements.txt

# 6. Инициализируйте
python init_app.py

# 7. Запустите production сервер
python run.py
```

Или используйте батник:
```bash
start_production.bat
```

### Вариант C: Manual Setup (Linux)

```bash
# 1. Установите зависимости
sudo apt update
sudo apt install postgresql redis-server nginx python3-pip

# 2. Создайте базу данных
sudo -u postgres psql
CREATE DATABASE tish_db;
CREATE USER tish_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tish_db TO tish_user;

# 3. Настройте .env
cp .env.production .env

# 4. Мигрируйте данные
python3 migrate_to_postgres.py

# 5. Установите Python зависимости
pip3 install -r requirements.txt

# 6. Инициализируйте
python3 init_app.py

# 7. Запустите через Gunicorn
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 server:app

# Или используйте docker-compose (предпочтительно)
docker-compose up -d
```

---

## 🔧 Настройка PostgreSQL

### Скрипт миграции:

```bash
# Настройте переменные окружения
export SQLITE_DB=tish_data.db
export PG_HOST=localhost
export PG_PORT=5432
export PG_DATABASE=tish_db
export PG_USER=tish_user
export PG_PASSWORD=your_password

# Запустите миграцию
python migrate_to_postgres.py
```

### Проверка миграции:

```bash
# Подключитесь к PostgreSQL
psql -U tish_user -d tish_db

# Проверьте таблицы
\dt

# Проверьте данные
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM sites;
```

---

## 📊 Мониторинг

### Celery Flower (Web UI для Celery):

```bash
# Установите Flower
pip install flower

# Запустите
celery -A celery_worker flower
```

Откройте `http://localhost:5555`

### Prometheus + Grafana:

Создайте `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'tish_search'
    static_configs:
      - targets: ['localhost:5000']
```

---

## 🔒 Безопасность

### Checklist перед запуском:

- [ ] **SECRET_KEY** изменён на уникальный
- [ ] **ADMIN_PASSWORD** изменён на сложный пароль (минимум 16 символов)
- [ ] **DATABASE_URL** настроен на PostgreSQL
- [ ] **SSL сертификат** установлен (Let's Encrypt)
- [ ] **Firewall** настроен (только 80, 443, 22)
- [ ] **Rate limiting** настроен в Nginx
- [ ] **Резервное копирование** БД настроено
- [ ] **Мониторинг** (Sentry, Prometheus) настроен

### Генерация SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### SSL сертификат (Let's Encrypt):

```bash
# Установите Certbot
sudo apt install certbot python3-certbot-nginx

# Получите сертификат
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo certbot renew --dry-run
```

---

## 📦 Резервное копирование

### PostgreSQL Backup:

```bash
# Создать backup
pg_dump -U tish_user tish_db > backup_$(date +%Y%m%d).sql

# Восстановить backup
psql -U tish_user tish_db < backup_20260406.sql
```

### Автоматический backup (cron):

```bash
# Откройте crontab
crontab -e

# Добавьте ежедневный backup в 3 ночи
0 3 * * * pg_dump -U tish_user tish_db > /backups/tish_$(date +\%Y\%m\%d).sql
```

---

## 🚨 Troubleshooting

### Ошибка: "database is locked"

**Причина:** SQLite не поддерживает многопользовательскую запись.

**Решение:** Мигрируйте на PostgreSQL:
```bash
python migrate_to_postgres.py
```

### Ошибка: "Permission denied: reports/social_results.xlsx"

**Причина:** Файл Excel открыт в другой программе.

**Решение:** Закройте Excel или используйте отдельную папку для отчётов.

### Ошибка: "Too many connections"

**Причина:** Превышен лимит подключений к PostgreSQL.

**Решение:** Увеличьте `max_connections` в `postgresql.conf`:
```
max_connections = 200
```

### Ошибка: "Worker lost"

**Причина:** Celery worker упал из-за нехватки памяти.

**Решение:** Увеличьте RAM или уменьшите `worker_concurrency`:
```bash
celery -A celery_worker worker --concurrency=2
```

---

## 📈 Масштабирование

### Горизонтальное масштабирование:

```yaml
# docker-compose.override.yml
services:
  web:
    replicas: 3
  
  celery:
    replicas: 5
```

### Вертикальное масштабирование:

Рекомендуемые ресурсы для 20+ пользователей:

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| CPU | 4 ядра | 8 ядер |
| RAM | 8 GB | 16 GB |
| SSD | 100 GB | 500 GB NVMe |
| GPU | - | NVIDIA RTX 3060 12GB |

---

## 📞 Поддержка

- **Telegram:** @tishteam_support
- **Email:** support@tishteam.space
- **Документация:** /docs

---

## ️ Roadmap

### v4.1 (Q2 2026)
- [ ] YooKassa/Stripe интеграция
- [ ] Email-рассылка отчётов
- [ ] Расширенная аналитика
- [ ] Mobile приложение

### v4.2 (Q3 2026)
- [ ] Мультиязычный AI-анализ
- [ ] Экспорт в PDF
- [ ] Командная работа
- [ ] Webhook интеграции

---

**Готово! 🎉**

Ваш TISH SEARCH v4 готов к продакшену!
