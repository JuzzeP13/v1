# 🏗️ Архитектура модуля Social Search в TISH Search v4

## Диаграмма потока данных

```
┌─────────────────────────┐
│   Браузер пользователя  │
│  (localhost:5000)       │
└────────────┬────────────┘
             │
      ┌──────┴──────┐
      │ WebSocket   │
      │ (Socket.IO) │
      ▼             
┌─────────────────────────────────────┐
│  Flask + Flask-SocketIO (server.py) │
│  @socketio.on("search_social")      │
│  process_social_search()            │
└──────┬──────────┬─────────┬──────────┘
       │          │         │
       ▼          ▼         ▼
  ┌──────────┐ ┌────────┐ ┌─────────────┐
  │  ПОИСК   │ │  AI    │ │ СОХРАНЕНИЕ  │
  │          │ │АНАЛИЗ  │ │             │
  │DuckDuckGo│→│ Ollama │→│ БД + Excel  │
  └──────────┘ └────────┘ │ + WebSocket │
                           └─────────────┘
```

---

## 1. Модуль ПОИСКА (social_search.py)

### Функции поиска по платформам

```python
search_social_media(query, platform, city)
├─ search_youtube_channels(query, max_results, city)
│  └─ build_social_queries() → расширенный набор запросов
│  └─ DuckDuckGo API → найденные каналы
│
├─ search_instagram_profiles(query, max_results, city)
│  └─ build_social_queries()
│  └─ DuckDuckGo API → найденные профили
│
└─ search_twitter_accounts(query, max_results, city)
   └─ build_social_queries()
   └─ DuckDuckGo API → найденные аккаунты
```

### Фильтрация результатов

- **normalize_social_url()** — приводит URL к стандартному формату
- **is_valid_social_url()** — проверяет что это действительно профиль
- **is_low_quality_social_result()** — отсекает логины, посты, видео
- **extract_username()** — извлекает @username или channel_id

### Возвращаемые данные

```json
[
  {
    "url": "https://www.youtube.com/channel/UCxxxxx",
    "title": "Channel Name",
    "description": "Channel description from search",
    "username": "@channel_id",
    "channel_id": "UCxxxxx",
    "platform": "youtube",
    "query": "web design",
    "found_at": "2026-04-05T10:00:00"
  }
]
```

---

## 2. Модуль AI АНАЛИЗА (server.py)

### Функция take_screenshot()

```python
take_screenshot(url)
├─ Playwright API
├─ Раскрывает URL в браузере (1280x800)
├─ Ждёт загрузки страницы (timeout 8)
└─ Возвращает скриншот в формате base64
```

### Функция analyze_social_profile()

```python
analyze_social_profile(platform, url, screenshot_b64)
├─ Отправляет запрос в Ollama Vision API
├─ Модель: qwen3-vl (или llava)
├─ Промпт: "Оцени дизайн и UX профила..."
└─ Парсит ответ:
   ├─ design_score (0-10)
   ├─ ux_score (0-10)
   ├─ design_text (описание дизайна)
   └─ ux_text (описание UX)
```

### Запрос к Ollama

```json
POST http://localhost:11434/api/chat
{
  "model": "qwen3-vl",
  "messages": [{
    "role": "user",
    "content": "Проанализируй скриншот...",
    "images": ["base64_image_data"]
  }],
  "stream": false,
  "options": {"temperature": 0.3}
}
```

---

## 3. Модуль СОХРАНЕНИЯ (server.py)

### process_social_search() — Главный flow

```
1. Поиск профилей (social_search.search_social_media)
   └─ [5-10 результатов]

2. Для каждого профиля:
   ├─ Скриншот (Playwright)
   ├─ AI анализ (Ollama vision)
   └─ Добавить design_score, ux_score

3. Сохранение в БД:
   ├─ INSERT INTO social_results (...)
   └─ При дубликате → UPDATE запись

4. Экспорт в Excel:
   ├─ Открыть/создать reports/social_results.xlsx
   ├─ Добавить строки в лист "SocialMedia"
   └─ Сохранить файл

5. WebSocket трансляция:
   ├─ socketio.emit("result", {...})
   └─ Браузер получает результаты в реальном времени
```

---

## 4. Хранилище данных: БД SQLite

### Таблица `social_results`

```sql
CREATE TABLE social_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT NOT NULL,              -- https://...
    platform            TEXT NOT NULL,              -- youtube|instagram|twitter
    title               TEXT,                       -- Название профила
    description         TEXT,                       -- Описание из поиска
    username            TEXT,                       -- @username или channel_id
    city                TEXT,                       -- Город поиска
    query               TEXT,                       -- Поисковый запрос
    found_at            TEXT,                       -- ISO дата поиска
    analyzed_at         TEXT,                       -- ISO дата анализа
    design_score        INTEGER,                    -- AI оценка 0-10 ⭐
    ux_score            INTEGER,                    -- AI оценка 0-10 ⭐
    design_text         TEXT,                       -- Описание дизайна ⭐
    ux_text             TEXT,                       -- Описание UX ⭐
    UNIQUE(url, platform)
)
```

### Пример записи

```
url: https://www.youtube.com/@webdesignstudio
platform: youtube
title: Web Design Studio
description: Learn modern web design
username: @webdesignstudio
city: Москва
query: web design курс
design_score: 8
ux_score: 9
design_text: "Современный миналистичный дизайн с хорошей цветовой схемой"
ux_text: "Интуитивная навигация по каналам и плейлистам"
found_at: 2026-04-05T10:00:00
analyzed_at: 2026-04-05T10:15:00
```

---

## 5. Экспорт в Excel

### Файл: `reports/social_results.xlsx`

**Лист: "SocialMedia"**

| # | Платформа | URL | Название | Описание | Username/ID | Дизайн | UX | Примечание | Город | Запрос | Дата |
|---|-----------|-----|----------|----------|-------------|--------|----|---------|----|--------|------|
| 1 | YOUTUBE | https://... | Channel X | ... | @user | 8 | 9 | Modern design... | Москва | web design | 2026-04-05 |

**Форматирование:**
- Заголовок платформы: красный фон (CC0000)
- Каждая платформа: своя цветная строка (YouTube=FFD6D6, Instagram=FFE8F0, Twitter=D6E8FF)
- Высота строк: 60px
- Текст с переносом (wrap)
- Границы между ячейками

---

## 6. WebSocket Трансляция

### Событие отправляемое клиенту

```javascript
socket.on('result', function(data) {
  // data структура
  {
    url: "https://youtube.com/...",
    type: "Соцсеть",
    category: "youtube",            // платформа
    design: "Дизайн: 8/10",          // оценка
    ux: "UX: 9/10",                  // оценка
    design_text: "Modern minimalist design...",
    ux_text: "Intuitive navigation...",
    index: 1                         // номер в очереди
  }
});
```

### Прогресс трансляция

```javascript
socket.on('status', function(data) {
  // data структура
  {
    message: "🔍 Ищу на youtube...",
    type: "info",    // info|success|warn|error
    progress: "2/5"  // (опционально)
  }
});
```

---

## 7. Файлы проекта

| Файл | Функция |
|------|---------|
| `social_search.py` | Поиск профилей в соцсетях (DuckDuckGo API) |
| `server.py` (main) | Flask приложение, маршруты, process_social_search() |
| `server.py` (take_screenshot) | Playwright скриншоты |
| `server.py` (analyze_social_profile) | Ollama vision анализ |
| `server.py` (save_social_to_excel) | Экспорт в Excel |
| `migrate_social_results.py` | Миграция БД (добавить колонки) |
| `tish_data.db` | SQLite база данных |
| `reports/social_results.xlsx` | Excel файл с результатами |

---

## 8. Зависимости и внешние сервисы

```
Python библиотеки:
├─ duckduckgo-search  → DuckDuckGo API (поиск)
├─ playwright         → Скриншоты (браузер)
├─ requests           → HTTP запросы
├─ openpyxl           → Excel файлы
└─ sqlite3            → БД

Внешние сервисы:
├─ DuckDuckGo         → Поиск (бесплатно)
├─ Ollama             → Vision модели (локально, http://localhost:11434)
│  └─ Модель: qwen3-vl или llava
└─ Браузер (Chromium) → Playwright за скриншотами
```

---

## 9. Примеры использования

### Получить результаты из БД

```python
import sqlite3

conn = sqlite3.connect('tish_data.db')

# Все YouTube каналы
youtube = conn.execute("""
    SELECT url, design_score, ux_score FROM social_results 
    WHERE platform='youtube' 
    ORDER BY design_score DESC LIMIT 10
""").fetchall()

for url, design, ux in youtube:
    print(f"{url}: Дизайн={design}/10, UX={ux}/10")

conn.close()
```

### По городу и платформе

```python
moscow_instagram = conn.execute("""
    SELECT url, title, design_text FROM social_results 
    WHERE city='Москва' AND platform='instagram' 
    ORDER BY analyzed_at DESC
""").fetchall()
```

### Лучшие профили (средняя оценка > 7)

```python
best = conn.execute("""
    SELECT url, platform, 
           ROUND((design_score + ux_score) / 2.0, 1) as avg_score
    FROM social_results 
    WHERE (design_score + ux_score) / 2.0 > 7
    ORDER BY avg_score DESC
""").fetchall()
```

---

## 10. Отладка

### Проверить Ollama

```bash
curl http://localhost:11434/api/tags
# Должна быть модель "qwen3-vl" или "llava"
```

### Посмотреть результаты в консоль

```bash
python -c "
import sqlite3
conn = sqlite3.connect('tish_data.db')
rows = conn.execute('SELECT * FROM social_results LIMIT 5').fetchall()
for row in rows:
    print(row)
"
```

### Проверить Excel

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook('reports/social_results.xlsx')
print('Листы:', wb.sheetnames)
print('Строк в SocialMedia:', wb['SocialMedia'].max_row)
"
```

---

## Резюме

**TISH Search v4 — Social Search Module:**

- ✅ Поиск профилей в 3 соцсетях (YouTube, Instagram, X)
- ✅ AI анализ дизайна и UX через Ollama vision
- ✅ Сохранение в БД SQLite с оценками
- ✅ Экспорт в Excel с форматированием
- ✅ WebSocket трансляция прогресса в браузер
- ✅ Фильтрация и нормализация URL
- ✅ Миграция БД для совместимости

**Результаты доступны в 3 местах:**
1. БД (для аналитики и экспорта)
2. Excel (для отчётов и презентаций)
3. Браузер (для просмотра в реальном времени)
