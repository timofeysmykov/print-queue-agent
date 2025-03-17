#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль для работы с Claude API.
Обеспечивает надёжную интеграцию с API Anthropic Claude,
используя прямые HTTP запросы вместо библиотеки anthropic.
"""

import os
import logging
import json
import requests
from typing import Dict, List, Any, Union, Optional
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("claude_api")

class ClaudeAPIClient:
    """
    Клиент для работы с Claude API от Anthropic.
    Использует прямые HTTP запросы для большей надёжности и контроля.
    """
    
    # API URL для Anthropic Claude
    API_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self):
        """
        Инициализация клиента Claude API.
        Загружает API ключ из переменных окружения.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Получение API ключа
        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            logger.error("API ключ Claude не найден в переменных окружения")
            raise ValueError("Необходимо указать CLAUDE_API_KEY в .env файле")
        
        # Настройка заголовков для API запросов
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Параметры по умолчанию
        self.default_model = "claude-3-haiku-20240307"
        self.default_max_tokens = 1000
        self.default_temperature = 0.1
        
        logger.info(f"Клиент Claude API инициализирован (API ключ: {self.api_key[:6]}...)")
    
    def process_prompt(self, 
                      prompt: str, 
                      model: str = None,
                      max_tokens: int = None,
                      temperature: float = None) -> str:
        """
        Отправляет промпт в Claude API через прямой HTTP запрос.
        
        Args:
            prompt (str): Текст промпта для обработки.
            model (str, optional): Модель Claude для использования.
            max_tokens (int, optional): Максимальное количество токенов в ответе.
            temperature (float, optional): Температура генерации (0.0-1.0).
            
        Returns:
            str: Ответ от Claude API.
            
        Raises:
            Exception: В случае ошибки при вызове API.
        """
        try:
            # Использование значений по умолчанию, если не указаны явно
            model = model or self.default_model
            max_tokens = max_tokens or self.default_max_tokens
            temperature = temperature if temperature is not None else self.default_temperature
            
            logger.info(f"Отправка запроса к Claude API (модель: {model})")
            logger.debug(f"Промпт: {prompt[:100]}...")
            
            # Формирование данных запроса
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            # Отправка HTTP запроса к API Claude
            response = requests.post(
                self.API_URL,
                headers=self.headers,
                json=payload,
                timeout=60  # Таймаут 60 секунд
            )
            
            # Проверка на ошибки
            response.raise_for_status()
            
            # Парсинг ответа
            response_data = response.json()
            
            # Извлечение текста из ответа
            if "content" in response_data and len(response_data["content"]) > 0:
                # Проверяем формат ответа
                if isinstance(response_data["content"], list) and "text" in response_data["content"][0]:
                    result = response_data["content"][0]["text"]
                elif isinstance(response_data["content"], list) and "type" in response_data["content"][0] and response_data["content"][0]["type"] == "text":
                    result = response_data["content"][0]["text"]
                else:
                    logger.warning("Неизвестный формат ответа от Claude API")
                    logger.debug(f"Содержимое content: {response_data['content']}")
                    return str(response_data)
            else:
                logger.warning("Неожиданный формат ответа от Claude API")
                logger.debug(f"Полученный ответ: {response_data}")
                return str(response_data)
            logger.info(f"Получен ответ от Claude API длиной {len(result)} символов")
            logger.debug(f"Ответ: {result[:100]}...")
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP при вызове Claude API: {str(e)}")
            raise Exception(f"Ошибка при связи с Claude API: {str(e)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка при парсинге ответа Claude API: {str(e)}")
            raise Exception(f"Неверный формат ответа от Claude API: {str(e)}")
            
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при вызове Claude API: {str(e)}")
            raise
    
    def extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """
        Извлекает JSON из текстового ответа Claude.
        
        Args:
            response_text (str): Текстовый ответ от Claude API.
            
        Returns:
            Dict[str, Any]: Распарсенный JSON или словарь с ошибкой.
        """
        try:
            # Попытка найти JSON в тексте (между фигурными скобками)
            if '{' in response_text and '}' in response_text:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_str = response_text[start:end]
                
                # Парсинг JSON
                result = json.loads(json_str)
                logger.info(f"JSON успешно извлечен из ответа Claude")
                return result
            else:
                # Альтернативная попытка: ищем JSON между маркерами
                if '```json' in response_text and '```' in response_text:
                    start = response_text.find('```json') + 7
                    end = response_text.find('```', start)
                    json_str = response_text[start:end].strip()
                    
                    # Парсинг JSON
                    result = json.loads(json_str)
                    logger.info(f"JSON успешно извлечен из блока кода в ответе Claude")
                    return result
                    
                logger.warning("JSON не найден в ответе Claude")
                return {"error": "JSON не найден в ответе"}
                
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка при парсинге JSON: {str(e)}")
            return {"error": f"Ошибка при парсинге JSON: {str(e)}"}
            
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при извлечении JSON: {str(e)}")
            return {"error": f"Непредвиденная ошибка: {str(e)}"}
    
    def process_order_text(self, order_text: str) -> Dict[str, Any]:
        """
        Обрабатывает текст заказа и извлекает структурированные данные.
        
        Args:
            order_text (str): Неструктурированный текст заказа.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа.
        """
        # Промпт для извлечения данных заказа
        prompt = f"""Извлеки все данные о заказе на печать из следующего текста: 
{order_text}

Верни результат в виде JSON со следующими полями:
- customer: имя клиента или название организации
- contact: контактные данные (телефон, email)
- description: краткое описание заказа
- quantity: количество копий
- deadline: срок выполнения в формате DD.MM.YYYY
- format: формат бумаги (A4, A3 и т.д.)
- paper_type: тип бумаги
- color_mode: цветная или черно-белая печать
- duplex: односторонняя или двусторонняя печать
- priority: приоритет (высокий, средний, низкий)
- comment: любые дополнительные пожелания или особенности

Если какие-то поля невозможно определить, оставь их пустыми.
Включи только JSON в твой ответ, без пояснений или текста вокруг него."""
        
        try:
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.1
            )
            
            # Извлечение JSON из ответа
            order_data = self.extract_json_from_response(response)
            
            # Проверка на наличие ошибок
            if "error" in order_data:
                logger.error(f"Ошибка при обработке заказа: {order_data['error']}")
                return {"error": order_data["error"]}
            
            logger.info(f"Заказ успешно обработан и структурирован")
            return order_data
            
        except Exception as e:
            logger.error(f"Ошибка при обработке заказа: {str(e)}")
            return {"error": f"Ошибка при обработке заказа: {str(e)}"}


# Тестирование модуля
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    try:
        # Тестовый пример заказа
        test_order = "ООО Рога и Копыта, +7(999)123-45-67, напечатать 500 брошюр на глянцевой бумаге, цветная двусторонняя печать, срок до 25.03.2025"
        
        # Инициализация клиента
        claude_client = ClaudeAPIClient()
        
        # Обработка тестового заказа
        print("Обработка тестового заказа...")
        result = claude_client.process_order_text(test_order)
        
        # Вывод результата
        print("\nРезультат обработки заказа:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"Ошибка при тестировании: {str(e)}")
