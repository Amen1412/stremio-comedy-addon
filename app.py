from flask import Flask, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import threading

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

feel_good_cache = []

# IDs: Comedy=35, Drama=18, Romance=10749
FEEL_GOOD_GENRES = {"35", "18", "10749"}
EXCLUDED_GENRES = {"16"}  # Animation (kids-style)

def fetch_feel_good_movies():
    global feel_good_cache
    print("[CACHE] Fetching Feel Good OTT movies...")

    today = datetime.now().strftime("%Y-%m-%d")
    final_movies = []

    for page in range(1, 1000):  # max page limit TMDB allows
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            results = response.json().get("results", [])
            if not results:
                break

            for movie in results:
                movie_id = movie.get("id")
                title = movie.get("title")
                genre_ids = set(str(g) for g in movie.get("genre_ids", []))

                # Genre filter
                if not genre_ids & FEEL_GOOD_GENRES or genre_ids & EXCLUDED_GENRES:
                    continue

                # Skip if already added
                if any(m.get("id") == movie_id for m in final_movies):
                    continue

                # Check OTT availability
                providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                prov_response = requests.get(providers_url, params={"api_key": TMDB_API_KEY})
                prov_data = prov_response.json()

                if "results" in prov_data and any("flatrate" in v for v in prov_data["results"].values()):
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

    feel_good_cache = unique_movies
    print(f"[CACHE] Fetched {len(feel_good_cache)} Feel Good movies ✅")

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
        "id": "org.feelgood.catalog",
        "version": "1.0.0",
        "name": "Feel Good",
        "description": "Feel Good Movies on OTT",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "feelgood",
            "name": "Feel Good"
        }],
        "idPrefixes": ["tt"]
    })

@app.route("/catalog/movie/feelgood.json")
def catalog():
    print("[INFO] Catalog requested")
    try:
        metas = [meta for meta in (to_stremio_meta(m) for m in feel_good_cache) if meta]
        print(f"[INFO] Returning {len(metas)} total movies ✅")
        return jsonify({"metas": metas})
    except Exception as e:
        print(f"[ERROR] Catalog error: {e}")
        return jsonify({"metas": []})

@app.route("/refresh")
def refresh():
    def do_refresh():
        try:
            fetch_feel_good_movies()
            print("[REFRESH] Background refresh complete ✅")
        except Exception as e:
            import traceback
            print(f"[REFRESH ERROR] {traceback.format_exc()}")

    threading.Thread(target=do_refresh).start()
    return jsonify({"status": "refresh started in background"})

# Fetch on startup
fetch_feel_good_movies()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
