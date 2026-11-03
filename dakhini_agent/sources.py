"""Candidate discovery: YouTube (yt-dlp) and podcast RSS (iTunes directory + feedparser)."""
import time
import feedparser
import requests
import yt_dlp

from .models import Candidate

YDL_BASE = {"quiet": True, "no_warnings": True, "skip_download": True}


def search_youtube(query: str, limit: int = 15) -> list[Candidate]:
    out = []
    with yt_dlp.YoutubeDL({**YDL_BASE, "extract_flat": True}) as ydl:
        try:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        except Exception as e:  # noqa: BLE001
            print(f"  [yt search failed] {query!r}: {e}")
            return out
    for e in (res or {}).get("entries", []) or []:
        if not e or not e.get("id"):
            continue
        out.append(Candidate(
            source="youtube", id=e["id"],
            url=e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
            title=e.get("title") or "", description=e.get("description") or "",
            duration=e.get("duration"), channel=e.get("channel") or e.get("uploader") or "",
            query=query))
    return out


def enrich_youtube(c: Candidate) -> Candidate:
    """Flat search results lack descriptions; fetch full metadata for survivors."""
    try:
        with yt_dlp.YoutubeDL(YDL_BASE) as ydl:
            info = ydl.extract_info(c.url, download=False)
        c.description = info.get("description") or c.description
        c.duration = info.get("duration") or c.duration
        c.channel = info.get("channel") or c.channel
        c.extra["upload_date"] = info.get("upload_date")
    except Exception as e:  # noqa: BLE001
        print(f"  [yt enrich failed] {c.url}: {e}")
    return c


def search_podcasts(query: str, feeds: int = 5, per_feed: int = 30) -> list[Candidate]:
    """Find podcasts through the iTunes Search API, then read their RSS feeds."""
    out = []
    try:
        r = requests.get("https://itunes.apple.com/search",
                         params={"term": query, "media": "podcast", "limit": feeds},
                         timeout=20)
        results = r.json().get("results", [])
    except Exception as e:  # noqa: BLE001
        print(f"  [itunes search failed] {query!r}: {e}")
        return out
    for p in results:
        feed_url = p.get("feedUrl")
        if feed_url:
            out.extend(read_feed(feed_url, query, per_feed, p.get("collectionName", "")))
    return out


def read_feed(feed_url: str, query: str = "", limit: int = 30, name: str = "") -> list[Candidate]:
    out = []
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:  # noqa: BLE001
        print(f"  [rss failed] {feed_url}: {e}")
        return out
    name = name or feed.feed.get("title", "")
    for ent in feed.entries[:limit]:
        enc = next((l.get("href") for l in ent.get("links", [])
                    if l.get("rel") == "enclosure"), None)
        if not enc:
            continue
        dur = ent.get("itunes_duration")
        out.append(Candidate(
            source="podcast", id=ent.get("id") or ent.get("guid") or enc, url=enc,
            title=ent.get("title", ""), description=ent.get("summary", ""),
            duration=_parse_dur(dur), channel=name, query=query,
            extra={"feed": feed_url}))
    return out


def _parse_dur(v):
    if not v:
        return None
    try:
        parts = [float(x) for x in str(v).split(":")]
    except ValueError:
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def polite_sleep():
    time.sleep(0.5)
