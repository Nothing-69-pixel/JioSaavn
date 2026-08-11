from flask import Flask, request, jsonify, make_response
import requests
import html
import math
import json

app = Flask(__name__)

BASE_URL = "https://www.jiosaavn.com/api.php"
PER_PAGE = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.jiosaavn.com/"
}


# =========================================================
# CORS
# Allows local HTML (content:// / file://) and other domains
# =========================================================

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        response = make_response("", 204)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response


# =========================================================
# Helpers
# =========================================================

def clean_text(value):
    if value is None:
        return ""
    return html.unescape(str(value)).strip()


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


def better_image(url):
    if not url:
        return ""

    url = str(url)

    replacements = [
        ("50x50", "500x500"),
        ("75x75", "500x500"),
        ("150x150", "500x500"),
        ("250x250", "500x500"),
    ]

    for old, new in replacements:
        url = url.replace(old, new)

    return url


def parse_json_response(response):
    try:
        return response.json()
    except Exception:
        text = response.text.strip()

        if not text:
            raise ValueError("Empty response from JioSaavn")

        # Try direct JSON
        try:
            return json.loads(text)
        except Exception:
            pass

        # Some responses may contain extra lines
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("{") or line.startswith("["):
                try:
                    return json.loads(line)
                except Exception:
                    continue

        raise ValueError("Invalid JSON response from JioSaavn")


def saavn_request(params):
    common = {
        "_format": "json",
        "_marker": "0",
        "ctx": "web6dot0",
        "api_version": "4"
    }

    common.update(params)

    response = requests.get(
        BASE_URL,
        params=common,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()
    return parse_json_response(response)


def get_primary_artists(song):
    info = song.get("more_info") or {}
    artist_map = info.get("artistMap") or {}
    artists = artist_map.get("primary_artists") or []

    names = []

    for artist in artists:
        if not isinstance(artist, dict):
            continue

        name = clean_text(artist.get("name"))
        if name:
            names.append(name)

    if names:
        return names

    primary = clean_text(
        song.get("primary_artists")
        or info.get("primary_artists")
    )

    if primary:
        return [x.strip() for x in primary.split(",") if x.strip()]

    subtitle = clean_text(song.get("subtitle"))

    if " - " in subtitle:
        subtitle = subtitle.split(" - ", 1)[0]

    return [x.strip() for x in subtitle.split(",") if x.strip()]


def normalize_song(song):
    info = song.get("more_info") or {}
    artists = get_primary_artists(song)

    return {
        "id": song.get("id"),
        "type": "song",
        "title": clean_text(song.get("title") or song.get("song")),
        "artists": artists,
        "artist": ", ".join(artists),
        "subtitle": clean_text(song.get("subtitle")),
        "album": clean_text(info.get("album") or song.get("album")),
        "album_id": info.get("album_id"),
        "image": better_image(song.get("image")),
        "duration": safe_int(info.get("duration") or song.get("duration")),
        "year": song.get("year"),
        "language": clean_text(song.get("language")),
        "play_count": safe_int(song.get("play_count")),
        "explicit": str(song.get("explicit_content", "0")) == "1",
        "has_lyrics": safe_bool(info.get("has_lyrics")),
        "320kbps": safe_bool(info.get("320kbps")),

        # Official JioSaavn song page (full-song playback stays on JioSaavn)
        "song_url": song.get("perma_url"),
        "full_song_url": song.get("perma_url"),

        # JioTune / preview URL when JioSaavn supplies one
        "preview_url": info.get("vlink"),

        # Protected media metadata returned by JioSaavn.
        # This is intentionally NOT decrypted or converted into a direct full-track URL.
        "protected_media": {
            "encrypted_media_url": info.get("encrypted_media_url"),
            "encrypted_drm_media_url": info.get("encrypted_drm_media_url"),
            "cache_state": info.get("cache_state"),
            "rights": info.get("rights") or {}
        }
    }


def normalize_playlist(item):
    info = item.get("more_info") or {}

    return {
        "id": (
            item.get("id")
            or item.get("listid")
            or item.get("list_id")
            or item.get("playlistid")
        ),
        "type": "playlist",
        "title": clean_text(
            item.get("title")
            or item.get("listname")
            or item.get("name")
        ),
        "subtitle": clean_text(item.get("subtitle")),
        "image": better_image(item.get("image")),
        "song_count": safe_int(
            info.get("song_count")
            or item.get("song_count")
            or item.get("list_count")
        ),
        "url": item.get("perma_url") or item.get("url")
    }


def normalize_album(item):
    info = item.get("more_info") or {}

    return {
        "id": (
            item.get("id")
            or item.get("albumid")
            or item.get("album_id")
        ),
        "type": "album",
        "title": clean_text(
            item.get("title")
            or item.get("name")
            or item.get("album")
        ),
        "subtitle": clean_text(item.get("subtitle")),
        "artist": clean_text(
            item.get("music")
            or info.get("music")
            or item.get("primary_artists")
        ),
        "image": better_image(item.get("image")),
        "year": item.get("year"),
        "language": clean_text(item.get("language")),
        "url": item.get("perma_url") or item.get("url")
    }


def normalize_artist(item):
    return {
        "id": (
            item.get("id")
            or item.get("artistid")
            or item.get("artistId")
        ),
        "type": "artist",
        "name": clean_text(item.get("title") or item.get("name")),
        "subtitle": clean_text(item.get("subtitle")),
        "image": better_image(item.get("image")),
        "url": item.get("perma_url") or item.get("url")
    }


def paginate(items, page, per_page=10):
    page = max(1, page)
    start = (page - 1) * per_page
    end = start + per_page

    sliced = items[start:end]
    total = len(items)
    total_pages = math.ceil(total / per_page) if total else 0

    return sliced, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": end < total,
        "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if end < total else None
    }


def extract_autocomplete_list(data, key):
    raw = data.get(key, [])

    if isinstance(raw, dict):
        return raw.get("data", []) or []

    if isinstance(raw, list):
        return raw

    return []


# =========================================================
# Root / health
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": True,
        "name": "JioSaavn Music API",
        "version": "2.1",
        "cors": True,
        "note": "Preview audio is exposed when available. Full protected tracks are not decrypted; use full_song_url to continue on JioSaavn.",
        "per_page": PER_PAGE,
        "endpoints": {
            "song_search": "/search?q=Tum Hi Ho&page=1",
            "all_search": "/search/all?q=Arijit&page=1",
            "playlist_search": "/search/playlists?q=Romantic&page=1",
            "album_search": "/search/albums?q=Aashiqui&page=1",
            "artist_search": "/search/artists?q=Arijit Singh&page=1",
            "song_details": "/song?id=aRZbUYD7",
            "playlist_details": "/playlist?id=PLAYLIST_ID&page=1",
            "album_details": "/album?id=ALBUM_ID&page=1"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": True,
        "message": "API is running",
        "cors": True
    })


# =========================================================
# Song search - 10 results per page
# =========================================================

@app.route("/search", methods=["GET"])
def search_songs():
    query = request.args.get("q", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not query:
        return jsonify({
            "status": False,
            "error": "Missing query",
            "usage": "/search?q=Tum Hi Ho&page=1"
        }), 400

    try:
        data = saavn_request({
            "__call": "search.getResults",
            "q": query,
            "p": page,
            "n": PER_PAGE
        })

        raw_results = data.get("results", []) or []
        songs = [normalize_song(song) for song in raw_results]

        total = safe_int(data.get("total"), len(songs))
        total_pages = math.ceil(total / PER_PAGE) if total else 0

        return jsonify({
            "status": True,
            "query": query,
            "type": "song",
            "page": page,
            "per_page": PER_PAGE,
            "count": len(songs),
            "total": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages if total_pages else False,
            "previous_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < total_pages else None,
            "results": songs
        })

    except requests.RequestException as e:
        return jsonify({
            "status": False,
            "error": "JioSaavn request failed",
            "details": str(e)
        }), 502

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Search failed",
            "details": str(e)
        }), 500


# =========================================================
# All search
# Songs + playlists + albums + artists
# =========================================================

@app.route("/search/all", methods=["GET"])
def search_all():
    query = request.args.get("q", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not query:
        return jsonify({
            "status": False,
            "error": "Missing query"
        }), 400

    try:
        data = saavn_request({
            "__call": "autocomplete.get",
            "query": query
        })

        songs_raw = extract_autocomplete_list(data, "songs")
        playlists_raw = extract_autocomplete_list(data, "playlists")
        albums_raw = extract_autocomplete_list(data, "albums")
        artists_raw = extract_autocomplete_list(data, "artists")

        combined = (
            [normalize_song(x) for x in songs_raw]
            + [normalize_playlist(x) for x in playlists_raw]
            + [normalize_album(x) for x in albums_raw]
            + [normalize_artist(x) for x in artists_raw]
        )

        results, pagination = paginate(combined, page, PER_PAGE)

        return jsonify({
            "status": True,
            "query": query,
            "type": "all",
            **pagination,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "All search failed",
            "details": str(e)
        }), 502


# =========================================================
# Playlist search
# =========================================================

@app.route("/search/playlists", methods=["GET"])
def search_playlists():
    query = request.args.get("q", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not query:
        return jsonify({
            "status": False,
            "error": "Missing query"
        }), 400

    try:
        data = saavn_request({
            "__call": "autocomplete.get",
            "query": query
        })

        raw = extract_autocomplete_list(data, "playlists")
        playlists = [normalize_playlist(x) for x in raw]

        results, pagination = paginate(playlists, page, PER_PAGE)

        return jsonify({
            "status": True,
            "query": query,
            "type": "playlist",
            **pagination,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Playlist search failed",
            "details": str(e)
        }), 502


# =========================================================
# Album search
# =========================================================

@app.route("/search/albums", methods=["GET"])
def search_albums():
    query = request.args.get("q", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not query:
        return jsonify({
            "status": False,
            "error": "Missing query"
        }), 400

    try:
        data = saavn_request({
            "__call": "autocomplete.get",
            "query": query
        })

        raw = extract_autocomplete_list(data, "albums")
        albums = [normalize_album(x) for x in raw]

        results, pagination = paginate(albums, page, PER_PAGE)

        return jsonify({
            "status": True,
            "query": query,
            "type": "album",
            **pagination,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Album search failed",
            "details": str(e)
        }), 502


# =========================================================
# Artist search
# =========================================================

@app.route("/search/artists", methods=["GET"])
def search_artists():
    query = request.args.get("q", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not query:
        return jsonify({
            "status": False,
            "error": "Missing query"
        }), 400

    try:
        data = saavn_request({
            "__call": "autocomplete.get",
            "query": query
        })

        raw = extract_autocomplete_list(data, "artists")
        artists = [normalize_artist(x) for x in raw]

        results, pagination = paginate(artists, page, PER_PAGE)

        return jsonify({
            "status": True,
            "query": query,
            "type": "artist",
            **pagination,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Artist search failed",
            "details": str(e)
        }), 502


# =========================================================
# Song details
# =========================================================

@app.route("/song", methods=["GET"])
def song_details():
    song_id = request.args.get("id", "").strip()

    if not song_id:
        return jsonify({
            "status": False,
            "error": "Missing song id",
            "usage": "/song?id=aRZbUYD7"
        }), 400

    try:
        data = saavn_request({
            "__call": "song.getDetails",
            "pids": song_id
        })

        song = None

        if isinstance(data, dict):
            if song_id in data and isinstance(data[song_id], dict):
                song = data[song_id]
            elif isinstance(data.get("songs"), list) and data["songs"]:
                song = data["songs"][0]
            elif data.get("id"):
                song = data

        if not song:
            return jsonify({
                "status": False,
                "error": "Song not found"
            }), 404

        return jsonify({
            "status": True,
            "result": normalize_song(song)
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Failed to fetch song",
            "details": str(e)
        }), 502


# =========================================================
# Playlist details - 10 songs per page
# =========================================================

@app.route("/playlist", methods=["GET"])
def playlist_details():
    playlist_id = request.args.get("id", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not playlist_id:
        return jsonify({
            "status": False,
            "error": "Missing playlist id"
        }), 400

    try:
        fetch_count = max(PER_PAGE, page * PER_PAGE)

        data = saavn_request({
            "__call": "playlist.getDetails",
            "listid": playlist_id,
            "p": 1,
            "n": fetch_count
        })

        raw_songs = data.get("songs") or data.get("list") or []
        songs = [normalize_song(x) for x in raw_songs]

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_songs = songs[start:end]

        total = safe_int(
            data.get("list_count")
            or data.get("song_count")
            or data.get("count"),
            len(songs)
        )

        total_pages = math.ceil(total / PER_PAGE) if total else 0

        has_next = (
            page < total_pages
            if total_pages
            else len(page_songs) == PER_PAGE
        )

        return jsonify({
            "status": True,
            "playlist": {
                "id": data.get("listid") or data.get("id") or playlist_id,
                "title": clean_text(
                    data.get("listname")
                    or data.get("title")
                    or data.get("name")
                ),
                "image": better_image(data.get("image")),
                "url": data.get("perma_url") or data.get("url")
            },
            "page": page,
            "per_page": PER_PAGE,
            "count": len(page_songs),
            "total": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": has_next,
            "previous_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if has_next else None,
            "songs": page_songs
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Failed to fetch playlist",
            "details": str(e)
        }), 502


# =========================================================
# Album details - 10 songs per page
# =========================================================

@app.route("/album", methods=["GET"])
def album_details():
    album_id = request.args.get("id", "").strip()
    page = max(1, safe_int(request.args.get("page"), 1))

    if not album_id:
        return jsonify({
            "status": False,
            "error": "Missing album id"
        }), 400

    try:
        data = saavn_request({
            "__call": "content.getAlbumDetails",
            "albumid": album_id
        })

        raw_songs = data.get("songs") or []
        songs = [normalize_song(x) for x in raw_songs]

        page_songs, pagination = paginate(songs, page, PER_PAGE)

        return jsonify({
            "status": True,
            "album": {
                "id": data.get("id") or data.get("albumid") or album_id,
                "title": clean_text(data.get("name") or data.get("title")),
                "artist": clean_text(
                    data.get("primary_artists")
                    or data.get("music")
                ),
                "image": better_image(data.get("image")),
                "year": data.get("year"),
                "language": clean_text(data.get("language")),
                "url": data.get("perma_url") or data.get("url")
            },
            **pagination,
            "count": len(page_songs),
            "songs": page_songs
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Failed to fetch album",
            "details": str(e)
        }), 502


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": False,
        "error": "Endpoint not found"
    }), 404


# =========================================================
# Local development
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
