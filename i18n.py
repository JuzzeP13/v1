"""
TISH SEARCH - Internationalisation (i18n) Module
Поддержка многоязычности (English, Русский)
"""

import json
import sys
import io
from pathlib import Path
from typing import Optional, Dict, Any

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class I18n:
    """Система интернационализации для TISH SEARCH"""
    
    SUPPORTED_LANGUAGES = ['en', 'ru']
    TRANSLATIONS_DIR = Path(__file__).parent / 'translations'
    
    def __init__(self, default_language: str = 'ru'):
        """
        Args:
            default_language: язык по умолчанию ('en' или 'ru')
        """
        self.default_language = default_language if default_language in self.SUPPORTED_LANGUAGES else 'ru'
        self.current_language = self.default_language
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.load_translations()
    
    def load_translations(self):
        """Загружает переводы из JSON файлов"""
        for lang in self.SUPPORTED_LANGUAGES:
            trans_file = self.TRANSLATIONS_DIR / f"{lang}.json"
            try:
                with open(trans_file, 'r', encoding='utf-8') as f:
                    self.translations[lang] = json.load(f)
                print(f"[i18n] ✅ Loaded translations for '{lang}'")
            except FileNotFoundError:
                print(f"[i18n] ⚠️ Translation file not found: {trans_file}")
            except json.JSONDecodeError as e:
                print(f"[i18n] ❌ Error parsing {lang}.json: {e}")
    
    def set_language(self, language: str):
        """
        Установить текущий язык
        
        Args:
            language: код языка ('en' или 'ru')
        """
        if language in self.SUPPORTED_LANGUAGES:
            self.current_language = language
        else:
            print(f"[i18n] ⚠️ Unsupported language: {language}, using default: {self.default_language}")
            self.current_language = self.default_language
    
    def get_language(self) -> str:
        """Получить текущий язык"""
        return self.current_language
    
    def t(self, key: str, *args, **kwargs) -> str:
        """
        Получить перевод (translate)
        
        Args:
            key: ключ перевода в формате "section.key" (например "auth.login")
            *args: позиционные аргументы для форматирования
            **kwargs: именованные аргументы для форматирования
        
        Returns:
            Переведённая строка с подставленными значениями
        
        Примеры:
            i18n.t("auth.login")
            i18n.t("search_status.searching_query", 1, 10, "web design")
            i18n.t("search_status.searching_query", index=1, total=10, query="web design")
        """
        # Разбиваем ключ по точкам
        keys = key.split('.')
        
        # Получаем значение из перевода текущего языка
        value = self.translations.get(self.current_language, {})
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                break
        
        # Если перевод не найден, пытаемся получить из английского
        if value is None:
            value = self.translations.get('en', {})
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    break
        
        # Если всё ещё не найден, возвращаем сам ключ
        if value is None:
            return key
        
        # Форматируем строку если передали аргументы
        if args or kwargs:
            try:
                if args:
                    value = value.format(*args)
                if kwargs:
                    value = value.format(**kwargs)
            except (IndexError, KeyError) as e:
                print(f"[i18n] ⚠️ Error formatting key '{key}': {e}")
        
        return str(value)
    
    def _(self, key: str, *args, **kwargs) -> str:
        """Сокращённый вариант t() для частого использования"""
        return self.t(key, *args, **kwargs)
    
    def available_languages(self) -> list:
        """Получить список доступных языков"""
        return self.SUPPORTED_LANGUAGES
    
    def language_name(self, language: str) -> str:
        """Получить название языка на его собственном языке"""
        names = {
            'en': 'English',
            'ru': 'Русский'
        }
        return names.get(language, language)


# Глобальный экземпляр i18n
i18n_instance = I18n(default_language='ru')


def get_i18n() -> I18n:
    """Получить глобальный экземпляр i18n"""
    return i18n_instance


def set_language(language: str):
    """Установить язык глобально"""
    i18n_instance.set_language(language)


def _(key: str, *args, **kwargs) -> str:
    """Сокращённая функция перевода для использования в коде"""
    return i18n_instance.t(key, *args, **kwargs)


# Альтернативное имя функции
t = _


# ─── ТЕСТИРОВАНИЕ ───

if __name__ == "__main__":
    print("\n🧪 Тест i18n модуля\n")
    
    # Получаем экземпляр i18n
    i18n = get_i18n()
    
    print(f"Текущий язык: {i18n.get_language()}")
    print(f"Доступные языки: {i18n.available_languages()}\n")
    
    # Тест 1: Получение переводов на русском
    print("[TEST 1] Переводы на русском")
    print(f"  auth.login: {_('auth.login')}")
    print(f"  search.search_category: {_('search.search_category')}")
    print(f"  common.search: {_('common.search')}\n")
    
    # Тест 2: Переключение на английский
    print("[TEST 2] Переключение на английский")
    set_language('en')
    print(f"  Текущий язык: {i18n.get_language()}")
    print(f"  auth.login: {_('auth.login')}")
    print(f"  search.search_category: {_('search.search_category')}\n")
    
    # Тест 3: Форматирование переводов
    print("[TEST 3] Форматирование переводов")
    set_language('ru')
    msg = _("search_status.searching_query", 1, 10, "web design")
    print(f"  Формированная строка: {msg}\n")
    
    # Тест 4: Форматирование с именованными аргументами
    print("[TEST 4] Форматирование с именованными аргументами")
    msg = _("search_status.starting_product_search", 40)
    print(f"  Результат: {msg}\n")
    
    # Тест 5: Обработка несуществующего ключа
    print("[TEST 5] Несуществующий ключ")
    msg = _("nonexistent.key")
    print(f"  Результат: {msg}\n")
    
    print("✅ Все тесты завершены!")
