#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Простой скрипт для тестирования соединения с Google Drive
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Импортируем класс для работы с Google Drive
from gdrive_integration import GoogleDriveIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("gdrive_test")

def main():
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем наличие необходимых переменных окружения
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        logger.error("Отсутствует GOOGLE_DRIVE_FOLDER_ID в .env файле")
        return
    
    logger.info(f"Используем GOOGLE_DRIVE_FOLDER_ID: {folder_id}")
    
    try:
        # Инициализируем интеграцию с Google Drive
        drive = GoogleDriveIntegration()
        
        # Создаем тестовый документ
        logger.info("Запуск тестирования создания документов")
        results = drive.create_test_document()
        
        if results["success"]:
            logger.info("✅ Тест пройден успешно!")
            logger.info(f"📄 Созданные файлы: {', '.join(results['created_files'])}")
            logger.info(f"🆔 ID файла: {results.get('file_id')}")
            logger.info(f"💾 Локальный путь: {results.get('local_file')}")
        else:
            logger.error("❌ Тест не пройден!")
            if results.get("errors"):
                for error in results["errors"]:
                    logger.error(f"⚠️ Ошибка: {error}")
    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")

if __name__ == "__main__":
    main()
