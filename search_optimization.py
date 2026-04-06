"""
TISH SEARCH - Оптимизированные функции поиска
Содержит параллельный поиск, улучшенные алгоритмы и кеширование
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Callable
from datetime import datetime

from ddgs import DDGS


class OptimizedProductSearch:
    """Оптимизированный поиск товаров/услуг с кешированием и параллелизмом"""
    
    def __init__(self, max_workers: int = 5, emit_callback: Callable = None):
        """
        Args:
            max_workers: количество параллельных потоков
            emit_callback: функция для отправки статусов клиенту (emit_status)
        """
        self.max_workers = max_workers
        self.emit = emit_callback or print
        self.results = []
        self.seen_urls = set()
        self.lock = threading.Lock()
    
    def search_single_query(self, query: str, category: str = None) -> List[dict]:
        """
        Поиск по одному запросу
        
        Args:
            query: поисковый запрос
            category: категория (опционально)
        
        Returns:
            Список результатов
        """
        results = []
        try:
            with DDGS() as ddgs:
                response = list(ddgs.text(query, max_results=30))
                for r in response:
                    url = (r.get("href", "") or "").strip()
                    if url and url.startswith("http"):
                        with self.lock:
                            if url not in self.seen_urls:
                                self.seen_urls.add(url)
                                results.append({
                                    "url": url,
                                    "title": r.get("title", ""),
                                    "description": r.get("body", ""),
                                    "query": query,
                                    "category": category,
                                    "found_at": datetime.now().isoformat()
                                })
        except Exception as e:
            self.emit(f"⚠️ Ошибка поиска '{query}': {str(e)[:50]}")
        
        return results
    
    def search_parallel(self, queries: List[Tuple[str, str]], max_results: int = 50) -> List[dict]:
        """
        Параллельный поиск по нескольким запросам
        
        Args:
            queries: Список кортежей (query, category)
            max_results: максимум результатов
        
        Returns:
            Список результатов
        """
        self.results = []
        self.seen_urls = set()
        
        self.emit(f"🚀 Запускаю параллельный поиск ({self.max_workers} потоков, {len(queries)} запросов)")
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            # Отправляем все задачи
            for i, (query, category) in enumerate(queries, 1):
                future = executor.submit(self.search_single_query, query, category)
                futures[future] = (query, i)
            
            # Обрабатываем результаты по мере их готовности
            completed = 0
            for future in as_completed(futures):
                query, idx = futures[future]
                try:
                    results = future.result()
                    with self.lock:
                        self.results.extend(results)
                    
                    completed += 1
                    progress = f"[{completed}/{len(queries)}]"
                    self.emit(f"✅ {progress} {query[:40]}: {len(results)} результатов")
                    
                    # Проверяем лимит
                    if len(self.results) >= max_results:
                        self.emit(f"🎯 Достигнут лимит результатов ({max_results})")
                        break
                
                except Exception as e:
                    self.emit(f"❌ Ошибка обработки '{query}': {e}")
        
        elapsed = time.time() - start_time
        self.emit(f"⏱️ Параллельный поиск завершён за {elapsed:.1f} сек. Найдено {len(self.results)} результатов")
        
        return self.results[:max_results]


class OptimizedSocialSearch:
    """Оптимизированный поиск в соцсетях с параллелизмом"""
    
    def __init__(self, max_workers: int = 3, emit_callback: Callable = None):
        """
        Args:
            max_workers: количество параллельных потоков (для платформ)
            emit_callback: функция для отправки статусов
        """
        self.max_workers = max_workers
        self.emit = emit_callback or print
    
    def create_expanded_social_queries(self, query: str, platform: str, city: str = None) -> List[str]:
        """
        Создаёт расширенный набор запросов для соцсетей
        
        Args:
            query: основной запрос
            platform: платформа (youtube, instagram, twitter)
            city: город (опционально)
        
        Returns:
            Список расширенных запросов
        """
        base = [query.strip()]
        
        if city:
            base.extend([
                f"{query} {city}",
                f"{query} {city} официальный",
                f"{query} {city} отзывы",
                f"{query} {city} контакты",
                f"{query} в городе {city}",
                f"{query} + {city}",
            ])
        
        # Расширенные модификаторы
        platform_modifiers = {
            "youtube": [
                "канал", "ютуб", "youtube channel", "обзор", "видео",
                "лучшие каналы", "топ каналы", "популярные", "новые",
                "@channel", "creator", "maker", "youtube.com/@",
                "official channel"
            ],
            "instagram": [
                "instagram", "инстаграм", "профиль", "аккаунт", "official",
                "creator", "studio", "agency", "@profile", "verified",
                "instagram.com/@", "insta", "профили", "официальный"
            ],
            "twitter": [
                "x", "twitter", "твиттер", "аккаунт", "official",
                "trends", "creator", "expert", "@account", "x.com/@",
                "twitter profile", "твиттер аккаунт"
            ]
        }
        
        site_prefix = {
            "youtube": "site:youtube.com",
            "instagram": "site:instagram.com",
            "twitter": "(site:x.com OR site:twitter.com)",
        }.get(platform, "")
        
        queries = []
        modifiers = platform_modifiers.get(platform, [])
        
        for item in base:
            # Базовый запрос
            full_query = f"{site_prefix} {item}".strip()
            queries.append(full_query)
            
            # С модификаторами
            for modifier in modifiers:
                mod_query = f"{site_prefix} {item} {modifier}".strip()
                queries.append(mod_query)
        
        # Убираем дубли, сохраняя порядок
        unique_queries = list(dict.fromkeys(q for q in queries if q.strip()))
        
        self.emit(f"🔍 Подготовлено {len(unique_queries)} запросов для {platform}")
        
        return unique_queries
    
    def search_platforms_parallel(self, query: str, city: str, platforms: List[str], 
                                  search_func: Callable = None, max_results: int = 10) -> List[dict]:
        """
        Параллельный поиск по нескольким платформам
        
        Args:
            query: поисковый запрос
            city: город
            platforms: список платформ (youtube, instagram, twitter)
            search_func: функция поиска (search_social_media из social_search.py)
            max_results: макс результатов на платформу
        
        Returns:
            Объединённые результаты со всех платформ
        """
        if not search_func:
            self.emit("❌ search_func не передана")
            return []
        
        all_results = []
        self.emit(f"🚀 Запускаю параллельный поиск по {len(platforms)} платформам")
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(search_func, query, platform, city): platform
                for platform in platforms
            }
            
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    self.emit(f"✅ {platform}: найдено {len(results)} профилей")
                except Exception as e:
                    self.emit(f"❌ {platform}: {str(e)[:100]}")
        
        elapsed = time.time() - start_time
        self.emit(f"⏱️ Параллельный поиск соцсетей завершён за {elapsed:.1f} сек. Всего {len(all_results)} результатов")
        
        return all_results


# ─── ФУНКЦИИ-ПОМОЩНИКИ ───

def estimate_speedup(num_queries: int, max_workers: int) -> float:
    """
    Расчётное ускорение параллельного поиска vs последовательного
    
    Args:
        num_queries: количество запросов
        max_workers: количество потоков
    
    Returns:
        Ожидаемое ускорение (раз)
    """
    import math
    # Формула: n / (n/m + overhead)
    # overhead - примерно 10% от времени одного запроса
    overhead_penalty = 1.1
    return num_queries / (num_queries / max_workers * overhead_penalty)


# ─── ТЕСТИРОВАНИЕ ───

if __name__ == "__main__":
    print("\n🧪 Тест поиск оптимизации\n")
    
    # Функция для эмиссии статусов
    def mock_emit(msg):
        print(f"  {msg}")
    
    # Тест 1: Расчёт ускорения
    print("[TEST 1] Расчёт ожидаемого ускорения")
    speedup_40_5 = estimate_speedup(40, 5)
    print(f"  ✅ 40 запросов, 5 потоков: {speedup_40_5:.1f}x ускорение")
    
    speedup_3_3 = estimate_speedup(3, 3)
    print(f"  ✅ 3 платформы, 3 потока: {speedup_3_3:.1f}x ускорение\n")
    
    # Тест 2: Инициализация OптимizedProductSearch
    print("[TEST 2] Создание объекта OptimizedProductSearch")
    product_search = OptimizedProductSearch(max_workers=5, emit_callback=mock_emit)
    print(f"  ✅ Объект создан (max_workers={product_search.max_workers})\n")
    
    # Тест 3: Расширенные запросы для соцсетей
    print("[TEST 3] Создание расширенных запросов для YouTube")
    social_search = OptimizedSocialSearch(emit_callback=mock_emit)
    queries = social_search.create_expanded_social_queries("web design", "youtube", "Москва")
    print(f"  ✅ Создано {len(queries)} запросов\n")
    print("  Примеры запросов:")
    for q in queries[:5]:
        print(f"    - {q}")
    print(f"    ... и ещё {len(queries)-5} запросов\n")
    
    print("✅ Все тесты завершены!")
