"""
Главный модуль ИИ-агента для автоматизации процесса формирования очереди печати.
Объединяет все компоненты системы и предоставляет основной интерфейс для управления.
"""

import os
import sys
import logging
import yaml
import argparse
import time
import threading
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Импорт других модулей проекта
from onedrive_integration import OneDriveIntegration
from data_processing import OrderProcessor
from queue_formation import QueueManager
from excel_editing import ExcelHandler
from telegram_bot import TelegramBot, TelegramNotifier

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/main.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("main")

class PrintQueueAgent:
    """Главный класс агента очереди печати."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация агента очереди печати.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Создание директории для логов
        Path("logs").mkdir(exist_ok=True)
        
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        
        # Получение путей к файлам
        self.files_config = self.config.get('files', {})
        self.onedrive_orders_path = self.files_config.get('onedrive_orders_path', '/Print/orders.xlsx')
        self.onedrive_queue_path = self.files_config.get('onedrive_queue_path', '/Print/queue.xlsx')
        self.onedrive_techlists_folder = self.files_config.get('onedrive_techlists_folder', '/Print/Techlists/')
        self.local_data_folder = Path(self.files_config.get('local_data_folder', 'data/'))
        
        # Создание директории для данных
        self.local_data_folder.mkdir(exist_ok=True, parents=True)
        
        # Получение настроек Telegram
        self.telegram_config = self.config.get('telegram', {})
        self.check_interval_minutes = self.telegram_config.get('check_interval_minutes', 30)
        
        # Инициализация компонентов системы
        self.onedrive = OneDriveIntegration(config_path)
        self.order_processor = OrderProcessor(config_path)
        self.queue_manager = QueueManager(config_path)
        self.excel_handler = ExcelHandler(config_path)
        
        # Инициализация Telegram-компонентов
        self.telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN') or self.telegram_config.get('token')
        self.admin_chat_ids = self.telegram_config.get('admin_chat_ids', [])
        
        if self.telegram_token:
            self.notifier = TelegramNotifier(self.telegram_token, self.admin_chat_ids)
            self.telegram_bot = TelegramBot(
                self.telegram_token,
                data_processor=self.order_processor,
                queue_manager=self.queue_manager
            )
        else:
            logger.warning("Не указан токен Telegram-бота. Уведомления через Telegram недоступны.")
        
        # Флаги для управления потоками
        self.should_run = True
        self.background_thread = None
        
        logger.info("Инициализация агента очереди печати завершена")
    
    def download_files_from_onedrive(self) -> Dict[str, str]:
        """
        Скачивание необходимых файлов из OneDrive.
        
        Returns:
            Dict[str, str]: Словарь с путями к скачанным файлам.
        """
        logger.info("Скачивание файлов из OneDrive")
        
        try:
            # Скачивание файла с заказами
            orders_local_path = self.onedrive.download_file(
                self.onedrive_orders_path, 
                Path(self.onedrive_orders_path).name
            )
            logger.info(f"Файл заказов скачан: {orders_local_path}")
            
            # Проверка существования файла очереди
            try:
                # Попытка скачать существующий файл очереди
                queue_local_path = self.onedrive.download_file(
                    self.onedrive_queue_path, 
                    Path(self.onedrive_queue_path).name
                )
                logger.info(f"Файл очереди скачан: {queue_local_path}")
            except Exception as e:
                logger.warning(f"Файл очереди не найден: {str(e)}")
                # Создание нового файла очереди
                queue_file_name = Path(self.onedrive_queue_path).name
                queue_local_path = self.excel_handler.create_empty_queue_file(
                    self.local_data_folder / queue_file_name
                )
                logger.info(f"Создан новый файл очереди: {queue_local_path}")
            
            return {
                "orders": orders_local_path,
                "queue": queue_local_path
            }
        except Exception as e:
            logger.error(f"Ошибка при скачивании файлов: {str(e)}")
            raise
    
    def upload_files_to_onedrive(self, files: Dict[str, str]) -> None:
        """
        Загрузка обновленных файлов в OneDrive.
        
        Args:
            files (Dict[str, str]): Словарь с путями к файлам для загрузки.
        """
        logger.info("Загрузка файлов в OneDrive")
        
        try:
            # Загрузка файла очереди
            if "queue" in files:
                self.onedrive.upload_file(
                    files["queue"],
                    self.onedrive_queue_path
                )
                logger.info(f"Файл очереди загружен: {self.onedrive_queue_path}")
            
            # Загрузка других файлов при необходимости
            if "orders" in files and files["orders"] != self.local_data_folder / Path(self.onedrive_orders_path).name:
                self.onedrive.upload_file(
                    files["orders"],
                    self.onedrive_orders_path
                )
                logger.info(f"Файл заказов загружен: {self.onedrive_orders_path}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке файлов: {str(e)}")
            raise
    
    def process_orders(self, orders_file_path: str) -> List[Dict[str, Any]]:
        """
        Обработка описаний заказов из файла.
        
        Args:
            orders_file_path (str): Путь к файлу с описаниями заказов.
            
        Returns:
            List[Dict[str, Any]]: Список структурированных данных заказов.
        """
        logger.info(f"Обработка заказов из файла: {orders_file_path}")
        
        try:
            # Извлечение описаний заказов
            descriptions = self.excel_handler.extract_order_descriptions(orders_file_path)
            logger.info(f"Извлечено {len(descriptions)} описаний заказов")
            
            # Обработка описаний
            processed_orders = self.order_processor.batch_process_orders(descriptions)
            logger.info(f"Обработано {len(processed_orders)} заказов")
            
            return processed_orders
        except Exception as e:
            logger.error(f"Ошибка при обработке заказов: {str(e)}")
            return []
    
    def update_queue(self, new_orders: List[Dict[str, Any]], queue_file_path: str) -> Dict[str, Any]:
        """
        Обновление очереди печати с учетом новых заказов.
        
        Args:
            new_orders (List[Dict[str, Any]]): Список новых заказов.
            queue_file_path (str): Путь к файлу с текущей очередью.
            
        Returns:
            Dict[str, Any]: Результаты обновления очереди.
        """
        logger.info(f"Обновление очереди печати: {queue_file_path}")
        
        try:
            # Чтение текущей очереди
            current_queue_df = self.excel_handler.read_excel(queue_file_path)
            
            # Преобразование DataFrame в список словарей
            if not current_queue_df.empty:
                current_queue = current_queue_df.to_dict(orient='records')
            else:
                current_queue = []
            
            logger.info(f"Текущая очередь содержит {len(current_queue)} заказов")
            
            # Объединение новых заказов с текущей очередью
            updated_queue = self.queue_manager.merge_with_existing_queue(new_orders, current_queue)
            logger.info(f"Обновленная очередь содержит {len(updated_queue)} заказов")
            
            # Определение проблемных заказов
            problematic_orders = self.queue_manager.identify_problematic_orders(updated_queue)
            
            # Определение срочных заказов
            emergency_threshold = self.config.get('queue', {}).get('emergency_threshold_days', 3)
            urgent_orders = [
                order for order in updated_queue 
                if self.queue_manager._calculate_days_to_deadline(order.get('deadline', '')) <= emergency_threshold
            ]
            
            # Преобразование обновленной очереди в DataFrame
            updated_queue_df = self.queue_manager.queue_to_dataframe(updated_queue)
            
            # Сохранение очереди в Excel
            self.excel_handler.write_excel(updated_queue_df, queue_file_path)
            logger.info(f"Очередь сохранена в файл: {queue_file_path}")
            
            return {
                "queue": updated_queue,
                "problematic_orders": problematic_orders,
                "urgent_orders": urgent_orders,
                "queue_file": queue_file_path
            }
        except Exception as e:
            logger.error(f"Ошибка при обновлении очереди: {str(e)}")
            raise
    
    def send_notifications(self, queue_data: Dict[str, Any]) -> None:
        """
        Отправка уведомлений на основе данных очереди.
        
        Args:
            queue_data (Dict[str, Any]): Данные очереди.
        """
        logger.info("Отправка уведомлений")
        
        try:
            # Получение данных
            queue = queue_data.get('queue', [])
            problematic_orders = queue_data.get('problematic_orders', [])
            urgent_orders = queue_data.get('urgent_orders', [])
            
            # Отправка уведомлений о срочных заказах
            if urgent_orders:
                self.notifier.send_urgent_orders_notification(urgent_orders)
            
            # Отправка уведомлений о проблемных заказах
            if problematic_orders:
                self.notifier.send_problematic_orders_notification(problematic_orders)
            
            # Ежедневный отчет
            # Проверяем, нужно ли отправлять ежедневный отчет
            send_daily = self.notifications_config.get('frequency', {}).get('send_daily_summary', False)
            if send_daily:
                daily_time = self.notifications_config.get('frequency', {}).get('daily_summary_time', '18:00')
                current_time = datetime.now().strftime('%H:%M')
                
                # Если текущее время близко к времени отправки (в пределах 5 минут)
                hour, minute = map(int, daily_time.split(':'))
                current_hour, current_minute = map(int, current_time.split(':'))
                
                if hour == current_hour and abs(minute - current_minute) <= 5:
                    self.notifier.send_daily_summary(queue, urgent_orders, problematic_orders)
                    logger.info("Отправлен ежедневный отчет")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомлений: {str(e)}")
    
    def update_web_interface(self, queue_data: Dict[str, Any]) -> None:
        """
        Обновление данных для веб-интерфейса.
        
        Args:
            queue_data (Dict[str, Any]): Данные очереди.
        """
        logger.info("Обновление данных для веб-интерфейса")
        
        try:
            # Здесь мы могли бы использовать веб-интерфейс для обновления данных,
            # но для упрощения просто сохраним их в JSON файл, который будет прочитан веб-приложением
            
            # Получение данных
            queue = queue_data.get('queue', [])
            problematic_orders = queue_data.get('problematic_orders', [])
            
            # Сохранение данных для веб-интерфейса
            web_data_path = self.local_data_folder / "web_queue_data.json"
            
            data = {
                "queue": queue,
                "problematic_orders": problematic_orders,
                "last_updated": datetime.now().strftime('%d.%m.%Y %H:%M:%S')
            }
            
            with open(web_data_path, 'w', encoding='utf-8') as file:
                import json
                json.dump(data, file, ensure_ascii=False, indent=2)
            
            logger.info(f"Данные для веб-интерфейса сохранены: {web_data_path}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных для веб-интерфейса: {str(e)}")
    
    def run_queue_processing(self) -> Dict[str, Any]:
        """
        Выполнение полного цикла обработки очереди печати.
        
        Returns:
            Dict[str, Any]: Результаты обработки.
        """
        logger.info("Запуск полного цикла обработки очереди печати")
        
        try:
            # Скачивание файлов из OneDrive
            files = self.download_files_from_onedrive()
            
            # Обработка заказов
            processed_orders = self.process_orders(files["orders"])
            
            # Обновление очереди
            queue_data = self.update_queue(processed_orders, files["queue"])
            
            # Загрузка обновленных файлов в OneDrive
            self.upload_files_to_onedrive({"queue": queue_data["queue_file"]})
            
            # Отправка уведомлений
            self.send_notifications(queue_data)
            
            # Обновление данных для веб-интерфейса
            self.update_web_interface(queue_data)
            
            logger.info("Цикл обработки очереди печати завершен успешно")
            return queue_data
        except Exception as e:
            logger.error(f"Ошибка при обработке очереди печати: {str(e)}")
            return {}
    
    def start_background_thread(self) -> None:
        """Запуск фонового потока для периодической обработки очереди."""
        
        def background_task():
            """Фоновая задача для периодической обработки."""
            logger.info("Запуск фоновой задачи для периодической обработки")
            
            while self.should_run:
                try:
                    # Выполнение цикла обработки
                    self.run_queue_processing()
                    
                    # Ожидание перед следующим циклом
                    for _ in range(self.check_interval_minutes * 60):
                        if not self.should_run:
                            break
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"Ошибка в фоновой задаче: {str(e)}")
                    # Ожидание перед повторной попыткой
                    time.sleep(60)
        
        # Создание и запуск потока
        self.background_thread = threading.Thread(target=background_task)
        self.background_thread.daemon = True
        self.background_thread.start()
        
        logger.info("Фоновый поток запущен")
    
    def stop_background_thread(self) -> None:
        """Остановка фонового потока."""
        self.should_run = False
        if self.background_thread:
            self.background_thread.join(timeout=5)
        logger.info("Фоновый поток остановлен")
    
    def run_cli(self) -> None:
        """Запуск приложения в режиме командной строки."""
        parser = argparse.ArgumentParser(description="Агент очереди печати")
        
        parser.add_argument('--run-once', action='store_true', 
                          help='Выполнить однократную обработку очереди')
        parser.add_argument('--background', action='store_true', 
                          help='Запустить фоновую обработку очереди')
        parser.add_argument('--download-files', action='store_true', 
                          help='Скачать файлы из OneDrive')
        parser.add_argument('--upload-files', action='store_true', 
                          help='Загрузить файлы в OneDrive')
        parser.add_argument('--report', action='store_true', 
                          help='Сформировать отчет об очереди')
        
        args = parser.parse_args()
        
        if args.run_once:
            # Однократная обработка
            self.run_queue_processing()
        elif args.background:
            # Запуск фоновой обработки
            self.start_background_thread()
            
            try:
                print("Фоновая обработка запущена. Нажмите Ctrl+C для остановки.")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Остановка фоновой обработки...")
                self.stop_background_thread()
        elif args.download_files:
            # Скачивание файлов
            files = self.download_files_from_onedrive()
            print(f"Файлы скачаны: {files}")
        elif args.upload_files:
            # Загрузка файлов
            # Определение файлов для загрузки
            queue_file = self.local_data_folder / Path(self.onedrive_queue_path).name
            if queue_file.exists():
                self.upload_files_to_onedrive({"queue": str(queue_file)})
                print(f"Файл очереди загружен: {self.onedrive_queue_path}")
            else:
                print(f"Файл очереди не найден: {queue_file}")
        elif args.report:
            # Формирование отчета
            # Сначала скачиваем файл очереди
            files = self.download_files_from_onedrive()
            
            # Чтение очереди
            queue_df = self.excel_handler.read_excel(files["queue"])
            queue = queue_df.to_dict(orient='records')
            
            # Формирование отчета
            report = self.queue_manager.generate_queue_report(queue)
            
            print(report)
        else:
            logger.info("Запуск режима по умолчанию: Telegram-бот и обработка очереди")
            
            # Запуск фоновой обработки очереди
            self.start_background_thread()
            
            # Запуск Telegram-бота, если он инициализирован
            if hasattr(self, 'telegram_bot'):
                print("Запуск Telegram-бота...")
                print("Для завершения работы нажмите Ctrl+C")
                try:
                    # Сначала запускаем однократную обработку очереди
                    self.run_queue_processing()
                    
                    # Добавляем администраторов в бота
                    self.telegram_bot.admin_ids = self.admin_chat_ids
                    
                    # Запускаем бота
                    self.telegram_bot.start()
                except KeyboardInterrupt:
                    # Остановка фонового потока при завершении
                    logger.info("Получен сигнал завершения. Останавливаю фоновые потоки...")
                    self.stop_background_thread()
                    print("Работа завершена.")
            else:
                # Если бот не инициализирован, запускаем однократную обработку по умолчанию
                logger.info("Бот не инициализирован. Запускаем однократную обработку...")
                self.run_queue_processing()


def main():
    """Точка входа в приложение."""
    try:
        agent = PrintQueueAgent()
        agent.run_cli()
    except Exception as e:
        logger.error(f"Ошибка при запуске агента: {str(e)}")
        print(f"Ошибка: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
