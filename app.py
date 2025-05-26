from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import os

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Global movie cache
comedy_movies_cache = []

def fetch_and_cache_comedy_movies():
    global comedy_movies_cache
    print("[CACHE] Fetching Comedy OTT movies...")

    final_movies = []

    for page in range(1, 1000):
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "with_genres": "35",  # Comedy
            "sort_by": "popularity.desc",
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            results = response.json().get("results", [])

            # ✅ Always continue unless error or empty page
            if results is None or len(results) == 0:
                break

            for movie in results:
                movie_id = movie.get("id")
                title = movie.get("title")
                if not movie_id or not title:
                    continue

                # Check OTT availability globally
                providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                prov_response = requests.get(providers_url, params={"api_key": TMDB_API_KEY})
                prov_data = prov_response.json()

                if "results" in prov_data:
                    has_ott = any(
                        "flatrate" in prov_data["results"].get(region, {})
                        for region in prov_data["results"]
                    )
                    if has_ott:
                        # Get IMDb ID
                        ext_url = f"{TMDB_BASE_URL}/movie/{movie_id}/external_ids"
                        ext_response = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
                        ext_data = ext_response.json()
                        imdb_id = ext_data.get("imdb_id")

                        if imdb_id and imdb_id.startswith("tt"):
                            movie["imdb_id"] = imdb_id
                            final_movies.append(movie)

        except Exception as e:
            print(f"[ERROR] Page {page} failed: {e}")
            break

    # Deduplicate
    seen_ids = set()
    unique_movies = []
    for movie in final_movies:
        imdb_id = movie.get("imdb_id")
        if imdb_id and imdb_id not in seen_ids:
            seen_ids.add(imdb_id)
            unique_movies.append(movie)

    comedy_movies_cache = unique_movies
    print(f"[CACHE] Fetched {len(comedy_movies_cache)} Comedy OTT movies ✅")


def to_stremio_meta(movie):
    try:
        imdb_id = movie.get("imdb_id")
        title = movie.get("title")
        if not imdb_id or not title:
            return None

        return {
            "id": imdb_id,
            "type": "movie",
            "name": title,
            "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "releaseInfo": movie.get("release_date", ""),
            "background": f"https://image.tmdb.org/t/p/w780{movie['backdrop_path']}" if movie.get("backdrop_path") else None
        }
    except Exception as e:
        print(f"[ERROR] to_stremio_meta failed: {e}")
        return None


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.comedy.catalog",
        "version": "1.0.0",
        "name": "Comedy",
        "description": "Comedy Movies available on OTT",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "comedy",
            "name": "Comedy"
        }],
        "idPrefixes": ["tt"]
    })


@app.route("/catalog/movie/comedy.json")
def catalog():
    print("[INFO] Catalog requested")

    try:
        metas = [meta for meta in (to_stremio_meta(m) for m in comedy_movies_cache) if meta]
        print(f"[INFO] Returning {len(metas)} total comedy movies ✅")
        return jsonify({"metas": metas})
    except Exception as e:
        print(f"[ERROR] Catalog error: {e}")
        return jsonify({"metas": []})


@app.route("/refresh")
def refresh():
    def do_refresh():
        try:
            fetch_and_cache_comedy_movies()
            print("[REFRESH] Manual refresh complete ✅")
        except Exception as e:
            import traceback
            print(f"[REFRESH ERROR] {traceback.format_exc()}")

    threading.Thread(target=do_refresh).start()
    return jsonify({"status": "refresh started in background"})


@app.route("/status")
def status():
    return jsonify({
        "cached_movies": len(comedy_movies_cache),
        "example": comedy_movies_cache[0] if comedy_movies_cache else "Still loading..."
    })


# ✅ Start fetch in background to avoid blocking port binding
def run_fetch_in_background():
    def bg():
        try:
            fetch_and_cache_comedy_movies()
        except Exception as e:
            print(f"[STARTUP ERROR] {e}")
    threading.Thread(target=bg).start()

run_fetch_in_background()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
