# TISH SEARCH v4 - Production Docker Image
FROM python:3.11-slim

# РЈСЃС‚Р°РЅР°РІР»РёРІР°РµРј СЃРёСЃС‚РµРјРЅС‹Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# РЎРѕР·РґР°С‘Рј СЂР°Р±РѕС‡СѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ
WORKDIR /app

# РљРѕРїРёСЂСѓРµРј requirements Рё СѓСЃС‚Р°РЅР°РІР»РёРІР°РµРј Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# РЈСЃС‚Р°РЅР°РІР»РёРІР°РµРј Playwright Р±СЂР°СѓР·РµСЂС‹ РЎ СЃРёСЃС‚РµРјРЅС‹РјРё Р·Р°РІРёСЃРёРјРѕСЃС‚СЏРјРё
# РљР РРўРР§РќРћ: --with-deps СѓСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ РІСЃРµ Р±РёР±Р»РёРѕС‚РµРєРё РґР»СЏ Chromium
RUN playwright install --with-deps chromium

# РљРѕРїРёСЂСѓРµРј РєРѕРґ РїСЂРёР»РѕР¶РµРЅРёСЏ
COPY . .

# РЎРѕР·РґР°С‘Рј РЅРµРѕР±С…РѕРґРёРјС‹Рµ РґРёСЂРµРєС‚РѕСЂРёРё
RUN mkdir -p reports screenshots uploads static/images

# РЈСЃС‚Р°РЅР°РІР»РёРІР°РµРј РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production

# РћС‚РєСЂС‹РІР°РµРј РїРѕСЂС‚
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Р—Р°РїСѓСЃРєР°РµРј РїСЂРёР»РѕР¶РµРЅРёРµ С‡РµСЂРµР· modules.system.python.run
CMD ["python", "-m", "modules.system.python.run"]

