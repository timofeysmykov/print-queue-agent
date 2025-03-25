"""Модуль для обработки неструктурированных описаний заказов с помощью Claude API.
Преобразует текстовые описания в структурированные данные для дальнейшей обработки.
"""

import os
import logging
import json
import yaml
import datetime
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Импорт клиента Claude API
from claude_api import ClaudeAPIClient

# Настройка логирования
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/data_processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("data_processing")

class OrderProcessor:
    """Класс для обработки заказов и извлечения информации."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация процессора заказов.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Загрузка конфигурации
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
            logger.info("Конфигурация успешно загружена")
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации: {str(e)}")
            self.config = {}
        
        # Инициализация клиента Claude API
        try:
            self.claude_client = ClaudeAPIClient()
            logger.info("Инициализирован клиент Claude API для обработки заказов")
        except Exception as e:
            logger.error(f"Ошибка при инициализации клиента Claude API: {str(e)}")
            self.claude_client = None
            
        logger.info("Инициализация процессора заказов завершена")
    
    def process_order_text(self, text: str) -> Dict[str, Any]:
        """
        Обрабатывает текстовое описание заказа и извлекает структурированные данные.
        
        Args:
            text (str): Текстовое описание заказа.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа или словарь с ошибкой.
        """
        logger.info(f"Обработка текста заказа: {text[:50]}...")
        
        if not self.claude_client:
            error_msg = "Claude API клиент не инициализирован"
            logger.error(error_msg)
            return {"error": error_msg}
        
        try:
            # Формирование промпта для Claude API
            prompt = f"""
            Проанализируй следующее описание заказа печати и извлеки из него структурированную информацию. 
            Верни результат ТОЛЬКО в формате JSON со следующими полями:
            - customer: имя клиента или организации
            - contact: контактная информация (телефон, email)
            - description: краткое описание заказа
            - quantity: количество или объем заказа
            - deadline: срок выполнения (в формате ДД.ММ.ГГГГ)
            - priority: приоритет заказа (срочно, обычный)
            
            Если какой-то информации нет в тексте, оставь соответствующее поле пустым.
            
            Описание заказа: {text}
            """
            
            # Отправка запроса к Claude API
            response = self.claude_client.process_prompt(prompt)
            
            # Извлечение JSON из ответа
            order_data = self.claude_client.extract_json_from_response(response)
            
            # Проверка на наличие ошибок
            if "error" in order_data:
                logger.error(f"Ошибка при обработке заказа: {order_data['error']}")
                return order_data
            
            # Добавление метаданных
            order_data['status'] = 'Новый'
            order_data['source'] = 'telegram'
            
            # Генерация уникального ID заказа
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            order_data['order_id'] = f"TG{timestamp}"
            
            logger.info(f"Заказ успешно обработан: ID={order_data.get('order_id', 'н/д')}")
            return order_data
                
        except Exception as e:
            error_msg = f"Ошибка при обработке заказа: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
    
    def batch_process_orders(self, order_texts: List[str]) -> List[Dict[str, Any]]:
        """
        Пакетная обработка нескольких текстовых описаний заказов.
        
        Args:
            order_texts (List[str]): Список текстовых описаний заказов.
            
        Returns:
            List[Dict[str, Any]]: Список структурированных данных заказов.
        """
        logger.info(f"Начало пакетной обработки {len(order_texts)} заказов")
        results = []
        
        for i, text in enumerate(order_texts):
            logger.info(f"Обработка заказа {i+1}/{len(order_texts)}")
            result = self.process_order_text(text)
            results.append(result)
            
        logger.info(f"Завершена пакетная обработка {len(order_texts)} заказов")
        return results


# Пример использования
if __name__ == "__main__":
    processor = OrderProcessor()
    
    test_order = """
    Клиент: ООО "Ромашка"
    Контакт: Иванов Иван, +7 (999) 123-45-67
    Заказ: Печать 100 буклетов А4, цветная, двусторонняя
    Срок: 25.05.2024
    Приоритет: Срочно
    """
    
    result = processor.process_order_text(test_order)
    print(json.dumps(result, indent=2, ensure_ascii=False))
