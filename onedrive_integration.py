"""
Модуль для интеграции с Microsoft OneDrive через Microsoft Graph API.
Обеспечивает функциональность аутентификации, скачивания и загрузки файлов.
"""

import os
import logging
import requests
import yaml
import msal
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/onedrive.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("onedrive_integration")

class OneDriveIntegration:
    """Класс для работы с Microsoft OneDrive через Microsoft Graph API."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация интеграции с OneDrive.
        
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
        
        # Microsoft Graph API URL
        self.graph_url = "https://graph.microsoft.com/v1.0"
        
        # Получение учетных данных из .env
        self.client_id = os.getenv("AZURE_APP_ID")
        self.client_secret = os.getenv("AZURE_APP_SECRET")
        self.tenant_id = os.getenv("AZURE_TENANT_ID")
        
        # Получение областей доступа из конфигурации
        self.scopes = self.config.get('microsoft', {}).get('scopes', [])
        
        # Создание кэша токенов
        self.token_cache = msal.SerializableTokenCache()
        
        # Токен доступа и время его истечения
        self.access_token = None
        self.token_expires_at = datetime.now()
        
        # Проверка наличия необходимых учетных данных
        if not self.client_id or not self.client_secret or not self.tenant_id:
            logger.error("Отсутствуют необходимые учетные данные Microsoft Graph API")
            raise ValueError("Необходимо указать AZURE_APP_ID, AZURE_APP_SECRET и AZURE_TENANT_ID в .env файле")
    
    def _get_access_token(self):
        """
        Получение токена доступа для Microsoft Graph API.
        
        Returns:
            str: Токен доступа.
        """
        # Проверка, есть ли действующий токен
        if self.access_token and datetime.now() < self.token_expires_at:
            return self.access_token
        
        # Создание приложения MSAL
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self.token_cache
        )
        
        # Получение токена
        result = app.acquire_token_for_client(scopes=self.scopes)
        
        if "access_token" not in result:
            logger.error(f"Не удалось получить токен доступа: {result.get('error_description', 'Неизвестная ошибка')}")
            raise Exception(f"Ошибка аутентификации: {result.get('error_description', 'Неизвестная ошибка')}")
        
        # Сохранение токена и времени его истечения
        self.access_token = result["access_token"]
        self.token_expires_at = datetime.now() + timedelta(seconds=result["expires_in"] - 300)  # С запасом в 5 минут
        
        logger.info("Получен новый токен доступа")
        return self.access_token
    
    def _make_request(self, method, endpoint, **kwargs):
        """
        Выполнение запроса к Microsoft Graph API.
        
        Args:
            method (str): HTTP метод (GET, POST, PUT и т.д.).
            endpoint (str): Конечная точка API.
            **kwargs: Дополнительные параметры запроса.
            
        Returns:
            dict: Ответ API в формате JSON.
        """
        # Получение токена
        token = self._get_access_token()
        
        # Формирование URL запроса
        url = f"{self.graph_url}{endpoint}"
        
        # Добавление заголовка авторизации
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        
        # Выполнение запроса
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            
            # Возврат JSON если есть, иначе просто ответ
            if response.content:
                return response.json()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при выполнении запроса {method} {endpoint}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Ответ сервера: {e.response.text}")
            raise
    
    def list_files(self, folder_path="/"):
        """
        Получение списка файлов из указанной папки OneDrive.
        
        Args:
            folder_path (str): Путь к папке в OneDrive.
            
        Returns:
            list: Список файлов и папок.
        """
        # Формирование пути с корректной кодировкой
        encoded_path = folder_path.strip("/")
        
        # Запрос списка файлов
        if encoded_path:
            endpoint = f"/me/drive/root:/{encoded_path}:/children"
        else:
            endpoint = "/me/drive/root/children"
        
        response = self._make_request("GET", endpoint)
        return response.get("value", [])
    
    def download_file(self, onedrive_path, local_filename=None):
        """
        Скачивание файла из OneDrive.
        
        Args:
            onedrive_path (str): Путь к файлу в OneDrive.
            local_filename (str, optional): Локальное имя файла. Если не указано, 
                                            используется имя из OneDrive.
                                            
        Returns:
            str: Путь к скачанному файлу.
        """
        # Получение информации о файле
        encoded_path = onedrive_path.strip("/")
        endpoint = f"/me/drive/root:/{encoded_path}"
        
        try:
            file_info = self._make_request("GET", endpoint)
            
            # Получение URL для скачивания
            download_url = self._make_request("GET", f"{endpoint}:/content")
            
            # Если URL напрямую не получен, получаем его из @microsoft.graph.downloadUrl
            if isinstance(download_url, dict) and "@microsoft.graph.downloadUrl" in download_url:
                download_url = download_url["@microsoft.graph.downloadUrl"]
            
            # Определение имени файла
            if not local_filename:
                local_filename = os.path.basename(onedrive_path)
            
            # Формирование пути для сохранения
            local_path = self.local_data_path / local_filename
            
            # Скачивание файла
            if isinstance(download_url, str):
                # Прямая ссылка на скачивание
                response = requests.get(download_url)
            else:
                # Используем содержимое ответа
                response = download_url
            
            # Сохранение файла
            with open(local_path, 'wb') as f:
                if hasattr(response, 'content'):
                    f.write(response.content)
                elif hasattr(response, 'read'):
                    f.write(response.read())
            
            logger.info(f"Файл {onedrive_path} успешно скачан как {local_path}")
            return str(local_path)
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла {onedrive_path}: {str(e)}")
            raise
    
    def upload_file(self, local_path, onedrive_path):
        """
        Загрузка файла в OneDrive.
        
        Args:
            local_path (str): Путь к локальному файлу.
            onedrive_path (str): Путь назначения в OneDrive.
            
        Returns:
            dict: Информация о загруженном файле.
        """
        # Проверка существования файла
        if not os.path.exists(local_path):
            logger.error(f"Локальный файл {local_path} не существует")
            raise FileNotFoundError(f"Файл {local_path} не найден")
        
        # Формирование пути с корректной кодировкой
        encoded_path = onedrive_path.strip("/")
        endpoint = f"/me/drive/root:/{encoded_path}:/content"
        
        # Чтение файла
        with open(local_path, 'rb') as file_content:
            # Определение типа контента
            file_extension = os.path.splitext(local_path)[1].lower()
            content_type = "application/octet-stream"  # По умолчанию
            
            if file_extension == '.xlsx':
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif file_extension == '.csv':
                content_type = "text/csv"
            elif file_extension == '.txt':
                content_type = "text/plain"
            
            # Загрузка файла
            headers = {"Content-Type": content_type}
            response = self._make_request("PUT", endpoint, headers=headers, data=file_content)
            
            logger.info(f"Файл {local_path} успешно загружен в {onedrive_path}")
            return response
    
    def create_folder(self, folder_path):
        """
        Создание папки в OneDrive.
        
        Args:
            folder_path (str): Путь к создаваемой папке.
            
        Returns:
            dict: Информация о созданной папке.
        """
        # Разделение пути на компоненты
        path_components = folder_path.strip("/").split("/")
        current_path = ""
        
        # Последовательное создание каждого уровня папок
        for folder_name in path_components:
            if current_path:
                current_path += f"/{folder_name}"
            else:
                current_path = folder_name
            
            # Проверка существования папки
            try:
                self._make_request("GET", f"/me/drive/root:/{current_path}")
                logger.info(f"Папка {current_path} уже существует")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Папка не существует, создаем
                    body = {
                        "name": folder_name,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "rename"
                    }
                    
                    if current_path == folder_name:
                        # Создание в корневой папке
                        endpoint = "/me/drive/root/children"
                    else:
                        # Создание в подпапке
                        parent_path = "/".join(current_path.split("/")[:-1])
                        endpoint = f"/me/drive/root:/{parent_path}:/children"
                    
                    response = self._make_request("POST", endpoint, json=body)
                    logger.info(f"Папка {current_path} успешно создана")
                else:
                    # Другая ошибка
                    logger.error(f"Ошибка при проверке папки {current_path}: {str(e)}")
                    raise
        
        # Возврат информации о созданной папке
        return self._make_request("GET", f"/me/drive/root:/{folder_path}")
    
    def delete_file(self, file_path):
        """
        Удаление файла из OneDrive.
        
        Args:
            file_path (str): Путь к файлу в OneDrive.
            
        Returns:
            bool: True если удаление успешно.
        """
        encoded_path = file_path.strip("/")
        endpoint = f"/me/drive/root:/{encoded_path}"
        
        try:
            self._make_request("DELETE", endpoint)
            logger.info(f"Файл {file_path} успешно удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")
            raise


if __name__ == "__main__":
    # Пример использования
    try:
        # Инициализация
        onedrive = OneDriveIntegration()
        
        # Вывод списка файлов в корневой папке
        files = onedrive.list_files()
        print("Файлы в корневой папке:")
        for file in files:
            print(f" - {file.get('name')} ({file.get('id')})")
        
        # Другие примеры (закомментированы для безопасности)
        # local_file = onedrive.download_file("/Documents/example.xlsx")
        # print(f"Файл скачан: {local_file}")
        
        # uploaded = onedrive.upload_file("local_file.xlsx", "/Documents/uploaded.xlsx")
        # print(f"Файл загружен: {uploaded.get('name')}")
    except Exception as e:
        print(f"Ошибка: {str(e)}")
