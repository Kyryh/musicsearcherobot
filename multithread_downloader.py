import asyncio
from threading import Thread
from queue import Queue
from typing import Any, Callable, Awaitable
from yt_dlp import YoutubeDL, DownloadError


class FilesizeTooLargeException(Exception):
    pass

class Downloader:
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
        "max_filesize": 50_000_000,
        'playlist_items': "1"
    }

    download_queue: Queue[tuple[
        str,
        Callable[[dict, list], Awaitable[None]],
        Callable[[Exception], Awaitable[None]],
        list
    ]]

    def __init__(self):
        self.event_loop = asyncio.new_event_loop()
        self.download_queue = Queue()
        self.ydl = YoutubeDL(self.YTDL_OPTIONS)
        Thread(target=self.__download_loop).start()

    def __download_loop(self):
        while True:
            if not self.download_queue.empty():
                try:
                    url, func, exc_func, args = self.download_queue.get_nowait()
                    self.event_loop.run_until_complete(
                        func(self.__download_song(url), *args)
                    )
                    
                except Exception as e:
                    self.event_loop.run_until_complete(
                        exc_func(e)
                    )

    def download(self, url: str, result_handler: Callable[[dict], Awaitable[None]], exception_handler: Callable[[Exception], Awaitable[None]], *args):
        self.download_queue.put_nowait((url, result_handler, exception_handler, args))
        return self.download_queue.qsize()
    
    
    def __download_song(self, url: str):
        info = None
        try:
            info = self.ydl.extract_info(url)
        except DownloadError as e:
            if "Requested format is not available." in e.msg:
                pass
            raise e
        if info is None:
            raise Exception("Unsupported website")
        song_info = info["entries"][0] if "entries" in info else info

        if (song_info["requested_downloads"][0].get("filesize_approx", 0) or song_info["requested_downloads"][0].get("filesize", 0)) > 50_000_000:
            raise FilesizeTooLargeException()
        
        return {
            "success": True,
            "performer": song_info.get("artist") or song_info.get("uploader"),
            "title": song_info.get("track") or song_info.get("title"),
            "duration": song_info.get("duration"),
            "thumbnail": song_info["thumbnails"][0]["url"] if "thumbnails" in song_info else song_info.get("thumbnail"),
            "filename": ".".join(song_info["requested_downloads"][0]["filename"].split(".")[:-1])+".m4a"
        }
