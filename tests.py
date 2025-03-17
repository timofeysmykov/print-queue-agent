"""
Модульные тесты для агента очереди печати.
Позволяют проверить работоспособность основных компонентов системы.
"""

import os
import unittest
import tempfile
import json
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path

# Импортируем модули проекта
from gdrive_integration import GoogleDriveIntegration
from data_processing import OrderProcessor, LLMProcessor
from queue_formation import QueueManager
from excel_editing import ExcelHandler
from notifications import NotificationManager
from main import PrintQueueAgent

# Константы для тестирования
TEST_CONFIG = {
    "microsoft_graph": {
        "app_id": "test_app_id",
        "tenant_id": "test_tenant_id"
    },
    "llm": {
        "provider": "anthropic",
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1000,
        "temperature": 0.2
    },
    "queue": {
        "emergency_threshold_days": 3,
        "max_queue_size": 100,
        "date_format": "%d.%m.%Y",
        "default_priority": "обычный"
    },
    "files": {
        "gdrive_orders_path": "/Print/orders.xlsx",
        "gdrive_queue_path": "/Print/queue.xlsx",
        "gdrive_techlists_folder": "/Print/Techlists/",
        "local_data_folder": "data/"
    },
    "notifications": {
        "email": {
            "enabled": True,
            "recipients": ["test@example.com"]
        },
        "frequency": {
            "check_interval_minutes": 30,
            "send_daily_summary": True,
            "daily_summary_time": "18:00"
        }
    }
}

# Пример данных для тестирования
SAMPLE_ORDERS = [
    {
        "order_id": "123",
        "customer": "Иванов И.И.",
        "deadline": "25.12.2023",
        "quantity": "500 листов",
        "priority": "срочно",
        "description": "Печать буклетов А4, цветная, двусторонняя"
    },
    {
        "order_id": "456",
        "customer": "ООО Ромашка",
        "deadline": "30.12.2023",
        "quantity": "1000 экз",
        "priority": "обычный",
        "description": "Печать каталогов А5, черно-белая"
    }
]


class TestGoogleDriveIntegration(unittest.TestCase):
    """Тесты для модуля интеграции с Google Drive."""
    
    @patch('gdrive_integration.service_account.Credentials.from_service_account_info')
    @patch('gdrive_integration.build')
    def setUp(self, mock_build, mock_credentials):
        """Настройка перед запуском тестов."""
        # Настройка моков
        mock_credentials.return_value = MagicMock()
        
        # Мок для драйв сервиса
        mock_drive_service = MagicMock()
        mock_files = MagicMock()
        mock_drive_service.files.return_value = mock_files
        mock_build.return_value = mock_drive_service
        
        # Создание тестового экземпляра
        with patch('builtins.open'), patch('yaml.safe_load', return_value=TEST_CONFIG), \
             patch('json.loads', return_value={'key': 'test_value'}), \
             patch('os.getenv', return_value='{"key": "test_value"}'):
            self.gdrive = GoogleDriveIntegration()
            self.onedrive.token = "test_token"
    
    def test_auth(self):
        """Проверка аутентификации."""
        self.assertEqual(self.onedrive.token, "test_token")
    
    @patch('onedrive_integration.requests.get')
    def test_list_files(self, mock_get):
        """Проверка листинга файлов."""
        # Настройка мока
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "value": [
                {"name": "file1.txt", "id": "123"},
                {"name": "file2.txt", "id": "456"}
            ]
        }
        
        # Вызов метода
        files = self.onedrive.list_files("/test")
        
        # Проверка результата
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]["name"], "file1.txt")
        self.assertEqual(files[1]["id"], "456")
    
    @patch('onedrive_integration.requests.get')
    def test_download_file(self, mock_get):
        """Проверка скачивания файла."""
        # Временный файл для теста
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Настройка моков
            mock_content = MagicMock()
            mock_content.status_code = 200
            mock_content.content = b"test content"
            mock_get.side_effect = [
                # Первый вызов для получения ссылки на загрузку
                MagicMock(status_code=200, json=lambda: {"@microsoft.graph.downloadUrl": "https://download-url"}),
                # Второй вызов для загрузки содержимого
                mock_content
            ]
            
            # Вызов метода
            with patch('builtins.open'):
                result = self.onedrive.download_file("/test/file.txt", temp_path)
            
            # Проверка результата
            self.assertEqual(result, temp_path)
            mock_get.assert_called()
        finally:
            # Удаление временного файла
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestDataProcessing(unittest.TestCase):
    """Тесты для модуля обработки данных."""
    
    def setUp(self):
        """Настройка перед запуском тестов."""
        # Создание тестового экземпляра с моком LLM
        with patch('data_processing.LLMProcessor'), patch('builtins.open'), patch('yaml.safe_load', return_value=TEST_CONFIG):
            self.processor = OrderProcessor()
            # Мок для LLM процессора
            self.processor.llm_processor = MagicMock()
            self.processor.llm_processor.process_text.return_value = json.dumps({
                "order_id": "123",
                "customer": "Тестовый заказчик",
                "deadline": "25.12.2023",
                "quantity": "100 шт",
                "priority": "обычный",
                "description": "Тестовое описание"
            })
    
    def test_process_order(self):
        """Проверка обработки заказа."""
        result = self.processor.process_order("Тестовое описание заказа")
        
        # Проверка результата
        self.assertEqual(result["order_id"], "123")
        self.assertEqual(result["customer"], "Тестовый заказчик")
        self.assertEqual(result["deadline"], "25.12.2023")
        self.assertEqual(result["quantity"], "100 шт")
        self.assertEqual(result["priority"], "обычный")
    
    def test_batch_process_orders(self):
        """Проверка пакетной обработки заказов."""
        result = self.processor.batch_process_orders(["Заказ 1", "Заказ 2"])
        
        # Проверка результата
        self.assertEqual(len(result), 2)
        for order in result:
            self.assertEqual(order["order_id"], "123")
            self.assertEqual(order["customer"], "Тестовый заказчик")


class TestQueueFormation(unittest.TestCase):
    """Тесты для модуля формирования очереди."""
    
    def setUp(self):
        """Настройка перед запуском тестов."""
        with patch('builtins.open'), patch('yaml.safe_load', return_value=TEST_CONFIG):
            self.queue_manager = QueueManager()
    
    def test_calculate_days_to_deadline(self):
        """Проверка расчета дней до дедлайна."""
        today = datetime.now().strftime("%d.%m.%Y")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
        
        # Проверка с различными сроками
        self.assertEqual(self.queue_manager._calculate_days_to_deadline(today), 0)
        self.assertEqual(self.queue_manager._calculate_days_to_deadline(tomorrow), 1)
        self.assertEqual(self.queue_manager._calculate_days_to_deadline(next_week), 7)
    
    def test_sort_queue(self):
        """Проверка сортировки очереди."""
        orders = [
            {
                "order_id": "1",
                "deadline": (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y"),
                "priority": "обычный"
            },
            {
                "order_id": "2",
                "deadline": (datetime.now() + timedelta(days=5)).strftime("%d.%m.%Y"),
                "priority": "срочно"
            },
            {
                "order_id": "3",
                "deadline": (datetime.now() + timedelta(days=2)).strftime("%d.%m.%Y"),
                "priority": "срочно"
            }
        ]
        
        sorted_orders = self.queue_manager.sort_orders_by_priority(orders)
        
        # Проверка результата сортировки (срочные с ближайшим сроком первые)
        self.assertEqual(sorted_orders[0]["order_id"], "3")
        self.assertEqual(sorted_orders[1]["order_id"], "2")
        self.assertEqual(sorted_orders[2]["order_id"], "1")
    
    def test_merge_with_existing_queue(self):
        """Проверка объединения с существующей очередью."""
        existing_queue = [
            {
                "order_id": "1",
                "queue_position": 1,
                "customer": "Существующий заказчик",
                "deadline": (datetime.now() + timedelta(days=5)).strftime("%d.%m.%Y")
            }
        ]
        
        new_orders = [
            {
                "order_id": "2",
                "customer": "Новый заказчик",
                "deadline": (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y"),
                "priority": "срочно"
            }
        ]
        
        merged_queue = self.queue_manager.merge_with_existing_queue(new_orders, existing_queue)
        
        # Проверка результата объединения
        self.assertEqual(len(merged_queue), 2)
        # Новый срочный заказ должен быть первым
        self.assertEqual(merged_queue[0]["order_id"], "2")
        self.assertEqual(merged_queue[0]["queue_position"], 1)
        # Существующий заказ должен переместиться на вторую позицию
        self.assertEqual(merged_queue[1]["order_id"], "1")
        self.assertEqual(merged_queue[1]["queue_position"], 2)


class TestExcelHandling(unittest.TestCase):
    """Тесты для модуля работы с Excel-файлами."""
    
    def setUp(self):
        """Настройка перед запуском тестов."""
        with patch('builtins.open'), patch('yaml.safe_load', return_value=TEST_CONFIG):
            self.excel_handler = ExcelHandler()
    
    def test_create_empty_queue_file(self):
        """Проверка создания пустого файла очереди."""
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Создание пустого файла очереди
            result = self.excel_handler.create_empty_queue_file(temp_path)
            
            # Проверка результата
            self.assertEqual(result, temp_path)
            self.assertTrue(os.path.exists(temp_path))
            
            # Проверка структуры файла
            df = pd.read_excel(temp_path)
            expected_columns = [
                'queue_position', 'order_id', 'customer', 'deadline', 
                'quantity', 'priority', 'status', 'description'
            ]
            for col in expected_columns:
                self.assertIn(col, df.columns)
        finally:
            # Удаление временного файла
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_write_and_read_excel(self):
        """Проверка записи и чтения Excel-файла."""
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Создание тестового DataFrame
            test_data = {
                'queue_position': [1, 2],
                'order_id': ['123', '456'],
                'customer': ['Тест1', 'Тест2'],
                'deadline': ['01.01.2023', '02.01.2023'],
                'quantity': ['100 шт', '200 шт'],
                'priority': ['срочно', 'обычный'],
                'status': ['ожидание', 'в работе'],
                'description': ['Описание1', 'Описание2']
            }
            test_df = pd.DataFrame(test_data)
            
            # Запись данных
            self.excel_handler.write_excel(test_df, temp_path)
            
            # Чтение данных
            read_df = self.excel_handler.read_excel(temp_path)
            
            # Проверка данных
            self.assertEqual(len(read_df), 2)
            self.assertEqual(read_df.iloc[0]['order_id'], '123')
            self.assertEqual(read_df.iloc[1]['customer'], 'Тест2')
        finally:
            # Удаление временного файла
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestNotifications(unittest.TestCase):
    """Тесты для модуля уведомлений."""
    
    def setUp(self):
        """Настройка перед запуском тестов."""
        with patch('builtins.open'), patch('yaml.safe_load', return_value=TEST_CONFIG):
            self.notifier = NotificationManager()
    
    @patch('notifications.smtplib.SMTP')
    def test_send_email(self, mock_smtp):
        """Проверка отправки email."""
        # Настройка тестовых данных
        self.notifier.email_enabled = True
        self.notifier.email_sender = "test@example.com"
        self.notifier.email_password = "password"
        self.notifier.smtp_server = "smtp.example.com"
        self.notifier.smtp_port = 587
        self.notifier.recipients = ["recipient@example.com"]
        
        # Настройка мока
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
        
        # Вызов метода
        with patch('notifications.NotificationManager._save_notification_history'):
            result = self.notifier.send_email("Тестовая тема", "Тестовое сообщение")
        
        # Проверка результата
        self.assertTrue(result)
        mock_smtp_instance.login.assert_called_with("test@example.com", "password")
        mock_smtp_instance.send_message.assert_called_once()
    
    @patch('notifications.NotificationManager.send_email')
    def test_send_urgent_orders_notification(self, mock_send_email):
        """Проверка отправки уведомления о срочных заказах."""
        # Настройка мока
        mock_send_email.return_value = True
        
        # Тестовые данные
        urgent_orders = [
            {
                "order_id": "123",
                "customer": "Тест",
                "deadline": "01.01.2023",
                "priority": "срочно",
                "problems": ["Срок истекает завтра"]
            }
        ]
        
        # Вызов метода
        result = self.notifier.send_urgent_orders_notification(urgent_orders)
        
        # Проверка результата
        self.assertTrue(result)
        mock_send_email.assert_called_once()
        
        # Проверка с пустым списком
        mock_send_email.reset_mock()
        result = self.notifier.send_urgent_orders_notification([])
        self.assertFalse(result)
        mock_send_email.assert_not_called()


class TestPrintQueueAgent(unittest.TestCase):
    """Тесты для основного класса агента очереди печати."""
    
    def setUp(self):
        """Настройка перед запуском тестов."""
        # Патчи для всех зависимых классов
        patches = [
            patch('main.GoogleDriveIntegration'),
            patch('main.OrderProcessor'),
            patch('main.QueueManager'),
            patch('main.ExcelHandler'),
            patch('main.NotificationManager'),
            patch('builtins.open'),
            patch('yaml.safe_load', return_value=TEST_CONFIG),
            patch('main.Path')
        ]
        
        # Применение всех патчей
        for p in patches:
            p.start()
        self.patches = patches
        
        # Создание тестового экземпляра
        self.agent = PrintQueueAgent()
        
        # Настройка моков для компонентов
        self.agent.gdrive = MagicMock()
        self.agent.order_processor = MagicMock()
        self.agent.queue_manager = MagicMock()
        self.agent.excel_handler = MagicMock()
        self.agent.notifier = MagicMock()
    
    def tearDown(self):
        """Завершение после тестов."""
        # Остановка всех патчей
        for p in self.patches:
            p.stop()
    
    def test_download_files_from_onedrive(self):
        """Проверка скачивания файлов из OneDrive."""
        # Настройка моков
        self.agent.onedrive.download_file.side_effect = ["/local/path/orders.xlsx", "/local/path/queue.xlsx"]
        
        # Вызов метода
        result = self.agent.download_files_from_onedrive()
        
        # Проверка результата
        self.assertEqual(result["orders"], "/local/path/orders.xlsx")
        self.assertEqual(result["queue"], "/local/path/queue.xlsx")
        self.assertEqual(self.agent.onedrive.download_file.call_count, 2)
    
    def test_process_orders(self):
        """Проверка обработки заказов."""
        # Настройка моков
        self.agent.excel_handler.extract_order_descriptions.return_value = ["Заказ 1", "Заказ 2"]
        self.agent.order_processor.batch_process_orders.return_value = SAMPLE_ORDERS
        
        # Вызов метода
        result = self.agent.process_orders("/local/path/orders.xlsx")
        
        # Проверка результата
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["order_id"], "123")
        self.assertEqual(result[1]["order_id"], "456")
        self.agent.excel_handler.extract_order_descriptions.assert_called_once()
        self.agent.order_processor.batch_process_orders.assert_called_once()
    
    def test_update_queue(self):
        """Проверка обновления очереди."""
        # Настройка моков
        self.agent.excel_handler.read_excel.return_value = pd.DataFrame()
        self.agent.queue_manager.merge_with_existing_queue.return_value = SAMPLE_ORDERS
        self.agent.queue_manager.identify_problematic_orders.return_value = []
        self.agent.queue_manager.queue_to_dataframe.return_value = pd.DataFrame()
        
        # Вызов метода
        result = self.agent.update_queue(SAMPLE_ORDERS, "/local/path/queue.xlsx")
        
        # Проверка результата
        self.assertEqual(result["queue"], SAMPLE_ORDERS)
        self.assertEqual(result["queue_file"], "/local/path/queue.xlsx")
        self.agent.excel_handler.read_excel.assert_called_once()
        self.agent.queue_manager.merge_with_existing_queue.assert_called_once()
        self.agent.excel_handler.write_excel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
