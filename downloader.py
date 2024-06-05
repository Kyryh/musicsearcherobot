import httpx
from contextlib import contextmanager
from dataclasses import dataclass


from telegram.ext import (
    CallbackContext,
    ExtBot,
)

class Downloader:

    SEARCH_URL = "https://music.youtube.com/youtubei/v1/search?prettyPrint=false"

    SECTIONS = {
        'albums': 'EgWKAQIYAWoKEAoQAxAEEAkQBQ==',
        'artists': 'EgWKAQIgAWoKEAoQAxAEEAkQBQ==',
        'community playlists': 'EgeKAQQoAEABagoQChADEAQQCRAF',
        'featured playlists': 'EgeKAQQoADgBagwQAxAJEAQQDhAKEAU==',
        'songs': 'EgWKAQIIAWoKEAoQAxAEEAkQBQ==',
        'videos': 'EgWKAQIQAWoKEAoQAxAEEAkQBQ==',
    }

    BASE_DATA_SEARCH = {
        "context": {
            "client": {
                "clientName": "WEB_REMIX",
                "clientVersion": "1.20240529.01.00"
            }
        },
    }

    BASE_DATA_ANDROID = {
        "context": {
            "client": {
                "clientName": "ANDROID_MUSIC",
                "clientVersion": "6.42.52"
            }
        },
    }

    def __init__(self):
        self.client = httpx.AsyncClient()
    

    async def __post(self, url: str, data: dict) -> httpx.Response:
        return await self.client.post(url, data=str.encode(str(data)))

    async def search_songs(self, query: str) -> list['Song']:
        data = self.BASE_DATA_SEARCH | {"query": query}
        request_songs = await self.__post(self.SEARCH_URL, data | {"params": self.SECTIONS["songs"]})
        request_videos = await self.__post(self.SEARCH_URL, data | {"params": self.SECTIONS["videos"]})
        return [item for sublist in zip(self.__extract_songs(request_songs), self.__extract_songs(request_videos)) for item in sublist]
    
    def __extract_songs(self, request: httpx.Response) -> list['Song']:
        raw_songs = request.json()["contents"]["tabbedSearchResultsRenderer"]["tabs"][0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"][1]["musicShelfRenderer"]["contents"]
        songs = []
        for song in raw_songs:
            if "playlistItemData" not in song["musicResponsiveListItemRenderer"]:
                continue
            video_id = song["musicResponsiveListItemRenderer"]["playlistItemData"]["videoId"]
            title = song["musicResponsiveListItemRenderer"]["flexColumns"][0]["musicResponsiveListItemFlexColumnRenderer"]["text"]["runs"][0]["text"]
            thumbnails = song["musicResponsiveListItemRenderer"]["thumbnail"]["musicThumbnailRenderer"]["thumbnail"]["thumbnails"]

            video_info = song['musicResponsiveListItemRenderer']['flexColumns'][1]['musicResponsiveListItemFlexColumnRenderer']['text']['runs']
            authors = views = album = duration = date = None
            if len(video_info) > 3:
                authors = [author["text"] for author in video_info[:-4:2]]

                if "views" in video_info[-3]["text"]:
                    views = video_info[-3]["text"]
                else:
                    album = video_info[-3]["text"]

                duration = video_info[-1]["text"]
            else:
                authors = video_info[-1]["text"]
                date = video_info[0]["text"]
            songs.append(Song(
                id=video_id,
                title=title,
                authors=authors,
                views=views,
                album=album,
                duration=duration,
                date=date,
                thumbnails=thumbnails
            ))
        return songs


    async def get_song(self, id: str):
        request = (await self.__post("https://music.youtube.com/youtubei/v1/player?prettyPrint=false", self.BASE_DATA_ANDROID | {"videoId": id})).json()

        song = request["videoDetails"]

        return Song(
            id=song["videoId"],
            title=song["title"],
            authors=[song["author"]],
            views=song["viewCount"],
            duration=int(song["lengthSeconds"]),
            thumbnails=song["thumbnail"]["thumbnails"]
        )


class DownloaderContext(CallbackContext[ExtBot, dict, dict, dict]):
    @property
    def downloader(self) -> Downloader:
        return self.application.downloader

@dataclass
class Song:
    id: str
    title: str
    authors: list[str]
    views: str = None
    album: str = None
    duration: str = None
    duration_seconds: int = None
    date: str = None
    thumbnails: list[dict[str]] = None

    @property
    def thumbnail(self) -> str:
        return self.thumbnails[0]["url"]

    @property
    def performer(self):
        return ", ".join(self.authors)

    def get_duration_seconds(self):
        if self.duration_seconds:
            return self.duration_seconds
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
        return f"{self.__duration_seconds//3600}:{(self.__duration_seconds%3600)//60}:{self.__duration_seconds%60}"


async def main():
    downloader = Downloader()
    print(await downloader.get_song("QbH90DqobJw"))

if __name__ == "__main__":
    import asyncio
    import pprint
    asyncio.run(main())