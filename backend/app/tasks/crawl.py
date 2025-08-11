from ..celery_app import celery
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Creator, Video, StatsSnapshot
from ..services.platforms.youtube import YouTubeClient
from ..core.etags import ETagCache
import redis, traceback

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def crawl_creator_task(self, platform: str, creator_external_id: str, latest_n: int = 20, include_comments: bool = False):
    r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    etags = ETagCache(r)
    db: Session = SessionLocal()
    try:
        if platform == "youtube":
            client = YouTubeClient(r, etags)
        else:
            raise NotImplementedError(platform)

        # 1) profile
        prof = client.fetch_creator(creator_external_id)

        # upsert creator
        creator = db.query(Creator).filter_by(platform=platform, external_id=creator_external_id).one_or_none()
        if not creator:
            creator = Creator(platform=platform, external_id=creator_external_id)
            db.add(creator)
        if prof.get("items"):
            sn = prof["items"][0]["snippet"]
            creator.handle = sn.get("customUrl") or sn.get("title")
            creator.display_name = sn.get("title")
        db.commit()

        # 2) latest videos, walk until N or page end
        vids, next_token = [], None
        while len(vids) < latest_n:
            page = client.fetch_latest_videos(creator_external_id, next_token, latest_n - len(vids))
            if page.get("not_modified"): break
            vids.extend(page["items"])
            next_token = page.get("nextPageToken")
            if not next_token: break

        # map to video IDs
        ids = [v["contentDetails"]["videoId"] for v in vids]
        if not ids:
            return {"status": "ok", "videos_found": 0}

        # 3) stats batch
        detail = client.fetch_video_stats(ids)

        # 4) upsert
        for item in detail["items"]:
            vid = db.query(Video).filter_by(creator_id=creator.id, external_id=item["id"]).one_or_none()
            if not vid:
                vid = Video(creator_id=creator.id, external_id=item["id"])
                db.add(vid)
            sn = item["snippet"]
            cd = item["contentDetails"]
            st = item.get("statistics", {})
            vid.title = sn["title"]
            vid.description = sn.get("description", "")
            vid.content_type = "SHORT" if any(k in sn.get("title","").lower() for k in ["#shorts","short"]) else "VIDEO"
            # naive parse of ISO8601 duration PT#M#S
            dur = 0
            import isodate
            try: dur = int(isodate.parse_duration(cd["duration"]).total_seconds())
            except Exception: pass
            vid.duration_s = dur

            snap = StatsSnapshot(video_id=vid.id, views=int(st.get("viewCount",0)), likes=int(st.get("likeCount",0)), comments=int(st.get("commentCount",0)), shares=0)
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
