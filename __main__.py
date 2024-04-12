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

import urllib3
from yt_dlp import YoutubeDL, DownloadError

from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

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

YTDL_OPTIONS = {
    "outtmpl": "%(id)s.%(ext)s",
    "format": "bestaudio",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a"
        }
    ],
    "format_sort": ["filesize:10M"],
    "max_filesize": 50_000_000
}

spotify_client = Spotify(auth_manager=SpotifyClientCredentials(
    getenv("SPOTIFY_CLIENT_ID"),
    getenv("SPOTIFY_CLIENT_SECRET")
))


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

def safely_remove(file: str):
    try:
        remove(file)
    except FileNotFoundError:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Welcome to the bot!\n"
        "\n"
        "<b>Features</b>:\n"
        "- Downloading songs via URL\n"
        "- Searching and downloading songs based on title and/or artists\n"
        "- Searching and downloading songs in inline mode\n"
        "\n"
        "<b>Made by @Kyryh\n</b>"
        "<i>Bot source code: https://github.com/Kyryh/musicsearcherobot</i>",
        link_preview_options=LinkPreviewOptions(True),
        parse_mode="HTML"
    )

async def handle_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for url in update.effective_message.parse_entities([MessageEntity.URL, MessageEntity.TEXT_LINK]).values():
        if "spotify.link" in url or "open.spotify.com" in url:
            msg = await update.effective_chat.send_message("Spotify link detected, searching for song on Youtube Music...")
            if "spotify.link" in url:
                url = urllib3.request("HEAD", url).url
            
            spotify_song = spotify_client.track(url)
            
            await send_song_private(update.effective_chat, f"https://music.youtube.com/search?q={spotify_song['name']} {spotify_song['artists'][0]['name']}#songs", context)

            await msg.delete()
        else:
            await send_song_private(update.effective_chat, url, context)

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

async def send_song_private(chat: Chat, url: str, context: ContextTypes.DEFAULT_TYPE):
    msg = await chat.send_message(
        "Downloading..."
    )
    try:
        if url in context.bot_data["cached_songs"]:
            audio = context.bot_data["cached_songs"][url]
            info = None
        else:
            info = download_song(url)
            audio = info["filename"]
        await msg.delete()
        msg = await chat.send_message(
            "Uploading..."
        )
        audio_message = await chat.send_audio(
            audio=audio,
            performer=info["performer"] if info else None,
            title=info["title"] if info else None,
            duration=info["duration"] if info else None,
            thumbnail=(urllib3.request("GET", info["thumbnail"]).data if info["thumbnail"] else None) if info else None,

        )
        
        context.bot_data["cached_songs"][url] = audio_message.audio
        await msg.delete()
        if isinstance(audio, str):
            safely_remove(audio)
    except Exception as e:
        if msg is not None:
            await msg.delete()
        await chat.send_message(f"ERROR: {e}")
        raise

async def download_song_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.effective_message.delete()
    await send_song_private(update.effective_chat, update.callback_query.data, context)

def download_song(url: str):
    with YoutubeDL(YTDL_OPTIONS| {'playlist_items': "1"}) as ydl:
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
        "thumbnail": song_info["thumbnails"][0]["url"] if "thumbnails" in song_info else song_info.get("thumbnail"),
        "filename": ".".join(song_info["requested_downloads"][0]["filename"].split(".")[:-1])+".m4a"
    }


def search_songs(query: str, playlist_items: str):
    with YoutubeDL(YTDL_OPTIONS | {'playlist_items': playlist_items, "extract_flat": True}) as ydl:

        info_songs = ydl.extract_info(f"https://music.youtube.com/search?q={query}#songs", download = False)
        info_videos = ydl.extract_info(f"https://music.youtube.com/search?q={query}#videos", download = False)

        return [
            {
                "id": song["id"],
                "performer": ', '.join(song.get("authors")),
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
        InlineQueryResultCachedAudio(
            id=song['id'],
            audio_file_id=context.bot_data["cached_songs"][song['id']].file_id
        )
        if song['id'] in context.bot_data["cached_songs"] else
        InlineQueryResultAudio(
            id=song['id'],
            audio_url="https://www.chosic.com/wp-content/uploads/2021/09/Elevator-music(chosic.com).mp3",
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

    await update.inline_query.answer(results, cache_time=3600)

async def inline_query_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_message_id = update.chosen_inline_result.inline_message_id
    video_id = update.chosen_inline_result.result_id

    if video_id in context.bot_data["cached_songs"]:
        audio = context.bot_data["cached_songs"][video_id]
        song_info = None
    else:
        song_info = download_song(video_id)

        audio = (await context.bot.send_audio(
            chat_id=OWNER_USER_ID,
            audio=song_info["filename"],
            performer=song_info["performer"],
            title=song_info["title"],
            duration=song_info["duration"],
            thumbnail=urllib3.request("GET", song_info["thumbnail"]).data if song_info["thumbnail"] else None
        )).audio
        context.bot_data["cached_songs"][video_id] = audio

    await context.bot.edit_message_media(
        media=InputMediaAudio(
            media=audio
        ),
        inline_message_id=inline_message_id,
    )
    safely_remove(song_info["filename"])


async def post_init(application: Application):
    application.bot_data.setdefault("cached_songs", {})

def main():
    application = (
        Application
        .builder()
        .token(TOKEN)
        .persistence(PicklePersistence("persistence.pickle"))
        .post_init(post_init)
        .concurrent_updates(True)
        .write_timeout(30)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Entity(MessageEntity.URL) | filters.Entity(MessageEntity.TEXT_LINK), handle_links))
    application.add_handler(MessageHandler(filters.TEXT, handle_messages))

    application.add_handler(CallbackQueryHandler(download_song_button))
    application.add_handler(InlineQueryHandler(inline_query))

    application.add_handler(ChosenInlineResultHandler(inline_query_edit))


    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()