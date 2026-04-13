# рџљЂ TISH SEARCH v4 - Production Deployment Guide

РџРѕР»РЅРѕРµ СЂСѓРєРѕРІРѕРґСЃС‚РІРѕ РїРѕ СЂР°Р·РІС‘СЂС‚С‹РІР°РЅРёСЋ РІ РїСЂРѕРґР°РєС€РµРЅРµ РґР»СЏ 20+ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№.

---

## рџ“‹ Р§С‚Рѕ Р±С‹Р»Рѕ СЃРґРµР»Р°РЅРѕ

### вњ… Р РµС€С‘РЅРЅС‹Рµ РїСЂРѕР±Р»РµРјС‹:

1. **РЎРµРєСЂРµС‚С‹ РІС‹РЅРµСЃРµРЅС‹ РІ .env**
   - РђРґРјРёРЅСЃРєРёР№ РїР°СЂРѕР»СЊ Р±РѕР»СЊС€Рµ РЅРµ РІ РєРѕРґРµ
   - SECRET_KEY РіРµРЅРµСЂРёСЂСѓРµС‚СЃСЏ РѕС‚РґРµР»СЊРЅРѕ
   - Р’СЃРµ РЅР°СЃС‚СЂРѕР№РєРё РІ РѕРґРЅРѕРј РјРµСЃС‚Рµ

2. **РЈС‚РµС‡РєР° РїР°РјСЏС‚Рё РёСЃРїСЂР°РІР»РµРЅР°**
   - `online_users_store` С‚РµРїРµСЂСЊ РѕС‡РёС‰Р°РµС‚СЃСЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё
   - Р¤РѕРЅРѕРІС‹Р№ РїРѕС‚РѕРє СѓРґР°Р»СЏРµС‚ stale Р·Р°РїРёСЃРё РєР°Р¶РґСѓСЋ РјРёРЅСѓС‚Сѓ

3. **Production СЃРµСЂРІРµСЂ РЅР°СЃС‚СЂРѕРµРЅ**
   - Waitress WSGI server РІРјРµСЃС‚Рѕ Flask dev
   - Gunicorn РґР»СЏ Linux
   - Eventlet РґР»СЏ WebSocket

4. **PostgreSQL РїРѕРґРґРµСЂР¶РєР° РґРѕР±Р°РІР»РµРЅР°**
   - РЎРєСЂРёРїС‚ РјРёРіСЂР°С†РёРё `migrate_to_postgres.py`
   - Р’СЃРµ С‚Р°Р±Р»РёС†С‹ СЃ РёРЅРґРµРєСЃР°РјРё
   - РџРѕРґРґРµСЂР¶РєР° РІ docker-compose

5. **РЎРёСЃС‚РµРјР° РѕС‡РµСЂРµРґРё Р·Р°РґР°С‡**
   - Celery + Redis РґР»СЏ С„РѕРЅРѕРІС‹С… Р·Р°РґР°С‡
   - РџРµСЂРёРѕРґРёС‡РµСЃРєР°СЏ РѕС‡РёСЃС‚РєР°
   - РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ СЃ РіР»Р°РІРЅС‹Рј СЃР°Р№С‚РѕРј

6. **Docker РєРѕРЅС‚РµР№РЅРµСЂРёР·Р°С†РёСЏ**
   - docker-compose.yml РґР»СЏ РІСЃРµРіРѕ СЃС‚РµРєР°
   - Nginx reverse proxy
   - Healthchecks РґР»СЏ РІСЃРµС… СЃРµСЂРІРёСЃРѕРІ

---

## рџљЂ Р‘С‹СЃС‚СЂС‹Р№ СЃС‚Р°СЂС‚ (Development)

### Windows:

```bash
# 1. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
pip install -r requirements.txt

# 2. РЎРєРѕРїРёСЂСѓР№С‚Рµ .env Рё РЅР°СЃС‚СЂРѕР№С‚Рµ
cp .env.example .env
# РР·РјРµРЅРёС‚Рµ SECRET_KEY Рё ADMIN_PASSWORD

# 3. РРЅРёС†РёР°Р»РёР·РёСЂСѓР№С‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ
python -m modules.system.python.init_app

# 4. Р—Р°РїСѓСЃС‚РёС‚Рµ СЃРµСЂРІРµСЂ
python -m modules.main.python.server
```

РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ Р±Р°С‚РЅРёРє:
```bash
start.bat
```

---

## рџЏ­ Production Deployment

### Р’Р°СЂРёР°РЅС‚ A: Docker (Р РµРєРѕРјРµРЅРґСѓРµС‚СЃСЏ)

```bash
# 1. РЎРєРѕРїРёСЂСѓР№С‚Рµ .env.production
cp .env.production .env

# 2. РР·РјРµРЅРёС‚Рµ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ:
# - SECRET_KEY
# - ADMIN_PASSWORD
# - DATABASE_URL (PostgreSQL)

# 3. Р—Р°РїСѓСЃС‚РёС‚Рµ С‡РµСЂРµР· docker-compose
docker-compose up -d

# 4. РџСЂРѕРІРµСЂСЊС‚Рµ Р»РѕРіРё
docker-compose logs -f web
```

**РЎРµСЂРІРёСЃС‹:**
- `http://localhost:5000` - РџСЂРёР»РѕР¶РµРЅРёРµ
- `http://localhost:5432` - PostgreSQL
- `http://localhost:6379` - Redis

### Р’Р°СЂРёР°РЅС‚ B: Manual Setup (Windows)

```bash
# 1. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ PostgreSQL
# РЎРєР°С‡Р°Р№С‚Рµ СЃ: https://www.postgresql.org/download/windows/

# 2. РЎРѕР·РґР°Р№С‚Рµ Р±Р°Р·Сѓ РґР°РЅРЅС‹С…
psql -U postgres
CREATE DATABASE tish_db;
CREATE USER tish_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tish_db TO tish_user;

# 3. РќР°СЃС‚СЂРѕР№С‚Рµ .env
cp .env.production .env
# РР·РјРµРЅРёС‚Рµ DATABASE_URL РЅР° PostgreSQL

# 4. РњРёРіСЂРёСЂСѓР№С‚Рµ РґР°РЅРЅС‹Рµ (РµСЃР»Рё РµСЃС‚СЊ SQLite)
python -m modules.migrations.python.migrate_to_postgres

# 5. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
pip install -r requirements.txt

# 6. РРЅРёС†РёР°Р»РёР·РёСЂСѓР№С‚Рµ
python -m modules.system.python.init_app

# 7. Р—Р°РїСѓСЃС‚РёС‚Рµ production СЃРµСЂРІРµСЂ
python -m modules.system.python.run
```

РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ Р±Р°С‚РЅРёРє:
```bash
start_production.bat
```

### Р’Р°СЂРёР°РЅС‚ C: Manual Setup (Linux)

```bash
# 1. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
sudo apt update
sudo apt install postgresql redis-server nginx python3-pip

# 2. РЎРѕР·РґР°Р№С‚Рµ Р±Р°Р·Сѓ РґР°РЅРЅС‹С…
sudo -u postgres psql
CREATE DATABASE tish_db;
CREATE USER tish_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tish_db TO tish_user;

# 3. РќР°СЃС‚СЂРѕР№С‚Рµ .env
cp .env.production .env

# 4. РњРёРіСЂРёСЂСѓР№С‚Рµ РґР°РЅРЅС‹Рµ
python3 -m modules.migrations.python.migrate_to_postgres

# 5. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Python Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
pip3 install -r requirements.txt

# 6. РРЅРёС†РёР°Р»РёР·РёСЂСѓР№С‚Рµ
python3 -m modules.system.python.init_app

# 7. Р—Р°РїСѓСЃС‚РёС‚Рµ С‡РµСЂРµР· Gunicorn
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 modules.main.python.app:app

# РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ docker-compose (РїСЂРµРґРїРѕС‡С‚РёС‚РµР»СЊРЅРѕ)
docker-compose up -d
```

---

## рџ”§ РќР°СЃС‚СЂРѕР№РєР° PostgreSQL

### РЎРєСЂРёРїС‚ РјРёРіСЂР°С†РёРё:

```bash
# РќР°СЃС‚СЂРѕР№С‚Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ
export SQLITE_DB=tish_data.db
export PG_HOST=localhost
export PG_PORT=5432
export PG_DATABASE=tish_db
export PG_USER=tish_user
export PG_PASSWORD=your_password

# Р—Р°РїСѓСЃС‚РёС‚Рµ РјРёРіСЂР°С†РёСЋ
python -m modules.migrations.python.migrate_to_postgres
```

### РџСЂРѕРІРµСЂРєР° РјРёРіСЂР°С†РёРё:

```bash
# РџРѕРґРєР»СЋС‡РёС‚РµСЃСЊ Рє PostgreSQL
psql -U tish_user -d tish_db

# РџСЂРѕРІРµСЂСЊС‚Рµ С‚Р°Р±Р»РёС†С‹
\dt

# РџСЂРѕРІРµСЂСЊС‚Рµ РґР°РЅРЅС‹Рµ
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM sites;
```

---

## рџ“Љ РњРѕРЅРёС‚РѕСЂРёРЅРі

### Celery Flower (Web UI РґР»СЏ Celery):

```bash
# РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Flower
pip install flower

# Р—Р°РїСѓСЃС‚РёС‚Рµ
celery -A modules.system.python.celery_worker:celery_app flower
```

РћС‚РєСЂРѕР№С‚Рµ `http://localhost:5555`

### Prometheus + Grafana:

РЎРѕР·РґР°Р№С‚Рµ `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'tish_search'
    static_configs:
      - targets: ['localhost:5000']
```

---

## рџ”’ Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ

### Checklist РїРµСЂРµРґ Р·Р°РїСѓСЃРєРѕРј:

- [ ] **SECRET_KEY** РёР·РјРµРЅС‘РЅ РЅР° СѓРЅРёРєР°Р»СЊРЅС‹Р№
- [ ] **ADMIN_PASSWORD** РёР·РјРµРЅС‘РЅ РЅР° СЃР»РѕР¶РЅС‹Р№ РїР°СЂРѕР»СЊ (РјРёРЅРёРјСѓРј 16 СЃРёРјРІРѕР»РѕРІ)
- [ ] **DATABASE_URL** РЅР°СЃС‚СЂРѕРµРЅ РЅР° PostgreSQL
- [ ] **SSL СЃРµСЂС‚РёС„РёРєР°С‚** СѓСЃС‚Р°РЅРѕРІР»РµРЅ (Let's Encrypt)
- [ ] **Firewall** РЅР°СЃС‚СЂРѕРµРЅ (С‚РѕР»СЊРєРѕ 80, 443, 22)
- [ ] **Rate limiting** РЅР°СЃС‚СЂРѕРµРЅ РІ Nginx
- [ ] **Р РµР·РµСЂРІРЅРѕРµ РєРѕРїРёСЂРѕРІР°РЅРёРµ** Р‘Р” РЅР°СЃС‚СЂРѕРµРЅРѕ
- [ ] **РњРѕРЅРёС‚РѕСЂРёРЅРі** (Sentry, Prometheus) РЅР°СЃС‚СЂРѕРµРЅ

### Р“РµРЅРµСЂР°С†РёСЏ SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### SSL СЃРµСЂС‚РёС„РёРєР°С‚ (Let's Encrypt):

```bash
# РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Certbot
sudo apt install certbot python3-certbot-nginx

# РџРѕР»СѓС‡РёС‚Рµ СЃРµСЂС‚РёС„РёРєР°С‚
sudo certbot --nginx -d your-domain.com

# РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРѕРµ РѕР±РЅРѕРІР»РµРЅРёРµ
sudo certbot renew --dry-run
```

---

## рџ“¦ Р РµР·РµСЂРІРЅРѕРµ РєРѕРїРёСЂРѕРІР°РЅРёРµ

### PostgreSQL Backup:

```bash
# РЎРѕР·РґР°С‚СЊ backup
pg_dump -U tish_user tish_db > backup_$(date +%Y%m%d).sql

# Р’РѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ backup
psql -U tish_user tish_db < backup_20260406.sql
```

### РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРёР№ backup (cron):

```bash
# РћС‚РєСЂРѕР№С‚Рµ crontab
crontab -e

# Р”РѕР±Р°РІСЊС‚Рµ РµР¶РµРґРЅРµРІРЅС‹Р№ backup РІ 3 РЅРѕС‡Рё
0 3 * * * pg_dump -U tish_user tish_db > /backups/tish_$(date +\%Y\%m\%d).sql
```

---

## рџљЁ Troubleshooting

### РћС€РёР±РєР°: "database is locked"

**РџСЂРёС‡РёРЅР°:** SQLite РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ РјРЅРѕРіРѕРїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєСѓСЋ Р·Р°РїРёСЃСЊ.

**Р РµС€РµРЅРёРµ:** РњРёРіСЂРёСЂСѓР№С‚Рµ РЅР° PostgreSQL:
```bash
python -m modules.migrations.python.migrate_to_postgres
```

### РћС€РёР±РєР°: "Permission denied: reports/social_results.xlsx"

**РџСЂРёС‡РёРЅР°:** Р¤Р°Р№Р» Excel РѕС‚РєСЂС‹С‚ РІ РґСЂСѓРіРѕР№ РїСЂРѕРіСЂР°РјРјРµ.

**Р РµС€РµРЅРёРµ:** Р—Р°РєСЂРѕР№С‚Рµ Excel РёР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РѕС‚РґРµР»СЊРЅСѓСЋ РїР°РїРєСѓ РґР»СЏ РѕС‚С‡С‘С‚РѕРІ.

### РћС€РёР±РєР°: "Too many connections"

**РџСЂРёС‡РёРЅР°:** РџСЂРµРІС‹С€РµРЅ Р»РёРјРёС‚ РїРѕРґРєР»СЋС‡РµРЅРёР№ Рє PostgreSQL.

**Р РµС€РµРЅРёРµ:** РЈРІРµР»РёС‡СЊС‚Рµ `max_connections` РІ `postgresql.conf`:
```
max_connections = 200
```

### РћС€РёР±РєР°: "Worker lost"

**РџСЂРёС‡РёРЅР°:** Celery worker СѓРїР°Р» РёР·-Р·Р° РЅРµС…РІР°С‚РєРё РїР°РјСЏС‚Рё.

**Р РµС€РµРЅРёРµ:** РЈРІРµР»РёС‡СЊС‚Рµ RAM РёР»Рё СѓРјРµРЅСЊС€РёС‚Рµ `worker_concurrency`:
```bash
celery -A modules.system.python.celery_worker:celery_app worker --concurrency=2
```

---

## рџ“€ РњР°СЃС€С‚Р°Р±РёСЂРѕРІР°РЅРёРµ

### Р“РѕСЂРёР·РѕРЅС‚Р°Р»СЊРЅРѕРµ РјР°СЃС€С‚Р°Р±РёСЂРѕРІР°РЅРёРµ:

```yaml
# docker-compose.override.yml
services:
  web:
    replicas: 3
  
  celery:
    replicas: 5
```

### Р’РµСЂС‚РёРєР°Р»СЊРЅРѕРµ РјР°СЃС€С‚Р°Р±РёСЂРѕРІР°РЅРёРµ:

Р РµРєРѕРјРµРЅРґСѓРµРјС‹Рµ СЂРµСЃСѓСЂСЃС‹ РґР»СЏ 20+ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№:

| РљРѕРјРїРѕРЅРµРЅС‚ | РњРёРЅРёРјСѓРј | Р РµРєРѕРјРµРЅРґСѓРµС‚СЃСЏ |
|-----------|---------|---------------|
| CPU | 4 СЏРґСЂР° | 8 СЏРґРµСЂ |
| RAM | 8 GB | 16 GB |
| SSD | 100 GB | 500 GB NVMe |
| GPU | - | NVIDIA RTX 3060 12GB |

---

## рџ“ћ РџРѕРґРґРµСЂР¶РєР°

- **Telegram:** @tishteam_support
- **Email:** support@tishteam.space
- **Р”РѕРєСѓРјРµРЅС‚Р°С†РёСЏ:** /docs

---

## пёЏ Roadmap

### v4.1 (Q2 2026)
- [ ] YooKassa/Stripe РёРЅС‚РµРіСЂР°С†РёСЏ
- [ ] Email-СЂР°СЃСЃС‹Р»РєР° РѕС‚С‡С‘С‚РѕРІ
- [ ] Р Р°СЃС€РёСЂРµРЅРЅР°СЏ Р°РЅР°Р»РёС‚РёРєР°
- [ ] Mobile РїСЂРёР»РѕР¶РµРЅРёРµ

### v4.2 (Q3 2026)
- [ ] РњСѓР»СЊС‚РёСЏР·С‹С‡РЅС‹Р№ AI-Р°РЅР°Р»РёР·
- [ ] Р­РєСЃРїРѕСЂС‚ РІ PDF
- [ ] РљРѕРјР°РЅРґРЅР°СЏ СЂР°Р±РѕС‚Р°
- [ ] Webhook РёРЅС‚РµРіСЂР°С†РёРё

---

**Р“РѕС‚РѕРІРѕ! рџЋ‰**

Р’Р°С€ TISH SEARCH v4 РіРѕС‚РѕРІ Рє РїСЂРѕРґР°РєС€РµРЅСѓ!

