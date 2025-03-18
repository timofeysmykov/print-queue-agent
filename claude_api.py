#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль для работы с Claude API.
Обеспечивает надёжную интеграцию с API Anthropic Claude 3.5 Haiku,
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/claude_api.log"),
        logging.StreamHandler()
    ]
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
        
        # Создание директории для логов, если она не существует
        os.makedirs("logs", exist_ok=True)
        
        # Настройка заголовков для API запросов
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Параметры по умолчанию для Claude 3.5 Haiku
        self.default_model = "claude-3-haiku-20240307"
        self.default_max_tokens = 4000
        self.default_temperature = 0.0
        
        logger.info(f"Клиент Claude API инициализирован (модель: {self.default_model})")
    
    def process_prompt(self, 
                      prompt: str, 
                      model: str = None,
                      max_tokens: int = None,
                      temperature: float = None,
                      system_prompt: str = None) -> str:
        """
        Отправляет промпт в Claude API через прямой HTTP запрос.
        
        Args:
            prompt (str): Текст промпта для обработки.
            model (str, optional): Модель Claude для использования.
            max_tokens (int, optional): Максимальное количество токенов в ответе.
            temperature (float, optional): Температура генерации (0.0-1.0).
            system_prompt (str, optional): Системный промпт для задания контекста.
            
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
            
            # Формирование данных запроса
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            # Добавляем системный промпт, если он указан
            if system_prompt:
                payload["system"] = system_prompt
            
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
                content_item = response_data["content"][0]
                if "text" in content_item:
                    result = content_item["text"]
                elif "type" in content_item and content_item["type"] == "text":
                    result = content_item["text"]
                else:
                    logger.warning("Неизвестный формат ответа от Claude API")
                    return str(response_data)
            else:
                logger.warning("Неожиданный формат ответа от Claude API")
                return str(response_data)
                
            logger.info(f"Получен ответ от Claude API длиной {len(result)} символов")
            
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

        # Системный промпт для задания контекста
        system_prompt = """Ты специалист по обработке заказов на печать. 
Твоя задача - извлекать структурированные данные из текстовых описаний заказов.
Все ответы должны быть в формате JSON, без пояснений или дополнительного текста."""
        
        try:
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=1000,
                temperature=0.0
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
    
    def analyze_orders_data(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализирует данные заказов и предлагает оптимальную очередь печати.
        
        Args:
            orders_data (List[Dict[str, Any]]): Список структурированных данных о заказах.
            
        Returns:
            Dict[str, Any]: Результат анализа с предложенной очередью и обоснованием.
        """
        try:
            # Преобразование данных заказов в формат для модели
            orders_json = json.dumps(orders_data, ensure_ascii=False, indent=2)
            
            # Промпт для анализа заказов и формирования очереди печати
            prompt = f"""Проанализируй следующие заказы на печать и создай оптимальную очередь их выполнения:

```json
{orders_json}
```

Учитывай следующие критерии (в порядке важности):
1. Срок выполнения (deadline) - приоритет заказам с ближайшими сроками
2. Приоритет заказа (priority) - высокий, средний, низкий
3. Объем работы (quantity)
4. Схожие технические параметры (бумага, формат, цвет) - группировка похожих заказов вместе
5. Время поступления заказа (более ранние имеют преимущество при прочих равных)

Верни результат в формате JSON:
```json
{
  "queue": [
    {
      "order_id": 1,  // ID или порядковый номер заказа из исходных данных
      "position": 1,  // Позиция в очереди
      "estimated_completion_time": "строка с примерным временем выполнения",
      "reason": "краткое обоснование позиции в очереди"
    },
    // другие заказы
  ],
  "optimization_notes": "общие замечания по оптимизации очереди",
  "estimated_total_completion_time": "строка с примерным временем выполнения всей очереди"
}
```

Обязательно включи в ответ только JSON, без дополнительных пояснений или текста вокруг него."""

            # Системный промпт для задания контекста
            system_prompt = """Ты эксперт по оптимизации производственных процессов в печатном центре.
Твоя задача - анализировать заказы и создавать наиболее эффективную очередь печати.
Все ответы должны быть в формате JSON, без пояснений или дополнительного текста."""
            
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=2000,
                temperature=0.0
            )
            
            # Извлечение JSON из ответа
            queue_data = self.extract_json_from_response(response)
            
            # Проверка на наличие ошибок
            if "error" in queue_data:
                logger.error(f"Ошибка при анализе заказов: {queue_data['error']}")
                return {"error": queue_data["error"]}
            
            logger.info(f"Анализ заказов успешно выполнен, сформирована очередь из {len(queue_data.get('queue', []))} позиций")
            return queue_data
            
        except Exception as e:
            logger.error(f"Ошибка при анализе заказов: {str(e)}")
            return {"error": f"Ошибка при анализе заказов: {str(e)}"}
    
    def summarize_orders_and_queue(self, orders_data: List[Dict[str, Any]], queue_data: Dict[str, Any]) -> str:
        """
        Создает краткую сводку по заказам и очереди печати для отправки пользователям.
        
        Args:
            orders_data (List[Dict[str, Any]]): Список структурированных данных о заказах.
            queue_data (Dict[str, Any]): Данные сформированной очереди печати.
            
        Returns:
            str: Текстовая сводка по заказам и очереди.
        """
        try:
            # Преобразование данных в формат для модели
            orders_json = json.dumps(orders_data, ensure_ascii=False, indent=2)
            queue_json = json.dumps(queue_data, ensure_ascii=False, indent=2)
            
            # Промпт для создания сводки
            prompt = f"""Создай краткую, но информативную сводку по заказам на печать и сформированной очереди на основе следующих данных:

**Данные заказов:**
```json
{orders_json}
```

**Данные очереди:**
```json
{queue_json}
```

Сводка должна быть лаконичной и содержать:
1. Общее количество заказов
2. Важные заказы с высоким приоритетом или ближайшим сроком
3. Общее расчетное время выполнения всех заказов
4. Любые особые замечания или проблемы

Сводка должна быть написана простым языком, понятным для персонала печатного центра.
Текст должен быть отформатирован для удобного чтения. Не используй сложные технические термины."""

            # Системный промпт для задания контекста
            system_prompt = """Ты аналитик в печатном центре. 
Твоя задача - создавать понятные сводки для персонала печатного центра на основе технических данных.
Пиши понятным языком без технического жаргона."""
            
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=1500,
                temperature=0.2  # Небольшая вариативность для текста
            )
            
            logger.info(f"Сводка успешно сформирована ({len(response)} символов)")
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при создании сводки: {str(e)}")
            return f"Ошибка при создании сводки: {str(e)}"
    
    def process_excel_data(self, excel_data_json: str) -> Dict[str, Any]:
        """
        Обрабатывает структурированные данные из Excel-файла для создания очереди печати.
        
        Args:
            excel_data_json (str): JSON с данными из Excel-файла.
            
        Returns:
            Dict[str, Any]: Обработанные данные с рекомендациями.
        """
        try:
            # Формирование промпта для обработки данных Excel
            prompt = f"""Проанализируй следующие данные из Excel-файла с заказами на печать:

```json
{excel_data_json}
```

Выполни следующие задачи:
1. Проверь данные на корректность и полноту
2. Создай оптимальную очередь печати с учетом сроков, приоритетов и технических параметров
3. Выяви любые проблемы или несоответствия в данных
4. Рассчитай приблизительное время завершения всех заказов

Верни результат в формате JSON:
```json
{
  "validation": {
    "is_valid": true|false,
    "issues": ["список проблем или несоответствий"],
    "missing_data": ["список полей с отсутствующими данными"]
  },
  "queue": [
    {
      "order_id": "идентификатор заказа",
      "position": 1,
      "reason": "обоснование позиции"
    }
  ],
  "estimated_completion": "общее расчетное время",
  "recommendations": ["список рекомендаций по оптимизации"]
}
```

Верни только JSON, без дополнительного текста или пояснений."""

            # Системный промпт для задания контекста
            system_prompt = """Ты эксперт по анализу данных печатного производства.
Твоя задача - проверять корректность данных из Excel и формировать оптимальные производственные планы.
Возвращай только JSON без пояснений."""
            
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=2500,
                temperature=0.0
            )
            
            # Извлечение JSON из ответа
            result = self.extract_json_from_response(response)
            
            # Проверка на наличие ошибок
            if "error" in result:
                logger.error(f"Ошибка при обработке данных Excel: {result['error']}")
                return {"error": result["error"]}
            
            logger.info(f"Данные Excel успешно обработаны")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при обработке данных Excel: {str(e)}")
            return {"error": f"Ошибка при обработке данных Excel: {str(e)}"}
    
    def generate_report(self, order_data: Dict[str, Any], execution_data: Dict[str, Any] = None) -> str:
        """
        Генерирует отчет о выполнении заказа на печать.
        
        Args:
            order_data (Dict[str, Any]): Данные о заказе.
            execution_data (Dict[str, Any], optional): Данные о выполнении заказа.
            
        Returns:
            str: Отформатированный отчет для клиента.
        """
        try:
            # Преобразование данных в формат для модели
            order_json = json.dumps(order_data, ensure_ascii=False, indent=2)
            
            execution_json = ""
            if execution_data:
                execution_json = f"""

**Данные о выполнении:**
```json
{json.dumps(execution_data, ensure_ascii=False, indent=2)}
```"""
                
            # Промпт для создания отчета
            prompt = f"""Создай официальный отчет о выполнении заказа на печать на основе следующих данных:

**Данные заказа:**
```json
{order_json}
```{execution_json}

Отчет должен включать:
1. Информацию о заказчике
2. Описание заказа
3. Технические параметры печати
4. Информацию о выполнении (если она предоставлена)
5. Дату и время создания отчета

Отчет должен быть официальным и профессиональным, но при этом понятным для клиента."""

            # Системный промпт для задания контекста
            system_prompt = """Ты помощник менеджера по работе с клиентами в печатном центре.
Твоя задача - составлять официальные, но понятные отчеты о выполнении заказов для клиентов."""
            
            # Отправка запроса к Claude API
            response = self.process_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=2000,
                temperature=0.2
            )
            
            logger.info(f"Отчет успешно сгенерирован ({len(response)} символов)")
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при генерации отчета: {str(e)}")
            return f"Ошибка при генерации отчета: {str(e)}"


# Тестирование модуля
if __name__ == "__main__":
    # Настройка для тестирования
    logging.basicConfig(level=logging.DEBUG)
    
    # Создание клиента Claude API
    claude = ClaudeAPIClient()
    
    # Пример обработки текста заказа
    test_order = """
    Заказ на печать: Компания "ТехноСтарт"
    Контакт: Иванов Иван, ivan@technostart.ru, +7-999-123-4567
    Требуется напечатать 100 цветных брошюр на глянцевой бумаге A4, двусторонняя печать.
    Срок исполнения: 25.05.2024. Высокий приоритет.
    Дополнительно: требуется сшивание скобами по краю.
    """
    
    # Обработка заказа
    print("Обработка текста заказа:")
    order_data = claude.process_order_text(test_order)
    print(json.dumps(order_data, ensure_ascii=False, indent=2))
    
    # Генерация отчета
    print("\nГенерация отчета:")
    report = claude.generate_report(order_data)
    print(report)
