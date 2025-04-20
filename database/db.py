import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                xui_account_id TEXT,
                vpn_config TEXT,
                subscription_status TEXT,
                subscription_start TEXT,
                subscription_end TEXT
            )
        """)
        await db.commit()
    logging.info("Database initialized")

async def init_user(user_id: int):
    try:
        async with aiosqlite.connect("users.db") as db:
            xui_account_id = f"xui_{user_id}"
            vpn_config = f"vless://{user_id}@your_server_ip:443?security=tls#user_{user_id}"
            start_date = datetime.now(timezone.utc).isoformat()
            end_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()  # 7 дней триала
            await db.execute(
                """
                INSERT OR IGNORE INTO users 
                (user_id, xui_account_id, vpn_config, subscription_status, subscription_start, subscription_end) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, xui_account_id, vpn_config, "trial", start_date, end_date)
            )
            await db.commit()
        logging.info(f"Initialized user {user_id} with trial period")
    except Exception as e:
        logging.error(f"Failed to initialize user {user_id}: {e}")

async def check_subscription(user_id: int):
    try:
        async with aiosqlite.connect("users.db") as db:
            cursor = await db.execute(
                "SELECT subscription_status, subscription_end FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]
            return None, None
    except Exception as e:
        logging.error(f"Failed to check subscription for user {user_id}: {e}")
        return None, None