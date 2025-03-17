#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки работы с Excel-файлами в Google Drive
"""

import os
import pandas as pd
from pathlib import Path
from gdrive_integration import GoogleDriveIntegration

def main():
    """Основная функция для проверки работы с Excel-файлами"""
    # Инициализируем интеграцию с Google Drive
    drive = GoogleDriveIntegration()
    
    # 1. Создаем тестовую папку
    test_folder_path = "/TestFolder"
    print(f"Создание тестовой папки: {test_folder_path}")
    
    # Проверяем, существует ли папка, и если нет, то создаем
    folder = drive.find_file_by_path(test_folder_path)
    if not folder:
        root_folder = drive.create_folder("TestFolder")
        print(f"Папка создана с ID: {root_folder['id']}")
    else:
        print(f"Папка уже существует с ID: {folder['id']}")
    
    # 2. Создание нового Excel-файла
    print("\nСоздание нового Excel-файла...")
    
    # Создаем DataFrame с тестовыми данными
    data = {
        'Имя': ['Иванов Иван', 'Петров Петр', 'Сидорова Анна'],
        'Возраст': [25, 30, 28],
        'Должность': ['Инженер', 'Менеджер', 'Дизайнер'],
        'Дата': ['2025-03-17', '2025-03-16', '2025-03-15']
    }
    df = pd.DataFrame(data)
    
    # Сохраняем DataFrame в локальный Excel-файл
    local_excel_path = "data/test_excel.xlsx"
    df.to_excel(local_excel_path, index=False)
    print(f"Локальный файл создан: {local_excel_path}")
    
    # Загружаем файл в Google Drive
    drive_path = f"{test_folder_path}/test_excel.xlsx"
    file_info = drive.upload_file(local_excel_path, drive_path)
    print(f"Файл загружен в Google Drive: {drive_path} (ID: {file_info.get('id', 'Нет ID')})")
    
    # 3. Скачивание Excel-файла из Google Drive
    print("\nСкачивание файла из Google Drive...")
    downloaded_file_path = drive.download_file(drive_path, "data/downloaded_excel.xlsx")
    print(f"Файл скачан: {downloaded_file_path}")
    
    # 4. Чтение и модификация файла
    print("\nИзменение Excel-файла...")
    downloaded_df = pd.read_excel(downloaded_file_path)
    print("Текущее содержимое файла:")
    print(downloaded_df)
    
    # Добавляем новую строку
    new_row = {'Имя': 'Смирнов Алексей', 'Возраст': 35, 'Должность': 'Директор', 'Дата': '2025-03-14'}
    modified_df = pd.concat([downloaded_df, pd.DataFrame([new_row])], ignore_index=True)
    
    # Сохраняем изменения
    modified_file_path = "data/modified_excel.xlsx"
    modified_df.to_excel(modified_file_path, index=False)
    print("Файл модифицирован, добавлена новая строка")
    
    # 5. Загружаем измененный файл обратно в Google Drive
    print("\nЗагрузка измененного файла обратно в Google Drive...")
    updated_file_info = drive.upload_file(modified_file_path, drive_path)
    print(f"Измененный файл загружен в Google Drive: {drive_path} (ID: {updated_file_info.get('id', 'Нет ID')})")
    
    print("\nВсе тесты выполнены успешно!")

if __name__ == "__main__":
    main()
