# Интеграция с главным сайтом (tishteam.space)

## Обзор архитектуры

```
Пользователь оплачивает подписку на tishteam.space
         ↓
Главный сайт генерирует API токен
         ↓
Пользователь заходит на search.tishteam.space
         ↓
Сервис проверяет токен через API главного сайта
         ↓
Получает данные: ID, план, приоритет
         ↓
Синхронизирует с локальной БД
         ↓
Предоставляет доступ согласно лимитам
```

---

## Настройка главного сайта (tishteam.space)

### 1. API endpoint для проверки токена

На главном сайте нужно создать endpoint:

```
GET /api/user/verify
Headers: Authorization: Bearer {api_token}

Response 200:
{
    "id": 123,
    "username": "user123",
    "email": "user@example.com",
    "subscription_plan": "pro",  // basic/pro/enterprise
    "subscription_expires": "2026-12-31T23:59:59",
    "priority": 2,  // 1=low, 2=normal, 3=high, 4=vip
    "is_active": true
}

Response 401:
{
    "error": "invalid_token"
}
```

### 2. Генерация API токена

При оплате подписки главный сайт должен:
1. Сгенерировать уникальный токен (JWT или случайная строка)
2. Сохранить связь: токен → пользователь
3. Передать токен пользователю

### 3. Передача токена пользователю

**Способ 1: Через редирект с параметром**
```
https://search.tishteam.space/?token=USER_API_TOKEN_HERE
```

**Способ 2: Через cookie**
```
Set-Cookie: main_site_token=USER_API_TOKEN_HERE; Domain=.tishteam.space; Path=/
```

**Способ 3: Через iframe postMessage**
```javascript
// На главном сайте после оплаты
window.postMessage({
    type: 'AUTH_TOKEN',
    token: 'USER_API_TOKEN_HERE'
}, 'https://search.tishteam.space');
```

---

## Настройка сервиса поиска

### 1. Обновить .env

```env
# Главный сайт
MAIN_SITE_URL=https://tishteam.space
MAIN_SITE_API_URL=https://tishteam.space/api
MAIN_SITE_API_TOKEN=SERVER_SECRET_TOKEN  # Для сервер-сервер запросов
```

### 2. Автоматическая синхронизация

При запуске сервера автоматически:
- Запускается фоновая синхронизация каждые 10 минут
- Все пользователи синхронизируются с главным сайтом
- Обновляются подписки и приоритеты

---

## Как это работает

### Вход пользователя

1. **Пользователь приходит с главного сайта:**
   - С токеном в URL: `?token=xxx`
   - С cookie: `main_site_token=xxx`
   - С заголовком: `X-Main-Site-Token: xxx`

2. **Сервис проверяет токен:**
   ```python
   GET {MAIN_SITE_API_URL}/user/verify
   Authorization: Bearer {token}
   ```

3. **Получает данные пользователя:**
   - ID с главного сайта
   - Подписка (basic/pro/enterprise)
   - Приоритет (1-4)
   - Дата истечения

4. **Создаёт/обновляет локального пользователя:**
   - Сохраняет `main_site_id`
   - Обновляет `subscription_plan`
   - Устанавливает `priority`

5. **Авторизует в системе**

### Проверка при каждом запросе

- При запуске анализа проверяется подписка
- Приоритет влияет на очередь (high/vip быстрее)
- Данные обновляются каждые 10 минут

---

## Приоритетность пользователей

| Приоритет | Уровень | Описание | Влияние на очередь |
|-----------|---------|----------|---------------------|
| 1 | Low | Бесплатный/Basic | Обычная очередь |
| 2 | Normal | Pro | Обычная очередь |
| 3 | High | Enterprise | Приоритет в очереди |
| 4 | VIP | VIP клиент | Мгновенный старт |

### Пример использования приоритета

```python
from main_site_integration import should_prioritize_queue

if should_prioritize_queue(user_id):
    # Пользователь получает приоритет
    process_immediately(user_task)
else:
    # Обычная очередь
    add_to_queue(user_task)
```

---

## ID пользователя для поддержки

Если у пользователя проблема, он может сообщить свой ID:

**Где найти ID:**
1. В URL профиля: `/profile?id=123`
2. В cookie: `user_id=123`
3. В главном сайте: ID аккаунта

**По ID можно определить:**
- Какую подписку имеет
- Когда оплатил
- Приоритетность
- Историю использования

---

## Обработка ошибок

### Токен истёк

```json
{
    "error": "token_expired",
    "redirect_to_main": true,
    "main_site_url": "https://tishteam.space/auth/login?redirect=..."
}
```

**Что делать:** Перенаправить пользователя на главный сайт для повторной авторизации.

### Токен невалиден

```json
{
    "error": "invalid_token"
}
```

**Что делать:** Запросить новый токен.

### Главный сайт недоступен

```
[MAIN SITE] Не удалось подключиться к главному сайту
```

**Что делать:**
1. Использовать кешированные данные (valid 5 минут)
2. Разрешить вход если данные есть в локальной БД
3. Повторить попытку позже

---

## Безопасность

### 1. Токены
- Кэшируются на 5 минут (меньше нагрузка на главный сайт)
- Не хранятся в открытом виде
- Передаются только по HTTPS

### 2. Данные пользователей
- Синхронизируются каждые 10 минут
- При изменении подписки на главном сайте - обновляются автоматически
- Если подписка истекла - доступ ограничивается

### 3. Защита от атак
- Rate limiting на проверку токенов
- Валидация всех данных с главного сайта
- Логи всех авторизаций

---

## Примеры запросов

### 1. Проверить токен

```bash
curl -X POST https://search.tishteam.space/auth/verify-token \
  -H "Content-Type: application/json" \
  -d '{"api_token": "USER_TOKEN_HERE"}'
```

**Ответ:**
```json
{
    "valid": true,
    "user": {
        "id": 123,
        "username": "user123",
        "subscription_plan": "pro",
        "priority": 2
    }
}
```

### 2. Войти через токен

```bash
curl -X POST https://search.tishteam.space/auth/login-from-main-site \
  -H "Content-Type: application/json" \
  -d '{"api_token": "USER_TOKEN_HERE"}'
```

**Ответ:**
```json
{
    "success": true,
    "user": {
        "id": 456,
        "username": "user123",
        "main_site_id": 123,
        "subscription_plan": "pro",
        "priority": 2
    },
    "redirect": "/dashboard"
}
```

### 3. Получить данные пользователя

```bash
curl -X GET https://search.tishteam.space/auth/api/me/subscription \
  -H "Cookie: session=SESSION_COOKIE"
```

**Ответ:**
```json
{
    "plan": "Pro",
    "plan_ru": "Профессиональный",
    "is_active": true,
    "expires": "2026-12-31T23:59:59",
    "limits": {
        "max_cities_per_day": 10,
        "max_sites_per_city": 100,
        "max_parallel": 5
    },
    "usage": {
        "cities_today": 2,
        "sites_today": 45
    }
}
```

---

## Troubleshooting

### Ошибка: "integration_not_configured"

**Причина:** Не найден файл `main_site_integration.py`

**Решение:** Убедитесь что файл существует в корне проекта.

### Ошибка: "Таймаут запроса к главному сайту"

**Причина:** Главный сайт не отвечает

**Решение:**
1. Проверьте доступность `https://tishteam.space`
2. Увеличьте таймаут в `main_site_integration.py`
3. Проверьте firewall/сеть

### Ошибка: "Неверный токен главного сайта"

**Причина:** Токен недействителен или истёк

**Решение:**
1. Запросить новый токен на главном сайте
2. Проверить что подписка активна
3. Обратиться в поддержку с ID пользователя

---

## Следующие шаги

### Для главного сайта:
1. ✅ Создать endpoint `/api/user/verify`
2. ✅ Реализовать генерацию API токенов
3. ✅ Настроить передачу токена (URL/cookie)
4. ✅ Обеспечить безопасность (HTTPS, rate limiting)

### Для сервиса поиска:
1. ✅ Интеграция с API главного сайта
2. ✅ Синхронизация пользователей
3. ✅ Проверка подписки и лимитов
4. ✅ Система приоритетов
5. ✅ Автоматический вход через токен/cookie

---

## Контакты поддержки

- **Telegram**: @tishteam_support
- **Email**: support@tishteam.space
- **Главный сайт**: https://tishteam.space
