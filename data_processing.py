"""
Модуль для обработки неструктурированных описаний заказов с помощью LLM.
Преобразует текстовые описания в структурированные данные для дальнейшей обработки.
"""

import os
import logging
import json
import yaml
import datetime
import anthropic
import openai
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/data_processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("data_processing")

class LLMProcessor:
    """Класс для обработки текста с помощью LLM."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация процессора LLM.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка переменных окружения
        load_dotenv()
        
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        
        # Получение настроек LLM
        self.llm_config = self.config.get('llm', {})
        self.provider = self.llm_config.get('provider', 'claude').lower()
        self.model = self.llm_config.get('model', 'claude-3-haiku-20240307')
        self.max_tokens = self.llm_config.get('max_tokens', 1000)
        self.temperature = self.llm_config.get('temperature', 0.1)
        
        # Инициализация клиента API в зависимости от провайдера
        if self.provider == 'claude':
            self.api_key = os.getenv("CLAUDE_API_KEY")
            if not self.api_key:
                logger.error("API ключ Claude не найден")
                raise ValueError("Необходимо указать CLAUDE_API_KEY в .env файле")
            
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == 'openai':
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                logger.error("API ключ OpenAI не найден")
                raise ValueError("Необходимо указать OPENAI_API_KEY в .env файле")
            
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            logger.error(f"Неподдерживаемый провайдер LLM: {self.provider}")
            raise ValueError(f"Неподдерживаемый провайдер LLM: {self.provider}")
            
        logger.info(f"Инициализация LLM процессора с провайдером {self.provider} и моделью {self.model}")
    
    def process_text(self, text: str, prompt: str = None) -> Union[str, Dict[str, Any]]:
        """
        Обработка текста с помощью LLM.
        
        Args:
            text (str): Текст для обработки.
            prompt (str, optional): Дополнительный промпт, объясняющий задачу.
            
        Returns:
            Union[str, Dict[str, Any]]: Результат обработки текста.
        """
        if not prompt:
            prompt = "Проанализируй следующее описание заказа и извлеки из него ключевую информацию."
        
        full_prompt = f"{prompt}\n\nОписание заказа: {text}"
        
        try:
            if self.provider == 'claude':
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=[
                        {"role": "user", "content": full_prompt}
                    ]
                )
                return response.content[0].text
                
            elif self.provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": "Ты - помощник, который извлекает структурированную информацию из текстовых описаний заказов."},
                        {"role": "user", "content": full_prompt}
                    ]
                )
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Ошибка при вызове LLM: {str(e)}")
            raise


class OrderProcessor:
    """Класс для обработки заказов и извлечения информации."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация процессора заказов.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Инициализация LLM процессора
        self.llm = LLMProcessor(config_path)
        
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
            
        logger.info("Инициализация процессора заказов")
        
    def extract_order_from_text(self, text: str) -> Dict[str, Any]:
        """
        Извлекает данные заказа из неструктурированного текста.
        Этот метод специально оптимизирован для использования с Telegram-ботом.
        
        Args:
            text (str): Неструктурированный текст заказа от пользователя.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа.
        """
        logger.info(f"Обработка заказа из Telegram: {text[:50]}...")
        
        prompt = """Извлеки все данные о заказе на печать из следующего текста. 
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
            # Обработка текста с помощью LLM
            response = self.llm.process_text(text, prompt)
            
            # Извлечение JSON из ответа
            json_data = self._extract_json(response)
            
            if not json_data:
                logger.warning("Не удалось извлечь JSON из ответа LLM")
                return {"error": "Не удалось извлечь данные заказа из текста"}
            
            try:
                # Преобразование строки JSON в словарь
                order_data = json.loads(json_data)
                
                # Проверка и обработка полученных данных
                processed_data = self._validate_and_process_order_data(order_data)
                
                # Добавляем статус "Новый" для всех заказов из Telegram
                processed_data['status'] = 'Новый'
                processed_data['source'] = 'telegram'
                
                # Генерация уникального ID заказа, если он не указан
                if 'id' not in processed_data:
                    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    processed_data['id'] = f"TG{timestamp}"
                
                return processed_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка при разборе JSON: {str(e)}")
                return {"error": f"Ошибка при разборе данных заказа: {str(e)}"}
                
        except Exception as e:
            logger.error(f"Ошибка при обработке заказа: {str(e)}")
            return {"error": f"Ошибка при обработке заказа: {str(e)}"}
    
    def parse_order_description(self, description: str) -> Dict[str, Any]:
        """
        Парсинг неструктурированного описания заказа.
        
        Args:
            description (str): Текстовое описание заказа.
            
        Returns:
            Dict[str, Any]: Структурированные данные заказа.
        """
        # Формирование промпта для LLM
        prompt = """
        Проанализируй следующее описание заказа печати и извлеки из него структурированную информацию. 
        Верни результат ТОЛЬКО в формате JSON со следующими полями:
        
        - order_id: Номер заказа (строка, только цифры)
        - customer: Имя заказчика (строка)
        - quantity: Количество (с единицей измерения, например "500 листов")
        - deadline: Срок выполнения (в формате DD.MM.YYYY, если формат отличается - преобразуй)
        - priority: Приоритет (строка, например "срочно", "обычный", "низкий")
        - description: Дополнительная информация о заказе (строка)
        
        Если какая-то информация отсутствует в описании, верни для этого поля пустую строку или null.
        Формат ответа должен быть строго JSON без дополнительного текста.
        """
        
        logger.info(f"Парсинг описания заказа: {description[:50]}...")
        
        try:
            # Обработка описания через LLM
            result = self.llm.process_text(description, prompt)
            
            # Извлечение JSON из ответа
            json_str = self._extract_json(result)
            order_data = json.loads(json_str)
            
            # Проверка и дополнительная обработка данных
            order_data = self._validate_and_process_order_data(order_data)
            
            logger.info(f"Заказ #{order_data.get('order_id')} успешно обработан")
            return order_data
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге описания заказа: {str(e)}")
            # Возвращаем минимальную структуру с информацией об ошибке
            return {
                "order_id": "",
                "customer": "",
                "quantity": "",
                "deadline": "",
                "priority": "",
                "description": f"Ошибка обработки: {str(e)}",
                "parsing_error": True
            }
    
    def _extract_json(self, text: str) -> str:
        """
        Извлечение JSON из текста.
        
        Args:
            text (str): Текст, предположительно содержащий JSON.
            
        Returns:
            str: Строка JSON.
        """
        # Поиск JSON в тексте
        if '{' in text and '}' in text:
            start = text.find('{')
            end = text.rfind('}') + 1
            return text[start:end]
            
        # Если JSON не найден, возвращаем ошибку
        logger.error(f"JSON не найден в ответе LLM: {text}")
        raise ValueError("JSON не найден в ответе LLM")
    
    def _validate_and_process_order_data(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверка и обработка данных заказа.
        
        Args:
            order_data (Dict[str, Any]): Данные заказа.
            
        Returns:
            Dict[str, Any]: Проверенные и обработанные данные заказа.
        """
        # Проверка и обработка идентификатора заказа
        if not order_data.get("order_id"):
            logger.warning("Идентификатор заказа отсутствует, генерируем временный ID")
            order_data["order_id"] = f"TEMP_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Проверка и обработка даты дедлайна
        if order_data.get("deadline"):
            try:
                # Нормализация формата даты (если это не DD.MM.YYYY)
                deadline = order_data["deadline"]
                if deadline and not self._is_valid_date_format(deadline):
                    # Попытка конвертировать дату в корректный формат
                    logger.info(f"Преобразование формата даты: {deadline}")
                    deadline = self._normalize_date_format(deadline)
                    order_data["deadline"] = deadline
            except Exception as e:
                logger.warning(f"Ошибка при обработке даты дедлайна: {str(e)}")
                order_data["deadline_error"] = True
        
        # Проверка и установка приоритета
        if not order_data.get("priority"):
            logger.info("Приоритет не указан, устанавливаем 'обычный'")
            order_data["priority"] = "обычный"
        
        # Добавление метаданных
        order_data["processed_at"] = datetime.datetime.now().isoformat()
        
        return order_data
    
    def _is_valid_date_format(self, date_str: str) -> bool:
        """
        Проверка формата даты (DD.MM.YYYY).
        
        Args:
            date_str (str): Строка с датой.
            
        Returns:
            bool: True, если формат даты корректен.
        """
        try:
            datetime.datetime.strptime(date_str, "%d.%m.%Y")
            return True
        except ValueError:
            return False
    
    def _normalize_date_format(self, date_str: str) -> str:
        """
        Нормализация формата даты к DD.MM.YYYY.
        
        Args:
            date_str (str): Строка с датой в произвольном формате.
            
        Returns:
            str: Дата в формате DD.MM.YYYY.
        """
        # Очистка от лишних символов и пробелов
        date_str = date_str.strip()
        
        # Попытка разбора распространенных форматов
        formats = [
            "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y",
            "%Y-%m-%d", "%y-%m-%d", "%m/%d/%Y", "%m/%d/%y",
            "%d %b %Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S"
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.datetime.strptime(date_str, fmt)
                return date_obj.strftime("%d.%m.%Y")
            except ValueError:
                continue
        
        # Если ни один формат не подошел, пытаемся извлечь дату с помощью LLM
        prompt = f"""
        Извлеки дату из текста "{date_str}" и преобразуй ее в формат DD.MM.YYYY. 
        Верни только дату в указанном формате, без дополнительного текста.
        """
        
        try:
            result = self.llm.process_text(date_str, prompt)
            # Удаление лишних символов
            result = result.strip()
            
            # Проверка формата полученной даты
            if self._is_valid_date_format(result):
                return result
            else:
                logger.warning(f"LLM не смог преобразовать дату: {date_str} -> {result}")
                return date_str
        except Exception as e:
            logger.error(f"Ошибка при нормализации даты с помощью LLM: {str(e)}")
            return date_str
    
    def batch_process_orders(self, descriptions: List[str]) -> List[Dict[str, Any]]:
        """
        Пакетная обработка нескольких описаний заказов.
        
        Args:
            descriptions (List[str]): Список текстовых описаний заказов.
            
        Returns:
            List[Dict[str, Any]]: Список структурированных данных заказов.
        """
        results = []
        
        for description in descriptions:
            try:
                order_data = self.parse_order_description(description)
                results.append(order_data)
            except Exception as e:
                logger.error(f"Ошибка при обработке заказа: {str(e)}")
                results.append({
                    "description": description,
                    "parsing_error": True,
                    "error_message": str(e)
                })
        
        return results


if __name__ == "__main__":
    # Пример использования
    processor = OrderProcessor()
    
    # Примеры описаний заказов
    test_descriptions = [
        "Заказ #123, Иванов, 500 листов, срочно к 15.10",
        "Заказ 456 от ООО 'Ромашка', тираж 1000 экз, крайний срок 30/11/2023, цветная печать",
        "№ 789, Петров П.П., буклеты А4, 200 шт., до конца месяца"
    ]
    
    # Обработка примеров
    for description in test_descriptions:
        order_data = processor.parse_order_description(description)
        print(f"Обработано: {json.dumps(order_data, ensure_ascii=False, indent=2)}")
    
    # Пакетная обработка
    results = processor.batch_process_orders(test_descriptions)
    print(f"Всего обработано: {len(results)} заказов")
