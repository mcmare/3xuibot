from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from database.db import init_user, check_subscription
from payments.yoomoney import create_payment_url  # type: ignore
import logging
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

router = Router()

# Парсим тарифы из .env
TARIFFS = []
try:
    tariff_str = os.getenv("TARIFFS", "30:500,90:1200,180:2000")
    for tariff in tariff_str.split(","):
        days, price = tariff.split(":")
        days = int(days)
        price = float(price)
        if days <= 0 or price <= 0:
            raise ValueError(f"Invalid tariff: days={days}, price={price}")
        TARIFFS.append({"days": days, "price": price})
    logging.info(f"Loaded tariffs: {TARIFFS}")
except ValueError as e:
    logging.error(f"Invalid TARIFFS format in .env: {e}")
    TARIFFS = [{"days": 30, "price": 500}, {"days": 90, "price": 1200}, {"days": 180, "price": 2000}]


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    subscription_status, subscription_end = await check_subscription(user_id)

    if subscription_status is None:
        await init_user(user_id)
        subscription_status = "trial"
        subscription_end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        logging.info(f"Registered user {user_id} with trial period")

    text = (
        f"**Добро пожаловать!**\n"
        f"Ваш статус подписки: {'Пробный' if subscription_status == 'trial' else 'Активна' if subscription_status == 'active' else 'Неактивна'}\n"
    )
    if subscription_status in ("active", "trial") and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end.replace("Z", "+00:00"))
            days_left = (end_date - datetime.now(timezone.utc)).days
            if days_left >= 0:
                text += f"Подписка активна ещё {days_left} дней\n"
            else:
                text += "Подписка истекла\n"
        except ValueError as e:
            logging.error(f"Invalid subscription_end format for user {user_id}: {e}")
            text += "Ошибка в дате подписки\n"
    else:
        text += "Подписка неактивна\n"

    text += "\nНажмите кнопку ниже, чтобы купить или продлить подписку."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить VPN", callback_data="buy_vpn")]
    ])

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.message(Command("check_payment"))
async def cmd_check_payment(message: Message):
    user_id = message.from_user.id
    subscription_status, subscription_end = await check_subscription(user_id)

    if subscription_status == "active" and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end.replace("Z", "+00:00"))
            days_left = (end_date - datetime.now(timezone.utc)).days
            if days_left >= 0:
                await message.answer(
                    f"**Подписка активна!**\nОсталось {days_left} дней.",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "Подписка истекла. Пожалуйста, продлите подписку.",
                    parse_mode="Markdown"
                )
        except ValueError as e:
            logging.error(f"Invalid subscription_end format for user {user_id}: {e}")
            await message.answer("Ошибка в дате подписки.")
    else:
        await message.answer("Подписка неактивна. Пожалуйста, оплатите подписку.")


@router.callback_query(F.data == "buy_vpn")
async def process_buy_vpn(callback_query: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{tariff['days']} дней ({tariff['price']} руб)",
            callback_data=f"tariff_{tariff['days']}_{tariff['price']}"
        )] for tariff in TARIFFS
    ])

    await callback_query.message.answer(
        "Выберите тарифный план:",
        reply_markup=keyboard
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def process_tariff_selection(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    tariff_data = callback_query.data.split("_")
    tariff_days = int(tariff_data[1])
    amount = float(tariff_data[2])

    tariff_name = {
        30: "1 месяц",
        90: "3 месяца",
        180: "6 месяцев"
    }.get(tariff_days, f"{tariff_days} дней")

    payment_url = create_payment_url(user_id, amount, tariff_days)
    logging.info(f"Generated payment URL for user {user_id}: {payment_url}")

    await callback_query.message.answer(
        f"**Оплатите подписку**\nТариф: {tariff_name} за {amount} руб.",
        parse_mode="Markdown"
    )

    text = (
        f"Перейдите по ссылке для оплаты:\n{payment_url}\n\n"
        f"После оплаты нажмите кнопку ниже для проверки."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=payment_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")]
    ])

    logging.info(f"Sending message to user {user_id}: {text}")

    await callback_query.message.answer(
        text=text,
        parse_mode=None,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback_query.answer()


@router.callback_query(F.data == "check_payment")
async def process_check_payment(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    subscription_status, subscription_end = await check_subscription(user_id)

    if subscription_status == "active" and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end.replace("Z", "+00:00"))
            days_left = (end_date - datetime.now(timezone.utc)).days
            if days_left >= 0:
                await callback_query.message.answer(
                    f"**Подписка активна!**\nОсталось {days_left} дней.",
                    parse_mode="Markdown"
                )
            else:
                await callback_query.message.answer(
                    "Подписка истекла. Пожалуйста, продлите подписку.",
                    parse_mode="Markdown"
                )
        except ValueError as e:
            logging.error(f"Invalid subscription_end format for user {user_id}: {e}")
            await callback_query.message.answer("Ошибка в дате подписки.")
    else:
        await callback_query.message.answer("Подписка неактивна. Пожалуйста, оплатите подписку.")
    await callback_query.answer()