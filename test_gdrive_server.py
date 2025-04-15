#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для тестирования соединения с Google Drive на сервере
"""

import os
import logging
import io
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Импортируем класс для работы с Google Drive
from gdrive_integration import GoogleDriveIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/gdrive_test.log')
    ]
)

logger = logging.getLogger('gdrive_test')

def create_test_document():
    """
    Создает тестовый текстовый документ в Google Drive
    """
    try:
        # Создаем директорию для логов, если она не существует
        Path('logs').mkdir(exist_ok=True)
        
        # Инициализируем интеграцию с Google Drive
        logger.info('Инициализация интеграции с Google Drive')
        drive = GoogleDriveIntegration()
        
        # Создаем временный текстовый файл
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'test_document_{timestamp}.txt'
        filepath = Path('data') / filename
        
        # Создаем директорию data, если она не существует
        Path('data').mkdir(exist_ok=True)
        
        # Содержимое тестового документа
        content = f"""Тестовый документ для проверки соединения с Google Drive
Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Этот файл был создан автоматически для проверки работоспособности интеграции с Google Drive.
"""
        
        # Записываем содержимое в файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f'Создан локальный файл: {filepath}')
        
        # Загружаем файл в Google Drive
        logger.info(f'Загрузка файла в Google Drive: {filename}')
        upload_result = drive.upload_file(filepath, filename)
        
        if upload_result:
            logger.info(f'Файл успешно загружен в Google Drive: {filename}')
            
            # Проверяем, что файл действительно существует в Google Drive
            file_info = drive.find_file_by_name(filename)
            if file_info:
                logger.info(f'Файл найден в Google Drive: ID={file_info.get("id")}')
                return {
                    'success': True,
                    'filename': filename,
                    'file_id': file_info.get('id'),
                    'local_path': str(filepath)
                }
            else:
                logger.error('Файл загружен, но не найден при проверке')
                return {
                    'success': False,
                    'error': 'Файл загружен, но не найден при проверке'
                }
        else:
            logger.error('Не удалось загрузить файл в Google Drive')
            return {
                'success': False,
                'error': 'Не удалось загрузить файл в Google Drive'
            }
            
    except Exception as e:
        logger.error(f'Ошибка при создании тестового документа: {str(e)}')
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    # Загружаем переменные окружения
    load_dotenv()
    
    # Создаем тестовый документ
    result = create_test_document()
    
    if result['success']:
        print(f'\n✅ Тест пройден успешно!')
        print(f'📄 Создан файл: {result["filename"]}')
        print(f'🆔 ID файла: {result["file_id"]}')
        print(f'💾 Локальный путь: {result["local_path"]}')
    else:
        print(f'\n❌ Тест не пройден!')
        print(f'⚠️ Ошибка: {result.get("error", "Неизвестная ошибка")}')
