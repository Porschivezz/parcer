import os
import re
import asyncio
import aiohttp
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.bot import DefaultBotProperties
from aiogram.types import ContentType, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, Command
from aiogram.enums.parse_mode import ParseMode

from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
AUTHORIZED_PASSWORD = os.environ.get('TELEGRAM_BOT_PASSWORD')
FASTAPI_URL = os.environ.get('API_URL')

# Проверка, что переменная окружения API_URL задана
if not FASTAPI_URL:
    logging.error("Переменная окружения API_URL не задана! Бот не может работать.")
    raise RuntimeError("API_URL env variable is required!")

logging.info(f"FASTAPI_URL = {FASTAPI_URL}")

# Регулярное выражение для проверки домена
DOMAIN_REGEX = re.compile(r'https?://(www\.)?([^/]+)')

# Список разрешенных доменов
ALLOWED_DOMAINS = ['reuters.com', 'ft.com', 'thenationalnews.com', 'wsj.com']

DOMAIN_SPIDER_MAP = {
    'reuters.com': 'reuters_spider',
    'ft.com': 'ft_spider',
    'thenationalnews.com': 'national_spider',
    'wsj.com': 'wsj_spider'
}

DOMAIN_SOURCE_MAP = {
    'reuters.com': 'Reuters',
    'ft.com': 'Financial Times',
    'thenationalnews.com': 'The National',
    'wsj.com': 'The Wall Street Journal'
}

# Инициализация бота и диспетчера
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Временное хранилище авторизованных пользователей
authorized_users = set()

# Определяем функцию для запуска парсинга страницы через FastAPI
async def trigger_scrapy_spider(spider_name, url):
    logging.info(f"Отправляю запрос к {FASTAPI_URL}/schedule/ для spider={spider_name}, url={url}")
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{FASTAPI_URL}/schedule/', json={'spider': spider_name, 'url': url}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('jobid')
            return 'Error: Failed to start scraping.'

# Определяем паука в зависимости от домена
def get_spider_name_by_domain(url):
    domain = urlparse(url).netloc
    for allowed in ALLOWED_DOMAINS:
        if allowed in domain:
            return DOMAIN_SPIDER_MAP.get(allowed)
    return None

# Клавиатура с опциями для получения текста статьи или ссылки на Telegraph
def item_events_markup(job_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text='📰 Показать текст статьи',
            callback_data=f'get_link:{job_id}'
        )
    ]])

# Клавиатура с опциями для перевода и саммари статьи
def item_options_markup(item_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text='🌐 Перевод статьи',
            callback_data=f'translate:{item_id}'
        ),
        InlineKeyboardButton(
            text='✏️ Саммари статьи',
            callback_data=f'summary:{item_id}'
        )
    ]])

def item_translate_button(item_id: str):
    return [InlineKeyboardButton(
        text='🇷🇺 Получить перевод статьи',
        callback_data=f'get_translate:{item_id}'
    )]

def item_summary_button(item_id: str):
    return [InlineKeyboardButton(
        text='📝 Получить саммари статьи',
        callback_data=f'get_summary:{item_id}'
    )]

# Обработчик команды /start
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        'Привет! 👋 Для работы с ботом необходимо '
        'авторизоваться с помощью команды /login <пароль>'
    )

# Обработчик команды /login
@dp.message(Command('login'))
async def login_command(message: types.Message):
    try:
        password = message.text.split()[1]
    except IndexError:
        await message.answer(
            '⚠️ Пожалуйста, введите команду в формате /login <пароль>.'
        )
        return

    if password == AUTHORIZED_PASSWORD:
        authorized_users.add(message.from_user.id)
        await message.answer(
            'Вы успешно авторизованы! 👍\n'
            'Теперь Вы можете отправлять ссылки '
            'для извлечения содержимого статей.'
        )
    else:
        await message.answer('⛔ Неверный пароль.')

# Обработка ссылки на статью
@dp.message(~F.text.startswith("/"))
async def handle_message(message: types.Message):
    if message.from_user.id not in authorized_users:
        await message.answer(
            '⚠️ Пожалуйста, авторизуйтесь с помощью команды /login.'
        )
        return

    url = message.text
    domain_match = DOMAIN_REGEX.search(url)
    if not domain_match:
        await message.answer(
            '⚠️ Это не похоже на ссылку.\n\n'
            'Пожалуйста, отправьте корректную ссылку.'
        )
        return

    domain = domain_match.group(2)
    if domain not in ALLOWED_DOMAINS or not DOMAIN_SPIDER_MAP.get(domain):
        await message.answer(
            f'⚠️ Домен {domain} не поддерживается.\n\n'
            f'Введите ссылку на статью с одного из сайтов: {", ".join(ALLOWED_DOMAINS)}.'
        )
        return

    # Отправляем запрос в сторонний сервис для парсинга
    logging.info(f"Отправляю запрос к {FASTAPI_URL}/scrapyd/schedule/ для url={url}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'{FASTAPI_URL}/scrapyd/schedule/',
            params={'chat_id': message.chat.id, 'url': url}
        ) as response:
            if response.status == 422:
                data = await response.json()
                return await message.answer(
                    data.get('detail')
                )
            if response.status != 200:
                return await message.answer(
                    '‼️ Ошибка при запуске парсера. Попробуйте позже.'
                )
            data = await response.json()
            return await message.answer(
                '⏱️ Подождите, запрос обрабатывается...',
                parse_mode=ParseMode.HTML
            )

# Обработка нажатий на кнопки
@dp.callback_query()
async def callback_query_handler(call: types.CallbackQuery):
    action, id_ = call.data.split(':')
    if action == 'get_translate':
        logging.info(f"Отправляю запрос к {FASTAPI_URL}/items/{id_}/translate")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f'{FASTAPI_URL}/items/{id_}/translate') as response:
                if response.status == 200:
                    message = '⏱️ Подождите, запрос обрабатывается...'
                else:
                    message = '⚠️ Что-то пошло не так'
        await call.message.answer(message, parse_mode=ParseMode.HTML)
    elif action == 'get_summary':
        logging.info(f"Отправляю запрос к {FASTAPI_URL}/items/{id_}/summarize")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f'{FASTAPI_URL}/items/{id_}/summarize') as response:
                if response.status == 200:
                    message = '⏱️ Подождите, запрос обрабатывается...'
                else:
                    message = '⚠️ Что-то пошло не так'
        await call.message.answer(
            message, parse_mode=ParseMode.HTML
        )

async def main():
    # Сбрасываем webhook, чтобы Telegram не пытался доставлять обновления через HTTP
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем polling (единожды!)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
