import httpx
from contextlib import contextmanager

from telegram.ext import (
    CallbackContext,
    ExtBot,
)

class Downloader:
    def __init__(self):
        self.client = httpx.AsyncClient()
    
    async def search_songs(self, query: str, num_items: int):
        return []
    
    @contextmanager
    async def download_song(self, id: str):
        try:
            yield None
        finally:
            pass


class DownloaderContext(CallbackContext[ExtBot, dict, dict, dict]):
    @property
    def downloader(self) -> Downloader:
        return self.application.downloader