"""
TISH SEARCH - Модуль кеширования результатов поиска
Кэширует результаты товаров/услуг и соцсетей на 24 часа
"""

import json
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta

# Конфигурация кеша
CACHE_DIR = Path("search_cache")
CACHE_TTL_HOURS = 24  # Время жизни кеша (часы)
CACHE_TTL_SECONDS = CACHE_TTL_HOURS * 3600

# Создаём директорию кеша если не существует
CACHE_DIR.mkdir(exist_ok=True)


def get_cache_key(query: str, city: str, search_type: str) -> str:
    """
    Генерирует уникальный ключ для кеша
    
    Args:
        query: поисковый запрос
        city: город
        search_type: тип поиска ('product', 'social')
    
    Returns:
        MD5 hash ключ
    """
    key_str = f"{search_type}:{query}:{city}".lower().strip()
    return hashlib.md5(key_str.encode()).hexdigest()


def get_from_cache(query: str, city: str, search_type: str) -> dict:
    """
    Получить результаты из кеша если они есть и не устарели
    
    Args:
        query: поисковый запрос
        city: город
        search_type: тип поиска
    
    Returns:
        {'results': [...], 'cached_at': datetime} или None если кеш istari или не существует
    """
    cache_key = get_cache_key(query, city, search_type)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    if not cache_file.exists():
        return None
    
    try:
        file_mtime = cache_file.stat().st_mtime
        cache_age = time.time() - file_mtime
        
        # Проверяем срок действия кеша
        if cache_age > CACHE_TTL_SECONDS:
            # Кеш устарел - удаляем его
            cache_file.unlink()
            return None
        
        # Кеш свежий - читаем и возвращаем
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Добавляем информацию о возрасте кеша
            data['cache_age_seconds'] = int(cache_age)
            data['cache_ttl_hours'] = CACHE_TTL_HOURS
            return data
    
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Cache] Ошибка чтения кеша {cache_key}: {e}")
        return None


def save_to_cache(query: str, city: str, search_type: str, results: list) -> bool:
    """
    Сохранить результаты в кеш
    
    Args:
        query: поисковый запрос
        city: город
        search_type: тип поиска
        results: список результатов для сохранения
    
    Returns:
        True если успешно, False если ошибка
    """
    cache_key = get_cache_key(query, city, search_type)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    try:
        data = {
            'query': query,
            'city': city,
            'search_type': search_type,
            'results': results,
            'cached_at': datetime.now().isoformat(),
            'count': len(results)
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[Cache] Сохранено {len(results)} результатов: {query[:50]} ({city})")
        return True
    
    except OSError as e:
        print(f"[Cache] Ошибка сохранения кеша {cache_key}: {e}")
        return False


def clear_cache(search_type: str = None, older_than_hours: int = None):
    """
    Очистить кеш
    
    Args:
        search_type: если указан, удалить только этот тип ('product', 'social')
        older_than_hours: если указано, удалить результаты старше N часов
    
    Returns:
        количество удалённых файлов
    """
    deleted = 0
    current_time = time.time()
    
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            # Проверяем тип если нужно
            if search_type:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('search_type') != search_type:
                        continue
            
            # Проверяем возраст если нужно
            if older_than_hours:
                file_age_hours = (current_time - cache_file.stat().st_mtime) / 3600
                if file_age_hours < older_than_hours:
                    continue
            
            cache_file.unlink()
            deleted += 1
        
        except Exception as e:
            print(f"[Cache] Ошибка при удалении {cache_file}: {e}")
    
    print(f"[Cache] Удалено {deleted} кеш-файлов")
    return deleted


def get_cache_stats() -> dict:
    """
    Получить статистику кеша
    
    Returns:
        Словарь со статистикой кеша
    """
    stats = {
        'total_files': 0,
        'total_size_mb': 0,
        'by_type': {},
        'oldest_cache_hours': None,
        'newest_cache_minutes': None
    }
    
    current_time = time.time()
    
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            search_type = data.get('search_type', 'unknown')
            count = data.get('count', 0)
            
            # Статистика по типам
            if search_type not in stats['by_type']:
                stats['by_type'][search_type] = {'count': 0, 'total_results': 0}
            stats['by_type'][search_type]['count'] += 1
            stats['by_type'][search_type]['total_results'] += count
            
            # Общая статистика
            stats['total_files'] += 1
            stats['total_size_mb'] += cache_file.stat().st_size / (1024 * 1024)
            
            # Возраст файлов
            file_age_hours = (current_time - cache_file.stat().st_mtime) / 3600
            file_age_minutes = (current_time - cache_file.stat().st_mtime) / 60
            
            if stats['oldest_cache_hours'] is None or file_age_hours > stats['oldest_cache_hours']:
                stats['oldest_cache_hours'] = file_age_hours
            
            if stats['newest_cache_minutes'] is None or file_age_minutes < stats['newest_cache_minutes']:
                stats['newest_cache_minutes'] = file_age_minutes
        
        except Exception as e:
            print(f"[Cache] Ошибка при сборе статистики {cache_file}: {e}")
    
    return stats


def print_cache_stats():
    """Печать статистики кеша в консоль"""
    stats = get_cache_stats()
    
    print("\n" + "="*60)
    print("📦 СТАТИСТИКА КЕША ПОИСКА")
    print("="*60)
    print(f"Всего файлов: {stats['total_files']}")
    print(f"Размер кеша: {stats['total_size_mb']:.2f} MB")
    
    if stats['by_type']:
        print("\nПо типам:")
        for search_type, data in stats['by_type'].items():
            print(f"  {search_type}: {data['count']} файлов, {data['total_results']} результатов")
    
    if stats['oldest_cache_hours']:
        print(f"\nСамый старый кеш: {stats['oldest_cache_hours']:.1f} часов назад")
    
    if stats['newest_cache_minutes']:
        print(f"Самый новый кеш: {stats['newest_cache_minutes']:.1f} минут назад")
    
    print("="*60 + "\n")


# ─── CLI Тестирование ───

if __name__ == "__main__":
    print("🧪 Тест модуля search_cache.py\n")
    
    # Тест 1: Сохранение в кеш
    print("[TEST 1] Сохранение результатов в кеш...")
    test_results = [
        {"url": "https://example.com/1", "title": "Result 1"},
        {"url": "https://example.com/2", "title": "Result 2"},
    ]
    success = save_to_cache("web design", "Москва", "product", test_results)
    print(f"  Result: {'✅ OK' if success else '❌ FAIL'}\n")
    
    # Тест 2: Получение из кеша
    print("[TEST 2] Получение результатов из кеша...")
    cached = get_from_cache("web design", "Москва", "product")
    if cached:
        print(f"  ✅ Найдено в кеше: {cached['count']} результатов")
        print(f"  Возраст кеша: {cached['cache_age_seconds']} сек\n")
    else:
        print("  ❌ Кеш не найден\n")
    
    # Тест 3: Статистика кеша
    print("[TEST 3] Статистика кеша...")
    print_cache_stats()
    
    # Тест 4: Несуществующий кеш
    print("[TEST 4] Попытка получить несуществующий кеш...")
    no_cache = get_from_cache("random query", "Random City", "social")
    print(f"  Result: {'✅ OK (None)' if no_cache is None else '❌ FAIL'}\n")
    
    print("✅ Все тесты завершены!")
