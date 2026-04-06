# TISH SEARCH v4 - Production Docker Image
FROM python:3.11-slim

# Устанавливаем системные зависимости + wget/gnupg для Playwright
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Playwright браузеры С ЗАВИСИМОСТЯМИ
# КРИТИЧНО: --with-deps устанавливает все системные библиотеки для Chromium
RUN npx playwright install --with-deps chromium

# Копируем код приложения
COPY . .

# Создаём необходимые директории
RUN mkdir -p reports screenshots uploads static/images

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production

# Открываем порт
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Запускаем приложение через run.py
CMD ["python", "run.py"]
