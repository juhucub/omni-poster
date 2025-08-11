import requests, os
from ...core.config import settings
from ...core.ratelimit import TokenBucket
from ...core.etags import ETagCache

class YouTubeClient:
    def __init__(self, r, etags: ETagCache):
        self.key = settings.YT_API_KEY
        self.r = r
        self.units = TokenBucket(r, "yt:units", settings.YT_UNITS_PER_MIN, settings.YT_UNITS_PER_MIN/60)
        self.etags = etags

    def _get(self, endpoint: str, params: dict, unit_cost: int, etag_key: str | None = None):
        if not self.units.acquire(unit_cost, block=True, timeout=10):
            raise RuntimeError("YouTube quota exhausted window")
        headers = {}
        if etag_key:
            et = self.etags.get("yt", etag_key)
            if et:
                headers["If-None-Match"] = et
        resp = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params={**params, "key": self.key}, headers=headers, timeout=20)
        if resp.status_code == 304:
            return {"items": [], "etag": resp.headers.get("ETag"), "not_modified": True}
        resp.raise_for_status()
        et = resp.headers.get("ETag")
        if et and etag_key:
            self.etags.set("yt", etag_key, et)
        return {**resp.json(), "etag": et}

    def fetch_creator(self, channel_id: str):
        return self._get("channels", {"part":"snippet,contentDetails","id":channel_id}, unit_cost=1, etag_key=f"channels:{channel_id}")

    def fetch_latest_videos(self, channel_id: str, page_token: str | None, limit: int):
        ch = self.fetch_creator(channel_id)
        if ch.get("not_modified"):
            return {"items": [], "nextPageToken": None}
        uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        params = {"part":"snippet,contentDetails","playlistId":uploads,"maxResults":min(limit,50)}
        if page_token: params["pageToken"] = page_token
        # playlistItems cost ~1 unit; videos.list later costs more
        return self._get("playlistItems", params, unit_cost=1, etag_key=f"playlist:{uploads}")

    def fetch_video_stats(self, video_ids: list[str]):
        chunks = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
        out = []
        for chunk in chunks:
            r = self._get("videos", {"part":"snippet,contentDetails,statistics","id":",".join(chunk)}, unit_cost=1, etag_key=None)
            out.extend(r["items"])
        return {"items": out}

    def fetch_comments(self, video_id: str, cursor: str | None, limit: int):
        params = {"part":"snippet","videoId":video_id,"maxResults":min(limit,100),"order":"time"}
        if cursor: params["pageToken"] = cursor
        return self._get("commentThreads", params, unit_cost=1, etag_key=None)
