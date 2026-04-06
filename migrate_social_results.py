#!/usr/bin/env python3
"""
Скрипт миграции БД для добавления AI оценок в таблицу social_results
Добавляет колонки: design_score, ux_score, design_text, ux_text
"""

import sqlite3
import sys
import io

# Исправляем кодировку на Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB_PATH = "tish_data.db"

def migrate():
    """Добавляет новые колонки в таблицу social_results"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем существующие колонки
        cursor.execute("PRAGMA table_info(social_results)")
        columns = {row[1] for row in cursor.fetchall()}
        
        print(f"[Migration] Текущие колонки: {columns}")
        
        # Добавляем недостающие колонки
        changes = []
        
        if "design_score" not in columns:
            cursor.execute("ALTER TABLE social_results ADD COLUMN design_score INTEGER DEFAULT 5")
            changes.append("✓ Добавлена колонка: design_score")
            print("[Migration] Added: design_score INTEGER DEFAULT 5")
        
        if "ux_score" not in columns:
            cursor.execute("ALTER TABLE social_results ADD COLUMN ux_score INTEGER DEFAULT 5")
            changes.append("✓ Добавлена колонка: ux_score")
            print("[Migration] Added: ux_score INTEGER DEFAULT 5")
        
        if "design_text" not in columns:
            cursor.execute("ALTER TABLE social_results ADD COLUMN design_text TEXT")
            changes.append("✓ Добавлена колонка: design_text")
            print("[Migration] Added: design_text TEXT")
        
        if "ux_text" not in columns:
            cursor.execute("ALTER TABLE social_results ADD COLUMN ux_text TEXT")
            changes.append("✓ Добавлена колонка: ux_text")
            print("[Migration] Added: ux_text TEXT")
        
        # Проверяем результат
        cursor.execute("PRAGMA table_info(social_results)")
        new_columns = [row[1] for row in cursor.fetchall()]
        
        conn.commit()
        conn.close()
        
        print(f"\n[Migration] ✅ Миграция завершена успешно!")
        print(f"[Migration] Новые колонки таблицы: {new_columns}")
        print("\n".join(changes) if changes else "[Migration] Никаких изменений не требовалось")
        
        return True
    
    except sqlite3.OperationalError as e:
        print(f"[Migration] ❌ Ошибка при миграции: {e}")
        return False
    except Exception as e:
        print(f"[Migration] ❌ Неожиданная ошибка: {e}")
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
