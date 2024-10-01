import asyncio
import html
import io
import json
import logging
import re
import sqlite3
import sys
import traceback
from datetime import datetime

from utils import reply_text, is_admin

import requests
from chaturbate import get_top_10_models_handler, get_activity_handler
from pprint import pprint
from datetime import datetime
from utils import reply_text, get_chat_admins_handle


from moderation import mute_user, unmute_user, ban_user, unban_user, warn_user, unwarn_user

from utils import notify_admins
import database
import openai_utils
import telegram
from constants import HERBAL, RATE_API_KEY, RATE_URL, STAT_URL, TOP_URL
from telegram import (BotCommand, ChatMember, ChatPermissions,
                      InlineKeyboardButton, InlineKeyboardMarkup, Update, User)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (AIORateLimiter, Application, ApplicationBuilder,
                          CallbackContext, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler,
                          filters)

import config
from utils import get_chat_info, notify_herbal, get_webcam_mirrors, get_rules, get_chat_info
from token_rate import token_rate_handle

db = database.Database()
logger = logging.getLogger(__name__)

user_semaphores = {}
user_tasks = {}


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name= user.last_name
        )
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)

    if user.id not in user_semaphores:
        user_semaphores[user.id] = asyncio.Semaphore(1)

    if db.get_user_attribute(user.id, "current_model") is None:
        db.set_user_attribute(user.id, "current_model", config.models["available_text_models"][0])

    n_used_tokens = db.get_user_attribute(user.id, "n_used_tokens")
    if isinstance(n_used_tokens, int) or isinstance(n_used_tokens, float):
        new_n_used_tokens = {
            "gpt-4": {
                "n_input_tokens": 0,
                "n_output_tokens": n_used_tokens
            }
        }
        db.set_user_attribute(user.id, "n_used_tokens", new_n_used_tokens)

    if db.get_user_attribute(user.id, "n_transcribed_seconds") is None:
        db.set_user_attribute(user.id, "n_transcribed_seconds", 0.0)

    if db.get_user_attribute(user.id, "n_generated_images") is None:
        db.set_user_attribute(user.id, "n_generated_images", 0)


async def is_bot_mentioned(update: Update, context: CallbackContext, message=None):
     try:
        if message is None:
            message = update.message

        if type(message) == str:
            for prefix in config.prefix:
                if message.lower().startswith(prefix.lower()):
                    return True  

        if message.chat.type == "private":
            if config.allow_private:
                return True
            else:
                return False

        if message.text is not None and ("@" + context.bot.username) in message.text:
            return True

        
        for prefix in config.prefix:
            if message.text is not None and message.text.lower().startswith(prefix.lower()):
                return True

        if message.reply_to_message is not None:
            if message.reply_to_message.from_user.id == context.bot.id:
                return True
     except Exception as e:
         return False
     else:
         return False


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    await get_chat_info(update, context)


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await get_chat_info(update, context)


async def help_group_chat_handle(update: Update, context: CallbackContext):
     await register_user_if_not_exists(update, context, update.message.from_user)
     user_id = update.message.from_user.id
     db.set_user_attribute(user_id, "last_interaction", datetime.now())

     await get_chat_info(update, context)


async def retry_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await reply_text(update, "No message to retry 🤷‍♂️")
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(user_id, dialog_messages, dialog_id=None)

    await message_handle(update, context, message=last_dialog_message["user"], use_new_dialog_timeout=False)


async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True):
    if update.edited_message is not None:
        return

    _message = message or update.message.text
    
    if _message.lower().startswith("курс"):
            await token_rate_handle(update, context)
            return
    
    await notify_herbal(message, update, context)
    
    if not await is_bot_mentioned(update, context, message):
        return

    _message = _message.replace("@" + context.bot.username, "").strip()

    for prefix in config.prefix:
        _message = _message.lower().replace(prefix.lower(), "").strip()


    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    message = update.message

    current_model = "gpt-3.5-turbo"

    for prefix in config.prefix:
        if _message is None:
            return

        if _message.lower().startswith("курс"):
            await token_rate_handle(update, context)
            return
        
        if _message.lower().startswith("админы"):
            await get_chat_admins_handle(update)
            return
        
        if _message.lower().startswith("актив"):
            await get_activity_handler(update)
            return
        
        if _message.lower().startswith("топы"):
            await get_top_10_models_handler(update)
            return
        
        if _message.lower().startswith("зеркала"):
            await get_webcam_mirrors(update, context)
            return
        
        if _message.lower().startswith("правила"):
            await get_rules(update, context)
            return
        
        if _message.lower().startswith("о чате"):
            await get_chat_info(update, context)
            return
        
        if _message.lower().startswith("инфа"):
            if await is_admin(update):
                await reply_text(update, f'<b>ID 1:</b> <code>{update.message.chat.id}</code>\n<b>ID 2:</b> <code>{update.message.from_user.id}</code>')
                return


    async def message_handle_fn():
        if use_new_dialog_timeout:
            if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
                db.start_new_dialog(user_id)
        db.set_user_attribute(user_id, "last_interaction", datetime.now())

        n_input_tokens, n_output_tokens = 0, 0

        try:
            placeholder_message = await reply_text(update, '...')

            await update.message.chat.send_action(action="typing")

            if _message is None or len(_message) == 0:
                 await reply_text(update, "🥲 Ты отправил(а) <b>пустое сообщение</b>. Попробуй еще раз!")
                 return

            dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            parse_mode = {
                "html": ParseMode.HTML,
                "markdown": ParseMode.MARKDOWN
            }[config.chat_modes[chat_mode]["parse_mode"]]

            chatgpt_instance = openai_utils.ChatGPT(model=current_model)
            if config.enable_message_streaming:
                gen = chatgpt_instance.send_message_stream(_message, dialog_messages=dialog_messages, chat_mode=chat_mode)
            else:
                answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = await chatgpt_instance.send_message(
                    _message,
                    dialog_messages=dialog_messages,
                    chat_mode=chat_mode
                )

                async def fake_gen():
                    yield "finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

                gen = fake_gen()

            prev_answer = ""
            
            async for gen_item in gen:
                status, answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = gen_item

                answer = answer[:4096]
                    
                if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
                    continue

                try:
                    await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id, parse_mode=parse_mode)
                except telegram.error.BadRequest as e:
                    if str(e).startswith("Message is not modified"):
                        continue
                    else:
                        await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id)

                await asyncio.sleep(0.01)
                
                prev_answer = answer
            
            new_dialog_message = {"user": [{"type": "text", "text": _message}], "bot": answer, "date": datetime.now()}

            db.set_dialog_messages(
                user_id,
                db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
                dialog_id=None
            )

            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)

        except asyncio.CancelledError:
            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)
            raise

        except Exception as e:
            error_text = f"<b>Что-то не так, я не могу ответить...</b>\n\n{e}"
            logger.error(error_text)
            await reply_text(update, error_text)
            return

        if n_first_dialog_messages_removed > 0:
            if n_first_dialog_messages_removed == 1:
                text = "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog"
            else:
                text = f"✍️ <i>Note:</i> Your current dialog is too long, so <b>{n_first_dialog_messages_removed} first messages</b> were removed from the context.\n Send /new command to start new dialog"

    async with user_semaphores[user_id]:
        if update.message.photo is not None and len(update.message.photo) > 0:
            return
        else:
            task = asyncio.create_task(
                message_handle_fn()
            )            

        user_tasks[user_id] = task

        try:
            await task
        except asyncio.CancelledError:
            await reply_text(update, "✅ Отменено")
        else:
            pass
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]


async def speech_to_text(update: Update, context: CallbackContext, audio_file, file_name: str, duration: int):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    audio_file = await context.bot.get_file(audio_file.file_id)
    
    buf = io.BytesIO()
    await audio_file.download_to_memory(buf)
    buf.name = file_name
    buf.seek(0)

    transcribed_text = await openai_utils.transcribe_audio(buf)
    text = f"{transcribed_text}"
    await reply_text(update, f'🎤: <i>{text}</i>')

    db.set_user_attribute(user_id, "n_transcribed_seconds", duration + db.get_user_attribute(user_id, "n_transcribed_seconds"))

    await message_handle(update, context, message=transcribed_text)


async def video_note_message_handle(update: Update, context: CallbackContext):
    video_note = update.message.video_note
    await speech_to_text(update, context, video_note, "video_note.mp4", video_note.duration)


async def voice_message_handle(update: Update, context: CallbackContext):
    voice = update.message.voice
    await speech_to_text(update, context, voice, "voice.oga", voice.duration)


async def is_previous_message_not_answered_yet(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    if user_semaphores[user_id].locked():
        return True
    else:
        return False


async def error_handle(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )
    except:
        pass


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("/help", "Что я умею"),
    ])


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    user_filter = filters.ALL
    if len(config.allowed_telegram_usernames) > 0:
        usernames = [x for x in config.allowed_telegram_usernames if isinstance(x, str)]
        any_ids = [x for x in config.allowed_telegram_usernames if isinstance(x, int)]
        user_ids = [x for x in any_ids if x > 0]
        group_ids = [x for x in any_ids if x < 0]
        user_filter = filters.User(username=usernames) | filters.User(user_id=user_ids) | filters.Chat(chat_id=group_ids)

    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))

    application.add_handler(MessageHandler(filters.VOICE & user_filter, voice_message_handle))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & user_filter, video_note_message_handle))

    application.add_handler(CommandHandler('ban', ban_user))
    application.add_handler(CommandHandler('unban', unban_user))
    application.add_handler(CommandHandler('mute', mute_user))
    application.add_handler(CommandHandler('unmute', unmute_user))
    application.add_handler(CommandHandler('warn', warn_user))
    application.add_handler(CommandHandler('unwarn', unwarn_user))
    application.add_handler(CommandHandler('admins', notify_admins))
    application.add_handler(CommandHandler('rules', get_rules))

    application.add_error_handler(error_handle)

    application.run_polling()


if __name__ == "__main__":
    run_bot()
