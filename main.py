import asyncio
import datetime
import json

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest

from alerts_in_ua import AsyncClient as AsyncAlertsClient


BOT_TOKEN = "8679723684:AAGxWFx0XnULaTE9Q0Pd38eXYBZ_Z1OHejE"
ALERT_API_KEY = "2f48ff711d40a56e505c69ff38f675bc6ead4aa0ab2203"

CHECK_INTERVAL = 30
OBLAST_NAME = "Запорізька область"

# ⚡ кеш оновлюється максимум раз на 15 секунд
CACHE_TTL = 15

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
alerts_client = AsyncAlertsClient(token=ALERT_API_KEY)

last_status = None
status_cache = None
cache_time = None


# -------------------- ПІДПИСНИКИ --------------------

def load_subscribers():
    try:
        with open("subscribers.json", "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_subscribers():
    with open("subscribers.json", "w") as f:
        json.dump(list(subscribers), f)


subscribers = load_subscribers()


# -------------------- КНОПКИ --------------------

def get_status_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Оновити дані",
                    callback_data="refresh_status"
                )
            ]
        ]
    )


def get_loading_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏳ Оновлюю...",
                    callback_data="loading"
                )
            ]
        ]
    )


# -------------------- КЕШОВАНИЙ СТАТУС --------------------

async def get_current_status():
    global status_cache, cache_time

    now = datetime.datetime.now()

    # якщо кеш ще актуальний
    if status_cache and cache_time:
        if (now - cache_time).total_seconds() < CACHE_TTL:
            return status_cache

    # якщо кеш прострочений — робимо API запит
    active_alerts = await alerts_client.get_active_alerts()
    air_raid_alerts = active_alerts.get_air_raid_alerts()

    oblast_alerts = [
        alert for alert in air_raid_alerts
        if alert.location_oblast == OBLAST_NAME
    ]

    result = (len(oblast_alerts) > 0, active_alerts.get_last_updated_at())

    status_cache = result
    cache_time = now

    return result


# -------------------- /start --------------------

@dp.message(CommandStart())
async def start_handler(message: Message):
    subscribers.add(message.chat.id)
    save_subscribers()

    is_alert, updated_at = await get_current_status()
    updated_str = updated_at.strftime("%H:%M:%S")

    if is_alert:
        status_text = "🚨 Зараз активна повітряна тривога!"
    else:
        status_text = "✅ Повітряної тривоги немає"

    text = (
        "👋 Вітаю!\n\n"
        "Цей бот показує інформацію про наявність повітряної тривоги "
        "в місті Запоріжжя.\n\n"
        f"{status_text}\n"
        f"📡 Дані API: {updated_str}"
    )

    await message.answer(text, reply_markup=get_status_keyboard())


# -------------------- КНОПКА --------------------

@dp.callback_query(F.data == "refresh_status")
async def refresh_status_handler(callback: CallbackQuery):

    # ✅ одразу відповідаємо Telegram
    await callback.answer()

    # 🔄 міняємо кнопку на "Оновлюю..."
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_loading_keyboard()
        )
    except:
        pass

    # отримуємо статус (з кешем)
    is_alert, updated_at = await get_current_status()
    updated_str = updated_at.strftime("%H:%M:%S")
    current_time = datetime.datetime.now().strftime("%H:%M:%S")

    if is_alert:
        status_text = "🚨 Зараз активна повітряна тривога!"
    else:
        status_text = "✅ Повітряної тривоги немає"

    text = (
        "ℹ️ Інформація про повітряну тривогу в місті Запоріжжя\n\n"
        f"{status_text}\n"
        f"📡 Дані API: {updated_str}\n"
        f"🕒 Ви оновили: {current_time}"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_status_keyboard()
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


# -------------------- КОМАНДИ --------------------

@dp.message(Command("ping"))
async def ping_handler(message: Message):
    await message.answer("🏓 Pong!")


# -------------------- АВТОПЕРЕВІРКА --------------------

async def check_alert():
    global last_status

    while True:
        try:
            is_alert, updated_at = await get_current_status()

            if last_status is None:
                last_status = is_alert

            if is_alert != last_status:
                last_status = is_alert

                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                updated_str = updated_at.strftime("%H:%M:%S")

                if is_alert:
                    text = (
                        f"🚨 Повітряна тривога!\n"
                        f"🕒 {current_time}\n"
                        f"📡 Дані API: {updated_str}"
                    )
                else:
                    text = (
                        f"✅ Відбій повітряної тривоги\n"
                        f"🕒 {current_time}\n"
                        f"📡 Дані API: {updated_str}"
                    )

                for user_id in subscribers.copy():
                    try:
                        await bot.send_message(user_id, text)
                    except:
                        subscribers.remove(user_id)
                        save_subscribers()

        except Exception as e:
            print("❌ Помилка:", e)

        await asyncio.sleep(CHECK_INTERVAL)


# -------------------- ЗАПУСК --------------------

async def main():
    asyncio.create_task(check_alert())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
