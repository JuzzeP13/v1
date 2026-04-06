# Полная интеграция с главным сайтом tishteam.space

## 🎯 Что реализовано

### 1. **Оплата через главный сайт**
- ✅ Пользователь оплачивает подписку на `tishteam.space`
- ✅ Главный сайт генерирует API токен
- ✅ Токен передаётся в сервис поиска (URL/cookie)

### 2. **Автоматический вход**
- ✅ Сервис получает токен пользователя
- ✅ Проверяет через API главного сайта
- ✅ Получает данные: ID, план, приоритет
- ✅ Создаёт/обновляет локального пользователя
- ✅ Авторизует автоматически

### 3. **Синхронизация данных**
- ✅ Фоновая синхронизация каждые 10 минут
- ✅ Обновление подписок
- ✅ Обновление приоритетов
- ✅ Кеш токенов (5 минут)

### 4. **Приоритетность**
- ✅ Priority 1 (Low) - Basic
- ✅ Priority 2 (Normal) - Pro
- ✅ Priority 3 (High) - Enterprise
- ✅ Priority 4 (VIP) - вручную

### 5. **ID пользователя**
- ✅ Каждый пользователь имеет `main_site_id`
- ✅ По ID можно определить всю информацию
- ✅ Для поддержки: "Мой ID: 123"

---

## 📁 Созданные/изменённые файлы

### Новые файлы:
1. ✅ `main_site_integration.py` - Основная логика интеграции
2. ✅ `MAIN_SITE_INTEGRATION.md` - Документация интеграции
3. ✅ `MAIN_SITE_SETUP.md` - Инструкция для главного сайта

### Изменённые файлы:
1. ✅ `models.py` - Добавлены поля: `main_site_id`, `main_site_api_token`, `priority`, `last_sync`
2. ✅ `auth.py` - Новые endpoint'ы для входа через главный сайт
3. ✅ `config.py` - Настройки главного сайта
4. ✅ `templates/index.html` - Автоматический вход через токен/cookie
5. ✅ `.env` - Добавлены настройки главного сайта

---

## 🔄 Поток данных

```
┌─────────────────────────────────────────────────────────────┐
│                        tishteam.space                        │
│  ┌──────────────────────────────────────────────┐            │
│  │ 1. Пользователь оплачивает подписку          │            │
│  │ 2. Генерируется API токен                    │
│  │ 3. Токен передаётся пользователю             │            │
│  └──────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                           ↓
         Редирект: https://search.tishteam.space/?token=XXX
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              search.tishteam.space (этот сервис)             │
│  ┌──────────────────────────────────────────────┐            │
│  │ 1. Получает токен из URL/cookie              │            │
│  │ 2. Проверяет через API главного сайта        │            │
│  │    GET /api/user/verify                      │            │
│  │ 3. Получает данные пользователя              │            │
│  │    {id, username, plan, priority}            │            │
│  │ 4. Синхронизирует с локальной БД             │            │
│  │ 5. Авторизует пользователя                   │            │
│  └──────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                           ↓
              Пользователь в системе!
              - Видит свой план
              - Может использовать сервис
              - Лимиты согласно подписке
```

---

## 🔧 API Endpoints главного сайта

### Требуется реализовать на tishteam.space:

#### 1. Проверка токена

```http
GET /api/user/verify
Authorization: Bearer {user_api_token}
```

**Ответ 200:**
```json
{
    "id": 123,
    "username": "ivan_petrov",
    "email": "ivan@example.com",
    "subscription_plan": "pro",
    "subscription_expires": "2026-12-31T23:59:59",
    "priority": 2,
    "is_active": true
}
```

**Ответ 401:**
```json
{
    "error": "invalid_token"
}
```

---

## 🔧 API Endpoints сервиса поиска

### Уже реализовано:

#### 1. Вход через главный сайт

```http
POST /auth/login-from-main-site
Content-Type: application/json

{
    "api_token": "USER_TOKEN_HERE"
}
```

**Ответ 200:**
```json
{
    "success": true,
    "user": {
        "id": 456,
        "username": "ivan_petrov",
        "main_site_id": 123,
        "subscription_plan": "pro",
        "priority": 2
    },
    "redirect": "/dashboard"
}
```

#### 2. Проверка токена (без входа)

```http
POST /auth/verify-token
Content-Type: application/json

{
    "api_token": "USER_TOKEN_HERE"
}
```

**Ответ 200:**
```json
{
    "valid": true,
    "user": {
        "id": 123,
        "username": "ivan_petrov",
        "subscription_plan": "pro"
    }
}
```

---

## 🎨 Как пользователь попадает в сервис

### Способ 1: Редирект с токеном в URL

**На главном сайте после оплаты:**
```python
return redirect(f"https://search.tishteam.space/?token={user_token}")
```

**Пользователь видит:**
```
https://search.tishteam.space/?token=aB3dEf6hIj9lMn...
```

**Сервис автоматически:**
- Забирает токен из URL
- Проверяет через API
- Авторизует
- Убирает токен из URL (чистый адресная строка)

---

### Способ 2: Через cookie

**Главный сайт устанавливает cookie:**
```python
response.set_cookie(
    'main_site_token',
    user_token,
    domain='.tishteam.space',
    httponly=True,
    secure=True
)
```

**Сервис автоматически:**
- Проверяет cookie при загрузке
- Авторизует если токен валиден

---

### Способ 3: Ручной ввод токена

**Пользователь в профиле главного сайта видит:**
```
Ваш API токен: aB3dEf6hIj9lMn...

[Копировать] [Открыть TISH SEARCH]
```

**Копирует токен и вставляет в сервисе** (если нужно)

---

## 🔐 Безопасность

### 1. Передача токена
- ✅ Только HTTPS
- ✅ HttpOnly cookie (недоступен из JavaScript)
- ✅ Secure flag (только HTTPS)
- ✅ Domain restriction (`.tishteam.space`)

### 2. Хранение токена
- ✅ Кеш в памяти (5 минут)
- ✅ Не сохраняется в БД в открытом виде
- ✅ Автоматическая очистка устаревших

### 3. Проверка валидности
- ✅ Запрос к главному сайту при входе
- ✅ Периодическая ресинхронизация (10 минут)
- ✅ Автоматический редирект если токен истёк

---

## 📊 Определение приоритетности

### Автоматически на основе подписки:

| Подписка | Приоритет | Описание |
|----------|-----------|----------|
| Basic | 1 (Low) | Обычная очередь |
| Pro | 2 (Normal) | Обычная очередь |
| Enterprise | 3 (High) | Приоритет в очереди |
| VIP (вручную) | 4 (VIP) | Мгновенный старт |

### Использование:

```python
from main_site_integration import get_user_priority, should_prioritize_queue

priority = get_user_priority(user_id)
# → 3 (High)

if should_prioritize_queue(user_id):
    # Приоритетная обработка
    process_now(user_task)
else:
    # Обычная очередь
    add_to_queue(user_task)
```

---

## 🆔 ID пользователя для поддержки

### Где посмотреть ID:

**В сервисе поиска:**
```javascript
// В консоли браузера
console.log(window.user_id);  // → 456
```

**На главном сайте:**
```
Профиль → Настройки → ID аккаунта: 123
```

### Что можно узнать по ID:

```sql
-- На главном сайте
SELECT * FROM users WHERE id = 123;
-- → Подписка, оплаты, даты

-- В сервисе поиска
SELECT * FROM users WHERE main_site_id = 123;
-- → Активность, лимиты, история
```

---

## 🚀 Развёртывание

### 1. На главном сайте (tishteam.space):

```bash
# 1. Создать endpoint /api/user/verify
# 2. Реализовать генерацию токенов
# 3. Настроить передачу токена (URL/cookie)
# 4. Протестировать
```

### 2. В сервисе поиска:

```bash
# 1. Обновить .env
MAIN_SITE_URL=https://tishteam.space
MAIN_SITE_API_URL=https://tishteam.space/api
MAIN_SITE_API_TOKEN=SERVER_SECRET_TOKEN

# 2. Убедиться что файлы существуют:
ls main_site_integration.py
ls MAIN_SITE_INTEGRATION.md
ls MAIN_SITE_SETUP.md

# 3. Запустить сервер
python server.py
```

### 3. Тестирование:

```bash
# Проверить вход через токен
curl -X POST http://localhost:5000/auth/login-from-main-site \
  -H "Content-Type: application/json" \
  -d '{"api_token": "TEST_TOKEN"}'

# Проверить верификацию
curl -X POST http://localhost:5000/auth/verify-token \
  -H "Content-Type: application/json" \
  -d '{"api_token": "TEST_TOKEN"}'
```

---

## ⚠️ Важно!

### Перед запуском:

1. **На главном сайте реализовать:**
   - ✅ Endpoint `/api/user/verify`
   - ✅ Генерацию API токенов
   - ✅ Передачу токена пользователю

2. **Настроить HTTPS:**
   - ✅ Сертификаты Let's Encrypt
   - ✅ Все редиректы только HTTPS
   - ✅ HSTS заголовки

3. **Безопасность:**
   - ✅ Уникальный `MAIN_SITE_API_TOKEN` в .env
   - ✅ Rate limiting на проверку токенов
   - ✅ Логи всех авторизаций

4. **Тестирование:**
   - ✅ Проверить полный поток: оплата → токен → вход
   - ✅ Проверить синхронизацию
   - ✅ Проверить обновление подписок

---

## 📞 Поддержка

Если что-то не работает:

1. **Проверить логи:**
   ```
   [AUTH] Успешный вход через главный сайт: ivan_petrov (ID: 123)
   [MAIN SITE] Ошибка верификации: 401
   [SYNC] Синхронизирован: ivan_petrov
   ```

2. **Проверить соединение:**
   ```bash
   curl https://tishteam.space/api/user/verify \
     -H "Authorization: Bearer TEST_TOKEN"
   ```

3. **Обратиться в поддержку:**
   - Telegram: @tishteam_support
   - Email: support@tishteam.space
   - Приложить ID пользователя и логи

---

## 📚 Документация

- **MAIN_SITE_INTEGRATION.md** - Полная документация интеграции
- **MAIN_SITE_SETUP.md** - Инструкция для главного сайта
- **PRODUCTION_IMPROVEMENTS.md** - Все улучшения для продакшена
- **README.md** - Основная документация сервиса

---

**Готово! 🎉**

Теперь:
- ✅ Оплата идёт через главный сайт
- ✅ Автоматический вход по токену
- ✅ Синхронизация подписок
- ✅ Приоритетность пользователей
- ✅ ID для поддержки
