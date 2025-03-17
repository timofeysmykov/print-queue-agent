"""
Модуль для интеграции с Google Drive.
Обеспечивает функциональность аутентификации, скачивания и загрузки файлов.
"""

import os
import logging
import json
import yaml
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/gdrive.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("gdrive_integration")

class GoogleDriveIntegration:
    """Класс для работы с Google Drive."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация интеграции с Google Drive.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        
        # Создание локальной директории для данных, если она не существует
        local_data_folder = self.config.get('files', {}).get('local_data_folder', 'data/')
        self.local_data_path = Path(local_data_folder)
        self.local_data_path.mkdir(exist_ok=True, parents=True)
        
        # Получение учетных данных
        self.service_account_key = os.getenv("GOOGLE_DRIVE_KEY")
        
        if not self.service_account_key:
            logger.error("Отсутствуют учетные данные Google Drive API")
            raise ValueError("Необходимо указать GOOGLE_DRIVE_KEY в .env файле")
        
        # Инициализация клиента Google Drive
        try:
            # Преобразуем строку JSON в словарь
            key_info = json.loads(self.service_account_key)
            
            # Создаем учетные данные
            self.credentials = service_account.Credentials.from_service_account_info(
                key_info, 
                scopes=['https://www.googleapis.com/auth/drive']
            )
            
            # Создаем клиент Drive API
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            logger.info("Google Drive API клиент успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Drive API: {str(e)}")
            raise
    
    def list_files(self, folder_id="root"):
        """
        Получение списка файлов из указанной папки Google Drive.
        
        Args:
            folder_id (str): ID папки в Google Drive. По умолчанию "root" для корневой папки.
            
        Returns:
            list: Список файлов и папок.
        """
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name, mimeType, createdTime, modifiedTime, size)",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"Получен список из {len(files)} файлов и папок")
            return files
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов: {str(e)}")
            raise
    
    def find_file_by_name(self, file_name, folder_id="root"):
        """
        Поиск файла по имени в указанной папке.
        
        Args:
            file_name (str): Имя файла.
            folder_id (str): ID папки в Google Drive. По умолчанию "root" для корневой папки.
            
        Returns:
            dict: Информация о найденном файле или None, если файл не найден.
        """
        try:
            query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name, mimeType)",
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            return files[0] if files else None
        except Exception as e:
            logger.error(f"Ошибка при поиске файла {file_name}: {str(e)}")
            raise
    
    def find_file_by_path(self, path):
        """
        Поиск файла по пути (например, '/Print/orders.xlsx').
        
        Args:
            path (str): Путь к файлу.
            
        Returns:
            dict: Информация о найденном файле или None, если файл не найден.
        """
        # Разделение пути на компоненты
        components = [comp for comp in path.strip('/').split('/') if comp]
        
        if not components:
            logger.error("Пустой путь к файлу")
            return None
        
        parent_id = "root"
        
        # Навигация по директориям
        for i, component in enumerate(components):
            is_last = (i == len(components) - 1)
            
            if is_last:
                # Ищем файл в текущей директории
                return self.find_file_by_name(component, parent_id)
            else:
                # Ищем папку
                folder = self.find_file_by_name(component, parent_id)
                if not folder:
                    logger.error(f"Папка {component} не найдена")
                    return None
                parent_id = folder['id']
        
        return None
    
    def download_file(self, file_path, local_filename=None):
        """
        Скачивание файла из Google Drive.
        
        Args:
            file_path (str): Путь к файлу в Google Drive (например, '/Print/orders.xlsx').
            local_filename (str, optional): Локальное имя файла. Если не указано, 
                                           используется имя из Google Drive.
                                           
        Returns:
            str: Путь к скачанному файлу.
        """
        try:
            # Поиск файла по пути
            file_info = self.find_file_by_path(file_path)
            
            if not file_info:
                logger.error(f"Файл {file_path} не найден")
                raise FileNotFoundError(f"Файл {file_path} не найден в Google Drive")
            
            # Определение имени файла
            if not local_filename:
                local_filename = file_info['name']
            
            # Формирование пути для сохранения
            local_path = self.local_data_path / local_filename
            
            # Скачивание файла
            request = self.drive_service.files().get_media(fileId=file_info['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.debug(f"Скачивание {file_path}: {int(status.progress() * 100)}%")
            
            # Сохранение файла
            with open(local_path, 'wb') as f:
                f.write(fh.getvalue())
            
            logger.info(f"Файл {file_path} успешно скачан как {local_path}")
            return str(local_path)
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла {file_path}: {str(e)}")
            raise
    
    def upload_file(self, local_path, drive_path):
        """
        Загрузка файла в Google Drive.
        
        Args:
            local_path (str): Путь к локальному файлу.
            drive_path (str): Путь назначения в Google Drive (например, '/Print/orders.xlsx').
            
        Returns:
            dict: Информация о загруженном файле.
        """
        # Проверка существования файла
        if not os.path.exists(local_path):
            logger.error(f"Локальный файл {local_path} не существует")
            raise FileNotFoundError(f"Файл {local_path} не найден")
        
        try:
            # Разделение пути на директорию и имя файла
            path_components = drive_path.strip('/').split('/')
            filename = path_components[-1]
            parent_path = '/'.join(path_components[:-1])
            
            # Получение ID родительской директории
            parent_id = "root"
            if parent_path:
                for folder_name in parent_path.split('/'):
                    folder = self.find_file_by_name(folder_name, parent_id)
                    if not folder:
                        # Создаем папку
                        folder = self.create_folder(folder_name, parent_id)
                    parent_id = folder['id']
            
            # Проверка, существует ли файл с таким именем
            existing_file = self.find_file_by_name(filename, parent_id)
            
            # Определение MIME типа файла
            file_extension = os.path.splitext(local_path)[1].lower()
            mime_type = "application/octet-stream"  # По умолчанию
            
            if file_extension == '.xlsx':
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif file_extension == '.csv':
                mime_type = "text/csv"
            elif file_extension == '.txt':
                mime_type = "text/plain"
            
            # Создание медиа объекта для загрузки
            media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
            
            if existing_file:
                # Обновление существующего файла
                file_metadata = {
                    'name': filename,
                    'mimeType': mime_type
                }
                file = self.drive_service.files().update(
                    fileId=existing_file['id'],
                    body=file_metadata,
                    media_body=media
                ).execute()
                logger.info(f"Файл {drive_path} успешно обновлен (ID: {file['id']})")
            else:
                # Создание нового файла
                file_metadata = {
                    'name': filename,
                    'parents': [parent_id],
                    'mimeType': mime_type
                }
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                logger.info(f"Файл {drive_path} успешно загружен (ID: {file['id']})")
            
            return file
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {drive_path}: {str(e)}")
            raise
    
    def create_folder(self, folder_name, parent_id="root"):
        """
        Создание папки в Google Drive.
        
        Args:
            folder_name (str): Имя создаваемой папки.
            parent_id (str): ID родительской папки. По умолчанию "root" для корневой папки.
            
        Returns:
            dict: Информация о созданной папке.
        """
        try:
            # Проверка существования папки
            existing_folder = self.find_file_by_name(folder_name, parent_id)
            if existing_folder:
                logger.info(f"Папка {folder_name} уже существует (ID: {existing_folder['id']})")
                return existing_folder
            
            # Создание новой папки
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id, name, mimeType'
            ).execute()
            
            logger.info(f"Папка {folder_name} успешно создана (ID: {folder['id']})")
            return folder
        except Exception as e:
            logger.error(f"Ошибка при создании папки {folder_name}: {str(e)}")
            raise
    
    def delete_file(self, file_path):
        """
        Удаление файла из Google Drive.
        
        Args:
            file_path (str): Путь к файлу в Google Drive.
            
        Returns:
            bool: True если удаление успешно.
        """
        try:
            # Поиск файла по пути
            file_info = self.find_file_by_path(file_path)
            
            if not file_info:
                logger.error(f"Файл {file_path} не найден")
                return False
            
            # Удаление файла
            self.drive_service.files().delete(fileId=file_info['id']).execute()
            logger.info(f"Файл {file_path} успешно удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")
            raise


if __name__ == "__main__":
    # Пример использования
    try:
        # Инициализация
        gdrive = GoogleDriveIntegration()
        
        # Вывод списка файлов в корневой папке
        files = gdrive.list_files()
        print("Файлы в корневой папке:")
        for file in files:
            print(f" - {file.get('name')} (ID: {file.get('id')})")
        
        # Другие примеры (закомментированы для безопасности)
        # local_file = gdrive.download_file("/Documents/example.xlsx")
        # print(f"Файл скачан: {local_file}")
        
        # uploaded = gdrive.upload_file("local_file.xlsx", "/Documents/uploaded.xlsx")
        # print(f"Файл загружен: {uploaded.get('id')}")
    except Exception as e:
        print(f"Ошибка: {str(e)}")
