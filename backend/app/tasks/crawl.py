from ..celery_app import celery
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Creator, Video, StatsSnapshot
from ..services.platforms.youtube import YouTubeClient
from ..core.etags import ETagCache
import redis, traceback

# Celery task that crawls a single creator on a specified platform (currently YouTube).
# Inputs:
#   - platform (str): The platform identifier, e.g., "youtube".
#   - creator_external_id (str): Platform-native channel/creator ID used by the API.
#   - latest_n (int, default=20): Max number of most recent videos to fetch.
#   - include_comments (bool, default=False): Whether to also fetch comments (not implemented here).
# Returns:
#   - Dict[str, Any]: Simple status payload, e.g., {"status": "ok", "videos_found": N}.
# Side effects:
#   - Reads/writes Redis for ETag caching and possibly rate limiting (via YouTubeClient).
#   - Reads from platform APIs; writes/updates Creator, Video, and StatsSnapshot in the DB.
#   - Commits transactions in batches; may raise to trigger Celery retries on failure.
# Depends on:
#   - Celery for task execution and retry semantics.
#   - SQLAlchemy session factory (SessionLocal) configured in ..db.
#   - YouTubeClient for platform API operations and ETag-aware fetching.
#   - Redis (ETagCache) reachable at the configured URL.
@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def crawl_creator_task(self, platform: str, creator_external_id: str, latest_n: int = 20, include_comments: bool = False):
    r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    etags = ETagCache(r)
    db: Session = SessionLocal()
    try:
        #Istantiate platform client. FIXME: extend for tiktok/instagram/reddit
        if platform == "youtube":
            client = YouTubeClient(r, etags)
        else:
            #avoid silent failures
            raise NotImplementedError(platform)

        # 1) profile
        prof = client.fetch_creator(creator_external_id)

        # try to find existing creator, create if missing
        creator = db.query(Creator).filter_by(platform=platform, external_id=creator_external_id).one_or_none()
        if not creator:
            creator = Creator(platform=platform, external_id=creator_external_id)
            db.add(creator)

        #Map profile snippet to local fields when available (Youtuve Data API response shape)    
        if prof.get("items"):
            sn = prof["items"][0]["snippet"]
            creator.handle = sn.get("customUrl") or sn.get("title")
            creator.display_name = sn.get("title")
        db.commit()

        # 2) latest videos, walk until N or page end. Respect ETag/not-modified optimization. 
        vids, next_token = [], None
        while len(vids) < latest_n:
            page = client.fetch_latest_videos(creator_external_id, next_token, latest_n - len(vids))
            if page.get("not_modified"): break  #Remote hasnt changed per Etag-stop early
            vids.extend(page["items"])
            next_token = page.get("nextPageToken")
            if not next_token: break

        # map to video IDs
        ids = [v["contentDetails"]["videoId"] for v in vids]
        if not ids:
            return {"status": "ok", "videos_found": 0}

        # 3) stats batch fetch video details/stats to avoid N+1 API calls
        detail = client.fetch_video_stats(ids)

        # 4) upsert and a StatsSnapshot per video 
        for item in detail["items"]:
            vid = db.query(Video).filter_by(creator_id=creator.id, external_id=item["id"]).one_or_none()
            if not vid:
                vid = Video(creator_id=creator.id, external_id=item["id"])
                db.add(vid)

            sn = item["snippet"]
            cd = item["contentDetails"]
            st = item.get("statistics", {})

            #description fields / metadata
            vid.title = sn["title"]
            vid.description = sn.get("description", "")

            #Simple heuristic to classify Shorts; can be refined via duration/aspect ratio
            vid.content_type = "SHORT" if any(k in sn.get("title","").lower() for k in ["#shorts","short"]) else "VIDEO"

            # Duration parsing (ISO8601). Fail safe if format is missing or invalid
            dur = 0
            import isodate
            try: dur = int(isodate.parse_duration(cd["duration"]).total_seconds())
            except Exception: pass
            vid.duration_s = dur

            #Snapshot current counters. shares not proviuded by YT Data API, set to 0
            snap = StatsSnapshot(
                video_id=vid.id, 
                views=int(st.get("viewCount",0)), 
                likes=int(st.get("likeCount",0)), 
                comments=int(st.get("commentCount",0)), 
                shares=0)
            db.add(snap)

        db.commit()

        # 5) (optional) comments — omitted here for brevity; follow same pattern with cursors

        return {"status": "ok", "videos_found": len(ids)}
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise
    finally:
        db.close()
