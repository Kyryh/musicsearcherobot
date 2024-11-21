from typing import Any, Optional, cast
import httpx
from dataclasses import dataclass
from abc import ABC

import logging

from telegram.ext import (
    CallbackContext,
    ExtBot,
)

logger = logging.getLogger("Downloader")

class Downloader(ABC):

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10)
    
    async def get(self, url: str, headers: dict[str, str] = None) -> httpx.Response:
        return await self.client.get(url, headers=headers)

    async def _post(self, url: str, data: dict) -> httpx.Response:
        return await self.client.post(url, data=str.encode(str(data)))

    async def search_songs(self, query: str) -> list['Song']:
        ...
    
    def _extract_songs(self, response_json: dict[str, Any]) -> list['Song']:
        ...

    async def get_song(self, id: str) -> 'Song':
        ...

    async def download_song(self, id: int, size_limit: float = None) -> tuple['Song', bytes]:
        song = await self.get_song(id)
        return (song, cast(bytes, await song.download(size_limit)))


class DownloaderContext(CallbackContext[ExtBot, dict, dict, dict]):
    @property
    def downloader(self) -> Downloader:
        return self.application.bot_data["downloader"]

@dataclass
class Song:
    id: str
    title: str
    authors: list[str]
    views: str
    thumbnails: list[dict[str, str|int]]
    downloader: Downloader
    album: Optional[str] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = None
    date: Optional[str] = None
    download_urls: Optional[list[dict[str, str|int]]] = None

    @property
    def thumbnail(self) -> str:
        return cast(str, self.thumbnails[0]["url"])

    @property
    def performer(self):
        return ", ".join(self.authors)

    def get_duration_seconds(self):
        if self.duration_seconds:
            return self.duration_seconds
        if not self.duration:
            return 0
        mult = 1
        seconds = 0
        split_duration = self.duration.split(":")[::-1]
        for s in split_duration:
            seconds += int(s)*mult
            mult *= 60
        return seconds

    def get_duration(self):
        if self.duration:
            return self.duration
        if not self.duration_seconds:
            return ""
        return f"{self.duration_seconds//3600}:{(self.duration_seconds%3600)//60}:{self.duration_seconds%60}"
    
    async def download(self, size_limit: float = None) -> Optional[bytes]:
        if not self.download_urls:
            self.download_urls = cast(list[dict[str, str|int]], (await self.downloader.get_song(self.id)).download_urls)
        for downloadUrl in self.download_urls:
            if size_limit is None or cast(int, downloadUrl["size"]) < size_limit:
                url = downloadUrl["url"]
                # could probably do all this with a stream
                # oh well
                song = b""
                i = 0
                while True:
                    request = await self.downloader.get(url, headers={"Range": f"bytes={8388608*i}-{8388608*(i+1)-1}"})
                    if request.status_code == 416:
                        break
                    if request.status_code == 302:
                        url = request.next_request.url
                        continue
                    song += request.read()
                    i += 1
                return song
        logger.info(self.id, self.download_urls[-1]["size"])
        return None


async def main():
    pass

if __name__ == "__main__":
    import asyncio
    import pprint
    asyncio.run(main())