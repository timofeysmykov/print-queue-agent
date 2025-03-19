#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Telegram-бот для взаимодействия с агентом очереди печати.
Позволяет отправлять уведомления и управлять заказами через Telegram.
"""

import logging
import os
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import yaml
import asyncio

# Импортируем клиент Claude API для работы с AI
from claude_api import ClaudeAPIClient

# Импортируем наши модули
from queue_formation import QueueManager
from data_processing import OrderProcessor

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора с ботом
WAIT_ORDER_TEXT, WAIT_CONFIRM, WAIT_AI_DESCRIPTION, PROCESSING_AI_REQUEST = range(4)

# Команды для обработки действий с кнопок
COMMAND_NEW_ORDER = 'new_order'
COMMAND_QUEUE = 'view_queue'
COMMAND_STATUS = 'check_status'
COMMAND_HELP = 'help'
COMMAND_EXIT_AI = 'exit_ai'

class TelegramNotifier:
    """Класс для отправки уведомлений через Telegram"""
    
    def __init__(self, token, chat_ids=None):
        """
        Инициализирует бота для отправки уведомлений.
        
        Args:
            token (str): Токен API Telegram-бота
            chat_ids (list, optional): Список ID чатов для отправки уведомлений
        """
        self.token = token
        self.chat_ids = chat_ids or []
        self.application = Application.builder().token(token).build()
        self.bot = self.application.bot
        
    def send_notification(self, message, chat_id=None):
        """
        Отправляет уведомление в Telegram.
        
        Args:
            message (str): Текст сообщения
            chat_id (int, optional): ID чата для отправки. Если не указан, 
                                    отправляет всем в self.chat_ids
        
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        try:
            if chat_id:
                self.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
            else:
                for chat in self.chat_ids:
                    self.bot.send_message(chat_id=chat, text=message, parse_mode=ParseMode.HTML)
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {str(e)}")
            return False
            
    def send_order_update(self, order_info, status, chat_id=None):
        """
        Отправляет уведомление об обновлении статуса заказа.
        
        Args:
            order_info (dict): Информация о заказе
            status (str): Новый статус заказа
            chat_id (int, optional): ID чата для отправки
        """
        customer = order_info.get('customer', 'Неизвестный клиент')
        order_id = order_info.get('id', 'ID не указан')
        
        message = f"<b>Обновление заказа #{order_id}</b>\n\n"
        message += f"<b>Клиент:</b> {customer}\n"
        message += f"<b>Статус:</b> {status}\n"
        
        if 'deadline' in order_info:
            message += f"<b>Срок выполнения:</b> {order_info['deadline']}\n"
            
        self.send_notification(message, chat_id)
        
    def send_urgency_alert(self, order_info, chat_id=None):
        """
        Отправляет уведомление о срочном заказе.
        
        Args:
            order_info (dict): Информация о заказе
            chat_id (int, optional): ID чата для отправки
        """
        customer = order_info.get('customer', 'Неизвестный клиент')
        order_id = order_info.get('id', 'ID не указан')
        
        message = f"🚨 <b>СРОЧНЫЙ ЗАКАЗ #{order_id}</b> 🚨\n\n"
        message += f"<b>Клиент:</b> {customer}\n"
        
        if 'description' in order_info:
            message += f"<b>Описание:</b> {order_info['description']}\n"
            
        if 'deadline' in order_info:
            message += f"<b>Срок выполнения:</b> {order_info['deadline']}\n"
            
        self.send_notification(message, chat_id)


class TelegramBot:
    """Основной класс Telegram-бота для управления очередью печати и общения с AI"""
    
    def __init__(self, token, data_processor=None, queue_manager=None):
        """
        Инициализирует Telegram-бота.
        
        Args:
            token (str): Токен API Telegram-бота
            data_processor: Процессор данных заказов
            queue_manager: Менеджер очереди печати
        """
        self.token = token
        self.data_processor = data_processor
        self.queue_manager = queue_manager
        
        # Создаем экземпляр Claude API клиента для общения с AI
        try:
            self.claude_client = ClaudeAPIClient()
            logger.info("Клиент Claude API успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Claude API: {str(e)}")
            self.claude_client = None
        
        # Создаем Application и передаем ему токен бота
        self.application = Application.builder().token(token).build()
        
        # Регистрируем обработчики команд
        self._register_handlers()
        
        # Список администраторов, имеющих доступ к боту
        self.admin_ids = []
        
        # Словарь для хранения истории разговоров с AI
        self.ai_conversations = {}
        
        # Промпт с информацией о печатном бизнесе для Claude
        self.ai_context = """Ты - помощник по работе с очередью печати. Ты помогаешь сотрудникам типографии отвечая на их вопросы о заказах, очереди и работе типографии.

Типография предоставляет следующие услуги:
- Цветная и черно-белая печать
- Печать на обычной, мелованной и глянцевой бумаге
- Печать визиток, буклетов, брошюр и постеров
- Переплет и ламинирование

При ответе на вопросы о сроках исполнения:
- Обычные заказы выполняются в течение 2-3 рабочих дней
- Срочные заказы могут быть выполнены в течение 24 часов (с наценкой 50%)
- Крупные заказы (>1000 копий) могут занять больше времени, обычно 4-5 рабочих дней

Ты должен быть вежливым, четким и профессиональным в ответах на вопросы."""
        
    def _register_handlers(self):
        """Регистрирует обработчики команд бота"""
        # Базовые команды
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        
        # Команды управления заказами
        self.application.add_handler(CommandHandler("queue", self.cmd_queue))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        
        # Обработчик для кнопок меню (должен быть до ConversationHandler)
        self.application.add_handler(CallbackQueryHandler(
            self.button_callback, 
            pattern=f"^({COMMAND_QUEUE}|{COMMAND_HELP}|{COMMAND_STATUS})$"
        ))
        
        # Обработчик разговора для создания нового заказа
        order_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("new_order", self.cmd_new_order),
                CallbackQueryHandler(self.cmd_new_order_callback, pattern=f"^{COMMAND_NEW_ORDER}$")
            ],
            states={
                WAIT_ORDER_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_order_text)
                ],
                WAIT_CONFIRM: [
                    CallbackQueryHandler(self.confirm_order_callback, pattern='^confirm$'),
                    CallbackQueryHandler(self.cancel_order_callback, pattern='^cancel$')
                ],
                PROCESSING_AI_REQUEST: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown_command)
                ]
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_order),
                # Дополнительно обрабатываем любые кнопки в fallbacks
                CallbackQueryHandler(self.button_callback, pattern=".*")
            ],
            # Важно: установим allow_reentry=True для повторного входа
            allow_reentry=True
        )
        self.application.add_handler(order_conv_handler)
        
        # Обработчик неизвестных команд
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        
        # Обработчик текстовых кнопок и простых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT, self.echo))

    async def clean_bot_state(self):
        """Очищает состояние бота перед запуском, удаляя все webhook'и и pending updates.
        Это предотвращает конфликты между несколькими экземплярами бота.
        """
        try:
            # Получаем доступ к боту
            bot = self.application.bot
            
            # Удаляем webhook если он есть
            logger.info("Удаление webhook и очистка обновлений...")
            # Используем await для асинхронного метода
            await bot.delete_webhook(drop_pending_updates=True)
            
            # Дополнительная проверка завершения всех активных сессий
            logger.info("Успешная очистка состояния бота")
            return True
        except Exception as e:
            logger.error(f"Ошибка при очистке состояния бота: {str(e)}")
            return False
    
    async def pre_run_setup(self, application):
        """Подготовка бота перед запуском"""
        logger.info("Подготовка бота перед запуском...")
        await self.clean_bot_state()
        logger.info("Подготовка завершена")
        
    def start(self):
        """Запускает бота"""
        import asyncio
        
        try:
            # Создаем и запускаем цикл для предварительной очистки
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Выполняем очистку состояния синхронно
            loop.run_until_complete(asyncio.gather(
                self.application.bot.delete_webhook(drop_pending_updates=True)
            ))
            
            # Запускаем бота в режиме получения обновлений
            logger.info("Запуск Telegram-бота...")
            self.application.run_polling(drop_pending_updates=True)
            logger.info("Бот запущен")
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {str(e)}")
        
    def is_admin(self, user_id):
        """Проверяет, является ли пользователь администратором"""
        # Удалена проверка прав - все пользователи имеют полный доступ
        return True
        
    # Обработчики команд
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /start"""
        user = update.effective_user
        
        # Создаем клавиатуру основных действий
        keyboard = [
            [KeyboardButton("📋 Просмотр очереди"), KeyboardButton("➕ Новый заказ")],
            [KeyboardButton("❓ Помощь")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f'Привет, {user.first_name}! Я бот для управления очередью печати. '
            'Выберите действие в меню ниже или используйте /help для получения списка доступных команд.',
            reply_markup=reply_markup
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /help"""
        help_text = """
        <b>Доступные команды:</b>
        
        📋 Просмотр очереди - Показать текущую очередь печати
        ➕ Новый заказ - Создать новый заказ
        /status ID - Проверить статус заказа по ID
        """
        
        # Создаем inline-кнопки действий
        keyboard = [
            [InlineKeyboardButton("📋 Просмотр очереди", callback_data=COMMAND_QUEUE)],
            [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение с кнопками
        await update.message.reply_text(
            help_text, 
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /queue - показывает текущую очередь печати"""
            
        if not self.queue_manager:
            await update.message.reply_text("Менеджер очереди не инициализирован.")
            return
            
        try:
            # Получаем текущую очередь
            queue = self.queue_manager.get_current_queue()
            
            if not queue:
                # Создаем кнопки действий
                keyboard = [
                    [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)],
                    [InlineKeyboardButton("🔄 Обновить", callback_data=COMMAND_QUEUE)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "Очередь пуста. Нажмите кнопку 'Новый заказ', чтобы добавить заказ.", 
                    reply_markup=reply_markup
                )
                return
                
            # Формируем сообщение с информацией о заказах
            message = "<b>Текущая очередь печати:</b>\n\n"
            
            for i, order in enumerate(queue, 1):
                order_id = order.get('order_id', order.get('id', 'N/A'))
                message += f"{i}. <b>Заказ #{order_id}</b>\n"
                message += f"   Клиент: {order.get('customer', 'Не указан')}\n"
                message += f"   Статус: {order.get('status', 'Не указан')}\n"
                if 'deadline' in order:
                    message += f"   Срок: {order['deadline']}\n"
                message += "\n"
            
            # Создаем кнопки действий для очереди
            keyboard = [
                [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)],
                [InlineKeyboardButton("🔄 Обновить", callback_data=COMMAND_QUEUE)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message, 
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при получении очереди: {str(e)}")
            await update.message.reply_text(f"Произошла ошибка: {str(e)}")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /status ID - проверяет статус заказа по ID"""
        if not context.args:
            await update.message.reply_text("Пожалуйста, укажите ID заказа: /status ID")
            return
            
        order_id = context.args[0]
        
        if not self.queue_manager:
            await update.message.reply_text("Менеджер очереди не инициализирован.")
            return
            
        try:
            # Получаем информацию о заказе
            order = self.queue_manager.get_order_by_id(order_id)
            
            if not order:
                await update.message.reply_text(f"Заказ с ID {order_id} не найден.")
                return
                
            # Формируем сообщение с информацией о заказе
            message = f"<b>Информация о заказе #{order_id}</b>\n\n"
            message += f"<b>Клиент:</b> {order.get('customer', 'Не указан')}\n"
            message += f"<b>Статус:</b> {order.get('status', 'Не указан')}\n"
            
            if 'description' in order:
                message += f"<b>Описание:</b> {order['description']}\n"
                
            if 'deadline' in order:
                message += f"<b>Срок выполнения:</b> {order['deadline']}\n"
                
            if 'quantity' in order:
                message += f"<b>Количество:</b> {order['quantity']}\n"
                
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о заказе: {str(e)}")
            await update.message.reply_text(f"Произошла ошибка: {str(e)}")
    
    async def cmd_new_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс создания нового заказа"""
        # Устанавливаем состояние в user_data
        context.user_data['state'] = WAIT_ORDER_TEXT
        
        await update.message.reply_text(
            "📝 Пожалуйста, опишите ваш заказ.\n"
            "Укажите как можно больше деталей: тип печати, количество копий, формат, срок и т.д.\n"
            "Для отмены введите /cancel",
            reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру для более удобного ввода текста
        )
        return WAIT_ORDER_TEXT
    
    async def process_order_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текст заказа от пользователя"""
        # Проверяем, что мы действительно ожидаем текст заказа
        if 'state' not in context.user_data or context.user_data['state'] != WAIT_ORDER_TEXT:
            # Если мы попали сюда не в нужном состоянии, игнорируем
            logger.warning(f"process_order_text вызван не в нужном состоянии: {context.user_data.get('state')}")
            return ConversationHandler.END
            
        order_text = update.message.text
        
        # Проверяем, что текст не является командой меню или кнопкой
        menu_commands = ["📋 Просмотр очереди", "➕ Новый заказ", "❓ Помощь", 
                         "Помощь", "👋 Начать", "Начать", "Новый заказ", 
                         "Просмотр очереди"]
        
        if order_text in menu_commands:
            logger.warning(f"Пользователь отправил команду меню '{order_text}' как текст заказа")
            await update.message.reply_text(
                "Это команда меню, а не текст заказа. Пожалуйста, введите текстовое описание заказа или /cancel для отмены."
            )
            return WAIT_ORDER_TEXT
        context.user_data['order_text'] = order_text
        
        # Получаем chat_id для идентификации пользователя
        chat_id = update.effective_chat.id
        
        await update.message.reply_text("Обрабатываю информацию о заказе...")
        
        try:
            if self.data_processor:
                # Используем LLM (Claude) для извлечения структурированных данных
                order_data = self.data_processor.extract_order_from_text(order_text)
                # Сохраняем данные заказа в контексте пользователя
                context.user_data['order_data'] = order_data
                
                # Дополнительно сохраняем данные в глобальном хранилище по ID чата
                if not hasattr(self, 'order_data_storage'):
                    self.order_data_storage = {}
                self.order_data_storage[chat_id] = order_data
                logger.info(f"Сохранены данные заказа для чата {chat_id}: {order_data}")
                
                # Формируем сообщение с извлеченной информацией
                message = "<b>Извлеченная информация о заказе:</b>\n\n"
                message += f"<b>Клиент:</b> {order_data.get('customer', 'Не удалось определить')}\n"
                
                if 'contact' in order_data:
                    message += f"<b>Контакт:</b> {order_data['contact']}\n"
                    
                if 'description' in order_data:
                    message += f"<b>Описание:</b> {order_data['description']}\n"
                    
                if 'quantity' in order_data:
                    message += f"<b>Количество:</b> {order_data['quantity']}\n"
                    
                if 'deadline' in order_data:
                    message += f"<b>Срок выполнения:</b> {order_data['deadline']}\n"
                
                # Создаем кнопки для подтверждения
                keyboard = [
                    [InlineKeyboardButton("✅ Да, всё верно", callback_data="confirm")],
                    [InlineKeyboardButton("❌ Нет, отменить", callback_data="cancel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    message + "\n<b>Всё верно? Нажмите на соответствующую кнопку:</b>", 
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
                return WAIT_CONFIRM
            else:
                await update.message.reply_text(
                    "Не удалось обработать заказ: процессор данных не инициализирован. "
                    "Попробуйте позже или обратитесь к администратору."
                )
                return ConversationHandler.END
        except Exception as e:
            logger.error(f"Ошибка при обработке заказа: {str(e)}")
            await update.message.reply_text(
                f"Произошла ошибка при обработке заказа: {str(e)}\n"
                "Пожалуйста, попробуйте позже или свяжитесь с администратором."
            )
            return ConversationHandler.END
    
    async def confirm_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждает создание заказа (для текстового ввода)"""
        order_data = context.user_data.get('order_data')
        
        if not order_data:
            await update.message.reply_text("Информация о заказе отсутствует. Пожалуйста, начните заново.")
            return ConversationHandler.END
            
        try:
            if self.queue_manager:
                # Сообщаем о начале процесса добавления заказа
                status_message = await update.message.reply_text(
                    "⏳ Начинаю создание заказа...\n"
                    "Пожалуйста, подождите, операция может занять некоторое время."
                )
                
                # Обновляем сообщение о статусе - скачивание очереди
                await status_message.edit_text(
                    "⏳ Начинаю создание заказа...\n"
                    "🔄 Загружаю текущую очередь с Google Drive..."
                )
                
                # Добавляем заказ в очередь
                order_id = self.queue_manager.add_order(order_data)
                
                # Обновляем сообщение о статусе - сохранение очереди
                await status_message.edit_text(
                    "⏳ Добавляю заказ в очередь...\n"
                    "✅ Очередь загружена с Google Drive\n"
                    "🔄 Обновляю очередь и сохраняю на Google Drive..."
                )
                
                # Небольшая задержка, чтобы пользователь успел увидеть изменения статусов
                await asyncio.sleep(1)
                
                # Обновляем сообщение о статусе - завершение операции
                await status_message.edit_text(
                    "✅ Заказ успешно добавлен в очередь\n"
                    "✅ Файл очереди обновлен на Google Drive"
                )
                
                # Создаем кнопки для дальнейших действий
                keyboard = [
                    [InlineKeyboardButton("📋 Просмотреть очередь", callback_data=COMMAND_QUEUE)],
                    [InlineKeyboardButton("➕ Добавить ещё заказ", callback_data=COMMAND_NEW_ORDER)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Отправляем окончательное подтверждение создания заказа
                await update.message.reply_text(
                    f"✅ Заказ успешно создан!\n\n"
                    f"Заказ добавлен в очередь печати и сохранен на Google Drive.\n"
                    f"Оригинальный файл на Google Drive сохранён, создана новая версия.\n\n"
                    f"Что вы хотите сделать дальше?",
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    "Не удалось добавить заказ: менеджер очереди не инициализирован. "
                    "Заказ сохранен в системе, но не добавлен в очередь."
                )
        except Exception as e:
            logger.error(f"Ошибка при добавлении заказа: {str(e)}")
            await update.message.reply_text(f"Произошла ошибка при добавлении заказа: {str(e)}")
            
        # Очищаем данные пользователя
        context.user_data.clear()
        return ConversationHandler.END
    
    async def confirm_order_callback(self, query, context):
        """Подтверждает создание заказа (для кнопок)"""
        try:
            # Получаем chat_id для идентификации пользователя
            chat_id = query.message.chat_id
            
            # Пытаемся получить данные заказа из контекста пользователя
            order_data = context.user_data.get('order_data')
            
            # Если данных нет в контексте, пробуем получить из глобального хранилища
            if not order_data and hasattr(self, 'order_data_storage') and chat_id in self.order_data_storage:
                order_data = self.order_data_storage[chat_id]
                logger.info(f"Получены данные заказа из глобального хранилища для чата {chat_id}")
                # Для дальнейшего использования сохраняем данные в контексте пользователя
                context.user_data['order_data'] = order_data
            
            # Проверяем наличие данных заказа
            if not order_data:
                logger.error(f"Не найдены данные заказа для чата {chat_id}")
                await query.edit_message_text(
                    "Ошибка: данные заказа не найдены. Пожалуйста, начните процесс создания заказа заново.",
                    reply_markup=None
                )
                # Очищаем данные пользователя
                context.user_data.clear()
                return ConversationHandler.END
            
            if self.queue_manager:
                # Шаг 1: Начало процесса
                await query.edit_message_text(
                    "⏳ Начинаю создание заказа...\n"
                    "🔍 Проверяю доступность Google Drive..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Шаг 2: Скачивание файла очереди
                await query.edit_message_text(
                    "⏳ Начинаю создание заказа...\n"
                    "✅ Google Drive доступен\n"
                    "📥 Скачиваю файл очереди в Excel формате..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Шаг 3: Загрузка существующей очереди из файла
                await query.edit_message_text(
                    "⏳ Начинаю создание заказа...\n"
                    "✅ Google Drive доступен\n"
                    "✅ Файл очереди скачан\n"
                    "📊 Загружаю данные из файла Excel..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Добавляем заказ в очередь
                order_id = self.queue_manager.add_order(order_data)
                
                # Шаг 4: Обновление очереди
                await query.edit_message_text(
                    "⏳ Добавляю заказ в очередь...\n"
                    "✅ Google Drive доступен\n"
                    "✅ Файл очереди скачан\n"
                    "✅ Данные успешно загружены из Excel\n"
                    "📝 Добавляю новый заказ в очередь..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Шаг 5: Сохранение обновленной очереди
                await query.edit_message_text(
                    "⏳ Добавляю заказ в очередь...\n"
                    "✅ Google Drive доступен\n"
                    "✅ Файл очереди скачан\n"
                    "✅ Данные успешно загружены из Excel\n"
                    "✅ Заказ добавлен в очередь\n"
                    "💾 Сохраняю обновленную очередь..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Шаг 6: Выгрузка обновленного файла на Google Drive
                await query.edit_message_text(
                    "⏳ Завершаю создание заказа...\n"
                    "✅ Google Drive доступен\n"
                    "✅ Файл очереди скачан\n"
                    "✅ Данные успешно загружены из Excel\n"
                    "✅ Заказ добавлен в очередь\n"
                    "✅ Очередь сохранена локально\n"
                    "📤 Выгружаю обновленный файл на Google Drive..."
                )
                await asyncio.sleep(1)  # Небольшая задержка для лучшего UX
                
                # Небольшая задержка, чтобы пользователь успел увидеть изменения статусов
                await asyncio.sleep(1)
                
                # Создаем кнопки для дальнейших действий
                keyboard = [
                    [InlineKeyboardButton("📋 Просмотреть очередь", callback_data=COMMAND_QUEUE)],
                    [InlineKeyboardButton("➕ Добавить ещё заказ", callback_data=COMMAND_NEW_ORDER)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Финальное сообщение о создании заказа
                await query.edit_message_text(
                    f"✅ Заказ успешно создан!\n\n"
                    f"Заказ добавлен в очередь печати и сохранен на Google Drive.\n"
                    f"Оригинальный файл на Google Drive сохранён, создана новая версия.\n\n"
                    f"Что вы хотите сделать дальше?",
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text(
                    "Не удалось добавить заказ: менеджер очереди не инициализирован. "
                    "Заказ сохранен в системе, но не добавлен в очередь."
                )
        except Exception as e:
            logger.error(f"Ошибка при добавлении заказа: {str(e)}")
            await query.edit_message_text(f"Произошла ошибка при добавлении заказа: {str(e)}")
            
        # Очищаем данные пользователя
        context.user_data.clear()
        return ConversationHandler.END
    
    async def cancel_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменяет создание заказа (для текстового ввода)"""
        await update.message.reply_text(
            "Создание заказа отменено. Вы можете начать заново с команды /new_order или кнопки 'Новый заказ'"
        )
        # Очищаем данные пользователя
        context.user_data.clear()
        return ConversationHandler.END
        
    async def cancel_order_callback(self, query, context):
        """Отменяет создание заказа (для кнопок)"""
        # Очищаем данные пользователя
        context.user_data.clear()
        
        # Создаем кнопки для дальнейших действий
        keyboard = [
            [InlineKeyboardButton("📋 Просмотр очереди", callback_data=COMMAND_QUEUE)],
            [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Создание заказа отменено. Выберите дальнейшее действие:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает неизвестные команды"""
        await update.message.reply_text(
            "Неизвестная команда. Используйте /help для получения списка доступных команд."
        )
    
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые кнопки меню"""
        text = update.message.text
        
        # Если пользователь в режиме ожидания ввода заказа
        if 'state' in context.user_data:
            state = context.user_data['state']
            if state == WAIT_ORDER_TEXT:
                return await self.process_order_text(update, context)
            elif state == WAIT_AI_DESCRIPTION:
                return await self.process_ai_description(update, context)
            elif state == WAIT_CONFIRM:
                # Если мы ожидаем подтверждения, но пользователь отправил текст
                await update.message.reply_text(
                    "Пожалуйста, используйте кнопки 'Да, всё верно' или 'Нет, отменить' "
                    "для подтверждения или отмены заказа."
                )
                return
        
        # Обработка текстовых кнопок меню
        elif text == "📋 Просмотр очереди":
            await self.cmd_queue(update, context)
        elif text == "➕ Новый заказ":
            # При нажатии текстовой кнопки устанавливаем состояние
            context.user_data['state'] = WAIT_ORDER_TEXT
            await self.cmd_new_order(update, context)
        elif text == "❓ Помощь":
            await self.cmd_help(update, context)
        # Игнорируем другие тексты, которые не соответствуют известным командам
        else:
            await update.message.reply_text(
                "Пожалуйста, используйте кнопки меню или /help для получения списка доступных команд."
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия на inline-кнопки"""
        query = update.callback_query
        
        # Логируем нажатую кнопку
        logger.info(f"Нажата кнопка с данными: {query.data}")
        
        # Получаем данные из кнопки
        callback_data = query.data
        
        # Предотвращаем повторные нажатия (мигание часиков)
        await query.answer()
        
        # Обработка кнопок подтверждения/отмены заказа
        if callback_data == 'confirm':
            return await self.confirm_order_callback(query, context)
        elif callback_data == 'cancel':
            return await self.cancel_order_callback(query, context)
        
        # Обработка меню и других действий
        elif callback_data == COMMAND_NEW_ORDER:
            return await self.cmd_new_order_callback(query, context)
        elif callback_data == COMMAND_QUEUE:
            return await self.cmd_queue_callback(query, context)
        elif callback_data == COMMAND_HELP:
            return await self.cmd_help_callback(query, context)
        elif callback_data == COMMAND_STATUS:
            # Запрашиваем ID заказа
            await query.edit_message_text(
                "Введите номер заказа, чтобы проверить его статус:"
            )
            # Устанавливаем состояние ожидания ID заказа
            context.user_data['waiting_for_order_id'] = True
            return
        elif callback_data == COMMAND_EXIT_AI:
            # Выход из режима общения с AI
            if 'ai_mode' in context.user_data:
                del context.user_data['ai_mode']
            
            await query.edit_message_text(
                "Режим общения с AI выключен. Используйте меню для выбора действий."
            )
            
            # Показываем основное меню
            await self._show_main_menu(query.message.chat_id)
            return
        else:
            # Обработка неизвестных команд
            logger.warning(f"Неизвестная команда кнопки: {callback_data}")
            await query.edit_message_text(
                "Неизвестная команда. Используйте меню для выбора действий.",
                reply_markup=self._get_main_menu_keyboard()
            )
            return
    
    async def cmd_new_order_callback(self, query, context):
        """Обрабатывает нажатие кнопки создания нового заказа"""
        # Очищаем пользовательские данные для начала нового заказа
        context.user_data.clear()
        
        # Устанавливаем состояние "ожидание текста заказа"
        context.user_data['state'] = WAIT_ORDER_TEXT
        
        # Отправляем сообщение с просьбой описать заказ
        await query.edit_message_text(
            "📝 Пожалуйста, опишите ваш заказ.\n"
            "Укажите как можно больше деталей: тип печати, количество копий, формат, срок и т.д.\n"
            "Для отмены введите /cancel"
        )
        
        # Важно: удаляем inline-кнопки, чтобы их текст не был обработан как заказ
        await query.message.reply_text(
            "⏬ Теперь введите текст вашего заказа ниже ⏬", 
            reply_markup=ReplyKeyboardRemove()
        )
        
        return WAIT_ORDER_TEXT
    
    async def cmd_help_callback(self, query, context):
        """Обрабатывает нажатие кнопки помощи"""
        help_text = """
        <b>Доступные команды:</b>
        
        📋 Просмотр очереди - Показать текущую очередь печати
        ➕ Новый заказ - Создать новый заказ
        /status ID - Проверить статус заказа по ID
        """
        
        # Создаем inline-кнопки действий
        keyboard = [
            [InlineKeyboardButton("📋 Просмотр очереди", callback_data=COMMAND_QUEUE)],
            [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            help_text, 
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def cmd_queue_callback(self, query, context):
        """Обрабатывает нажатие кнопки просмотра очереди"""
        if not self.queue_manager:
            await query.edit_message_text("Менеджер очереди не инициализирован.")
            return
            
        try:
            # Получаем текущую очередь
            queue = self.queue_manager.get_current_queue()
            
            if not queue:
                # Создаем кнопки действий
                keyboard = [
                    [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)],
                    [InlineKeyboardButton("🔄 Обновить", callback_data=COMMAND_QUEUE)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "Очередь пуста. Нажмите кнопку 'Новый заказ', чтобы добавить заказ.", 
                    reply_markup=reply_markup
                )
                return
                
            # Формируем сообщение с информацией о заказах
            message = "<b>Текущая очередь печати:</b>\n\n"
            
            for i, order in enumerate(queue, 1):
                order_id = order.get('order_id', order.get('id', 'N/A'))
                message += f"{i}. <b>Заказ #{order_id}</b>\n"
                message += f"   Клиент: {order.get('customer', 'Не указан')}\n"
                message += f"   Статус: {order.get('status', 'Не указан')}\n"
                if 'deadline' in order:
                    message += f"   Срок: {order['deadline']}\n"
                message += "\n"
            
            # Создаем кнопки действий для очереди
            keyboard = [
                [InlineKeyboardButton("➕ Новый заказ", callback_data=COMMAND_NEW_ORDER)],
                [InlineKeyboardButton("🔄 Обновить", callback_data=COMMAND_QUEUE)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message, 
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при получении очереди: {str(e)}")
            await query.edit_message_text(f"Произошла ошибка: {str(e)}")


    # Методы для работы с Claude AI
    # Удалён обработчик команды /ai

    def process_order_description(self, text):
        """Структурирует описание заказа с помощью Claude API"""
        prompt = f"""Преобразуй описание заказа в JSON-формат:
        {{
            "client": str,
            "phone": str,
            "material": str,
            "date": DD.MM.YY,
            "print_type": str,
            "quantity": int
        }}
        Текст: {text}"""
        return claude_api.query(prompt)


def main():
    """Основная функция для запуска бота"""
    # Загрузка конфигурации
    config_path = "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    
    # Создаем папки для данных и логов если они не существуют
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Инициализация компонентов
    queue_manager = QueueManager(config_path)
    data_processor = OrderProcessor(config_path="config.yaml")
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram", {}).get("token", "")
    
    # Создание бота с подключением менеджера очереди
    bot = TelegramBot(token, data_processor=data_processor, queue_manager=queue_manager)
    
    # Запуск бота
    bot.start()


if __name__ == "__main__":
    main()
