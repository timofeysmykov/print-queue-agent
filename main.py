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
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Импорт других модулей проекта
from gdrive_integration import GoogleDriveIntegration
from excel_editing import ExcelHandler
from telegram_bot import TelegramBot, TelegramNotifier
from claude_api import ClaudeAPIClient

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
        self.orders_filename = self.files_config.get('orders_filename', 'orders.xlsx')
        self.queue_filename = self.files_config.get('queue_filename', 'queue.xlsx')
        self.local_data_folder = Path(self.files_config.get('local_data_folder', 'data/'))
        
        # Создание директории для данных
        self.local_data_folder.mkdir(exist_ok=True, parents=True)
        
        # Получение настроек Telegram
        self.telegram_config = self.config.get('telegram', {})
        self.check_interval_minutes = self.telegram_config.get('check_interval_minutes', 30)
        
        # Инициализация компонентов системы
        self.gdrive = GoogleDriveIntegration()
        self.claude_client = ClaudeAPIClient()
        self.excel_handler = ExcelHandler(config_path)
        
        # Инициализация Telegram-компонентов
        self.telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN') or self.telegram_config.get('token')
        self.admin_chat_ids = self.telegram_config.get('admin_chat_ids', [])
        
        if self.telegram_token:
            self.notifier = TelegramNotifier(self.telegram_token, self.admin_chat_ids)
            self.telegram_bot = TelegramBot(
                self.telegram_token,
                data_processor=self,
                queue_manager=self
            )
        else:
            logger.warning("Не указан токен Telegram-бота. Уведомления через Telegram недоступны.")
        
        # Флаги для управления потоками
        self.should_run = True
        self.background_thread = None
        
        logger.info("Инициализация агента очереди печати завершена")
    
    def download_files_from_gdrive(self) -> Dict[str, str]:
        """
        Скачивание необходимых файлов из Google Drive.
        
        Returns:
            Dict[str, str]: Словарь с путями к скачанным файлам.
        """
        logger.info("Скачивание файлов из Google Drive")
        
        try:
            # Скачивание файла с заказами
            orders_local_path = self.gdrive.download_file(
                self.orders_filename,
                self.local_data_folder / self.orders_filename
            )
            
            if not orders_local_path:
                logger.error(f"Не удалось скачать файл заказов {self.orders_filename}")
                return {}
                
            logger.info(f"Файл заказов скачан: {orders_local_path}")
            
            # Проверка существования файла очереди
            queue_local_path = self.gdrive.download_file(
                self.queue_filename,
                self.local_data_folder / self.queue_filename
            )
            
            if not queue_local_path:
                logger.warning(f"Файл очереди не найден, создаем новый")
                # Создание нового файла очереди
                queue_local_path = self.excel_handler.create_empty_queue_file(
                    self.local_data_folder / self.queue_filename
                )
                logger.info(f"Создан новый файл очереди: {queue_local_path}")
            else:
                logger.info(f"Файл очереди скачан: {queue_local_path}")
            
            return {
                "orders": orders_local_path,
                "queue": queue_local_path
            }
        except Exception as e:
            logger.error(f"Ошибка при скачивании файлов: {str(e)}")
            return {}
    
    def upload_files_to_gdrive(self, files: Dict[str, str]) -> bool:
        """
        Загрузка обновленных файлов в Google Drive.
        
        Args:
            files (Dict[str, str]): Словарь с путями к файлам для загрузки.
            
        Returns:
            bool: True если все файлы успешно загружены, иначе False.
        """
        logger.info("Загрузка файлов в Google Drive")
        
        try:
            all_successful = True
            
            # Загрузка файла очереди
            if "queue" in files:
                result = self.gdrive.upload_file(files["queue"])
                if result:
                    logger.info(f"Файл очереди успешно загружен")
                else:
                    logger.error(f"Не удалось загрузить файл очереди")
                    all_successful = False
            
            # Загрузка других файлов при необходимости
            if "orders" in files and files["orders"] != str(self.local_data_folder / self.orders_filename):
                result = self.gdrive.upload_file(files["orders"])
                if result:
                    logger.info(f"Файл заказов успешно загружен")
                else:
                    logger.error(f"Не удалось загрузить файл заказов")
                    all_successful = False
                    
            return all_successful
                    
        except Exception as e:
            logger.error(f"Ошибка при загрузке файлов: {str(e)}")
            return False
    
    def process_orders_with_claude(self, orders_file_path: str) -> List[Dict[str, Any]]:
        """
        Обработка заказов из Excel-файла с использованием Claude 3.5 Haiku.
        
        Args:
            orders_file_path (str): Путь к файлу с заказами.
            
        Returns:
            List[Dict[str, Any]]: Список структурированных данных заказов.
        """
        logger.info(f"Обработка заказов из файла: {orders_file_path}")
        
        try:
            # Чтение данных из Excel
            df = self.excel_handler.read_excel(orders_file_path)
            
            if df.empty:
                logger.warning("Файл заказов пуст или имеет неверный формат")
                return []
            
            # Преобразование DataFrame в JSON для Claude
            orders_data = df.to_dict(orient='records')
            orders_json = json.dumps(orders_data, ensure_ascii=False, indent=2)
            
            # Обработка данных заказов через Claude
            processed_data = self.claude_client.process_excel_data(orders_json)
            
            # Проверка на наличие ошибок
            if "error" in processed_data:
                logger.error(f"Ошибка обработки данных через Claude: {processed_data['error']}")
                return []
            
            # Получение очереди заказов
            queue = processed_data.get("queue", [])
            logger.info(f"Claude успешно обработал {len(queue)} заказов")
            
            return queue
        except Exception as e:
            logger.error(f"Ошибка при обработке заказов через Claude: {str(e)}")
            return []
    
    def update_queue(self, processed_orders: List[Dict[str, Any]], queue_file_path: str) -> Dict[str, Any]:
        """
        Обновление очереди печати с учетом новых обработанных заказов.
        
        Args:
            processed_orders (List[Dict[str, Any]]): Список обработанных заказов.
            queue_file_path (str): Путь к файлу с текущей очередью.
            
        Returns:
            Dict[str, Any]: Результат обновления очереди.
        """
        logger.info(f"Обновление очереди печати: {queue_file_path}")
        
        try:
            # Преобразование в DataFrame
            new_queue_df = pd.DataFrame(processed_orders)
            
            if new_queue_df.empty:
                logger.warning("Нет новых заказов для добавления в очередь")
                return {"status": "no_changes", "queue_file": queue_file_path}
            
            # Обновление файла очереди
            updated_file = self.excel_handler.update_excel(
                queue_file_path, 
                new_queue_df,
                sheet_name="Очередь печати",
                key_column="order_id"
            )
            
            logger.info(f"Очередь печати обновлена: {updated_file}")
            return {
                "status": "updated",
                "queue_file": updated_file,
                "queue_data": processed_orders
            }
        except Exception as e:
            logger.error(f"Ошибка при обновлении очереди: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def generate_queue_summary(self, processed_orders: List[Dict[str, Any]]) -> str:
        """
        Генерация текстовой сводки по очереди печати с использованием Claude 3.5 Haiku.
        
        Args:
            processed_orders (List[Dict[str, Any]]): Список обработанных заказов.
            
        Returns:
            str: Текстовая сводка.
        """
        try:
            # Если заказов нет, возвращаем базовое сообщение
            if not processed_orders:
                return "Очередь печати пуста. Нет активных заказов."
            
            # Формирование сводки с помощью Claude
            queue_data = {
                "queue": processed_orders,
                "optimization_notes": "Очередь сформирована на основе приоритетов и сроков выполнения",
                "estimated_total_completion_time": "Ориентировочное время выполнения всех заказов: 2 рабочих дня"
            }
            
            summary = self.claude_client.summarize_orders_and_queue(processed_orders, queue_data)
            logger.info("Сводка по очереди печати успешно сгенерирована")
            
            return summary
        except Exception as e:
            logger.error(f"Ошибка при генерации сводки: {str(e)}")
            return f"Не удалось сгенерировать сводку: {str(e)}"
    
    def generate_order_report(self, order_data: Dict[str, Any]) -> str:
        """
        Генерация отчета о выполнении заказа с использованием Claude 3.5 Haiku.
        
        Args:
            order_data (Dict[str, Any]): Данные о заказе.
            
        Returns:
            str: Отформатированный отчет.
        """
        try:
            # Генерация отчета с помощью Claude
            report = self.claude_client.generate_report(order_data)
            logger.info(f"Отчет для заказа успешно сгенерирован")
            return report
        except Exception as e:
            logger.error(f"Ошибка при генерации отчета: {str(e)}")
            return f"Не удалось сгенерировать отчет: {str(e)}"
    
    def process_order_text(self, text: str) -> Dict[str, Any]:
        """
        Обработка текстового описания заказа с использованием Claude API.
        
        Args:
            text (str): Текстовое описание заказа.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа.
        """
        logger.info(f"Обработка текста заказа: {text[:50]}...")
        
        try:
            # Используем Claude API для обработки текста заказа
            order_data = self.claude_client.process_order_text(text)
            
            if "error" in order_data:
                logger.error(f"Ошибка при обработке заказа: {order_data['error']}")
                return order_data
            
            # Добавляем статус "Новый" и источник для заказов
            order_data['status'] = 'Новый'
            order_data['source'] = 'telegram'
            
            # Генерация уникального ID заказа, если он не указан
            if 'id' not in order_data:
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                order_data['id'] = f"TG{timestamp}"
            
            logger.info(f"Заказ успешно обработан: ID={order_data.get('id', 'н/д')}")
            return order_data
            
        except Exception as e:
            logger.error(f"Ошибка при обработке заказа: {str(e)}")
            return {"error": f"Ошибка при обработке заказа: {str(e)}"}
    
    def extract_order_from_text(self, text: str) -> Dict[str, Any]:
        """
        Извлекает данные заказа из неструктурированного текста.
        Метод-адаптер для совместимости с TelegramBot.
        
        Args:
            text (str): Неструктурированный текст заказа.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа.
        """
        return self.process_order_text(text)
    
    def monitor_file_changes(self) -> None:
        """
        Мониторинг изменений в файлах на Google Drive.
        Запускается в отдельном потоке.
        """
        logger.info("Запущен мониторинг изменений файлов")
        
        while self.should_run:
            try:
                # Проверка обновлений в основных файлах
                changed_files = self.gdrive.watch_folder()
                
                if changed_files:
                    logger.info(f"Обнаружены изменения в {len(changed_files)} файлах")
                    
                    # Проверяем, изменился ли файл заказов
                    orders_changed = any(
                        file.get('name') == self.orders_filename 
                        for file in changed_files
                    )
                    
                    if orders_changed:
                        logger.info("Файл заказов был изменен, запускаем обработку")
                        self.run_queue_processing()
                    else:
                        logger.info("Изменения не касаются файла заказов")
                
                # Проверяем новые текстовые заказы
                self.check_new_order_files()
                
                # Ожидание до следующей проверки
                sleep_interval = self.check_interval_minutes * 60
                for _ in range(sleep_interval):
                    if not self.should_run:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Ошибка при мониторинге файлов: {str(e)}")
                time.sleep(60)  # Пауза перед повторной попыткой
    
    def check_new_order_files(self) -> None:
        """
        Проверяет наличие новых текстовых файлов с заказами в специальной папке Google Drive,
        обрабатывает их и добавляет в очередь печати.
        """
        try:
            # Получаем список текстовых файлов с новыми заказами
            order_files = self.gdrive.watch_for_txt_files()
            
            if not order_files:
                logger.debug("Новых текстовых файлов с заказами не обнаружено")
                return
                
            logger.info(f"Обнаружено {len(order_files)} новых текстовых файлов с заказами")
            
            processed_orders = []
            
            # Обрабатываем каждый файл
            for file_info in order_files:
                file_name = file_info['name']
                file_id = file_info['id']
                
                logger.info(f"Обработка файла заказа: {file_name}")
                
                # Получаем содержимое файла
                file_content = self.gdrive.get_file_content_as_string(file_name)
                
                if not file_content:
                    logger.error(f"Не удалось прочитать содержимое файла {file_name}")
                    continue
                
                # Обрабатываем текст заказа
                order_data = self.process_order_text(file_content)
                
                if "error" in order_data:
                    logger.error(f"Ошибка при обработке заказа из файла {file_name}: {order_data['error']}")
                    continue
                
                # Устанавливаем источник заказа
                order_data['source'] = 'gdrive_txt'
                
                # Добавляем в список обработанных заказов
                processed_orders.append(order_data)
                
                # Удаляем обработанный файл
                self.gdrive.delete_file(file_name)
                logger.info(f"Файл {file_name} успешно обработан и удален")
            
            if processed_orders:
                # Скачиваем файл очереди
                files = self.download_files_from_gdrive()
                
                if not files or "queue" not in files:
                    logger.error("Не удалось получить файл очереди печати")
                    return
                
                # Обновляем очередь печати
                queue_result = self.update_queue(processed_orders, files["queue"])
                
                if queue_result["status"] == "error":
                    logger.error(f"Ошибка при обновлении очереди: {queue_result.get('error')}")
                    return
                
                # Загружаем обновленный файл очереди обратно в Google Drive
                upload_success = self.upload_files_to_gdrive({
                    "queue": queue_result["queue_file"]
                })
                
                # Генерируем и отправляем уведомление
                if upload_success:
                    queue_summary = self.generate_queue_summary(processed_orders)
                    self.send_notifications(queue_summary, processed_orders)
                    logger.info(f"Очередь успешно обновлена с {len(processed_orders)} новыми заказами")
                
        except Exception as e:
            logger.error(f"Ошибка при проверке новых файлов заказов: {str(e)}")
    
    def run_queue_processing(self) -> Dict[str, Any]:
        """
        Запуск полного цикла обработки очереди.
        Включает скачивание файлов, обработку заказов, обновление очереди и отправку уведомлений.
        
        Returns:
            Dict[str, Any]: Результат обработки.
        """
        logger.info("Запуск цикла обработки очереди печати")
        
        try:
            # Скачивание файлов из Google Drive
            files = self.download_files_from_gdrive()
            
            if not files or "orders" not in files or "queue" not in files:
                logger.error("Не удалось получить необходимые файлы для обработки")
                return {"status": "error", "message": "Ошибка при скачивании файлов"}
            
            # Обработка заказов с использованием Claude
            processed_orders = self.process_orders_with_claude(files["orders"])
            
            if not processed_orders:
                logger.warning("Нет заказов для обработки или произошла ошибка")
                return {"status": "no_orders", "message": "Нет заказов для обработки"}
            
            # Обновление очереди
            queue_result = self.update_queue(processed_orders, files["queue"])
            
            if queue_result["status"] == "error":
                logger.error(f"Ошибка при обновлении очереди: {queue_result.get('error')}")
                return {"status": "error", "message": f"Ошибка при обновлении очереди: {queue_result.get('error')}"}
            
            # Загрузка обновленных файлов обратно в Google Drive
            upload_success = self.upload_files_to_gdrive({
                "queue": queue_result["queue_file"]
            })
            
            # Генерация сводки по очереди
            queue_summary = self.generate_queue_summary(processed_orders)
            
            # Отправка уведомлений
            notification_sent = self.send_notifications(queue_summary, processed_orders)
            
            return {
                "status": "success",
                "processed_orders": len(processed_orders),
                "upload_success": upload_success,
                "notification_sent": notification_sent,
                "summary": queue_summary
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке очереди: {str(e)}")
            return {"status": "error", "message": f"Ошибка при обработке очереди: {str(e)}"}
    
    def start_monitoring(self) -> threading.Thread:
        """
        Запускает мониторинг изменений файлов в фоновом режиме.
        
        Returns:
            threading.Thread: Объект потока мониторинга.
        """
        if self.background_thread and self.background_thread.is_alive():
            logger.warning("Мониторинг файлов уже запущен")
            return self.background_thread
        
        self.should_run = True
        self.background_thread = threading.Thread(
            target=self.monitor_file_changes,
            daemon=True
        )
        self.background_thread.start()
        logger.info("Мониторинг файлов запущен в фоновом режиме")
        
        return self.background_thread
    
    def stop_monitoring(self) -> None:
        """Останавливает мониторинг изменений файлов."""
        if not self.background_thread or not self.background_thread.is_alive():
            logger.warning("Мониторинг файлов не был запущен")
            return
        
        logger.info("Остановка мониторинга файлов...")
        self.should_run = False
        self.background_thread.join(timeout=10)  # Ожидание завершения потока
        logger.info("Мониторинг файлов остановлен")
    
    def start_telegram_bot(self) -> None:
        """Запускает Telegram-бота."""
        if hasattr(self, 'telegram_bot') and self.telegram_bot:
            logger.info("Запуск Telegram-бота")
            self.telegram_bot.start_polling()
        else:
            logger.warning("Telegram-бот не инициализирован")
    
    def run_agent(self, monitor=True, telegram=True) -> None:
        """
        Запускает агента очереди печати со всеми активными компонентами.
        
        Args:
            monitor (bool): Запустить мониторинг файлов.
            telegram (bool): Запустить Telegram-бота.
        """
        logger.info("Запуск агента очереди печати")
        
        # Первичная обработка очереди
        initial_result = self.run_queue_processing()
        logger.info(f"Результат начальной обработки: {initial_result}")
        
        # Запуск мониторинга файлов
        if monitor:
            self.start_monitoring()
        
        # Запуск Telegram-бота
        if telegram and hasattr(self, 'telegram_bot') and self.telegram_bot:
            self.start_telegram_bot()
        
        logger.info("Агент очереди печати успешно запущен")


def main():
    """Точка входа в приложение."""
    parser = argparse.ArgumentParser(description="Агент очереди печати с интеграцией Claude 3.5 Haiku")
    parser.add_argument('--config', type=str, default='config.yaml', help='Путь к файлу конфигурации')
    parser.add_argument('--no-monitor', action='store_true', help='Отключить мониторинг изменений файлов')
    parser.add_argument('--no-telegram', action='store_true', help='Отключить Telegram-бота')
    parser.add_argument('--process-once', action='store_true', help='Выполнить однократную обработку очереди без запуска сервисов')
    
    args = parser.parse_args()
    
    # Инициализация агента
    agent = PrintQueueAgent(config_path=args.config)
    
    if args.process_once:
        # Только однократная обработка без запуска сервисов
        result = agent.run_queue_processing()
        print(f"Результат обработки очереди: {json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        # Запуск агента с указанными флагами
        agent.run_agent(
            monitor=not args.no_monitor,
            telegram=not args.no_telegram
        )
        
        try:
            # Бесконечный цикл для поддержания работы основного потока
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            # Корректное завершение при нажатии Ctrl+C
            print("\nЗавершение работы агента...")
            agent.stop_monitoring()
            print("Работа агента завершена")


if __name__ == "__main__":
    main()
