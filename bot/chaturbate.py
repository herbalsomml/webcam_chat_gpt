from datetime import datetime, timezone, timedelta
from telegram import Update, InputMediaPhoto
from telegram.ext import CallbackContext
import matplotlib.pyplot as plt
import requests
from constants import STAT_URL, TOP_URL
from telegram.constants import ParseMode


def parse_time(time_str):
    time_str = time_str.rstrip('Z')
    if '.' in time_str:
        time_str = time_str[:26]

    return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)


def make_diagram(p1, p2, p3, p4, online, is_users=False):
    percentages = [p1, p2, p3, p4]
    labels = ['Девушки', 'Пары', 'Парни', 'Транс']
    colors = ['#F7B5CA','#B5CFB7','#92C7CF','#FDFFAB']

    plt.figure(figsize=(8, 6))
    plt.pie(percentages, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.axis('equal')
    plt.legend(labels, loc='upper right')
    if not is_users:
        plt.title(f'Моделей онлайн: {online}', fontsize=16)
        plt.savefig('models_circle.png')
    else:
        plt.title(f'Мемберов онлайн: {online}', fontsize=16)
        plt.savefig('users_circle.png')
    
    plt.close()


async def get_activity():
    stats = []
    current_time = datetime.now(timezone.utc)
    users_max = 0
    models_max = 0
    users_min = 8000000
    models_min = 8000000
    time_users_max = None
    time_models_max = None
    time_users_min = None
    time_models_min = None
    
    try:
        response = requests.get(STAT_URL)
    except Exception as e:
        print(e)
        return None
    
    if response.status_code != 200:
        return None
    
    for i in response.json():
        time = i["time"]
        time = parse_time(time)

        if current_time - time < timedelta(days=1):
            stats.append(i)

    stat_len = len(stats)
    last_stat = stats[stat_len-1]
    now_models = last_stat["stats"]["all"]["bc"]
    now_users = last_stat["stats"]["all"]["vc"]
    female_p = last_stat["stats"]["f"]["pct_b"]
    users_female_p = last_stat["stats"]["f"]["pct_v"]
    couple_p = last_stat["stats"]["c"]["pct_b"]
    users_couple_p = last_stat["stats"]["c"]["pct_v"]
    male_p = last_stat["stats"]["m"]["pct_b"]
    users_male_p = last_stat["stats"]["m"]["pct_v"]
    trans_p = last_stat["stats"]["s"]["pct_b"]
    users_trans_p = last_stat["stats"]["s"]["pct_v"]

    make_diagram(female_p, couple_p, male_p, trans_p, now_models)
    make_diagram(users_female_p, users_couple_p, users_male_p, users_trans_p, now_users, is_users=True)

    for i in stats:
        time_str = i["time"].replace('Z', '')
        time_str = time_str[:26]
        timee = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%f').strftime('%H:%M')
        if i["stats"]["all"]["bc"] > models_max:
            models_max = i["stats"]["all"]["bc"]
            time_models_max = timee


        if i["stats"]["all"]["bc"] < models_min:
            models_min = i["stats"]["all"]["bc"]
            time_models_min = timee

        if i["stats"]["all"]["vc"] > users_max:
            users_max = i["stats"]["all"]["vc"]
            time_users_max = timee
            
        if i["stats"]["all"]["vc"] < users_min:
            users_min = i["stats"]["all"]["vc"]
            time_users_min = timee
    
    return f"<b><u>Активность Chaturbate сейчас:</u></b>\n\n⛏️ <b>Моделей онлайн:</b><code> {now_models}</code>\n👴🏻<b> Мемберов онлайн: </b><code>{now_users}</code>\n\n<b><u>За сутки:</u></b>\n\n🔼 <b>Макс. моделей:</b><code> {models_max}</code><i> в {time_models_max}</i>\n🔽<b> Мин. моделей:</b> <code>{models_min}</code><i> в {time_models_min}</i>\n\n🔼<b> Макс. мемберов:</b> <code>{users_max}</code><i> в {time_users_max}</i>\n🔽 <b>Мин. мемберов: </b><code>{users_min}</code><i> в {time_users_min}</i>"


async def get_activity_handler(update: Update):
    stat = await get_activity()
    photos = ['models_circle.png', 'users_circle.png']
    media = []
    for i, photo in enumerate(photos):
        if i == 0:
            media.append(InputMediaPhoto(open(photo, 'rb'), caption=stat, parse_mode=ParseMode.HTML))
        else:
            media.append(InputMediaPhoto(open(photo, 'rb')))

    if stat:
        await update.message.reply_media_group(media=media)


async def get_top_10_models():
    try:
        response = requests.get(TOP_URL)
    except Exception as e:
        print(e)
        return None
    
    if response.status_code != 200:
        return None
    
    models = []
    
    it = 0
    for i in response.json():
        if it < 10:
            titul = ""
            if it == 0:
                titul = "🥇"
            if it == 1:
                titul = "🥈"
            if it == 2:
                titul = "🥉"

            model_info = (titul, i['username'], i['chat_room_url_revshare'], i['num_users'], i['seconds_online'])
            models.append(model_info)
            it += 1
        else:
            break

    text = "<b><u>📶 Топ-10 моделей в листинге:</u></b>\n\n"

    for model in models:
        titul, username, link, views, online = model
        text += f"<b><a href='{link}'>{titul} {username}</a></b> - 👥 {views} | 🕒 {round(online/60, 1)} мин.\n"
    

    return text


async def get_top_10_models_handler(update: Update):
    top = await get_top_10_models()

    if top:
        await update.message.reply_text(top, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

