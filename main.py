from flask import Flask, request, jsonify
import requests
import html
import math

app = Flask(__name__)

BASE_URL = "https://www.jiosaavn.com/api.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.jiosaavn.com/"
}

PER_PAGE = 10


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


def better_image(url):
    if not url:
        return ""

    return (
        str(url)
        .replace("50x50", "500x500")
        .replace("150x150", "500x500")
    )


def saavn_request(params):
    base_params = {
        "_format": "json",
        "_marker": "0",
        "ctx": "web6dot0",
        "api_version": "4"
    }

    base_params.update(params)

    response = requests.get(
        BASE_URL,
        params=base_params,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    try:
        return response.json()
    except Exception:
        # Some JioSaavn responses can contain extra lines.
        text = response.text.strip()

        for line in text.splitlines():
            line = line.strip()

            if line.startswith("{") or line.startswith("["):
                try:
                    return requests.models.complexjson.loads(line)
                except Exception:
                    continue

        raise ValueError("Invalid JSON response from JioSaavn")


def get_primary_artists(song):
    info = song.get("more_info") or {}
    artist_map = info.get("artistMap") or {}

    artists = artist_map.get("primary_artists") or []

    names = []

    for artist in artists:
        name = clean_text(artist.get("name"))

        if name:
            names.append(name)

    if names:
        return names

    subtitle = clean_text(song.get("subtitle"))

    if " - " in subtitle:
        subtitle = subtitle.split(" - ")[0]

    return [
        x.strip()
        for x in subtitle.split(",")
        if x.strip()
    ]


def normalize_song(song):
    info = song.get("more_info") or {}

    artists = get_primary_artists(song)

    return {
        "id": song.get("id"),
        "type": "song",

        "title": clean_text(
            song.get("title") or
            song.get("song")
        ),

        "artists": artists,
        "artist": ", ".join(artists),

        "subtitle": clean_text(
            song.get("subtitle")
        ),

        "album": clean_text(
            info.get("album") or
            song.get("album")
        ),

        "album_id": info.get("album_id"),

        "image": better_image(
            song.get("image")
        ),

        "duration": safe_int(
            info.get("duration") or
            song.get("duration")
        ),

        "year": song.get("year"),

        "language": clean_text(
            song.get("language")
        ),

        "play_count": safe_int(
            song.get("play_count")
        ),

        "explicit": (
            str(song.get("explicit_content", "0")) == "1"
        ),

        "has_lyrics": bool(
            info.get("has_lyrics")
        ),

        "320kbps": (
            str(info.get("320kbps", "")).lower()
            == "true"
        ),

        # JioSaavn song page
        "song_url": song.get("perma_url"),

        # JioTune/preview link when supplied
        "preview_url": info.get("vlink")
    }


def normalize_playlist(item):
    info = item.get("more_info") or {}

    return {
        "id": (
            item.get("id")
            or item.get("listid")
            or item.get("list_id")
        ),

        "type": "playlist",

        "title": clean_text(
            item.get("title")
            or item.get("listname")
            or item.get("name")
        ),

        "subtitle": clean_text(
            item.get("subtitle")
        ),

        "image": better_image(
            item.get("image")
        ),

        "song_count": safe_int(
            info.get("song_count")
            or item.get("song_count")
            or item.get("list_count")
        ),

        "url": (
            item.get("perma_url")
            or item.get("url")
        )
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

        "subtitle": clean_text(
            item.get("subtitle")
        ),

        "artist": clean_text(
            item.get("music")
            or info.get("music")
            or item.get("primary_artists")
        ),

        "image": better_image(
            item.get("image")
        ),

        "year": item.get("year"),

        "language": clean_text(
            item.get("language")
        ),

        "url": (
            item.get("perma_url")
            or item.get("url")
        )
    }


def normalize_artist(item):
    return {
        "id": (
            item.get("id")
            or item.get("artistid")
            or item.get("artistId")
        ),

        "type": "artist",

        "name": clean_text(
            item.get("title")
            or item.get("name")
        ),

        "subtitle": clean_text(
            item.get("subtitle")
        ),

        "image": better_image(
            item.get("image")
        ),

        "url": (
            item.get("perma_url")
            or item.get("url")
        )
    }


def paginate(items, page, per_page=10):
    page = max(1, page)

    start = (page - 1) * per_page
    end = start + per_page

    sliced = items[start:end]

    total = len(items)

    return sliced, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": math.ceil(total / per_page)
        if total
        else 0,

        "has_previous": page > 1,

        "has_next": end < total,

        "previous_page": (
            page - 1 if page > 1 else None
        ),

        "next_page": (
            page + 1 if end < total else None
        )
    }


# =========================================================
# Root
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "status": True,
        "name": "JioSaavn Music API",
        "version": "1.0",

        "endpoints": {
            "songs":
                "/search?q=Tum Hi Ho&page=1",

            "all":
                "/search/all?q=Arijit&page=1",

            "playlists":
                "/search/playlists?q=Romantic&page=1",

            "albums":
                "/search/albums?q=Aashiqui&page=1",

            "artists":
                "/search/artists?q=Arijit Singh&page=1",

            "playlist_details":
                "/playlist?id=PLAYLIST_ID&page=1",

            "album_details":
                "/album?id=ALBUM_ID&page=1",

            "song_details":
                "/song?id=SONG_ID"
        }
    })


# =========================================================
# SONG SEARCH
# 10 songs per page
# =========================================================

@app.route("/search")
def search_songs():
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page"), 1)

    if page < 1:
        page = 1

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

        raw_results = data.get("results", [])

        songs = [
            normalize_song(song)
            for song in raw_results
        ]

        total = safe_int(data.get("total"), len(songs))

        total_pages = (
            math.ceil(total / PER_PAGE)
            if total
            else 0
        )

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

            "has_next": (
                page < total_pages
                if total_pages
                else False
            ),

            "previous_page": (
                page - 1
                if page > 1
                else None
            ),

            "next_page": (
                page + 1
                if page < total_pages
                else None
            ),

            "results": songs
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Search failed",
            "details": str(e)
        }), 502


# =========================================================
# AUTOCOMPLETE / ALL SEARCH
# Songs + albums + playlists + artists
# =========================================================

@app.route("/search/all")
def search_all():
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page"), 1)

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

        songs_raw = (
            data.get("songs", {}).get("data", [])
            if isinstance(data.get("songs"), dict)
            else data.get("songs", [])
        )

        albums_raw = (
            data.get("albums", {}).get("data", [])
            if isinstance(data.get("albums"), dict)
            else data.get("albums", [])
        )

        playlists_raw = (
            data.get("playlists", {}).get("data", [])
            if isinstance(data.get("playlists"), dict)
            else data.get("playlists", [])
        )

        artists_raw = (
            data.get("artists", {}).get("data", [])
            if isinstance(data.get("artists"), dict)
            else data.get("artists", [])
        )

        songs = [
            normalize_song(x)
            for x in songs_raw
        ]

        albums = [
            normalize_album(x)
            for x in albums_raw
        ]

        playlists = [
            normalize_playlist(x)
            for x in playlists_raw
        ]

        artists = [
            normalize_artist(x)
            for x in artists_raw
        ]

        combined = (
            songs
            + playlists
            + albums
            + artists
        )

        results, pagination = paginate(
            combined,
            page,
            PER_PAGE
        )

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
            "error": "Search failed",
            "details": str(e)
        }), 502


# =========================================================
# PLAYLIST SEARCH
# =========================================================

@app.route("/search/playlists")
def search_playlists():
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page"), 1)

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

        raw = data.get("playlists", [])

        if isinstance(raw, dict):
            raw = raw.get("data", [])

        playlists = [
            normalize_playlist(x)
            for x in raw
        ]

        results, pagination = paginate(
            playlists,
            page,
            PER_PAGE
        )

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
# ALBUM SEARCH
# =========================================================

@app.route("/search/albums")
def search_albums():
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page"), 1)

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

        raw = data.get("albums", [])

        if isinstance(raw, dict):
            raw = raw.get("data", [])

        albums = [
            normalize_album(x)
            for x in raw
        ]

        results, pagination = paginate(
            albums,
            page,
            PER_PAGE
        )

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
# ARTIST SEARCH
# =========================================================

@app.route("/search/artists")
def search_artists():
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page"), 1)

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

        raw = data.get("artists", [])

        if isinstance(raw, dict):
            raw = raw.get("data", [])

        artists = [
            normalize_artist(x)
            for x in raw
        ]

        results, pagination = paginate(
            artists,
            page,
            PER_PAGE
        )

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
# SONG DETAILS
# =========================================================

@app.route("/song")
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

            if song_id in data:
                song = data[song_id]

            elif "songs" in data:
                songs = data.get("songs") or []

                if songs:
                    song = songs[0]

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
# PLAYLIST DETAILS
# Songs 10 per page
# =========================================================

@app.route("/playlist")
def playlist_details():
    playlist_id = request.args.get("id", "").strip()
    page = safe_int(request.args.get("page"), 1)

    if not playlist_id:
        return jsonify({
            "status": False,
            "error": "Missing playlist id"
        }), 400

    if page < 1:
        page = 1

    try:
        # Fetch enough songs to support requested page.
        fetch_count = page * PER_PAGE

        data = saavn_request({
            "__call": "playlist.getDetails",
            "listid": playlist_id,
            "p": 1,
            "n": fetch_count
        })

        raw_songs = (
            data.get("songs")
            or data.get("list")
            or []
        )

        songs = [
            normalize_song(x)
            for x in raw_songs
        ]

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE

        page_songs = songs[start:end]

        total = safe_int(
            data.get("list_count")
            or data.get("song_count")
            or data.get("count"),
            len(songs)
        )

        total_pages = (
            math.ceil(total / PER_PAGE)
            if total
            else 0
        )

        return jsonify({
            "status": True,

            "playlist": {
                "id": (
                    data.get("listid")
                    or data.get("id")
                    or playlist_id
                ),

                "title": clean_text(
                    data.get("listname")
                    or data.get("title")
                    or data.get("name")
                ),

                "image": better_image(
                    data.get("image")
                ),

                "url": (
                    data.get("perma_url")
                    or data.get("url")
                )
            },

            "page": page,
            "per_page": PER_PAGE,
            "count": len(page_songs),
            "total": total,
            "total_pages": total_pages,

            "has_previous": page > 1,
            "has_next": (
                page < total_pages
                if total_pages
                else len(page_songs) == PER_PAGE
            ),

            "previous_page": (
                page - 1
                if page > 1
                else None
            ),

            "next_page": (
                page + 1
                if (
                    page < total_pages
                    or (
                        not total_pages
                        and len(page_songs) == PER_PAGE
                    )
                )
                else None
            ),

            "songs": page_songs
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": "Failed to fetch playlist",
            "details": str(e)
        }), 502


# =========================================================
# ALBUM DETAILS
# Songs 10 per page
# =========================================================

@app.route("/album")
def album_details():
    album_id = request.args.get("id", "").strip()
    page = safe_int(request.args.get("page"), 1)

    if not album_id:
        return jsonify({
            "status": False,
            "error": "Missing album id"
        }), 400

    if page < 1:
        page = 1

    try:
        data = saavn_request({
            "__call": "content.getAlbumDetails",
            "albumid": album_id
        })

        raw_songs = data.get("songs") or []

        songs = [
            normalize_song(x)
            for x in raw_songs
        ]

        page_songs, pagination = paginate(
            songs,
            page,
            PER_PAGE
        )

        return jsonify({
            "status": True,

            "album": {
                "id": (
                    data.get("id")
                    or data.get("albumid")
                    or album_id
                ),

                "title": clean_text(
                    data.get("name")
                    or data.get("title")
                ),

                "artist": clean_text(
                    data.get("primary_artists")
                    or data.get("music")
                ),

                "image": better_image(
                    data.get("image")
                ),

                "year": data.get("year"),

                "language": clean_text(
                    data.get("language")
                ),

                "url": (
                    data.get("perma_url")
                    or data.get("url")
                )
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
