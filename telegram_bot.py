#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Telegram-бот для взаимодействия с агентом очереди печати.
Позволяет отправлять уведомления и управлять заказами через Telegram.
"""

import logging
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора с ботом
WAIT_ORDER_TEXT, WAIT_CONFIRM = range(2)

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
    """Основной класс Telegram-бота для управления очередью печати"""
    
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
        
        # Создаем Application и передаем ему токен бота
        self.application = Application.builder().token(token).build()
        
        # Регистрируем обработчики команд
        self._register_handlers()
        
        # Список администраторов, имеющих доступ к боту
        self.admin_ids = []
        
    def _register_handlers(self):
        """Регистрирует обработчики команд бота"""
        # Базовые команды
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        
        # Команды управления заказами
        self.application.add_handler(CommandHandler("queue", self.cmd_queue))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        
        # Обработчик разговора для создания нового заказа
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("new_order", self.cmd_new_order)],
            states={
                WAIT_ORDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_order_text)],
                WAIT_CONFIRM: [
                    MessageHandler(filters.Regex('^(Да|да)$'), self.confirm_order),
                    MessageHandler(filters.Regex('^(Нет|нет)$'), self.cancel_order),
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_order)]
        )
        self.application.add_handler(conv_handler)
        
        # Обработчик неизвестных команд
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        
        # Обработчик любых других сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))
        
    def start(self):
        """Запускает бота"""
        # Запускаем бота
        self.application.run_polling()
        logger.info("Бот запущен")
        
    def is_admin(self, user_id):
        """Проверяет, является ли пользователь администратором"""
        # Удалена проверка прав - все пользователи имеют полный доступ
        return True
        
    # Обработчики команд
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /start"""
        user = update.effective_user
        await update.message.reply_text(
            f'Привет, {user.first_name}! Я бот для управления очередью печати. '
            'Используйте /help для получения списка доступных команд.'
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /help"""
        help_text = """
        <b>Доступные команды:</b>
        
        /queue - Показать текущую очередь печати
        /status ID - Проверить статус заказа по ID
        /new_order - Создать новый заказ
        /help - Показать это сообщение
        
        Для создания нового заказа введите /new_order и следуйте инструкциям.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    
    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает команду /queue - показывает текущую очередь печати"""
            
        if not self.queue_manager:
            await update.message.reply_text("Менеджер очереди не инициализирован.")
            return
            
        try:
            # Получаем текущую очередь
            queue = self.queue_manager.get_current_queue()
            
            if not queue:
                await update.message.reply_text("Очередь пуста.")
                return
                
            # Формируем сообщение с информацией о заказах
            message = "<b>Текущая очередь печати:</b>\n\n"
            
            for i, order in enumerate(queue, 1):
                message += f"{i}. <b>Заказ #{order.get('id', 'N/A')}</b>\n"
                message += f"   Клиент: {order.get('customer', 'Не указан')}\n"
                message += f"   Статус: {order.get('status', 'Не указан')}\n"
                if 'deadline' in order:
                    message += f"   Срок: {order['deadline']}\n"
                message += "\n"
                
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)
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
        await update.message.reply_text(
            "Пожалуйста, отправьте описание заказа в свободной форме. "
            "Включите информацию о клиенте, контактных данных, типе печати, "
            "сроках и любых особых требованиях."
        )
        return WAIT_ORDER_TEXT
    
    async def process_order_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текст заказа от пользователя"""
        order_text = update.message.text
        context.user_data['order_text'] = order_text
        
        await update.message.reply_text("Обрабатываю информацию о заказе...")
        
        try:
            if self.data_processor:
                # Используем LLM (Claude) для извлечения структурированных данных
                order_data = self.data_processor.extract_order_from_text(order_text)
                context.user_data['order_data'] = order_data
                
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
                    
                message += "\n<b>Всё верно? (Да/Нет)</b>"
                
                await update.message.reply_text(message, parse_mode=ParseMode.HTML)
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
        """Подтверждает создание заказа"""
        order_data = context.user_data.get('order_data')
        
        if not order_data:
            await update.message.reply_text("Информация о заказе отсутствует. Пожалуйста, начните заново с /new_order")
            return ConversationHandler.END
            
        try:
            if self.queue_manager:
                # Добавляем заказ в очередь
                order_id = self.queue_manager.add_order(order_data)
                
                await update.message.reply_text(
                    f"Заказ успешно создан с ID: {order_id}\n"
                    f"Вы можете проверить его статус командой /status {order_id}"
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
    
    async def cancel_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменяет создание заказа"""
        await update.message.reply_text(
            "Создание заказа отменено. Вы можете начать заново с команды /new_order"
        )
        # Очищаем данные пользователя
        context.user_data.clear()
        return ConversationHandler.END
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает неизвестные команды"""
        await update.message.reply_text(
            "Неизвестная команда. Используйте /help для получения списка доступных команд."
        )
    
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отвечает на обычные сообщения"""
        await update.message.reply_text(
            "Я понимаю только команды. Используйте /help для получения списка доступных команд."
        )


def main():
    """Основная функция для запуска бота"""
    # Получаем токен из переменной окружения или конфигурационного файла
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден. Укажите токен в переменных окружения.")
        return
        
    # Здесь должно быть создание и инициализация других компонентов системы
    # data_processor = DataProcessor()
    # queue_manager = QueueManager()
    
    # Создаем и запускаем бота
    bot = TelegramBot(token)  # , data_processor=data_processor, queue_manager=queue_manager
    bot.start()


if __name__ == "__main__":
    main()
