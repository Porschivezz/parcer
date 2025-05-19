# News Parser Project

Проект для сбора, обработки и распространения новостей через Telegram бота.

## Компоненты проекта

- **API** - FastAPI сервер для управления новостями
- **Bot** - Telegram бот для распространения новостей
- **Scrapy** - Парсер новостей с различных источников
- **PostgreSQL** - База данных для хранения новостей

## Требования

- Docker
- Docker Compose
- Python 3.9+

## Установка и запуск

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd parcer
```

2. Создайте файл .env на основе .env.example:
```bash
cp .env.example .env
```

3. Отредактируйте .env файл, указав необходимые параметры

4. Запустите проект:
```bash
docker-compose up -d
```

## Доступ к сервисам

- API: http://localhost:8000
- Scrapyd: http://localhost:6800
- PostgreSQL: localhost:5432

## Структура проекта

```
.
├── api/            # FastAPI приложение
├── bot/           # Telegram бот
├── scrapy/        # Парсер новостей
├── docker-compose.yml
└── .env
```

## Разработка

Для разработки рекомендуется использовать виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
.\venv\Scripts\activate  # для Windows
```

## Лицензия

MIT 