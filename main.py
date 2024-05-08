from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import logging
import pickle
import re
from telethon import TelegramClient, events
from config import api_id, api_hash, bot_token, my_id
import json
import time
import aiosqlite
from playwright.async_api import async_playwright, Browser, expect
from datetime import datetime, timedelta
browser = None


# Определение состояния для ожидания ввода ID канала
class ChannelAdding(StatesGroup):
    waiting_for_channel_id = State()


# Установка настроек логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

editing_message_id = None

moderation_active = False
message_storage = {}

client = TelegramClient('myGrab', api_id, api_hash, system_version="4.16.30-vxMAX")
bot = Bot(token=bot_token)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logger.info("GRAB - Запущен")
database = None

async def setup_database():
    global database
    database = await aiosqlite.connect("solscan.db")

async def close_database():
    global database
    if database:
        await database.close()

async def clear_database_at_midnight():
    while True:
        now = datetime.now()
        next_run = now.replace(hour=0, minute=0, second=0, microsecond=0)  # следующее выполнение в полночь
        if now.hour >= 12:  # если уже после полудня, планируем на следующий день
            next_run += timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)  # ожидаем до полуночи

        # код очистки данных
        async with database as db:
            await db.execute("DELETE FROM data;")
            await db.commit()
        logger.info("База данных успешно очищена.")


try:
    with open('channels.pickle', 'rb') as f:
        channels = pickle.load(f)
except FileNotFoundError:
    channels = {}

try:
    with open('destination_channels.pickle', 'rb') as f:
        destination_channels = pickle.load(f)
except FileNotFoundError:
    destination_channels = {}

try:
    with open('channel_mapping.pickle', 'rb') as f:
        channel_mapping = pickle.load(f)
except FileNotFoundError:
    channel_mapping = {}


def save_channels():
    with open('channels.pickle', 'wb') as f:
        pickle.dump(channels, f)
    with open('destination_channels.pickle', 'wb') as f:
        pickle.dump(destination_channels, f)
    with open('channel_mapping.pickle', 'wb') as f:
        pickle.dump(channel_mapping, f)


# Отправка уведомления в Telegram чат
async def send_notification(message):
    chat_id = my_id
    await bot.send_message(chat_id, message)


bot_id = int(bot_token.split(':')[0])


async def setup_browser():
    global browser
    if browser is None or not browser.is_connected():
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)

# async def close_browser():
#     global browser
#     if browser:
#         await browser.close()
#         browser = None

async def fetch_data_with_playwright(link):
    global browser
    await setup_browser()

    page = None
    try:
        page = await browser.new_page()
        link_regular = re.compile(r'([\S]*ipfs[\S]*)|([\S]*irys[\S]*)|([\S]*arweave[\S]*)')

        async with page.expect_response(link_regular, timeout=90000) as response_info:
            await page.goto(link, timeout=90000)
            response = await response_info.value
            if response and response.ok:
                response_data = await response.json()
                logger.info(f"Данные запроса{response_data}")
                return response_data  # Возвращаем данные как текст
            else:
                return None
    except Exception as e:
        logger.error(f"Ошибка при работе с Playwright: {e}")
        return None
    finally:
        if page and not page.is_closed():
            await page.close()


async def solscan_data(link):
    data = dict()
    response_data = await fetch_data_with_playwright(link)

    # Предположим, что response_data является JSON-строкой (исправьте согласно вашим нуждам)

    parsed_data = response_data
    parsed_data_str = json.dumps(response_data)
    data['name'] = parsed_data['name']
    data['symbol'] = parsed_data['symbol']

    # Найти ссылки на Telegram
    telegram_link_regular = re.compile(r'(t\.me\/[\w+]*)')
    tg_link_match = telegram_link_regular.findall(parsed_data_str)
    if tg_link_match:
        data['tg_link'] = f"https://{tg_link_match[0]}"
        logger.info(f"Ссылка на TG найдена: {tg_link_match[0]}")
    else:
        data['tg_link'] = None
        logger.info("Ссылка на TG не найдена")
    logger.info(f"Данные для вывода{data}")
    return data


async def get_destination_channel_info(destination_channel_id):
    destination_channel = await client.get_entity(destination_channel_id)
    if destination_channel:
        return destination_channel.title, destination_channel_id
    else:
        return f"Канал с ID {destination_channel_id}", destination_channel_id


@client.on(events.NewMessage(chats=channels))
async def my_event_handler(event):
    if event.message.grouped_id:
        return

    original_text = event.message.text
    # current_time = datetime.now().strftime("%H")
    # if current_time == "23" or current_time == "11":
    #     cursor.execute("DELETE FROM data;")
    #     con.commit()

    token_regular = re.compile(
        r'\[\*\*[\S\s]+?\*\*\]\([\S\s]+?\)\*\*\:\*\*\s\`([\S\s]+?)\`|\*\*Token Address:\*\*\s([\S\s]+?)\s')
    tg_link_regular = re.compile(r'(https?:\/\/t\.me\/[\w-]+)')
    spam_regular = re.compile(r'(Spam)')



    for source_channel_id, destination_channel_id in channel_mapping.items():
        if event.chat_id == source_channel_id:
            try:
                if not spam_regular.findall(original_text):
                    tokens = token_regular.findall(original_text)
                    tg_link = tg_link_regular.findall(original_text)
                    print(tg_link)
                    for token in tokens[0]:
                        if not token:
                            pass
                        else:
                            print(token)
                            async with database.execute("SELECT * FROM token_table WHERE token=?", (token,)) as cursor:
                                existing_record = await cursor.fetchone()
                                # print(existing_record)
                                if existing_record:
                                    logger.info(f"Токен {token} уже существует в базе данных")
                                else:
                                    token = token
                                    source = "TG_Channel"
                                    solcan_token_link = f"https://solscan.io/token/{token}"

                                    # Вставка новой записи в базу данных
                                    async with database.execute(
                                        'INSERT INTO token_table (source, token, solscan_token_link) VALUES (?, ?, ?)',
                                        (source, token, solcan_token_link)) as cursor:
                                        await database.commit()

                                    logger.info(f"Токен {token} добавлен в базу данных")
                        if not token:
                            pass
                        else:
                            if (tg_link[0] == "https://t.me/neo_bonkbot" or tg_link == ""):
                                time.sleep(30)
                                logger.info(f"Начата работа с сообщением с канала: {source_channel_id}")
                                pars_link_to_db = f"https://solscan.io/token/{token}"
                                data_from_solscan = await solscan_data(link=pars_link_to_db)
                                tg_link_solscan = data_from_solscan['tg_link']
                                if not tg_link_solscan:
                                    pass
                                else:
                                    async with database.execute("SELECT * FROM token_table WHERE tg_link=?",
                                                                (tg_link_solscan,)) as cursor:
                                        existing_token_record = await cursor.fetchone()
                                    if existing_token_record:
                                        logger.info(f"Тг ссылка {token} уже существует в базе данных")
                                    else:
                                        source = "Solscan Metadata"
                                        async with database.execute("UPDATE token_table SET tg_link=? WHERE token=?",
                                                                    (tg_link_solscan, token)) as cursor:
                                            await database.commit()
                                        await client.send_message(destination_channel_id,
                                                                  f"{source}\nTG:{tg_link_solscan}")
                            else:
                                async with database.execute("SELECT * FROM token_table WHERE tg_link=?", (tg_link[0],)) as cursor:
                                    existing_token_record = await cursor.fetchone()
                                if existing_token_record:
                                    logger.info(f"Тг ссылка {token} уже существует в базе данных")
                                else:
                                    async with database.execute("UPDATE token_table SET tg_link=? WHERE token=?", (tg_link[0], token)) as cursor:
                                        await database.commit()
                                    source = "TG_Channel"
                                    logger.info(f"Тг ссылка {token} добавлен в базу данных")
                                    await client.send_message(destination_channel_id,
                                                              f"{source}\nTG:{tg_link[0]}")

                else:
                    logger.info(f"Обнаружено сообщение-спам{original_text}")


                logger.info(
                    f"Сообщение переслано: {original_text} из канала {source_channel_id} в канал {destination_channel_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения: {str(e)}")


# Функция для создания клавиатуры с меню
def create_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Помощь", callback_data='help'))
    keyboard.add(InlineKeyboardButton("Добавить канал", callback_data='add_channel'))
    keyboard.add(InlineKeyboardButton("Удалить канал", callback_data='remove_channel'))
    keyboard.add(InlineKeyboardButton("Показать список каналов", callback_data='list_channels'))
    keyboard.add(InlineKeyboardButton("Добавить канал-получатель", callback_data='add_destination_channel'))
    keyboard.add(InlineKeyboardButton("Удалить канал-получатель", callback_data='remove_destination_channel'))
    keyboard.add(InlineKeyboardButton("Показать список каналов-получателей", callback_data='list_destination_channels'))
    keyboard.add(InlineKeyboardButton("Установить соответствие между каналами", callback_data='set_channel_mapping'))
    keyboard.add(InlineKeyboardButton("Показать соответствия", callback_data='show_mapping'))
    keyboard.add(InlineKeyboardButton("Удалить соответствие каналов", callback_data='remove_mapping'))
    keyboard.add(InlineKeyboardButton("Отправить последние сообщения", callback_data='last_messages'))
    keyboard.add(InlineKeyboardButton("Перезагрузить бота", callback_data='restart_bot'))

    # Меняем текст кнопки "Модерация" в зависимости от статуса модерации
    moderation_text = "Модерация: выкл" if moderation_active else "Модерация: вкл"
    keyboard.add(InlineKeyboardButton(moderation_text, callback_data='toggle_moderation'))

    return keyboard


@dp.callback_query_handler(lambda c: c.data == 'show_mapping')
async def process_callback_show_mapping(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    try:
        with open('channel_mapping.pickle', 'rb') as f:
            loaded_mapping = pickle.load(f)

        if loaded_mapping:
            mapping_text = "\n".join(
                f"{channels[source]} ({source}) -> {destination_channels[destination]} ({destination})"
                for source, destination in loaded_mapping.items())
            await bot.send_message(callback_query.from_user.id, "Текущие соответствия каналов:\n" + mapping_text)
        else:
            await bot.send_message(callback_query.from_user.id, "Соответствий каналов пока нет.")
    except FileNotFoundError:
        await bot.send_message(callback_query.from_user.id, "Файл соответствий не найден.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, f"Произошла ошибка при загрузке соответствий: {e}")


# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    start_message = "Привет!"
    keyboard = create_menu_keyboard()
    await message.reply(start_message, reply_markup=keyboard)



@dp.callback_query_handler(lambda c: c.data == 'help')
async def process_callback_help(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await help(callback_query.message)


@dp.callback_query_handler(lambda c: c.data == 'add_channel')
async def process_callback_add_channel(callback_query: types.CallbackQuery):
    await ChannelAdding.waiting_for_channel_id.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           'Введите ID канала или его username, который вы хотите добавить:')
    logger.info("Ожидание ввода ID канала")


@dp.message_handler(state=ChannelAdding.waiting_for_channel_id)
async def add_channel(message: types.Message, state: FSMContext):
    try:
        channel_input = message.text.strip()
        channel_id = None
        chat = None

        # Проверяем, начинается ли введенное значение с "@" (username)
        if channel_input.startswith("@"):
            username = channel_input[1:]  # Убираем символ "@" в начале
            chat = await client.get_entity(username)
        # Проверяем, начинается ли введенное значение с "-" (ID)
        elif channel_input.startswith("-"):
            channel_id = int(channel_input)
            chat = await client.get_entity(channel_id)

        if chat:
            channels[channel_id or chat.id] = chat.title
            await message.reply(f"Канал {chat.title} (ID: {chat.id}) добавлен")
            save_channels()
            logger.info(f"Канал {chat.title} добавлен")
        else:
            await message.reply(
                "Канал не найден. Пожалуйста, укажите корректный ID канала или его username (начинается с '@').")
            logger.error("Ошибка при добавлении канала")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении канала.")
        logger.error(f"Ошибка при добавлении канала: {str(e)}")
    finally:
        await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'remove_channel')
async def process_callback_remove_channel(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel_id, channel_name in channels.items():
        keyboard.insert(InlineKeyboardButton(channel_name, callback_data='remove_channel_' + str(channel_id)))
    await bot.send_message(callback_query.from_user.id, 'Выберите канал, который вы хотите удалить:',
                           reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('remove_channel_'))
async def process_callback_remove_channel_confirm(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    channel_id = int(callback_query.data[len('remove_channel_'):])
    channel_name = channels.pop(channel_id, None)
    if channel_name:
        await bot.send_message(callback_query.from_user.id, f'Канал {channel_name} удален')
        save_channels()
    else:
        await bot.send_message(callback_query.from_user.id, 'Канал не найден')


@dp.callback_query_handler(lambda c: c.data == 'list_channels')
async def process_callback_list_channels(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await list_channels(callback_query.message)


class DestinationChannelAdding(StatesGroup):
    waiting_for_destination_channel_id = State()


@dp.callback_query_handler(lambda c: c.data == 'add_destination_channel')
async def process_callback_add_destination_channel(callback_query: types.CallbackQuery):
    await DestinationChannelAdding.waiting_for_destination_channel_id.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           'Введите ID канала-получателя или его username, который вы хотите добавить:')


@dp.message_handler(state=DestinationChannelAdding.waiting_for_destination_channel_id)
async def add_destination_channel(message: types.Message, state: FSMContext):
    try:
        channel_input = message.text.strip()
        channel_id = None
        chat = None

        # Проверяем, начинается ли введенное значение с "@" (username)
        if channel_input.startswith("@"):
            username = channel_input[1:]  # Убираем символ "@" в начале
            chat = await client.get_entity(username)
        # Проверяем, начинается ли введенное значение с "-" (ID)
        elif channel_input.startswith("-"):
            channel_id = int(channel_input)
            chat = await client.get_entity(channel_id)

        if chat:
            destination_channels[channel_id or chat.id] = chat.title
            await message.reply(f"Канал-получатель {chat.title} (ID: {chat.id}) добавлен")
            save_channels()
            logger.info(f"Канал-получатель {chat.title} добавлен")
        else:
            await message.reply(
                "Канал-получатель не найден. Пожалуйста, укажите корректный ID канала-получателя или его username (начинается с '@').")
            logger.error("Ошибка при добавлении канала-получателя")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении канала-получателя.")
        logger.error(f"Ошибка при добавлении канала-получателя: {str(e)}")
    finally:
        await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'remove_destination_channel')
async def process_callback_remove_destination_channel(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel_id, channel_name in destination_channels.items():
        keyboard.insert(
            InlineKeyboardButton(channel_name, callback_data='remove_destination_channel_' + str(channel_id)))
    await bot.send_message(callback_query.from_user.id, 'Выберите канал-получатель, который вы хотите удалить:',
                           reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('remove_destination_channel_'))
async def process_callback_remove_destination_channel_confirm(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    channel_id = int(callback_query.data[len('remove_destination_channel_'):])
    channel_name = destination_channels.pop(channel_id, None)
    if channel_name:
        await bot.send_message(callback_query.from_user.id, f'Канал-получатель {channel_name} удален')
        save_channels()
    else:
        await bot.send_message(callback_query.from_user.id, 'Канал-получатель не найден')


@dp.callback_query_handler(lambda c: c.data == 'list_destination_channels')
async def process_callback_list_destination_channels(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await list_destination_channels(callback_query.message)


@dp.callback_query_handler(lambda c: c.data == 'set_channel_mapping')
async def process_callback_set_channel_mapping(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           'Пожалуйста, введите ID канала-источника и ID канала-получателя через пробел после команды /set_channel_mapping.')


@dp.callback_query_handler(lambda c: c.data == 'remove_mapping')
async def process_callback_remove_mapping(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    global channel_mapping
    channel_mapping.clear()  # Очистка всего словаря соответствий
    save_channels()  # Сохранение изменений

    await bot.send_message(callback_query.from_user.id,
                           'Все соответствия каналов удалены и файл channel_mapping.pickle очищен.')


@dp.callback_query_handler(lambda c: c.data == 'last_messages')
async def process_callback_last_messages(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           'Пожалуйста, введите количество последних сообщений, которые вы хотите отправить, после команды /last_messages.')


@dp.message_handler(commands=['help'])
async def help(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    help_message = (
        "Список доступных команд:\n"
        "/start - Начало работы с ботом\n"
        "/help - Получить список доступных команд\n"
        "/add_channel - Добавить канал для работы\n"
        "/remove_channel - Удалить канал из списка\n"
        "/list_channels - Показать список добавленных каналов\n"
        "/add_destination_channel - Добавить канал-получатель\n"
        "/remove_destination_channel - Удалить канал-получатель из списка\n"
        "/list_destination_channels - Показать список каналов-получателей\n"
        "/set_channel_mapping - Установить соответствие между каналами\n"
        "/last_messages (ко-во сообщений или all, если все) - Отправить последние сообщения с каналов\n"
    )

    await message.reply(help_message)


@dp.message_handler(commands=['add_channel'])
async def add_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    try:
        channel_id = int(message.get_args())
        chat = await client.get_entity(channel_id)
        channels[channel_id] = chat.title
        await message.reply(f"Канал {chat.title} добавлен")
        save_channels()
    except (ValueError, IndexError):
        await message.reply("Пожалуйста, укажите корректный ID канала: /add_channel -1001234567890")


@dp.message_handler(commands=['remove_channel'])
async def remove_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    try:
        channel_id = int(message.get_args())
        if channel_id in channels:
            del channels[channel_id]  # Удаляем, если ключ существует
            await message.reply(f"Канал {channel_id} удален")
            save_channels()
        else:
            await message.reply(f"Канал {channel_id} не найден")
    except (ValueError, IndexError):
        await message.reply("Пожалуйста, укажите корректный ID канала: /remove_channel -1001234567890")


@dp.message_handler(commands=['list_channels'])
async def list_channels(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    if channels:
        await message.reply('\n'.join(f"{name} ({id})" for id, name in channels.items()))
    else:
        await message.reply("Список каналов пуст")


@dp.message_handler(commands=['add_destination_channel'])
async def add_destination_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    try:
        channel_id = int(message.get_args())
        chat = await client.get_entity(channel_id)
        destination_channels[channel_id] = chat.title
        await message.reply(f"Канал-получатель {chat.title} добавлен")
        save_channels()
    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректный ID канала-получателя: /add_destination_channel -1001234567890")


@dp.message_handler(commands=['remove_destination_channel'])
async def remove_destination_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    try:
        channel_id = int(message.get_args())
        if channel_id in destination_channels:
            del destination_channels[channel_id]  # Удаляем, если ключ существует
            await message.reply(f"Канал-получатель {channel_id} удален")
            save_channels()
        else:
            await message.reply(f"Канал-получатель {channel_id} не найден")
    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректный ID канала-получателя: /remove_destination_channel -1001234567890")


@dp.message_handler(commands=['list_destination_channels'])
async def list_destination_channels(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return

    if destination_channels:
        await message.reply('\n'.join(f"{name} ({id})" for id, name in destination_channels.items()))
    else:
        await message.reply("Список каналов-получателей пуст")


@dp.message_handler(commands=['set_channel_mapping'])
async def set_channel_mapping(message: types.Message):
    global channel_mapping

    if message.from_user.id != my_id:
        return  # Игнорировать команду, если ID пользователя не совпадает с my_id

    args = message.get_args().split()
    if len(args) != 2:
        await message.reply(
            "Пожалуйста, укажите ID канала-источника и ID канала-получателя через пробел: /set_channel_mapping -1001234567890 -1000987654321")
        return

    try:
        source_channel_id = int(args[0])
        destination_channel_id = int(args[1])

        if source_channel_id not in channels:
            await message.reply(f"Канал-источник {source_channel_id} не найден в списке источников")
            return

        if destination_channel_id not in destination_channels:
            await message.reply(f"Канал-получатель {destination_channel_id} не найден в списке получателей")
            return

        # Получение объектов каналов и их названий
        source_channel = await client.get_entity(source_channel_id)
        destination_channel = await client.get_entity(destination_channel_id)

        channel_mapping[source_channel_id] = destination_channel_id
        await message.reply(
            f"Канал {source_channel.title} ({source_channel_id}) теперь будет пересылать контент на канал {destination_channel.title} ({destination_channel_id})")
        save_channels()

        # Обновление соответствий в коде
        try:
            with open('channel_mapping.pickle', 'rb') as f:
                channel_mapping = pickle.load(f)
        except FileNotFoundError:
            channel_mapping = {}

    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректные ID каналов: /set_channel_mapping -1001234567890 -1000987654321")
    except Exception as e:
        await message.reply(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    async def main():
        try:
            await setup_browser()
            # Объявление переменной channel_mapping перед использованием
            global channel_mapping
            channel_mapping = {}

            # Отправка уведомления о запуске бота
            await send_notification("Бот запущен")

            # Обновление соответствий каналов
            try:
                with open('channel_mapping.pickle', 'rb') as f:
                    channel_mapping = pickle.load(f)
            except FileNotFoundError:
                pass
            clear_db_task = asyncio.create_task(clear_database_at_midnight())

            await client.start()
            await client.connect()
            await setup_database()

            dp.register_message_handler(start, commands=['start'], commands_prefix='/')
            dp.register_message_handler(help, commands=['help'], commands_prefix='/')

            await dp.start_polling()

        except Exception as e:
            # Отправка уведомления об ошибке
            await send_notification(f"Произошла ошибка: {str(e)}")

        finally:
            # Отправка уведомления об остановке бота
            if browser:
                await browser.close()
            await send_notification("Бот остановлен")
            await client.disconnect()
            await close_database()



    asyncio.run(main())
