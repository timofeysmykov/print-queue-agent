#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки обновленной интеграции с Claude API.
"""

import os
import sys
import logging
import json
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test")

# Импорт наших модулей
from claude_api import ClaudeAPIClient
from data_processing import OrderProcessor

def test_claude_api_direct():
    """Проверка прямого использования модуля claude_api"""
    try:
        logger.info("Тестирование прямого взаимодействия с Claude API...")
        
        # Инициализация клиента
        client = ClaudeAPIClient()
        logger.info("Клиент Claude API успешно инициализирован")
        
        # Тестовый заказ
        test_order = "ООО Рога и Копыта, +7(999)123-45-67, напечатать 500 брошюр на глянцевой бумаге, цветная двусторонняя печать, срок до 25.06.2023"
        
        # Обработка заказа
        logger.info("Отправка тестового заказа на обработку...")
        result = client.process_order_text(test_order)
        
        # Вывод результата
        logger.info("Результат обработки заказа:")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании прямого взаимодействия с Claude API: {str(e)}")
        return False

def test_order_processor():
    """Проверка работы OrderProcessor с Claude API"""
    try:
        logger.info("Тестирование OrderProcessor с обновленной интеграцией Claude API...")
        
        # Инициализация процессора заказов
        processor = OrderProcessor()
        logger.info("Процессор заказов успешно инициализирован")
        
        # Тестовый заказ
        test_order = "Компания ABC Tech, контакт: info@abctech.com, необходимо срочно напечатать 100 цветных буклетов формата A4 на плотной бумаге до 15.07.2023"
        
        # Обработка заказа
        logger.info("Отправка тестового заказа на обработку через OrderProcessor...")
        result = processor.extract_order_from_text(test_order)
        
        # Вывод результата
        logger.info("Результат обработки заказа через OrderProcessor:")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании OrderProcessor: {str(e)}")
        return False

if __name__ == "__main__":
    # Загрузка переменных окружения
    load_dotenv()
    
    # Проверка наличия ключа API
    if not os.getenv("CLAUDE_API_KEY"):
        logger.error("Ключ API Claude не найден. Убедитесь, что он указан в файле .env")
        sys.exit(1)
    
    # Запуск тестов
    logger.info("=== Начало тестирования интеграции с Claude API ===")
    
    # Тест прямого взаимодействия с Claude API
    direct_test_success = test_claude_api_direct()
    
    # Тест OrderProcessor
    processor_test_success = test_order_processor()
    
    # Итоги тестирования
    logger.info("=== Результаты тестирования ===")
    logger.info(f"Прямое взаимодействие с Claude API: {'УСПЕШНО' if direct_test_success else 'ОШИБКА'}")
    logger.info(f"OrderProcessor с Claude API: {'УСПЕШНО' if processor_test_success else 'ОШИБКА'}")
    
    if direct_test_success and processor_test_success:
        logger.info("Все тесты успешно пройдены!")
        sys.exit(0)
    else:
        logger.error("Тестирование завершилось с ошибками.")
        sys.exit(1)
