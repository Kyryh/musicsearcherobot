from typing import Any
from downloader import Downloader, Song


class YoutubeDownloader(Downloader):

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

    async def search_songs(self, query: str) -> list['Song']:
        data = self.BASE_DATA_SEARCH | {"query": query}
        request_songs = await self._post(self.SEARCH_URL, data | {"params": self.SECTIONS["songs"]})
        request_videos = await self._post(self.SEARCH_URL, data | {"params": self.SECTIONS["videos"]})
        return [item for sublist in zip(self._extract_songs(request_songs.json()), self._extract_songs(request_videos.json())) for item in sublist]
    
    def _extract_songs(self, response_json: dict[str, Any]) -> list['Song']:
        try:
            raw_songs = response_json["contents"]["tabbedSearchResultsRenderer"]["tabs"][0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"][-1]["musicShelfRenderer"]["contents"]
        except KeyError:
            return []
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
                thumbnails=thumbnails,
                downloader=self
            ))
        return songs

    async def get_song(self, id: str) -> 'Song':
        request = (await self._post("https://music.youtube.com/youtubei/v1/player?prettyPrint=false", self.BASE_DATA_ANDROID | {"videoId": id})).json()

        song = request["videoDetails"]

        downloadUrls = [
            {
                "url": format["url"],
                "size": int(format["contentLength"])/1024**2
            } for format in request["streamingData"]["adaptiveFormats"] if format["itag"] in (139,140,141)
        ][::-1]

        return Song(
            id=song["videoId"],
            title=song["title"],
            authors=[song["author"]],
            views=song["viewCount"],
            duration_seconds=int(song["lengthSeconds"]),
            thumbnails=song["thumbnail"]["thumbnails"],
            download_urls=downloadUrls,
            downloader=self
        )

