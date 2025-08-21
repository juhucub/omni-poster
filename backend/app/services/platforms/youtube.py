"""
Purpose: Thin YT Data API client used by crawler tasks to fetch creators, latest videos, video stats,
         and comments. Implements ETag-aware conditional requests and a token-bucket rate limiter to
         respect quota limits.

Interactions:
    - Reads YouTube API key from settings (core.config.settings.YT_API_KEY).
    - Uses Redis-backed TokenBucket (core.ratelimit.TokenBucket) to enforce request unit budgets.
    - Uses Redis-backed ETagCache (core.etags.ETagCache) to perform conditional GETs and reduce quota.
    - Called by crawler tasks (e.g., tasks/crawl.py) to retrieve channel metadata and content.

Key Chart Map idk:
    - Security: API key must come from environment/secret manager; never hardcode. Prefer HTTPS only.
    - Quotas: Each endpoint consumes YouTube “units”; TokenBucket helps avoid exceeding per-minute caps.
    - Caching: ETag-based conditional requests return 304 to save units; cache keys must be stable.
    - Reliability: All requests have a timeout; callers should handle raise_for_status exceptions & retries.
    - Performance: Batches `videos.list` up to 50 IDs per call to minimize API round trips.
"""

import requests, os
from ...core.config import settings
from ...core.ratelimit import TokenBucket
from ...core.etags import ETagCache

# Minimal YouTube Data API v3 client with quota and ETag handling.
# Inputs:
#   - r: Redis client instance used by TokenBucket/ETagCache for state.
#   - etags (ETagCache): Helper to store/retrieve ETag values by namespace/key.
# Side effects:
#   - Initializes a TokenBucket in Redis to throttle request "units".
# Depends on:
#   - settings.YT_API_KEY, settings.YT_UNITS_PER_MIN
class YouTubeClient:
    def __init__(self, r, etags: ETagCache):
        self.key = settings.YT_API_KEY
        self.r = r
        self.units = TokenBucket(r, "yt:units", settings.YT_UNITS_PER_MIN, settings.YT_UNITS_PER_MIN/60)
        self.etags = etags


    # Internal helper to call YouTube endpoints with quota and ETag handling.
    # Inputs:
    #   - endpoint (str): YouTube API resource path (e.g., "videos", "channels").
    #   - params (dict): Query parameters (without API key).
    #   - unit_cost (int): Estimated YouTube “unit” cost to charge this call.
    #   - etag_key (str|None): Optional key for conditional GET; if provided, sends If-None-Match and stores ETag.
    # Returns:
    #   - dict: Parsed JSON body merged with "etag" and possibly "not_modified".
    # Side effects:
    #   - Consumes tokens from the TokenBucket; blocks up to 10s if bucket is empty.
    #   - Reads/writes ETagCache.
    # Raises:
    #   - RuntimeError if quota window is exhausted.
    #   - requests.HTTPError via raise_for_status for non-2xx responses.
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

    # Fetch channel metadata (snippet + contentDetails) by channel ID.
    # Inputs:
    #   - channel_id (str): YouTube channel ID.
    # Returns:
    #   - dict: API response with channel data and ETag metadata.
    # Side effects:
    #   - Charges 1 unit to the token bucket; uses/stores ETag under "channels:{channel_id}".
    # Depends on:
    #   - YouTube channels.list endpoint.
    def fetch_creator(self, channel_id: str):
        return self._get("channels", {"part":"snippet,contentDetails","id":channel_id}, unit_cost=1, etag_key=f"channels:{channel_id}")

    # Fetch the latest videos from the channel's "uploads" playlist (paginated).
    # Inputs:
    #   - channel_id (str): YouTube channel ID used to resolve uploads playlist.
    #   - page_token (str|None): Continuation token for pagination.
    #   - limit (int): Maximum number of playlist items to request in this page (<=50).
    # Returns:
    #   - dict: { "items": [...], "nextPageToken": <str|None>, "etag": <str>, "not_modified"?: True }
    # Side effects:
    #   - Resolves uploads playlist from channel; issues playlistItems.list with ETag caching.
    # Notes:
    #   - playlistItems cost ~1 unit; heavier details come later via videos.list.
    def fetch_latest_videos(self, channel_id: str, page_token: str | None, limit: int):
        ch = self.fetch_creator(channel_id)
        if ch.get("not_modified"):
            return {"items": [], "nextPageToken": None}
        uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        params = {"part":"snippet,contentDetails","playlistId":uploads,"maxResults":min(limit,50)}
        if page_token: params["pageToken"] = page_token
        # playlistItems cost ~1 unit; videos.list later costs more
        return self._get("playlistItems", params, unit_cost=1, etag_key=f"playlist:{uploads}")

    # Batch fetch video details and statistics for up to 50 IDs per call.
    # Inputs:
    #   - video_ids (list[str]): One or more video IDs.
    # Returns:
    #   - dict: {"items": [ ...video objects with snippet/contentDetails/statistics... ]}
    # Side effects:
    #   - Multiple API calls if len(video_ids) > 50; each charged ~1 unit per chunk.
    # Depends on:
    #   - YouTube videos.list endpoint.
    def fetch_video_stats(self, video_ids: list[str]):
        chunks = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
        out = []
        for chunk in chunks:
            r = self._get("videos", {"part":"snippet,contentDetails,statistics","id":",".join(chunk)}, unit_cost=1, etag_key=None)
            out.extend(r["items"])
        return {"items": out}

    # Fetch comment threads for a given video, ordered by time (newest first).
    # Inputs:
    #   - video_id (str): YouTube video ID.
    #   - cursor (str|None): pageToken for pagination.
    #   - limit (int): Maximum items to request (<=100 per API constraints).
    # Returns:
    #   - dict: Standard commentThreads response including nextPageToken when present.
    # Side effects:
    #   - Consumes ~1 unit per request; no ETag caching here by default.
    # Considerations:
    #   - Comments can be high-volume; callers should respect quotas and apply backoff.
    def fetch_comments(self, video_id: str, cursor: str | None, limit: int):
        params = {"part":"snippet","videoId":video_id,"maxResults":min(limit,100),"order":"time"}
        if cursor: params["pageToken"] = cursor
        return self._get("commentThreads", params, unit_cost=1, etag_key=None)
