import requests
import re
from constants import RATE_URL
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
import config
from utils import reply_text


def create_rates_keyboard(dollar, euro, ruble):
    keyboard = [
        [InlineKeyboardButton(f'🇺🇸 {dollar} USD', callback_data="nothing")],
        [InlineKeyboardButton(f'🇪🇺 {euro} EUR', callback_data="nothing")],
        [InlineKeyboardButton(f'🇷🇺 {ruble} RUB', callback_data="nothing")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def fetch_rates():
    try:
        response = requests.get(RATE_URL)
        response.raise_for_status()
        data = response.json()

        euro_rate = round(data['rates'].get('EUR', 0), 2)
        ruble_rate = round(data['rates'].get('RUB', 0), 2)
        return euro_rate, ruble_rate
    except (requests.RequestException, KeyError):
        return 0, 0


async def calculate_rate(number):
    euro_rate, ruble_rate = await fetch_rates()
    
    dollar_value = int(number) / 20
    token_rub = round(0.05 * ruble_rate, 2)
    token_eur = round(0.05 * euro_rate, 4)

    text = (
        f"<b>-- 1 USD --</b>\n<i>🇪🇺 {euro_rate} EUR\n🇷🇺 {ruble_rate} RUB</i>\n\n"
        f"<b>-- 1 TOKEN --</b>\n<i>🇺🇸 0.05 USD\n🇪🇺 {token_eur} EUR\n🇷🇺 {token_rub} RUB</i>\n\n"
    )

    if number > 0:
        text += f"<b>-- {number} TK. --</b>"

    return text, create_rates_keyboard(dollar=dollar_value, euro=round(dollar_value * euro_rate, 2), ruble=round(dollar_value * ruble_rate, 2))


async def token_rate_handle(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    
    for prefix in config.prefix:
        text = text.replace(f"{prefix.lower()} ", "")
    
    match = re.match(r'курс\s+(\d+)', text)
    
    if match:
        number = int(match.group(1))
    else:
        number = 0

    rate_text, reply_markup = await calculate_rate(number)
    await reply_text(update, rate_text, reply_markup=reply_markup if number > 0 else None)
