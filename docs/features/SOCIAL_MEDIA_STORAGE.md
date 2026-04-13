# 📱 Где сохраняются результаты поиска по соцсетям?

## 🎯 Краткий ответ

Результаты поиска по соцсетям (YouTube, Instagram, X/Twitter) сохраняются в **трёх местах**:

1. **БД SQLite** (`tish_data.db`, таблица `social_results`)
2. **Excel файл** (`reports/social_results.xlsx`, лист "SocialMedia")
3. **Оперативная память** (в переменной `state["results"]`)

---

## 📂 Подробное описание

### 1. БД SQLite — Таблица `social_results`

**Расположение:** `tish_data.db`  
**Таблица:** `social_results`

**Схема таблицы:**
```sql
CREATE TABLE social_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    platform TEXT NOT NULL,          -- 'youtube', 'instagram', 'twitter'
    title TEXT,                      -- Название профиля/канала
    description TEXT,                -- Описание из поиска
    username TEXT,                   -- Username или channel_id
    city TEXT,                       -- Город поиска
    query TEXT,                      -- Поисковый запрос
    found_at TEXT,                   -- ISO дата когда найден
    analyzed_at TEXT,                -- ISO дата когда проанализирован
    design_score INTEGER,            -- AI оценка дизайна (0-10) ⭐
    ux_score INTEGER,                -- AI оценка UX (0-10) ⭐
    design_text TEXT,                -- Текстовая оценка дизайна ⭐
    ux_text TEXT,                    -- Текстовая оценка UX ⭐
    UNIQUE(url, platform)            -- Нет дубликатов
)
```

**Как сохраняется:**
```python
# В server.py, функция process_social_search() (строка 2206)
INSERT INTO social_results 
(url, platform, title, description, username, city, query, found_at, analyzed_at, 
 design_score, ux_score, design_text, ux_text)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

### 2. Excel файл — Лист "SocialMedia"

**Расположение:** `reports/social_results.xlsx`  
**Лист:** "SocialMedia"

**Столбцы:**
| # | Платформа | URL | Название | Описание | Username/ID | Дизайн | UX | Примечание | Город | Запрос | Дата |
|---|-----------|-----|----------|----------|-------------|--------|----|---------|----|--------|------|
| №п/п | youtube/instagram/twitter | Profile URL | Заголовок | Описание | @username | 0-10 ⭐ | 0-10 ⭐ | design_text + ux_text | Город | Query | YYYY-MM-DD |

**Как сохраняется:**
```python
# В server.py, функция save_social_to_excel() (строка 2270)
# Загружает существующий файл или создаёт новый
# Добавляет новые строки с результатами
# Применяет форматирование (цвета, шрифты, границы)
wb.save(filepath)
```

### 3. Оперативная память (WebSocket)

**В переменной:** `state["results"]`  
**Как отправляется клиенту** (в реальном времени):

```python
socketio.emit("result", {
    "url": result.get("url", ""),
    "type": "Соцсеть",
    "category": result.get("platform", "social"),
    "design": f"Дизайн: {result.get('design_score', 5)}/10",
    "ux": f"UX: {result.get('ux_score', 5)}/10",
    "design_text": result.get("design_text", "")[:200],
    "ux_text": result.get("ux_text", "")[:200],
    "index": idx
})
```

---

## 🔄 Процесс сохранения (Flow)

```
1. ПОИСК в DuckDuckGo
   └─→ search_social_media() в social_search.py
   └─→ Возвращает список профилей (url, title, description, username, etc.)

2. AI АНАЛИЗ каждого профиля
   └─→ take_screenshot(url) — скриншот профиля
   └─→ analyze_social_profile(platform, url, screenshot_b64)
   └─→ Ollama vision-модель анализирует изображение
   └─→ Парсит ответ: design_score, ux_score, design_text, ux_text

3. СОХРАНЕНИЕ в БД (INSERT или UPDATE)
   └─→ con.execute(INSERT INTO social_results...)
   └─→ Если дубликат (url + platform) → UPDATE record

4. СОХРАНЕНИЕ в Excel
   └─→ save_social_to_excel(all_results)
   └─→ Открывает/создаёт reports/social_results.xlsx
   └─→ Добавляет новые строки с результатами

5. ОТПРАВКА клиенту (WebSocket)
   └─→ socketio.emit("result", {...})
   └─→ Клиент видит результаты в реальном времени
```

---

## 📊 Пример запроса данных из БД

```python
import sqlite3

# Получить все YouTube каналы
conn = sqlite3.connect('tish_data.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Все результаты
results = cursor.execute(
    "SELECT * FROM social_results WHERE platform='youtube' ORDER BY design_score DESC"
).fetchall()

# По городу и платформе
results = cursor.execute(
    "SELECT * FROM social_results WHERE city='Москва' AND platform='instagram' ORDER BY analyzed_at DESC"
).fetchall()

for row in results:
    print(f"{row['url']}: Дизайн={row['design_score']}, UX={row['ux_score']}")

conn.close()
```

---

## ⭐ Где AI оценки (design_score, ux_score)?

**Ответ:** В БД, колонки:
- `design_score` — оценка дизайна от 0 до 10
- `ux_score` — оценка UX от 0 до 10
- `design_text` — текстовое описание дизайна
- `ux_text` — текстовое описание UX

**Эти значения:**
- ✅ Сохраняются в БД
- ✅ Экспортируются в Excel
- ✅ Отправляются клиенту через WebSocket
- ✅ Получены от Ollama vision-модели (qwen3-vl или llava)

---

## 🔍 Отладка: Посмотреть сохранённые результаты

```python
# 1. В БД через Python
import sqlite3
conn = sqlite3.connect('tish_data.db')
count = conn.execute("SELECT COUNT(*) FROM social_results").fetchone()[0]
print(f"Всего результатов в БД: {count}")

# 2. В Excel
# Откройте reports/social_results.xlsx в LibreOffice/Excel
# Список "SocialMedia" содержит все результаты

# 3. Во время выполнения
# Смотрите консоль Flask:
# [Social Search] platform='youtube': найдено 5 профилей
# [Social DB sync] Instagram: 3 записей обработано
# [Excel] Social Excel сохранён: social_results.xlsx
```

---

## 🛠️ Если результаты не сохраняются?

**Проверьте:**

1. ✅ Запущен ли Ollama (`http://localhost:11434`)?
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. ✅ Есть ли дискового место для `reports/social_results.xlsx`?

3. ✅ Права доступа к `tish_data.db`?

4. ✅ Смотрите консоль Flask на ошибки:
   ```
   [Screenshot Error] ...
   [Social Analysis Error] ...
   [DB Insert Error] ...
   ```

5. ✅ Проверьте `.env` переменные:
   ```
   OLLAMA_URL=http://localhost:11434
   VISION_MODEL=qwen3-vl  (или llava)
   ```

---

## 📝 Резюме

| Где | Что | Когда |
|---|---|---|
| **БД (`tish_data.db`)** | Полные данные + AI оценки | После каждого поиска |
| **Excel (`reports/social_results.xlsx`)** | Форматированные результаты | Сразу после сохранения в БД |
| **RAM (`state["results"]`)** | WebSocket трансляция | В реальном времени |

**Все три хранилища синхронизированы!** ✅
