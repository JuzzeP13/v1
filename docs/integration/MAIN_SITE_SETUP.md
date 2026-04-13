# Инструкция для главного сайта (tishteam.space)

## Что нужно реализовать на главном сайте

### 1. API endpoint для проверки пользователей

Создать endpoint: `GET /api/user/verify`

**Запрос:**
```http
GET /api/user/verify
Authorization: Bearer {user_api_token}
```

**Ответ (200 OK):**
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

**Ответ (401 Unauthorized):**
```json
{
    "error": "invalid_token",
    "message": "Токен недействителен или истёк"
}
```

---

### 2. Генерация API токена для пользователя

После оплаты подписки:

```python
import secrets
from datetime import datetime, timedelta

def generate_user_api_token(user_id):
    """Генерирует API токен для пользователя"""
    token = secrets.token_urlsafe(48)  # 64 символа
    
    # Сохраняем в БД
    db.execute("""
        INSERT INTO user_api_tokens (user_id, token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        token,
        datetime.now(),
        datetime.now() + timedelta(days=365)  # Год validity
    ))
    db.commit()
    
    return token
```

---

### 3. Передача токена в сервис поиска

**Вариант A: Редирект с токеном в URL**

```python
from flask import redirect

def after_payment_redirect(user_id):
    token = generate_user_api_token(user_id)
    return redirect(f"https://search.tishteam.space/?token={token}")
```

**Вариант B: Через cookie (рекомендуется)**

```python
from flask import make_response

def after_payment_redirect(user_id):
    token = generate_user_api_token(user_id)
    
    response = make_response(redirect("https://search.tishteam.space/"))
    response.set_cookie(
        'main_site_token',
        token,
        domain='.tishteam.space',  # Доступно для всех поддоменов
        httponly=True,
        secure=True,  # Только HTTPS
        max_age=365*24*60*60  # 1 год
    )
    return response
```

**Вариант C: Через пост-оплатную страницу**

```html
<!-- На странице "Оплата успешна" -->
<script>
// Автоматический переход в сервис поиска
window.location.href = `https://search.tishteam.space/?token=${USER_TOKEN}`;
</script>

<button onclick="window.open('https://search.tishteam.space/?token=XXX')">
    Перейти к сервису
</button>
```

---

### 4. Страница профиля пользователя

Добавить в профиль пользователя:

```html
<div class="api-token-section">
    <h3>🔑 Ваш API токен для сервиса поиска</h3>
    <p>Используйте этот токен для входа в TISH SEARCH</p>
    
    <div class="token-display">
        <input type="password" value="{{ user.api_token }}" readonly id="apiToken">
        <button onclick="copyToken()">📋 Копировать</button>
    </div>
    
    <div class="token-actions">
        <a href="https://search.tishteam.space/?token={{ user.api_token }}" 
           class="btn btn-primary" target="_blank">
            🚀 Открыть TISH SEARCH
        </a>
    </div>
    
    <div class="subscription-info">
        <p><strong>Подписка:</strong> {{ user.subscription_plan|upper }}</p>
        <p><strong>Истекает:</strong> {{ user.subscription_expires.strftime('%d.%m.%Y') }}</p>
        <p><strong>Ваш ID:</strong> {{ user.id }}</p>
    </div>
</div>
```

---

### 5. Обработка оплаты

```python
def handle_payment_success(user_id, plan, expires_at):
    """Обработка успешной оплаты"""
    
    # 1. Обновляем подписку пользователя
    db.execute("""
        UPDATE users 
        SET subscription_plan = ?,
            subscription_expires = ?
        WHERE id = ?
    """, (plan, expires_at, user_id))
    db.commit()
    
    # 2. Генерируем/обновляем API токен
    token = get_or_create_api_token(user_id)
    
    # 3. Логируем
    log_payment(user_id, plan, amount)
    
    # 4. Редиректим в сервис поиска
    return redirect(f"https://search.tishteam.space/?token={token}")
```

---

### 6. Проверка токена (серверная)

```python
from flask import request, jsonify
from functools import wraps

def require_api_token(f):
    """Декоратор для проверки API токена"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'no_token'}), 401
        
        # Проверяем токен в БД
        user = db.execute("""
            SELECT u.* FROM users u
            JOIN user_api_tokens t ON u.id = t.user_id
            WHERE t.token = ? 
            AND t.expires_at > NOW()
            AND u.is_active = 1
        """, (token,)).fetchone()
        
        if not user:
            return jsonify({'error': 'invalid_token'}), 401
        
        # Возвращаем данные пользователя
        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'subscription_plan': user['subscription_plan'],
            'subscription_expires': user['subscription_expires'],
            'priority': user['priority'],
            'is_active': True
        })
    
    return decorated


# Пример использования
@app.route('/api/user/verify', methods=['GET'])
@require_api_token
def verify_user(user_data):
    """Проверка пользователя"""
    return user_data  # Уже проверено декоратором
```

---

### 7. Приоритетность пользователей

```python
def calculate_priority(user):
    """Вычисляет приоритет пользователя"""
    
    # На основе подписки
    if user['subscription_plan'] == 'enterprise':
        return 3  # High
    elif user['subscription_plan'] == 'pro':
        return 2  # Normal
    else:
        return 1  # Low

# Или явно установить
def set_user_priority(user_id, priority):
    """Установить приоритет вручную"""
    db.execute(
        "UPDATE users SET priority = ? WHERE id = ?",
        (priority, user_id)
    )
    db.commit()
```

---

### 8. Webhook для обновления данных

Если нужно уведомить сервис поиска об изменениях:

```python
import requests

def notify_search_service(user_id):
    """Уведомить сервис поиска об изменениях"""
    
    user = get_user(user_id)
    
    try:
        requests.post(
            "https://search.tishteam.space/api/sync-user",
            json={
                'server_token': 'SERVER_SECRET_TOKEN',  # Из .env
                'user_id': user['id'],
                'username': user['username'],
                'subscription_plan': user['subscription_plan'],
                'subscription_expires': user['subscription_expires'],
                'priority': user['priority']
            },
            timeout=10
        )
    except Exception as e:
        print(f"Failed to notify search service: {e}")
```

---

## Пример полного потока

### 1. Пользователь оплачивает подписку

```
Пользователь → tishteam.space/subscribe → Оплата → Подписка активна
```

### 2. Главный сайт генерирует токен

```python
token = generate_user_api_token(user_id=123)
# token = "aB3dEf6hIj9lMnOpQrStUvWxYz0123456789"
```

### 3. Редирект в сервис поиска

```
https://search.tishteam.space/?token=aB3dEf6hIj9lMnOpQrStUvWxYz0123456789
```

### 4. Сервис поиска проверяет токен

```
GET https://tishteam.space/api/user/verify
Authorization: Bearer aB3dEf6hIj9lMnOpQrStUvWxYz0123456789

← 200 OK
{
    "id": 123,
    "username": "ivan_petrov",
    "subscription_plan": "pro",
    "priority": 2
}
```

### 5. Сервис создаёт/обновляет пользователя

```sql
INSERT INTO users (main_site_id, username, subscription_plan, priority, ...)
VALUES (123, 'ivan_petrov', 'pro', 2, ...)
```

### 6. Пользователь авторизован

```
→ Dashboard сервиса поиска
→ Видит свой план: Pro
→ Может запустить анализ (10 городов/день, 100 сайтов)
```

---

## ID пользователя для поддержки

Если пользователь обращается в поддержку:

```
"Мой ID: 123"

→ Поиск в БД главного сайта:
  SELECT * FROM users WHERE id = 123
  
→ Получаем все данные:
  - Подписка: Pro
  - Истекает: 31.12.2026
  - Оплаты: [список платежей]
  
→ Синхронизация с сервисом поиска:
  SELECT * FROM users WHERE main_site_id = 123
  
→ Видим активность в сервисе:
  - Последний вход: сегодня
  - Городов сегодня: 3/10
  - Ошибки: нет
```

---

## Security Checklist

- [ ] HTTPS везде (сертификаты Let's Encrypt)
- [ ] Токены хранятся хешированными (bcrypt)
- [ ] Rate limiting на `/api/user/verify`
- [ ] Токены истекают (макс 1 год)
- [ ] Логи всех проверок токенов
- [ ] Защита от перебора токенов
- [ ] CORS только для `*.tishteam.space`
- [ ] Валидация всех входных данных

---

## Контакты

- **Разработчик сервиса поиска**: @tishteam_support
- **Email**: support@tishteam.space
- **Документация**: `/MAIN_SITE_INTEGRATION.md`
