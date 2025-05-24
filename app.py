from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import threading

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Global cache
feel_good_movies_cache = []

# Fetch feel-good movies (loose genre/keyword match + OTT filter)
def fetch_and_cache_movies():
    global feel_good_movies_cache
    print("[CACHE] Fetching feel-good OTT movies...")

    today = datetime.now().strftime("%Y-%m-%d")
    final_movies = []
    seen_ids = set()

    # Loop through TMDB pages until exhausted
    for page in range(1, 1000):
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "with_watch_monetization_types": "flatrate",
            "include_adult": False,
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            data = response.json()
            results = data.get("results", [])
            if not results:
                break

            for movie in results:
                if not movie.get("id") or not movie.get("title"):
                    continue

                movie_id = movie["id"]

                # Skip if already added
                if movie_id in seen_ids:
                    continue

                # Check OTT availability
                prov_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                prov_res = requests.get(prov_url, params={"api_key": TMDB_API_KEY})
                prov_data = prov_res.json()
                if not prov_data.get("results") or not prov_data["results"].get("IN"):
                    continue
                if "flatrate" not in prov_data["results"]["IN"]:
                    continue

                # Get IMDb ID
                ext_url = f"{TMDB_BASE_URL}/movie/{movie_id}/external_ids"
                ext_res = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
                ext_data = ext_res.json()
                imdb_id = ext_data.get("imdb_id")

                if imdb_id and imdb_id.startswith("tt"):
                    movie["imdb_id"] = imdb_id
                    final_movies.append(movie)
                    seen_ids.add(movie_id)

        except Exception as e:
            print(f"[ERROR] Page {page} failed: {e}")
            break

    feel_good_movies_cache = final_movies
    print(f"[CACHE] Fetched {len(feel_good_movies_cache)} feel-good OTT movies ✅")

# Convert TMDB movie data to Stremio meta
def to_stremio_meta(movie):
    try:
        return {
            "id": movie["imdb_id"],
            "type": "movie",
            "name": movie["title"],
            "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "releaseInfo": movie.get("release_date", ""),
            "background": f"https://image.tmdb.org/t/p/w780{movie['backdrop_path']}" if movie.get("backdrop_path") else None
        }
    except Exception as e:
        print(f"[ERROR] to_stremio_meta failed: {e}")
        return None

# Stremio manifest
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.feelgood.catalog",
        "version": "1.0.0",
        "name": "Feel Good",
        "description": "Feel-Good & Heartwarming Movies on OTT",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "feelgood",
            "name": "Feel Good"
        }],
        "idPrefixes": ["tt"]
    })

# Catalog endpoint
@app.route("/catalog/movie/feelgood.json")
def catalog():
    print("[INFO] Feel Good catalog requested")
    try:
        metas = [meta for meta in (to_stremio_meta(m) for m in feel_good_movies_cache) if meta]
        print(f"[INFO] Returning {len(metas)} movies ✅")
        return jsonify({"metas": metas})
    except Exception as e:
        print(f"[ERROR] Catalog error: {e}")
        return jsonify({"metas": []})

# Manual refresh
@app.route("/refresh")
def refresh():
    def do_refresh():
        try:
            fetch_and_cache_movies()
            print("[REFRESH] Background refresh complete ✅")
        except Exception as e:
            import traceback
            print(f"[REFRESH ERROR] {traceback.format_exc()}")
    threading.Thread(target=do_refresh).start()
    return jsonify({"status": "refresh started in background"})

# Start background fetch after server is up
threading.Thread(target=fetch_and_cache_movies).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
