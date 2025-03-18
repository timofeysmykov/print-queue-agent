#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import yaml
import logging
import pandas as pd
from pathlib import Path
from gdrive_integration import GoogleDriveIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_gdrive')

def main():
    try:
        # Загрузка конфигурации
        with open('config.yaml', 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        
        # Получение путей из конфигурации
        onedrive_queue_path = config.get('files', {}).get('onedrive_queue_path', '/Print/queue.xlsx')
        local_data_folder = config.get('files', {}).get('local_data_folder', 'data/')
        
        logger.info(f"Путь к файлу очереди в Google Drive: {onedrive_queue_path}")
        logger.info(f"Локальная папка для данных: {local_data_folder}")
        
        # Создание тестового файла Excel
        os.makedirs(local_data_folder, exist_ok=True)
        test_file_path = os.path.join(local_data_folder, 'test_queue.xlsx')
        
        # Создаем простой DataFrame и сохраняем его в Excel
        df = pd.DataFrame({
            'order_id': ['TEST-001', 'TEST-002'],
            'customer': ['Тестовый клиент 1', 'Тестовый клиент 2'],
            'quantity': [100, 200],
            'deadline': ['01.06.2024', '15.06.2024'],
            'status': ['Новый', 'Новый']
        })
        df.to_excel(test_file_path, index=False)
        logger.info(f"Создан тестовый файл: {test_file_path}")
        
        # Инициализация Google Drive API
        logger.info("Инициализация Google Drive API...")
        gd = GoogleDriveIntegration()
        logger.info('Google Drive API инициализирован успешно!')
        
        # Проверка существования папки
        logger.info(f"Проверка пути {onedrive_queue_path}...")
        path_components = onedrive_queue_path.strip('/').split('/')
        folder_name = path_components[0] if len(path_components) > 0 else None
        
        if folder_name:
            logger.info(f"Поиск папки {folder_name} в корневой директории...")
            folder = gd.find_file_by_name(folder_name, "root")
            
            if folder:
                logger.info(f"Папка {folder_name} найдена (ID: {folder['id']})")
                
                # Получение списка файлов в папке
                files = gd.list_files(folder['id'])
                logger.info(f'Найдено файлов в папке {folder_name}: {len(files)}')
                for file in files[:5]:
                    logger.info(f' - {file.get("name")}')
            else:
                logger.warning(f"Папка {folder_name} не найдена, будет создана при загрузке файла")
        
        # Загрузка тестового файла
        logger.info(f"Загрузка тестового файла {test_file_path} в {onedrive_queue_path}...")
        result = gd.upload_file(test_file_path, onedrive_queue_path)
        
        if result:
            logger.info(f"Файл успешно загружен! ID файла: {result.get('id')}")
        else:
            logger.error("Не удалось загрузить файл")
            
    except Exception as e:
        logger.error(f'Ошибка: {str(e)}', exc_info=True)

if __name__ == "__main__":
    main()
