import asyncio
import logging
import shelve
import sys
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForumTopic
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ========== НАСТРОЙКИ ==========
API_TOKEN_FILE = 'api'  # Файл с токеном бота
ADMIN_GROUP_ID = None  # ID группы для админов (заполнится автоматически)
DATABASE_FILE = 'bot_database.db'

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ========== БАЗА ДАННЫХ ==========
class Database:
    """Простая база данных для хранения связей пользователь-тема"""

    def __init__(self, filename=DATABASE_FILE):
        self.filename = filename

    def get_user_topic(self, user_id: int) -> Optional[int]:
        """Получить ID темы для пользователя"""
        with shelve.open(self.filename) as db:
            return db.get(f'user_{user_id}')

    def set_user_topic(self, user_id: int, topic_id: int):
        """Сохранить связь пользователь-тема"""
        with shelve.open(self.filename) as db:
            db[f'user_{user_id}'] = topic_id
            db[f'topic_{topic_id}'] = user_id

    def get_user_by_topic(self, topic_id: int) -> Optional[int]:
        """Получить пользователя по ID темы"""
        with shelve.open(self.filename) as db:
            return db.get(f'topic_{topic_id}')

    def delete_user(self, user_id: int):
        """Удалить пользователя из базы"""
        with shelve.open(self.filename) as db:
            topic_id = db.get(f'user_{user_id}')
            if topic_id:
                if f'user_{user_id}' in db:
                    del db[f'user_{user_id}']
                if f'topic_{topic_id}' in db:
                    del db[f'topic_{topic_id}']

    def save_group_id(self, group_id: int):
        """Сохранить ID группы админов"""
        with shelve.open(self.filename) as db:
            db['admin_group_id'] = group_id

    def get_group_id(self) -> Optional[int]:
        """Получить ID группы админов"""
        with shelve.open(self.filename) as db:
            return db.get('admin_group_id')


# ========== КОМАНДЫ ДЛЯ АДМИНОВ ==========
async def admin_set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для установки админской группы"""
    user_id = update.effective_user.id

    # Проверяем, что команда вызвана в группе
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эту команду нужно использовать в группе!")
        return

    # Проверяем, что пользователь - администратор
    try:
        admins = await update.effective_chat.get_administrators()
        is_admin = any(admin.user.id == user_id for admin in admins)

        if not is_admin:
            await update.message.reply_text("❌ Только администраторы могут использовать эту команду!")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав администратора")
        return

    # Сохраняем ID группы
    chat_id = update.effective_chat.id
    db = Database()
    db.save_group_id(chat_id)

    # Обновляем глобальную переменную
    global ADMIN_GROUP_ID
    ADMIN_GROUP_ID = chat_id

    await update.message.reply_text(
        f"✅ Группа установлена как админская!\n"
        f"ID: {chat_id}\n"
        f"Название: {update.effective_chat.title}\n\n"
        f"Теперь бот будет создавать темы в этой группе для каждого нового пользователя."
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь для админов"""
    help_text = """
🛠 Команды для администраторов:

/setgroup - Установить текущую группу как админскую (выполнить в группе)
/stats - Статистика по обращениям
/closeall - Закрыть все старые темы
/adminhelp - Эта справка

📌 Как работает бот:
1. Пользователь пишет боту в личку
2. Бот создает тему в этой группе
3. Вы отвечаете в теме (reply на сообщение бота)
4. Бот пересылает ответ пользователю
    """
    await update.message.reply_text(help_text)


# ========== КОМАНДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    welcome_text = f"""
👋 Привет, {user.first_name}!

Я бот-посредник. Все сообщения, которые ты мне отправишь, будут анонимно переданы команде поддержки.

📌 Правила:
1. Пиши свои вопросы/сообщения — я передам их
2. Ответы от поддержки будут приходить сюда
3. Не спамь — это может привести к блокировке

Просто напиши свое сообщение, и я его передам!
    """

    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
🤖 Помощь по боту:

Я передаю ваши сообщения команде поддержки анонимно. Просто напишите мне что-нибудь, и я передам это.

📝 Доступные команды:
/start - Начать общение
/help - Эта справка
/status - Статус вашего обращения
/cancel - Отменить текущее обращение

⏰ Время ответа: обычно в течение 24 часов
    """
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус обращения пользователя"""
    user_id = update.effective_user.id
    db = Database()
    topic_id = db.get_user_topic(user_id)

    if topic_id:
        status_text = "✅ У вас есть активное обращение. Команда поддержки уже видит ваши сообщения."
    else:
        status_text = "❌ У вас нет активных обращений. Напишите любое сообщение, чтобы создать обращение."

    await update.message.reply_text(status_text)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена обращения пользователя"""
    user_id = update.effective_user.id
    db = Database()
    topic_id = db.get_user_topic(user_id)

    if topic_id and ADMIN_GROUP_ID:
        # Закрываем тему в группе
        try:
            await context.bot.close_forum_topic(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=topic_id
            )
            await update.message.reply_text("✅ Ваше обращение закрыто. Если будут вопросы - пишите снова!")
        except Exception as e:
            logger.error(f"Error closing topic: {e}")
            await update.message.reply_text("✅ Обращение отменено (тема в группе останется открытой).")

        # Удаляем из базы
        db.delete_user(user_id)
    else:
        await update.message.reply_text("❌ У вас нет активных обращений.")


# ========== ОСНОВНАЯ ЛОГИКА ==========
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений от пользователей в личке"""
    global ADMIN_GROUP_ID

    # Загружаем ID группы из базы, если еще не загружено
    if ADMIN_GROUP_ID is None:
        db = Database()
        ADMIN_GROUP_ID = db.get_group_id()

    user = update.effective_user
    user_id = user.id
    message_text = update.message.text or update.message.caption or "[Медиа-файл]"

    db = Database()

    # Проверяем, есть ли уже тема для этого пользователя
    topic_id = db.get_user_topic(user_id)

    if not topic_id:
        # Создаем новую тему в группе
        if not ADMIN_GROUP_ID:
            await update.message.reply_text(
                "⏳ Админская группа еще не настроена. "
                "Администраторы должны добавить бота в группу и выполнить команду /setgroup"
            )
            return

        # Создаем тему с информацией о пользователе
        user_info = f"👤 Аноним (ID: {user_id})"
        if user.username:
            user_info = f"👤 @{user.username}"

        try:
            topic = await context.bot.create_forum_topic(
                chat_id=ADMIN_GROUP_ID,
                name=user_info[:128]  # Ограничение Telegram на длину названия темы
            )
            topic_id = topic.message_thread_id

            # Сохраняем связь в базе
            db.set_user_topic(user_id, topic_id)

            # Отправляем приветственное сообщение в тему
            welcome_to_admins = f"""
📨 Новое обращение!

ID пользователя: {user_id}
Имя: {user.first_name}
Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """

            if user.username:
                welcome_to_admins += f"\nUsername: @{user.username}"

            if message_text and message_text != "[Медиа-файл]":
                welcome_to_admins += f"\n\nПервое сообщение:\n{message_text}"

            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=topic_id,
                text=welcome_to_admins
            )

            # Если это медиа-файл, пересылаем его отдельно
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    photo=update.message.photo[-1].file_id,
                    caption=message_text if message_text != "[Медиа-файл]" else None
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    document=update.message.document.file_id,
                    caption=message_text if message_text != "[Медиа-файл]" else None
                )
            elif message_text and message_text != "[Медиа-файл]":
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    text=f"👤 Пользователь:\n{message_text}"
                )

            # Подтверждаем пользователю
            await update.message.reply_text("✅ Ваше сообщение отправлено команде поддержки. Ожидайте ответа здесь.")

        except Exception as e:
            logger.error(f"Error creating topic: {e}")
            await update.message.reply_text("❌ Ошибка при создании обращения. Попробуйте позже.")
            return
    else:
        # Пересылаем сообщение в существующую тему
        try:
            # Если есть текст
            if update.message.text:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    text=f"👤 Пользователь:\n{message_text}"
                )
            # Если есть фото
            elif update.message.photo:
                await context.bot.send_photo(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    photo=update.message.photo[-1].file_id,
                    caption=f"👤 Пользователь: {message_text}" if message_text != "[Медиа-файл]" else None
                )
                await update.message.reply_text("✅ Фото отправлено команде поддержки.")
            # Если есть документ
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    document=update.message.document.file_id,
                    caption=f"👤 Пользователь: {message_text}" if message_text != "[Медиа-файл]" else None
                )
                await update.message.reply_text("✅ Файл отправлен команде поддержки.")

        except Exception as e:
            logger.error(f"Error forwarding message: {e}")
            await update.message.reply_text("❌ Ошибка при отправке сообщения.")


async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответов админов в группе"""
    global ADMIN_GROUP_ID

    # Загружаем ID группы из базы, если еще не загружено
    if ADMIN_GROUP_ID is None:
        db = Database()
        ADMIN_GROUP_ID = db.get_group_id()
        if not ADMIN_GROUP_ID:
            return

    # Проверяем, что это ответ на сообщение бота
    if not update.message.reply_to_message:
        return

    # Проверяем, что это ответ именно на сообщение бота
    if update.message.reply_to_message.from_user.id != context.bot.id:
        return

    # Получаем ID темы из сообщения
    topic_id = update.message.message_thread_id

    # Находим пользователя по теме
    db = Database()
    user_id = db.get_user_by_topic(topic_id)

    if not user_id:
        await update.message.reply_text(
            "❌ Не могу найти пользователя для этой темы.",
            reply_to_message_id=update.message.message_id
        )
        return

    # Пересылаем ответ пользователю
    try:
        reply_text = f"📨 Ответ от поддержки:\n\n{update.message.text}"

        # Добавляем кнопку "Ответить" для пользователя
        keyboard = [[InlineKeyboardButton("📝 Ответить", callback_data="reply_to_admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=reply_text,
            reply_markup=reply_markup
        )

        # Подтверждаем админу
        await update.message.reply_text(
            "✅ Ответ отправлен пользователю.",
            reply_to_message_id=update.message.message_id
        )

    except Exception as e:
        logger.error(f"Error sending reply to user: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}",
            reply_to_message_id=update.message.message_id
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    if query.data == "reply_to_admin":
        await query.edit_message_text(
            "📝 Напишите ваш ответ. Он будет передан команде поддержки."
        )


# ========== ЗАПУСК БОТА ==========
def main():
    """Основная функция запуска бота"""

    # Читаем токен из файла
    try:
        with open(API_TOKEN_FILE, 'r') as f:
            TOKEN = f.read().strip()
    except FileNotFoundError:
        print(f"❌ Файл '{API_TOKEN_FILE}' не найден!")
        print(f"Создайте файл '{API_TOKEN_FILE}' и поместите туда токен бота.")
        return

    if not TOKEN:
        print("❌ Токен не найден в файле!")
        return

    print("✅ Токен загружен")

    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд для пользователей
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    # Обработчики команд для админов
    application.add_handler(CommandHandler("setgroup", admin_set_group))
    application.add_handler(CommandHandler("adminhelp", admin_help))

    # Обработчики сообщений - ТЕКСТ
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_private_message
    ))

    # Обработчик медиа-файлов
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.Document.ALL) & filters.ChatType.PRIVATE,
        handle_private_message
    ))

    # Обработчик ответов в группе
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS & filters.REPLY,
        handle_group_reply
    ))

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Бот запускается...")
    print("=" * 50)
    print("📋 ИНСТРУКЦИЯ ПО НАСТРОЙКЕ:")
    print("1. Добавьте бота в группу (где будут работать вы и ваши друзья)")
    print("2. Назначьте бота администратором группы")
    print("3. Превратите группу в Супергруппу")
    print("4. Включите 'Темы' в настройках группы")
    print("5. В группе выполните команду /setgroup")
    print("6. Теперь пользователи могут писать боту в личку")
    print("=" * 50)

    # Загружаем сохраненный ID группы
    db = Database()
    group_id = db.get_group_id()
    if group_id:
        global ADMIN_GROUP_ID
        ADMIN_GROUP_ID = group_id
        print(f"✅ Загружен ID админской группы: {group_id}")

    # Запускаем бота
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")


if __name__ == '__main__':
    main()