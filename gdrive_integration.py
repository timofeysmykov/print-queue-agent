"""
Модуль для интеграции с Google Drive.
Обеспечивает функциональность аутентификации, скачивания и загрузки файлов.
"""

import os
import logging
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import io
import time

from google.oauth2 import service_account
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

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
    
    def __init__(self):
        """
        Инициализация интеграции с Google Drive.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Создание локальной директории для данных, если она не существует
        self.local_data_path = Path("data/")
        self.local_data_path.mkdir(exist_ok=True, parents=True)
        
        # Получение ID папки Google Drive из .env
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not self.folder_id:
            logger.error("Отсутствует ID папки Google Drive в .env файле")
            raise ValueError("Необходимо указать GOOGLE_DRIVE_FOLDER_ID в .env файле")
        
        # Инициализация клиента Google Drive
        try:
            # Создаем учетные данные из переменных окружения
            self.credentials = self._create_credentials_from_env()
            
            # Создаем клиент Drive API
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            
            # Сохраняем последнюю проверку изменений файлов
            self.last_check_time = datetime.now()
            
            logger.info("Google Drive API клиент успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Drive API: {str(e)}")
            raise
    
    def _create_credentials_from_env(self) -> Credentials:
        """
        Создает учетные данные Google API из переменных окружения.
        
        Returns:
            Credentials: Объект учетных данных для Google API.
        """
        try:
            # Создаем словарь с учетными данными из переменных окружения
            credentials_dict = {
                "type": os.getenv("GOOGLE_DRIVE_CREDS_TYPE", "service_account"),
                "project_id": os.getenv("GOOGLE_DRIVE_PROJECT_ID"),
                "private_key_id": os.getenv("GOOGLE_DRIVE_PRIVATE_KEY_ID"),
                "private_key": os.getenv("GOOGLE_DRIVE_PRIVATE_KEY").replace('\\n', '\n'),
                "client_email": os.getenv("GOOGLE_DRIVE_CLIENT_EMAIL"),
                "client_id": os.getenv("GOOGLE_DRIVE_CLIENT_ID"),
                "auth_uri": os.getenv("GOOGLE_DRIVE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri": os.getenv("GOOGLE_DRIVE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                "auth_provider_x509_cert_url": os.getenv("GOOGLE_DRIVE_AUTH_PROVIDER_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
                "client_x509_cert_url": os.getenv("GOOGLE_DRIVE_CLIENT_CERT_URL"),
                "universe_domain": os.getenv("GOOGLE_DRIVE_UNIVERSE_DOMAIN", "googleapis.com")
            }
            
            # Создаем учетные данные из словаря
            credentials = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            
            return credentials
        except Exception as e:
            logger.error(f"Ошибка при создании учетных данных: {str(e)}")
            raise
    
    def list_files(self, query=None):
        """
        Получение списка файлов из папки Google Drive.
        
        Args:
            query (str, optional): Дополнительное условие запроса.
        
        Returns:
            list: Список файлов и папок.
        """
        try:
            base_query = f"'{self.folder_id}' in parents and trashed = false"
            
            if query:
                final_query = f"{base_query} and {query}"
            else:
                final_query = base_query
                
            results = self.drive_service.files().list(
                q=final_query,
                fields="files(id, name, mimeType, createdTime, modifiedTime, size)",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"Получен список из {len(files)} файлов и папок")
            return files
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов: {str(e)}")
            return []
    
    def find_file_by_name(self, file_name):
        """
        Поиск файла по имени в папке Google Drive.
        
        Args:
            file_name (str): Имя файла.
            
        Returns:
            dict: Информация о найденном файле или None, если файл не найден.
        """
        try:
            query = f"'{self.folder_id}' in parents and name='{file_name}' and trashed = false"
            
            response = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields="files(id, name, mimeType, modifiedTime)",
                pageSize=10  # Нам нужен только один файл
            ).execute()
            
            files = response.get('files', [])
            
            if files:
                logger.info(f"Найден файл: {file_name} (ID: {files[0].get('id')})")
                return files[0]
            else:
                logger.info(f"Файл '{file_name}' не найден в папке Google Drive.")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при поиске файла {file_name}: {str(e)}")
            return None
    
    def download_file(self, file_name, local_path=None):
        """
        Скачивание файла из Google Drive по имени.
        
        Args:
            file_name (str): Имя файла в Google Drive.
            local_path (str/Path, optional): Локальный путь для сохранения. 
                                           Если не указан, файл сохраняется в data/.
        
        Returns:
            str: Путь к скачанному файлу или None при ошибке.
        """
        try:
            # Поиск файла по имени
            file_info = self.find_file_by_name(file_name)
            
            if not file_info:
                logger.error(f"Файл {file_name} не найден в Google Drive")
                return None
            
            file_id = file_info['id']
            
            # Определяем путь для сохранения файла
            if not local_path:
                local_path = self.local_data_path / file_name
            else:
                local_path = Path(local_path)
            
            # Создаем директории, если их нет
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Скачивание файла
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logger.debug(f"Скачивание {int(status.progress() * 100)}% завершено")
            
            logger.info(f"Файл {file_name} успешно скачан: {local_path}")
            return str(local_path)
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла {file_name}: {str(e)}")
            return None
    
    def upload_file(self, local_file_path, file_name=None):
        """
        Загрузка файла в Google Drive.
        
        Args:
            local_file_path (str/Path): Локальный путь к файлу для загрузки.
            file_name (str, optional): Имя файла в Google Drive. 
                                     Если не указано, используется имя локального файла.
        
        Returns:
            bool: True если загрузка успешна, иначе False.
        """
        try:
            local_path = Path(local_file_path)
            
            # Проверка существования файла
            if not local_path.exists():
                logger.error(f"Локальный файл не найден: {local_file_path}")
                return False
            
            # Определение имени файла
            if not file_name:
                file_name = local_path.name
            
            # Проверяем существует ли файл с таким именем
            existing_file = self.find_file_by_name(file_name)
            
            # Создаем медиа-объект для загрузки
            media = MediaFileUpload(
                local_path,
                resumable=True
            )
            
            if existing_file:
                # Обновление существующего файла
                file_id = existing_file['id']
                request = self.drive_service.files().update(
                    fileId=file_id,
                    media_body=media
                )
                logger.info(f"Обновление существующего файла: {file_name}")
            else:
                # Создание нового файла
                file_metadata = {
                    'name': file_name,
                    'parents': [self.folder_id]
                }
                request = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                )
                logger.info(f"Создание нового файла: {file_name}")
            
            # Выполнение запроса на загрузку
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.debug(f"Загрузка {int(status.progress() * 100)}% завершена")
            
            logger.info(f"Файл успешно загружен: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {local_file_path}: {str(e)}")
            return False
    
    def create_folder(self, folder_name, parent_id=None):
        """
        Создание новой папки в Google Drive.
        
        Args:
            folder_name (str): Имя папки.
            parent_id (str, optional): ID родительской папки. 
                                     Если не указано, создается в корневой папке.
        
        Returns:
            str: ID созданной папки или None при ошибке.
        """
        try:
            if not parent_id:
                parent_id = self.folder_id
            
            # Проверка существования папки
            existing_folder = self.find_file_by_name(folder_name)
            if existing_folder and existing_folder.get('mimeType') == 'application/vnd.google-apps.folder':
                logger.info(f"Папка '{folder_name}' уже существует, ID: {existing_folder['id']}")
                return existing_folder['id']
            
            # Создание метаданных папки
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            
            # Создание папки
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"Создана новая папка '{folder_name}', ID: {folder_id}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Ошибка при создании папки {folder_name}: {str(e)}")
            return None
    
    def delete_file(self, file_name):
        """
        Удаление файла из Google Drive.
        
        Args:
            file_name (str): Имя файла для удаления.
        
        Returns:
            bool: True если удаление успешно, иначе False.
        """
        try:
            # Поиск файла
            file_info = self.find_file_by_name(file_name)
            
            if not file_info:
                logger.warning(f"Файл {file_name} не найден для удаления")
                return False
            
            # Удаление файла
            self.drive_service.files().delete(fileId=file_info['id']).execute()
            
            logger.info(f"Файл {file_name} успешно удален")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {file_name}: {str(e)}")
            return False
    
    def watch_folder(self):
        """
        Проверяет изменения в папке Google Drive с момента последней проверки.
        
        Returns:
            list: Список измененных файлов.
        """
        try:
            current_time = datetime.now()
            
            # Формируем запрос для поиска измененных после последней проверки файлов
            modified_time = self.last_check_time.strftime("%Y-%m-%dT%H:%M:%S")
            query = f"modifiedTime > '{modified_time}'"
            
            # Получаем список измененных файлов
            modified_files = self.list_files(query)
            
            # Обновляем время последней проверки
            self.last_check_time = current_time
            
            if modified_files:
                logger.info(f"Обнаружено {len(modified_files)} изменений в папке Google Drive")
            
            return modified_files
            
        except Exception as e:
            logger.error(f"Ошибка при проверке изменений в папке: {str(e)}")
            return []
    
    def get_file_content_as_string(self, file_name):
        """
        Получает содержимое текстового файла как строку.
        
        Args:
            file_name (str): Имя файла в Google Drive.
        
        Returns:
            str: Содержимое файла или None при ошибке.
        """
        try:
            # Поиск файла по имени
            file_info = self.find_file_by_name(file_name)
            
            if not file_info:
                logger.error(f"Файл {file_name} не найден в Google Drive")
                return None
            
            file_id = file_info['id']
            
            # Скачивание содержимого файла в память
            request = self.drive_service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            
            downloader = MediaIoBaseDownload(file_content, request)
            done = False
            while done is False:
                _, done = downloader.next_chunk()
                
            file_content.seek(0)
            content = file_content.read().decode('utf-8')
            
            logger.info(f"Файл {file_name} успешно прочитан")
            return content
            
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_name}: {str(e)}")
            return None
            
    def watch_for_txt_files(self, orders_folder_name="Новые заказы"):
        """
        Проверяет наличие новых текстовых файлов в указанной папке.
        
        Args:
            orders_folder_name (str): Имя папки с новыми заказами
            
        Returns:
            list: Список новых текстовых файлов.
        """
        try:
            # Найдем папку с заказами
            folder_info = self.find_file_by_name(orders_folder_name)
            if not folder_info:
                logger.warning(f"Папка {orders_folder_name} не найдена в Google Drive")
                return []
                
            folder_id = folder_info['id']
            
            # Получаем список текстовых файлов
            query = f"'{folder_id}' in parents and (mimeType='text/plain' or name contains '.txt' or name contains '.md')"
            
            response = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields="files(id, name, mimeType, modifiedTime)",
                pageSize=100
            ).execute()
            
            files = response.get('files', [])
            
            if files:
                logger.info(f"Найдено {len(files)} текстовых файлов в папке {orders_folder_name}")
            
            return files
                
        except Exception as e:
            logger.error(f"Ошибка при поиске текстовых файлов: {str(e)}")
            return []
    
    def excel_test(self, folder_link=""):
        """
        Тестовая функция для работы с Excel файлами в Google Drive.
        Создает и загружает Excel файл с тестовыми данными.
        
        Args:
            folder_link (str): Ссылка на папку в Google Drive (опционально)
            
        Returns:
            dict: Результаты тестирования с информацией о созданных файлах
        """
        import pandas as pd
        import numpy as np
        from datetime import datetime
        
        logger.info("Начало тестирования работы с Excel файлами")
        
        results = {
            "success": False, 
            "created_files": [],
            "errors": []
        }
        
        try:
            # Если передана ссылка на папку, пробуем извлечь ID
            if folder_link and "drive.google.com" in folder_link:
                # Извлекаем ID папки из ссылки
                import re
                folder_id_match = re.search(r"folders/([a-zA-Z0-9_-]+)", folder_link)
                if folder_id_match:
                    test_folder_id = folder_id_match.group(1)
                    logger.info(f"Извлечен ID папки: {test_folder_id}")
                    # Временно сохраняем старый ID и устанавливаем новый
                    old_folder_id = self.folder_id
                    self.folder_id = test_folder_id
                    results["folder_id"] = test_folder_id
                else:
                    logger.warning(f"Не удалось извлечь ID папки из ссылки: {folder_link}")
                    results["errors"].append("Не удалось извлечь ID папки из ссылки")
            
            # 1. Создаем временную директорию для тестов
            from pathlib import Path
            test_dir = Path("data/test_excel")
            test_dir.mkdir(exist_ok=True, parents=True)
            
            # 2. Создаем DataFrame с тестовыми данными заказов
            test_data = {
                "ID": [1, 2, 3],
                "Клиент": ["ООО Тест", "ИП Иванов", "АО Пример"],
                "Заказ": ["Визитки 100 шт.", "Баннер 2x3м", "Буклеты A4 50 шт."],
                "Дата создания": [datetime.now(), datetime.now(), datetime.now()],
                "Срок исполнения": ["21.03.2025", "22.03.2025", "25.03.2025"],
                "Статус": ["Новый", "Новый", "Новый"]
            }
            
            df = pd.DataFrame(test_data)
            
            # 3. Сохраняем Excel файл локально
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_filename = f"test_orders_{timestamp}.xlsx"
            excel_path = test_dir / excel_filename
            
            df.to_excel(excel_path, index=False, engine='openpyxl')
            logger.info(f"Создан локальный Excel файл: {excel_path}")
            results["local_file"] = str(excel_path)
            
            # 4. Загружаем файл в Google Drive
            upload_result = self.upload_file(excel_path, excel_filename)
            if upload_result:
                logger.info(f"Excel файл успешно загружен в Google Drive: {excel_filename}")
                results["created_files"].append(excel_filename)
            else:
                logger.error("Не удалось загрузить Excel файл в Google Drive")
                results["errors"].append("Ошибка загрузки Excel файла")
                return results
            
            # 5. Пробуем найти загруженный файл
            file_info = self.find_file_by_name(excel_filename)
            if file_info:
                logger.info(f"Файл найден в Google Drive: {file_info.get('id')}")
                results["file_id"] = file_info.get('id')
            else:
                logger.error(f"Не удалось найти загруженный файл: {excel_filename}")
                results["errors"].append("Ошибка поиска загруженного файла")
                return results
            
            # 6. Скачиваем файл с новым именем для проверки
            download_filename = f"downloaded_{excel_filename}"
            download_path = test_dir / download_filename
            
            download_result = self.download_file(excel_filename, download_path)
            if download_result:
                logger.info(f"Excel файл успешно скачан: {download_path}")
                results["downloaded_file"] = str(download_path)
            else:
                logger.error("Не удалось скачать Excel файл из Google Drive")
                results["errors"].append("Ошибка скачивания Excel файла")
                return results
            
            # 7. Загружаем скачанный файл и проверяем данные
            try:
                downloaded_df = pd.read_excel(download_path, engine='openpyxl')
                if len(downloaded_df) == len(df):
                    logger.info("Проверка данных Excel файла прошла успешно")
                    results["data_verification"] = "OK"
                else:
                    logger.warning("Количество строк в скачанном файле не совпадает с оригиналом")
                    results["data_verification"] = "WARNING: размер данных не совпадает"
            except Exception as e:
                logger.error(f"Ошибка при проверке скачанного файла: {str(e)}")
                results["errors"].append(f"Ошибка проверки скачанного файла: {str(e)}")
            
            # Если дошли до этой точки без критических ошибок, тест успешен
            results["success"] = len(results["errors"]) == 0
            
            # Восстанавливаем исходный ID папки, если он был изменен
            if folder_link and "drive.google.com" in folder_link and "old_folder_id" in locals():
                self.folder_id = old_folder_id
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при тестировании Excel файлов: {str(e)}")
            results["errors"].append(str(e))
            
            # Восстанавливаем исходный ID папки, если он был изменен
            if folder_link and "drive.google.com" in folder_link and "old_folder_id" in locals():
                self.folder_id = old_folder_id
                
            return results
    
    def create_test_document(self):
        """
        Создает тестовый текстовый документ в Google Drive для проверки соединения.
        
        Returns:
            dict: Результаты тестирования с информацией о созданном файле
        """
        logger.info("Начало тестирования создания текстового документа")
        
        results = {
            "success": False, 
            "created_files": [],
            "errors": []
        }
        
        try:
            # Создаем временную директорию для тестов
            test_dir = Path("data/test_docs")
            test_dir.mkdir(exist_ok=True, parents=True)
            
            # Создаем тестовый текстовый файл
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            txt_filename = f"test_document_{timestamp}.txt"
            txt_path = test_dir / txt_filename
            
            # Содержимое тестового документа
            content = f"""Тестовый документ для проверки соединения с Google Drive
Создан: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Этот файл был создан автоматически для проверки работоспособности интеграции с Google Drive.
"""
            
            # Записываем содержимое в файл
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"Создан локальный текстовый файл: {txt_path}")
            results["local_file"] = str(txt_path)
            
            # Загружаем файл в Google Drive
            upload_result = self.upload_file(txt_path, txt_filename)
            if upload_result:
                logger.info(f"Текстовый файл успешно загружен в Google Drive: {txt_filename}")
                results["created_files"].append(txt_filename)
            else:
                logger.error("Не удалось загрузить текстовый файл в Google Drive")
                results["errors"].append("Ошибка загрузки текстового файла")
                return results
            
            # Проверяем, что файл существует в Google Drive
            file_info = self.find_file_by_name(txt_filename)
            if file_info:
                logger.info(f"Файл найден в Google Drive: {file_info.get('id')}")
                results["file_id"] = file_info.get('id')
                results["success"] = True
            else:
                logger.error(f"Не удалось найти загруженный файл: {txt_filename}")
                results["errors"].append("Ошибка поиска загруженного файла")
                
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при создании тестового документа: {str(e)}")
            results["errors"].append(str(e))
            return results
    
if __name__ == "__main__":
    # Пример использования
    try:
        drive = GoogleDriveIntegration()
        
        # Получение списка файлов
        files = drive.list_files()
        print(f"Найдено {len(files)} файлов в папке Google Drive:")
        for file in files:
            print(f"- {file.get('name')} ({file.get('id')})")
        
        # Пример мониторинга изменений
        print("\nМониторинг изменений (проверка каждые 10 секунд, 3 раза):")
        for i in range(3):
            time.sleep(10)
            changes = drive.watch_folder()
            if changes:
                print(f"Обнаружены изменения: {len(changes)} файлов")
                for change in changes:
                    print(f"- {change.get('name')} (изменен: {change.get('modifiedTime')})")
            else:
                print("Изменений не обнаружено")
        
    except Exception as e:
        print(f"Ошибка при выполнении примера: {str(e)}")
