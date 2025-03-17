"""
Модуль для работы с Excel-файлами очереди печати и заказов.
Обеспечивает чтение, запись и обновление данных в Excel-файлах.
"""

import os
import logging
import pandas as pd
import yaml
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/excel_editing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("excel_editing")

class ExcelHandler:
    """Класс для работы с Excel-файлами."""
    
    def __init__(self, config_path="config.yaml"):
        """
        Инициализация обработчика Excel-файлов.
        
        Args:
            config_path (str): Путь к файлу конфигурации.
        """
        # Загрузка конфигурации
        with open(config_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        
        # Получение путей к файлам
        self.files_config = self.config.get('files', {})
        self.local_data_folder = Path(self.files_config.get('local_data_folder', 'data/'))
        
        # Создание локальной папки, если она не существует
        self.local_data_folder.mkdir(exist_ok=True, parents=True)
        
        logger.info("Инициализация обработчика Excel-файлов")
    
    def read_excel(self, file_path: Union[str, Path], sheet_name: str = None) -> pd.DataFrame:
        """
        Чтение данных из Excel-файла.
        
        Args:
            file_path (Union[str, Path]): Путь к файлу.
            sheet_name (str, optional): Имя листа для чтения.
            
        Returns:
            pd.DataFrame: DataFrame с данными из файла.
        """
        try:
            logger.info(f"Чтение Excel-файла: {file_path}")
            
            # Чтение файла
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            else:
                df = pd.read_excel(file_path)
            
            logger.info(f"Успешно прочитано {len(df)} строк из {file_path}")
            return df
        except Exception as e:
            logger.error(f"Ошибка при чтении Excel-файла {file_path}: {str(e)}")
            # Возвращаем пустой DataFrame в случае ошибки
            return pd.DataFrame()
    
    def write_excel(self, df: pd.DataFrame, file_path: Union[str, Path], 
                    sheet_name: str = "Очередь печати", index: bool = False) -> str:
        """
        Запись данных в Excel-файл.
        
        Args:
            df (pd.DataFrame): DataFrame с данными для записи.
            file_path (Union[str, Path]): Путь к файлу.
            sheet_name (str, optional): Имя листа для записи.
            index (bool, optional): Включать ли индекс в файл.
            
        Returns:
            str: Путь к созданному файлу.
        """
        try:
            logger.info(f"Запись {len(df)} строк в Excel-файл: {file_path}")
            
            # Обеспечение наличия директории
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Запись в файл
            df.to_excel(file_path, sheet_name=sheet_name, index=index)
            
            logger.info(f"Данные успешно записаны в файл {file_path}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Ошибка при записи в Excel-файл {file_path}: {str(e)}")
            raise
    
    def update_excel(self, file_path: Union[str, Path], new_data: pd.DataFrame, 
                    sheet_name: str = "Очередь печати", key_column: str = "Номер заказа") -> str:
        """
        Обновление существующего Excel-файла новыми данными.
        
        Args:
            file_path (Union[str, Path]): Путь к файлу.
            new_data (pd.DataFrame): DataFrame с новыми данными.
            sheet_name (str, optional): Имя листа для обновления.
            key_column (str, optional): Ключевая колонка для сопоставления строк.
            
        Returns:
            str: Путь к обновленному файлу.
        """
        try:
            # Проверка существования файла
            if os.path.exists(file_path):
                logger.info(f"Обновление существующего Excel-файла: {file_path}")
                
                # Чтение существующих данных
                existing_data = self.read_excel(file_path, sheet_name)
                
                # Проверка наличия ключевой колонки
                if key_column in existing_data.columns and key_column in new_data.columns:
                    # Обновление по ключевой колонке
                    merged_data = self._merge_dataframes(existing_data, new_data, key_column)
                else:
                    logger.warning(f"Ключевая колонка {key_column} не найдена, заменяем файл полностью")
                    merged_data = new_data
            else:
                logger.info(f"Файл {file_path} не существует, создаем новый")
                merged_data = new_data
            
            # Запись объединенных данных
            return self.write_excel(merged_data, file_path, sheet_name)
        except Exception as e:
            logger.error(f"Ошибка при обновлении Excel-файла {file_path}: {str(e)}")
            raise
    
    def _merge_dataframes(self, existing_df: pd.DataFrame, new_df: pd.DataFrame, key_column: str) -> pd.DataFrame:
        """
        Объединение двух DataFrame по ключевой колонке.
        
        Args:
            existing_df (pd.DataFrame): Существующий DataFrame.
            new_df (pd.DataFrame): Новый DataFrame.
            key_column (str): Ключевая колонка для объединения.
            
        Returns:
            pd.DataFrame: Объединенный DataFrame.
        """
        # Создание копий для предотвращения ошибок
        existing = existing_df.copy()
        new = new_df.copy()
        
        # Получение списка существующих ключей
        existing_keys = set(existing[key_column].astype(str))
        new_keys = set(new[key_column].astype(str))
        
        # Ключи для обновления и добавления
        keys_to_update = existing_keys.intersection(new_keys)
        keys_to_add = new_keys - existing_keys
        
        # Обновление существующих строк
        for key in keys_to_update:
            # Индексы строк для обновления
            existing_idx = existing[existing[key_column].astype(str) == key].index
            new_idx = new[new[key_column].astype(str) == key].index
            
            if len(existing_idx) > 0 and len(new_idx) > 0:
                # Обновление каждой колонки по отдельности
                for col in new.columns:
                    if col in existing.columns:
                        existing.loc[existing_idx[0], col] = new.loc[new_idx[0], col]
        
        # Добавление новых строк
        rows_to_add = new[new[key_column].astype(str).isin(keys_to_add)]
        if not rows_to_add.empty:
            existing = pd.concat([existing, rows_to_add], ignore_index=True)
        
        logger.info(f"Объединено: {len(keys_to_update)} обновлено, {len(keys_to_add)} добавлено")
        return existing
    
    def extract_order_descriptions(self, file_path: Union[str, Path], 
                                 text_column: str = "Описание") -> List[str]:
        """
        Извлечение текстовых описаний заказов из Excel-файла.
        
        Args:
            file_path (Union[str, Path]): Путь к файлу с заказами.
            text_column (str, optional): Имя колонки с описаниями.
            
        Returns:
            List[str]: Список описаний заказов.
        """
        try:
            logger.info(f"Извлечение описаний заказов из файла: {file_path}")
            
            # Чтение файла
            df = self.read_excel(file_path)
            
            # Проверка наличия колонки с текстом
            if text_column in df.columns:
                # Извлечение непустых описаний
                descriptions = df[text_column].dropna().astype(str).tolist()
                logger.info(f"Извлечено {len(descriptions)} описаний заказов")
                return descriptions
            else:
                # Если колонка не найдена, пытаемся найти похожую
                text_columns = [col for col in df.columns if 'опис' in col.lower() or 'заказ' in col.lower()]
                
                if text_columns:
                    logger.info(f"Использую альтернативную колонку: {text_columns[0]}")
                    descriptions = df[text_columns[0]].dropna().astype(str).tolist()
                    logger.info(f"Извлечено {len(descriptions)} описаний заказов")
                    return descriptions
                
                logger.warning(f"Колонка с описаниями не найдена в файле {file_path}")
                # Попытка вернуть все нечисловые колонки в качестве запасного варианта
                text_data = []
                for col in df.columns:
                    if df[col].dtype == 'object':
                        text_data.extend(df[col].dropna().astype(str).tolist())
                
                logger.info(f"Собрано {len(text_data)} текстовых элементов из всех колонок")
                return text_data
        except Exception as e:
            logger.error(f"Ошибка при извлечении описаний заказов из {file_path}: {str(e)}")
            return []
    
    def create_empty_queue_file(self, file_path: Union[str, Path]) -> str:
        """
        Создание пустого шаблона файла очереди печати.
        
        Args:
            file_path (Union[str, Path]): Путь к создаваемому файлу.
            
        Returns:
            str: Путь к созданному файлу.
        """
        # Создание пустого DataFrame с необходимыми колонками
        columns = [
            "Позиция", "Номер заказа", "Заказчик", "Количество", 
            "Срок сдачи", "Приоритет", "Описание", "Дата обработки"
        ]
        
        df = pd.DataFrame(columns=columns)
        
        logger.info(f"Создание пустого шаблона файла очереди: {file_path}")
        return self.write_excel(df, file_path, sheet_name="Очередь печати")
    
    def create_sample_orders_file(self, file_path: Union[str, Path]) -> str:
        """
        Создание примера файла с описаниями заказов.
        
        Args:
            file_path (Union[str, Path]): Путь к создаваемому файлу.
            
        Returns:
            str: Путь к созданному файлу.
        """
        # Примеры заказов для тестирования
        sample_data = [
            {"Описание": "Заказ #123, Иванов, 500 листов, срочно к 15.10"},
            {"Описание": "Заказ 456 от ООО 'Ромашка', тираж 1000 экз, крайний срок 30/11/2023, цветная печать"},
            {"Описание": "№ 789, Петров П.П., буклеты А4, 200 шт., до конца месяца"},
            {"Описание": "Срочный заказ для OOO 'ТехноПром', 300 каталогов A4, номер 987, нужно до 25.12"}
        ]
        
        df = pd.DataFrame(sample_data)
        
        logger.info(f"Создание примера файла с заказами: {file_path}")
        return self.write_excel(df, file_path, sheet_name="Заказы")
    
    def check_and_prepare_data_folder(self) -> None:
        """
        Проверка и подготовка папки с данными.
        Создает необходимую структуру директорий и пример файлов.
        """
        # Создание директории если не существует
        self.local_data_folder.mkdir(exist_ok=True, parents=True)
        
        # Пути к примерам файлов
        sample_orders_path = self.local_data_folder / "orders_sample.xlsx"
        sample_queue_path = self.local_data_folder / "queue_sample.xlsx"
        
        # Создание примеров файлов, если они не существуют
        if not sample_orders_path.exists():
            self.create_sample_orders_file(sample_orders_path)
        
        if not sample_queue_path.exists():
            self.create_empty_queue_file(sample_queue_path)
        
        logger.info("Папка с данными проверена и подготовлена")


if __name__ == "__main__":
    # Пример использования
    handler = ExcelHandler()
    
    # Подготовка тестовых файлов
    handler.check_and_prepare_data_folder()
    
    # Пути к тестовым файлам
    sample_orders_file = handler.local_data_folder / "orders_sample.xlsx"
    sample_queue_file = handler.local_data_folder / "queue_sample.xlsx"
    
    # Чтение описаний заказов
    descriptions = handler.extract_order_descriptions(sample_orders_file)
    print(f"Извлечено {len(descriptions)} описаний заказов:")
    for desc in descriptions:
        print(f" - {desc}")
    
    # Создание тестовых данных для очереди
    test_queue_data = {
        "Позиция": [1, 2, 3],
        "Номер заказа": ["123", "456", "789"],
        "Заказчик": ["Иванов", "ООО Ромашка", "Петров П.П."],
        "Количество": ["500 листов", "1000 экз", "200 шт"],
        "Срок сдачи": ["15.10.2023", "30.11.2023", "31.12.2023"],
        "Приоритет": ["срочно", "обычный", "низкий"],
        "Описание": ["Буклеты", "Цветная печать", "Буклеты А4"]
    }
    
    # Запись тестовых данных
    test_df = pd.DataFrame(test_queue_data)
    updated_file = handler.update_excel(sample_queue_file, test_df)
    
    print(f"Файл очереди обновлен: {updated_file}")
