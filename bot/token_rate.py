import requests
import re
from constants import RATE_URL
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
import config
from utils import reply_text

RATE_API_URL = "https://chaturbate-tokens.com/api/rate/"
def get_rate():
    try:
        response = requests.get(RATE_API_URL)
        response.raise_for_status()
        data = response.json()
        return data.get("rate_25"), data.get("rate_50"), data.get("rate_100"), data.get("rate_250"), data.get("rate_500")
    except Exception as e:
        return 0, 0, 0, 0, 0


def calculate_rates() -> dict:
    r25, r50, r100, r250, r500 = get_rate()
    return {
        25: r25,
        50: r50,
        100: r100,
        250: r250,
        500: r500,
    }


def get_rate_for_amount(rates: dict, amount: float) -> float:
    for threshold in sorted(rates.keys(), reverse=True):
        if amount >= threshold:
            return rates[threshold]
    return rates[max(rates.keys())]

def create_rates_keyboard(rates, rubles, small=False):
    if rubles > 0 and not small:
        keyboard = [
            [InlineKeyboardButton(f'🇷🇺 {rubles} RUB', url="https://t.me/wc_world_owner")]
        ]
        return InlineKeyboardMarkup(keyboard)
    elif small:
        keyboard = [
            [InlineKeyboardButton(f'от {rates[25]} до {rates[500]} RUB', url="https://t.me/wc_world_owner")]
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

    our_text = f'\n\n<b><a href="https://t.me/wc_world_owner">🔥 ВЕБКАМ WORLD</a> выведет на карту:</b>'
    rates = calculate_rates()
    exchange_rate = get_rate_for_amount(rates, dollar_value)
    rubles = int(dollar_value * exchange_rate)

    keyboard = create_rates_keyboard(rates, rubles)
    if dollar_value < 25:
        our_text = f'\n\n<b>🔥 Курс обменника <a href="https://t.me/wc_world_owner">ВЕБКАМ WORLD:</a></b>'
        keyboard = create_rates_keyboard(rates, rubles, small=True)
        
    text = (
        f"<b>-- 1 USD --</b>\n<i>🇪🇺 {euro_rate} EUR\n🇷🇺 {ruble_rate} RUB</i>\n\n"
        f"<b>-- 1 TOKEN --</b>\n<i>🇺🇸 0.05 USD\n🇪🇺 {token_eur} EUR\n🇷🇺 {token_rub} RUB</i>"
    )

    if number > 0:
        text += f"\n\n<b>-- {number} TK. --</b>\n🇺🇸 {dollar_value} USD\n🇪🇺 {round(dollar_value * euro_rate, 2)} EUR\n🇷🇺 {round(dollar_value * ruble_rate, 2)} RUB"

    text = text + our_text
    return text, keyboard


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
    await reply_text(update, rate_text, reply_markup=reply_markup)
