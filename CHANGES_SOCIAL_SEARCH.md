# 📋 Изменения в модуле Social Search

**Решэена проблема:** Непонятно куда сохраняются результаты поиска по соцсетям  
**Дата:** 2026-04-05

---

## 🎯 ЧТО БЫЛО ИЗМЕНЕНО?

### 1️⃣ Четкость: Теперь понятно КУДа сохраняются результаты

**Результаты сохраняются в 3 местах:**

```
🔹 БД SQLite (tish_data.db) → таблица social_results
                ├── url, platform, username
                ├── design_score, ux_score ⭐ (новое)
                ├── design_text, ux_text ⭐ (новое)
                └── title, description, city, query, found_at, analyzed_at

🔹 Excel файл (reports/social_results.xlsx) → лист "SocialMedia"
                ├── Все данные из БД
                ├── Форматированные таблицы
                └── Цветовая индикация по платформам

🔹 WebSocket (реальное время) → клиенту в браузер
                ├── Прогресс анализа
                ├── Результаты по мере обработки
                └── AI оценки через socketio.emit()
```

---

### 2️⃣ Добавлена AI оценка для соцсетей

**Старое поведение:**
- Найти профили в соцсетях ✓
- Сохранить в БД ✓
- Экспортировать в Excel ✓
- **Но БЕЗ AI анализа** ❌

**Новое поведение:**
- Найти профили в соцсетях ✓
- **Взять скриншот профиля** ✓ (новое)
- **Анализировать через Ollama vision** ✓ (новое)
- Получить design_score/ux_score ✓ (новое)
- Сохранить в БД с оценками ✓ (новое)
- Экспортировать в Excel с оценками ✓ (новое)

---

### 3️⃣ Изменения в коде

#### `server.py`

**Таблица `social_results` (строка 296-314):**
```python
# БЫЛО:
CREATE TABLE IF NOT EXISTS social_results (
    id, url, platform, title, description, username, city, query, found_at, analyzed_at
)

# ТЕПЕРЬ:
CREATE TABLE IF NOT EXISTS social_results (
    id, url, platform, title, description, username, city, query,
    found_at, analyzed_at,
    design_score INTEGER,    # ⭐ новое
    ux_score INTEGER,        # ⭐ новое
    design_text TEXT,        # ⭐ новое
    ux_text TEXT             # ⭐ новое
)
```

**Функция `process_social_search()` (строка 2106-2206):**
```python
# БЫЛО:
1. Поиск в Google/DuckDuckGo
2. Сохранение в БД (без анализа)
3. Экспорт в Excel
4. WebSocket трансляция

# ТЕПЕРЬ:
1. Поиск в DuckDuckGo
2. Скриншот каждого профиля (Playwright)
3. AI анализ через Ollama vision
4. Сохранение в БД (с design_score, ux_score)
5. Экспорт в Excel (с AI оценками)
6. WebSocket трансляция (с AI оценками)
```

**Функция `save_social_to_excel()` (строка 2270-2380):**
```python
# БЫЛО:
headers = ["#", "Платформа", "URL", "Название", "Описание", "Username/ID", "Город", "Запрос", "Дата"]

# ТЕПЕРЬ:
headers = ["#", "Платформа", "URL", "Название", "Описание", "Username/ID", 
           "Дизайн", "UX", "Примечание", "Город", "Запрос", "Дата"]
           
# Добавлены колонки 7-9:
# - design_score (0-10)
# - ux_score (0-10)
# - design_text + ux_text (примечание)
```

#### `social_search.py`

**Удалены неиспользуемые функции:**
```python
# Удалено:
- save_social_result() (не вызывалась)
- get_social_results() (не вызывалась)

# Добавлено:
# (Ничего нового в social_search.py, только удаление старого)
```

---

### 4️⃣ Новые файлы

| Файл | Назначение |
|------|-----------|
| `migrate_social_results.py` | Миграция БД для добавления новых колонок |
| `SOCIAL_MEDIA_STORAGE.md` | Документация: куда сохраняются результаты |
| `CHANGES_SOCIAL_SEARCH.md` | Этот файл - список изменений |

---

## 📊 Данные в БД

### Схема таблицы `social_results`:

```sql
id                  INTEGER PRIMARY KEY AUTOINCREMENT
url                 TEXT NOT NULL               -- Profile URL
platform            TEXT NOT NULL               -- 'youtube', 'instagram', 'twitter'
title               TEXT                        -- Название профиля
description         TEXT                        -- Описание из поиска
username            TEXT                        -- @username или channel_id
city                TEXT                        -- Город поиска
query               TEXT                        -- Поисковый запрос
found_at            TEXT                        -- ISO дата поиска
analyzed_at         TEXT                        -- ISO дата анализа
design_score        INTEGER                     -- AI оценка дизайна (0-10) ⭐
ux_score            INTEGER                     -- AI оценка UX (0-10) ⭐
design_text         TEXT                        -- Текстовая оценка дизайна ⭐
ux_text             TEXT                        -- Текстовая оценка UX ⭐

UNIQUE(url, platform)                           -- Нет дубликатов
```

---

## 🔄 Процесс сохранения (Flow)

```
ПОИСК (social_search.search_social_media)
  ↓
  ├─ youtube_search() | instagram_search() | twitter_search()
  └─ Возвращает: [url, title, description, username, ...]
  
  ↓
АНАЛИЗ (process_social_search в server.py)
  ↓
  ├─ take_screenshot(url) — Playwright скриншот
  ├─ analyze_social_profile(platform, url, screenshot)
  │   └─ Ollama vision анализ → design_score, ux_score, design_text, ux_text
  └─ Добавляет поля в result dict
  
  ↓
СОХРАНЕНИЕ (INSERT/UPDATE)
  ↓
  ├─ БД: INSERT INTO social_results (...)
  ├─ Excel: save_social_to_excel(results)
  └─ WebSocket: socketio.emit("result", {...})
```

---

## ✅ Доступ к результатам

### 1. **Через Python код:**
```python
import sqlite3

conn = sqlite3.connect('tish_data.db')
conn.row_factory = sqlite3.Row

# Все результаты
results = conn.execute("SELECT * FROM social_results").fetchall()

# Отфильтрованные
youtube_results = conn.execute(
    "SELECT url, design_score, ux_score FROM social_results WHERE platform='youtube' ORDER BY design_score DESC"
).fetchall()

for row in youtube_results:
    print(f"{row['url']}: Дизайн={row['design_score']}/10, UX={row['ux_score']}/10")

conn.close()
```

### 2. **Через Excel:**
- Открыть `reports/social_results.xlsx`
- Выбрать лист "SocialMedia"
- Можно сортировать по design_score или ux_score

### 3. **Через WebSocket (в браузере):**
```javascript
socket.on('result', function(data) {
    console.log(`${data.category}: ${data.design} / ${data.ux}`);
});
```

---

## 🚀 Как запустить новое поведение?

1. **Миграция БД:**
   ```bash
   python migrate_social_results.py
   ```

2. **Запустить server.py:**
   ```bash
   python server.py
   ```

3. **Открыть веб-интерфейс:**
   ```
   http://localhost:5000
   ```

4. **Выбрать "Поиск по соцсетям":**
   - Города: Москва, Санкт-Петербург, etc.
   - Платформы: YouTube, Instagram, X/Twitter
   - Запрос: web design, IT, красота, etc.

5. **Результаты появятся:**
   - В браузере (WebSocket)
   - В БД (tish_data.db)
   - В Excel (reports/social_results.xlsx)

---

## ⚠️ Важные замечания

### Если результаты не сохраняются:

1. ✅ **Ollama запущена?**
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. ✅ **Видение модель установлена?**
   - В `.env`: `VISION_MODEL=qwen3-vl` (или `llava`)
   - Проверить команду: `ollama pull qwen3-vl`

3. ✅ **Места для Excel?**
   - Проверить что `reports/` директория существует

4. ✅ **Права доступа?**
   - `tish_data.db` доступен для записи
   - `reports/` директория доступна для записи

### Отладка:

```bash
# Посмотреть консоль Flask
python server.py

# Проверить БД
python -c "import sqlite3; conn = sqlite3.connect('tish_data.db'); print(conn.execute('SELECT COUNT(*) FROM social_results').fetchone()[0])"

# Проверить Excel
python -c "import openpyxl; wb = openpyxl.load_workbook('reports/social_results.xlsx'); print(wb['SocialMedia'].max_row)"
```

---

## 📝 Резюме изменений

| Что | Было | Стало |
|-----|------|-------|
| **Скриншоты соцсетей** | ❌ | ✅ |
| **AI анализ дизайна** | ❌ | ✅ (0-10) |
| **AI анализ UX** | ❌ | ✅ (0-10) |
| **Сохранение в БД** | ✅ (без оценок) | ✅ (с оценками) |
| **Экспорт в Excel** | ✅ (без оценок) | ✅ (с оценками) |
| **WebSocket трансляция** | ✅ (без оценок) | ✅ (с оценками) |
| **Таблиц в БД** | 1 (неполная) | 1 (полная) |

---

## 🎉 Результат

Теперь **ПОЛНОСТЬЮ ПОНЯТНО**:

✅ Где сохраняются результаты (БД + Excel + WebSocket)  
✅ Как они сохраняются (с AI оценками)  
✅ Как их получить (SQL, Excel, браузер)  
✅ Что там хранится (все метаданные + AI анализ)

Проблема **РЕШЕНА**! 🎯
