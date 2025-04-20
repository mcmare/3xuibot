import hashlib
import hmac
import aiosqlite
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException, Depends
from yoomoney import Client, Quickpay  # type: ignore
from dotenv import load_dotenv
import os
import logging
from aiogram import Bot

load_dotenv()

YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN")
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET")
NOTIFICATION_SECRET = os.getenv("YOOMONEY_NOTIFICATION_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()

# Проверка переменных окружения
if not all([YOOMONEY_TOKEN, YOOMONEY_WALLET, NOTIFICATION_SECRET, BOT_TOKEN]):
    logging.error("Missing environment variables: YOOMONEY_TOKEN, YOOMONEY_WALLET, NOTIFICATION_SECRET, or BOT_TOKEN")
    raise ValueError("Missing required environment variables")


# Функция для создания экземпляра Bot
async def get_bot():
    return Bot(token=BOT_TOKEN)


def create_payment_url(user_id: int, amount: float, tariff_days: int) -> str:
    try:
        client = Client(YOOMONEY_TOKEN)
        quickpay = Quickpay(
            receiver=YOOMONEY_WALLET,
            quickpay_form="shop",
            targets=f"Подписка на VPN \\({tariff_days} дней\\)",
            paymentType="PC",
            sum=amount,
            label=f"user_{user_id}_{tariff_days}"
        )
        logging.info(f"Created payment URL for user {user_id}, tariff {tariff_days} days")
        return quickpay.redirected_url
    except Exception as e:
        logging.error(f"Failed to create payment URL for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment URL")


def verify_notification(data: dict) -> bool:
    try:
        fields = [
            data.get("notification_type", ""),
            data.get("operation_id", ""),
            str(data.get("amount", "")),
            data.get("currency", ""),
            data.get("datetime", ""),
            data.get("sender", ""),
            str(data.get("codepro", "")).lower(),
            NOTIFICATION_SECRET,
            data.get("label", "")
        ]
        check_string = "&".join(str(field) for field in fields)
        computed_sha1 = hmac.new(
            NOTIFICATION_SECRET.encode(),
            check_string.encode(),
            hashlib.sha1
        ).hexdigest()

        received_sha1 = data.get("sha1_hash", "")
        logging.info(f"Verify notification - Check string: {check_string}")
        logging.info(f"Computed SHA1: {computed_sha1}")
        logging.info(f"Received SHA1: {received_sha1}")

        return computed_sha1 == received_sha1
    except Exception as e:
        logging.error(f"Error in verify_notification: {e}")
        return False


@app.post("/yoomoney")
async def handle_yoomoney_notification(request: Request, bot: Bot = Depends(get_bot)):
    try:
        data = await request.form()
        data = dict(data)
        logging.info(f"Received YooMoney notification: {data}")

        # Проверяем подпись
        if not verify_notification(data):
            logging.error("Invalid YooMoney notification signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Проверяем время (±5 минут)
        try:
            notification_time = datetime.fromisoformat(data.get("datetime").replace("Z", "+00:00"))
            current_time = datetime.now(timezone.utc)
            time_diff = abs((current_time - notification_time).total_seconds())
            logging.info(f"Notification time: {notification_time}, Current time: {current_time}, Diff: {time_diff}s")
            if time_diff > 300:
                logging.error("YooMoney notification time mismatch")
                raise HTTPException(status_code=400, detail="Time mismatch")
        except ValueError as e:
            logging.error(f"Invalid datetime format: {e}")
            raise HTTPException(status_code=400, detail="Invalid datetime")

        # Извлекаем user_id и tariff_days
        label = data.get("label", "")
        logging.info(f"Processing label: {label}")
        if not label.startswith("user_"):
            logging.error(f"Invalid label format: {label}")
            raise HTTPException(status_code=400, detail="Invalid label")

        try:
            _, user_id, tariff_days = label.split("_")
            user_id = int(user_id)
            tariff_days = int(tariff_days)
            logging.info(f"Parsed label: user_id={user_id}, tariff_days={tariff_days}")
        except ValueError as e:
            logging.error(f"Invalid label parsing: {e}")
            raise HTTPException(status_code=400, detail="Invalid label format")

        # Активируем подписку
        async with aiosqlite.connect("users.db") as db:
            try:
                cursor = await db.execute(
                    "SELECT xui_account_id, vpn_config FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    logging.error(f"User {user_id} not found in database")
                    raise HTTPException(status_code=404, detail="User not found")

                xui_account_id, vpn_config = row
                start_date = datetime.now(timezone.utc).isoformat()
                end_date = (datetime.now(timezone.utc) + timedelta(days=tariff_days)).isoformat()
                await db.execute(
                    """
                    UPDATE users 
                    SET subscription_status = ?, subscription_start = ?, subscription_end = ?
                    WHERE user_id = ?
                    """,
                    ("active", start_date, end_date, user_id)
                )
                await db.commit()
                logging.info(f"Updated database for user {user_id}: status=active, start={start_date}, end={end_date}")
            except Exception as e:
                logging.error(f"Failed to update database for user {user_id}: {e}")
                raise HTTPException(status_code=500, detail="Database update failed")

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"**Оплата успешна!**\n"
                    f"Ваша подписка активирована на {tariff_days} дней.\n\n"
                    f"**Ваша конфигурация VPN** (скопируйте строку):\n"
                    f"```{vpn_config}```"
                ),
                parse_mode="Markdown"
            )
            logging.info(f"Sent success notification to user {user_id}")
        except Exception as e:
            logging.error(f"Failed to send notification to user {user_id}: {e}")

        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error in handle_yoomoney_notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))