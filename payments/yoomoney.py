import hashlib
import hmac
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from yoomoney import Client, Quickpay
from dotenv import load_dotenv
import os
import logging
from database.db import reactivate_xui_account

load_dotenv()

YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN")
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET")
NOTIFICATION_SECRET = os.getenv("YOOMONEY_NOTIFICATION_SECRET")

app = FastAPI()


def create_payment_url(user_id: int, amount: float, tariff_days: int) -> str:
    client = Client(YOOMONEY_TOKEN)
    quickpay = Quickpay(
        receiver=YOOMONEY_WALLET,
        quickpay_form="shop",
        targets=f"Подписка на VPN ({tariff_days} дней)",
        payment_type="PC",
        sum=amount,
        label=f"user_{user_id}_{tariff_days}"
    )
    return quickpay.redirected_url


def verify_notification(data: dict) -> bool:
    # Поля для проверки подписи
    fields = [
        data.get("notification_type", ""),
        data.get("operation_id", ""),
        str(data.get("amount", "")),
        data.get("currency", ""),
        data.get("datetime", ""),
        data.get("sender", ""),
        data.get("codepro", ""),
        NOTIFICATION_SECRET,
        data.get("label", "")
    ]
    check_string = "&".join(str(field) for field in fields)
    computed_sha1 = hmac.new(
        NOTIFICATION_SECRET.encode(),
        check_string.encode(),
        hashlib.sha1
    ).hexdigest()

    return computed_sha1 == data.get("sha1_hash", "")


@app.post("/yoomoney")
async def handle_yoomoney_notification(request: Request, bot: Bot = None):
    data = await request.form()
    data = dict(data)

    # Проверяем подпись
    if not verify_notification(data):
        logging.error("Invalid YooMoney notification signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Проверяем время (с допуском ±5 минут)
    notification_time = datetime.fromisoformat(data.get("datetime").replace("Z", "+00:00"))
    current_time = datetime.utcnow()
    if abs((current_time - notification_time).total_seconds()) > 300:
        logging.error("YooMoney notification time mismatch")
        raise HTTPException(status_code=400, detail="Time mismatch")

    # Извлекаем user_id и tariff_days из label
    label = data.get("label", "")
    if not label.startswith("user_"):
        logging.error("Invalid label format")
        raise HTTPException(status_code=400, detail="Invalid label")

    try:
        _, user_id, tariff_days = label.split("_")
        user_id = int(user_id)
        tariff_days = int(tariff_days)
    except ValueError:
        logging.error("Invalid label parsing")
        raise HTTPException(status_code=400, detail="Invalid label format")

    # Активируем подписку
    async with aiosqlite.connect("users.db") as db:
        cursor = await db.execute(
            "SELECT xui_account_id, vpn_config FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            logging.error(f"User {user_id} not found")
            raise HTTPException(status_code=404, detail="User not found")

        xui_account_id, vpn_config = row
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=tariff_days)).isoformat()
        await db.execute(
            "UPDATE users SET subscription_status = ?, subscription_start = ?, subscription_end = ? WHERE user_id = ?",
            ("active", start_date, end_date, user_id)
        )
        await db.commit()
        await reactivate_xui_account(xui_account_id)

    # Отправляем уведомление пользователю
    if bot:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"**Оплата успешна!**\n"
                f"Ваша подписка активирована на {tariff_days} дней.\n\n"
                "**Ваша конфигурация VPN** (скопируйте строку):\n"
                f"```{vpn_config}```"
            ),
            parse_mode="Markdown"
        )

    logging.info(f"Activated subscription for user {user_id}, tariff: {tariff_days} days")
    return {"status": "success"}