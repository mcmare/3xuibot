import asyncio
import logging
from aiogram import Bot, Dispatcher
from fastapi import FastAPI
import uvicorn
from handlers import start
from payments.yoomoney import app as fastapi_app
from database.db import init_db

logging.basicConfig(level=logging.INFO)


async def main():
    logging.info("Initializing database...")
    await init_db()

    logging.info("Starting bot...")
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(start.router)

    logging.info("Starting FastAPI server...")
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=9000)
    server = uvicorn.Server(config)

    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    asyncio.run(main())