import sqlite3
from datetime import timedelta

from telegram import ChatPermissions, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from utils import is_admin
from telegram.constants import ChatAction, ParseMode
from utils import reply_text
from datetime import datetime


def create_db():
    conn = sqlite3.connect('warnings.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS warnings (
        user_id INTEGER PRIMARY KEY,
        warnings_count INTEGER DEFAULT 0
    )
    ''')
    conn.commit()

    return cursor, conn

async def get_user_by_arg(arg, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if arg.isdigit():
        try:
            return await context.bot.get_chat(int(arg))
        except:
            await reply_text(update, '<b>Не удалось найти этого юзера</b>')
            return None
    await update.message.reply_text("<b>⚠️ Некорректный аргумент пользователя</b>", parse_mode=ParseMode.HTML)
    return None

async def handle_restriction(user, update: Update, context: ContextTypes.DEFAULT_TYPE, mute=True, duration=None):
    bot_info = await context.bot.get_me()
    if user.id == bot_info.id:
        await update.message.reply_text("<b>😠 Я бот, я бот!</b>", parse_mode=ParseMode.HTML)
        return

    permissions = ChatPermissions(
        can_send_messages=not mute,
        can_send_media_messages=not mute,
        can_send_polls=not mute,
        can_send_other_messages=not mute,
        can_add_web_page_previews=not mute,
    )

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            permissions=permissions,
            until_date=datetime.now() + duration if mute else None
        )
        status = "не может" if mute else "может"
        await update.message.reply_text(
            f"<b>🗨 Пользователь {user.full_name} теперь {status} отправлять сообщения</b>",
            parse_mode=ParseMode.HTML
        )
    except BadRequest as e:
        await handle_bad_request(e, update)

async def handle_bad_request(e, update: Update):
    if "not found" in str(e):
        await update.message.reply_text("<b>⚠️ Пользователь не найден</b>", parse_mode=ParseMode.HTML)
    elif "restrict" in str(e):
        await update.message.reply_text("<b>⚠️ Не удалось выполнить команду. Возможно, у меня недостаточно прав</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>⚠️ Произошла ошибка во время выполнения команды</b>", parse_mode=ParseMode.HTML)

############
### Муты ###
############

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update) is False:
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return

    mute_duration = get_mute_duration(update, context)
    user_to_mute = await get_user_from_context(update, context)

    if user_to_mute:
        await handle_restriction(user_to_mute, update, context, mute=True, duration=mute_duration)

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return

    user_to_unmute = await get_user_from_context(update, context)

    if user_to_unmute:
        await handle_restriction(user_to_unmute, update, context, mute=False)

def get_mute_duration(update, context):
    if len(context.args) == 1 and context.args[0].isdigit() and update.message.reply_to_message:
        return timedelta(minutes=int(context.args[0]))
    if len(context.args) == 2 and context.args[1].isdigit():
        return timedelta(minutes=int(context.args[1]))
    return timedelta(hours=6)

async def get_user_from_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    elif len(context.args) >= 1:
        return await get_user_by_arg(context.args[0], update, context)
    
    await update.message.reply_text(
        "<b>⚠️ Используйте /mute или /unmute [User ID] или как ответ на сообщение</b>", 
        parse_mode=ParseMode.HTML
    )
    return None

#############
### Варны ###
#############


async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor, conn = create_db()
    bot_info = await context.bot.get_me()

    if not await is_admin(update):
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return


    if update.message.reply_to_message:
        user_to_warn = update.message.reply_to_message.from_user
    elif len(context.args) == 1:
        arg = context.args[0]
        if arg.isdigit():
            user_id = int(arg)
            user_to_warn = await context.bot.get_chat(user_id)
        else:
            await update.message.reply_text("<b>⚠️ Некорректный аргумент. Используйте ID пользователя</b>", parse_mode=ParseMode.HTML,)
            return
    else:
        await update.message.reply_text("<b>⚠️ Используйте /warn как ответ на сообщение или укажите ID пользователя</b>", parse_mode=ParseMode.HTML,)
        return

    try:
        user_id = user_to_warn.id
        if user_id == bot_info.id:
            await update.message.reply_text("<b>😠 Себя заварнь, а?</b>", parse_mode=ParseMode.HTML,)
            return
        user_name = user_to_warn.full_name

        cursor.execute('SELECT warnings_count FROM warnings WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()

        if result:
            warnings_count = result[0] + 1
            cursor.execute('UPDATE warnings SET warnings_count = ? WHERE user_id = ?', (warnings_count, user_id))
        else:
            warnings_count = 1
            cursor.execute('INSERT INTO warnings (user_id, warnings_count) VALUES (?, ?)', (user_id, warnings_count))

        conn.commit()

        if warnings_count >= 3:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user_id)
            await update.message.reply_text(f"<b>🤛 Пользователь {user_name} был забанен за 3 предупреждения</b>", parse_mode=ParseMode.HTML,)
        else:
            await update.message.reply_text(f"<b>🚽 Пользователь {user_name} получил предупреждение ({warnings_count}/3)</b>", parse_mode=ParseMode.HTML,)

    except BadRequest as e:
        if "not found" in str(e):
            await update.message.reply_text("<b>⚠️ Пользователь не найден</b>", parse_mode=ParseMode.HTML,)
        elif "ban" in str(e):
            await update.message.reply_text("<b>⚠️ Не удалось забанить пользователя. Возможно, у меня недостаточно прав</b>", parse_mode=ParseMode.HTML,)
        else:
            await update.message.reply_text("<b>⚠️ Произошла ошибка при попытке варнить пользователя</b>", parse_mode=ParseMode.HTML,)


async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor, conn = create_db()
    bot_info = await context.bot.get_me()
    if not await is_admin(update):
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return
    if update.message.reply_to_message:
        user_to_unwarn = update.message.reply_to_message.from_user
    elif len(context.args) == 1:
        arg = context.args[0]
        if arg.isdigit():
            user_id = int(arg)
            user_to_unwarn = await context.bot.get_chat(user_id)
        else:
            await update.message.reply_text("<b>⚠️ Некорректный аргумент. Используйте ID пользователя</b>", parse_mode=ParseMode.HTML,)
            return
    else:
        await update.message.reply_text("<b>⚠️ Используйте /unwarn как ответ на сообщение или укажите ID пользователя</b>", parse_mode=ParseMode.HTML,)
        return

    try:
        user_id = user_to_unwarn.id
        if user_id == bot_info.id:
            await update.message.reply_text("<b>😠 Да я блин бот у меня варнов нема</b>", parse_mode=ParseMode.HTML,)
            return
        user_name = user_to_unwarn.full_name

        cursor.execute('SELECT warnings_count FROM warnings WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text(f"<b>🤔 У пользователя {user_name} нет варнов</b>", parse_mode=ParseMode.HTML,)
            return

        warnings_count = result[0]

        if len(context.args) == 2 and context.args[1].isdigit():
            unwarn_count = int(context.args[1])
            if unwarn_count >= warnings_count:
                cursor.execute('DELETE FROM warnings WHERE user_id = ?', (user_id,))
                await update.message.reply_text(f"<b>✅ Все варны пользователя {user_name} были сняты</b>", parse_mode=ParseMode.HTML,)
            else:
                new_warnings_count = warnings_count - unwarn_count
                cursor.execute('UPDATE warnings SET warnings_count = ? WHERE user_id = ?', (new_warnings_count, user_id))
                await update.message.reply_text(f"<b>✅ У пользователя {user_name} снято {unwarn_count} варна(ов)</b>\nТекущий счет варнов: {new_warnings_count}", parse_mode=ParseMode.HTML,)
        else:
            cursor.execute('DELETE FROM warnings WHERE user_id = ?', (user_id,))
            await update.message.reply_text(f"<b>✅ Все варны пользователя {user_name} были сняты</b>", parse_mode=ParseMode.HTML,)

        conn.commit()

    except BadRequest as e:
        if "not found" in str(e):
            await update.message.reply_text("<b>⚠️ Пользователь не найден</b>", parse_mode=ParseMode.HTML,)
        elif "ban" in str(e):
            await update.message.reply_text("<b>⚠️ Не удалось снять варны у пользователя. Возможно, у меня недостаточно прав</b>", parse_mode=ParseMode.HTML,)
        else:
            await update.message.reply_text("<b>⚠️ Произошла ошибка при попытке снять варны у пользователя</b>", parse_mode=ParseMode.HTML,)


############
### Баны ###
############

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_info = await context.bot.get_me()
    if not await is_admin(update):
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return
    if len(context.args) == 0 and update.message.reply_to_message:
        user_to_ban = update.message.reply_to_message.from_user
    elif len(context.args) == 1:
        arg = context.args[0]
        
        if arg.isdigit():
            user_id = int(arg)
            user_to_ban = await context.bot.get_chat(user_id)
        elif arg.startswith('@'):
            username = arg[1:]
            user_to_ban = await context.bot.get_chat(username)
        else:
            await update.message.reply_text("<b>⚠️ Некорректный аргумент. Используйте ID пользователя</b>", parse_mode=ParseMode.HTML,)
            return
    else:
        await update.message.reply_text("<b>⚠️ Используйте /ban [User ID] или как ответ на сообщение</b>", parse_mode=ParseMode.HTML,)
        return

    try:
        if user_to_ban.id == bot_info.id:
            await update.message.reply_text("<b>😠 Ну и кого ты банишь?</b>", parse_mode=ParseMode.HTML,)
            return
        await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_ban.id)
        await update.message.reply_text(f"<b>🚽 Пользователь {user_to_ban.full_name} был забанен</b>", parse_mode=ParseMode.HTML,)
    except BadRequest as e:
        if "not found" in str(e):
            await update.message.reply_text("<b>⚠️ Пользователь не найден</b>", parse_mode=ParseMode.HTML,)
        elif "ban" in str(e):
            await update.message.reply_text("<b>⚠️ Не удалось забанить пользователя. Возможно, у меня недостаточно прав</b>", parse_mode=ParseMode.HTML,)
        else:
            await update.message.reply_text("<b>⚠️ Произошла ошибка при бане пользователя</b>", parse_mode=ParseMode.HTML,)


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_info = await context.bot.get_me()
    if not await is_admin(update):
        await update.message.reply_text("<b>⚠️ Кажется, ты не админ!</b>", parse_mode=ParseMode.HTML)
        return
    if len(context.args) == 0 and update.message.reply_to_message:
        user_to_unban = update.message.reply_to_message.from_user
    elif len(context.args) == 1:
        arg = context.args[0]

        if arg.isdigit():
            user_id = int(arg)
            user_to_unban = await context.bot.get_chat(user_id)

        elif arg.startswith('@'):
            username = arg[1:]
            user_to_unban = await context.bot.get_chat(username)
        else:
            await update.message.reply_text("<b>⚠️ Некорректный аргумент. Используйте ID пользователя</b>", parse_mode=ParseMode.HTML,)
            return
    else:
        await update.message.reply_text("<b>⚠️ Используйте /unban [User ID] или как ответ на сообщение</b>", parse_mode=ParseMode.HTML,)
        return

    try:
        if user_to_unban.id == bot_info.id:
            await update.message.reply_text("<b>😠 Я бот. Я не забанен. Я не могу разбанить себя</b>", parse_mode=ParseMode.HTML,)
            return
        chat_member = await context.bot.get_chat_member(chat_id=update.effective_chat.id, user_id=user_to_unban.id)

        if chat_member.status != 'kicked':
            await update.message.reply_text(f"<b>🗿 Пользователь {user_to_unban.full_name} не забанен</b>", parse_mode=ParseMode.HTML,)
            return

        await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_unban.id)
        await update.message.reply_text(f"<b>✅ Пользователь {user_to_unban.full_name} был разбанен</b>", parse_mode=ParseMode.HTML,)
    except BadRequest as e:
        if "not found" in str(e):
            await update.message.reply_text("<b>⚠️ Пользователь не найден</b>", parse_mode=ParseMode.HTML,)
        elif "unban" in str(e):
            await update.message.reply_text("<b>⚠️ Не удалось разбанить пользователя. Возможно, у меня недостаточно прав</b>", parse_mode=ParseMode.HTML,)
        else:
            await update.message.reply_text("<b>⚠️ Произошла ошибка при разбане пользователя</b>", parse_mode=ParseMode.HTML,)
