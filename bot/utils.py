from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from constants import HERBAL
import config


async def get_chat_admins(update: Update):
    chat = update.effective_chat
    admins = await chat.get_administrators()
    return [admin.user for admin in admins]


async def get_chat_admins_handle(update: Update):
    admins = await get_chat_admins(update)
    text = '<b><u>🛡️ Вот список администраторов нашего чата:\n\n</u></b>'

    for admin in admins:
        if admin.username is None and admin.id != config.hidden_owner_id:
            text += f'<a href="tg://user?id={admin.id}">{admin.first_name}</a>\n'
        elif admin.id != config.hidden_owner_id:
            text += f'<a href="https://t.me/{admin.username}">{admin.full_name}</a>\n'

    text += f'\n<i>По вопросам рекламы и разблокировки: @{config.main_admin}</i>'
    await reply_text(update, text)


async def send_message(context: CallbackContext, receiver, text, parse_mode=ParseMode.HTML):
    try:
        await context.bot.send_message(receiver, text, parse_mode=parse_mode)
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")


async def send_message_to_admins(update: Update, context: CallbackContext, text: str):
    admins = await get_chat_admins(update)
    for admin in admins:
        await send_message(context, admin.id, text)


async def reply_text(update: Update, text: str, reply_markup=None):
    return await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def is_admin(update: Update):
    admins_id = []
    admins = await get_chat_admins(update)

    for admin in admins:
        admins_id.append(admin.id)

    if update.message.from_user.id in admins_id:
        return True
    
    for id in config.chat_id
        if update.message.from_user.id == id:
            return True

    return False

async def notify_herbal(message, update: Update, context: CallbackContext):
    text = message if isinstance(message, str) else update.message.text

    if text:
        lower_text = text.lower()
        for name in HERBAL:
            if name in lower_text:
                user = update.message.from_user
                await send_message(
                    context,
                    config.hidden_owner_id,
                    f"<b>Тебя упомянул @{user.username} | {user.full_name}</b>\n"
                    f"Ссылка: https://t.me/c/{update.effective_chat.id,}/{update.message.message_id}\n\n"
                    f"Текст:\n<code>{text}</code>"
                )
                break


async def notify_admins(update: Update, context: CallbackContext):
    await reply_text(update, "<b>Админы призваны!</b>")
    user = update.message.from_user
    msg_id = update.message.message_id

    await send_message_to_admins(update, context, f"<b>@{user.username} | {user.full_name} призывает админов </b>\nСсылка: https://t.me/c/{update.effective_chat.id}/{msg_id}")


async def forward_message(context: CallbackContext, update: Update, message_id: int):
    await context.bot.forward_message(
        chat_id=update.message.chat_id,
        from_chat_id=config.info_channel,
        message_id=message_id
    )


async def get_webcam_mirrors(update: Update, context: CallbackContext):
    await forward_message(context, update, config.mirrors_id)


async def get_chat_info(update: Update, context: CallbackContext):
    await forward_message(context, update, config.info_id)


async def get_rules(update: Update, context: CallbackContext):
    await forward_message(context, update, config.rules_id)
