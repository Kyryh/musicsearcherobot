import logging

from telegram import (
    Update,
    MessageEntity,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultAudio,
    InlineQueryResultCachedAudio,
    InputMediaAudio,
    LinkPreviewOptions
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    InlineQueryHandler,
    ChosenInlineResultHandler,
    PicklePersistence
)

from downloader import Downloader, DownloaderContext

from os import getenv, remove
import typing

__import__("dotenv").load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TOKEN = getenv("TOKEN")
OWNER_USER_ID = getenv("OWNER_USER_ID")




class FilesizeTooLargeException(Exception):
    pass

def safely_remove(file: str):
    try:
        remove(file)
    except FileNotFoundError:
        pass

async def start(update: Update, context: DownloaderContext):
    await update.effective_message.reply_text(
        "Welcome to the bot!\n"
        "\n"
        "<b>Features</b>:\n"
        "- Searching and downloading songs based on title and/or artists\n"
        "- Searching and downloading songs in inline mode\n"
        "\n"
        "<b>Made by @Kyryh\n</b>"
        "<i>Bot source code: https://github.com/Kyryh/musicsearcherobot</i>",
        link_preview_options=LinkPreviewOptions(True),
        parse_mode="HTML"
    )

async def handle_messages(update: Update, context: DownloaderContext):
    msg = await update.effective_chat.send_message(
        "Searching songs..."
    )
    search_results = [song for song in await context.downloader.search_songs(update.effective_message.text) if song.get_duration_seconds() < 1800]
    await msg.delete()
    await update.effective_chat.send_message(
        "Results:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"{song.title} by {song.performer} ({song.get_duration()})", callback_data=song.id)
                ] for song in search_results
            ] 
        )
    )

async def send_song_private(chat: Chat, url: str, context: DownloaderContext):
    msg = await chat.send_message(
        "Downloading..."
    )
    try:
        if url in context.bot_data["cached_songs"]:
            audio = context.bot_data["cached_songs"][url]
            await chat.send_audio(
                audio=audio
            )
            await msg.delete()
            return
        info, audio = await context.downloader.download_song(url, 10)
        await msg.delete()
        msg = await chat.send_message(
            "Uploading..."
        )
        audio_message = await chat.send_audio(
            audio=audio,
            performer=info.performer,
            title=info.title,
            duration=info.get_duration_seconds(),
            thumbnail=await context.downloader.get(info.thumbnail)
        )
        
        context.bot_data["cached_songs"][url] = audio_message.audio.file_id
        await msg.delete()
    except Exception as e:
        if msg is not None:
            await msg.delete()
        await chat.send_message(f"ERROR: {repr(e)}")
        raise

async def download_song_button(update: Update, context: DownloaderContext):
    await update.callback_query.answer()
    if (update.callback_query.data == "ignore"):
        return
    
    await update.effective_message.edit_reply_markup(
        InlineKeyboardMarkup([
            button if button[0].callback_data != update.callback_query.data else (InlineKeyboardButton(f"✅ {button[0].text}", callback_data="ignore"),)
            for button in update.effective_message.reply_markup.inline_keyboard
        ])
    )
    await send_song_private(update.effective_chat, update.callback_query.data, context)


async def inline_query(update: Update, context: DownloaderContext):
    query = update.inline_query.query

    if not query:
        return
    
    
    results = [
        InlineQueryResultCachedAudio(
            id=song.id,
            audio_file_id=context.bot_data["cached_songs"][song.id]
        )
        if song.id in context.bot_data["cached_songs"] else
        InlineQueryResultAudio(
            id=song.id,
            audio_url="https://www.chosic.com/wp-content/uploads/2021/09/Elevator-music(chosic.com).mp3",
            title=song.title,
            performer=song.performer,
            audio_duration=song.get_duration_seconds(),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Downloading song, please wait...", callback_data="ignore")
                    ]
                ]
            )
        ) for song in await context.downloader.search_songs(query) if song.get_duration_seconds() < 1800
    ]

    await update.inline_query.answer(results, cache_time=3600)

async def inline_query_edit(update: Update, context: DownloaderContext):
    inline_message_id = update.chosen_inline_result.inline_message_id
    if not inline_message_id:
        return
    video_id = update.chosen_inline_result.result_id

    if video_id in context.bot_data["cached_songs"]:
        audio = context.bot_data["cached_songs"][video_id]
    else:
        info, song = await context.downloader.download_song(video_id, 10)
        if song is None:
            await context.bot.edit_message_reply_markup(
                inline_message_id=inline_message_id,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Filesize too large, can't download", callback_data="ignore")
                        ]
                    ]
                )
            )
            return
        audio = (await context.bot.send_audio(
            chat_id=OWNER_USER_ID,
            audio=song,
            performer=info.performer,
            title=info.title,
            duration=info.get_duration_seconds(),
            thumbnail=await context.downloader.get(info.thumbnail)
        )).audio
        context.bot_data["cached_songs"][video_id] = audio.file_id

    await context.bot.edit_message_media(
        media=InputMediaAudio(
            media=audio
        ),
        inline_message_id=inline_message_id,
    )


async def post_init(application: Application):
    application.bot_data.setdefault("cached_songs", {})
    application.downloader = Downloader()

def main():
    application = (
        Application
        .builder()
        .token(TOKEN)
        .persistence(PicklePersistence("persistence.pickle"))
        .post_init(post_init)
        .concurrent_updates(True)
        .write_timeout(30)
        .context_types(ContextTypes(DownloaderContext))
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT, handle_messages))

    application.add_handler(CallbackQueryHandler(download_song_button))
    application.add_handler(InlineQueryHandler(inline_query))

    application.add_handler(ChosenInlineResultHandler(inline_query_edit))


    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
