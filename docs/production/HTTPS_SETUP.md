# 🔒 HTTPS Setup Guide

Настройка HTTPS для TISH SEARCH v4

---

## Вариант A: Cloudflare (Бесплатно, 10 минут)

**Рекомендуется для продакшена!**

### 1. Зарегистрируйся на Cloudflare
https://dash.cloudflare.com/sign-up

### 2. Добавь домен
- Введи свой домен (например `search.tishteam.space`)
- Cloudflare просканирует DNS записи

### 3. Измени nameservers
- Зайди к своему регистратору домена
- Измени NS записи на те что дал Cloudflare

### 4. Включи SSL/TLS
- Перейди в **SSL/TLS** → **Overview**
- Выбери **Full (strict)**

### 5. Готово!
- Cloudflare автоматически выдаст SSL сертификат
- Все запросы будут через HTTPS
- До 5 минут на активацию

**Плюсы:**
- ✅ Бесплатно
- ✅ Автоматический SSL
- ✅ DDoS защита
- ✅ CDN ускорение

---

## Вариант B: Let's Encrypt + Nginx (Linux, 15 минут)

### 1. Установи Certbot
```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

### 2. Получи сертификат
```bash
sudo certbot --nginx -d search.tishteam.space
```

### 3. Автоматическое обновление
```bash
sudo certbot renew --dry-run
```

### 4. Готово!
- Nginx автоматически настроен на HTTPS
- Сертификат обновляется автоматически

---

## Вариант C: Самоподписанный сертификат (Тестирование)

**Только для разработки!**

### Windows:
```bash
# Создай папку для SSL
mkdir ssl

# Сгенерируй сертификат
openssl req -x509 -nodes -days 365 -newkey rsa:2048 ^
  -keyout ssl/privkey.pem ^
  -out ssl/fullchain.pem ^
  -subj "/CN=localhost"
```

### Linux/Mac:
```bash
mkdir ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/privkey.pem \
  -out ssl/fullchain.pem \
  -subj "/CN=localhost"
```

### Используй в Nginx:
```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/ssl/fullchain.pem;
    ssl_certificate_key /path/to/ssl/privkey.pem;
    
    location / {
        proxy_pass http://localhost:5000;
        # ... остальные настройки
    }
}
```

⚠️ Браузер покажет предупреждение о безопасности - это нормально для тестов.

---

## Проверка HTTPS

```bash
# Проверь что HTTPS работает
curl -I https://localhost:443

# Или через браузер
# Открой https://your-domain.com
```

---

## Checklist

- [ ] SSL сертификат получен
- [ ] Nginx/Cloudflare настроен
- [ ] HTTP → HTTPS редирект работает
- [ ] WebSocket работает через WSS
- [ ] Все ресурсы загружаются по HTTPS

---

## Troubleshooting

### Mixed Content Warning
**Причина:** Некоторые ресурсы загружаются по HTTP

**Решение:** Убедись что все URL в коде начинаются с `https://`

### Certificate Expired
**Решение:** Obнови сертификат
```bash
sudo certbot renew
```

### WebSocket не работает
**Решение:** Добавь в Nginx:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

---

**Готово! 🎉**

Теперь твой сайт работает по HTTPS!
