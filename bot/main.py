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
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import urlparse
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Получаем переменные окружения
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
AUTHORIZED_PASSWORD = os.getenv('TELEGRAM_BOT_PASSWORD')
FASTAPI_URL = os.getenv('API_URL')

# Проверка обязательных переменных окружения
if not all([API_TOKEN, AUTHORIZED_PASSWORD, FASTAPI_URL]):
    missing_vars = []
    if not API_TOKEN:
        missing_vars.append('TELEGRAM_BOT_TOKEN')
    if not AUTHORIZED_PASSWORD:
        missing_vars.append('TELEGRAM_BOT_PASSWORD')
    if not FASTAPI_URL:
        missing_vars.append('API_URL')
    error_msg = f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)

logger.info(f"FASTAPI_URL = {FASTAPI_URL}")

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

# Функция для повторных попыток API запросов
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def make_api_request(session, url, method='GET', **kwargs):
    try:
        async with getattr(session, method.lower())(url, **kwargs) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 422:
                data = await response.json()
                raise ValueError(data.get('detail', 'Validation error'))
            else:
                raise aiohttp.ClientError(f"API request failed with status {response.status}")
    except Exception as e:
        logger.error(f"API request failed: {str(e)}")
        raise

# Определяем функцию для запуска парсинга страницы через FastAPI
async def trigger_scrapy_spider(spider_name, url):
    logger.info(f"Отправляю запрос к {FASTAPI_URL}/schedule/ для spider={spider_name}, url={url}")
    async with aiohttp.ClientSession() as session:
        try:
            data = await make_api_request(
                session,
                f'{FASTAPI_URL}/schedule/',
                method='POST',
                json={'spider': spider_name, 'url': url}
            )
            return data.get('jobid')
        except Exception as e:
            logger.error(f"Failed to trigger spider: {str(e)}")
            return None

# Определяем паука в зависимости от домена
def get_spider_name_by_domain(url):
    try:
        domain = urlparse(url).netloc
        for allowed in ALLOWED_DOMAINS:
            if allowed in domain:
                return DOMAIN_SPIDER_MAP.get(allowed)
        return None
    except Exception as e:
        logger.error(f"Error parsing domain: {str(e)}")
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

    url = message.text.strip()
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

    # Отправляем запрос в API для парсинга
    try:
        async with aiohttp.ClientSession() as session:
            data = await make_api_request(
                session,
                f'{FASTAPI_URL}/scrapyd/schedule/',
                method='POST',
                params={'chat_id': message.chat.id, 'url': url}
            )
            await message.answer(
                '⏱️ Подождите, запрос обрабатывается...',
                parse_mode=ParseMode.HTML
            )
    except ValueError as e:
        await message.answer(str(e))
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}")
        await message.answer(
            '‼️ Произошла ошибка при обработке запроса. Попробуйте позже.'
        )

# Обработка нажатий на кнопки
@dp.callback_query()
async def callback_query_handler(call: types.CallbackQuery):
    try:
        action, id_ = call.data.split(':')
        async with aiohttp.ClientSession() as session:
            if action == 'get_translate':
                logger.info(f"Отправляю запрос к {FASTAPI_URL}/items/{id_}/translate")
                await make_api_request(
                    session,
                    f'{FASTAPI_URL}/items/{id_}/translate',
                    method='GET'
                )
                message = '⏱️ Подождите, запрос обрабатывается...'
            elif action == 'get_summary':
                logger.info(f"Отправляю запрос к {FASTAPI_URL}/items/{id_}/summarize")
                await make_api_request(
                    session,
                    f'{FASTAPI_URL}/items/{id_}/summarize',
                    method='GET'
                )
                message = '⏱️ Подождите, запрос обрабатывается...'
            else:
                message = '⚠️ Неизвестное действие'
            
            await call.message.answer(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}")
        await call.message.answer(
            '⚠️ Произошла ошибка при обработке запроса. Попробуйте позже.'
        )

async def main():
    try:
        # Сбрасываем webhook, чтобы Telegram не пытался доставлять обновления через HTTP
        await bot.delete_webhook(drop_pending_updates=True)
        # Запускаем polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {str(e)}")
        raise
