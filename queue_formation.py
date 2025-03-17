"""
Модуль для формирования очереди печати на основе структурированных данных заказов.
Выполняет анализ приоритетов, сроков и других параметров для оптимальной очередности.
"""

import os
import logging
import json
import yaml
import pandas as pd
import datetime
from typing import Dict, List, Any, Optional, Union

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/queue_formation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("queue_formation")

class QueueManager:
    """Класс для управления очередью печати."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация менеджера очереди.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        
        # Получение настроек очереди
        self.queue_config = self.config.get('queue', {})
        self.deadline_weight = self.queue_config.get('priority_factors', {}).get('deadline_weight', 0.7)
        self.customer_priority_weight = self.queue_config.get('priority_factors', {}).get('customer_priority_weight', 0.3)
        self.emergency_threshold_days = self.queue_config.get('emergency_threshold_days', 3)
        
        logger.info("Инициализация менеджера очереди печати")
    
    def _calculate_days_to_deadline(self, deadline_str: str) -> int:
        """
        Расчет количества дней до дедлайна.
        
        Args:
            deadline_str (str): Строка с датой дедлайна (DD.MM.YYYY).
            
        Returns:
            int: Количество дней до дедлайна (или 999 в случае ошибки).
        """
        try:
            if not deadline_str:
                return 999  # Максимальное значение для заказов без дедлайна
            
            deadline = datetime.datetime.strptime(deadline_str, "%d.%m.%Y").date()
            today = datetime.datetime.now().date()
            
            days_difference = (deadline - today).days
            return max(days_difference, 0)  # Не меньше 0 дней
        except ValueError:
            logger.warning(f"Неверный формат даты дедлайна: {deadline_str}")
            return 999
        except Exception as e:
            logger.error(f"Ошибка при расчете дней до дедлайна: {str(e)}")
            return 999
    
    def _calculate_priority_score(self, order: Dict[str, Any]) -> float:
        """
        Расчет приоритета заказа по различным факторам.
        
        Args:
            order (Dict[str, Any]): Данные заказа.
            
        Returns:
            float: Оценка приоритета (меньше = выше приоритет).
        """
        # Расчет дней до дедлайна
        days_to_deadline = self._calculate_days_to_deadline(order.get('deadline', ''))
        
        # Определение базовой приоритетности по срочности
        if days_to_deadline <= self.emergency_threshold_days:
            base_priority = 1  # Срочный заказ
        else:
            base_priority = 3  # Обычный заказ
        
        # Корректировка по явно указанному приоритету
        priority_text = order.get('priority', '').lower()
        if 'срочно' in priority_text or 'высокий' in priority_text:
            priority_modifier = 0.5
        elif 'низкий' in priority_text:
            priority_modifier = 2.0
        else:
            priority_modifier = 1.0
        
        # Расчет итогового приоритета
        deadline_factor = days_to_deadline * self.deadline_weight
        priority_factor = base_priority * priority_modifier * self.customer_priority_weight
        
        total_score = deadline_factor + priority_factor
        
        logger.debug(f"Заказ #{order.get('order_id')}: дни до дедлайна={days_to_deadline}, "
                    f"базовый приоритет={base_priority}, модификатор={priority_modifier}, "
                    f"итоговый счет={total_score}")
        
        return total_score
    
    def sort_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Сортировка заказов по приоритету.
        
        Args:
            orders (List[Dict[str, Any]]): Список заказов.
            
        Returns:
            List[Dict[str, Any]]: Отсортированный список заказов.
        """
        # Расчет приоритета для каждого заказа
        for order in orders:
            order['priority_score'] = self._calculate_priority_score(order)
        
        # Сортировка заказов по приоритету (от высокого к низкому)
        sorted_orders = sorted(orders, key=lambda x: x.get('priority_score', 999))
        
        logger.info(f"Отсортировано {len(sorted_orders)} заказов по приоритету")
        return sorted_orders
    
    def merge_with_existing_queue(self, new_orders: List[Dict[str, Any]], 
                                current_queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Слияние новых заказов с существующей очередью.
        
        Args:
            new_orders (List[Dict[str, Any]]): Список новых заказов.
            current_queue (List[Dict[str, Any]]): Текущая очередь.
            
        Returns:
            List[Dict[str, Any]]: Обновленная очередь.
        """
        # Создание множества идентификаторов существующих заказов
        existing_order_ids = {order.get('order_id') for order in current_queue}
        
        # Добавление новых заказов, которых нет в очереди
        for order in new_orders:
            order_id = order.get('order_id')
            
            if order_id and order_id not in existing_order_ids:
                current_queue.append(order)
                existing_order_ids.add(order_id)
                logger.info(f"Добавлен новый заказ #{order_id} в очередь")
            elif order_id in existing_order_ids:
                # Обновление существующего заказа
                for i, existing_order in enumerate(current_queue):
                    if existing_order.get('order_id') == order_id:
                        # Сохраняем позицию в очереди
                        queue_position = existing_order.get('queue_position')
                        # Обновляем данные
                        current_queue[i] = order
                        # Восстанавливаем позицию
                        if queue_position is not None:
                            current_queue[i]['queue_position'] = queue_position
                        logger.info(f"Обновлен существующий заказ #{order_id} в очереди")
                        break
        
        # Пересортировка всей очереди с учетом новых заказов
        updated_queue = self.sort_orders(current_queue)
        
        # Обновление порядковых номеров в очереди
        for i, order in enumerate(updated_queue):
            order['queue_position'] = i + 1
        
        logger.info(f"Обновлена очередь, итого {len(updated_queue)} заказов")
        return updated_queue
    
    def generate_queue_report(self, queue: List[Dict[str, Any]]) -> str:
        """
        Генерация текстового отчета об очереди печати.
        
        Args:
            queue (List[Dict[str, Any]]): Очередь заказов.
            
        Returns:
            str: Текстовый отчет.
        """
        # Форматирование отчета
        report = "=== ТЕКУЩАЯ ОЧЕРЕДЬ ПЕЧАТИ ===\n\n"
        
        report += f"Дата формирования: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        report += f"Всего заказов в очереди: {len(queue)}\n\n"
        
        # Срочные заказы
        urgent_orders = [o for o in queue if self._calculate_days_to_deadline(o.get('deadline', '')) <= self.emergency_threshold_days]
        report += f"СРОЧНЫЕ ЗАКАЗЫ ({len(urgent_orders)}):\n"
        if urgent_orders:
            for order in urgent_orders:
                deadline = order.get('deadline', 'Не указан')
                days = self._calculate_days_to_deadline(deadline)
                days_text = f"(осталось {days} дн.)" if days < 999 else ""
                
                report += (f"#{order.get('queue_position', '-')}. Заказ #{order.get('order_id', '-')}, "
                         f"{order.get('customer', '-')}, {order.get('quantity', '-')}, "
                         f"срок: {deadline} {days_text}\n")
        else:
            report += "Нет срочных заказов\n"
            
        report += "\nПОЛНАЯ ОЧЕРЕДЬ:\n"
        for order in queue:
            deadline = order.get('deadline', 'Не указан')
            days = self._calculate_days_to_deadline(deadline)
            days_text = f"(осталось {days} дн.)" if days < 999 else ""
            
            report += (f"#{order.get('queue_position', '-')}. Заказ #{order.get('order_id', '-')}, "
                     f"{order.get('customer', '-')}, {order.get('quantity', '-')}, "
                     f"срок: {deadline} {days_text}\n")
        
        return report
    
    def queue_to_dataframe(self, queue: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Преобразование очереди в DataFrame для экспорта в Excel.
        
        Args:
            queue (List[Dict[str, Any]]): Очередь заказов.
            
        Returns:
            pd.DataFrame: DataFrame с данными очереди.
        """
        # Создание DataFrame
        df = pd.DataFrame(queue)
        
        # Определение основных колонок для экспорта и их порядка
        columns = [
            'queue_position', 'order_id', 'customer', 'quantity', 
            'deadline', 'priority', 'description', 'processed_at'
        ]
        
        # Фильтрация колонок, которые есть в DataFrame
        existing_columns = [col for col in columns if col in df.columns]
        
        # Добавление остальных колонок, если есть
        for col in df.columns:
            if col not in existing_columns and col != 'priority_score':
                existing_columns.append(col)
        
        # Возврат DataFrame с нужными колонками
        result_df = df[existing_columns].copy()
        
        # Переименование колонок для Excel
        column_mapping = {
            'queue_position': 'Позиция',
            'order_id': 'Номер заказа',
            'customer': 'Заказчик',
            'quantity': 'Количество',
            'deadline': 'Срок сдачи',
            'priority': 'Приоритет',
            'description': 'Описание',
            'processed_at': 'Дата обработки'
        }
        
        # Применение переименования только для существующих колонок
        rename_dict = {k: v for k, v in column_mapping.items() if k in result_df.columns}
        result_df.rename(columns=rename_dict, inplace=True)
        
        return result_df
    
    def dataframe_to_queue(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Преобразование DataFrame обратно в список заказов.
        
        Args:
            df (pd.DataFrame): DataFrame с данными очереди.
            
        Returns:
            List[Dict[str, Any]]: Список заказов.
        """
        # Обратное переименование колонок из Excel
        column_mapping = {
            'Позиция': 'queue_position',
            'Номер заказа': 'order_id',
            'Заказчик': 'customer',
            'Количество': 'quantity',
            'Срок сдачи': 'deadline',
            'Приоритет': 'priority',
            'Описание': 'description',
            'Дата обработки': 'processed_at'
        }
        
        # Применение обратного переименования для существующих колонок
        rename_dict = {v: k for k, v in column_mapping.items() if v in df.columns}
        df_renamed = df.rename(columns=rename_dict)
        
        # Преобразование в список словарей
        queue = df_renamed.to_dict(orient='records')
        
        # Добавление пустых приоритетных оценок для возможной сортировки
        for order in queue:
            if 'priority_score' not in order:
                order['priority_score'] = None
        
        return queue
    
    def identify_problematic_orders(self, queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Выявление проблемных заказов в очереди.
        
        Args:
            queue (List[Dict[str, Any]]): Очередь заказов.
            
        Returns:
            List[Dict[str, Any]]: Список проблемных заказов с описанием проблем.
        """
        problematic_orders = []
        
        for order in queue:
            problems = []
            
            # Проверка наличия критических полей
            if not order.get('order_id'):
                problems.append("Отсутствует номер заказа")
            
            if not order.get('customer'):
                problems.append("Отсутствует информация о заказчике")
            
            if not order.get('quantity'):
                problems.append("Отсутствует информация о количестве")
            
            # Проверка дедлайна
            deadline = order.get('deadline', '')
            if deadline:
                try:
                    deadline_date = datetime.datetime.strptime(deadline, "%d.%m.%Y").date()
                    days_to_deadline = (deadline_date - datetime.datetime.now().date()).days
                    
                    # Просроченные заказы
                    if days_to_deadline < 0:
                        problems.append(f"Заказ просрочен на {abs(days_to_deadline)} дней")
                    # Срочные заказы
                    elif days_to_deadline <= self.emergency_threshold_days:
                        problems.append(f"Срочный заказ (осталось {days_to_deadline} дней)")
                except ValueError:
                    problems.append(f"Некорректный формат даты дедлайна: {deadline}")
            else:
                problems.append("Отсутствует срок сдачи")
            
            # Если есть проблемы, добавляем в список
            if problems:
                problem_info = order.copy()
                problem_info['problems'] = problems
                problematic_orders.append(problem_info)
        
        logger.info(f"Выявлено {len(problematic_orders)} проблемных заказов в очереди")
        return problematic_orders
    
    def add_order(self, order_data: Dict[str, Any]) -> str:
        """
        Добавляет новый заказ в очередь печати.
        
        Args:
            order_data (Dict[str, Any]): Данные заказа.
            
        Returns:
            str: Идентификатор созданного заказа.
        """
        # Генерация уникального идентификатора заказа, если не задан
        if 'order_id' not in order_data or not order_data['order_id']:
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            order_data['order_id'] = f"ORD-{timestamp}"
        
        # Добавление времени создания, если не задано
        if 'created_at' not in order_data:
            order_data['created_at'] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Установка статуса, если не задан
        if 'status' not in order_data:
            order_data['status'] = "Новый"
        
        # Пробуем получить текущую очередь
        try:
            current_queue = self.get_current_queue()
        except Exception as e:
            logger.error(f"Ошибка при получении текущей очереди: {str(e)}")
            current_queue = []
        
        # Добавление заказа в очередь
        current_queue.append(order_data)
        
        # Пересортировка очереди
        sorted_queue = self.sort_orders(current_queue)
        
        # Обновление порядковых номеров
        for i, order in enumerate(sorted_queue):
            order['queue_position'] = i + 1
        
        # Сохранение обновленной очереди (если требуется)
        try:
            self.save_queue(sorted_queue)
        except Exception as e:
            logger.error(f"Ошибка при сохранении очереди: {str(e)}")
        
        logger.info(f"Добавлен новый заказ #{order_data['order_id']} в очередь")
        return order_data['order_id']
    
    def get_current_queue(self) -> List[Dict[str, Any]]:
        """
        Получение текущей очереди печати.
        
        Returns:
            List[Dict[str, Any]]: Список заказов в очереди.
        """
        # Здесь должна быть логика загрузки очереди из файла или базы данных
        # Пока вернем пустой список для простоты
        return []
    
    def save_queue(self, queue: List[Dict[str, Any]]) -> bool:
        """
        Сохранение очереди печати.
        
        Args:
            queue (List[Dict[str, Any]]): Очередь заказов для сохранения.
            
        Returns:
            bool: True в случае успеха, False в случае ошибки.
        """
        # Здесь должна быть логика сохранения очереди в файл или базу данных
        # Пока просто логируем действие
        logger.info(f"Сохранение очереди с {len(queue)} заказами")
        return True
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение заказа по его идентификатору.
        
        Args:
            order_id (str): Идентификатор заказа.
            
        Returns:
            Optional[Dict[str, Any]]: Данные заказа или None, если заказ не найден.
        """
        current_queue = self.get_current_queue()
        
        for order in current_queue:
            if order.get('order_id') == order_id:
                return order
        
        return None


if __name__ == "__main__":
    # Пример использования
    manager = QueueManager()
    
    # Пример очереди заказов
    example_orders = [
        {
            "order_id": "123",
            "customer": "Иванов",
            "quantity": "500 листов",
            "deadline": "15.10.2023",
            "priority": "срочно",
            "description": "Буклеты"
        },
        {
            "order_id": "456",
            "customer": "ООО Ромашка",
            "quantity": "1000 экз",
            "deadline": "30.11.2023",
            "priority": "обычный",
            "description": "Цветная печать"
        },
        {
            "order_id": "789",
            "customer": "Петров П.П.",
            "quantity": "200 шт",
            "deadline": "31.12.2023",
            "priority": "низкий",
            "description": "Буклеты А4"
        }
    ]
    
    # Сортировка по приоритету
    sorted_orders = manager.sort_orders(example_orders)
    
    # Вывод отчета
    report = manager.generate_queue_report(sorted_orders)
    print(report)
    
    # Проблемные заказы
    problematic = manager.identify_problematic_orders(sorted_orders)
    for order in problematic:
        print(f"Заказ #{order.get('order_id')} имеет проблемы: {', '.join(order.get('problems', []))}")
