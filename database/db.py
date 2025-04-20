import aiosqlite
from datetime import datetime, timedelta
import logging
import uuid

DB_PATH = "users.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                subscription_status TEXT NOT NULL,
                subscription_start TEXT NOT NULL,
                subscription_end TEXT NOT NULL,
                xui_account_id TEXT NOT NULL,
                vpn_config TEXT NOT NULL
            )
        """)
        await db.commit()


async def create_xui_account(user_id: int) -> tuple[str, str]:
    # Заглушка для создания аккаунта в 3X-UI
    # В реальной версии здесь будет запрос к API 3X-UI
    xui_account_id = str(uuid.uuid4())
    vpn_config = f"vless://{xui_account_id}@your_server_ip:443?security=tls#user_{user_id}"
    return xui_account_id, vpn_config


async def deactivate_xui_account(xui_account_id: str):
    # Заглушка для деактивации аккаунта
    # В реальной версии: отправляем запрос к API 3X-UI с enable=false
    logging.info(f"Deactivating XUI account {xui_account_id}")


async def reactivate_xui_account(xui_account_id: str):
    # Заглушка для реактивации аккаунта
    # В реальной версии: отправляем запрос к API 3X-UI с enable=true
    logging.info(f"Reactivating XUI account {xui_account_id}")


async def register_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем, есть ли пользователь
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if await cursor.fetchone():
            logging.info(f"User {user_id} already registered")
            return False, None

        # Создаём аккаунт в 3X-UI
        xui_account_id, vpn_config = await create_xui_account(user_id)

        # Регистрируем нового пользователя с пробным периодом
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=3)).isoformat()
        await db.execute(
            "INSERT INTO users (user_id, username, subscription_status, subscription_start, subscription_end, xui_account_id, vpn_config) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, "trial", start_date, end_date, xui_account_id, vpn_config)
        )
        await db.commit()
        logging.info(f"Registered user {user_id} with trial period")
        return True, vpn_config


async def get_user_status(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT subscription_status, subscription_start, subscription_end, xui_account_id, vpn_config FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        status, start_date, end_date, xui_account_id, vpn_config = row
        end_date_dt = datetime.fromisoformat(end_date)
        if end_date_dt < datetime.now() and status != "expired":
            # Деактивируем аккаунт в 3X-UI
            await deactivate_xui_account(xui_account_id)
            await db.execute(
                "UPDATE users SET subscription_status = ? WHERE user_id = ?",
                ("expired", user_id)
            )
            await db.commit()
            status = "expired"

        return {
            "status": status,
            "start_date": datetime.fromisoformat(start_date),
            "end_date": end_date_dt,
            "xui_account_id": xui_account_id,
            "vpn_config": vpn_config
        }


async def simulate_trial_end(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT xui_account_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False

        xui_account_id = row[0]
        # Устанавливаем subscription_end в прошлое
        past_date = (datetime.now() - timedelta(days=1)).isoformat()
        await db.execute(
            "UPDATE users SET subscription_end = ?, subscription_status = ? WHERE user_id = ?",
            (past_date, "expired", user_id)
        )
        await db.commit()
        await deactivate_xui_account(xui_account_id)
        logging.info(f"Simulated trial end for user {user_id}")
        return True


async def simulate_payment(user_id: int, tariff_days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT xui_account_id, vpn_config FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None, None

        xui_account_id, vpn_config = row
        # Обновляем подписку
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=tariff_days)).isoformat()
        await db.execute(
            "UPDATE users SET subscription_status = ?, subscription_start = ?, subscription_end = ? WHERE user_id = ?",
            ("active", start_date, end_date, user_id)
        )
        await db.commit()
        await reactivate_xui_account(xui_account_id)
        logging.info(f"Simulated payment for user {user_id}, tariff: {tariff_days} days")
        return xui_account_id, vpn_config