import asyncio
import logging
import uvicorn
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os
from database.db import init_db
from handlers import start
from payments.yoomoney import app as fastapi_app
from fastapi import Depends

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Регистрация обработчиков
dp.include_router(start.router)


# Передаём bot в FastAPI через Depends
def get_bot():
    return bot


fastapi_app.dependency_overrides[Depends] = get_bot


async def start_bot():
    logging.info("Starting bot...")
    await dp.start_polling(bot)


async def start_fastapi():
    logging.info("Starting FastAPI server...")
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    logging.info("Initializing database...")
    await init_db()

    # Запускаем бот и FastAPI параллельно
    await asyncio.gather(start_bot(), start_fastapi())


if __name__ == "__main__":
    asyncio.run(main())