import logging
import aiohttp

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status  # noqa
from sqlalchemy.ext.asyncio import AsyncSession
from scrapyd_api import ScrapydAPI

from api import deps
from core.config import settings

import schemas, crud

# Настройка логгера для этого модуля
logger = logging.getLogger("scrapyd_api")

SCRAPYD_URL = "http://scrapyd:6800"
scrapyd = ScrapydAPI(SCRAPYD_URL)

router = APIRouter()

@router.post("/schedule/")
async def schedule_task(
    *,
    db: AsyncSession = Depends(deps.get_db),
    chat_id: int = None,
    url: str,
    domain: str = Depends(deps.get_domain),
    source: schemas.source = Depends(deps.get_source)
) -> Any:
    logger.info(f"Получен запрос на парсинг: url={url}, chat_id={chat_id}, domain={domain}")
    logger.info(f"Объект source: {source}")

    if not source:
        allowed_domains = [
            source.domain for source in await crud.source.get_rows(db, limit=None)
        ]
        detail = (
            f'⚠️ Домен {domain} не поддерживается.\n\n'
            f'Введите ссылку на статью с одного из сайтов: '
            f'{", ".join(allowed_domains)}.'
        )
        logger.warning(f"Домен не поддерживается: {domain}")
        raise HTTPException(status_code=422, detail=detail)

    item = await crud.item.get_by_url(db=db, url=url)
    if item:
        logger.info(f"URL уже существует в базе, возвращаю job_id={item.job_id}")
        return {'job_id': item.job_id}

    logger.info(f"Создаю новую запись item для url={url}, source_id={source.id}")
    _ = await crud.item.create(
        db=db, obj_in={
            'chat_id': chat_id,
            'source_id': source.id,
            'url': url,
            'status': schemas.Status.NEW
        }
    )

    logger.info(f"Пробую запустить паука: project='default', spider_name='{source.spider_name}', url='{url}'")
    try:
        result = scrapyd.schedule(
            'default', source.spider_name, url=url
        )
        logger.info(f"Результат scrapyd.schedule: {result}")
    except Exception as e:
        logger.error(f"Ошибка при вызове scrapyd.schedule: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка scrapyd: {e}"
        )

    status_ = result.get('status')
    if status_ == 'ok':
        jobid = result.get('jobid')
        logger.info(f"Задача успешно запущена: jobid={jobid}")
        return {'job_id': jobid}

    logger.error(f"Ошибка запуска паука: {result}")
    raise HTTPException(
        status_code=422,
        detail=f"Scrapy spider with name '{source.spider_name}' not found"
    )

@router.get("/status/{job_id}")
async def get_status(
    *,
    db: AsyncSession = Depends(deps.get_db),
    job_id: str
) -> schemas.Item:
    logger.info(f"Получен запрос на статус job_id={job_id}")
    item = await crud.item.get_by_job_id(db=db, job_id=job_id)
    if not item:
        logger.warning(f"Item с job_id={job_id} не найден")
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.get("/webhook/{item_id}")
async def webhook(
    *,
    db: AsyncSession = Depends(deps.get_db),
    item_id: int
) -> schemas.Item:
    logger.info(f"Получен webhook для item_id={item_id}")
    item = await crud.item.get(db=db, id=item_id)
    if not item:
        logger.warning(f"Item с id={item_id} не найден")
        raise HTTPException(status_code=404, detail="Item not found")
    TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
    TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    text = (f'<b>{item.title}</b>\n\n'
            f'<a href="{item.telegraph_url}">'
            f'{item.telegraph_url}'
            '</a>')
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🇷🇺 Перевод статьи', 'callback_data': f'get_translate:{item.id}'},
                {'text': '📝️ Саммари статьи', 'callback_data': f'get_summary:{item.id}'}
            ]
        ]
    }
    payload = {
        'chat_id': item.chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': keyboard
    }
    logger.info(f"Отправляю сообщение в Telegram для chat_id={item.chat_id}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
                TELEGRAM_API_URL,
                json=payload
        ) as response:
            resp_text = await response.text()
            if response.status == 200:
                logger.info(f"Telegram sendMessage OK: {resp_text}")
            else:
                logger.warning(f"Telegram sendMessage failed: {response.status} {resp_text}")

    return item
