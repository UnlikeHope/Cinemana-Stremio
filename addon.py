"""Stremio stream add-on: find Cinemana sources for a requested IMDb ID."""

import base64
import os
import re
from functools import lru_cache
from urllib.parse import quote

import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CINEMANA_BASE = "https://cinemana.shabakaty.com/api/android"
IMDB_SUGGEST = "https://v3.sg.media-imdb.com/suggestion/a"
ANIME_MAPPING = "https://arm.haglund.dev/api/v2/imdb"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

MAX_SEARCH_PAGES = 5
SEARCH_PAGE_SIZE = 12
MEDIA_KINDS = {"movie": "1", "series": "2"}

MAL_RE = re.compile(r"myanimelist\.net/anime/(\d+)")

MANIFEST = {
    "id": "org.cinemana.stremio",
    "version": "1.0.0",
    "name": "Cinemana",
    "description": "Direct streams from Shabakaty's Cinemana",
    "logo": "https://cinemana.shabakaty.com/favicon.ico",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": [],
}


def cinemana_get(path, params=None):
    response = requests.get(
        f"{CINEMANA_BASE}/{path}", headers=HEADERS, params=params, timeout=30
    )
    response.raise_for_status()
    return response.json()


def imdb_lookup(imdb_id):
    """Return (title, year) for an IMDb ID, or None."""
    try:
        response = requests.get(
            f"{IMDB_SUGGEST}/{imdb_id}.json", headers=HEADERS, timeout=15
        )
        response.raise_for_status()
        for item in response.json().get("d", []):
            if item.get("id") == imdb_id and item.get("l"):
                return item["l"], item.get("y")
    except Exception:
        pass
    return None


def extract_imdb_id(url):
    match = re.search(r"tt\d+", str(url or ""))
    return match.group(0) if match else None


def extract_mal_id(url):
    match = MAL_RE.search(str(url or ""))
    return match.group(1) if match else None


@lru_cache(maxsize=1024)
def imdb_to_mal(imdb_id):
    """Map an IMDb ID to its MyAnimeList ID (many Cinemana anime only carry a MAL link)."""
    try:
        response = requests.get(
            ANIME_MAPPING, headers=HEADERS, params={"id": imdb_id}, timeout=10
        )
        response.raise_for_status()
        data = response.json()
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if entry.get("myanimelist"):
                return str(entry["myanimelist"])
    except Exception:
        pass
    return None


def normalize_title(title):
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()


def has_matching_title(info, titles):
    requested = {normalize_title(title) for title in titles if title}
    available = {
        normalize_title(info.get(key))
        for key in ("en_title", "other_title", "ar_title")
    }
    requested.discard("")
    available.discard("")
    return bool(requested & available)


def info_matches_imdb(info, imdb_id, mal_id, titles, year=None):
    ref = info.get("imdbUrlRef") or ""

    ref_imdb = extract_imdb_id(ref)
    if ref_imdb:
        return ref_imdb == imdb_id

    ref_mal = extract_mal_id(ref)
    if ref_mal and mal_id:
        return ref_mal == mal_id

    # Don't trust title-only matches for entries linked to an unrelated site.
    if ref and not ref_mal:
        return False

    if not has_matching_title(info, titles):
        return False

    info_year = info.get("year")
    if year and info_year:
        try:
            return abs(int(str(year)[:4]) - int(str(info_year)[:4])) <= 1
        except ValueError:
            return True
    return True


def is_media_type(item, media_type):
    return str(item.get("kind")) == MEDIA_KINDS[media_type]


def cinemana_search(title, media_type, year=None):
    """Search via AdvancedSearch, newest first."""
    results = []
    for page in range(MAX_SEARCH_PAGES):
        params = {
            "level": 0,
            "videoTitle": title,
            "sort": "desc",
            "page": page,
            "type": media_type,
        }
        if year:
            params["year"] = f"{year},{year}"

        page_items = cinemana_get("AdvancedSearch", params=params)
        if not isinstance(page_items, list):
            break
        results.extend(item for item in page_items if is_media_type(item, media_type))
        if len(page_items) < SEARCH_PAGE_SIZE:
            break
    return results


def cinemana_simple_search(title, media_type):
    """Title search endpoint also indexes `other_title`, unlike AdvancedSearch."""
    keyword = quote(base64.b64encode(title.encode()).decode(), safe="")
    results = []
    for page in range(MAX_SEARCH_PAGES):
        path = (
            f"video/V/2/itemsPerPage/20/video_title_search/{keyword}"
            f"/itemsPerPage/{SEARCH_PAGE_SIZE}/pageNumber/{page}/level/0"
        )
        page_items = cinemana_get(path)
        if not isinstance(page_items, list):
            break
        results.extend(item for item in page_items if is_media_type(item, media_type))
        if len(page_items) < SEARCH_PAGE_SIZE:
            break
    return results


def unique_videos(results, seen):
    for item in results:
        video_id = item.get("nb")
        if video_id and video_id not in seen:
            seen.add(video_id)
            yield item


def search_candidates(titles, media_type, year=None):
    """Yield candidate videos: AdvancedSearch first, then the simple search fallback."""
    seen = set()

    for title in titles:
        results = cinemana_search(title, media_type, year)
        if not results and year:
            results = cinemana_search(title, media_type)
        yield from unique_videos(results, seen)

    # AdvancedSearch can miss entries whose English title only lives in `other_title`.
    for title in titles:
        yield from unique_videos(cinemana_simple_search(title, media_type), seen)


def cinemana_info(video_id):
    return cinemana_get(f"allVideoInfo/id/{video_id}")


def cinemana_episodes(series_id):
    data = cinemana_get(f"videoSeason/id/{series_id}")
    return data if isinstance(data, list) else []


def cinemana_streams(video_id):
    data = cinemana_get(f"transcoddedFiles/id/{video_id}")
    return data if isinstance(data, list) else []


def find_match(imdb_id, title, media_type, year=None):
    titles = [title]
    simple_title = re.split(r"[:\-–]", title, maxsplit=1)[0].strip()
    if simple_title and simple_title != title:
        titles.append(simple_title)

    mal_id = None
    mal_checked = False

    for result in search_candidates(titles, media_type, year):
        info = cinemana_info(result["nb"])
        if not info:
            continue
        if not mal_checked and extract_mal_id(info.get("imdbUrlRef")):
            mal_id = imdb_to_mal(imdb_id)
            mal_checked = True
        if info_matches_imdb(info, imdb_id, mal_id, titles, year):
            return info

    return None


def build_streams(video_id, info):
    streams = []
    for item in cinemana_streams(video_id):
        url = item.get("videoUrl")
        if not url:
            continue
        quality = item.get("resolution") or item.get("name") or "unknown"
        streams.append({
            "url": url,
            "title": f"{quality} - Cinemana",
            "name": f"Cinemana {quality}",
            "behaviorHints": {
                "notWebReady": False,
                "bingeGroup": "cinemana",
            },
        })

    subtitles = [
        {"url": translation["file"], "lang": translation["type"]}
        for translation in info.get("translations") or []
        if translation.get("file") and translation.get("type")
    ]
    if subtitles:
        for stream in streams:
            stream["subtitles"] = subtitles

    return streams


def find_episode_id(series_id, season, episode):
    for item in cinemana_episodes(series_id):
        if (
            str(item.get("season")) == season
            and str(item.get("episodeNummer")) == episode
        ):
            return item.get("nb")
    return None


def get_streams(media_type, item_id):
    if media_type not in MEDIA_KINDS:
        return []

    parts = item_id.split(":")
    imdb_id = parts[0]

    lookup = imdb_lookup(imdb_id)
    if not lookup:
        return []
    title, year = lookup

    info = find_match(imdb_id, title, media_type, year)
    if not info:
        return []

    if media_type == "movie":
        return build_streams(info.get("nb"), info)

    season = parts[1] if len(parts) > 1 else "1"
    episode = parts[2] if len(parts) > 2 else "1"
    episode_id = find_episode_id(info.get("nb"), season, episode)
    if not episode_id:
        return []
    return build_streams(episode_id, info)


@app.route("/manifest.json")
@app.route("/<config>/manifest.json")
def manifest(config=None):
    return jsonify(MANIFEST)


@app.route("/stream/<media_type>/<item_id>.json")
@app.route("/<config>/stream/<media_type>/<item_id>.json")
def stream(media_type, item_id, config=None):
    return jsonify({"streams": get_streams(media_type, item_id)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5069))
    app.run(host="0.0.0.0", port=port, threaded=True)
