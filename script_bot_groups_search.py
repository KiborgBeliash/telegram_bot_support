import asyncio
import os
from telegram import Bot
from telegram.constants import ChatType


async def get_bot_groups():
    """
    Получает список всех групп, в которых состоит бот.
    Возвращает список словарей с информацией о группе.
    """

    # 1. Читаем токен из файла 'api'
    if not os.path.exists('api'):
        print("❌ Файл 'api' не найден!")
        print("Создайте файл 'api' в той же директории и поместите туда токен вашего бота.")
        return []

    with open('api', 'r') as f:
        token = f.read().strip()

    if not token:
        print("❌ Токен не найден в файле 'api'!")
        return []

    print(f"✅ Токен загружен (первые 10 символов): {token[:10]}...")

    # 2. Создаем экземпляр бота
    bot = Bot(token=token)

    # 3. Получаем информацию о боте (для проверки)
    try:
        me = await bot.get_me()
        print(f"🤖 Бот: @{me.username} ({me.first_name})")
    except Exception as e:
        print(f"❌ Ошибка при получении информации о боте: {e}")
        return []

    # 4. Получаем обновления, чтобы найти чаты
    print("📡 Получаю список чатов...")

    groups = []

    try:
        # Получаем последние обновления (можно увеличить лимит при необходимости)
        updates = await bot.get_updates(limit=100, timeout=10)

        print(f"🔍 Найдено {len(updates)} обновлений в истории...")

        # Проходим по всем обновлениям и собираем уникальные чаты
        seen_chats = set()

        for update in updates:
            chat = None

            # Определяем, откуда пришло обновление
            if update.message:
                chat = update.message.chat
            elif update.edited_message:
                chat = update.edited_message.chat
            elif update.channel_post:
                chat = update.channel_post.chat
            elif update.edited_channel_post:
                chat = update.edited_channel_post.chat
            elif update.my_chat_member:
                chat = update.my_chat_member.chat
            elif update.chat_member:
                chat = update.chat_member.chat
            elif update.chat_join_request:
                chat = update.chat_join_request.chat

            if chat and chat.id not in seen_chats:
                seen_chats.add(chat.id)

                # Фильтруем только группы и супергруппы
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    # Получаем более полную информацию о чате
                    try:
                        chat_info = await bot.get_chat(chat.id)

                        group_info = {
                            'id': chat_info.id,
                            'title': chat_info.title,
                            'type': chat_info.type,
                            'username': chat_info.username,
                            'invite_link': chat_info.invite_link,
                            'member_count': getattr(chat_info, 'member_count', 'N/A')
                        }

                        groups.append(group_info)
                        print(f"✅ Добавлена группа: {chat_info.title} (ID: {chat_info.id})")

                    except Exception as e:
                        print(f"⚠️ Не удалось получить информацию о чате {chat.id}: {e}")

    except Exception as e:
        print(f"❌ Ошибка при получении обновлений: {e}")

    # 5. Альтернативный метод: если бот администратор, можно получить список чатов через getChatAdministrators
    # Но для этого нужно знать ID чатов заранее

    return groups


async def main():
    """
    Основная асинхронная функция
    """
    print("=" * 50)
    print("🔍 ПОИСК ГРУПП БОТА")
    print("=" * 50)

    groups = await get_bot_groups()

    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ")
    print("=" * 50)

    if groups:
        print(f"\n✅ Бот состоит в {len(groups)} группе(ах):\n")

        for i, group in enumerate(groups, 1):
            print(f"{i}. {group['title']}")
            print(f"   ID: {group['id']}")
            print(f"   Тип: {group['type']}")
            if group['username']:
                print(f"   Юзернейм: @{group['username']}")
            if group['invite_link']:
                print(f"   Пригласительная ссылка: {group['invite_link']}")
            if group['member_count'] != 'N/A':
                print(f"   Участников: {group['member_count']}")
            print()
    else:
        print("\n❌ Бот не найден ни в одной группе.")
        print("\n💡 Советы:")
        print("1. Убедитесь, что бот добавлен в группу как участник")
        print("2. Отправьте любое сообщение в группе, где есть бот")
        print("3. Попробуйте перезапустить бота командой /start в личке с ботом")
        print("4. Метод работает только с чатами, где бот получал обновления")

    print("\n📝 Примечание:")
    print("Этот метод находит только те группы, где бот получал обновления.")
    print("Для получения полного списка нужно использовать другой подход.")


def run_script():
    """
    Запускает асинхронную функцию
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Скрипт остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")


if __name__ == "__main__":
    run_script()