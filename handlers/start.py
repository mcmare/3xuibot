from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from aiogram.enums import ParseMode
from datetime import datetime
from database.db import register_user, get_user_status, simulate_trial_end
from payments.yoomoney import create_payment_url

router = Router()

# Определение тарифов
TARIFFS = {
    "month": {"name": "1 месяц", "price": 500, "days": 30}
    # Другие тарифы можно добавить, раскомментировав:
    # "quarter": {"name": "3 месяца", "price": 1200, "days": 90},
    # "year": {"name": "1 год", "price": 5000, "days": 365}
}


class TariffCallback(CallbackData, prefix="buy"):
    tariff: str


@router.message(Command("start"))
async def cmd_start(message: Message):
    # Регистрируем пользователя
    username = message.from_user.username or "unknown"
    result = await register_user(message.from_user.id, username)

    # Проверяем статус подписки
    user_status = await get_user_status(message.from_user.id)
    if not user_status:
        await message.answer("Ошибка: пользователь не найден.")
        return

    status = user_status["status"]
    end_date = user_status["end_date"]
    vpn_config = user_status["vpn_config"]
    days_left = (end_date - datetime.now()).days if status != "expired" else 0

    # Формируем сообщение
    if isinstance(result, tuple) and result[0]:  # Новый пользователь
        msg = (
            "**Добро пожаловать!**\n"
            "Вы получили бесплатный пробный период на 3 дня.\n\n"
            "**Ваша конфигурация VPN** (скопируйте строку):\n"
            f"```{vpn_config}```"
        )
    elif status == "trial":
        msg = (
            "**Ваш пробный период активен**\n"
            f"Осталось: {days_left} дней\n\n"
            "**Ваша конфигурация VPN** (скопируйте строку):\n"
            f"```{vpn_config}```"
        )
    elif status == "active":
        msg = (
            "**Ваша подписка активна**\n"
            f"Осталось: {days_left} дней\n\n"
            "**Ваша конфигурация VPN** (скопируйте строку):\n"
            f"```{vpn_config}```"
        )
    else:
        msg = (
            "**Ваш пробный период истёк**\n"
            "Оформите подписку, чтобы продолжить.\n\n"
            "**Ваша конфигурация VPN** (неактивна, скопируйте для последующего использования):\n"
            f"```{vpn_config}```"
        )

    # Добавляем кнопку "Купить VPN"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить VPN", callback_data="show_tariffs")]
    ])
    await message.answer(
        f"{msg}\n\n**Действия**: Нажмите кнопку ниже, чтобы купить или продлить подписку:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


@router.callback_query(lambda c: c.data == "show_tariffs")
async def show_tariffs(callback_query):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{TARIFFS['month']['name']} ({TARIFFS['month']['price']} руб)",
                              callback_data=TariffCallback(tariff="month").pack())]
        # Другие тарифы можно добавить, раскомментировав:
        # [InlineKeyboardButton(text=f"{TARIFFS['quarter']['name']} ({TARIFFS['quarter']['price']} руб)", callback_data=TariffCallback(tariff="quarter").pack())],
        # [InlineKeyboardButton(text=f"{TARIFFS['year']['name']} ({TARIFFS['year']['price']} руб)", callback_data=TariffCallback(tariff="year").pack())]
    ])
    await callback_query.message.answer("**Выберите тариф**:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback_query.answer()


@router.callback_query(TariffCallback.filter())
async def process_tariff_selection(callback_query, callback_data: TariffCallback):
    tariff = callback_data.tariff
    if tariff not in TARIFFS:
        await callback_query.message.answer("Ошибка: выбранный тариф недоступен.")
        return

    # Создаём платёжную ссылку
    payment_url = create_payment_url(
        user_id=callback_query.from_user.id,
        amount=TARIFFS[tariff]["price"],
        tariff_days=TARIFFS[tariff]["days"]
    )

    await callback_query.message.answer(
        f"**Оплатите подписку**\n"
        f"Тариф: {TARIFFS[tariff]['name']} за {TARIFFS[tariff]['price']} руб.\n"
        f"Перейдите по ссылке для оплаты:\n{payment_url}\n\n"
        "После оплаты используйте /check_payment для проверки статуса.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback_query.answer()


@router.message(Command("simulate_trial_end"))
async def cmd_simulate_trial_end(message: Message):
    success = await simulate_trial_end(message.from_user.id)
    if not success:
        await message.answer("Ошибка: пользователь не найден.")
        return
    await message.answer("Триальный период завершён. Проверьте статус с помощью /start.")


@router.message(Command("check_payment"))
async def cmd_check_payment(message: Message):
    # Временная заглушка, позже интегрируем проверку через базу данных
    await message.answer("Проверка оплаты пока не реализована. Ожидайте уведомления от бота после оплаты.")