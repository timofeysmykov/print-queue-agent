#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки работы Claude API
"""

import os
import json
import logging
import anthropic
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_claude_api():
    """Тестирует подключение к Claude API и базовую функциональность"""
    
    # Загрузка переменных окружения
    load_dotenv()
    
    # Получение API ключа
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("API ключ Claude не найден")
        return False
    
    logger.info(f"API ключ Claude получен: {api_key[:10]}...")
    
    try:
        # Инициализация клиента
        client = anthropic.Anthropic(api_key=api_key)
        
        # Тестовый вызов API
        test_prompt = "Привет! Ты работаешь? Ответь коротко 'Да, я работаю!' если это так."
        
        logger.info("Отправка тестового запроса к Claude API...")
        
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=100,
            temperature=0.1,
            messages=[
                {"role": "user", "content": test_prompt}
            ]
        )
        
        # Вывод результата
        result = response.content[0].text
        logger.info(f"Получен ответ от Claude API: {result}")
        
        # Пробуем тестовый запрос на структурирование данных заказа
        order_prompt = """Извлеки все данные о заказе на печать из следующего текста: 
LLC Labs, +79261234567, картонная бумага, 20.03.25, обычная печать, 1000шт.

Верни результат в виде JSON со следующими полями:
- customer: имя клиента или название организации
- contact: контактные данные (телефон, email)
- description: краткое описание заказа
- quantity: количество копий
- deadline: срок выполнения в формате DD.MM.YYYY
- paper_type: тип бумаги
- color_mode: цветная или черно-белая печать

Если какие-то поля невозможно определить, оставь их пустыми."""
        
        logger.info("Отправка тестового запроса на структурирование заказа...")
        
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.1,
            messages=[
                {"role": "user", "content": order_prompt}
            ]
        )
        
        # Вывод результата структурирования
        structured_result = response.content[0].text
        logger.info(f"Получен структурированный ответ: {structured_result}")
        
        # Пробуем извлечь JSON из ответа
        try:
            # Ищем JSON в тексте
            if '{' in structured_result and '}' in structured_result:
                start = structured_result.find('{')
                end = structured_result.rfind('}') + 1
                json_data = structured_result[start:end]
                
                # Парсим JSON
                parsed_json = json.loads(json_data)
                logger.info(f"Успешно извлечен и распарсен JSON: {json.dumps(parsed_json, ensure_ascii=False, indent=2)}")
            else:
                logger.error("Не удалось найти JSON в ответе")
        except Exception as e:
            logger.error(f"Ошибка при обработке JSON: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при работе с Claude API: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Запуск теста Claude API...")
    success = test_claude_api()
    
    if success:
        logger.info("Тест Claude API успешно завершен")
    else:
        logger.error("Тест Claude API завершился с ошибкой")
