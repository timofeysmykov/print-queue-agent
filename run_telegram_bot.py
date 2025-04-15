#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска Telegram-бота агента очереди печати.
"""

import os
import sys
import logging
import signal
from dotenv import load_dotenv

# Установим рабочую директорию
# Проверяем, существует ли директория /opt/print-queue-agent (на сервере)
if os.path.exists('/opt/print-queue-agent'):
    os.chdir('/opt/print-queue-agent')
else:
    # Если директории нет, значит мы на локальной машине
    logger = logging.getLogger('telegram_bot_runner')
    logger.info('Запуск в локальном режиме')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('telegram_bot.log')
    ]
)

logger = logging.getLogger('telegram_bot_runner')

# Загрузка переменных окружения
load_dotenv()

# Проверка наличия токена
telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
if not telegram_token:
    logger.error('TELEGRAM_BOT_TOKEN не найден в переменных окружения')
    sys.exit(1)

# Обработчик сигналов для корректного завершения
def signal_handler(sig, frame):
    logger.info('Получен сигнал завершения, останавливаем бота...')
    if 'bot' in globals():
        try:
            # Здесь будет код для корректной остановки бота
            logger.info('Бот успешно остановлен')
        except Exception as e:
            logger.error(f'Ошибка при остановке бота: {str(e)}')
    sys.exit(0)

# Регистрация обработчиков сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

try:
    logger.info('Запуск Telegram-бота')
    
    # Импорт после настройки логирования
    from telegram_bot import TelegramBot
    from data_processing import OrderProcessor
    from queue_formation import QueueManager
    
    # Создание необходимых объектов
    order_processor = OrderProcessor()
    queue_manager = QueueManager()
    
    # Создание и запуск бота
    bot = TelegramBot(
        telegram_token,
        data_processor=order_processor,
        queue_manager=queue_manager
    )
    
    # Добавление администраторов (если они указаны в переменных окружения)
    admin_ids_str = os.getenv('ADMIN_CHAT_IDS', '')
    if admin_ids_str:
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip().isdigit()]
        bot.admin_ids = admin_ids
        logger.info(f'Добавлены администраторы: {admin_ids}')
    
    # Запуск бота
    logger.info('Запуск Telegram-бота...')
    bot.start()
    
except Exception as e:
    logger.error(f'Ошибка при запуске Telegram-бота: {str(e)}', exc_info=True)
    sys.exit(1)
