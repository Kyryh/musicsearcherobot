import logging

from telegram import (
    Update,
    MessageEntity,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultAudio,
    InputMediaAudio,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    InlineQueryHandler,
    ChosenInlineResultHandler
)

import urllib3
from yt_dlp import YoutubeDL, DownloadError
from os import getenv, remove
import typing

__import__("dotenv").load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TOKEN = getenv("TOKEN")
OWNER_USER_ID = getenv("OWNER_USER_ID")

YTDL_OPTIONS = {
    "outtmpl": "temp.%(ext)s",
    "format": "bestaudio",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a"
        }
    ],
    "format_sort": ["filesize:50M"],
    "max_filesize": 50_000_000
}



def first_n_elements(g: typing.Iterator, n: int):
    for i in range(n):
        yield next(g)

def parse_duration(duration: str):
    if duration is None:
        return None
    mult = 1
    seconds = 0
    split_duration = duration.split(":")[::-1]
    for s in split_duration:
        seconds += int(s)*mult
        mult *= 60
    return seconds


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("p")

async def handle_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for url in update.effective_message.parse_entities([MessageEntity.URL, MessageEntity.TEXT_LINK]).values():
        if "spotify.link" in url or "open.spotify.com" in url:
            # TODO
            pass
        else:
            await send_song_private(update.effective_chat, url)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_chat.send_message(
        "Searching songs..."
    )
    search_results = search_songs(update.effective_message.text, '1,2,3,4,5')
    await msg.delete()
    await update.effective_chat.send_message(
        "Results:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"{song['title']} by {song['performer']} ({song['duration']})", callback_data=song["id"])
                ] for song in search_results
            ] 
        )
    )

async def send_song_private(chat: Chat, url: str):
    msg = await chat.send_message(
        "Downloading..."
    )
    try:
        info = download_song(url)
        await msg.delete()
        msg = await chat.send_message(
            "Uploading..."
        )
        await chat.send_audio(
            audio="temp.m4a",
            performer=info["performer"],
            title=info["title"],
            duration=info["duration"],
            thumbnail=urllib3.request("GET", info["thumbnail"]).data if info["thumbnail"] else None
        )
        await msg.delete()
        remove("temp.m4a")
    except Exception as e:
        if msg is not None:
            await msg.delete()
        await chat.send_message(f"ERROR: {e}")

async def download_song_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.effective_message.delete()
    await send_song_private(update.effective_chat, update.callback_query.data)

def download_song(url: str):
    with YoutubeDL(YTDL_OPTIONS) as ydl:
        info = None
        try:
            info = ydl.extract_info(url)
        except DownloadError as e:
            if "Requested format is not available." in e.msg:
                pass
            raise e
        if info is None:
            raise Exception("Unsupported website")
        song_info = info["entries"][0] if "entries" in info else info

        if song_info["requested_downloads"][0].get("filesize_approx", 0) > 50_000_000:
            raise Exception("Filesize too large")
    
    return {
        "performer": song_info.get("artist") or song_info.get("uploader"),
        "title": song_info.get("track") or song_info.get("title"),
        "duration": song_info.get("duration"),
        "thumbnail": song_info["thumbnails"][0]["url"] if "thumbnails" in song_info else song_info.get("thumbnail")
    }

def search_songs(query: str, playlist_items: str):
    with YoutubeDL(YTDL_OPTIONS | {'playlist_items': playlist_items, "extract_flat": True}) as ydl:

        info_songs = ydl.extract_info(f"https://music.youtube.com/search?q={query}#songs", download = False)
        info_videos = ydl.extract_info(f"https://music.youtube.com/search?q={query}#videos", download = False)

        return [
            {
                "id": song["id"],
                "performer": ''.join(song.get("authors")),
                "title": song.get("title"),
                "duration": song.get("video_duration"),
                "thumbnail": song["thumbnails"][0]["url"] if "thumbnails" in song else song.get("thumbnail")
            }
             for song in [item for sublist in zip(info_songs["entries"], info_videos["entries"]) for item in sublist] if song.get("filesize", 0) < 50_000_000
        ]
    

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query

    if not query:
        return
    
    results = [
        InlineQueryResultAudio(
            id=song['id'],
            audio_url="https://www.myinstants.com/media/sounds/1sec_silence.mp3",
            title=song['title'],
            performer=song["performer"],
            audio_duration=parse_duration(song["duration"]),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Downloading song, please wait...", callback_data="ignore")
                    ]
                ]
            )
        ) for song in search_songs(query, '1,2,3,4,5')
    ]


    await update.inline_query.answer(results, cache_time=0)

async def inline_query_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_message_id = update.chosen_inline_result.inline_message_id
    video_id = update.chosen_inline_result.result_id
    song_info = download_song(video_id)



    audio = (await context.bot.send_audio(
        chat_id=OWNER_USER_ID,
        audio="temp.m4a",
        performer=song_info["performer"],
        title=song_info["title"],
        duration=song_info["duration"],
        thumbnail=urllib3.request("GET", song_info["thumbnail"]).data if song_info["thumbnail"] else None
    )).audio

    await context.bot.edit_message_media(
        media=InputMediaAudio(
            media=audio
        ),
        inline_message_id=inline_message_id,
    )

    remove("temp.m4a")




def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Entity(MessageEntity.URL) | filters.Entity(MessageEntity.TEXT_LINK), handle_links))
    application.add_handler(MessageHandler(filters.TEXT, handle_messages))

    application.add_handler(CallbackQueryHandler(download_song_button))
    application.add_handler(InlineQueryHandler(inline_query))

    application.add_handler(ChosenInlineResultHandler(inline_query_edit))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()