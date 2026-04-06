# TISH SEARCH v4 - Automatic Database Backup Script
# Автоматическое резервное копирование базы данных
# Запуск: python backup.py

import os
import shutil
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════

DB_FILE = "tish_data.db"
BACKUP_DIR = Path("backups")
MAX_BACKUPS = 30  # Хранить последние 30 бэкапов

# ═══════════════════════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════════════════════

def create_backup():
    """Создать резервную копию базы данных"""
    
    # Создаём директорию для бэкапов
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Проверяем что БД существует
    if not Path(DB_FILE).exists():
        print(f"❌ База данных не найдена: {DB_FILE}")
        return False
    
    # Генерируем имя файла с датой
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"tish_data_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name
    
    try:
        # Копируем БД
        shutil.copy2(DB_FILE, backup_path)
        
        # Получаем размер
        size_mb = backup_path.stat().st_size / 1024 / 1024
        
        print(f"✅ Бэкап создан: {backup_name}")
        print(f"   Размер: {size_mb:.2f} MB")
        print(f"   Путь: {backup_path.absolute()}")
        
        # Очищаем старые бэкапы
        cleanup_old_backups()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании бэкапа: {e}")
        return False

def cleanup_old_backups():
    """Удалить старые бэкапы (оставить только MAX_BACKUPS последних)"""
    try:
        backups = sorted(BACKUP_DIR.glob("tish_data_*.db"))
        
        if len(backups) > MAX_BACKUPS:
            to_delete = backups[:-MAX_BACKUPS]
            
            for old_backup in to_delete:
                old_backup.unlink()
                print(f"🗑️  Удалён старый бэкап: {old_backup.name}")
            
            print(f"   Осталось бэкапов: {MAX_BACKUPS}")
            
    except Exception as e:
        print(f"⚠️  Ошибка при очистке: {e}")

def list_backups():
    """Показать список всех бэкапов"""
    backups = sorted(BACKUP_DIR.glob("tish_data_*.db"), reverse=True)
    
    if not backups:
        print("📭 Нет бэкапов")
        return
    
    print(f"\n📦 Доступные бэкапы ({len(backups)}):")
    print("-" * 60)
    
    for i, backup in enumerate(backups[:10], 1):  # Показываем 10 последних
        size_mb = backup.stat().st_size / 1024 / 1024
        date = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        print(f"  {i}. {backup.name:30s} {size_mb:6.2f} MB  {date}")
    
    if len(backups) > 10:
        print(f"  ... и ещё {len(backups) - 10} бэкапов")

def restore_backup(backup_name=None):
    """Восстановить БД из бэкапа"""
    backups = sorted(BACKUP_DIR.glob("tish_data_*.db"), reverse=True)
    
    if not backups:
        print("❌ Нет бэкапов для восстановления")
        return False
    
    # Если не указан конкретный бэкап, берём последний
    if backup_name:
        backup_path = BACKUP_DIR / backup_name
        if not backup_path.exists():
            print(f"❌ Бэкап не найден: {backup_name}")
            return False
    else:
        backup_path = backups[0]
    
    try:
        # Создаём бэкап текущей БД перед восстановлением
        if Path(DB_FILE).exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_restore_backup = BACKUP_DIR / f"pre_restore_{timestamp}.db"
            shutil.copy2(DB_FILE, pre_restore_backup)
            print(f"💾 Создан бэкап текущей БД: {pre_restore_backup.name}")
        
        # Восстанавливаем
        shutil.copy2(backup_path, DB_FILE)
        print(f"✅ БД восстановлена из: {backup_path.name}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при восстановлении: {e}")
        return False

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    import sys
    
    print("=" * 60)
    print("  TISH SEARCH v4 - Database Backup Tool")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "backup":
            create_backup()
            
        elif command == "list":
            list_backups()
            
        elif command == "restore":
            backup_name = sys.argv[2] if len(sys.argv) > 2 else None
            if backup_name or input("Восстановить из последнего бэкапа? (y/n): ").lower() == 'y':
                restore_backup(backup_name)
                
        elif command == "help":
            print("Команды:")
            print("  backup          - Создать бэкап")
            print("  list            - Показать список бэкапов")
            print("  restore [name]  - Восстановить из бэкапа")
            print("  help            - Показать справку")
            
        else:
            print(f"❌ Неизвестная команда: {command}")
            
    else:
        # По умолчанию создаём бэкап
        create_backup()

if __name__ == "__main__":
    main()
